#!/usr/bin/env python3
"""herdr-titles: feed each agent pane's live task title and herdr agent name to
the sidebar as $task and $name.

herdr 0.7.4 lets sidebar rows carry custom `$name` tokens fed through pane
metadata (`herdr pane report-metadata ... --token name=value`). This plugin
reports two tokens for every agent pane so you can put them on its sidebar row
for both Claude and Codex:

  $task  the agent's current task title (derived — see the priority list below)
  $name  the herdr agent name (`herdr agent rename`); empty when the agent has none

It also (by default) renames each agent pane's tab to a robot-prefixed task title
(🤖 <task>), so agent tabs stand out and read as the task rather than herdr's auto
label. Disable with `[tab] rename = false` in the plugin config dir. Non-agent tabs
are never touched, and a tab is only renamed when its label actually differs (no
tab-bar churn).

$name is herdr's own agent name, not something this plugin owns: `herdr agent
rename <pane> <name>` is the single source of truth, and the plugin only mirrors
it into a sidebar token (herdr has no built-in sidebar token for it). herdr's
rules apply as-is — the name must match [a-z][a-z0-9_-]{0,31}, must be unique
among live agents, and herdr clears it when the agent exits, is released, or is
replaced. The `titles.rename` action opens a small popup that renames the focused
agent pane and writes the token immediately, so a rename shows up at once.

$task source, per pane (best-first):
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
gated on a per-pane change signature (title + terminal title + agent name), refreshes
only what actually changed — so a /rename reflects in <100ms while idle panes cost
nothing (blocking read, no wakeups). Each pane.updated inlines the full pane, so no
`pane list` round-trip is needed per change.

Two changes carry no event at all and need a slow timer as the fallback: a Codex
/rename (it only rewrites thread_name in the shared session_index.jsonl) and a
`herdr agent rename` typed straight into a shell. So a coarse REFRESH_INTERVAL timer
re-derives every known pane from an authoritative `agent list` snapshot. That snapshot
is also the only place the agent name is readable — pane.updated inlines a PaneInfo,
which has no `name` field — so between ticks the push path reuses the last snapshot's
name. Immediate full reconciliation is the `titles.refresh` action; the popup rename
writes its own token, so it never waits for a tick.

The [[events]] hooks just `ensure` the daemon is up (idempotent, pidfile-guarded).

The parse/derive helpers are pure (no I/O) so they can be unit-tested; the herdr
CLI, its event socket, and the agent transcript files are the only external
dependencies and are reached through thin wrappers.

Subcommands:
  ensure       start the watch daemon if not already running (from [[events]])
  watch        the event-subscription loop itself (spawned detached by ensure)
  report       update one pane's tokens from HERDR_PLUGIN_EVENT_JSON (manual/compat)
  report-all   update every agent pane now (backfill / the titles.refresh action)
  rename-open  resolve the target agent pane and open the rename popup (the action)
  rename-ui    the rename popup itself (runs inside the plugin popup pane)
"""
from __future__ import annotations

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
TOKEN_NAME = "name"    # sidebar row token -> $name (the herdr agent name)
TITLE_MAX = 60         # cap so the reported token stays small; herdr re-truncates
TAB_LABEL_MAX = 24     # tab bar is narrow, so tab labels get a tighter cap
AGENT_TAB_PREFIX = "🤖 "  # marks agent tabs in the tab bar; cap applies to the label only

# Harness-injected "user" records that are not a real prompt (slash-command
# caveats, reminders, memory blocks) — skipped when picking a fallback title.
SYNTHETIC_PREFIXES = (
    "<local-command", "<command-message>", "<command-name>", "<command-args>",
    "Caveat:", "<bash-", "<system-reminder>", "<user-memory", "<user-prompt-submit",
)

# A terminal title that looks like a shell prompt (`user@host:~/path`) rather
# than an agent's task summary. Cheap to match and task titles don't hit it.
_SHELL_TITLE_RE = re.compile(r"^[^\s@]+@[^\s:]+:")

# herdr's own agent-name rule (mirrored so the popup can reject before calling).
_AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


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
    """Tab label for an agent tab: robot-prefixed task title (empty if no title).

    Deliberately the task, not the agent name: the tab bar answers "what is going
    on in there", and the name is already on the sidebar row."""
    clipped = clean_tab_label(title)
    return AGENT_TAB_PREFIX + clipped if clipped else ""


def is_valid_agent_name(name: str) -> bool:
    """herdr's rule: [a-z][a-z0-9_-]{0,31}. Uniqueness is herdr's to enforce."""
    return bool(_AGENT_NAME_RE.match(name or ""))


def name_token(name: str) -> str:
    """The $name token value: the herdr agent name, or "" when it has none.

    Empty clears the token, so an unnamed agent shows nothing on its sidebar row
    rather than a placeholder."""
    return " ".join(str(name or "").split())


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


def context_pane(context_json: str) -> str:
    """focused_pane_id from HERDR_PLUGIN_CONTEXT_JSON, herdr's invocation context.

    This is the pane the user is actually looking at when a keybinding fires, which
    is what "rename this agent" means; HERDR_PANE_ID is only the pane the command
    happens to run in. Empty when the env var is absent or unparsable.
    """
    try:
        ctx = json.loads(context_json or "")
    except json.JSONDecodeError:
        return ""
    pid = ctx.get("focused_pane_id") if isinstance(ctx, dict) else None
    return pid if isinstance(pid, str) else ""


def resolve_target_pane(agents: list, caller_pane: str = "") -> str:
    """The agent pane a rename should target, given an `agent list` snapshot.

    Prefers the pane the caller named (the focused pane, else the pane the command
    ran in) and otherwise falls back to whichever agent herdr reports as focused.
    A caller pane that holds no agent yields "" rather than silently retargeting
    somebody else's agent.
    """
    known = {a.get("pane_id") for a in agents if isinstance(a, dict)}
    if caller_pane:
        return caller_pane if caller_pane in known else ""
    for a in agents:
        if isinstance(a, dict) and a.get("focused"):
            return a.get("pane_id") or ""
    return ""


def error_message(*streams: str) -> str:
    """The human-readable part of herdr's JSON error output ({"error": {...}}).

    Falls back to the first non-empty line, so an unparsable failure still says
    something useful in the popup instead of a bare "failed".
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
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
            return line
    return "rename failed"


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


def agent_list() -> list:
    """Every agent pane, as AgentInfo dicts.

    Used instead of `pane list` everywhere the full set is needed: it is already
    filtered to agent panes and, unlike PaneInfo, carries the agent's herdr `name`.
    """
    agents = run_json(["agent", "list"]).get("result", {}).get("agents", [])
    return agents if isinstance(agents, list) else []


def agent_info(target: str) -> dict | None:
    """One agent by pane id or agent name; None when that pane holds no agent."""
    data = run_json(["agent", "get", target])
    result = data.get("result", data) if isinstance(data, dict) else {}
    agent = result.get("agent") if isinstance(result, dict) else None
    return agent if isinstance(agent, dict) else None


def agent_rename(target: str, name: str) -> "tuple[bool, str]":
    """herdr agent rename (empty name clears it) -> (ok, error message).

    herdr owns the name: it validates the slug, enforces uniqueness among live
    agents, and drops the name when the agent exits. We surface its error text
    rather than second-guessing any of that.
    """
    args = ["agent", "rename", target] + ([name] if name else ["--clear"])
    try:
        proc = subprocess.run([herdr_bin(), *args], capture_output=True, text=True)
    except OSError as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, ""
    return False, error_message(proc.stderr, proc.stdout)


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


def apply_pane(pane: dict, rename_tabs: bool, title: str = None, name: str = None) -> None:
    """Report an agent pane's $task + $name, and (optionally) rename its tab.

    Idempotent: each token is only rewritten when its value actually changes, and
    the tab only when its label differs — so re-applying every tick is cheap.
    `title` is the precomputed $task and `name` the agent's herdr name (the daemon
    already has both); None recomputes/reads them from `pane`.
    """
    pane_id = pane.get("pane_id")
    if not pane_id:
        return
    tokens = pane.get("tokens") or {}
    if title is None:
        title = title_for_pane(pane)
    if name is None:
        name = pane.get("name") or ""
    if title != (tokens.get(TOKEN_TASK) or ""):
        report_token(pane_id, TOKEN_TASK, title)
    value = name_token(name)
    if value != (tokens.get(TOKEN_NAME) or ""):
        report_token(pane_id, TOKEN_NAME, value)
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
# status change (full pane inlined); created/closed/exited keep the set in sync.
# agent_status_changed is subsumed by pane.updated, and its subscription would
# demand a per-pane id anyway, so it is left out.
WATCH_SUBSCRIPTIONS = [
    {"type": "pane.updated"},
    {"type": "pane.created"},
    {"type": "pane.closed"},
    {"type": "pane.exited"},
]

# How long the daemon may sleep between authoritative `agent list` re-derives. It
# is a pure fallback for the two changes that emit no event — a Codex /rename
# (thread_name only) and a `herdr agent rename` typed into a shell — so it is
# deliberately slow; the popup and titles.refresh cover "right now".
REFRESH_INTERVAL = 60.0


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


def _refresh_pane(pane: dict, state: dict, rename_tabs: bool, name: str = None) -> None:
    """Re-derive one agent pane's signature and apply it if it changed. Shared by the
    event path and the refresh tick so the change-gate and caches behave identically
    no matter what woke us.

    Gated on (title, terminal_title, name): terminal_title catches Claude /rename &
    live summaries, and `title` catches an explicit rename that moves nothing else —
    notably a Codex /rename, which only rewrites session_index.jsonl and emits no
    event. `name` comes from an `agent list` snapshot when the caller has one (the
    tick), else from the last snapshot: pane.updated inlines a PaneInfo, which has
    no name field, so the push path must not clobber a known name with a blank.
    """
    pid = pane.get("pane_id")
    if not pid:
        return
    if name is None:
        name = state["names"].get(pid, "")
    else:
        state["names"][pid] = name
    agent, sid = resolve_session(pane)
    # a Codex /rename lives in the shared index, not the transcript, so its mtime is
    # part of the title's cache key.
    mtime = transcript_mtime(pane, state["path_cache"])
    meta = (mtime, codex_index_mtime()) if agent == "codex" else (mtime,)
    title = title_for_pane(pane, _cached_session_titles(agent, sid, meta, state))
    tt = pane.get("terminal_title_stripped") or ""
    sig = (title, tt, name)
    if sig != state["last"].get(pid):
        state["last"][pid] = sig
        apply_pane(pane, rename_tabs, title=title, name=name)
    state["panes"][pid] = pane


def _forget_pane(pid: str, state: dict) -> None:
    for book in ("last", "panes", "names"):
        state[book].pop(pid, None)


def _refresh_all(state: dict, rename_tabs: bool) -> None:
    """Re-derive every agent pane from an authoritative `agent list` snapshot.

    The only path that reads the herdr agent name, and the one that reconciles
    whatever changed while we were (re)connecting or between ticks. Panes that
    vanished from the snapshot are forgotten.
    """
    live = set()
    for agent in agent_list():
        pid = agent.get("pane_id")
        if not pid:
            continue
        live.add(pid)
        _refresh_pane(agent, state, rename_tabs, name=agent.get("name") or "")
    for pid in [p for p in state["panes"] if p not in live]:
        _forget_pane(pid, state)


def cmd_watch() -> int:
    """The event-subscription loop. Single-instance via flock; exits when its herdr
    goes away. Pushes off pane.updated instead of polling; a coarse timer re-derives
    from `agent list` to catch the changes that carry no event."""
    os.makedirs(state_dir(), exist_ok=True)
    lockfd = os.open(pidfile_path() + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another watcher already owns this instance
    with open(pidfile_path(), "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))

    interval = float(os.environ.get("TITLES_REFRESH_INTERVAL") or REFRESH_INTERVAL)
    debug = os.environ.get("TITLES_DEBUG") == "1"
    sockpath = os.environ.get("HERDR_SOCKET_PATH")
    rename_tabs = tab_rename_enabled()
    _log("watch start pid=%d push mode interval=%.1f rename_tabs=%s"
         % (os.getpid(), interval, rename_tabs))
    # pane_id -> signature / last full pane / last known agent name; session_id caches.
    state = {"last": {}, "panes": {}, "names": {},
             "path_cache": {}, "sess_cache": {}}

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
        try:
            _refresh_all(state, rename_tabs)
        except Exception as exc:
            _log("backfill error: %r" % (exc,))

        buf = b""
        # Deadline for the next refresh tick. It must fire on schedule even while
        # events stream in — a busy pane keeps select readable, so an idle-timeout
        # tick would starve and an event-less rename would never be re-checked.
        next_tick = time.time() + interval
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
                    # refresh tick: re-read agent names and transcripts / the Codex
                    # index as the fallback for changes that fire no event.
                    _refresh_all(state, rename_tabs)
                    next_tick = time.time() + interval
                    if debug:
                        _log("refresh tick panes=%d" % len(state["panes"]))
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
# rename popup
# ---------------------------------------------------------------------------


def _popup_target() -> str:
    """The pane the popup renames: whatever `rename-open` resolved and passed in.

    Never HERDR_PANE_ID — inside the popup that is the popup's own pane.
    """
    return (os.environ.get("TITLES_TARGET_PANE") or "").strip()


def cmd_rename_open() -> int:
    """Resolve the agent pane to rename and open the popup on it.

    Runs as the `titles.rename` action, i.e. in whatever context the keybinding
    fired from; the popup itself can only see its own pane once it takes focus, so
    the target is resolved here and handed over via TITLES_TARGET_PANE (the same
    pattern nav's favorites overlay uses for its tab). An empty target still opens
    the popup — it explains that there is no agent here, which beats a keypress
    that silently does nothing.
    """
    caller = (context_pane(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "")
              or (os.environ.get("HERDR_PANE_ID") or "")).strip()
    target = _popup_target() or resolve_target_pane(agent_list(), caller)
    args = [herdr_bin(), "plugin", "pane", "open", "--plugin", "titles",
            "--entrypoint", "rename-agent", "--focus",
            "--env", "TITLES_TARGET_PANE=%s" % target]
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


def _rename_apply(target: str, name: str) -> "tuple[bool, str]":
    """Rename and immediately mirror the result into the $name token.

    The daemon would pick this up on its next tick, but the whole point of the
    popup is that a rename you just typed is on screen when it closes.
    """
    ok, err = agent_rename(target, name)
    if not ok:
        return False, err
    agent = agent_info(target)
    if agent:
        apply_pane(agent, tab_rename_enabled(), name=agent.get("name") or "")
    return True, ""


def cmd_rename_ui() -> int:
    """The rename popup: edit the focused agent pane's herdr name."""
    try:
        import curses
    except ImportError:
        sys.stderr.write("Python curses is unavailable; cannot draw the rename popup.\n")
        return 1
    import locale
    locale.setlocale(locale.LC_ALL, "")
    target = _popup_target()
    agent = agent_info(target) if target else None
    curses.wrapper(_rename_loop, target, agent)
    return 0


def _rename_loop(stdscr, target: str, agent: dict) -> None:
    import curses
    try:
        curses.set_escdelay(25)
    except (AttributeError, curses.error):
        pass

    def line(row: int, text: str, attr=0) -> None:
        width = stdscr.getmaxyx()[1]
        try:
            stdscr.addstr(row, 0, text[: max(0, width - 1)], attr)
        except curses.error:
            pass

    if not agent:
        curses.curs_set(0)
        stdscr.erase()
        line(0, "Rename agent", curses.A_BOLD)
        line(2, "No agent in this pane.", curses.A_DIM)
        line(4, "any key to close", curses.A_DIM)
        stdscr.refresh()
        stdscr.getch()
        return

    def footer(text: str, attr=0) -> None:
        """Draw the hint/error under the input, wrapped into whatever rows are left.
        herdr's rename errors (a name collision names every candidate) are far longer
        than one popup row, so the tail must not be silently cut."""
        import textwrap
        rows, width = stdscr.getmaxyx()
        for i, chunk in enumerate(textwrap.wrap(text, max(8, width - 1))[: max(1, rows - 4)]):
            line(4 + i, chunk, attr)

    curses.curs_set(1)
    buf = agent.get("name") or ""
    was = buf
    status = ""
    while True:
        stdscr.erase()
        line(0, "Rename agent", curses.A_BOLD)
        line(1, "%s · %s%s" % (target, agent.get("agent") or "?",
                               (" · %s" % was) if was else ""), curses.A_DIM)
        line(3, "name> " + buf)
        if status:
            footer(status, curses.A_BOLD)
        elif buf and not is_valid_agent_name(buf):
            footer("! a-z 0-9 - _ only, must start with a letter (max 32)", curses.A_BOLD)
        else:
            footer("enter save · ctrl+d clear · esc cancel", curses.A_DIM)
        try:
            stdscr.move(3, min(6 + len(buf), stdscr.getmaxyx()[1] - 1))
        except curses.error:
            pass
        stdscr.refresh()

        try:
            ch = stdscr.get_wch()
        except (curses.error, KeyboardInterrupt):
            return
        status = ""
        if ch in ("\x1b", 27):                                  # esc -> cancel
            return
        if ch in ("\n", "\r", curses.KEY_ENTER):                # enter -> save
            if not buf:
                return                                          # nothing typed: cancel
            if not is_valid_agent_name(buf):
                status = "! invalid name"
                continue
            ok, err = _rename_apply(target, buf)
            if ok:
                return
            status = "! " + err
        elif ch == "\x04":                                      # ctrl+d -> clear
            ok, err = _rename_apply(target, "")
            if ok:
                return
            status = "! " + err
        elif ch == "\x15":                                      # ctrl+u -> clear line
            buf = ""
        elif ch in ("\x7f", "\b", curses.KEY_BACKSPACE):
            buf = buf[:-1]
        elif isinstance(ch, str) and ch.isprintable():
            buf += ch


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
    agent = agent_info(pane_id)
    if not agent:
        return 0
    apply_pane(agent, tab_rename_enabled())
    return 0


def cmd_report_all() -> int:
    rename_tabs = tab_rename_enabled()
    for agent in agent_list():
        apply_pane(agent, rename_tabs)
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
    if cmd == "rename-open":
        return cmd_rename_open()
    if cmd == "rename-ui":
        return cmd_rename_ui()
    sys.stderr.write(
        "usage: titles.py <ensure|watch|report|report-all|rename-open|rename-ui>\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
