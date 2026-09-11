# WireGuard

[← 개요](../README.ko.md) · [Shadowsocks + Outline](../shadowsocks/README.ko.md)

기기별 키를 쓰고, 내 컴퓨터에서 `vpnctl.py`로 관리한다. 다른 기기를 건드리지 않고
한 대만 폐기할 수 있다.

처음부터 끝까지 약 30분.

```
0. 계정 → 1. 네트워크 → 2. 보안 → 3. 인스턴스 → 4. 관리 머신 → 5. 기기 등록 → 6. 확인
   Home     VCN         51820    init script  config.local  vpnctl.py add  핸드셰이크
   Region   마법사      열기     첨부                       → QR / .conf   + 출구 IP
   = 뭄바이
```

더 간단한 쪽을 원한다면 [Shadowsocks + Outline](../shadowsocks/README.ko.md)은 관리 머신이
필요 없고 링크 하나만 공유하면 된다 ([비교](../README.ko.md#방식-선택)).

---

## 0. 계정

이미 인도 리전으로 만든 Oracle Cloud 계정이 있다면 건너뛴다.

[oracle.com/cloud/free](https://www.oracle.com/cloud/free/)에서 가입한다. 가입 도중
**Home Region** 을 묻는데, **India West (Mumbai)** 또는 **India South (Hyderabad)** 를
고른다.

> **되돌릴 수 없는 유일한 선택이다.** Home Region은 계정을 만든 뒤로는 바꿀 수 없다.
> 다른 곳을 고르면 VPN이 그 나라로 나가고, 고치는 방법은 계정을 새로 만드는 것뿐이다.
> 이 단계 이후는 전부 되돌릴 수 있지만 이것만은 아니다.

신원 확인용으로 신용카드를 요구한다. Always Free 리소스는 계속 무료이며, 한도 안에서
쓰는 한 카드에 청구되지 않는다.

## 1. 네트워크

콘솔 → **Networking → Virtual Cloud Networks → Create VCN → VCN with Internet Connectivity**

- 이름: `vpn-vcn`
- 나머지는 기본값 그대로 두고 **Create** 까지 진행한다

마법사가 VCN, 퍼블릭 서브넷, Internet Gateway, 라우팅 테이블을 한 번에 만든다. 수동으로
하면 이 네 가지를 직접 만들어야 한다.

## 2. 보안

콘솔 → **Networking → VCN → 서브넷 → Default Security List → Add Ingress Rules**

| Source CIDR | IP Protocol | Destination Port |
|---|---|---|
| `0.0.0.0/0` | UDP | `51820` |

TCP가 아니라 **UDP**다. SSH(TCP 22)는 마법사가 이미 열어뒀다.

## 3. 인스턴스

콘솔 → **Compute → Instances → Create Instance**

| 항목 | 값 |
|---|---|
| Name | `vpn` |
| Image | **Canonical Ubuntu** 22.04 또는 24.04 — Oracle Linux 아님 |
| Shape | `VM.Standard.E2.1.Micro` — *Always Free eligible* 표시가 있는 것 |
| Subnet | 1단계에서 만든 퍼블릭 서브넷 |
| Public IPv4 address | **Assign** |
| SSH keys | **Generate a key pair** 후 개인키를 다운로드한다 |

이어서 **Show advanced options → Management → Initialization script**

- **Choose a cloud-init script file** 선택
- `wireguard/install.sh` 업로드
- 텍스트로 **붙여넣지 않는다** — 입력창이 줄바꿈을 없애서 `Incorrectly formatted request` 로 실패한다

**Create** 를 누른다. **Running** 이 된 뒤 cloud-init이 끝나기까지 2분 정도 더 기다린다.

> `Out of host capacity` — 지금 무료 물량이 없다는 뜻이다. 재시도하거나 다른 가용성
> 도메인을 고른다.
> `Too many requests` — Create를 연타했을 때 뜬다. 5~10분 기다렸다 한 번만 누른다.

SSH로 확인한다.

macOS / Linux:

```bash
chmod 600 ~/Downloads/ssh-key-*.key          # OCI가 열린 권한으로 내려준다
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<server-ip>
```

Windows — PowerShell, 별도 설치 없이 된다 (Windows 10+ 에 OpenSSH 내장):

```powershell
icacls .\ssh-key.key /inheritance:r
icacls .\ssh-key.key /grant:r "$env:USERNAME:R"
ssh -i .\ssh-key.key ubuntu@<server-ip>
```

`icacls` 가 Windows의 `chmod 600` 에 해당한다. 이걸 하지 않으면 `ssh` 가 키 권한이
너무 열려 있다며 거부한다.

접속한 뒤 서버에서:

```bash
sudo cloud-init status --wait                # 끝날 때까지 기다린다
sudo systemctl is-active wg-quick@wg0        # active 여야 한다
```

## 4. 관리 머신 설정

Shadowsocks와 달리 WireGuard는 **내 컴퓨터**에서 운영한다. 한 번만 해두면 된다.

- macOS: `brew install wireguard-tools qrencode`
- Linux: `sudo apt install wireguard-tools qrencode`

> **macOS와 Linux만 지원한다.** Windows는 관리 머신으로 지원하지 않는다. Windows를
> 쓴다면 관리 머신 자체가 필요 없는
> [Shadowsocks + Outline](../shadowsocks/README.ko.md)을 쓴다.

| 패키지 | 용도 | 필수 |
|---|---|---|
| `wireguard-tools` | 키 생성, 이 컴퓨터에서 접속 | 예 |
| `qrencode` | 터미널 QR 및 PNG 생성 | QR 사용 시 필수 — 없으면 `.conf` 파일로 연결 |
| Python 3.9+ | `vpnctl.py`, 표준 라이브러리만 사용 | 예 — macOS와 WSL에 기본 탑재 |

CLI가 서버를 바라보게 한다.

```bash
cd oracle-vpn/wireguard
cp config.example config.local
```

```ini
OVPN_SERVER=203.0.113.10                 # 인스턴스 공인 IP
OVPN_SSH_USER=ubuntu
OVPN_SSH_KEY=~/Downloads/ssh-key-2026-01-15.key
```

서버에 닿는지 확인한다.

```bash
./vpnctl.py list        # 갓 만든 서버라면 "no devices registered" 가 정상이다
```

`config.local` 은 gitignore 대상이다. 같은 이름의 환경변수가 파일보다 우선한다.

## 5. 기기 등록

```bash
./vpnctl.py add phone -p iphone     # QR 출력 + phone-almond.conf 생성
./vpnctl.py add mac   -p mac
```

이름은 `<기기>-<쿠키>` 로 자동 생성되고 쿠키는 A~Z 순서라, 이름만 봐도 등록 순서를 안다 —
`phone-almond`, `mac-brownie`, `ipad-chocochip`.

- 비어 있는 터널 주소를 찾아 피어를 등록하고 `<이름>.conf` 와 QR PNG를 만든다
- 기존 연결은 끊기지 않는다 — `wg set` 으로 즉시 반영하므로 재시작이 없다
- 이름을 직접 정하려면 `-n <이름>`

이제 연결한다.

| 플랫폼 | 방법 |
|---|---|
| **iPhone / Android** | App Store 또는 Play에서 **WireGuard** 설치 → **+ → Scan from QR code** → 토글 ON |
| **Windows** | [wireguard.com/install](https://www.wireguard.com/install/) 에서 설치 → **Add Tunnel → Import from file** → `.conf` 선택 → **Activate** |
| **macOS** | `./vpnctl.py up mac` — 또는 App Store 앱에 `.conf` 임포트 후 메뉴바에서 토글 |

## 6. 확인

터널을 켠 상태에서 실행한다.

```bash
./vpnctl.py status          # 피어, 마지막 핸드셰이크, 이 컴퓨터의 출구 IP
curl ifconfig.me            # 서버 IP
```

`status` 에 방금 연결한 기기의 핸드셰이크가 몇 분 이내로 찍혀야 한다. 모바일에서는
브라우저로 `ifconfig.me` 에 접속한다.

핸드셰이크는 최근인데 출구 IP가 그대로라면, 터널은 떠 있지만 아무것도 나르지 못하는
상태다 — [연결은 되는데 인터넷이 안 된다](#연결은-되는데-인터넷이-안-된다)를 참고한다.

> 다 쓰면 터널을 끈다 — 켜둔 채로는 모든 트래픽이 지연 230ms의 뭄바이를 경유한다.

---

## 기기 관리

```bash
./vpnctl.py add <기기> [-p iphone|android|mac|windows]   # 등록 + QR
./vpnctl.py list                                          # 기기 목록과 상태
./vpnctl.py qr <이름>                                     # QR 다시 출력
./vpnctl.py rm <이름>                                     # 기기 하나만 폐기
./vpnctl.py rename <옛이름> <새이름>
./vpnctl.py status                                        # 서버 + 출구 IP
./vpnctl.py up|down [이름]                                # 이 컴퓨터 연결/해제 (macOS/Linux)
```

앞부분만 입력해도 된다 — `./vpnctl.py up mac` 이 `mac-brownie` 를 찾는다.

```
$ ./vpnctl.py list
   NAME          ADDRESS    LAST SEEN  RX        TX        SOURCE
-  ------------  ---------  ---------  --------  --------  -------------
*  phone-almond  10.66.0.3  57s ago    3.8MiB    16.6MiB   198.51.100.24
*  mac-brownie   10.66.0.4  34s ago    227.5MiB  454.7MiB  198.51.100.77

* active within the last 3 minutes   2 device(s)
```

개인키는 **로컬에서** 생성되며 서버로 전송되지 않는다 — 공개키만 등록된다. 터널 서브넷은
`10.66.0.0/24` 이고 서버가 `.1`, 클라이언트는 `.2` 부터 비어 있는 가장 낮은 주소를 받는다.

QR 생성은 로컬에서만 수행한다. 로컬에 `qrencode`가 없으면 설정 파일을 앱에 임포트한다.
설치 스크립트의 레거시 서버용 `add-vpn-peer.sh`는 서버에 개인키를 저장하므로,
로컬 키 관리를 원하면 이 가이드의 `vpnctl.py`를 사용한다.

인터넷 연결은 IPv4만 지원한다. 클라이언트의 `AllowedIPs = 0.0.0.0/0, ::/0`은
IPv6도 터널로 보내 서버의 IPv4 전용 피어 정책에서 차단한다. IPv6 우회를 방지하는
설정이며 터널 종료 시의 킬 스위치는 아니다.
기존 설정은 `[Peer]`의 `AllowedIPs`를 위 값으로 바꾸고 재연결한다.
QR은 설정을 변경한 뒤 `vpnctl.py qr <이름>`으로 다시 생성한다.

---

## 문제 해결

### 연결은 되는데 인터넷이 안 된다

핸드셰이크는 성공하는데 아무 페이지도 열리지 않는다. 느린 것처럼 보이지만 실제로는 완전
차단이다.

Oracle 이미지는 FORWARD 체인에 `REJECT all` 을 기본 탑재하는데, `iptables -A FORWARD` 는
그 **아래에** 규칙을 붙인다. 그래서 VPN 트래픽이 앞의 REJECT에 먼저 걸린다. 핸드셰이크는
FORWARD가 아니라 INPUT을 지나므로 여전히 성공한다.

```bash
sudo iptables -L FORWARD -n -v --line-numbers    # REJECT만 오르고 wg0 ACCEPT는 0인가?
sudo iptables -I FORWARD 1 -i wg0 -j ACCEPT
sudo iptables -I FORWARD 2 -o wg0 -j ACCEPT
sudo netfilter-persistent save
```

이 한 줄 차이로 0에서 36 Mbps가 됐다. 이걸 고치기 전에는 다른 무엇도 소용없다.
`install.sh` 는 이미 `-I` 를 쓴다.

### 트래픽이 흐르다 멈춘다

MTU 문제다. 양쪽 `[Interface]` 에 `MTU = 1280` 을 넣는다. IPv6 전용 이동통신망에서 특히
잦고, 이때 엔드포인트가 NAT64 주소(`[64:ff9b::...]`)로 잡힌다 — 뒤쪽 16진수가 서버의
IPv4다.

```bash
sudo sed -i '/^\[Interface\]/a MTU = 1280' /etc/wireguard/wg0.conf
sudo systemctl restart wg-quick@wg0
```

### down 할 때 `is not a WireGuard interface`

터널을 올린 뒤에 설정 파일 이름을 바꾼 경우다. `wg-quick` 은 올릴 당시의 파일명을 인터페이스
이름으로 쓴다. `vpnctl.py down` 이 이를 감지해 실행 중인 이름으로 대신 내린다. 실제로 떠
있는 것은 `sudo wg show` 로 확인한다.

### 설정이 유출됐다

```bash
./vpnctl.py rm <이름>       # 서버에서 폐기하고 로컬 파일도 삭제한다
./vpnctl.py add <기기>      # 새로 발급한다
```

다른 기기는 영향받지 않는다.

---

## 설치되는 것

| 경로 | 용도 |
|---|---|
| `/etc/wireguard/wg0.conf` | 서버 설정, 키, PostUp/PostDown 방화벽 규칙 |
| `/etc/wireguard/peers/` | 기기별 키와 설정 |
| `/usr/local/bin/add-vpn-peer.sh` | 서버에서 직접 기기 등록 (`vpnctl.py` 대안) |
| `wg-quick@wg0` | systemd 유닛. PostUp이 방화벽과 NAT 규칙을 넣는다 |

설치 스크립트를 다시 실행하면 **서버 키가 새로 생성되고** `wg0.conf` 가 교체되어, 등록된
모든 기기가 무효화된다.
