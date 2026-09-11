#!/bin/bash
# Install shadowsocks-rust as a systemd service, alongside an existing
# WireGuard setup. No Docker required.
#
# Clients connect with the Outline app (or any Shadowsocks client) using the
# ss:// URL this script prints.
#
# Two ways to run it:
#   1. As the instance Initialization script (cloud-init) when creating the VM.
#      Upload this file as-is; it runs at first boot with the default port.
#   2. Over SSH on a VM that is already running:
#        sudo bash install-shadowsocks.sh [port]
#
# Either way the ss:// URL is printed and saved to /root/ss-url.txt
set -euo pipefail

VERSION="v1.25.0"
PORT="${1:-8388}"
# chacha20-ietf-poly1305 is what every Shadowsocks client supports, Outline
# included. The newer AEAD-2022 ciphers (2022-blake3-*) work with the
# shadowsocks-rust client but Outline rejects them as an invalid access key.
METHOD="chacha20-ietf-poly1305"
CONF_DIR=/etc/shadowsocks
BIN=/usr/local/bin/ssserver

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }

# musl builds are statically linked; the gnu ones need a newer glibc than
# Ubuntu 22.04 ships (they want GLIBC_2.38+).
case "$(uname -m)" in
  x86_64)  ARCH=x86_64-unknown-linux-musl ;;
  aarch64) ARCH=aarch64-unknown-linux-musl ;;
  *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive
echo 'iptables-persistent iptables-persistent/autosave_v4 boolean true' | debconf-set-selections
echo 'iptables-persistent iptables-persistent/autosave_v6 boolean true' | debconf-set-selections
apt-get update
apt-get install -y curl ca-certificates xz-utils iptables-persistent
systemctl enable netfilter-persistent

echo "==> downloading shadowsocks-rust $VERSION ($ARCH)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
URL="https://github.com/shadowsocks/shadowsocks-rust/releases/download/${VERSION}/shadowsocks-${VERSION}.${ARCH}.tar.xz"
curl -fsSL "$URL" -o "$TMP/ss.tar.xz"
tar -xJf "$TMP/ss.tar.xz" -C "$TMP"
install -m 755 "$TMP/ssserver" "$BIN"
"$BIN" --version

echo "==> writing config"
mkdir -p "$CONF_DIR"
PSK=$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | head -c 24)
cat > "$CONF_DIR/config.json" <<CONF
{
    "server": "0.0.0.0",
    "server_port": $PORT,
    "method": "$METHOD",
    "password": "$PSK",
    "mode": "tcp_and_udp",
    "timeout": 300
}
CONF
# The service runs as a dedicated system user, so the config must be readable
# by that user - not root-only.
id -u shadowsocks >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin shadowsocks
chown root:shadowsocks "$CONF_DIR/config.json"
chmod 640 "$CONF_DIR/config.json"

echo "==> installing systemd unit"
cat > /etc/systemd/system/shadowsocks.service <<'UNIT'
[Unit]
Description=Shadowsocks-rust server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ssserver -c /etc/shadowsocks/config.json
Restart=on-failure
RestartSec=3
LimitNOFILE=51200
User=shadowsocks
Group=shadowsocks
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadOnlyPaths=/etc/shadowsocks

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable shadowsocks
# A rerun rotates the key; enable --now would leave an active process
# serving the old configuration and accepting the revoked key.
systemctl restart shadowsocks

echo "==> opening the host firewall"
# Insert before Oracle's default REJECT rule, which sits in INPUT.
iptables -I INPUT 1 -p tcp --dport "$PORT" -j ACCEPT
iptables -I INPUT 2 -p udp --dport "$PORT" -j ACCEPT
netfilter-persistent save

sleep 1
systemctl is-active --quiet shadowsocks && echo "service: running" || {
  echo "service failed to start:" >&2
  journalctl -u shadowsocks -n 20 --no-pager >&2
  exit 1
}

IP=$(curl -s --max-time 10 ifconfig.me || echo "<server-ip>")
TAG="oracle-vpn"
# SIP002 userinfo is base64("method:key") regardless of cipher. Verified against
# the shadowsocks-rust client, which rejects a percent-encoded userinfo outright.
USERINFO=$(printf '%s:%s' "$METHOD" "$PSK" | base64 -w0 2>/dev/null || printf '%s:%s' "$METHOD" "$PSK" | base64)

SS_URL="ss://${USERINFO}@${IP}:${PORT}#${TAG}"

# Persist it: when this runs as a cloud-init script there is no terminal to
# read, so the URL has to be fetchable over SSH afterwards.
umask 077
printf '%s\n' "$SS_URL" > /root/ss-url.txt

cat <<EOF

================================================================
  shadowsocks-rust is running on port $PORT

  $SS_URL

  Paste that URL into the Outline app (or any Shadowsocks client).
  Saved to /root/ss-url.txt

  Still to do: allow TCP+UDP $PORT in the OCI Security List.
  The host firewall is already open; the cloud one is separate.
================================================================
EOF
