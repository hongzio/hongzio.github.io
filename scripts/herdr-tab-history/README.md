# tab-history

브라우저식 **back/forward** 로 최근 방문한 tab을 오가는 herdr 플러그인.

`prefix+ctrl+o` → 뒤로(older), `prefix+ctrl+i` → 앞으로(newer). (vim jumplist 니모닉: `o`lder / `i`nner-newer)

## 기능

- **이벤트 기반 히스토리** — herdr가 tab 전환마다 발생시키는 `tab.focused` 이벤트를 구독해 방문 tab을 기록. 데몬도 폴링도 없음.
- **브라우저 히스토리 시맨틱** — 리스트 + cursor 모델.
  - `A-B(*)-C` 에서 B로 back 한 뒤 D로 이동하면 → `A-B-D(*)`. 즉 cursor 뒤쪽(forward 분기)은 새 이동 시 잘려나간다.
- **이동은 기록하지 않음** — back/forward 로 옮긴 focus는 히스토리에 다시 쌓이지 않는다. (cursor가 가리키는 tab으로의 focus는 no-op이라, back/forward가 일으키는 focus 메아리가 자연히 무시됨 — 마커 파일 불필요.)
- **닫힌 tab 건너뛰기** — 이동 시 `herdr tab list` 로 살아있는 tab을 확인해, 닫힌 tab은 skip 하고 그 다음 살아있는 항목으로.
- **전체 workspace 단일 히스토리** — 모든 workspace의 tab focus가 하나의 히스토리. cross-workspace back/forward 가능.
- **최대 개수 설정 가능** (기본 100).

## 동작 원리

```
[[events]] on = "tab.focused"
   → tabhist.py record   # 이벤트 JSON에서 tab_id 추출
                         #  cursor가 가리키는 tab과 같으면 no-op(메아리)
                         #  다르면 cursor 뒤쪽을 자르고 append, cursor를 끝으로
[[actions]] back  (prefix+ctrl+o → tab-history.back)
[[actions]] forward (prefix+ctrl+i → tab-history.forward)
   → tabhist.py back/forward  # cursor를 좌/우로, 닫힌 tab은 skip
                              #  → 새 위치를 저장한 뒤 herdr tab focus
```

이벤트 페이로드(확인됨):
```json
{"event":"tab_focused",
 "data":{"type":"tab_focused","tab_id":"w1:t1","previous_tab_id":"w1:t2"}}
```

히스토리는 `$HERDR_PLUGIN_STATE_DIR/state.json` 에 `{"entries":[...tab_id...],"cursor":N}` 로 저장. back/forward 는 **cursor를 저장한 뒤 focus** 하므로, 그 focus의 `tab.focused` 메아리가 도착할 때는 이미 `entries[cursor]` 와 같아 record가 no-op → 이동이 재기록되지 않는다.

## 요구사항

| 도구 | 용도 |
|---|---|
| `herdr` ≥ 0.7.1 | 호스트 (`tab.focused` 이벤트, `tab list`/`tab focus`) |
| `python3` | 로직 (표준 라이브러리만 사용) |

## 설치

### 1. herdr 설정 연결
`prefix+ctrl+o` / `prefix+ctrl+i` 키바인딩은 이 repo의 `herdr.toml`에 있음. herdr config로 심링크:
```sh
mkdir -p ~/.config/herdr
ln -sf "$(pwd)/../../herdr.toml" ~/.config/herdr/config.toml   # repo 루트의 herdr.toml
```

### 2. 플러그인 등록
```sh
herdr plugin link "$(pwd)"          # scripts/herdr-tab-history 에서 실행
herdr server reload-config
herdr plugin list                   # tab-history enabled 확인
```
> herdr 서버가 실행 중이어야 함.

## 설정

`~/.config/herdr/tab-history.toml` (record가 처음 실행될 때 기본값으로 자동 생성):
```toml
max = 100
```
`max` = back/forward 로 되짚을 수 있는 최근 tab 개수. 최소 2. 코드 수정/재시작 없이 즉시 반영(호출마다 다시 읽음).

## 사용

1. 여러 tab을 오가며 작업
2. `prefix+ctrl+o` → 직전 tab으로 (닫힌 tab은 건너뜀)
3. `prefix+ctrl+i` → 다시 앞으로
4. back 한 상태에서 다른 tab으로 이동하면, 그 뒤쪽 forward 기록은 버려지고 새 경로가 시작됨

## 구성

| 파일 | 역할 |
|---|---|
| `herdr-plugin.toml` | 매니페스트 — `tab.focused` 구독 + `back`/`forward` 액션 |
| `tabhist.py` | 로직 — `record`(이벤트→히스토리) / `back`,`forward`(cursor 이동→herdr tab focus) + 순수 함수 |
| `test_tabhist.py` | 단위테스트 (config/이벤트 parse, record 시맨틱, back/forward skip, 시나리오) |

키바인딩은 **매니페스트가 아니라 유저 `herdr.toml`** 에 둠:

| 키 | 액션 |
|---|---|
| `prefix+ctrl+o` | `tab-history.back` — 뒤로 |
| `prefix+ctrl+i` | `tab-history.forward` — 앞으로 |

## 개발

```sh
python3 test_tabhist.py       # 단위테스트
```
`tabhist.py`는 호출마다 새로 읽히므로 로직 수정 후 herdr reload/재시작 불필요. **매니페스트(`herdr-plugin.toml`) 수정 시에는 `herdr plugin link "$(pwd)"`로 재-link** 해야 반영됨. 특히 `[[events]]` 구독 등록은 재-link + reload 필요.

## Caveat

- `link`는 repo 절대경로를 가리킴 — repo를 옮기면 `herdr plugin unlink tab-history` 후 재-link.
- 히스토리는 이벤트가 발생해야 쌓이므로 **플러그인을 붙인 뒤부터** 채워진다.
- **이미 focus 중인 tab을 다시 focus** 하면 herdr가 `tab.focused` 이벤트를 발생시키지 않으므로 기록되지 않는다(정상 — 위치 변화가 없음).
- cursor는 매 tab focus 이벤트로 실제 focus와 동기화된다. 이벤트가 유실되면 어긋날 수 있으나, 다음 수동 tab 이동에서 새 항목이 append 되며 자기복구된다.
- macOS 전용(`platforms = ["macos"]`).
