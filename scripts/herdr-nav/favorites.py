#!/usr/bin/env python3
"""herdr favorites picker.

A curses overlay that pins herdr tabs to 9 slots (ctrl+1..9). The tab that was
focused when the overlay opened is passed in via the FAV_ACTIVE_TAB env var;
pressing enter on a slot stores that tab_id there. ctrl+1..9 (bound in the user
herdr.toml) read the same file and `herdr tab focus` the stored tab.

Subcommand:
  ui    run the overlay (used inside the plugin overlay pane)

The file parse/render helpers are pure (no I/O) so they can be unit-tested; the
`herdr` CLI and the favorites file are the only external dependencies and are
reached through thin wrappers.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unicodedata

HOME = os.path.expanduser("~")
SLOT_COUNT = 9

FILE_HEADER = (
    "# herdr nav — favorites pins (ctrl+1..9 focus these tabs).\n"
    "# Machine-managed state written by the prefix+ctrl+f overlay; values are\n"
    "# herdr tab_ids. Safe to delete; it is regenerated when you pin a tab.\n"
)


# ---------------------------------------------------------------------------
# favorites file (parse/render are pure; load/save do I/O)
# ---------------------------------------------------------------------------


def parse_favorites(text: str) -> dict[int, str]:
    """Parse `N = "tab_id"` lines into {slot: tab_id}. Tolerant of junk/comments.

    Only slots 1..SLOT_COUNT are kept; blanks and unparsable lines are ignored.
    """
    slots: dict[int, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key.isdigit():
            continue
        slot = int(key)
        if not 1 <= slot <= SLOT_COUNT:
            continue
        tab = val.strip().strip('"').strip("'").strip()
        if tab:
            slots[slot] = tab
    return slots


def render_favorites(slots: dict[int, str]) -> str:
    """Render all SLOT_COUNT slots to file text (empty slots become `N = ""`)."""
    lines = [FILE_HEADER.rstrip("\n")]
    for slot in range(1, SLOT_COUNT + 1):
        tab = slots.get(slot, "") or ""
        lines.append(f'{slot} = "{tab}"')
    return "\n".join(lines) + "\n"


def state_dir() -> str:
    """Per-plugin state dir (herdr sets HERDR_PLUGIN_STATE_DIR); fall back sanely."""
    d = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if not d:
        d = os.path.join(HOME, ".local", "state", "herdr", "plugins", "nav")
    return d


def fav_path() -> str:
    return os.path.join(state_dir(), "favorites.toml")


def load_favorites() -> dict[int, str]:
    try:
        with open(fav_path(), encoding="utf-8") as fh:
            return parse_favorites(fh.read())
    except OSError:
        return {}


def save_favorites(slots: dict[int, str]) -> None:
    path = fav_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(render_favorites(slots))
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# herdr CLI wrappers
# ---------------------------------------------------------------------------


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def herdr(*args: str) -> dict:
    try:
        proc = subprocess.run([herdr_bin(), *args], capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"herdr binary not found: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)} failed: {proc.stderr.strip()}")
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def tab_directory() -> dict[str, dict]:
    """tab_id -> {number, label, workspace_id} for every live tab."""
    try:
        data = herdr("tab", "list")
    except (RuntimeError, json.JSONDecodeError):
        return {}
    result = {}
    for tab in data.get("result", {}).get("tabs", []):
        tid = tab.get("tab_id")
        if tid:
            result[tid] = {
                "number": tab.get("number"),
                "label": tab.get("label") or "",
                "workspace_id": tab.get("workspace_id") or "",
            }
    return result


# ---------------------------------------------------------------------------
# display (pure)
# ---------------------------------------------------------------------------


def slot_line(slot: int, tab_id: str, tabs: dict[str, dict], active_tab: str) -> str:
    """One row: 'N  <tab description>' with markers for missing / current tab."""
    if not tab_id:
        body = "—"
    else:
        meta = tabs.get(tab_id)
        if meta is None:
            body = f"{tab_id}  (missing)"
        else:
            num = meta["number"]
            label = meta["label"] or "(unnamed)"
            num_part = f"#{num} " if num is not None else ""
            body = f"{meta['workspace_id']} {num_part}{label}".strip()
        if tab_id == active_tab:
            body += "  ← current"
    return f"{slot}  {body}"


def _disp_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _fit_width(s: str, maxw: int) -> str:
    if maxw <= 0:
        return ""
    if _disp_width(s) <= maxw:
        return s
    out, used = "", 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        if used + cw > maxw - 1:
            return out + "…"
        out += c
        used += cw
    return out


# ---------------------------------------------------------------------------
# overlay
# ---------------------------------------------------------------------------


def _fail(msg: str) -> int:
    sys.stderr.write(msg + "\n")
    if sys.stdin.isatty():
        try:
            input("(enter to close) ")
        except (EOFError, KeyboardInterrupt):
            pass
    return 1


def cmd_ui() -> int:
    try:
        import curses  # noqa: F401
    except ImportError:
        return _fail("Python curses is unavailable; cannot draw the favorites overlay.")
    import locale
    locale.setlocale(locale.LC_ALL, "")
    active_tab = (os.environ.get("FAV_ACTIVE_TAB") or "").strip()
    slots = load_favorites()
    tabs = tab_directory()
    curses.wrapper(_overlay_loop, slots, tabs, active_tab)
    return 0


def _overlay_loop(stdscr, slots, tabs, active_tab):
    import curses
    try:
        curses.set_escdelay(25)
    except (AttributeError, curses.error):
        pass
    curses.curs_set(0)
    stdscr.keypad(True)
    sel = 0
    active_meta = tabs.get(active_tab)
    if active_meta:
        num = active_meta["number"]
        num_part = f"#{num} " if num is not None else ""
        active_desc = f"{active_meta['workspace_id']} {num_part}{active_meta['label']}".strip()
    else:
        active_desc = active_tab or "(none)"

    while True:
        height, width = stdscr.getmaxyx()
        stdscr.erase()
        title = "Favorites — pin a tab to a slot"
        current = f"current tab: {active_desc}"
        hint = "↑/↓ move   enter: pin current tab   x/del: clear   esc: close"
        try:
            stdscr.addstr(0, 0, _fit_width(title, width - 1), curses.A_BOLD)
            stdscr.addstr(1, 0, _fit_width(current, width - 1), curses.A_DIM)
        except curses.error:
            pass
        for i in range(SLOT_COUNT):
            slot = i + 1
            line = slot_line(slot, slots.get(slot, ""), tabs, active_tab)
            marker = "▌ " if i == sel else "  "
            attr = curses.A_REVERSE if i == sel else curses.A_NORMAL
            try:
                stdscr.addstr(3 + i, 0, _fit_width(marker + line, width - 1), attr)
            except curses.error:
                pass
        try:
            stdscr.addstr(3 + SLOT_COUNT + 1, 0, _fit_width(hint, width - 1), curses.A_DIM)
        except curses.error:
            pass
        stdscr.refresh()

        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue
        if ch in (27, "\x1b", 3, "\x03"):                    # esc / ctrl-c -> close
            return
        if ch in ("\n", "\r", curses.KEY_ENTER):             # enter -> pin & close
            if active_tab:
                slots[sel + 1] = active_tab
                save_favorites(slots)
            return
        if ch in (curses.KEY_UP, "\x10", "k"):               # up / ctrl-p / k
            sel = (sel - 1) % SLOT_COUNT
        elif ch in (curses.KEY_DOWN, "\x0e", "j"):           # down / ctrl-n / j
            sel = (sel + 1) % SLOT_COUNT
        elif ch in (curses.KEY_DC, curses.KEY_BACKSPACE,     # delete / backspace / x -> clear
                    "\x7f", "\b", "\x08", "x"):
            if slots.pop(sel + 1, None) is not None:
                save_favorites(slots)
        elif isinstance(ch, str) and ch.isdigit() and ch != "0":
            sel = int(ch) - 1                                # jump to slot by number


def cmd_focus(slot_arg: str) -> int:
    """Focus the tab pinned to slot N. No-op (exit 0) if the slot is empty or
    the tab is gone — a missing favorite should never surface an error."""
    if not slot_arg.isdigit():
        return 2
    slot = int(slot_arg)
    if not 1 <= slot <= SLOT_COUNT:
        return 2
    tab_id = load_favorites().get(slot, "")
    if not tab_id:
        return 0
    try:
        herdr("tab", "focus", tab_id)
    except RuntimeError:
        return 0
    return 0


USAGE = "usage: favorites.py {ui|focus <slot>}"


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "ui":
        return cmd_ui()
    if len(argv) >= 3 and argv[1] == "focus":
        return cmd_focus(argv[2])
    sys.stderr.write(USAGE + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
