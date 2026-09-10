# Shadowsocks + Outline

[← Overview](../README.md) · [WireGuard](../wireguard/README.md)

**Recommended.** One `ss://` link is the whole credential — paste it into the
Outline app and connect. Nothing to install on your own machine.

Start to finish: about 20 minutes.

```
0. Account → 1. Network → 2. Security → 3. Instance → 4. Get the key → 5. Connect → 6. Verify
   Home Region  VCN         open 8388     attach the     SSH in, read     Outline     egress IP
   = Mumbai     wizard                    init script    ss-url.txt       app         is India
```

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

Open the port before the VM exists — a missing rule is the #1 cause of "invalid
access key" later.

Console → **Networking → VCN → your subnet → Default Security List → Add Ingress Rules**.

Add **two** rules (OCI does not accept TCP+UDP in one):

| Source CIDR | IP Protocol | Destination Port |
|---|---|---|
| `0.0.0.0/0` | TCP | `8388` |
| `0.0.0.0/0` | UDP | `8388` |

SSH (TCP 22) is already open by default from the wizard.

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

Then, in the same form: **Show advanced options → Management → Initialization script**

- Select **Choose a cloud-init script file**
- Upload `shadowsocks/install.sh`
- Do **not** paste it as text — the field strips newlines and Create fails with `Incorrectly formatted request`

Click **Create**. The instance boots and installs itself; the key exists ~2
minutes after the state turns **Running**.

> `Out of host capacity` — the free pool is empty right now. Retry, or pick a
> different Availability Domain in the form.
> `Too many requests` — Create was clicked repeatedly. Wait 5–10 min, click once.

## 4. Get the key

Copy the instance's **Public IP address** from its details page, then:

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

On the server:

```bash
sudo systemctl is-active shadowsocks         # expect: active
sudo cat /root/ss-url.txt                    # the ss:// link
```

Not active yet? cloud-init may still be running:

```bash
sudo cloud-init status --wait                # blocks until done
sudo tail -30 /var/log/cloud-init-output.log
```

## 5. Connect

Install **Outline** from [getoutline.org](https://getoutline.org/) — macOS,
Windows, Linux, iOS, Android.

1. Copy the `ss://` line from step 4
2. Open Outline — it reads the clipboard and offers to add the server
3. If it does not, tap **+** and paste
4. **Connect**

Sharing with someone else: send them the same `ss://` line and these four app
steps. They never touch a terminal.

## 6. Verify

With the tunnel on, from the client:

```bash
curl ifconfig.me            # the server's IP
curl -s ipinfo.io/city      # Mumbai
```

No terminal on the device? Open `ifconfig.me` in a browser instead.

If the IP is still your own, the tunnel is not carrying traffic — see
[Troubleshooting](#troubleshooting).

> Disconnect when you are done. Leaving it on routes everything through Mumbai
> and adds ~230 ms to every request.

---

## Rotating the key

One shared key, so this cuts off everyone at once. Re-run the installer:

```bash
ssh -i ~/path/to/ssh-key.key ubuntu@<server-ip>
sudo bash /tmp/install.sh 8388    # or scp the script again first
sudo cat /root/ss-url.txt                     # new link
```

For per-device revocation, use [WireGuard](../wireguard/README.md) instead.

> The `ss://` URL **is** the credential. Anyone holding it can use the VPN. Send
> it privately; never commit or post it.

---

## Troubleshooting

### "Invalid access key" in Outline

Outline shows this for **any** unreachable server, not just a malformed key.
Check in this order.

**1. Port open?** From your own machine:

```bash
# macOS / Linux
python3 -c "
import socket
s = socket.socket(); s.settimeout(6)
print('open' if s.connect_ex(('<server-ip>', 8388)) == 0 else 'blocked')
"
```

```powershell
# Windows
Test-NetConnection <server-ip> -Port 8388      # TcpTestSucceeded : True
```

Closed → the step 2 Security List rule is missing or wrong. Most common cause.

**2. Cipher supported?** Outline does not support the AEAD-2022 ciphers
(`2022-blake3-*`), even though other Shadowsocks clients do. A server using one
produces this exact error with a perfectly valid key.

```bash
sudo grep method /etc/shadowsocks/config.json    # expect: chacha20-ietf-poly1305
```

`install.sh` defaults to `chacha20-ietf-poly1305` for this reason.

**3. URL intact?** Copying through a chat app can insert line breaks. It is one
line, no spaces. Re-read it with `sudo cat /root/ss-url.txt`.

### Service will not start

```bash
sudo journalctl -u shadowsocks -n 20 --no-pager
```

- `Permission denied` on the config — must be readable by the `shadowsocks` user: `chown root:shadowsocks /etc/shadowsocks/config.json`, `chmod 640`
- `GLIBC_2.38 not found` — the gnu build needs a newer glibc than Ubuntu 22.04 ships. Use the musl build (the script already does)

### Connects but slow

Expected ceiling: ~38 Mbps down, 230 ms latency. See
[performance](../README.md#performance).

---

## What gets installed

| Path | Purpose |
|---|---|
| `/usr/local/bin/ssserver` | shadowsocks-rust, static musl build — no Docker |
| `/etc/shadowsocks/config.json` | port, cipher, pre-shared key |
| `/root/ss-url.txt` | the `ss://` link |
| `shadowsocks.service` | systemd unit, runs as a dedicated system user |

~6 MB resident. Runs alongside WireGuard without conflict — different ports.

### Why not the official Outline Server

It requires Docker (~150–250 MB with daemon and containers) and gives you Outline
Manager, a GUI for issuing keys. On a 1 GB Always Free instance with no swap that
is a poor trade, and with one shared key there is little for the GUI to manage.

The Outline **client** app is identical either way — same `ss://` format, same
protocol.
