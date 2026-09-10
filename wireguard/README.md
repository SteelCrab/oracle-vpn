# WireGuard

[← Overview](../README.md) · [Shadowsocks + Outline](../shadowsocks/README.md)

Per-device keys, managed from your own machine with `vpnctl.py`. Revoke one
device without touching the others.

Start to finish: about 30 minutes.

```
0. Account → 1. Network → 2. Security → 3. Instance → 4. Admin setup → 5. Add a device → 6. Verify
   Home Region  VCN         open 51820    attach the     config.local    vpnctl.py add   handshake +
   = Mumbai     wizard                    init script                    → QR / .conf    egress IP
```

Want something simpler? [Shadowsocks + Outline](../shadowsocks/README.md) needs no
admin machine and shares one link
([comparison](../README.md#pick-a-method)).

---

## 0. Account

Skip if you already have an Oracle Cloud account in an Indian region.

Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/). During
signup you are asked for a **Home Region** — pick **India West (Mumbai)** or
**India South (Hyderabad)**.

> **This is the one choice you cannot undo.** The Home Region is fixed for the
> life of the account. Pick anything else and the VPN exits from that country
> instead, and the only fix is a new account. Everything after this step is
> reversible; this is not.

A credit card is required for identity verification. Always Free resources stay
free — the card is not charged as long as you stay within the limits.

## 1. Network

Console → **Networking → Virtual Cloud Networks → Create VCN → VCN with Internet Connectivity**.

- Name: `vpn-vcn`
- Leave every default, click through to **Create**

The wizard creates the VCN, a public subnet, an Internet Gateway and a route
table together. Doing this by hand means creating all four yourself.

## 2. Security

Console → **Networking → VCN → your subnet → Default Security List → Add Ingress Rules**.

| Source CIDR | IP Protocol | Destination Port |
|---|---|---|
| `0.0.0.0/0` | UDP | `51820` |

Note **UDP**, not TCP. SSH (TCP 22) is already open from the wizard.

## 3. Instance

Console → **Compute → Instances → Create Instance**.

| Field | Value |
|---|---|
| Name | `vpn` |
| Image | **Canonical Ubuntu** 22.04 or 24.04 — not Oracle Linux |
| Shape | `VM.Standard.E2.1.Micro` — marked *Always Free eligible* |
| Subnet | the public subnet from step 1 |
| Public IPv4 address | **Assign** |
| SSH keys | **Generate a key pair**, then download the private key |

Then: **Show advanced options → Management → Initialization script**

- Select **Choose a cloud-init script file**
- Upload `wireguard/install.sh`
- Do **not** paste it as text — the field strips newlines and Create fails with `Incorrectly formatted request`

Click **Create**. Wait for **Running**, then ~2 minutes more for cloud-init.

> `Out of host capacity` — the free pool is empty right now. Retry, or pick a
> different Availability Domain.
> `Too many requests` — Create was clicked repeatedly. Wait 5–10 min, click once.

Verify over SSH:

macOS / Linux:

```bash
chmod 600 ~/Downloads/ssh-key-*.key          # OCI downloads it world-readable
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<server-ip>
```

Windows — PowerShell, no extra software (OpenSSH ships with Windows 10+):

```powershell
icacls .\ssh-key.key /inheritance:r
icacls .\ssh-key.key /grant:r "$env:USERNAME:R"
ssh -i .\ssh-key.key ubuntu@<server-ip>
```

`icacls` is the Windows equivalent of `chmod 600` — without it `ssh` refuses the
key as too permissive.

Then, on the server:

```bash
sudo cloud-init status --wait                # blocks until done
sudo systemctl is-active wg-quick@wg0        # expect: active
```

## 4. Admin setup

Unlike Shadowsocks, WireGuard is driven from **your** machine. Do this once.

- macOS: `brew install wireguard-tools qrencode`
- Linux: `sudo apt install wireguard-tools qrencode`

> **macOS or Linux only.** Windows is not supported as an admin machine —
> use [Shadowsocks + Outline](../shadowsocks/README.md), which needs no admin
> machine at all.

| Package | For | Required |
|---|---|---|
| `wireguard-tools` | generating keys, connecting from this machine | yes |
| `qrencode` | QR codes as PNG files | optional — terminal QR still works |
| Python 3.9+ | `vpnctl.py`, standard library only | yes — preinstalled on macOS and in WSL |

Point the CLI at your server:

```bash
cd oracle-vpn/wireguard
cp config.example config.local
```

```ini
OVPN_SERVER=203.0.113.10                 # the instance's public IP
OVPN_SSH_USER=ubuntu
OVPN_SSH_KEY=~/Downloads/ssh-key-2026-01-15.key
```

Confirm it reaches the server:

```bash
./vpnctl.py list        # "no devices registered" on a fresh server is correct
```

`config.local` is gitignored. Environment variables of the same name win over it.

## 5. Add a device

```bash
./vpnctl.py add phone -p iphone     # prints a QR + writes phone-almond.conf
./vpnctl.py add mac   -p mac
```

Names are generated `<device>-<cookie>`, cookies in A–Z order, so the name shows
registration order: `phone-almond`, `mac-brownie`, `ipad-chocochip`.

- Picks a free tunnel address, registers the peer, writes `<name>.conf` and a QR PNG
- Existing connections stay up — applied live with `wg set`, no restart
- `-n <name>` to name it yourself

Then connect:

| Platform | Steps |
|---|---|
| **iPhone / Android** | Install **WireGuard** from the App Store or Play → **+ → Scan from QR code** → toggle on |
| **Windows** | Install from [wireguard.com/install](https://www.wireguard.com/install/) → **Add Tunnel → Import from file** → select the `.conf` → **Activate** |
| **macOS** | `./vpnctl.py up mac` — or import the `.conf` into the App Store app and toggle from the menu bar |

## 6. Verify

With the tunnel on:

```bash
./vpnctl.py status          # peers, last handshake, and this machine's egress IP
curl ifconfig.me            # the server's IP
```

`status` should show a handshake within the last couple of minutes for the device
you just connected. On mobile, open `ifconfig.me` in a browser.

A recent handshake but an unchanged egress IP means the tunnel is up and carrying
nothing — see [Connects, but no internet](#connects-but-no-internet).

> Turn the tunnel off when done — it routes everything through Mumbai at ~230 ms.

---

## Managing devices

```bash
./vpnctl.py add <device> [-p iphone|android|mac|windows]   # register + QR
./vpnctl.py list                                            # devices and status
./vpnctl.py qr <name>                                       # reprint a QR
./vpnctl.py rm <name>                                       # revoke one device
./vpnctl.py rename <old> <new>
./vpnctl.py status                                          # server + egress IP
./vpnctl.py up|down [name]                                  # connect this machine (macOS/Linux)
```

Prefixes resolve — `./vpnctl.py up mac` finds `mac-brownie`.

```
$ ./vpnctl.py list
   NAME          ADDRESS    LAST SEEN  RX        TX        SOURCE
-  ------------  ---------  ---------  --------  --------  -------------
*  phone-almond  10.66.0.3  57s ago    3.8MiB    16.6MiB   198.51.100.24
*  mac-brownie   10.66.0.4  34s ago    227.5MiB  454.7MiB  198.51.100.77

* active within the last 3 minutes   2 device(s)
```

Private keys are generated **locally** and never sent to the server — only public
keys are registered. Tunnel subnet is `10.66.0.0/24`; the server holds `.1`,
clients get the lowest free address from `.2`.

---

## Troubleshooting

### Connects, but no internet

Handshake succeeds, nothing loads. Looks like slowness; is a complete block.

Oracle images ship `REJECT all` in the FORWARD chain, and `iptables -A FORWARD`
**appends** below it — so VPN traffic hits the REJECT first. The handshake still
works because it goes through INPUT, not FORWARD.

```bash
sudo iptables -L FORWARD -n -v --line-numbers    # REJECT climbing, wg0 ACCEPT at 0?
sudo iptables -I FORWARD 1 -i wg0 -j ACCEPT
sudo iptables -I FORWARD 2 -o wg0 -j ACCEPT
sudo netfilter-persistent save
```

Took the tunnel from 0 to 36 Mbps. Nothing else helps until this is fixed.
`install.sh` already uses `-I`.

### Traffic starts, then stalls

MTU. Set `MTU = 1280` in `[Interface]` on both ends. Most common on IPv6-only
mobile networks, where the endpoint appears as NAT64 (`[64:ff9b::...]` — the
trailing hex is the server's IPv4).

```bash
sudo sed -i '/^\[Interface\]/a MTU = 1280' /etc/wireguard/wg0.conf
sudo systemctl restart wg-quick@wg0
```

### `is not a WireGuard interface` on down

The config was renamed after the tunnel came up. `wg-quick` names the interface
after the filename at that moment. `vpnctl.py down` detects this and falls back
to the running name; `sudo wg show` lists what is actually up.

### Leaked config

```bash
./vpnctl.py rm <name>       # revokes on the server, deletes local files
./vpnctl.py add <device>    # issue a fresh one
```

Other devices are unaffected.

---

## What gets installed

| Path | Purpose |
|---|---|
| `/etc/wireguard/wg0.conf` | server config, keys, PostUp/PostDown firewall rules |
| `/etc/wireguard/peers/` | per-device keys and configs |
| `/usr/local/bin/add-vpn-peer.sh` | on-server device registration (alternative to `vpnctl.py`) |
| `wg-quick@wg0` | systemd unit; PostUp installs the firewall and NAT rules |

Running the install script again generates a **fresh server keypair** and
replaces `wg0.conf`, invalidating every registered device.
