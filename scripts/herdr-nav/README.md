# nav

workspace 안을 "원하는 곳으로 점프"하는 herdr 네비게이션 유틸 4종을 **한 플러그인(id `nav`)** 으로 묶은 번들. 각 기능은 독립이고, 관리 단위(link 1번·manifest 1개)만 하나로 합쳐져 있다.

| 기능 | 하는 일 | 기본 키 |
|---|---|---|
| **favorites** | 탭을 `ctrl+1..9` 슬롯에 핀 고정 → 즉시 focus | `prefix+ctrl+f`(오버레이), `ctrl+1..9`(focus) |
| **conversations** | 과거 Claude/Codex 대화를 골라 복원해서 이동 | `prefix+c` |
| **attention** | 손이 필요한(done/blocked) 에이전트들을 최신순으로 순회 focus | `prefix+ctrl+.` |
| **tab-history** | 브라우저식 탭 back/forward + 최근 두 탭 토글 | `prefix+ctrl+o`/`prefix+ctrl+i`, `prefix+ctrl+;`(토글) |

## 구조

```
herdr-nav/
  herdr-plugin.toml   # 통합 매니페스트 — events 2, panes 2, actions 17
  favorites.py        # 탭 핀 (오버레이 ui / focus N)          + test_favorites.py
  conversations.py    # 대화 피커 (list/preview/open/ui)        + test_conversations.py
  attention.py        # 완료 에이전트 로그/focus (record/focus) + test_attention.py
  tabhist.py          # 탭 히스토리 (record/back/forward/toggle) + test_tabhist.py
```

action id는 기능별 prefix로 평평하게 구분한다(같은 플러그인 안에서 충돌 방지 + 키바인딩 가독성):

| action | → | action | → |
|---|---|---|---|
| `nav.fav-open` | 즐겨찾기 오버레이 | `nav.conv-open` | 대화 피커(auto) |
| `nav.fav-1`..`nav.fav-9` | 핀 슬롯 focus | `nav.conv-open-fzf` / `-native` | 모드 강제 |
| `nav.attention-focus` | 대기 에이전트 순회 | `nav.tab-back` / `-forward` / `-toggle` | 탭 back/forward/토글 |

pane id(`fav-picker`, `conversations`)는 매니페스트 내부에서 action의 `--entrypoint`가 참조하는 이름일 뿐, 키바인딩에는 노출되지 않는다.

## 상태 / 설정 파일

**유저 편집 config**와 **기계 write state**를 분리하고, 둘 다 herdr가 넘겨주는 per-plugin dir를 쓴다(경로 하드코딩 안 함 → 유저가 `HERDR_CONFIG_PATH`로 config 위치를 바꿔도 따라감). 핀은 오버레이가 write하는 disposable 데이터라 config가 아니라 state로 둔다.

**config** — 유저가 튜닝하는 값. `HERDR_PLUGIN_CONFIG_DIR`(기본 `~/.config/herdr/plugins/config/nav/`)의 `config.toml`:

| 섹션 | 키 | 성격 |
|---|---|---|
| `[tab-history]` | `max` | back/forward로 되짚을 최근 탭 개수 (첫 record 때 기본 100으로 자동 생성) |
| `[tab-history]` | `min_dwell_seconds` | 탭에 이 시간(초) 이상 머물러야 히스토리에 기록 (기본 5, `0`=끄고 즉시 기록). 빠르게 지나친 탭은 무시 |

**state** — 기계가 write, 언제든 삭제 가능. `HERDR_PLUGIN_STATE_DIR`(기본 `~/.local/state/herdr/plugins/nav/`)을 공유하되 파일명이 안 겹친다:

| 모듈 | 파일 | 성격 |
|---|---|---|
| tabhist | `tab-history.json` | 탭 히스토리(entries+cursor+pending) |
| attention | `recents.log` | 완료(done/blocked) 에이전트 append 로그 |
| attention | `attention-cursor` | 순회 커서 — 마지막으로 focus한 pane |
| favorites | `favorites.toml` | 핀 슬롯 1..9 → tab_id |
| conversations | (영속 상태 없음) | `~/.claude/projects`, `~/.codex/sessions` 등을 읽기만 |

## 설치

```sh
# 1) 키바인딩: repo 루트 herdr.toml을 herdr config로 심링크 (nav.* 참조가 여기 있음)
mkdir -p ~/.config/herdr
ln -sf "$(pwd)/../../herdr.toml" ~/.config/herdr/config.toml

# 2) 플러그인 등록 (scripts/herdr-nav 에서)
herdr plugin link "$(pwd)"
herdr server reload-config
herdr plugin list            # nav (Navigation) enabled 확인
```

## 개발

```sh
# 각 모듈 단위테스트 (herdr-nav 디렉토리에서)
for t in test_favorites test_conversations test_attention test_tabhist; do python3 -m unittest "$t"; done
```

py 로직은 호출마다 새로 읽히므로 수정 후 재시작 불필요. **매니페스트(`herdr-plugin.toml`) 수정 시에는** `herdr plugin link "$(pwd)"` 재-link + `herdr server reload-config` 필요(특히 events 구독·action 추가).

## Caveat

- `link`는 repo 절대경로를 가리킴 — repo 이동 시 `herdr plugin unlink nav` 후 재-link.
- events 기반(attention/tab-history)은 **플러그인을 붙인 뒤부터** 기록이 쌓인다.
- macOS 전용(`platforms = ["macos"]`).
