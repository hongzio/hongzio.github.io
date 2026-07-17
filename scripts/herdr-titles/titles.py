#!/usr/bin/env python3
"""herdr-titles: feed each agent pane's live task title to the sidebar as $task.

herdr 0.7.4 lets sidebar rows carry custom `$name` tokens fed through pane
metadata (`herdr pane report-metadata ... --token name=value`). This plugin
reports a `task` token for every agent pane so you can put the agent's current
task title on its sidebar row for both Claude and Codex.

It also (by default) renames each agent pane's tab to a robot-prefixed task title
(🤖 <task>), so agent tabs stand out and read as the task rather than herdr's auto
label. Disable with
`[tab] rename = false` in the plugin config dir. Non-agent tabs are never touched,
and a tab is only renamed when its label actually differs (no tab-bar churn).

Title source, per pane (best-first):
  1. an explicit user-set title — Claude's /rename customTitle or Codex's
     thread_name. The user named it on purpose, so it wins outright (Claude's
     /rename only writes the transcript, not the terminal title, so without this
     it would be shadowed).
  2. the pane's own terminal title, when it looks like a task rather than the
     shell's `user@host:path` default. Claude Code keeps this as a live rolling
     summary ("온보드 페이지 다시 만들기").
  3. the derived transcript title: Claude ai-title -> first user message; Codex
     first user message. Covers Codex and Claude right after attach.

Driven by a small poll daemon, because herdr emits NO plugin event when a pane's
terminal title changes — and /rename is exactly that (a local slash command with
no idle<->working flip). So agent_status_changed alone can't catch it. The `watch`
daemon polls `pane list` (cheap) and, gated on a per-pane change signature
(terminal title + transcript mtime), refreshes only what actually changed — so a
/rename reflects within one poll (~3s) while idle panes cost nothing. The
[[events]] hooks just `ensure` the daemon is up (idempotent, pidfile-guarded).

The parse/derive helpers are pure (no I/O) so they can be unit-tested; the herdr
CLI and the agent transcript files are the only external dependencies and are
reached through thin wrappers.

Subcommands:
  ensure      start the watch daemon if not already running (from [[events]])
  watch       the poll loop itself (spawned detached by ensure)
  report      update one pane's $task from HERDR_PLUGIN_EVENT_JSON (manual/compat)
  report-all  update every agent pane now (backfill / the titles.refresh action)
"""
from __future__ import annotations

import fcntl
import glob
import json
import os
import re
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
CODEX_SESSIONS = os.path.join(HOME, ".codex", "sessions")
CODEX_INDEX = os.path.join(HOME, ".codex", "session_index.jsonl")

SOURCE = "titles"        # metadata source namespace (keeps our tokens ours)
TOKEN_TASK = "task"    # sidebar row token -> $task
TOKEN_AGO = "ago"      # sidebar row token -> $ago (relative time since last activity)
TITLE_MAX = 60         # cap so the reported token stays small; herdr re-truncates
TAB_LABEL_MAX = 24     # tab bar is narrow, so tab labels get a tighter cap
AGENT_TAB_PREFIX = "🤖 "  # marks agent tabs in the tab bar; cap applies to the title only

# Harness-injected "user" records that are not a real prompt (slash-command
# caveats, reminders, memory blocks) — skipped when picking a fallback title.
SYNTHETIC_PREFIXES = (
    "<local-command", "<command-message>", "<command-name>", "<command-args>",
    "Caveat:", "<bash-", "<system-reminder>", "<user-memory", "<user-prompt-submit",
)

# A terminal title that looks like a shell prompt (`user@host:~/path`) rather
# than an agent's task summary. Cheap to match and task titles don't hit it.
_SHELL_TITLE_RE = re.compile(r"^[^\s@]+@[^\s:]+:")


# ---------------------------------------------------------------------------
# pure helpers (no I/O)
# ---------------------------------------------------------------------------


def is_synthetic_user_text(text: str) -> bool:
    t = str(text).lstrip()
    return t == "" or t.startswith(SYNTHETIC_PREFIXES)


def message_text(content) -> str:
    """Extract plain text from a Claude/Codex message `content` field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in ("text", "input_text", "output_text") and block.get("text"):
                    parts.append(block["text"])
                elif isinstance(block.get("text"), str):
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""


def _clip(text: str, maxlen: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= maxlen else text[: maxlen - 1] + "…"


def clean_title(text: str) -> str:
    return _clip(text, TITLE_MAX)


def clean_tab_label(text: str) -> str:
    return _clip(text, TAB_LABEL_MAX)


def agent_tab_label(title: str) -> str:
    """Tab label for an agent tab: robot-prefixed task title (empty if no title)."""
    clipped = clean_tab_label(title)
    return AGENT_TAB_PREFIX + clipped if clipped else ""


def humanize_ago(seconds: float) -> str:
    """'Nm/Nh/Nd/Nw ago' — the largest unit, half-up rounded on the next-smaller
    unit (3h29m -> 3h ago, 3h31m -> 4h ago). Rounding that reaches a full higher
    unit carries up (59.6m -> 1h ago). Under ~30s reads as 'just now'."""
    d = max(0, int(seconds))
    minute, hour, day, week = 60, 3600, 86400, 604800
    if d < hour:
        v = int(d / minute + 0.5)      # int() on a positive float = round half up
        if v == 0:
            return "just now"
        if v < 60:
            return "%dm ago" % v
        d = hour                       # rounded up to a full hour; fall through
    if d < day:
        v = int(d / hour + 0.5)
        if v < 24:
            return "%dh ago" % v
        d = day
    if d < week:
        v = int(d / day + 0.5)
        if v < 7:
            return "%dd ago" % v
        d = week
    return "%dw ago" % int(d / week + 0.5)


def parse_tab_rename(text: str) -> bool:
    """Whether to also rename tabs. `[tab] rename = false` disables it; default on.

    A minimal hand-rolled scan rather than tomllib: the event hook's login shell
    resolves an older system python3 (3.9, no tomllib), so this must be stdlib-only.
    """
    section = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
        elif section == "tab" and "=" in line:
            key, val = (part.strip() for part in line.split("=", 1))
            if key == "rename":
                return val.strip("'\"").lower() not in ("false", "0", "no", "off")
    return True


def is_shell_title(title: str) -> bool:
    return bool(_SHELL_TITLE_RE.match(title.strip()))


def claude_titles(records) -> tuple[str, str]:
    """(explicit, derived) from Claude transcript records.

    explicit = the /rename custom title (user-set, authoritative). Title records
    carry no timestamp and can be rewritten, so the last one wins.
    derived  = the ai-generated title, else the first substantive user message.
    """
    custom = ai = first_user = ""
    for rec in records:
        if not isinstance(rec, dict):
            continue
        t = rec.get("type")
        if t == "custom-title" and isinstance(rec.get("customTitle"), str):
            custom = rec["customTitle"]
        elif t == "ai-title" and isinstance(rec.get("aiTitle"), str):
            ai = rec["aiTitle"]
        if not first_user and t == "user":
            txt = message_text((rec.get("message") or {}).get("content"))
            if txt.strip() and not is_synthetic_user_text(txt):
                first_user = txt
    return custom.strip(), (ai.strip() or first_user.strip())


def codex_titles(records, thread_name: str = "") -> tuple[str, str]:
    """(explicit, derived): explicit = user thread_name; derived = first user msg."""
    first_user = ""
    for rec in records:
        if not isinstance(rec, dict) or rec.get("type") != "response_item":
            continue
        payload = rec.get("payload") or {}
        if payload.get("role") == "user":
            txt = message_text(payload.get("content"))
            if txt.strip() and not is_synthetic_user_text(txt):
                first_user = txt
                break
    return thread_name.strip(), first_user.strip()


def event_pane_id(obj) -> str | None:
    """pane_id from a herdr plugin event payload (HERDR_PLUGIN_EVENT_JSON).

    Handles both shapes: agent_status_changed carries data.pane_id directly;
    pane.updated carries the full pane under data.pane.
    """
    data = obj.get("data") if isinstance(obj, dict) else None
    if not isinstance(data, dict):
        return None
    pane = data.get("pane_id")
    if isinstance(pane, str) and pane:
        return pane
    nested = data.get("pane")
    if isinstance(nested, dict) and isinstance(nested.get("pane_id"), str) and nested["pane_id"]:
        return nested["pane_id"]
    return None


# ---------------------------------------------------------------------------
# transcript I/O
# ---------------------------------------------------------------------------


def read_claude_records(path: str) -> list:
    """Parse only the transcript lines that can carry a title/first-user msg."""
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if '-title"' not in line and '"type":"user"' not in line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def read_codex_records(path: str, limit: int = 400) -> list:
    """Parse the head of a Codex rollout (the first user turn is near the top)."""
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i > limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def find_claude_path(session_id: str) -> str | None:
    hits = glob.glob(os.path.join(CLAUDE_PROJECTS, "*", session_id + ".jsonl"))
    return hits[0] if hits else None


def find_codex_path(session_id: str) -> str | None:
    hits = glob.glob(
        os.path.join(CODEX_SESSIONS, "**", "rollout-*" + session_id + ".jsonl"),
        recursive=True,
    )
    return hits[0] if hits else None


def codex_thread_name(session_id: str) -> str:
    try:
        with open(CODEX_INDEX, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or session_id not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("id") == session_id and isinstance(rec.get("thread_name"), str):
                    return rec["thread_name"]
    except OSError:
        pass
    return ""


def session_titles(agent: str, session_id: str) -> tuple[str, str]:
    """(explicit, derived) title from the agent's transcript; ("", "") if none."""
    if agent == "claude":
        path = find_claude_path(session_id)
        return claude_titles(read_claude_records(path)) if path else ("", "")
    if agent == "codex":
        path = find_codex_path(session_id)
        if not path:
            return ("", "")
        return codex_titles(read_codex_records(path), codex_thread_name(session_id))
    return ("", "")


def transcript_path(pane: dict, cache: dict = None) -> str | None:
    """Locate a pane's agent transcript file; optional session_id->path cache."""
    agent = pane.get("agent") or (pane.get("agent_session") or {}).get("agent")
    sid = (pane.get("agent_session") or {}).get("value")
    if not (agent and sid):
        return None
    if cache is not None and cache.get(sid):
        return cache[sid]
    path = find_claude_path(sid) if agent == "claude" else \
        find_codex_path(sid) if agent == "codex" else None
    if cache is not None and path:
        cache[sid] = path
    return path


def transcript_mtime(pane: dict, cache: dict = None) -> float:
    path = transcript_path(pane, cache)
    if not path:
        return 0.0
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def pane_ago(pane: dict, mtime: float = None) -> str:
    """Relative time since the agent last wrote its transcript (~= last activity /
    completion). Empty when there is no transcript to date."""
    if mtime is None:
        mtime = transcript_mtime(pane)
    return humanize_ago(time.time() - mtime) if mtime else ""


def title_for_pane(pane: dict) -> str:
    """Best task title for an agent pane.

    Priority: an explicit user-set title (Claude /rename customTitle, Codex
    thread_name) wins — the user named it on purpose. Otherwise the pane's own
    terminal title when it reads like a task (Claude's live rolling summary),
    then the derived transcript title.
    """
    agent = pane.get("agent") or (pane.get("agent_session") or {}).get("agent")
    sess = (pane.get("agent_session") or {}).get("value")
    explicit, derived = session_titles(agent, sess) if agent and sess else ("", "")
    if explicit:
        return clean_title(explicit)
    tt = (pane.get("terminal_title_stripped") or "").strip()
    if tt and not is_shell_title(tt):
        return clean_title(tt)
    if derived:
        return clean_title(derived)
    return ""


# ---------------------------------------------------------------------------
# herdr CLI wrappers
# ---------------------------------------------------------------------------


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def run_json(args: list[str]) -> dict:
    try:
        proc = subprocess.run([herdr_bin(), *args], capture_output=True, text=True)
        return json.loads(proc.stdout) if proc.stdout.strip() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def pane_info(pane_id: str) -> dict | None:
    data = run_json(["pane", "get", pane_id])
    if not data:
        return None
    result = data.get("result", data)
    return result.get("pane", result) if isinstance(result, dict) else None


def report_token(pane_id: str, name: str, value: str) -> None:
    """Set (or clear, when value is empty) one metadata token under --source titles."""
    args = ["pane", "report-metadata", pane_id, "--source", SOURCE]
    args += ["--token", "%s=%s" % (name, value)] if value else ["--clear-token", name]
    try:
        subprocess.run([herdr_bin(), *args], capture_output=True, text=True)
    except OSError:
        pass


def tab_rename_enabled() -> bool:
    """Read [tab] rename from the plugin config dir; default on if absent/unreadable."""
    d = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if not d:
        return True
    try:
        with open(os.path.join(d, "config.toml"), encoding="utf-8") as fh:
            return parse_tab_rename(fh.read())
    except OSError:
        return True


def tab_label(tab_id: str) -> str:
    tab = (run_json(["tab", "get", tab_id]).get("result") or {}).get("tab") or {}
    return tab.get("label") or ""


def set_tab_label(tab_id: str, label: str) -> None:
    """Rename the tab, skipping the API call when it already shows this label."""
    if not label or tab_label(tab_id) == label:
        return
    try:
        subprocess.run([herdr_bin(), "tab", "rename", tab_id, label],
                       capture_output=True, text=True)
    except OSError:
        pass


def apply_pane(pane: dict, rename_tabs: bool, mtime: float = None) -> None:
    """Report an agent pane's $task + $ago, and (optionally) rename its tab.

    Idempotent: each token is only rewritten when its value actually changes, and
    the tab only when its label differs — so re-applying every poll is cheap.
    """
    pane_id = pane.get("pane_id")
    if not pane_id:
        return
    tokens = pane.get("tokens") or {}
    title = title_for_pane(pane)
    if title != (tokens.get(TOKEN_TASK) or ""):
        report_token(pane_id, TOKEN_TASK, title)
    ago = pane_ago(pane, mtime)
    if ago != (tokens.get(TOKEN_AGO) or ""):
        report_token(pane_id, TOKEN_AGO, ago)
    if rename_tabs and title and pane.get("tab_id"):
        set_tab_label(pane["tab_id"], agent_tab_label(title))


# ---------------------------------------------------------------------------
# watch daemon (pidfile-guarded, one per herdr instance)
# ---------------------------------------------------------------------------


def state_dir() -> str:
    d = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if not d:
        d = os.path.join(HOME, ".local", "state", "herdr", "plugins", "titles")
    return d


def pidfile_path() -> str:
    # one daemon per herdr instance: key the pidfile by the socket this hook talks to.
    sp = os.environ.get("HERDR_SOCKET_PATH") or "default"
    key = re.sub(r"[^A-Za-z0-9]", "_", sp)[-40:]
    return os.path.join(state_dir(), "watch-%s.pid" % key)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True  # e.g. PermissionError -> it exists


def daemon_running() -> bool:
    try:
        with open(pidfile_path(), encoding="utf-8") as fh:
            return _pid_alive(int(fh.read().strip()))
    except (OSError, ValueError):
        return False


def _log(msg: str) -> None:
    """Append a line to the daemon log (best effort). Set TITLES_DEBUG=1 for per-poll
    detail; errors are always logged so a silently-dead daemon is diagnosable."""
    try:
        with open(os.path.join(state_dir(), "watch.log"), "a", encoding="utf-8") as fh:
            fh.write("%d %s\n" % (int(time.time()), msg))
    except OSError:
        pass


def cmd_watch() -> int:
    """The poll loop. Single-instance via flock; exits when its herdr goes away."""
    os.makedirs(state_dir(), exist_ok=True)
    lockfd = os.open(pidfile_path() + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another watcher already owns this instance
    with open(pidfile_path(), "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))

    interval = float(os.environ.get("TITLES_WATCH_INTERVAL", "3.0"))
    debug = os.environ.get("TITLES_DEBUG") == "1"
    sockpath = os.environ.get("HERDR_SOCKET_PATH")
    rename_tabs = tab_rename_enabled()
    _log("watch start pid=%d interval=%.2f rename_tabs=%s" % (os.getpid(), interval, rename_tabs))
    last: dict = {}          # pane_id -> signature
    path_cache: dict = {}    # session_id -> transcript path
    while True:
        if sockpath and not os.path.exists(sockpath):
            _log("socket gone, exiting")
            return 0  # this herdr instance is gone; stop the daemon
        try:
            panes = run_json(["pane", "list"]).get("result", {}).get("panes", [])
            seen = set()
            applied = 0
            for pane in panes:
                if not (pane.get("agent") or pane.get("agent_session")):
                    continue
                pid = pane.get("pane_id")
                if not pid:
                    continue
                seen.add(pid)
                mtime = transcript_mtime(pane, path_cache)
                tt = pane.get("terminal_title_stripped") or ""
                ago = humanize_ago(time.time() - mtime) if mtime else ""
                # $ago changes as time passes even when nothing else does, so it is
                # part of the signature — that's what makes "N분전" tick up on idle
                # panes. tt + mtime still catch /rename and new activity.
                sig = (tt, mtime, ago)
                if sig != last.get(pid):
                    last[pid] = sig
                    apply_pane(pane, rename_tabs, mtime=mtime)
                    applied += 1
            for pid in list(last):        # forget closed panes
                if pid not in seen:
                    del last[pid]
            if debug:
                _log("poll panes=%d agents=%d applied=%d" % (len(panes), len(seen), applied))
        except Exception as exc:
            _log("poll error: %r" % (exc,))
        time.sleep(interval)


def cmd_ensure() -> int:
    """Start the watch daemon if it isn't already running (idempotent)."""
    if daemon_running():
        return 0
    if os.fork() != 0:          # detach: setsid + second fork, like herdr-web
        return 0
    os.setsid()
    if os.fork() != 0:
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    try:
        cmd_watch()
    finally:
        os._exit(0)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_report() -> int:
    raw = os.environ.get("HERDR_PLUGIN_EVENT_JSON")
    if not raw:
        return 0
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    pane_id = event_pane_id(obj)
    if not pane_id:
        return 0
    pane = pane_info(pane_id)
    if not pane or not (pane.get("agent") or pane.get("agent_session")):
        return 0
    apply_pane(pane, tab_rename_enabled())
    return 0


def cmd_report_all() -> int:
    rename_tabs = tab_rename_enabled()
    for pane in run_json(["pane", "list"]).get("result", {}).get("panes", []):
        if pane.get("agent") or pane.get("agent_session"):
            apply_pane(pane, rename_tabs)
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "ensure":
        return cmd_ensure()
    if cmd == "watch":
        return cmd_watch()
    if cmd == "report":
        return cmd_report()
    if cmd == "report-all":
        return cmd_report_all()
    sys.stderr.write("usage: titles.py <ensure|watch|report|report-all>\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
