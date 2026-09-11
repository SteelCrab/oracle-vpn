#!/usr/bin/env python3
"""oracle-vpn - WireGuard peer management CLI

Manages peers on the Oracle Cloud Mumbai server from your local machine.
Adding a device issues both a config file and a QR code, plus platform-specific
connection instructions.

Private keys are generated locally and never sent to the server; only the
public key is registered.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_settings() -> dict[str, str]:
    """Settings come from config.local (KEY=value), overridden by the environment.

    config.local is gitignored because it holds the server address and the path
    to your SSH key. Copy config.example to get started.
    """
    values: dict[str, str] = {}
    cfg = HERE / "config.local"
    if cfg.is_file():
        for line in cfg.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if k.startswith("OVPN_")})
    return values


_S = load_settings()

SERVER = _S.get("OVPN_SERVER", "")
SSH_USER = _S.get("OVPN_SSH_USER", "ubuntu")
SSH_KEY = os.path.expanduser(_S.get("OVPN_SSH_KEY", ""))
OUT_DIR = Path(_S.get("OVPN_DIR", str(HERE)))

WG_IF = "wg0"
WG_CONF = f"/etc/wireguard/{WG_IF}.conf"
SUBNET = ipaddress.ip_network("10.66.0.0/24")
SERVER_TUN_IP = ipaddress.ip_address("10.66.0.1")
PORT = 51820
DNS = "1.1.1.1"
MTU = 1280

PLATFORMS = ("iphone", "android", "mac", "windows")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,30}$")

# Device names follow <device>-<cookie>. Cookies are handed out in A-Z order,
# so the name alone tells you the registration order.
COOKIES = (
    "almond", "brownie", "chocochip", "donut", "eclair", "financier",
    "ginger", "honey", "icebox", "jam", "kifli", "lemon", "macaron",
    "nougat", "oreo", "pretzel", "quadratini", "raisin", "shortbread",
    "tuile", "ube", "vanilla", "waffle", "walnut", "yogurt", "zebra",
)


# ---------------------------------------------------------------- helpers

def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


def run(cmd: list[str], input_text: str | None = None, check: bool = True) -> str:
    p = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
    if check and p.returncode != 0:
        die(f"command failed: {' '.join(cmd[:3])}...\n{p.stderr.strip()}")
    return p.stdout


def require_settings():
    missing = [k for k, v in (("OVPN_SERVER", SERVER), ("OVPN_SSH_KEY", SSH_KEY)) if not v]
    if missing:
        die(f"missing setting(s): {', '.join(missing)}\n"
            f"Copy config.example to config.local and fill it in:\n"
            f"    cp {HERE / 'config.example'} {HERE / 'config.local'}")
    if not Path(SSH_KEY).is_file():
        die(f"SSH key not found: {SSH_KEY}   (check OVPN_SSH_KEY in config.local)")


def ssh(remote_cmd: str, check: bool = True) -> str:
    require_settings()
    return run(
        ["ssh", "-i", SSH_KEY, "-o", "ConnectTimeout=15",
         "-o", "StrictHostKeyChecking=accept-new",
         f"{SSH_USER}@{SERVER}", remote_cmd],
        check=check,
    )


def check_name(name: str) -> str:
    if not NAME_RE.match(name):
        die("names may contain letters, digits, '-' and '_' only (e.g. phone, mac, work-ipad)")
    return name


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TiB"


def fmt_ago(ts: int) -> str:
    if ts == 0:
        return "-"
    d = int(time.time()) - ts
    if d < 60:
        return f"{d}s ago"
    if d < 3600:
        return f"{d // 60}m ago"
    if d < 86400:
        return f"{d // 3600}h ago"
    return f"{d // 86400}d ago"


# ---------------------------------------------------------------- server queries

def server_pubkey() -> str:
    key = ssh("sudo cat /etc/wireguard/server_public.key").strip()
    if not key:
        die("could not read the server public key")
    return key


def peers_from_conf() -> list[dict]:
    """Parse the server's wg0.conf into [{name, pubkey, ip}]."""
    text = ssh(f"sudo cat {WG_CONF}")
    peers, cur = [], None
    for line in text.splitlines():
        s = line.strip()
        if s == "[Peer]":
            cur = {"name": "", "pubkey": "", "ip": ""}
            peers.append(cur)
        elif cur is not None:
            if s.startswith("#") and not cur["name"]:
                cur["name"] = s.lstrip("#").strip()
            elif s.startswith("PublicKey"):
                cur["pubkey"] = s.split("=", 1)[1].strip()
            elif s.startswith("AllowedIPs"):
                cur["ip"] = s.split("=", 1)[1].strip().split("/")[0]
    return [p for p in peers if p["pubkey"]]


def live_status() -> dict[str, dict]:
    """Live connection state from `wg show dump`, keyed by public key."""
    out = ssh(f"sudo wg show {WG_IF} dump", check=False)
    status = {}
    for line in out.splitlines()[1:]:          # first line describes the interface
        f = line.split("\t")
        if len(f) < 8:
            continue
        status[f[0]] = {
            "endpoint": f[2],
            "handshake": int(f[4]),
            "rx": int(f[5]),
            "tx": int(f[6]),
        }
    return status


def next_cookie(peers: list[dict]) -> str:
    """Pick the next unused cookie in alphabetical order."""
    used = {p["name"].rsplit("-", 1)[1] for p in peers if "-" in p["name"]}
    for c in COOKIES:
        if c not in used:
            return c
    n = 2                                   # past 26 devices: almond2, brownie2, ...
    while True:
        for c in COOKIES:
            if f"{c}{n}" not in used:
                return f"{c}{n}"
        n += 1


def next_free_ip(peers: list[dict]) -> str:
    used = {SERVER_TUN_IP} | {ipaddress.ip_address(p["ip"]) for p in peers if p["ip"]}
    for host in SUBNET.hosts():
        if host not in used:
            return str(host)
    die("no free addresses left in the tunnel subnet")


def resolve_name(name: str, peers: list[dict] | None = None) -> str:
    """Allow a prefix: 'mac' resolves to 'mac-brownie'."""
    names = [p["name"] for p in (peers if peers is not None else peers_from_conf())]
    if name in names:
        return name
    hits = [n for n in names if n.startswith(name + "-")]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        die(f"'{name}' matches several devices: {', '.join(hits)}")
    die(f"no such device: {name}   (run 'list' to see them)")


def local_conf(name: str) -> Path:
    exact = OUT_DIR / f"{name}.conf"
    if exact.is_file():
        return exact
    hits = sorted(OUT_DIR.glob(f"{name}-*.conf"))
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        die(f"'{name}' matches several configs: {', '.join(h.stem for h in hits)}")
    die(f"config not found: {exact}")


# ---------------------------------------------------------------- QR

def qr_terminal(conf_path: Path) -> bool:
    """Render locally only: the config contains the client's private key."""
    if have("qrencode"):
        sys.stdout.write(run(["qrencode", "-t", "ansiutf8", "-r", str(conf_path)]))
        return True
    return False


def qr_png(conf_path: Path, png_path: Path) -> bool:
    if have("qrencode"):
        run(["qrencode", "-t", "png", "-s", "8", "-o", str(png_path), "-r", str(conf_path)])
        png_path.chmod(0o600)
        return True
    return False


# ---------------------------------------------------------------- commands

def cmd_add(args):
    peers = peers_from_conf()

    if args.name:                            # explicit name
        name = check_name(args.name)
    else:                                    # generated <device>-<cookie>
        device = check_name(args.device)
        name = f"{device}-{next_cookie(peers)}"

    if any(p["name"] == name for p in peers):
        die(f"name already in use: {name}  (use 'qr {name}' to reissue)")

    if not have("wg"):
        die("wireguard-tools is required:  brew install wireguard-tools")

    priv = run(["wg", "genkey"]).strip()
    pub = run(["wg", "pubkey"], input_text=priv).strip()
    ip = next_free_ip(peers)
    srv_pub = server_pubkey()

    # Apply live with `wg set` and append to the config for persistence.
    # No service restart, so existing connections stay up.
    block = f"\n[Peer]\n# {name}\nPublicKey = {pub}\nAllowedIPs = {ip}/32\n"
    ssh(
        f"sudo wg set {WG_IF} peer {shlex.quote(pub)} allowed-ips {ip}/32 && "
        f"printf %s {shlex.quote(block)} | sudo tee -a {WG_CONF} >/dev/null"
    )

    conf = (
        f"[Interface]\n"
        f"PrivateKey = {priv}\n"
        f"Address = {ip}/{SUBNET.prefixlen}\n"
        f"DNS = {DNS}\n"
        f"MTU = {MTU}\n\n"
        f"[Peer]\n"
        f"PublicKey = {srv_pub}\n"
        f"Endpoint = {SERVER}:{PORT}\n"
        # Capture IPv6 too. The server peer permits IPv4 sources only,
        # so IPv6 is dropped rather than bypassing the VPN.
        f"AllowedIPs = 0.0.0.0/0, ::/0\n"
        f"PersistentKeepalive = 25\n"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conf_path = OUT_DIR / f"{name}.conf"
    conf_path.write_text(conf)
    conf_path.chmod(0o600)

    print(f"added: {name}  ({ip})")
    print(f"  config: {conf_path}")

    png_path = OUT_DIR / f"{name}-qr.png"
    if qr_png(conf_path, png_path):
        print(f"  QR image: {png_path}")
    else:
        print("  QR image: skipped - qrencode not installed (brew install qrencode)")

    if args.platform in ("iphone", "android") or args.platform is None:
        print()
        if not qr_terminal(conf_path):
            print("  (cannot render QR - install qrencode, then run 'qr')")
    print()
    print_hint(args.platform, conf_path)


def print_hint(platform: str | None, conf_path: Path):
    if platform == "iphone":
        print("iPhone: install WireGuard from the App Store, then + > Scan from QR code")
    elif platform == "android":
        print("Android: install WireGuard from Google Play, then + > Scan from QR code")
    elif platform == "mac":
        print(f"macOS:  sudo wg-quick up {conf_path}")
        print("        or import the .conf into the WireGuard app from the App Store")
    elif platform == "windows":
        print("Windows: install the client from wireguard.com/install")
        print(f"         Add Tunnel > Import from file > {conf_path.name}")
    else:
        print("Mobile: scan the QR above in the WireGuard app.")
        print(f"Desktop: import {conf_path.name}, or run  sudo wg-quick up {conf_path}")


def cmd_list(args):
    peers = peers_from_conf()
    if not peers:
        print("no devices registered")
        return
    status = live_status()

    rows = []
    for p in peers:
        st = status.get(p["pubkey"], {})
        hs = st.get("handshake", 0)
        online = hs and (time.time() - hs) < 180
        rows.append((
            "*" if online else " ",
            p["name"] or "(unnamed)",
            p["ip"],
            fmt_ago(hs),
            fmt_bytes(st.get("rx", 0)),
            fmt_bytes(st.get("tx", 0)),
            (st.get("endpoint") or "-").rsplit(":", 1)[0],
        ))

    head = ("", "NAME", "ADDRESS", "LAST SEEN", "RX", "TX", "SOURCE")
    widths = [max(len(str(r[i])) for r in (rows + [head])) for i in range(len(head))]
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(head)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)))
    print(f"\n* active within the last 3 minutes   {len(rows)} device(s)")


def cmd_qr(args):
    name = resolve_name(check_name(args.name))
    conf_path = OUT_DIR / f"{name}.conf"
    if not conf_path.is_file():
        die(f"no local config: {conf_path}\n"
            f"The private key is not stored on the server and cannot be recovered.\n"
            f"Run 'rm {name}' then 'add' to issue a new one.")
    png_path = OUT_DIR / f"{name}-qr.png"
    if qr_png(conf_path, png_path):
        print(f"QR image: {png_path}\n")
    if not qr_terminal(conf_path):
        die("no QR encoder available:  brew install qrencode")


def cmd_rename(args):
    peers = peers_from_conf()
    old = resolve_name(check_name(args.old), peers)
    new = check_name(args.new)
    if any(p["name"] == new for p in peers):
        die(f"name already in use: {new}")

    pub = next(p["pubkey"] for p in peers if p["name"] == old)
    ssh(
        f"sudo python3 - {shlex.quote(pub)} {shlex.quote(new)} <<'EOF_PY'\n"
        "import sys\n"
        "pub, new = sys.argv[1], sys.argv[2]\n"
        f"p = '{WG_CONF}'\n"
        "out, blocks = [], open(p).read().split('[Peer]')\n"
        "out.append(blocks[0])\n"
        "for b in blocks[1:]:\n"
        "    if pub in b:\n"
        "        lines = b.splitlines(True)\n"
        "        b = ''.join(('# ' + new + '\\n') if l.strip().startswith('#') else l for l in lines)\n"
        "    out.append('[Peer]' + b)\n"
        "open(p, 'w').write(''.join(out))\n"
        "EOF_PY"
    )
    for suffix in (".conf", "-qr.png"):
        src, dst = OUT_DIR / f"{old}{suffix}", OUT_DIR / f"{new}{suffix}"
        if src.exists():
            src.rename(dst)
    print(f"renamed: {old} -> {new}")


def cmd_rm(args):
    peers = peers_from_conf()
    name = resolve_name(check_name(args.name), peers)
    target = next(p for p in peers if p["name"] == name)

    if not args.yes:
        ans = input(f"Remove '{name}' ({target['ip']})? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("cancelled")
            return

    pub = target["pubkey"]
    # Revoke immediately, then drop the [Peer] block from the config file.
    ssh(
        f"sudo wg set {WG_IF} peer {shlex.quote(pub)} remove && "
        f"sudo python3 - {shlex.quote(pub)} <<'EOF_PY'\n"
        "import sys\n"
        "pub = sys.argv[1]\n"
        f"p = '{WG_CONF}'\n"
        "blocks = open(p).read().split('[Peer]')\n"
        "kept = [blocks[0]] + ['[Peer]' + b for b in blocks[1:] if pub not in b]\n"
        "open(p, 'w').write(''.join(kept))\n"
        "EOF_PY"
    )
    for f in (OUT_DIR / f"{name}.conf", OUT_DIR / f"{name}-qr.png"):
        if f.exists():
            f.unlink()
    print(f"removed: {name}  (revoked on server, local files deleted)")


def cmd_status(args):
    print(ssh(f"sudo wg show {WG_IF}").rstrip())
    print()
    ip = run(["curl", "-s", "--max-time", "10", "https://ipinfo.io/ip"], check=False).strip()
    if ip:
        where = "India - VPN active" if ip == SERVER else "VPN not in use"
        print(f"This machine's egress IP: {ip}  ->  {where}")


def cmd_up(args):
    conf_path = local_conf(check_name(args.name))
    print("connecting (sudo may prompt for your password)...")
    subprocess.run(["sudo", "wg-quick", "up", str(conf_path)])


def live_tunnels() -> list[str]:
    """Tunnel names wg-quick currently has up on this machine."""
    d = Path("/var/run/wireguard")
    return sorted(p.stem for p in d.glob("*.name")) if d.is_dir() else []


def cmd_down(args):
    name = check_name(args.name)
    up = live_tunnels()

    # wg-quick registers a tunnel under the config's filename at the time it was
    # brought up. Renaming the file afterwards orphans that name, so `down`
    # cannot find it. Fall back to whatever is actually running.
    conf_path = local_conf(name)
    if up and conf_path.stem not in up:
        match = next((t for t in up if t.startswith(name.split("-")[0])), None)
        if match:
            print(f"note: this tunnel is running as '{match}', not '{conf_path.stem}'")
            print("      (the config was renamed after it was brought up)")
            tmp = conf_path.with_name(f"{match}.conf")
            tmp.write_text(conf_path.read_text())
            tmp.chmod(0o600)
            try:
                subprocess.run(["sudo", "wg-quick", "down", str(tmp)])
            finally:
                tmp.unlink(missing_ok=True)
            return
        print(f"note: no tunnel named '{conf_path.stem}' is up. Running: {', '.join(up) or 'none'}")

    subprocess.run(["sudo", "wg-quick", "down", str(conf_path)])


# ---------------------------------------------------------------- entry point

def main():
    ap = argparse.ArgumentParser(
        prog="vpnctl.py",
        description="oracle-vpn peer management - issues a config and QR code per device.",
        epilog=f"server: {SERVER or '(unset - see config.example)'}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser(
        "add", help="register a device (config + QR)",
        description="Names are generated as <device>-<cookie>, e.g. phone -> phone-almond",
    )
    p.add_argument("device", help="device kind (e.g. phone, mac, ipad)")
    p.add_argument("-p", "--platform", choices=PLATFORMS, help="print platform-specific setup steps")
    p.add_argument("-n", "--name", help="use this exact name instead of generating one")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="show devices and connection state")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("qr", help="reprint a device's QR code")
    p.add_argument("name")
    p.set_defaults(func=cmd_qr)

    p = sub.add_parser("rm", help="remove a device (revokes access)")
    p.add_argument("name")
    p.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    p.set_defaults(func=cmd_rm)

    p = sub.add_parser("rename", help="rename a device")
    p.add_argument("old")
    p.add_argument("new")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("status", help="server state and current egress IP")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("up", help="connect this machine (macOS)")
    p.add_argument("name", nargs="?", default="mac")
    p.set_defaults(func=cmd_up)

    p = sub.add_parser("down", help="disconnect this machine (macOS)")
    p.add_argument("name", nargs="?", default="mac")
    p.set_defaults(func=cmd_down)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
