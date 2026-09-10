#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 boolean true" | debconf-set-selections

apt-get update
apt-get install -y wireguard qrencode iptables-persistent curl

echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
sysctl -p

umask 077
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key

IFACE=$(ip -4 route ls table main | awk '/^default/ {print $5; exit}')
SRV_PRIV=$(cat /etc/wireguard/server_private.key)

cat > /etc/wireguard/wg0.conf <<CONF
[Interface]
Address = 10.66.0.1/24
ListenPort = 51820
MTU = 1280
PrivateKey = $SRV_PRIV
PostUp = iptables -I FORWARD 1 -i wg0 -j ACCEPT; iptables -I FORWARD 2 -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o $IFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o $IFACE -j MASQUERADE
CONF
chmod 600 /etc/wireguard/wg0.conf

iptables -I INPUT -p udp --dport 51820 -j ACCEPT
netfilter-persistent save

systemctl enable --now wg-quick@wg0

mkdir -p /etc/wireguard/peers

cat > /usr/local/bin/add-vpn-peer.sh <<'PEEREOF'
#!/usr/bin/env bash
set -euo pipefail
NAME="${1:?usage: add-vpn-peer.sh <name>}"
DIR=/etc/wireguard/peers
mkdir -p "$DIR"
umask 077

PRIV="$DIR/${NAME}_private.key"
PUB="$DIR/${NAME}_public.key"
if [[ -f "$PRIV" ]]; then
  echo "peer name already exists: $NAME" >&2
  exit 1
fi

wg genkey | tee "$PRIV" | wg pubkey > "$PUB"

N=$(( $(ls "$DIR"/*_public.key 2>/dev/null | wc -l) + 1 ))
CLIENT_IP="10.66.0.$((N + 1))"
SERVER_PUB=$(cat /etc/wireguard/server_public.key)
ENDPOINT="$(curl -s ifconfig.me):51820"

{
  echo ""
  echo "[Peer]"
  echo "# $NAME"
  echo "PublicKey = $(cat "$PUB")"
  echo "AllowedIPs = $CLIENT_IP/32"
} >> /etc/wireguard/wg0.conf

systemctl restart wg-quick@wg0

CLIENT_CONF="$DIR/${NAME}.conf"
cat > "$CLIENT_CONF" <<CONF
[Interface]
PrivateKey = $(cat "$PRIV")
Address = $CLIENT_IP/24
DNS = 1.1.1.1
MTU = 1280

[Peer]
PublicKey = $SERVER_PUB
Endpoint = $ENDPOINT
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
CONF

echo "client config created: $CLIENT_CONF"
echo
qrencode -t ansiutf8 -l L < "$CLIENT_CONF"
PEEREOF
chmod +x /usr/local/bin/add-vpn-peer.sh

echo "=== WireGuard server public key ==="
cat /etc/wireguard/server_public.key
