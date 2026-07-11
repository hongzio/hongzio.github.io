#!/usr/bin/env python3
"""herdr attention plugin.

Cycle focus through the agents that need attention — the ones that entered
done/blocked, i.e. finished a turn or are waiting on input. Completions are
tracked event-driven via herdr's `pane.agent_status_changed` plugin event
(no daemon, no polling).

Subcommands:
  record   append a completion to the recents log (run from the [[events]] hook)
  focus    focus the NEXT waiting agent, rotating (run from the [[actions]] hook)

Behaviour: `focus` builds the newest-first list of agents still in an attention
state (done/blocked) and rotates through it. A persisted cursor remembers the
last agent we focused; each press advances to the one after it, wrapping at the
end. If the cursor is gone or resumed working, we restart at the newest. With a
single waiting agent this collapses to the old idempotent behaviour.

The parse/select helpers are pure (no I/O) so they can be unit-tested; the herdr
CLI, the recents log, and the cursor file are the only external dependencies and
are reached through thin wrappers.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

# Statuses that mean "stopped working, needs my attention". herdr reports `done`
# the instant an agent finishes a turn; `blocked` means it is waiting on
# input/permission. (`idle` — a done turn that has since settled — is
# deliberately excluded so the cycle holds only freshly-done or blocked agents.)
ATTENTION_STATES = frozenset({"done", "blocked"})

KEEP_LINES = 100   # lines retained when the log is trimmed
TRIM_AT = 400      # trim once the log grows past this many lines


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------


def state_dir() -> str:
    """Per-plugin state dir (herdr sets HERDR_PLUGIN_STATE_DIR); fall back sanely."""
    d = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if not d:
        d = os.path.join(
            os.path.expanduser("~"), ".local", "state", "herdr", "plugins", "nav"
        )
    return d


def recents_path() -> str:
    return os.path.join(state_dir(), "recents.log")


def cursor_path() -> str:
    return os.path.join(state_dir(), "attention-cursor")


# ---------------------------------------------------------------------------
# pure helpers (no I/O)
# ---------------------------------------------------------------------------


def extract_event(obj: object) -> tuple[str | None, str | None]:
    """(pane_id, agent_status) from a pane.agent_status_changed event payload.

    Payload shape (confirmed):
      {"event": "pane_agent_status_changed",
       "data": {"type": "pane_agent_status_changed",
                "pane_id": "w1:p1", "workspace_id": "w1",
                "agent_status": "done", "agent": "claude"}}
    Returns (None, None) for anything that does not match.
    """
    data = obj.get("data") if isinstance(obj, dict) else None
    if not isinstance(data, dict):
        return None, None
    pane = data.get("pane_id")
    status = data.get("agent_status")
    if not isinstance(pane, str) or not pane:
        return None, None
    if not isinstance(status, str) or not status:
        return None, None
    return pane, status


def parse_recents(text: str) -> list[str]:
    """Ordered (oldest -> newest) pane_ids from `<ts>\\t<pane_id>\\t<status>` lines.

    Tolerant of blank/short lines; a bare `<pane_id>` line is also accepted.
    """
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        pane = (parts[1] if len(parts) >= 2 else parts[0]).strip()
        if pane:
            out.append(pane)
    return out


def newest_unique(pane_ids: list[str]) -> list[str]:
    """Newest-first, de-duplicated (keeps each pane's most recent position)."""
    seen: set[str] = set()
    out: list[str] = []
    for pane in reversed(pane_ids):
        if pane not in seen:
            seen.add(pane)
            out.append(pane)
    return out


def waiting_panes(order: list[str], live: dict[str, str]) -> list[str]:
    """Panes from `order` (newest-first) that still exist and need attention."""
    return [pane for pane in order if live.get(pane) in ATTENTION_STATES]


def next_in_cycle(
    order: list[str], live: dict[str, str], cursor: str | None
) -> str | None:
    """Next attention pane after `cursor`, rotating over the newest-first list.

    Advances one step past `cursor` and wraps at the end. If `cursor` is not
    among the currently-waiting panes (never set, gone, or resumed working),
    starts at the newest. Returns None when nothing is waiting.
    """
    panes = waiting_panes(order, live)
    if not panes:
        return None
    if cursor in panes:
        return panes[(panes.index(cursor) + 1) % len(panes)]
    return panes[0]


def trim_text(text: str, keep: int) -> str:
    """Keep only the last `keep` non-blank lines."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-keep:]) + "\n"


# ---------------------------------------------------------------------------
# herdr CLI wrappers
# ---------------------------------------------------------------------------


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def live_status_map() -> dict[str, str]:
    """pane_id -> agent_status for every live agent (empty on any failure)."""
    try:
        proc = subprocess.run(
            [herdr_bin(), "agent", "list"], capture_output=True, text=True
        )
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, str] = {}
    for agent in data.get("result", {}).get("agents", []):
        pane = agent.get("pane_id")
        status = agent.get("agent_status")
        if pane:
            result[pane] = status
    return result


def focus_pane(pane: str) -> bool:
    try:
        proc = subprocess.run(
            [herdr_bin(), "agent", "focus", pane], capture_output=True, text=True
        )
        return proc.returncode == 0
    except OSError:
        return False


# ---------------------------------------------------------------------------
# recents log I/O
# ---------------------------------------------------------------------------


def append_recent(pane: str, status: str) -> None:
    directory = state_dir()
    os.makedirs(directory, exist_ok=True)
    path = recents_path()
    # Small single-line append is atomic; concurrent status changes never
    # corrupt each other (unlike a read-modify-write JSON list).
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{time.time_ns()}\t{pane}\t{status}\n")
    _maybe_trim(path)


def _maybe_trim(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return
    if text.count("\n") <= TRIM_AT:
        return
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(trim_text(text, KEEP_LINES))
    os.replace(tmp, path)


def load_order() -> list[str]:
    try:
        with open(recents_path(), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    return newest_unique(parse_recents(text))


def load_cursor() -> str | None:
    """Last-focused pane for the rotation (None if unset)."""
    try:
        with open(cursor_path(), encoding="utf-8") as fh:
            val = fh.read().strip()
    except OSError:
        return None
    return val or None


def save_cursor(pane: str) -> None:
    directory = state_dir()
    os.makedirs(directory, exist_ok=True)
    tmp = cursor_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(pane + "\n")
    os.replace(tmp, cursor_path())


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_record() -> int:
    raw = os.environ.get("HERDR_PLUGIN_EVENT_JSON")
    if not raw:
        return 0
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    pane, status = extract_event(obj)
    if not pane or status not in ATTENTION_STATES:
        return 0
    append_recent(pane, status)
    return 0


def cmd_focus() -> int:
    order = load_order()
    if not order:
        return 0
    target = next_in_cycle(order, live_status_map(), load_cursor())
    if target:
        focus_pane(target)
        save_cursor(target)
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "record":
        return cmd_record()
    if cmd == "focus":
        return cmd_focus()
    sys.stderr.write("usage: attention.py <record|focus>\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
