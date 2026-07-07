# favorites

herdr 탭을 `ctrl+1..9` 슬롯에 고정(pin)하는 herdr 플러그인.

`prefix+ctrl+f` → 오버레이 → 슬롯 선택 → `enter`로 **현재 탭**을 그 슬롯에 저장 → 이후 `ctrl+1..9`로 그 탭에 focus.

## 기능

- **9개 슬롯** — 각 슬롯에 tab_id 하나를 저장
- **오버레이 UI** — `↑/↓`(또는 `j/k`, 숫자키)로 이동, `enter`로 현재 탭 저장(저장 후 닫힘), `x`/`delete`로 슬롯 비우기, `esc`로 닫기
- **라벨 표시** — 저장된 tab_id를 `herdr tab list`로 조회해 `workspace #번호 라벨`로 보여줌. 없어진 탭은 `(missing)`, 지금 보고 있던 탭은 `← current`
- **즉시 focus** — non-prefix `ctrl+1..9` → `favorites.focus-N` 액션 → `herdr tab focus`

## 동작 원리

오버레이는 focus를 가져가는 순간 "직전에 어떤 탭이 활성이었는지" 스스로 알 수 없다. 그래서
`prefix+ctrl+f` → `favorites.open` **plugin_action** 이 실행되고, 이 action의 command는
herdr가 주입해주는 `$HERDR_TAB_ID`(트리거 시점 focus된 탭)를 `--env FAV_ACTIVE_TAB=...`로
오버레이에 넘겨준다. 오버레이는 이 값을 슬롯에 저장한다.

> plugin_action의 command 환경에는 `HERDR_ACTIVE_TAB_ID`(키바인딩 전용)는 없지만,
> `HERDR_TAB_ID`/`HERDR_PANE_ID`/`HERDR_WORKSPACE_ID`/`HERDR_PLUGIN_CONTEXT_JSON`
> 등 focus 컨텍스트가 들어온다. 그래서 `HERDR_TAB_ID`로 충분하다.

저장 위치는 `~/.config/herdr/favorites.toml` (`N = "tab_id"` 형식). `prefix+ctrl+f` 오버레이가
쓰고, `ctrl+1..9` → `favorites.focus-N` 액션(`picker.py focus N`)이 읽어 `herdr tab focus` 한다.
슬롯이 비어있거나 저장된 탭이 없어졌으면 조용히 no-op.

> plugin_action은 런타임 인자를 못 받아서(`invoke` params = plugin_id/action_id/context 뿐)
> 슬롯마다 `focus-1..9` 액션을 따로 둔다. 대신 파싱은 전부 `picker.py`에 모여 있고
> `herdr.toml`은 `command = "favorites.focus-N"` 한 줄씩만 갖는다.

## 요구사항

| 도구 | 용도 |
|---|---|
| `herdr` ≥ 0.7.1 | 호스트 (`tab list`/`tab focus`, `HERDR_ACTIVE_TAB_ID` 노출) |
| `python3` | 로직 (표준 라이브러리 `curses`만 사용) |

## 설치

### 1. herdr 설정 연결
`prefix+ctrl+f` 와 `ctrl+1..9` 키바인딩은 이 repo의 `herdr.toml`에 있음. herdr config로 심링크:
```sh
mkdir -p ~/.config/herdr
ln -sf "$(pwd)/../../herdr.toml" ~/.config/herdr/config.toml   # repo 루트의 herdr.toml
```

### 2. 플러그인 등록
dotfiles repo 안에 있으므로 `link` (편집이 라이브 반영):
```sh
herdr plugin link "$(pwd)"          # scripts/herdr-favorites 에서 실행
herdr server reload-config
herdr plugin list                   # favorites enabled 확인
```
> herdr 서버가 실행 중이어야 함. 처음이면 `herdr` 한 번 실행.

## 사용

1. 슬롯에 넣고 싶은 탭으로 이동
2. `prefix+ctrl+f` → 오버레이
3. `↑/↓`로 슬롯 선택 → `enter` (그 슬롯에 현재 탭 저장, 오버레이 닫힘)
4. 이후 `ctrl+1..9`로 해당 탭에 즉시 focus

슬롯 비우기: 오버레이에서 슬롯 선택 후 `x` 또는 `delete`.

## 구성

| 파일 | 역할 |
|---|---|
| `herdr-plugin.toml` | 매니페스트 — overlay pane(`picker`) + `open`·`focus-1..9` 액션 |
| `picker.py` | 로직 — `ui`(오버레이) / `focus <slot>` 서브커맨드 + 파일 parse/render |
| `test_picker.py` | 단위테스트 (파일 parse/render, 슬롯 렌더, `focus` 디스패치) |

키바인딩은 **매니페스트가 아니라 유저 `herdr.toml`** 에 둠 (herdr가 플러그인 매니페스트의 키는 안 읽음). 전부 `type=plugin_action` (conv-picker와 동일한 구조):

| 키 | 액션 |
|---|---|
| `prefix+ctrl+f` | `favorites.open` — 오버레이 (액션이 `$HERDR_TAB_ID`를 `--env`로 넘김) |
| `ctrl+1..9` | `favorites.focus-1..9` — 슬롯 N의 탭에 focus |

## 개발

```sh
python3 test_picker.py       # 단위테스트
```
`picker.py`는 호출마다 새로 읽히므로 로직 수정 후 herdr reload/재시작 불필요. **매니페스트(`herdr-plugin.toml`) 수정 시에는 `herdr plugin link "$(pwd)"`로 재-link** 해야 반영됨 (`herdr server reload-config`는 config.toml 키바인딩만 다시 읽고 플러그인 매니페스트는 안 읽음).

## Caveat

- `link`는 repo 절대경로를 가리킴 — repo를 옮기면 `herdr plugin unlink favorites` 후 재-link.
- 저장하는 건 tab_id(`w1:t1`)라서 그 탭을 닫으면 슬롯은 `(missing)`이 되고 `ctrl+N`은 아무 동작 안 함. 다시 `enter`로 덮어쓰면 됨.
- macOS 전용(`platforms = ["macos"]`).
