#!/usr/bin/env python3
"""herdr queued-questions plugin.

Keeps a per-agent-session queue of pending questions. prefix+u captures the
draft currently sitting in the focused agent's composer (input box) into the
queue — even mid-turn while the agent is working — clears the composer, and
opens a popup listing the queue. From the popup: enter feeds the selected
question back into the composer (without submitting), e edits it, d deletes
it, esc closes.

Queues are keyed by the agent's own session id (herdr's agent_session.value,
e.g. the Claude session UUID), so a queue survives herdr server restarts and
`claude --resume`: the resumed agent reports the same session id and picks its
queue back up.

subcommands:
  open   capture the focused agent's draft, then open the popup (the action)
  ui     the popup itself (runs inside the plugin pane)

Runs under the system /usr/bin/python3 (3.9): stdlib only, no 3.10+ syntax at
runtime (annotations are fine, they are never evaluated).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unicodedata
from typing import NamedTuple

# ---------------------------------------------------------------------------
# composer (prompt box) scraping
# ---------------------------------------------------------------------------

# Claude Code renders the composer between two full-width ─ rules; the draft's
# first row is "❯ text" (a no-break space after ❯ while the agent is working)
# and every further row — soft wrap and hard newline alike, they are
# indistinguishable in the rendered buffer — is indented two spaces.

PROMPT_GLYPH = "❯"
MIN_RULE_LEN = 8


class PromptBox(NamedTuple):
    text: str      # the draft, rows joined with single spaces
    raw_len: int   # visible draft characters across all rows
    rows: int      # visual rows the draft occupies


def _is_rule(line: str) -> bool:
    s = line.strip()
    return len(s) >= MIN_RULE_LEN and set(s) == {"─"}


def parse_prompt_box(snapshot: str) -> "PromptBox | None":
    """The composer draft in a detection-buffer snapshot, or None if the
    bottom of the screen is not showing a composer (menu, dialog, no box)."""
    lines = snapshot.splitlines()
    rule_idx = [i for i, l in enumerate(lines) if _is_rule(l)]
    if len(rule_idx) < 2:
        return None
    body = lines[rule_idx[-2] + 1:rule_idx[-1]]
    body = [l for l in body if l.strip()]
    if not body or not body[0].lstrip().startswith(PROMPT_GLYPH):
        return None
    first = body[0].lstrip()[len(PROMPT_GLYPH):].replace("\xa0", " ").strip()
    rest = [l.replace("\xa0", " ").strip() for l in body[1:]]
    parts = [p for p in [first, *rest] if p]
    text = " ".join(parts)
    return PromptBox(text=text, raw_len=sum(len(p) for p in parts), rows=len(body))


def clear_count(box: PromptBox) -> int:
    """Backspaces to send to empty the composer. Deliberately overshoots
    (row boundaries hide a consumed space or newline each, and extra
    backspaces on an empty composer are a no-op)."""
    if not box.text:
        return 0
    return box.raw_len + box.rows + 8


# ---------------------------------------------------------------------------
# queue store
# ---------------------------------------------------------------------------


def state_dir() -> str:
    d = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if d:
        return d
    return os.path.expanduser("~/.local/state/herdr/plugins/queue")


def sanitize_session(session_id: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in session_id) or "unknown"


def queue_path(session_id: str) -> str:
    return os.path.join(state_dir(), "queue-%s.json" % sanitize_session(session_id))


def load_queue(session_id: str) -> list:
    try:
        with open(queue_path(session_id), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict) and isinstance(i.get("text"), str)]


def save_queue(session_id: str, items: list) -> None:
    path = queue_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "items": items}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def add_question(items: list, text: str) -> list:
    text = text.strip()
    if not text:
        return items
    next_id = max((i.get("id", 0) for i in items), default=0) + 1
    return items + [{"id": next_id, "text": text, "ts": time.time()}]


# ---------------------------------------------------------------------------
# popup rendering / editing helpers
# ---------------------------------------------------------------------------


def disp_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def fit_width(s: str, maxw: int) -> str:
    if maxw <= 0:
        return ""
    if disp_width(s) <= maxw:
        return s
    out, used = "", 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        if used + cw > maxw - 1:
            return out + "…"
        out += c
        used += cw
    return out


def item_label(text: str, width: int) -> str:
    return fit_width(text.replace("\n", "⏎"), width)


def edit_key(text: str, cur: int, ch) -> tuple:
    """One keypress against a single-line edit buffer.

    Returns (text, cursor, done) with done in (None, "commit", "cancel").
    """
    import curses
    if ch in ("\n", "\r", curses.KEY_ENTER):
        return text, cur, "commit"
    if ch in (27, "\x1b", 3, "\x03"):
        return text, cur, "cancel"
    if ch in (curses.KEY_LEFT, "\x02"):
        return text, max(0, cur - 1), None
    if ch in (curses.KEY_RIGHT, "\x06"):
        return text, min(len(text), cur + 1), None
    if ch in (curses.KEY_HOME, "\x01"):
        return text, 0, None
    if ch in (curses.KEY_END, "\x05"):
        return text, len(text), None
    if ch in (curses.KEY_BACKSPACE, "\x7f", "\b", "\x08"):
        if cur > 0:
            return text[:cur - 1] + text[cur:], cur - 1, None
        return text, cur, None
    if ch == curses.KEY_DC:
        return text[:cur] + text[cur + 1:], cur, None
    if isinstance(ch, str) and ch.isprintable():
        return text[:cur] + ch + text[cur:], cur + len(ch), None
    return text, cur, None


# ---------------------------------------------------------------------------
# herdr CLI wrappers
# ---------------------------------------------------------------------------


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def herdr(*args: str) -> dict:
    out = herdr_text(*args)
    return json.loads(out) if out.strip() else {}


def herdr_text(*args: str) -> str:
    """Raw stdout — for commands like `agent read` that print plain text."""
    proc = subprocess.run([herdr_bin(), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("herdr %s failed: %s" % (" ".join(args[:3]), proc.stderr.strip()))
    return proc.stdout


def context_pane() -> str:
    """focused_pane_id from HERDR_PLUGIN_CONTEXT_JSON (the pane the user was
    looking at when the keybinding fired), else the caller pane."""
    try:
        ctx = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "")
    except json.JSONDecodeError:
        ctx = None
    if isinstance(ctx, dict) and isinstance(ctx.get("focused_pane_id"), str):
        return ctx["focused_pane_id"]
    return os.environ.get("HERDR_PANE_ID", "")


def agent_on(pane_id: str) -> dict:
    """The agent occupying pane_id, or {} when the pane holds no agent."""
    try:
        data = herdr("agent", "get", pane_id)
    except (RuntimeError, json.JSONDecodeError):
        return {}
    agent = data.get("result", {}).get("agent")
    return agent if isinstance(agent, dict) else {}


def send_backspaces(pane_id: str, count: int, batch: int = 50) -> None:
    while count > 0:
        n = min(count, batch)
        herdr("agent", "send-keys", pane_id, *(["backspace"] * n))
        count -= n


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------

POPUP_WIDTH = "62%"
POPUP_HEIGHT = 18


def cmd_open() -> int:
    pane = context_pane()
    agent = agent_on(pane) if pane else {}
    session = (agent.get("agent_session") or {}).get("value") or ""
    error = ""
    if not agent:
        error = "no agent in the focused pane"
    elif not session:
        error = "agent session id not known yet"
    elif agent.get("agent") == "claude":
        # capture the composer draft, then clear it (works mid-turn too:
        # backspaces never interrupt a working agent, unlike esc)
        try:
            snap = herdr_text("agent", "read", pane, "--source", "detection", "--lines", "40")
            box = parse_prompt_box(snap)
            if box and box.text:
                save_queue(session, add_question(load_queue(session), box.text))
                send_backspaces(pane, clear_count(box))
        except RuntimeError as exc:
            error = "capture failed: %s" % exc
    herdr("plugin", "pane", "open", "--plugin", "queue", "--entrypoint", "queue-picker",
          "--placement", "popup", "--width", POPUP_WIDTH, "--height", str(POPUP_HEIGHT),
          "--focus",
          "--env", "QQ_TARGET_PANE=%s" % pane,
          "--env", "QQ_SESSION=%s" % session,
          "--env", "QQ_ERROR=%s" % error)
    return 0


def cmd_ui() -> int:
    import curses
    session = os.environ.get("QQ_SESSION", "")
    target = os.environ.get("QQ_TARGET_PANE", "")
    error = os.environ.get("QQ_ERROR", "")
    curses.wrapper(_popup_loop, session, target, error)
    return 0


def _popup_loop(stdscr, session: str, target: str, error: str) -> None:
    import curses
    try:
        curses.set_escdelay(25)
    except (AttributeError, curses.error):
        pass
    curses.curs_set(0)
    stdscr.keypad(True)
    items = load_queue(session) if session else []
    sel = 0
    status = error
    editing = None  # (buffer, cursor) while editing the selected item

    while True:
        sel = max(0, min(sel, len(items) - 1))
        height, width = stdscr.getmaxyx()
        stdscr.erase()
        title = "Queued questions — %d" % len(items)
        hint = "enter: put into composer   e: edit   d: delete   esc: close"
        _put(stdscr, 0, title, curses.A_BOLD)
        list_rows = max(1, height - 4)
        top = max(0, sel - list_rows + 1)
        for row, item in enumerate(items[top:top + list_rows]):
            i = top + row
            marker = "▌ " if i == sel else "  "
            attr = curses.A_REVERSE if i == sel else curses.A_NORMAL
            _put(stdscr, 2 + row, marker + item_label(item["text"], width - 4), attr)
        if not items and not status:
            _put(stdscr, 2, "  (empty)", curses.A_DIM)
        if editing is not None:
            buf, cur = editing
            _put(stdscr, height - 2, "edit: " + fit_width(buf, width - 8))
            _put(stdscr, height - 1, "enter: save   esc: cancel", curses.A_DIM)
            curses.curs_set(1)
            stdscr.move(height - 2, min(width - 1, disp_width("edit: " + buf[:cur])))
        else:
            curses.curs_set(0)
            _put(stdscr, height - 1, status or hint, curses.A_DIM)
        stdscr.refresh()

        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue

        if editing is not None:
            buf, cur, done = edit_key(editing[0], editing[1], ch)
            if done == "commit":
                if buf.strip():
                    items[sel]["text"] = buf.strip()
                    save_queue(session, items)
                editing = None
            elif done == "cancel":
                editing = None
            else:
                editing = (buf, cur)
            continue

        status = ""
        if ch in (27, "\x1b", 3, "\x03", "q"):
            return
        if ch in ("\n", "\r", curses.KEY_ENTER) and items:
            try:
                herdr("pane", "send-text", target, items[sel]["text"])
            except RuntimeError as exc:
                status = "send failed: %s" % exc
                continue
            del items[sel]
            save_queue(session, items)
            return
        if ch in (curses.KEY_UP, "\x10", "k"):
            sel -= 1
        elif ch in (curses.KEY_DOWN, "\x0e", "j"):
            sel += 1
        elif ch in ("d", "x", curses.KEY_DC) and items:
            del items[sel]
            save_queue(session, items)
        elif ch == "e" and items:
            editing = (items[sel]["text"], len(items[sel]["text"]))


def _put(stdscr, y: int, s: str, attr=0) -> None:
    import curses
    height, width = stdscr.getmaxyx()
    if 0 <= y < height:
        try:
            stdscr.addstr(y, 0, fit_width(s, width - 1), attr)
        except curses.error:
            pass


USAGE = "usage: questions.py {open|ui}"


def main(argv: list) -> int:
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 2
    if argv[1] == "open":
        return cmd_open()
    if argv[1] == "ui":
        return cmd_ui()
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
