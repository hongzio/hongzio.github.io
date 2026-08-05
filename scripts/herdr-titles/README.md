# titles

각 **에이전트 pane의 라이브 상태**를 herdr 사이드바에 커스텀 토큰으로 흘려넣는 플러그인 (Claude + Codex). herdr 0.7.4의 커스텀 사이드바 토큰(`$name`) + pane metadata 리포팅 위에서 동작하고, 에이전트 이름은 herdr 0.8.0의 `agent rename`을 그대로 쓴다.

| 토큰/기능 | 내용 | 방식 |
|---|---|---|
| `$task` | 현재 task title | `report-metadata --token task=…` |
| `$name` | herdr 에이전트 이름 (없으면 표시 안 함) | `agent list`에서 읽어 `--token name=…` |
| 탭 이름 | `🤖 <task>`로 rename (기본 on) | `herdr tab rename <tab_id> <label>` |
| rename UI | 현재 pane의 에이전트 이름을 바꾸는 팝업 (`titles.rename`) | `herdr agent rename` + 즉시 토큰 write |
| 트리거 | 소켓 이벤트 구독 (`pane.updated` push) + 60s 재조회 타이머 |

## `$name` — herdr 에이전트 이름 미러링

`$name`은 이 플러그인이 소유하는 값이 아니다. **진실은 herdr의 `agent rename`** 이고, 플러그인은 그걸 사이드바 토큰으로 옮겨줄 뿐이다(herdr에는 이름용 빌트인 사이드바 토큰이 없다: 빌트인은 `state_icon`, `state_text`, `workspace`, `tab`, `pane`, `agent`, `terminal_title`, `terminal_title_stripped`). 그래서 herdr의 규칙이 그대로 적용된다:

- 이름은 `[a-z][a-z0-9_-]{0,31}` — **한글·공백·대문자 불가**. 팝업이 herdr를 부르기 전에 같은 규칙으로 먼저 걸러주고, 중복 이름 같은 나머지 에러는 herdr 메시지를 그대로 보여준다.
- live agent 간 **유일**해야 한다.
- agent가 exit/release/replace되면 herdr가 이름을 **지운다**. 플러그인은 복구하지 않는다(이름이 사라지면 `$name` 토큰도 지워진다).

이름이 없으면 토큰을 **clear**한다(placeholder 없음) — 사이드바 행에는 아무것도 안 나온다.

`$name`은 `agent list`로만 읽을 수 있다. `pane.updated`가 실어주는 **PaneInfo에는 `name` 필드가 없기** 때문(AgentInfo에만 있다). 그래서 이름은 재조회 틱의 `agent list` 스냅샷에서 갱신되고, 틱 사이의 push 이벤트는 마지막 스냅샷의 이름을 재사용한다(빈 값으로 덮어쓰지 않는다).

## title 소스 (pane별, 우선순위)

1. **명시적 사용자 지정 title** — Claude `/rename`의 `customTitle`, Codex `thread_name`. 사용자가 일부러 붙인 이름이라 무조건 우선. `/rename`은 terminal title도 바꾸지만 Claude의 라이브 롤링 요약이 곧 덮어쓰므로, transcript에서 읽어 명시 이름을 안정적으로 유지한다.
2. **pane 자체의 terminal title** — 위가 없고, shell 기본값(`user@host:~/path`)이 아니라 task 요약처럼 보이면 사용. Claude Code가 진행 중인 작업 요약으로 라이브 갱신("온보드 페이지 다시 만들기")하는 가장 신선한 소스.
3. **derived transcript title** — 위 둘 다 없을 때. Claude: `ai-title` > 첫 user 메시지. Codex: 첫 user 메시지. → Codex, 그리고 attach 직후(터미널 타이틀 붙기 전) Claude를 커버.

## 사용법

### 1) 사이드바 행에 토큰 넣기 — repo 루트 `herdr.toml`

```toml
[ui.sidebar.agents]
# 1행: 상태 · 워크스페이스 · 에이전트 이름,  2행: task
rows = [["state_icon", "workspace", "$name"], ["$task"]]
```

특정 에이전트만 다른 레이아웃은 `[ui.sidebar.agents.rows_by_agent]`.

> Claude만 herdr 빌트인 `terminal_title_stripped`로도 같은 라이브 타이틀을 얻을 수 있다. `$task`의 이점은 **Claude·Codex를 한 토큰으로 통일**하고, 터미널 타이틀이 없을 때 transcript로 fallback한다는 것.

### 2) 이름 바꾸기 — 팝업 (`prefix+ctrl+r`)

```toml
[[keys.command]]
key = "prefix+ctrl+r"
type = "plugin_action"
command = "titles.rename"
description = "rename this agent"
```

현재 focus된 agent pane을 대상으로 작은 팝업이 뜬다. 현재 이름이 프리필되고, `enter` 저장 / `ctrl+d` 이름 삭제 / `esc` 취소 / `ctrl+u` 입력 지움. 저장에 성공하면 팝업이 **직접 `$name` 토큰과 탭 라벨을 write**하므로 틱을 기다리지 않는다. agent가 없는 pane에서 누르면 "No agent in this pane."을 띄운다.

셸에서 직접 치는 것도 당연히 된다 — `herdr agent rename <pane|name> <name>` / `--clear`. 이 경우엔 이벤트가 없어서 다음 틱(≤60s)이나 `titles.refresh`에 반영된다.

> herdr는 팝업을 **한 번에 하나만** 허용한다. 다른 팝업이 떠 있으면 이 액션은 아무 일도 안 하고 `herdr plugin log list --plugin titles`에 `popup already open`을 남긴다.

### 3) 플러그인 등록

```sh
cd scripts/herdr-titles
herdr plugin link "$(pwd)"
herdr server reload-config
herdr plugin list                       # titles (Agent Titles) enabled 확인
python3 titles.py report-all            # 최초 backfill (이벤트가 아직 안 뜬 pane 채우기)
```

## config — 탭 rename 토글

기본적으로 agent pane의 **탭 이름도 같은 task title로 rename**한다(`🤖 <task>`). 에이전트 이름은 사이드바 행에만 나오고 탭에는 안 들어간다 — 탭 바는 "저기서 무슨 일이 벌어지는가"를 답하는 자리다. 끄려면 `herdr plugin config-dir titles`의 `config.toml`:

```toml
[tab]
rename = false   # 기본 true. false면 토큰만 표시하고 탭 이름은 건드리지 않음
```

- **agent가 있는 탭만** 대상 — `[git]`/`[vi]` 같은 non-agent 자동 라벨은 절대 안 건드린다.
- 현재 라벨이 목표와 같으면 rename API를 건너뛴다(탭 바 churn 방지).
- 탭 바가 좁아 라벨은 24자로 캡(사이드바 `$task`는 60자). task가 없으면 라벨을 비우는 대신 herdr 자동 라벨을 그대로 둔다. rename은 herdr 자동 네이밍을 덮으므로, `/rename` 값이 있으면 그게 탭에도 그대로 들어간다(`$task`와 동일 소스).

## 왜 데몬인가 (그리고 왜 push인가)

플러그인 `[[events]]` **훅 표면**에는 terminal title 변경 이벤트가 없다(`agent_status_changed`는 idle↔working 플립에만 뜸). 하지만 herdr 소켓 API의 `events.subscribe`에는 있다: pane의 terminal title이 바뀔 때마다 **`pane.updated`** 가 뜨고, Claude `/rename`은 OSC 타이틀을 emit하므로(실측: `terminal_title` == `/rename`의 `customTitle`) 여기에 함께 잡힌다. 그래서 폴링 대신 **소켓 이벤트를 구독하는 push 데몬**을 쓴다.

데몬(`titles.py watch`)은 구독 하나를 유지하며, **pane별 변경 signature(title + terminal_title + name)** 로 게이트해 **실제로 바뀐 pane만** 갱신한다. `pane.updated`가 pane 객체를 통째로 실어주므로 변경마다 `pane list`를 되묻지 않는다 → idle 땐 blocking read라 wakeup 0, `/rename`·title 변경은 <100ms 반영.

**이벤트가 아예 안 뜨는 변경이 두 가지** 있고, 60초 재조회 타이머(`TITLES_REFRESH_INTERVAL`)는 순전히 그 둘을 위한 fallback이다:

1. **Codex `/rename`** — Claude와 달리 terminal title(OSC)을 안 바꾸고 공유 `session_index.jsonl`의 `thread_name`만 갱신한다. 그래서 변경 signature에 resolved title을 포함시키고 그 캐시 키에 `session_index.jsonl` mtime을 넣어 다음 틱에 잡는다. (이건 **task 이름**이지 agent 이름이 아니다.)
2. **`herdr agent rename`** — 이름 변경에 대응하는 herdr 이벤트가 없다(실측: rename 후 `pane.updated` 0건). 팝업 경로는 자기가 토큰을 쓰므로 즉시 반영되고, 셸에서 직접 친 rename만 틱을 기다린다.

틱은 `agent list` 스냅샷 하나로 두 가지를 동시에 처리한다(이름 + transcript 재조회). 즉시 전체 반영은 `titles.refresh`(`prefix+ctrl+u`).

또 herdr가 세션을 pane에 못 붙인 Codex pane(=`agent_session` 없음)은 **cwd로 rename된 rollout을 매칭**해 resolve하므로, 바인딩 안 된 세션의 `/rename`도 표시된다.

```
titles (Agent Titles)
  startup: (세션 복원 / live handoff) ┐
  events:  pane.agent_detected        ┴─ titles.py ensure   # 데몬만 idempotent하게 띄움
  actions: titles.refresh              → titles.py report-all   # 즉시 전체 재계산(키용)
           titles.rename               → titles.py rename-open  # 팝업 열기(대상 pane 결정)
  panes:   rename-agent (popup)        → titles.py rename-ui    # 이름 입력 UI

  daemon:  events.subscribe(pane.updated / created / closed / exited)  # push
           + 60s agent list 재조회 타이머
```

데몬 부트스트랩은 **`[[startup]]` 훅**(herdr 0.7.5: 세션 복원·live handoff 직후 인스턴스당 1회, 소켓 준비 후)이 맡고, `pane.agent_detected`는 크래시 복구용 안전망이다. `ensure`는 pidfile로 단일 인스턴스를 보장한다(herdr 인스턴스당 하나, `HERDR_SOCKET_PATH` 키). 데몬은 그 socket이 사라지면(=herdr 종료) 스스로 exit하고, 이벤트 스트림이 끊기면 재구독한다. 재조회 주기는 `TITLES_REFRESH_INTERVAL`(초, 기본 60), 디버그 로그는 `TITLES_DEBUG=1` → state dir의 `watch.log`. 에러는 항상 로깅.

## rename 팝업이 대상 pane을 정하는 법

팝업은 focus를 가져가는 순간 **자기 pane의 컨텍스트만** 보게 된다. 그래서 대상은 액션 단계(`rename-open`)에서 정하고 `TITLES_TARGET_PANE`으로 넘긴다(nav favorites가 탭에 쓰는 것과 같은 패턴). 우선순위는 `HERDR_PLUGIN_CONTEXT_JSON.focused_pane_id`(키를 눌렀을 때 사용자가 보고 있던 pane) → `HERDR_PANE_ID`(명령이 실행된 pane) → `agent list`의 `focused` 에이전트. 지정된 pane에 agent가 없으면 **다른 에이전트로 슬쩍 갈아타지 않고** 빈 대상으로 팝업을 열어 그렇다고 말한다.

## 구조

```
herdr-titles/
  herdr-plugin.toml   # startup 1, events 1 (→ensure), panes 1 (popup), actions 2
  titles.py           # ensure / watch / report / report-all / rename-open / rename-ui
  test_titles.py
  README.md
```

`report-metadata`는 `--source titles`로 네임스페이스를 잡아 다른 리포터와 충돌하지 않는다. 토큰은 지속 토큰(TTL 없음)이라 유지되고, 값이 바뀔 때만(멱등) 다시 쓴다. pane이 사라지면 herdr가 metadata도 함께 정리한다.

> **주의**: 이벤트 훅은 `sh -lc`로 돌아 **시스템 python 3.9**(mise 아님)를 쓴다. 스크립트는 stdlib-only·3.9 호환이어야 한다(예: `tomllib` 금지). 죽은 훅은 `herdr plugin log list --plugin titles`로 진단.

## 테스트

```sh
python3 -m unittest test_titles
```

순수 파서(title 추출·shell-title 판정·이벤트 pane 추출·pane별 title 선택·이름 검증·대상 pane 결정·herdr 에러 메시지 추출)만 테스트한다. herdr CLI/transcript 파일 접근은 얇은 래퍼로 격리.

## Caveat

- **min_herdr_version 0.8.0** — `agent rename`과 `AgentInfo.name`이 0.8.0 기능이다(`report-metadata`·커스텀 `$` 토큰은 0.7.4, `[[startup]]` 훅은 0.7.5).
- transcript fallback 경로는 `~/.claude/projects`, `~/.codex/sessions`(+ `session_index.jsonl`)를 읽기만 한다.
- macOS 전용(`platforms = ["macos"]`).
- 세션 id 매핑은 herdr가 pane에 붙여주는 `agent_session.value`(claude jsonl stem / codex rollout uuid)를 그대로 쓴다.
- pane metadata 토큰 write는 `pane.updated`를 **발생시키지 않는다**(실측: revision만 오르고 이벤트 0건). 데몬이 자기 write에 반응할 일 자체가 없다.
