# conv-picker

Claude/Codex 대화 목록을 herdr 오버레이에서 골라 복구하는 herdr 플러그인.

`prefix+c` → 오버레이 picker → 최신순 대화 목록에서 선택 → 복구.

## 기능

- **Claude + Codex** 대화를 한 목록에 병합, **최신순** 정렬
- **스트리밍 파싱** — 목록이 blocking 없이 파싱되는 대로 채워짐 (622개 기준 ~0.5s)
- **라벨 우선순위**: Claude `/rename`(custom-title) > AI 자동 제목(ai-title) > 첫 유저 메시지 / Codex는 `thread_name`
- **활성 표시**: 현재 agent에서 돌고 있는 대화는 `●`, 아니면 `○`
- **fzf preview**: 오른쪽에 대화 마지막 메시지들
- **복구 dispatch** (3-케이스):
  1. 이미 agent에서 활성 → 그 pane을 **focus**
  2. 대화의 working dir와 같은 루트 cwd의 space가 있으면 → 그 space에 **새 탭**으로 복구
  3. 같은 space가 없으면 → 그 cwd로 **새 space + 새 탭** 복구
- **탭 이름**: 새로 만드는 탭은 대화 이름으로 라벨링 — 제목(custom-title/ai-title/`thread_name`) 우선, 없으면 첫 유저 메시지를 짧게(≤30자), 그것도 없으면 cwd 이름

## 요구사항

| 도구 | 용도 |
|---|---|
| `herdr` ≥ 0.7.1 | 호스트 (agent_session 노출 필요) |
| `fzf` | picker UI |
| `python3` | 로직 (표준 라이브러리만 사용) |
| `claude` / `codex` CLI | 대화 resume |
| **claude/codex integration** | **필수** — `agent_session` report (아래 3번) |

## 설치

### 1. herdr + 의존성
```sh
brew install herdr fzf     # herdr는 homebrew-core, tap 불필요
# python3, claude, codex CLI는 별도 준비
```

### 2. herdr 설정 연결
`prefix+c` 키바인딩은 이 repo의 `herdr.toml`에 있음. herdr config로 심링크:
```sh
mkdir -p ~/.config/herdr
ln -sf "$(pwd)/../../herdr.toml" ~/.config/herdr/config.toml   # repo 루트의 herdr.toml
```

### 3. Agent integration (필수)
```sh
herdr integration install claude
herdr integration install codex
```
SessionStart hook이 세션 id를 herdr에 report → `pane list`의 `agent_session.value`가 채워짐.
**이게 없으면 "이미 활성" 판별(케이스 1)이 동작하지 않음.**

### 4. 플러그인 등록
dotfiles repo 안에 있으므로 `link` (편집이 라이브 반영):
```sh
herdr plugin link "$(pwd)"          # scripts/herdr-conv-picker 에서 실행
herdr server reload-config
herdr plugin list                   # conv-picker enabled 확인
```
> herdr 서버가 실행 중이어야 함(link/reload는 socket API 사용). 처음이면 `herdr` 한 번 실행.

남에게 공유·설치용으로는 GitHub에서 직접 설치도 가능(별도 사본, 라이브 편집 X):
```sh
herdr plugin install hongzio/hongzio.github.io/scripts/herdr-conv-picker
```

## 사용

`prefix+c` → 오버레이 → 타이핑으로 필터 → `enter`로 복구. `esc`로 취소.

## 구성

| 파일 | 역할 |
|---|---|
| `herdr-plugin.toml` | 매니페스트 — overlay pane(`picker`) + `open` 액션 |
| `picker.py` | 로직 — `list` / `preview` / `open` / `ui` 서브커맨드 |
| `test_picker.py` | 순수 함수 단위테스트 |

키바인딩(`prefix+c` → `conv-picker.open`)은 **매니페스트가 아니라 유저 `herdr.toml`** 에 둠 (herdr가 플러그인 매니페스트의 키는 안 읽음).

데이터 소스:
- Claude: `~/.claude/projects/<enc-cwd>/<session-id>.jsonl`
- Codex: `~/.codex/session_index.jsonl` (+ rollout `session_meta`)

## 개발

```sh
python3 test_picker.py       # 단위테스트
python3 picker.py list       # 목록 출력(디버그)
```
`picker.py`는 호출마다 새로 읽히므로 로직 수정 후 **herdr reload/재시작 불필요**. 매니페스트(`herdr-plugin.toml`) 수정 시에만 `herdr server reload-config`.

## Caveat

- **integration 설치 전부터 돌던 세션**은 `agent_session`이 없어 "활성"으로 인식되지 않음 → 골라도 새 pane으로 resume(중복 가능). 재시작하면 해소되는 self-healing 한계.
- `link`는 repo 절대경로를 가리킴 — repo를 옮기면 `herdr plugin unlink conv-picker` 후 재-link.
- macOS 전용(`platforms = ["macos"]`).
