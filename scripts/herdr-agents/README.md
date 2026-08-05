# agents

지금 보고 있는 **에이전트 그 자체**에 하는 동작들을 `prefix+a` 팝업 하나로 모은 herdr 플러그인(id `agents`). 기능이 늘어나도 키는 `prefix+a` 하나 — 새 기능은 팝업 메뉴 항목으로 붙는다([기능 추가](#기능-추가)).

## 기능

| 항목 | 키 | 하는 일 |
|---|---|---|
| **fork** | `prefix+a` → `f`/enter | 지금 pane의 대화를 그대로 복사한 새 에이전트를 **같은 workspace의 새 탭**으로 띄운다 |

### fork

두 에이전트 모두 네이티브 fork를 갖고 있어서 transcript를 직접 복사하지 않는다:

| kind | 실행 커맨드 |
|---|---|
| claude | `claude --resume <session-id> --fork-session` (원본은 그대로, 새 session id로 이어씀) |
| codex | `codex fork <session-id>` (새 세션의 `session_meta.forked_from_id`에 원본이 기록됨) |

session id는 `herdr agent get`의 `agent_session.value`에서 가져온다(`kind = "id"`일 때만 — herdr가 세션을 transcript 경로로만 알고 있으면 둘 중 어느 CLI도 받지 못하므로 포크 불가로 처리한다).

동작 순서:

1. `herdr tab create --workspace <원본 ws> --cwd <원본 cwd> --no-focus`
2. 새 탭 root pane에 `pane run <fork 커맨드>` (쉘 프롬프트 뜰 때까지 짧게 재시도)
3. `herdr tab focus <새 탭>`

**agent name은 붙이지 않는다.** `herdr agent start <NAME>`이 아니라 `pane run`으로 띄우기 때문에 포크된 에이전트는 herdr agent name이 없다(사이드바 `$name` 빈칸). 이름은 살아있는 에이전트끼리 유일해야 해서 복사본이 원본 이름을 물려받을 수 없고, 임의로 지어 붙이면 사이드바만 지저분해진다. 필요하면 `prefix+ctrl+r`(titles 플러그인)로 직접 붙이면 된다.

포크 시점은 **디스크에 flush된 transcript 기준**이다. 원본이 턴 도중(`working`)이면 진행 중인 마지막 응답은 포크에 안 들어올 수 있다.

## 구조

```
herdr-agents/
  herdr-plugin.toml   # panes 1 (menu popup), actions: menu + 기능별 단축 액션
  agents.py           # menu-open / menu-ui / <기능 id> [PANE]
  test_agents.py      # 순수 함수 (대상 해석, 커맨드 조립, 검증, 메뉴 모델)
```

기능 하나는 `agents.py` 안에서 세 조각으로 표현된다 — `MENU` 항목(팝업에 보이는 것), `ITEM_ERROR` 검증기(이 에이전트에 쓸 수 있나), `FEATURE_COMMANDS` 실행부. 셋 다 **기능 id**로 묶이고, 그 id가 곧 서브커맨드 이름이라 팝업은 `agents.py <기능 id> <pane>`을 그대로 띄우면 된다.

| action | → |
|---|---|
| `agents.menu` | 기능 팝업 열기 (`prefix+a`) — 모든 기능은 여기로 닿는다 |
| `agents.fork` | 팝업 없이 바로 fork (키에 직접 바인딩하고 싶을 때) |

### 대상 pane 해석

액션은 `HERDR_PLUGIN_CONTEXT_JSON.focused_pane_id`(키를 누른 순간 보고 있던 pane)로 대상을 정하고, 그 값을 `AGENTS_TARGET_PANE`으로 팝업에 넘긴다. 팝업은 포커스를 가져간 뒤라 자기 pane밖에 못 보기 때문(titles의 rename 팝업과 같은 패턴). 대상 pane에 에이전트가 없으면 다른 에이전트로 슬쩍 갈아타지 않고 그대로 에러를 띄운다.

### 팝업이 직접 실행하지 않는 이유

팝업은 herdr pane이고, 프로세스가 끝나면 herdr가 팝업을 닫으면서 **직전 포커스를 복원**한다. 팝업 안에서 작업을 끝까지 하면 그 복원과 경쟁한다(fork라면 새 탭이 방금 가져간 포커스를 뺏긴다). 그래서 팝업은 검증만 하고(에러는 팝업 안에 표시) 실제 작업은 detach된 자식 프로세스(`agents.py <기능 id> <pane>`)에 넘기고 즉시 종료한다. detach된 쪽은 stderr가 갈 곳이 없으므로 실패는 `herdr notification show`로 알린다.

검증은 **항목별**이다(`ITEM_ERROR`). 기능마다 요구하는 게 다르므로(fork는 fork 가능한 CLI의 session id가 필요하지만 다음 기능은 아닐 수 있다) 메뉴 전체를 한 검사로 막지 않고, 커서가 놓인 항목의 사용 가능 여부를 누르기 전에 힌트 자리에 보여준다.

## 설치

```sh
# 1) 키바인딩: repo 루트 herdr.toml을 herdr config로 심링크 (agents.* 참조가 여기 있음)
mkdir -p ~/.config/herdr
ln -sf "$(pwd)/../../herdr.toml" ~/.config/herdr/config.toml

# 2) 플러그인 등록 (scripts/herdr-agents 에서)
herdr plugin link "$(pwd)"
herdr server reload-config
herdr plugin list            # agents (Agent Actions) enabled 확인
```

## 개발

```sh
python3 -m unittest test_agents
```

py 로직은 호출마다 새로 읽히므로 수정 후 재시작 불필요. **매니페스트(`herdr-plugin.toml`) 수정 시에는** `herdr plugin link "$(pwd)"` 재-link + `herdr server reload-config` 필요.

### 기능 추가

`agents.py`에서 세 군데 + 매니페스트 한 줄(팝업 크기)이면 끝이고, 키바인딩은 건드릴 게 없다:

1. `MENU`에 `Item(<id>, <단축키>, <제목>, <설명>)` 추가 — 단축키로 `q`/`j`/`k`는 못 쓴다(팝업이 닫기·이동으로 먼저 먹는다).
2. 그 기능이 아무 에이전트에나 되는 게 아니면 `ITEM_ERROR[<id>]`에 검증기 추가 (에이전트 자체가 없는 경우는 공통 처리).
3. `FEATURE_COMMANDS[<id>]`에 `cmd_*` 추가 — 시그니처는 `(pane_arg: str) -> int`, 실패는 `_fail(<id>, msg)`.
4. 매니페스트 팝업 `height`를 항목 수만큼 키운다 (현재 9 = 헤더+빈줄+항목1+빈줄+힌트).

키를 따로 주고 싶으면 매니페스트에 `[[actions]]` 하나(`agents.py <id>` 실행)를 더하고 `herdr.toml`에서 바인딩하면 된다. 테스트가 1↔3 연결(모든 `MENU` 항목이 실행 가능한지)과 단축키 충돌을 검사하므로 빠뜨리면 `python3 -m unittest test_agents`에서 걸린다.

## Caveat

- `link`는 repo 절대경로를 가리킴 — repo 이동 시 `herdr plugin unlink agents` 후 재-link.
- fork는 claude / codex만. 다른 kind에서는 팝업 힌트 자리에 지원 안 한다고 표시하고 아무것도 하지 않는다.
- herdr는 팝업을 한 번에 하나만 띄운다 — 다른 팝업이 열려 있으면 `prefix+a`는 no-op이 되고 이유는 플러그인 로그(`herdr plugin log`)에 남는다.
- macOS 전용(`platforms = ["macos"]`).
