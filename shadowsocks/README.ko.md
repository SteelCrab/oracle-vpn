# Shadowsocks + Outline

[← 개요](../README.ko.md) · [WireGuard](../wireguard/README.ko.md)

**추천.** `ss://` 링크 하나가 자격증명 전부다. Outline 앱에 붙여넣고 연결하면 된다.
내 컴퓨터에는 아무것도 설치하지 않는다.

처음부터 끝까지 약 20분.

```
0. 계정 → 1. 네트워크 → 2. 보안 → 3. 인스턴스 → 4. 키 받기 → 5. 연결 → 6. 확인
   Home     VCN         8388     init script  SSH 접속 후  Outline  출구 IP가
   Region   마법사      열기     첨부         ss-url.txt   앱       인도인지
   = 뭄바이
```

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

콘솔 → **Networking → Virtual Cloud Networks → Create VCN → VCN with Internet Connectivity**.

- 이름: `vpn-vcn`
- 나머지는 기본값 그대로 두고 **Create**까지 진행한다

마법사가 VCN, 퍼블릭 서브넷, Internet Gateway, 라우팅 테이블을 한 번에 만든다. 수동으로
하면 이 넷을 직접 다 만들어야 한다.

## 2. 보안

VM을 만들기 전에 포트를 연다. 규칙 누락이 나중에 나오는 `invalid access key`의 1순위
원인이다.

콘솔 → **Networking → VCN → 해당 서브넷 → Default Security List → Add Ingress Rules**.

규칙을 **두 개** 추가한다 (OCI는 TCP+UDP를 한 규칙에 넣지 못한다):

| Source CIDR | IP Protocol | Destination Port |
|---|---|---|
| `0.0.0.0/0` | TCP | `8388` |
| `0.0.0.0/0` | UDP | `8388` |

SSH(TCP 22)는 마법사가 기본으로 열어 둔다.

## 3. 인스턴스

콘솔 → **Compute → Instances → Create Instance**.

| 항목 | 값 |
|---|---|
| Name | `vpn` |
| Image | **Canonical Ubuntu** 22.04 또는 24.04 — Oracle Linux 아님 |
| Shape | `VM.Standard.E2.1.Micro` — *Always Free eligible* 표시가 있는 것 |
| Subnet | 1단계에서 만든 퍼블릭 서브넷 |
| Public IPv4 address | **Assign** |
| SSH keys | **Generate a key pair** 후 개인키를 내려받는다 |

이어서 같은 화면에서: **Show advanced options → Management → Initialization script**

- **Choose a cloud-init script file** 을 선택한다
- `shadowsocks/install.sh` 를 업로드한다
- 텍스트로 **붙여넣지 않는다** — 입력창이 줄바꿈을 지워서 Create가 `Incorrectly formatted request`로 실패한다

**Create**를 누른다. 인스턴스가 부팅하면서 스스로 설치한다. 상태가 **Running**이 된 뒤
약 2분이면 키가 생성된다.

> `Out of host capacity` — 지금 무료 물량이 없다. 재시도하거나 화면에서 다른 Availability
> Domain을 고른다.
> `Too many requests` — Create를 연타했다. 5~10분 기다렸다가 한 번만 누른다.

## 4. 키 받기

인스턴스 상세 화면에서 **Public IP address**를 복사한 뒤:

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

서버에서:

```bash
sudo systemctl is-active shadowsocks         # expect: active
sudo cat /root/ss-url.txt                    # the ss:// link
```

아직 active가 아니면 cloud-init이 실행 중일 수 있다:

```bash
sudo cloud-init status --wait                # blocks until done
sudo tail -30 /var/log/cloud-init-output.log
```

## 5. 연결

[getoutline.org](https://getoutline.org/)에서 **Outline**을 설치한다 — macOS, Windows,
Linux, iOS, Android.

1. 4단계의 `ss://` 줄을 복사한다
2. Outline을 연다 — 클립보드를 읽고 서버 추가를 제안한다
3. 뜨지 않으면 **+** 를 누르고 붙여넣는다
4. **Connect**

다른 사람에게 줄 때: 같은 `ss://` 줄과 위 앱 4단계만 전달하면 된다. 터미널을 쓸 일이 없다.

## 6. 확인

터널을 켠 상태에서 클라이언트에서 실행한다.

```bash
curl ifconfig.me            # 서버 IP
curl -s ipinfo.io/city      # Mumbai
```

터미널이 없는 기기라면 브라우저로 `ifconfig.me`에 접속한다.

IP가 여전히 내 것이라면 터널이 트래픽을 나르지 못하고 있다 — [문제 해결](#문제-해결)을
참고한다.

> 다 쓰면 연결을 끊는다. 켜 두면 모든 트래픽이 뭄바이를 거치고 요청마다 약 230 ms가
> 더해진다.

---

## 키 교체

공유 키 하나라서 전원이 한 번에 끊긴다. 설치 스크립트를 다시 실행한다:

```bash
ssh -i ~/path/to/ssh-key.key ubuntu@<server-ip>
sudo bash /tmp/install.sh 8388    # or scp the script again first
sudo cat /root/ss-url.txt                     # new link
```

기기별로 폐기하려면 [WireGuard](../wireguard/README.ko.md)를 쓴다.

> `ss://` URL은 그 자체가 자격증명이다. 가진 사람은 누구나 VPN을 쓸 수 있다. 비공개 경로로
> 전달하고 커밋하거나 공개된 곳에 올리지 않는다.

---

## 문제 해결

### Outline에서 "invalid access key"

Outline은 서버에 닿지 못하면 **무조건** 이 메시지를 낸다. 키 형식 문제만이 아니다.
아래 순서로 확인한다.

**1. 포트가 열려 있는가?** 내 컴퓨터에서:

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

`blocked`이면 2단계 Security List 규칙이 없거나 잘못됐다. 가장 흔한 원인이다.

**2. 암호군을 지원하는가?** Outline은 AEAD-2022 암호군(`2022-blake3-*`)을 지원하지 않는다.
다른 Shadowsocks 클라이언트는 지원한다. 그 암호군을 쓰는 서버는 키가 완전히 정상이어도
정확히 이 오류를 낸다.

```bash
sudo grep method /etc/shadowsocks/config.json    # expect: chacha20-ietf-poly1305
```

`install.sh`가 `chacha20-ietf-poly1305`를 기본값으로 쓰는 이유다.

**3. URL이 온전한가?** 채팅 앱을 거쳐 복사하면 줄바꿈이 섞일 수 있다. 공백 없는 한 줄이다.
`sudo cat /root/ss-url.txt`로 다시 읽는다.

### 서비스가 시작되지 않는다

```bash
sudo journalctl -u shadowsocks -n 20 --no-pager
```

- 설정 파일에 `Permission denied` — `shadowsocks` 사용자가 읽을 수 있어야 한다: `chown root:shadowsocks /etc/shadowsocks/config.json`, `chmod 640`
- `GLIBC_2.38 not found` — gnu 빌드는 Ubuntu 22.04보다 최신 glibc를 요구한다. musl 빌드를 쓴다 (스크립트가 이미 그렇게 한다)

### 연결은 되는데 느리다

예상 상한: 다운로드 약 38 Mbps, 지연 시간 230 ms. [성능](../README.ko.md#성능) 참고.

---

## 설치되는 것

| 경로 | 용도 |
|---|---|
| `/usr/local/bin/ssserver` | shadowsocks-rust, 정적 musl 빌드 — Docker 불필요 |
| `/etc/shadowsocks/config.json` | 포트, 암호군, 사전 공유 키 |
| `/root/ss-url.txt` | `ss://` 링크 |
| `shadowsocks.service` | systemd 유닛. 전용 시스템 사용자로 실행된다 |

메모리 약 6 MB. 포트가 다르므로 WireGuard와 함께 운영해도 충돌하지 않는다.

### 공식 Outline Server를 쓰지 않는 이유

Docker가 필요하고(데몬과 컨테이너 포함 약 150~250 MB), 키 발급용 GUI인 Outline Manager를
제공한다. 스왑 없는 1 GB Always Free 인스턴스에서는 손해가 크고, 공유 키 하나뿐이라 GUI가
관리할 것도 별로 없다.

Outline **클라이언트** 앱은 어느 쪽이든 동일하다 — 같은 `ss://` 형식, 같은 프로토콜.
