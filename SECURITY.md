# Credential handling

Publish only source code, documentation, diagrams, and example settings.
Real WireGuard configs and QR images grant VPN access. Keep them private,
along with SSH keys, `config.local`, Shadowsocks `config.json`, and `ss-url.txt`.
The ignore rules cover these usual filenames, but cannot protect secrets pasted
into documentation, renamed files, screenshots, or forced Git additions.

Before pushing, inspect `git diff --cached` and `git ls-files`. Never upload an
archive of the working directory: ignored credentials may still be inside it.
Server logs and terminal output can contain access links, keys, or client IPs;
redact these before sharing diagnostics.

If credentials are published, revoke or rotate them first, then remove them
from repository history. Deleting the latest copy alone does not revoke access.

## 한국어

소스 코드·문서·도식·예시 설정만 공개합니다. 실제 WireGuard 설정과 QR 이미지는
VPN 접속 자격증명이므로 SSH 키, `config.local`, Shadowsocks `config.json`,
`ss-url.txt`와 함께 비공개로 보관합니다.

푸시 전 `git diff --cached`와 `git ls-files`를 확인합니다. 작업 폴더를 통째로
압축하면 Git 제외 파일도 포함되므로 업로드하지 않습니다. 로그·스크린샷의
접속 링크, 키, 클라이언트 IP도 가려야 합니다. 공개된 키는 먼저 폐기하거나
교체한 뒤 Git 기록에서 제거합니다.
