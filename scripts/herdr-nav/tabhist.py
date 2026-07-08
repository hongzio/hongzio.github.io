#!/usr/bin/env python3
"""herdr tab-history plugin.

Browser-style back/forward navigation over the tabs you visit. Every tab focus
is captured event-driven via herdr's `tab.focused` plugin event (no daemon, no
polling) and appended to a history list with a cursor. `prefix+ctrl+o` steps the
cursor back, `prefix+ctrl+i` steps it forward, focusing that tab.

Subcommands:
  record    record a tab focus into the history (run from the [[events]] hook)
  back      move the cursor to the previous live tab and focus it
  forward   move the cursor to the next live tab and focus it

History model — a list `entries` plus an integer `cursor` (index of the current
tab), exactly like a browser:

  * A new focus that differs from `entries[cursor]` TRUNCATES everything after
    the cursor and appends the tab (so A-B(*)-C then focus D => A-B-D(*)).
  * A focus equal to `entries[cursor]` is a no-op. This is what makes back/
    forward navigation itself NOT get recorded: the action moves the cursor and
    focuses the tab, and the resulting `tab.focused` echo lands on the tab the
    cursor already points at, so record does nothing. No marker files needed.
  * back/forward skip over tabs that no longer exist (checked against
    `herdr tab list`), landing on the nearest still-live tab.

The list/cursor helpers are pure (no I/O) so they can be unit-tested; the herdr
CLI, the state file, and the config file are the only external dependencies and
are reached through thin wrappers.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

DEFAULT_MAX = 100   # history entries kept (oldest dropped past this)
MIN_MAX = 2         # a 1-entry history has nothing to navigate to

HOME = os.path.expanduser("~")

CONFIG_TEMPLATE = (
    "# herdr nav — tab-history config.\n"
    "\n"
    "[tab-history]\n"
    "# max = how many recently-visited tabs to remember for back/forward.\n"
    "max = {max}\n"
)


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------


def state_dir() -> str:
    """Per-plugin state dir (herdr sets HERDR_PLUGIN_STATE_DIR); fall back sanely."""
    d = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if not d:
        d = os.path.join(HOME, ".local", "state", "herdr", "plugins", "nav")
    return d


def state_path() -> str:
    return os.path.join(state_dir(), "tab-history.json")


def config_dir() -> str:
    """Per-plugin config dir (herdr sets HERDR_PLUGIN_CONFIG_DIR); fall back sanely.

    Using herdr's provided dir means the config follows a custom config location
    (herdr's HERDR_CONFIG_PATH) instead of assuming ~/.config/herdr.
    """
    d = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if not d:
        d = os.path.join(HOME, ".config", "herdr", "plugins", "config", "nav")
    return d


def config_path() -> str:
    return os.path.join(config_dir(), "config.toml")


# ---------------------------------------------------------------------------
# pure helpers (no I/O)
# ---------------------------------------------------------------------------


def parse_max(text: str, default: int = DEFAULT_MAX) -> int:
    """Parse `max = N` from the config text. Tolerant of comments/junk.

    Returns `default` when absent/unparsable; clamps to at least MIN_MAX.
    """
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        if key.strip() != "max":
            continue
        val = val.strip().strip('"').strip("'").strip()
        if val.isdigit():
            return max(MIN_MAX, int(val))
    return default


def extract_tab(obj: object) -> str | None:
    """tab_id from a `tab.focused` event payload, or None if it does not match.

    Payload shape (confirmed): {"event": "tab_focused",
      "data": {"type": "tab_focused", "tab_id": "w1:t1",
               "previous_tab_id": "w1:t2", ...}}
    """
    data = obj.get("data") if isinstance(obj, dict) else None
    if not isinstance(data, dict):
        return None
    tab = data.get("tab_id")
    return tab if isinstance(tab, str) and tab else None


def clamp_cursor(cursor: int, n: int) -> int:
    """Clamp cursor into [-1, n-1] (-1 means 'empty history')."""
    if n <= 0:
        return -1
    if cursor < 0:
        return -1
    if cursor > n - 1:
        return n - 1
    return cursor


def record_focus(
    entries: list[str], cursor: int, tab_id: str, limit: int
) -> tuple[list[str], int]:
    """Apply a tab focus to (entries, cursor). Pure; returns the new state.

    No-op when the tab is already the current one (this absorbs the echo of a
    back/forward move). Otherwise truncate after the cursor, append, and trim
    the oldest entries past `limit`.
    """
    n = len(entries)
    if 0 <= cursor < n and entries[cursor] == tab_id:
        return entries, cursor
    cursor = clamp_cursor(cursor, n)
    new = entries[: cursor + 1] + [tab_id]
    if len(new) > limit:
        new = new[len(new) - limit :]
    return new, len(new) - 1


def step_back(entries: list[str], cursor: int, live: set[str]) -> int | None:
    """Nearest index left of the cursor whose tab still exists, or None."""
    i = cursor - 1
    while i >= 0:
        if entries[i] in live:
            return i
        i -= 1
    return None


def step_forward(entries: list[str], cursor: int, live: set[str]) -> int | None:
    """Nearest index right of the cursor whose tab still exists, or None."""
    i = cursor + 1
    n = len(entries)
    while i < n:
        if entries[i] in live:
            return i
        i += 1
    return None


# ---------------------------------------------------------------------------
# config I/O
# ---------------------------------------------------------------------------


def read_max() -> int:
    try:
        with open(config_path(), encoding="utf-8") as fh:
            return parse_max(fh.read())
    except OSError:
        return DEFAULT_MAX


def ensure_config() -> None:
    """Write a default config file the first time so the user can discover it."""
    path = config_path()
    if os.path.exists(path):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(CONFIG_TEMPLATE.format(max=DEFAULT_MAX))
        os.replace(tmp, path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# state I/O
# ---------------------------------------------------------------------------


def load_state() -> tuple[list[str], int]:
    """(entries, cursor) from the state file; ([], -1) on missing/corrupt."""
    try:
        with open(state_path(), encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return [], -1
    if not isinstance(obj, dict):
        return [], -1
    entries = obj.get("entries")
    cursor = obj.get("cursor")
    if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
        return [], -1
    if not isinstance(cursor, int):
        return [], -1
    return entries, clamp_cursor(cursor, len(entries))


def save_state(entries: list[str], cursor: int) -> None:
    directory = state_dir()
    os.makedirs(directory, exist_ok=True)
    path = state_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"entries": entries, "cursor": cursor}, fh)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# herdr CLI wrappers
# ---------------------------------------------------------------------------


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def live_tab_set() -> set[str]:
    """Set of tab_ids for every live tab (empty on any failure)."""
    try:
        proc = subprocess.run(
            [herdr_bin(), "tab", "list"], capture_output=True, text=True
        )
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for tab in data.get("result", {}).get("tabs", []):
        tid = tab.get("tab_id")
        if tid:
            out.add(tid)
    return out


def focus_tab(tab_id: str) -> bool:
    try:
        proc = subprocess.run(
            [herdr_bin(), "tab", "focus", tab_id], capture_output=True, text=True
        )
        return proc.returncode == 0
    except OSError:
        return False


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_record() -> int:
    ensure_config()
    raw = os.environ.get("HERDR_PLUGIN_EVENT_JSON")
    if not raw:
        return 0
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    tab_id = extract_tab(obj)
    if not tab_id:
        return 0
    entries, cursor = load_state()
    new_entries, new_cursor = record_focus(entries, cursor, tab_id, read_max())
    if new_entries != entries or new_cursor != cursor:
        save_state(new_entries, new_cursor)
    return 0


def _navigate(step) -> int:
    """Shared back/forward: move the cursor via `step`, persist, focus the tab.

    Persist BEFORE focusing so the resulting `tab.focused` echo lands on the tab
    the cursor now points at and record no-ops (the move isn't re-recorded).
    """
    entries, cursor = load_state()
    if not entries:
        return 0
    target = step(entries, cursor, live_tab_set())
    if target is None:
        return 0
    save_state(entries, target)
    focus_tab(entries[target])
    return 0


def cmd_back() -> int:
    return _navigate(step_back)


def cmd_forward() -> int:
    return _navigate(step_forward)


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "record":
        return cmd_record()
    if cmd == "back":
        return cmd_back()
    if cmd == "forward":
        return cmd_forward()
    sys.stderr.write("usage: tabhist.py <record|back|forward>\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
