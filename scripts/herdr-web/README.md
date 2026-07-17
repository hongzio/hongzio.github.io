# web

herdr 세션을 **브라우저 웹 터미널**로 노출하는 플러그인. 방화벽/NAT 뒤 머신을 cloudflared quick tunnel로 optional하게 외부 공개할 수 있다. 순수 python3 stdlib + vendored xterm.js.

## 동작
- `pane.created` 이벤트에 idempotent 런처(`serve.py ensure`)를 걸어 세션 시작과 함께 데몬이 뜬다.
- 데몬은 `http.server` + 손으로 짠 WebSocket으로 vendored xterm.js를 서빙하고, `pty.fork()`로 `herdr`에 attach한다. 브라우저 창 리사이즈는 TIOCSWINSZ→SIGWINCH로 herdr까지 전파된다.
- 기본 바인딩 `127.0.0.1:8022`. Basic Auth 필수(첫 기동 시 랜덤 비번 자동 생성, state dir에 0600 저장). URL·자격증명은 herdr toast로 표시.
- 설정 포트가 이미 사용 중이면 **빈 포트를 자동 선택**해서 뜨고(터널도 그 포트로 연결), 실제 포트를 state에 기록해 `web.status`·패널이 표시한다. 포트는 시작 시 고정.
- **멀티 인스턴스**: herdr를 여러 개 돌리면(서버 소켓 기준) 각 인스턴스가 **자기 데몬·포트·터널 URL·비밀번호**를 가진다. 런타임 state(pidfile/port/tunnel_url/password)는 `HERDR_SOCKET_PATH` 키로 `state/instances/<키>/`에 분리되어 인스턴스별 격리(한 URL 비번 노출이 다른 인스턴스에 영향 없음). username·나머지 config는 공유. 포트 충돌은 자동 폴백이 처리. 각 인스턴스의 비번은 해당 herdr에서 `web.status`/패널로 확인.

## 설치
```sh
cd scripts/herdr-web
# vendored 자산(커밋돼 있음). 재취득이 필요하면:
#   curl -fsSL https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.js        -o static/xterm.js
#   curl -fsSL https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css       -o static/xterm.css
#   curl -fsSL https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.js -o static/addon-fit.js
herdr plugin link "$(pwd)"
herdr server reload-config
herdr plugin list   # web (Web Terminal) enabled 확인
```

## config
`herdr plugin config-dir web`의 `config.toml`:
```toml
[server]
port = 8022
bind = "127.0.0.1"
[auth]
username = "herdr"
[tunnel]
enabled = false          # true면 cloudflared quick tunnel 동반 기동
require_os_auth = false   # false=노출 시 Basic Auth(강한 랜덤 비번) 단독.
                          # true면 pty가 ssh localhost를 exec해 OS 로그인 한 겹 추가
                          # (원격 로그인 sshd가 켜져 있어야 동작)
```

## 액션
- `web.panel` — 접속 패널(curses popup, session-modal 플로팅 박스). 로컬/공개 URL·**데몬 pid** 표시 + **로컬(serve.py)·터널 on/off 토글**(`Space`) + **username·password 실시간 편집**(저장 시 재시작 없이 새 연결부터 적용, URL 고정). `Ctrl-G` 랜덤 비번. 로컬을 끄면 터널도 같이 내려가고, 터널 토글은 데몬 재시작 없이 라이브로 cloudflared를 켜고 끈다(감독 스레드가 `[tunnel] enabled`를 라이브로 반영). 로컬 on/off는 state(`local_enabled`)에 저장돼 **herdr 재시작·패널 재접속에도 유지**되고, `ensure`(auto-start)가 이를 존중한다(신규 설치엔 값이 없어 기본 ON). 패널은 **싱글 인스턴스**라 이미 열려 있는데 `web.panel`을 또 호출하면 중복으로 안 뜨고(flock), 기존 패널을 focus한다.
- `web.status` — URL(로컬+공개 터널)/자격증명 toast 재표시
- `web.stop` — 데몬 종료
- `web.restart` — 재시작

인증은 **매 요청마다 현재 username/password를 다시 읽어** 검증한다(동적 인증). 그래서 패널의 편집이 재시작 없이 즉시 반영되고, 서버 시작 시 고정되는 URL/포트/터널은 유지된다. 이미 열린 세션은 연결 시점 인증이라 유지되고, 바뀐 자격증명은 다음 접속부터 적용된다.

## 보안 주의
- cloudflared로 노출하면 Cloudflare Access 신원 게이트가 없다. 기본값 `require_os_auth=false`에선 **Basic Auth의 자동 생성 24자 랜덤 비번이 유일 방벽**이다(≈144비트라 무차별 대입은 사실상 불가, TLS 암호화됨). 더 강하게 하려면 `require_os_auth=true`(OS 로그인 2중) + 원격 로그인 활성화.
- herdr `[experimental] pane_history=true`면 스크롤백에 secrets가 남을 수 있다.
- quick tunnel URL은 재시작마다 바뀐다. scp/rsync/포트포워딩은 미지원(터미널 전용).

## 테스트
```sh
python3 -m unittest test_config test_ws test_ptybridge test_authstate test_serve test_panel
```
