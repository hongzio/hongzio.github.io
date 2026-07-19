# titles

각 **에이전트 pane의 라이브 상태**를 herdr 사이드바에 커스텀 토큰으로 흘려넣는 플러그인 (Claude + Codex). herdr 0.7.4의 커스텀 사이드바 토큰(`$name`) + pane metadata 리포팅 위에서 동작한다.

| 토큰/기능 | 내용 | 방식 |
|---|---|---|
| `$task` | 현재 task title | `report-metadata --token task=…` |
| `$ago` | 마지막 실제 턴 이후 경과(`Nm/Nh/Nd/Nw ago`, `just now`) | `report-metadata --token ago=…` |
| 탭 이름 | `🤖 <task>`로 rename (기본 on) | `herdr tab rename <tab_id> <label>` |
| 트리거 | 소켓 이벤트 구독 (`pane.updated` push) + `$ago` 전용 저빈도 타이머 |

`$ago`는 transcript의 **마지막 실제 assistant/user 턴 timestamp**를 현재와 비교해 **가장 큰 단위 + 아랫단위 반올림**으로 표시한다(3h29m→`3h ago`, 3h31m→`4h ago`, 반올림이 상위 단위에 닿으면 올림). 파일 mtime이 아니라 **턴 시각**을 쓰므로 `/rename`(custom-title 레코드)이나 세션 restore 같은 메타데이터 쓰기는 무시되고 진짜 마지막 작업만 반영된다. 재파싱은 mtime이 바뀔 때만 하고(캐시), 시간이 지나면 데몬이 매 폴링 재계산해 `Nm ago`가 tick 된다.

## title 소스 (pane별, 우선순위)

1. **명시적 사용자 지정 title** — Claude `/rename`의 `customTitle`, Codex `thread_name`. 사용자가 일부러 붙인 이름이라 무조건 우선. `/rename`은 terminal title도 바꾸지만 Claude의 라이브 롤링 요약이 곧 덮어쓰므로, transcript에서 읽어 명시 이름을 안정적으로 유지한다.
2. **pane 자체의 terminal title** — 위가 없고, shell 기본값(`user@host:~/path`)이 아니라 task 요약처럼 보이면 사용. Claude Code가 진행 중인 작업 요약으로 라이브 갱신(“온보드 페이지 다시 만들기”)하는 가장 신선한 소스.
3. **derived transcript title** — 위 둘 다 없을 때. Claude: `ai-title` > 첫 user 메시지. Codex: 첫 user 메시지. → Codex, 그리고 attach 직후(터미널 타이틀 붙기 전) Claude를 커버.

## 사용법

### 1) 사이드바 행에 토큰 넣기 — repo 루트 `herdr.toml`

```toml
[ui.sidebar.agents]
# 1행: 상태 · 워크스페이스 · 경과시간,  2행: task
rows = [["state_icon", "workspace", "$ago"], ["$task"]]
```

빌트인 토큰: `state_icon`, `state_text`, `workspace`, `tab`, `pane`, `agent`, `terminal_title`, `terminal_title_stripped`. 특정 에이전트만 다른 레이아웃은 `[ui.sidebar.agents.rows_by_agent]`.

> Claude만 herdr 빌트인 `terminal_title_stripped`로도 같은 라이브 타이틀을 얻을 수 있다. `$task`의 이점은 **Claude·Codex를 한 토큰으로 통일**하고, 터미널 타이틀이 없을 때 transcript로 fallback한다는 것.

### 2) 플러그인 등록

```sh
cd scripts/herdr-titles
herdr plugin link "$(pwd)"
herdr server reload-config
herdr plugin list                       # titles (Agent Titles) enabled 확인
python3 titles.py report-all         # 최초 backfill (이벤트가 아직 안 뜬 pane 채우기)
```

## config — 탭 rename 토글

기본적으로 agent pane의 **탭 이름도 같은 task title로 rename**한다(방법 2: `herdr tab rename`). 끄려면 `herdr plugin config-dir titles`의 `config.toml`:

```toml
[tab]
rename = false   # 기본 true. false면 $task 토큰만 표시하고 탭 이름은 건드리지 않음
```

- **agent가 있는 탭만** 대상 — `[git]`/`[vi]` 같은 non-agent 자동 라벨은 절대 안 건드린다.
- 현재 라벨이 목표와 같으면 rename API를 건너뛴다(탭 바 churn 방지).
- 탭 바가 좁아 라벨은 24자로 캡(사이드바 `$task`는 60자). rename은 herdr 자동 네이밍을 덮으므로, `/rename` 값이 있으면 그게 탭에도 그대로 들어간다(`$task`와 동일 소스).

## 왜 데몬인가 (그리고 왜 push인가)

플러그인 `[[events]]` **훅 표면**에는 terminal title 변경 이벤트가 없다(`agent_status_changed`는 idle↔working 플립에만 뜸). 하지만 herdr 소켓 API의 `events.subscribe`에는 있다: pane의 terminal title이 바뀔 때마다 **`pane.updated`** 가 뜨고, Claude `/rename`은 OSC 타이틀을 emit하므로(실측: `terminal_title` == `/rename`의 `customTitle`) 여기에 함께 잡힌다. 그래서 폴링 대신 **소켓 이벤트를 구독하는 push 데몬**을 쓴다.

데몬(`titles.py watch`)은 구독 하나를 유지하며, **pane별 변경 signature(terminal_title + last-activity ts + $ago 문자열)** 로 게이트해 **실제로 바뀐 pane만** 갱신한다. `pane.updated`가 pane 객체를 통째로 실어주므로 변경마다 `pane list`를 되묻지 않는다 → idle 땐 blocking read라 wakeup 0, `/rename`·title 변경은 <100ms 반영. 내가 쓴 `$task/$ago` 토큰도 `pane.updated`로 echo되지만 signature 3요소를 하나도 안 움직이므로 데몬이 자기 write에 반응하지 않는다.

`$ago`만은 시간이 흐르는 것만으로 값이 바뀌므로 유일하게 타이머가 필요하다. 단 고정 주기가 아니라 **다음 humanize 버킷 경계까지 sleep**한다("5m"면 분당 1회, "3h"면 시간당 1회로 자동으로 뜸해짐). 이 타이머는 놓친 explicit-title 쓰기에 대한 **저빈도 re-check fallback**도 겸한다. 즉시 전체 반영은 `titles.refresh`(`prefix+ctrl+u`).

**Codex `/rename`은 push의 예외다.** Claude와 달리 Codex는 rename 시 terminal title(OSC)을 안 바꾸고 공유 `session_index.jsonl`의 `thread_name`만 갱신 → herdr 이벤트가 안 뜬다. 그래서 변경 signature에 **resolved title을 포함**시키고 그 캐시 키에 `session_index.jsonl` mtime을 넣어, rename을 **다음 `$ago` 틱(≤ ago_cap, 기본 60s)** 에 잡는다(즉시는 `titles.refresh`). 또 herdr가 세션을 pane에 못 붙인 Codex pane(=`agent_session` 없음)은 **cwd로 rename된 rollout을 매칭**해 resolve하므로, 바인딩 안 된 세션의 `/rename`도 표시된다.

```
titles (Agent Titles)
  events:  pane.agent_status_changed ┐
           pane.agent_detected        ├─ titles.py ensure   # 데몬만 idempotent하게 띄움
           pane.created              ┘
  actions: titles.refresh              → titles.py report-all  # 즉시 전체 재계산(키용)

  daemon:  events.subscribe(pane.updated / created / closed / exited)  # push
           + $ago 버킷 경계 타이머
```

`ensure`는 pidfile로 단일 인스턴스를 보장한다(herdr 인스턴스당 하나, `HERDR_SOCKET_PATH` 키). 데몬은 그 socket이 사라지면(=herdr 종료) 스스로 exit하고, 이벤트 스트림이 끊기면 재구독한다. `$ago` 타이머 상한은 `TITLES_AGO_INTERVAL`(초, 기본 60; 하위호환으로 `TITLES_WATCH_INTERVAL`도 인식), 디버그 로그는 `TITLES_DEBUG=1` → state dir의 `watch.log`. 에러는 항상 로깅.

`/rename` 직후 **즉시** 반영을 원하면 `titles.refresh`를 키에 걸어라(`herdr.toml`):
```toml
[[keys.command]]
key = "prefix+ctrl+u"
type = "plugin_action"
command = "titles.refresh"
description = "refresh sidebar task titles"
```

## 구조

```
herdr-titles/
  herdr-plugin.toml   # events 3 (→ensure), action 1 (report-all)
  titles.py        # ensure / watch / report / report-all  + test_titles.py
  README.md
```

`report-metadata`는 `--source titles`로 네임스페이스를 잡아 다른 리포터와 충돌하지 않는다. title은 지속 토큰(TTL 없음)이라 유지되고, 값이 바뀔 때만(멱등) 다시 쓴다. pane이 사라지면 herdr가 metadata도 함께 정리한다.

> **주의**: 이벤트 훅은 `sh -lc`로 돌아 **시스템 python 3.9**(mise 아님)를 쓴다. 스크립트는 stdlib-only·3.9 호환이어야 한다(예: `tomllib` 금지). 죽은 훅은 `herdr plugin log list --plugin titles`로 진단.

## 테스트

```sh
python3 -m unittest test_titles
```

순수 파서(title 추출·shell-title 판정·이벤트 pane 추출·pane별 title 선택)만 테스트한다. herdr CLI/transcript 파일 접근은 얇은 래퍼로 격리.

## Caveat

- **min_herdr_version 0.7.4** — `report-metadata`와 커스텀 `$` 토큰이 0.7.4 기능.
- transcript fallback 경로는 `~/.claude/projects`, `~/.codex/sessions`(+ `session_index.jsonl`)를 읽기만 한다.
- macOS 전용(`platforms = ["macos"]`).
- 세션 id 매핑은 herdr가 pane에 붙여주는 `agent_session.value`(claude jsonl stem / codex rollout uuid)를 그대로 쓴다.
