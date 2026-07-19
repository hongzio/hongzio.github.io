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
     thread_name. The user named it on purpose, so it wins outright. /rename does
     set the terminal title too, but Claude's live rolling summary overwrites that
     during work, so reading the transcript keeps the explicit name authoritative.
  2. the pane's own terminal title, when it looks like a task rather than the
     shell's `user@host:path` default. Claude Code keeps this as a live rolling
     summary ("온보드 페이지 다시 만들기").
  3. the derived transcript title: Claude ai-title -> first user message; Codex
     first user message. Covers Codex and Claude right after attach.

Driven by a small `watch` daemon that pushes off the herdr socket event stream
rather than busy-polling. The plugin [[events]] hook surface carries no title-change
event (agent_status_changed only flips on idle<->working), but the socket API's
`events.subscribe` does: a `pane.updated` fires whenever a pane's terminal title
changes — and Claude's /rename emits an OSC title, so it surfaces there too (empirically
terminal_title tracks the /rename customTitle). The daemon holds one subscription and,
gated on a per-pane change signature (terminal title + last-activity ts + $ago string),
refreshes only what actually changed — so a /rename reflects in <100ms while idle panes
cost nothing (blocking read, no wakeups). Each pane.updated inlines the full pane, so no
`pane list` round-trip is needed per change. $ago is the one thing that moves with the
clock alone, so a coarse timer sleeps until the next humanize bucket boundary (a "5m"
pane ticks once/min, a "3h" pane once/hour) and rewrites only panes whose string flipped;
that timer doubles as a slow re-stat fallback for any missed transcript write. The
[[events]] hooks just `ensure` the daemon is up (idempotent, pidfile-guarded).

The parse/derive helpers are pure (no I/O) so they can be unit-tested; the herdr
CLI, its event socket, and the agent transcript files are the only external
dependencies and are reached through thin wrappers.

Subcommands:
  ensure      start the watch daemon if not already running (from [[events]])
  watch       the event-subscription loop itself (spawned detached by ensure)
  report      update one pane's $task from HERDR_PLUGIN_EVENT_JSON (manual/compat)
  report-all  update every agent pane now (backfill / the titles.refresh action)
"""
from __future__ import annotations

import datetime
import fcntl
import glob
import json
import os
import re
import select
import socket
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


_AGO_UNITS = (60, 3600, 86400, 604800)  # minute, hour, day, week — matches humanize_ago


def _active_ago_unit(age: float) -> int:
    """The unit humanize_ago(age) renders in (60/3600/86400/604800 seconds).

    Mirrors humanize_ago's branch structure, including the carry-up fall-through
    (59.6m renders as '1h', so its active unit is the hour), so the boundary math
    below lands on the exact age where the rendered string next changes."""
    minute, hour, day, week = _AGO_UNITS
    d = max(0.0, age)
    if d < hour:
        if int(d / minute + 0.5) < 60:
            return minute
        d = hour
    if d < day:
        if int(d / hour + 0.5) < 24:
            return hour
        d = day
    if d < week:
        if int(d / day + 0.5) < 7:
            return day
    return week


def seconds_to_next_ago_change(age: float) -> float:
    """Seconds from now until humanize_ago(age) would render a different string.

    Lets the daemon sleep exactly until $ago flips rather than polling on a fixed
    tick: a '5m ago' pane wakes ~once/min, a '3h ago' pane ~once/hour, a '2d ago'
    pane ~once/day. Rounding is half-up on the active unit, so the string changes
    at the (v + 0.5) * unit boundary."""
    age = max(0.0, age)
    unit = _active_ago_unit(age)
    boundary = (int(age / unit + 0.5) + 0.5) * unit
    while boundary <= age:
        boundary += unit
    return max(1.0, boundary - age)


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
    """The session's current thread_name. session_index.jsonl is append-only — each
    /rename adds a new record — so the LAST (highest updated_at) entry for this id
    wins; returning the first would pin the name to the original rename forever."""
    best_name, best_key = "", ""
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
                    key = rec.get("updated_at") or ""
                    if best_name == "" or key >= best_key:
                        best_name, best_key = rec["thread_name"], key
    except OSError:
        pass
    return best_name


def codex_index_mtime() -> float:
    try:
        return os.path.getmtime(CODEX_INDEX)
    except OSError:
        return 0.0


def read_index_entries() -> list:
    """Every renamed-session record in Codex's session_index.jsonl (id + thread_name).
    Only /rename'd sessions land here, so this list is naturally small."""
    out = []
    try:
        with open(CODEX_INDEX, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and isinstance(rec.get("id"), str):
                    out.append(rec)
    except OSError:
        pass
    return out


def codex_rollout_cwd(path: str) -> str:
    """The session's cwd, read from the head of a Codex rollout."""
    try:
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i > 40:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = rec.get("payload") or {}
                if isinstance(payload, dict) and isinstance(payload.get("cwd"), str):
                    return payload["cwd"]
    except OSError:
        pass
    return ""


def pick_codex_session(entries: list, cwd: str) -> "str | None":
    """The id of the most recently renamed session whose cwd matches (or None).

    Pure so the newest-match tie-break is unit-testable; `entries` are dicts with
    id/cwd/updated_at."""
    best_id = best_key = None
    for e in entries:
        if not cwd or e.get("cwd") != cwd:
            continue
        key = e.get("updated_at") or ""
        if best_id is None or key > best_key:
            best_id, best_key = e.get("id"), key
    return best_id


_CODEX_CWD_CACHE: dict = {}   # cwd -> (index_mtime, sid_or_None)


def codex_session_for_cwd(cwd: str) -> "str | None":
    """Best-effort session id for a Codex pane herdr never bound (no agent_session):
    the newest renamed session sharing this cwd. Cached on session_index.jsonl mtime,
    and only the renamed sessions are scanned, so this stays cheap."""
    if not cwd:
        return None
    mtime = codex_index_mtime()
    cached = _CODEX_CWD_CACHE.get(cwd)
    if cached and cached[0] == mtime:
        return cached[1]
    enriched = []
    for e in read_index_entries():
        sid = e.get("id")
        path = find_codex_path(sid) if sid else None
        enriched.append({"id": sid,
                         "cwd": codex_rollout_cwd(path) if path else "",
                         "updated_at": e.get("updated_at")})
    sid = pick_codex_session(enriched, cwd)
    _CODEX_CWD_CACHE[cwd] = (mtime, sid)
    return sid


def resolve_session(pane: dict) -> "tuple[str | None, str | None]":
    """(agent, session_id) for a pane. Falls back to a cwd match for Codex panes
    herdr left unbound, so a /rename'd-but-unbound Codex session still resolves."""
    agent = pane.get("agent") or (pane.get("agent_session") or {}).get("agent")
    sid = (pane.get("agent_session") or {}).get("value")
    if not sid and agent == "codex":
        sid = codex_session_for_cwd(pane.get("cwd") or pane.get("foreground_cwd") or "")
    return agent, sid


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
    agent, sid = resolve_session(pane)
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


def _parse_iso(iso: str) -> float:
    """Claude's UTC ISO-8601 stamp (e.g. 2026-07-18T13:39:02.000Z) -> unix epoch.

    Parses the second-precision prefix so it works on Python 3.9, whose
    datetime.fromisoformat rejects both the 'Z' suffix and 3-digit fractions —
    the daemon runs under the system 3.9, so this must not depend on 3.11+."""
    try:
        dt = datetime.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
    except (ValueError, TypeError):
        return 0.0


def last_activity_ts(path: str) -> float:
    """Epoch of the last real assistant/user turn in a Claude transcript.

    Uses the message timestamps, NOT the file mtime, so /rename (a custom-title
    record) and session restore (metadata rewrites) do not count as activity —
    only actual turns do. Reads the tail (last 256 KB) since the last turn is near
    the end. Returns 0.0 for Codex/no-timestamp transcripts (caller falls back)."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > 262144:
                fh.seek(size - 262144)
                fh.readline()  # discard the partial first line
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return 0.0
    ts = 0.0
    for line in data.splitlines():
        if '"timestamp"' not in line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = rec.get("type")
        if kind == "assistant" or (
            kind == "user"
            and not is_synthetic_user_text(message_text((rec.get("message") or {}).get("content")))
        ):
            ep = _parse_iso(rec.get("timestamp") or "")
            if ep > ts:
                ts = ep
    return ts


def pane_ago(pane: dict, ts: float = None) -> str:
    """Relative time since the agent's last real turn (~= last completion). Empty
    when there's no transcript. Falls back to file mtime when no turn timestamp is
    found (e.g. Codex)."""
    if ts is None:
        path = transcript_path(pane)
        ts = (last_activity_ts(path) if path else 0.0) or transcript_mtime(pane)
    return humanize_ago(time.time() - ts) if ts else ""


def title_for_pane(pane: dict, sess: "tuple[str, str]" = None) -> str:
    """Best task title for an agent pane.

    Priority: an explicit user-set title (Claude /rename customTitle, Codex
    thread_name) wins — the user named it on purpose. Otherwise the pane's own
    terminal title when it reads like a task (Claude's live rolling summary),
    then the derived transcript title.

    `sess` is the (explicit, derived) pair; passed in by the daemon (cached, mtime-
    gated) to avoid re-reading the transcript on every event, else resolved here.
    """
    if sess is None:
        agent, sid = resolve_session(pane)
        sess = session_titles(agent, sid) if agent and sid else ("", "")
    explicit, derived = sess
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
    if os.environ.get("TITLES_DEBUG") == "1":
        _log("WRITE %s %s=%r" % (pane_id, name, value))
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


def apply_pane(pane: dict, rename_tabs: bool, ts: float = None, title: str = None) -> None:
    """Report an agent pane's $task + $ago, and (optionally) rename its tab.

    Idempotent: each token is only rewritten when its value actually changes, and
    the tab only when its label differs — so re-applying every poll is cheap.
    `ts` is the last-activity epoch (the daemon caches it); None recomputes it.
    `title` is the precomputed $task (the daemon already has it); None recomputes it.
    """
    pane_id = pane.get("pane_id")
    if not pane_id:
        return
    tokens = pane.get("tokens") or {}
    if title is None:
        title = title_for_pane(pane)
    if title != (tokens.get(TOKEN_TASK) or ""):
        report_token(pane_id, TOKEN_TASK, title)
    ago = pane_ago(pane, ts)
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


# subscriptions the watch loop needs: pane.updated carries every terminal-title /
# tokens / status change (full pane inlined); created/closed/exited keep the set in
# sync. agent_status_changed is subsumed by pane.updated, and its subscription would
# demand a per-pane id anyway, so it is left out.
WATCH_SUBSCRIPTIONS = [
    {"type": "pane.updated"},
    {"type": "pane.created"},
    {"type": "pane.closed"},
    {"type": "pane.exited"},
]


def subscribe_events(subscriptions: list) -> "socket.socket | None":
    """Open the herdr event socket and start a subscription; None if unavailable."""
    sp = os.environ.get("HERDR_SOCKET_PATH")
    if not sp:
        return None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(sp)
        req = {"id": "titles", "method": "events.subscribe",
               "params": {"subscriptions": subscriptions}}
        sock.sendall((json.dumps(req) + "\n").encode())
        return sock
    except OSError:
        return None


def _cached_session_titles(agent: str, sid: str, meta: tuple, state: dict) -> tuple:
    """(explicit, derived) for a session, re-read only when `meta` (transcript mtime,
    plus Codex's session_index mtime) changes. Keeps title derivation off the hot
    event path while still catching a Codex /rename, which touches only the index."""
    if not (agent and sid):
        return ("", "")
    cached = state["sess_cache"].get(sid)
    if cached and cached[0] == meta:
        return cached[1]
    st = session_titles(agent, sid)
    state["sess_cache"][sid] = (meta, st)
    return st


def _refresh_pane(pane: dict, state: dict, rename_tabs: bool) -> float:
    """Re-derive one agent pane's signature and apply it if it changed; return its
    last-activity ts. Shared by the event path, the $ago tick, and the backfill so
    the change-gate and caches behave identically no matter what woke us.

    Gated on (title, terminal_title, last-activity ts, $ago string): terminal_title
    catches Claude /rename & live summaries, ts catches real new turns, $ago makes
    idle panes tick, and `title` catches an explicit rename that moves none of those
    — notably a Codex /rename, which only rewrites session_index.jsonl and emits no
    event (so the $ago tick, not a push, is what reflects it). Our own token writes
    echo back as pane.updated but move nothing here, so the daemon ignores itself."""
    pid = pane.get("pane_id")
    if not pid:
        return 0.0
    agent, sid = resolve_session(pane)
    # last-activity epoch, re-parsed only when the transcript file actually changes.
    # A /rename or restore bumps mtime but leaves the last real turn ts unchanged,
    # so $ago reflects real work, not metadata writes.
    mtime = transcript_mtime(pane, state["path_cache"])
    cached = state["ts_cache"].get(sid)
    if cached and cached[0] == mtime:
        ts = cached[1]
    else:
        path = transcript_path(pane, state["path_cache"])
        ts = (last_activity_ts(path) if path else 0.0) or mtime
        state["ts_cache"][sid] = (mtime, ts)
    # a Codex /rename lives in the shared index, not the transcript, so its mtime is
    # part of the title's cache key.
    meta = (mtime, codex_index_mtime()) if agent == "codex" else (mtime,)
    title = title_for_pane(pane, _cached_session_titles(agent, sid, meta, state))
    tt = pane.get("terminal_title_stripped") or ""
    ago = humanize_ago(time.time() - ts) if ts else ""
    sig = (title, tt, ts, ago)
    if sig != state["last"].get(pid):
        state["last"][pid] = sig
        apply_pane(pane, rename_tabs, ts=ts, title=title)
    state["panes"][pid] = pane
    state["ts_by_pid"][pid] = ts
    return ts


def _forget_pane(pid: str, state: dict) -> None:
    for book in ("last", "panes", "ts_by_pid"):
        state[book].pop(pid, None)


def _next_ago_wait(state: dict, cap: float) -> float:
    """Seconds to sleep until some pane's $ago string would next flip (capped)."""
    now = time.time()
    wait = cap
    for ts in state["ts_by_pid"].values():
        if ts:
            wait = min(wait, seconds_to_next_ago_change(now - ts))
    return max(0.5, min(wait, cap))


def cmd_watch() -> int:
    """The event-subscription loop. Single-instance via flock; exits when its herdr
    goes away. Pushes off pane.updated instead of polling; a coarse $ago timer sleeps
    until the next humanize bucket boundary and doubles as a missed-write fallback."""
    os.makedirs(state_dir(), exist_ok=True)
    lockfd = os.open(pidfile_path() + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another watcher already owns this instance
    with open(pidfile_path(), "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))

    # cap on the $ago timer: how long we may sleep between forced re-derives even when
    # every pane's next flip is further out. Keeps us honest as a missed-write fallback.
    cap = float(os.environ.get("TITLES_AGO_INTERVAL")
                or os.environ.get("TITLES_WATCH_INTERVAL") or "60")
    debug = os.environ.get("TITLES_DEBUG") == "1"
    sockpath = os.environ.get("HERDR_SOCKET_PATH")
    rename_tabs = tab_rename_enabled()
    _log("watch start pid=%d push mode ago_cap=%.1f rename_tabs=%s"
         % (os.getpid(), cap, rename_tabs))
    # pane_id -> signature / last full pane / last-activity ts; session_id caches.
    state = {"last": {}, "panes": {}, "ts_by_pid": {},
             "path_cache": {}, "ts_cache": {}, "sess_cache": {}}

    while True:
        if sockpath and not os.path.exists(sockpath):
            _log("socket gone, exiting")
            return 0  # this herdr instance is gone; stop the daemon
        sock = subscribe_events(WATCH_SUBSCRIPTIONS)
        if sock is None:
            _log("subscribe failed; retrying")
            time.sleep(2)
            continue
        _log("subscribed")
        # Backfill from an authoritative snapshot: reconcile anything that changed
        # while we were (re)connecting, and forget panes that vanished.
        try:
            snapshot = run_json(["pane", "list"]).get("result", {}).get("panes", [])
            live = set()
            for pane in snapshot:
                if pane.get("agent") or pane.get("agent_session"):
                    pid = pane.get("pane_id")
                    if pid:
                        live.add(pid)
                        _refresh_pane(pane, state, rename_tabs)
            for pid in [p for p in state["panes"] if p not in live]:
                _forget_pane(pid, state)
        except Exception as exc:
            _log("backfill error: %r" % (exc,))

        buf = b""
        # Deadline for the next $ago tick. It must fire on schedule even while events
        # stream in — a busy pane keeps select readable, so an idle-timeout tick would
        # starve and a Codex /rename (no event of its own) would never be re-checked.
        next_tick = time.time() + _next_ago_wait(state, cap)
        try:
            while True:
                if sockpath and not os.path.exists(sockpath):
                    _log("socket gone, exiting")
                    sock.close()
                    return 0
                ready, _, _ = select.select([sock], [], [], max(0.0, next_tick - time.time()))
                if ready:
                    data = sock.recv(65536)
                    if not data:
                        _log("event stream closed; reconnecting")
                        break
                    buf += data
                    applied = 0
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        d = obj.get("data")
                        if not isinstance(d, dict):
                            continue  # subscription_started ack and other envelopes
                        et = d.get("type")
                        if et in ("pane_updated", "pane_created"):
                            pane = d.get("pane") or {}
                            pid = pane.get("pane_id")
                            if not pid:
                                continue
                            if pane.get("agent") or pane.get("agent_session"):
                                _refresh_pane(pane, state, rename_tabs)
                                applied += 1
                            else:
                                _forget_pane(pid, state)  # agent released this pane
                        elif et in ("pane_closed", "pane_exited"):
                            pid = d.get("pane_id")
                            if pid:
                                _forget_pane(pid, state)
                    if debug and applied:
                        _log("events applied=%d panes=%d" % (applied, len(state["panes"])))
                if time.time() >= next_tick:
                    # $ago tick: re-derive every known pane (advances $ago, and re-reads
                    # transcripts / the Codex index as a fallback for changes with no event).
                    for pane in list(state["panes"].values()):
                        _refresh_pane(pane, state, rename_tabs)
                    next_tick = time.time() + _next_ago_wait(state, cap)
                    if debug:
                        _log("ago tick panes=%d" % len(state["panes"]))
        except OSError as exc:
            _log("stream error: %r; reconnecting" % (exc,))
        finally:
            try:
                sock.close()
            except OSError:
                pass
        time.sleep(1)  # brief backoff before resubscribing


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
