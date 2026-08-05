#!/usr/bin/env python3
"""herdr agents — things you can do to the agent you are looking at.

prefix+a opens a small popup listing this plugin's features; each one acts on
the agent that was focused when the key fired. Features live in MENU, so adding
one is an entry there plus its branch in _menu_loop — no new keybinding.

  fork  copy the pane's conversation into a brand new agent, opened as a new tab
        in the same workspace. Both sides keep their own transcript from the
        fork point on; the original is not touched.

Both fork-capable agents fork natively, so the transcript is never copied by hand:
  claude --resume <id> --fork-session   (resume, but write to a new session id)
  codex fork <id>                       (records forked_from_id in the new session)

Subcommands — every feature is one, named after its MENU id, so it can be run
from the popup, from an action, or by hand:
  menu-open     resolve the caller's agent pane and open the menu popup (action)
  menu-ui       the popup itself (runs inside the plugin pane)
  fork [PANE]   fork the conversation in PANE (default: the focused agent pane)

The fork is launched with `pane run`, not `herdr agent start`: that leaves it
with NO herdr agent name. Names must be unique among live agents, so a copy
cannot inherit the original's, and inventing one would be noise in the sidebar.

The pure helpers (target resolution, command building, validation, menu model)
do no I/O so they can be unit-tested; the `herdr` CLI is the only external
dependency and is reached through thin wrappers.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass

# Agent kinds that can fork themselves, and how to ask them to. The session id
# comes from herdr's agent_session; both CLIs take it as a positional UUID.
FORK_TEMPLATES = {
    "claude": "claude --resume {sid} --fork-session",
    "codex": "codex fork {sid}",
}


# ---------------------------------------------------------------------------
# menu model (pure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    id: str
    key: str     # single-key accelerator
    title: str
    desc: str


# Accelerators must avoid q/j/k — the popup handles those itself (quit, nav).
MENU = [
    Item("fork", "f", "fork", "copy this conversation into a new tab"),
]


def item_line(item: Item, title_width: int = 0) -> str:
    return f"{item.key}  {item.title.ljust(title_width or len(item.title))}  {item.desc}"


def menu_lines(items: list[Item]) -> list[str]:
    """The item rows, descriptions aligned to the widest title in the menu."""
    width = max((len(i.title) for i in items), default=0)
    return [item_line(i, width) for i in items]


def accel_index(items: list[Item], ch) -> int:
    """Index of the item whose accelerator is `ch`, else -1."""
    if not isinstance(ch, str) or len(ch) != 1:
        return -1
    for i, item in enumerate(items):
        if item.key == ch.lower():
            return i
    return -1


# ---------------------------------------------------------------------------
# source agent (pure)
# ---------------------------------------------------------------------------


def context_pane(context_json: str) -> str:
    """focused_pane_id from HERDR_PLUGIN_CONTEXT_JSON, herdr's invocation context.

    This is the pane the user is actually looking at when the keybinding fires,
    which is what "fork this agent" means; HERDR_PANE_ID is only the pane the
    command happens to run in. Empty when the var is absent or unparsable.
    """
    try:
        ctx = json.loads(context_json or "")
    except json.JSONDecodeError:
        return ""
    pid = ctx.get("focused_pane_id") if isinstance(ctx, dict) else None
    return pid if isinstance(pid, str) else ""


def resolve_target_pane(agents: list, caller_pane: str = "") -> str:
    """The agent pane a fork should copy, given an `agent list` snapshot.

    Prefers the pane the caller named (the focused pane, else the pane the
    command ran in) and otherwise falls back to whichever agent herdr reports as
    focused. A caller pane that holds no agent yields "" rather than silently
    forking somebody else's conversation.
    """
    known = {a.get("pane_id") for a in agents if isinstance(a, dict)}
    if caller_pane:
        return caller_pane if caller_pane in known else ""
    for a in agents:
        if isinstance(a, dict) and a.get("focused"):
            return a.get("pane_id") or ""
    return ""


def find_agent(agents: list, pane_id: str) -> dict | None:
    if not pane_id:
        return None
    for a in agents:
        if isinstance(a, dict) and a.get("pane_id") == pane_id:
            return a
    return None


def session_id(agent: dict) -> str:
    """The agent's own session id, only when herdr resolved it as an id.

    herdr can also report a session as a transcript path (kind != "id"); neither
    fork CLI takes a path, so that counts as "not forkable yet" rather than
    something to guess at.
    """
    sess = agent.get("agent_session") or {}
    if not isinstance(sess, dict) or sess.get("kind") != "id":
        return ""
    return str(sess.get("value") or "").strip()


def fork_error(agent: dict | None) -> str:
    """Why this pane cannot be forked, or "" when it can."""
    if not agent:
        return "no agent in this pane"
    kind = str(agent.get("agent") or "")
    if kind not in FORK_TEMPLATES:
        return "fork supports %s only (this is %s)" % (
            "/".join(sorted(FORK_TEMPLATES)), kind or "not an agent")
    if not session_id(agent):
        return "%s has no session id yet — send it one message first" % kind
    if not agent.get("workspace_id"):
        return "cannot tell which workspace this pane is in"
    return ""


# What each menu item needs from the source agent. Features differ here — fork
# needs a session id from a fork-capable CLI, the next one may not — so the
# popup asks per item rather than gating the whole menu on one check.
ITEM_ERROR = {
    "fork": fork_error,
}


def item_error(item_id: str, agent: dict | None) -> str:
    """Why this item cannot run against this agent, or "" when it can."""
    if not agent:
        return "no agent in this pane"
    check = ITEM_ERROR.get(item_id)
    return check(agent) if check else ""


def fork_command(kind: str, sid: str) -> str:
    return FORK_TEMPLATES[kind].format(sid=shlex.quote(sid))


def fork_cwd(agent: dict) -> str:
    """Where to start the fork: where the agent itself runs, else the pane's cwd."""
    return str(agent.get("foreground_cwd") or agent.get("cwd") or "").strip()


def source_label(agent: dict | None, pane_id: str) -> str:
    """One-line description of what would be forked, for the popup header."""
    if not agent:
        return pane_id or "(none)"
    parts = [str(agent.get("pane_id") or pane_id), str(agent.get("agent") or "")]
    title = str(agent.get("terminal_title_stripped") or "").strip()
    if title:
        parts.append("· " + title)
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# herdr CLI wrappers
# ---------------------------------------------------------------------------


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def herdr(*args: str) -> dict:
    try:
        proc = subprocess.run([herdr_bin(), *args], capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeError("herdr binary not found: %s" % exc) from exc
    if proc.returncode != 0:
        raise RuntimeError("herdr %s failed: %s" % (" ".join(args), error_message(proc.stderr, proc.stdout)))
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def error_message(*streams: str) -> str:
    """The human-readable part of herdr's JSON error output ({"error": {...}}).

    Falls back to the first non-empty line so an unparsable failure still says
    something useful instead of a bare "failed".
    """
    for stream in streams:
        for line in (stream or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return line
            err = obj.get("error") if isinstance(obj, dict) else None
            if isinstance(err, dict):
                return str(err.get("message") or err.get("code") or line)
            if isinstance(err, str):
                return err
            return line
    return "failed"


def agent_list() -> list:
    try:
        return herdr("agent", "list").get("result", {}).get("agents", []) or []
    except RuntimeError:
        return []


def notify(title: str, body: str) -> None:
    """Best-effort toast. The fork worker is detached, so this is its only voice."""
    try:
        subprocess.run([herdr_bin(), "notification", "show", title, "--body", body],
                       capture_output=True, text=True)
    except OSError:
        pass


def run_when_ready(pane_id: str, command: str, attempts: int = 20) -> None:
    """`pane run` once the new tab's shell settles; retry briefly past the launch race."""
    last = "no attempt"
    for _ in range(attempts):
        try:
            herdr("pane", "run", pane_id, command)
            return
        except RuntimeError as exc:
            last = str(exc)
            time.sleep(0.1)
    raise RuntimeError("pane run failed after retries: %s" % last)


# ---------------------------------------------------------------------------
# source agent (I/O)
# ---------------------------------------------------------------------------


def caller_pane() -> str:
    return (context_pane(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "")
            or (os.environ.get("HERDR_PANE_ID") or "")).strip()


def resolve_source(pane_arg: str = "") -> "tuple[str, dict | None]":
    agents = agent_list()
    target = resolve_target_pane(agents, (pane_arg or caller_pane()).strip())
    return target, find_agent(agents, target)


# ---------------------------------------------------------------------------
# feature: fork
# ---------------------------------------------------------------------------


def do_fork(agent: dict) -> str:
    """Create the fork's tab, launch it, focus it. Returns the new tab id."""
    cmd = fork_command(str(agent["agent"]), session_id(agent))
    args = ["tab", "create", "--workspace", str(agent["workspace_id"]), "--no-focus"]
    cwd = fork_cwd(agent)
    if cwd:
        args += ["--cwd", cwd]
    result = herdr(*args).get("result", {})
    pane = (result.get("root_pane") or {}).get("pane_id")
    tab = (result.get("tab") or {}).get("tab_id")
    if not pane:
        raise RuntimeError("tab create returned no pane to launch into")
    run_when_ready(pane, cmd)
    if tab:
        herdr("tab", "focus", tab)
    return tab or ""


def cmd_fork(pane_arg: str = "") -> int:
    """Fork the conversation in the given (or focused) agent pane.

    Also the body of the detached worker the popup spawns, so failures are
    reported as a herdr notification and not only on stderr (which, for a
    keybinding, is just the plugin log).
    """
    try:
        _, agent = resolve_source(pane_arg)
        err = item_error("fork", agent)
        if err:
            return _fail("fork", err)
        do_fork(agent)
    except RuntimeError as exc:
        return _fail("fork", str(exc))
    return 0


def _fail(feature: str, msg: str) -> int:
    sys.stderr.write(msg + "\n")
    notify("%s failed" % feature, msg)
    return 1


# ---------------------------------------------------------------------------
# menu popup
# ---------------------------------------------------------------------------


def cmd_menu_open() -> int:
    """Resolve the agent pane to act on and open the menu popup over it.

    The popup can only see its own pane once it takes focus, so the target is
    resolved here and handed over via AGENTS_TARGET_PANE (the same pattern the
    titles rename popup uses). An empty target still opens the popup — it says
    there is no agent here, which beats a keypress that silently does nothing.
    """
    target, _ = resolve_source()
    args = [herdr_bin(), "plugin", "pane", "open", "--plugin", "agents",
            "--entrypoint", "menu", "--focus",
            "--env", "AGENTS_TARGET_PANE=%s" % target]
    try:
        proc = subprocess.run(args, capture_output=True, text=True)
    except OSError as exc:
        sys.stderr.write("%s\n" % exc)
        return 1
    if proc.returncode != 0:
        # herdr allows one popup at a time, so a popup left open elsewhere makes
        # this a no-op; say so in the plugin log rather than dying silently.
        sys.stderr.write(error_message(proc.stderr, proc.stdout) + "\n")
        return 1
    return 0


def spawn_item(item_id: str, pane_id: str) -> None:
    """Run a menu item detached from the popup (every item is also a subcommand).

    The popup owns a herdr pane; herdr closes it when this process exits and
    restores focus to the pane that was focused before. Doing the work inline
    would race that restore — fork's new tab, say, would lose the focus it just
    took — so the popup only validates, hands the work to a detached child, and
    gets out of the way.
    """
    subprocess.Popen([sys.executable, os.path.abspath(__file__), item_id, pane_id],
                     start_new_session=True,
                     stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def cmd_menu_ui() -> int:
    """The popup: pick a feature to run against the agent that was focused."""
    try:
        import curses  # noqa: F401
    except ImportError:
        sys.stderr.write("Python curses is unavailable; cannot draw the agents menu.\n")
        return 1
    import locale
    locale.setlocale(locale.LC_ALL, "")
    target = (os.environ.get("AGENTS_TARGET_PANE") or "").strip()
    agent = find_agent(agent_list(), target)
    curses.wrapper(_menu_loop, target, agent)
    return 0


def _menu_loop(stdscr, target: str, agent: dict | None) -> None:
    import curses
    try:
        curses.set_escdelay(25)
    except (AttributeError, curses.error):
        pass
    curses.curs_set(0)
    stdscr.keypad(True)
    sel = 0
    hint = "↑/↓ move   enter: run   esc: close"
    lines = menu_lines(MENU)

    while True:
        # per item, and shown before you press anything: an item that cannot run
        # against this agent says so up front rather than on a dead keypress
        status = item_error(MENU[sel].id, agent)
        _, width = stdscr.getmaxyx()
        stdscr.erase()
        _put(stdscr, 0, "Agents — %s" % source_label(agent, target), width, curses.A_BOLD)
        for i, line in enumerate(lines):
            marker = "▌ " if i == sel else "  "
            attr = curses.A_REVERSE if i == sel else curses.A_NORMAL
            _put(stdscr, 2 + i, marker + line, width, attr)
        row = 2 + len(MENU) + 1
        _put(stdscr, row, status or hint, width,
             curses.A_NORMAL if status else curses.A_DIM)
        stdscr.refresh()

        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue
        if ch in (27, "\x1b", 3, "\x03", "q"):               # esc / ctrl-c / q
            return
        if ch in (curses.KEY_UP, "\x10", "k"):
            sel = (sel - 1) % len(MENU)
            continue
        if ch in (curses.KEY_DOWN, "\x0e", "j"):
            sel = (sel + 1) % len(MENU)
            continue
        idx = accel_index(MENU, ch)
        if idx >= 0:
            sel = idx
        elif ch not in ("\n", "\r", curses.KEY_ENTER):
            continue
        # run the selected item — the redraw already told us whether it can run
        if item_error(MENU[sel].id, agent):
            continue
        spawn_item(MENU[sel].id, target)
        return


def _disp_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _fit(s: str, maxw: int) -> str:
    if _disp_width(s) <= maxw:
        return s
    out, w = "", 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in "WF" else 1
        if w + cw > maxw - 1:
            break
        out, w = out + c, w + cw
    return out + "…"


def _put(stdscr, row: int, text: str, width: int, attr) -> None:
    import curses
    try:
        stdscr.addstr(row, 0, _fit(text, max(width - 1, 1)), attr)
    except curses.error:
        pass


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


# Each feature is a subcommand named after its MENU id: that is what the popup
# spawns, and what a keybinding can call directly to skip the menu.
FEATURE_COMMANDS = {
    "fork": cmd_fork,
}


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "menu-open":
        return cmd_menu_open()
    if cmd == "menu-ui":
        return cmd_menu_ui()
    if cmd in FEATURE_COMMANDS:
        return FEATURE_COMMANDS[cmd](argv[2] if len(argv) > 2 else "")
    sys.stderr.write("usage: agents.py <menu-open|menu-ui|%s> [PANE]\n"
                     % "|".join(sorted(FEATURE_COMMANDS)))
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
