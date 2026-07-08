# recent-agent

가장 최근에 **완료된**(작업을 멈추고 내 개입이 필요해진) agent로 focus 하는 herdr 플러그인.

`prefix+ctrl+l` → 방금 끝난(그리고 아직 대기 중인) agent로 즉시 이동.

## 기능

- **이벤트 기반 완료 추적** — herdr가 상태 전이마다 발생시키는 `pane.agent_status_changed` 이벤트를 구독. 데몬도 폴링도 없음.
- **completed = ATTENTION 진입** — agent가 `idle`/`done`/`blocked` 로 전이하면 "완료(내 개입 필요)"로 보고 기록. (herdr는 agent가 턴을 끝내는 순간 `done`, 이후 대기하며 앉아 있으면 `idle`, 입력/권한 대기는 `blocked`로 보고한다.)
- **most-recent-still-waiting fall-through** — `prefix+ctrl+l` 은 완료 기록을 최신순으로 훑어, **여전히 대기 중인** 첫 agent에 focus. 이미 다시 `working` 으로 돌아간 항목은 건너뛰고 그 다음 최근으로 넘어간다(cycle 아님).
- **멱등** — 상태 변화가 없으면 반복해서 눌러도 같은 대상. 후보가 없으면 조용히 no-op.
- **전체 workspace 범위** — 다른 workspace의 완료 agent로도 이동(`herdr agent focus` 가 맥락 전환 포함).

## 동작 원리

```
[[events]] on = "pane.agent_status_changed"
   → recent.py record   # 이벤트 JSON에서 pane_id + 새 status 추출,
                        #  ATTENTION 이면 recents 로그에 append
[[actions]] focus  (prefix+ctrl+l → recent-agent.focus)
   → recent.py focus    # 로그를 최신순 dedup → herdr agent list 로 현재 status 대조
                        #  → 여전히 ATTENTION 인 첫 pane 에 herdr agent focus
```

이벤트 페이로드(확인됨):
```json
{"event":"pane_agent_status_changed",
 "data":{"type":"pane_agent_status_changed",
         "pane_id":"w1:p1","workspace_id":"w1","agent_status":"done","agent":"claude"}}
```

완료 기록은 `$HERDR_PLUGIN_STATE_DIR/recents.log` 에 `<ts_ns>\t<pane_id>\t<status>` 한 줄씩 **append-only** 로 쌓인다. 여러 agent가 동시에 전이해도 작은 라인 append는 원자적이라 레이스가 없다(read-modify-write JSON list와 달리). 로그가 커지면 record가 마지막 N줄만 남기고 잘라낸다.

focus는 로그를 **최신순**으로 읽되, 저장된 status를 믿지 않고 `herdr agent list`로 **현재** status를 다시 확인한다. 그래서 focus 시점에 이미 working으로 돌아간 agent나 없어진 pane은 자동으로 건너뛴다.

## 요구사항

| 도구 | 용도 |
|---|---|
| `herdr` ≥ 0.7.1 | 호스트 (`pane.agent_status_changed` 이벤트, `agent list`/`agent focus`) |
| `python3` | 로직 (표준 라이브러리만 사용) |

## 설치

### 1. herdr 설정 연결
`prefix+ctrl+l` 키바인딩은 이 repo의 `herdr.toml`에 있음. herdr config로 심링크:
```sh
mkdir -p ~/.config/herdr
ln -sf "$(pwd)/../../herdr.toml" ~/.config/herdr/config.toml   # repo 루트의 herdr.toml
```

### 2. 플러그인 등록
```sh
herdr plugin link "$(pwd)"          # scripts/herdr-recent-agent 에서 실행
herdr server reload-config
herdr plugin list                   # recent-agent enabled 확인
```
> herdr 서버가 실행 중이어야 함. 처음이면 `herdr` 한 번 실행.

## 사용

1. 여러 agent를 돌리는 중, 하나가 응답을 끝냄
2. `prefix+ctrl+l` → 방금 완료된 agent로 이동
3. 그 agent와 상호작용을 시작하면(→ working) 다시 `prefix+ctrl+l` 은 그 다음으로 최근에 완료된, 아직 대기 중인 agent로 이동

## 구성

| 파일 | 역할 |
|---|---|
| `herdr-plugin.toml` | 매니페스트 — `pane.agent_status_changed` 이벤트 구독 + `focus` 액션 |
| `recent.py` | 로직 — `record`(이벤트→로그) / `focus`(로그→herdr agent focus) + 순수 파서/선택 함수 |
| `test_recent.py` | 단위테스트 (이벤트 parse, 최신순 dedup, 대상 선택, 로그 trim) |

키바인딩은 **매니페스트가 아니라 유저 `herdr.toml`** 에 둠 (herdr가 플러그인 매니페스트의 키는 안 읽음):

| 키 | 액션 |
|---|---|
| `prefix+ctrl+l` | `recent-agent.focus` — 가장 최근에 완료된, 아직 대기 중인 agent에 focus |

## 개발

```sh
python3 test_recent.py       # 단위테스트
```
`recent.py`는 호출마다 새로 읽히므로 로직 수정 후 herdr reload/재시작 불필요. **매니페스트(`herdr-plugin.toml`) 수정 시에는 `herdr plugin link "$(pwd)"`로 재-link** 해야 반영됨 (`herdr server reload-config`는 config.toml 키바인딩만 다시 읽고 플러그인 매니페스트는 안 읽음). 특히 `[[events]]` 구독 등록은 재-link + reload가 필요.

## Caveat

- `link`는 repo 절대경로를 가리킴 — repo를 옮기면 `herdr plugin unlink recent-agent` 후 재-link.
- 완료 기록은 이벤트가 발생해야 쌓이므로 **플러그인을 붙인 뒤부터** 채워진다(설치 직후 몇 번은 대상이 없을 수 있음).
- 현재 focus 중인 pane도 후보에서 제외하지 않는다. 즉 이미 "가장 최근 완료" agent를 보고 있으면 다시 눌러도 no-op(멱등). 현재 pane을 건너뛰고 싶으면 `pick_target`에 현재 pane 제외 로직을 추가하면 됨.
- `blocked`(권한/입력 대기)도 완료로 취급해 이동 대상에 포함한다.
- macOS 전용(`platforms = ["macos"]`).
