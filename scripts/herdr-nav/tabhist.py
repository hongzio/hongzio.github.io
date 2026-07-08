#!/usr/bin/env python3
"""herdr tab-history plugin.

Browser-style back/forward navigation over the tabs you visit. Every tab focus
is captured event-driven via herdr's `tab.focused` plugin event (no daemon, no
polling). A focus is only committed to history once the tab has held focus for
at least `min_dwell_seconds` (default 5) — tabs you quickly pass through are
dropped, so back/forward isn't polluted by fly-bys. `prefix+ctrl+o` steps the
cursor back, `prefix+ctrl+i` steps it forward, focusing that tab.

Subcommands:
  record    stage a tab focus, committing the previous one if it was held long
            enough (run from the [[events]] hook)
  back      move the cursor to the previous live tab and focus it
  forward   move the cursor to the next live tab and focus it
  toggle    bounce between the two newest history entries (top <-> second),
            a "last tab" style flip

Dwell gate — the event model has no timer, so we can't know at focus time
whether a tab will be held. Instead each focus is STAGED as `pending` (tab +
timestamp); the NEXT focus (or a back/forward press) resolves it: if the gap is
>= min_dwell_seconds the staged tab is committed to history, otherwise it is
dropped. A tab thus enters history when you leave it (or navigate away) having
stayed long enough, not the instant you land on it. `min_dwell_seconds = 0`
disables the gate (record every focus immediately, the pre-dwell behaviour).

History model — a committed list `entries` plus an integer `cursor` (index of
the current anchor), exactly like a browser:

  * A committed focus that differs from `entries[cursor]` TRUNCATES everything
    after the cursor and appends the tab (so A-B(*)-C then focus D => A-B-D(*)).
  * A focus equal to `entries[cursor]` is a no-op. This is what makes back/
    forward navigation itself NOT get recorded: the action moves the cursor and
    focuses the tab, and the resulting `tab.focused` echo lands on the tab the
    cursor already points at, so record does nothing. No marker files needed.
  * If you press back/forward while sitting on an uncommitted fly-by (a tab not
    held long enough), the first press snaps back to the anchor rather than
    stepping — the fly-by is transparent to navigation.
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
import time

DEFAULT_MAX = 100   # history entries kept (oldest dropped past this)
MIN_MAX = 2         # a 1-entry history has nothing to navigate to

DEFAULT_MIN_DWELL = 5   # seconds a tab must hold focus before it is recorded

HOME = os.path.expanduser("~")

CONFIG_TEMPLATE = (
    "# herdr nav — tab-history config.\n"
    "\n"
    "[tab-history]\n"
    "# max = how many recently-visited tabs to remember for back/forward.\n"
    "max = {max}\n"
    "\n"
    "# min_dwell_seconds = how long (seconds) a tab must hold focus before it is\n"
    "# recorded into history. Tabs you pass through faster than this are ignored,\n"
    "# so quickly tabbing past a tab won't pollute back/forward. 0 disables the\n"
    "# gate (record every focus immediately).\n"
    "min_dwell_seconds = {min_dwell}\n"
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


def parse_min_dwell(text: str, default: float = DEFAULT_MIN_DWELL) -> float:
    """Parse `min_dwell_seconds = N` (seconds) from the config text.

    Returns `default` when absent/unparsable; 0 is allowed (disables the gate);
    negatives fall back to `default`.
    """
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        if key.strip() != "min_dwell_seconds":
            continue
        val = val.strip().strip('"').strip("'").strip()
        try:
            seconds = float(val)
        except ValueError:
            return default
        return seconds if seconds >= 0 else default
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


def settle(
    entries: list[str],
    cursor: int,
    pending: tuple[str, float] | None,
    now: float,
    threshold: float,
    limit: int,
) -> tuple[list[str], int, bool]:
    """Resolve a staged `pending` focus against the dwell threshold. Pure.

    `pending` is (tab_id, focused_at) or None. Returns (entries, cursor,
    off_anchor):
      * held >= threshold and not already the anchor -> committed to history.
      * held  < threshold                            -> dropped as a fly-by.
      * equal to the current anchor                  -> no-op (back/forward echo).

    `off_anchor` is True only when a fly-by was dropped while it differs from the
    anchor — i.e. the user is physically sitting on an uncommitted tab, so a
    back/forward press should snap back to the anchor instead of stepping.
    """
    if pending is None:
        return entries, cursor, False
    tab, at = pending
    anchor = entries[cursor] if 0 <= cursor < len(entries) else None
    if tab == anchor:
        return entries, cursor, False
    if now - at >= threshold:
        entries, cursor = record_focus(entries, cursor, tab, limit)
        return entries, cursor, False
    return entries, cursor, True


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


def step_toggle(entries: list[str], cursor: int, live: set[str]) -> int | None:
    """Index for the top<->second toggle (a two-way "last tab" bounce). Pure.

    From the newest entry (cursor at the last index) go to the second newest;
    from anywhere else go to the newest. This makes the first press from deep in
    the history return to the top, and subsequent presses flip between the top
    two. Unlike back/forward it does NOT skip closed tabs: the target is exactly
    one of the top two, so a dead target yields None (no-op) rather than sliding
    onto a third tab and breaking the two-way semantic.
    """
    n = len(entries)
    if n == 0:
        return None
    last = n - 1
    target = last - 1 if cursor == last else last
    if target < 0:
        return None
    return target if entries[target] in live else None


# ---------------------------------------------------------------------------
# config I/O
# ---------------------------------------------------------------------------


def read_max() -> int:
    try:
        with open(config_path(), encoding="utf-8") as fh:
            return parse_max(fh.read())
    except OSError:
        return DEFAULT_MAX


def read_min_dwell() -> float:
    try:
        with open(config_path(), encoding="utf-8") as fh:
            return parse_min_dwell(fh.read())
    except OSError:
        return DEFAULT_MIN_DWELL


def ensure_config() -> None:
    """Write a default config file the first time so the user can discover it."""
    path = config_path()
    if os.path.exists(path):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(CONFIG_TEMPLATE.format(max=DEFAULT_MAX, min_dwell=DEFAULT_MIN_DWELL))
        os.replace(tmp, path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# state I/O
# ---------------------------------------------------------------------------


def _parse_pending(raw: object) -> tuple[str, float] | None:
    """(tab_id, focused_at) from the persisted `pending` blob, or None."""
    if not isinstance(raw, dict):
        return None
    tab = raw.get("tab")
    at = raw.get("at")
    if isinstance(tab, str) and tab and isinstance(at, (int, float)):
        return tab, float(at)
    return None


def load_state() -> tuple[list[str], int, tuple[str, float] | None]:
    """(entries, cursor, pending) from the state file; ([], -1, None) on missing/corrupt.

    `pending` is the staged-but-uncommitted current focus (tab_id, focused_at),
    or None. Pre-dwell state files have no `pending` key and load as None.
    """
    try:
        with open(state_path(), encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return [], -1, None
    if not isinstance(obj, dict):
        return [], -1, None
    entries = obj.get("entries")
    cursor = obj.get("cursor")
    if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
        return [], -1, None
    if not isinstance(cursor, int):
        return [], -1, None
    return entries, clamp_cursor(cursor, len(entries)), _parse_pending(obj.get("pending"))


def save_state(
    entries: list[str], cursor: int, pending: tuple[str, float] | None = None
) -> None:
    directory = state_dir()
    os.makedirs(directory, exist_ok=True)
    path = state_path()
    tmp = path + ".tmp"
    obj: dict[str, object] = {"entries": entries, "cursor": cursor}
    if pending is not None:
        obj["pending"] = {"tab": pending[0], "at": pending[1]}
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
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
    entries, cursor, pending = load_state()
    limit = read_max()
    threshold = read_min_dwell()
    now = time.time()
    if threshold <= 0:
        # gate disabled: record immediately, exactly like the pre-dwell behaviour.
        new_entries, new_cursor = record_focus(entries, cursor, tab_id, limit)
        save_state(new_entries, new_cursor, None)
        return 0
    # Commit the previously-staged tab if it was held >= threshold (its dwell is
    # now - its focus time), then stage this focus as the new pending.
    new_entries, new_cursor, _ = settle(entries, cursor, pending, now, threshold, limit)
    save_state(new_entries, new_cursor, (tab_id, now))
    return 0


def _navigate(step, now: float) -> int:
    """Shared back/forward: settle the current focus, move the cursor, focus.

    Persist BEFORE focusing so the resulting `tab.focused` echo lands on the tab
    the cursor now points at and record no-ops (the move isn't re-recorded).
    """
    entries, cursor, pending = load_state()
    threshold = read_min_dwell()
    limit = read_max()
    entries, cursor, off_anchor = settle(entries, cursor, pending, now, threshold, limit)

    target = None
    if off_anchor:
        # Sitting on an uncommitted fly-by: snap back to the anchor first.
        if 0 <= cursor < len(entries):
            target = cursor
    elif entries:
        target = step(entries, cursor, live_tab_set())

    if target is None:
        # Nowhere to go, but settle may have committed a tab — persist that and
        # clear the now-resolved pending.
        save_state(entries, cursor, None)
        return 0

    save_state(entries, target, (entries[target], now))
    focus_tab(entries[target])
    return 0


def cmd_back() -> int:
    return _navigate(step_back, time.time())


def cmd_forward() -> int:
    return _navigate(step_forward, time.time())


def cmd_toggle() -> int:
    return _navigate(step_toggle, time.time())


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "record":
        return cmd_record()
    if cmd == "back":
        return cmd_back()
    if cmd == "forward":
        return cmd_forward()
    if cmd == "toggle":
        return cmd_toggle()
    sys.stderr.write("usage: tabhist.py <record|back|forward|toggle>\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
