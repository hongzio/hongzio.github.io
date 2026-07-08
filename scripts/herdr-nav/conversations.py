#!/usr/bin/env python3
"""herdr conversations picker.

Lists Claude/Codex conversations, lets you pick one with fzf, and restores it:
  1. already active in an agent -> focus that pane
  2. a space with the same root cwd exists -> new tab in that space
  3. no matching space -> new space (+ tab) at that cwd

Subcommands:
  list             stream conversation rows (recency-desc) for fzf
  preview <token>  render the tail of a conversation
  open <token>     restore the conversation (dispatch)
  ui               run the fzf picker (used inside the overlay pane)

The pure functions (parsing, dispatch decision, matching) are kept free of I/O
side effects so they can be unit-tested; the `herdr` CLI and filesystem are the
only external dependencies and are reached through thin wrappers.
"""
from __future__ import annotations

import base64
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field

HOME = os.path.expanduser("~")
CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
CODEX_SESSIONS = os.path.join(HOME, ".codex", "sessions")
CODEX_INDEX = os.path.join(HOME, ".codex", "session_index.jsonl")
HERDR_SESSION_JSON = os.path.join(HOME, ".config", "herdr", "session.json")

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
LABEL_MAX = 72
TAB_NAME_MAX = 30
PREVIEW_MESSAGES = 20

# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------


@dataclass
class Conversation:
    agent: str          # "claude" | "codex"
    session_id: str
    path: str           # transcript / rollout file
    mtime: float
    cwd: str = ""       # working dir (may be filled lazily)
    label: str = ""     # display label: title or first user message / thread name
    title: str = ""     # name-like title only (custom/ai title, thread_name); "" if none
    name: str = ""      # short tab name, carried through the token to open time


# ---------------------------------------------------------------------------
# token codec (opaque field passed through fzf)
# ---------------------------------------------------------------------------


def encode_token(conv: Conversation) -> str:
    payload = {"a": conv.agent, "s": conv.session_id, "p": conv.path,
               "c": conv.cwd, "n": tab_name(conv)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_token(token: str) -> Conversation:
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    d = json.loads(raw)
    return Conversation(agent=d["a"], session_id=d["s"], path=d["p"], mtime=0.0,
                        cwd=d.get("c", ""), name=d.get("n", ""))


# ---------------------------------------------------------------------------
# text helpers (pure)
# ---------------------------------------------------------------------------


def clean_label(text: str) -> str:
    text = " ".join(str(text).split())
    if len(text) > LABEL_MAX:
        text = text[: LABEL_MAX - 1] + "…"
    return text


def tab_name(conv: "Conversation") -> str:
    """Short, name-like label for a restored conversation's tab.

    Prefer an explicit title (Claude custom/ai title, Codex thread_name); fall
    back to the display label (first user message), then the cwd basename. Kept
    short so it fits herdr's tab sidebar rather than the 72-char picker label.
    """
    base = " ".join((conv.title or conv.label or "").split())
    if not base or base in ("(claude)", "(codex)"):
        base = os.path.basename(conv.cwd.rstrip("/")) if conv.cwd else base
    if len(base) > TAB_NAME_MAX:
        base = base[: TAB_NAME_MAX - 1] + "…"
    return base


SYNTHETIC_PREFIXES = (
    "<local-command", "<command-message>", "<command-name>", "<command-args>",
    "Caveat:", "<bash-", "<system-reminder>", "<user-memory", "<user-prompt-submit",
)


def is_synthetic_user_text(text: str) -> bool:
    """True for harness-injected user records (slash-command caveats, reminders)."""
    t = text.lstrip()
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


def rel_time(ts: float, now: float | None = None) -> str:
    now = time.time() if now is None else now
    d = max(0, int(now - ts))
    if d < 60:
        return "방금"          # just now
    if d < 3600:
        return f"{d // 60}분"       # Nm
    if d < 86400:
        return f"{d // 3600}시간"  # Nh
    if d < 172800:
        return "어제"          # yesterday
    if d < 604800:
        return f"{d // 86400}일"    # Nd
    return f"{d // 604800}주"       # Nw


# ---------------------------------------------------------------------------
# claude source
# ---------------------------------------------------------------------------


def claude_candidates() -> list[Conversation]:
    out = []
    for path in glob.glob(os.path.join(CLAUDE_PROJECTS, "*", "*.jsonl")):
        stem = os.path.splitext(os.path.basename(path))[0]
        if not UUID_RE.fullmatch(stem):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        out.append(Conversation(agent="claude", session_id=stem, path=path, mtime=mtime))
    return out


def claude_enrich(conv: Conversation) -> None:
    """Fill cwd + label from the transcript.

    Label priority: /rename `custom-title` > `ai-title` > first user message.
    Title records carry no timestamp and can be rewritten, so the *last* one
    wins and the whole file is scanned — but JSON is only parsed for lines that
    a cheap substring pre-filter marks as relevant.
    """
    cwd = custom_title = ai_title = first_user = ""
    try:
        with open(conv.path, encoding="utf-8") as fh:
            for line in fh:
                if '-title"' not in line and '"cwd"' not in line and '"type":"user"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = rec.get("type")
                if t == "custom-title" and isinstance(rec.get("customTitle"), str):
                    custom_title = rec["customTitle"]
                elif t == "ai-title" and isinstance(rec.get("aiTitle"), str):
                    ai_title = rec["aiTitle"]
                elif not cwd and isinstance(rec.get("cwd"), str):
                    cwd = rec["cwd"]
                if not first_user and t == "user":
                    txt = message_text((rec.get("message") or {}).get("content"))
                    if txt.strip() and not is_synthetic_user_text(txt):
                        first_user = txt
    except OSError:
        pass
    conv.cwd = cwd
    conv.title = custom_title.strip() or ai_title.strip()
    conv.label = clean_label(conv.title or first_user or "(claude)")


def claude_messages(path: str) -> list[tuple[str, str]]:
    msgs = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = rec.get("type")
                if role in ("user", "assistant"):
                    txt = message_text((rec.get("message") or {}).get("content")).strip()
                    if txt:
                        msgs.append((role, txt))
    except OSError:
        pass
    return msgs


# ---------------------------------------------------------------------------
# codex source
# ---------------------------------------------------------------------------


def codex_index() -> dict[str, dict]:
    idx = {}
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
                if isinstance(rec.get("id"), str):
                    idx[rec["id"]] = rec
    except OSError:
        pass
    return idx


def codex_candidates() -> list[Conversation]:
    out = []
    for path in glob.glob(os.path.join(CODEX_SESSIONS, "**", "rollout-*.jsonl"), recursive=True):
        m = UUID_RE.search(os.path.basename(path))
        if not m:
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        out.append(Conversation(agent="codex", session_id=m.group(0), path=path, mtime=mtime))
    return out


def codex_session_meta(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("type") == "session_meta":
                    return rec.get("payload") or {}
                return rec.get("payload") or {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def codex_first_user(path: str) -> str:
    """First non-synthetic user message in a rollout (fallback label)."""
    try:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh):
                if lineno > 400:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "response_item":
                    continue
                payload = rec.get("payload") or {}
                if payload.get("role") == "user":
                    txt = message_text(payload.get("content"))
                    if txt.strip() and not is_synthetic_user_text(txt):
                        return txt
    except OSError:
        pass
    return ""


def codex_enrich(conv: Conversation, index: dict[str, dict]) -> None:
    meta = codex_session_meta(conv.path)
    conv.cwd = meta.get("cwd", "") if isinstance(meta.get("cwd"), str) else ""
    entry = index.get(conv.session_id)
    thread_name = ""
    if entry and isinstance(entry.get("thread_name"), str):
        thread_name = entry["thread_name"].strip()
    conv.title = thread_name
    label = thread_name or codex_first_user(conv.path)
    conv.label = clean_label(label) if label.strip() else "(codex)"


def codex_messages(path: str) -> list[tuple[str, str]]:
    msgs = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "response_item":
                    continue
                payload = rec.get("payload") or {}
                role = payload.get("role")
                if role in ("user", "assistant"):
                    txt = message_text(payload.get("content")).strip()
                    if txt:
                        msgs.append((role, txt))
    except OSError:
        pass
    return msgs


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


def active_session_map() -> dict[str, str]:
    """session_id -> pane_id for agents herdr currently tracks."""
    try:
        data = herdr("pane", "list")
    except (RuntimeError, json.JSONDecodeError):
        return {}
    result = {}
    for pane in data.get("result", {}).get("panes", []):
        sess = pane.get("agent_session") or {}
        val = sess.get("value")
        if val:
            result[val] = pane["pane_id"]
    return result


def space_cwd_map() -> dict[str, str]:
    """realpath(root cwd) -> workspace_id, from herdr session.json identity_cwd."""
    result = {}
    try:
        with open(HERDR_SESSION_JSON, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        data = None
    if data is not None:
        for wid, cwd in _walk_identity_cwd(data):
            if cwd:
                result[os.path.realpath(os.path.expanduser(cwd))] = wid
    if result:
        return result
    # fallback: group live panes by workspace (less reliable — pane cwd drifts)
    try:
        panes = herdr("pane", "list").get("result", {}).get("panes", [])
    except (RuntimeError, json.JSONDecodeError):
        panes = []
    for pane in panes:
        cwd = pane.get("cwd")
        if cwd:
            result.setdefault(os.path.realpath(cwd), pane["workspace_id"])
    return result


def _walk_identity_cwd(obj) -> list[tuple[str, str]]:
    out = []
    if isinstance(obj, dict):
        if "id" in obj and "identity_cwd" in obj:
            out.append((obj["id"], obj.get("identity_cwd")))
        for v in obj.values():
            out += _walk_identity_cwd(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _walk_identity_cwd(v)
    return out


# ---------------------------------------------------------------------------
# dispatch (decision is pure; effects are separate)
# ---------------------------------------------------------------------------


def resume_command(agent: str, session_id: str) -> str:
    if agent == "claude":
        return f"claude --resume {shlex.quote(session_id)}"
    if agent == "codex":
        return f"codex resume {shlex.quote(session_id)}"
    raise ValueError(f"unknown agent: {agent}")


def decide_action(conv: Conversation, active: dict[str, str], spaces: dict[str, str]) -> dict:
    """Return {kind, ...} describing what to do. Pure — no side effects."""
    if conv.session_id in active:
        return {"kind": "focus", "pane_id": active[conv.session_id]}
    target = os.path.realpath(os.path.expanduser(conv.cwd)) if conv.cwd else ""
    if target and target in spaces:
        return {"kind": "new_tab", "workspace_id": spaces[target], "cwd": target}
    return {"kind": "new_space", "cwd": target or os.path.expanduser(conv.cwd)}


def perform_action(action: dict, conv: Conversation) -> None:
    kind = action["kind"]
    if kind == "focus":
        herdr("agent", "focus", action["pane_id"])
        return
    cmd = resume_command(conv.agent, conv.session_id)
    if kind == "new_tab":
        args = ["tab", "create", "--workspace", action["workspace_id"],
                "--cwd", action["cwd"], "--no-focus"]
        if conv.name:
            args += ["--label", conv.name]
        res = herdr(*args)
        pane = res["result"]["root_pane"]["pane_id"]
        tab = res["result"]["tab"]["tab_id"]
        _run_when_ready(pane, cmd)
        herdr("tab", "focus", tab)
    elif kind == "new_space":
        label = os.path.basename(action["cwd"].rstrip("/")) or action["cwd"]
        res = herdr("workspace", "create", "--cwd", action["cwd"],
                    "--label", label, "--no-focus")
        result = res["result"]
        pane = (result.get("root_pane") or {}).get("pane_id")
        wid = (result.get("workspace") or {}).get("workspace_id") or result.get("workspace_id")
        if not pane:  # fall back to the workspace's active tab pane
            pane = _first_pane_of_workspace(wid)
        _run_when_ready(pane, cmd)
        # the space carries the cwd basename; name its tab after the conversation
        if conv.name and wid:
            tab = _first_tab_of_workspace(wid)
            if tab:
                try:
                    herdr("tab", "rename", tab, conv.name)
                except RuntimeError:
                    pass
        if wid:
            herdr("workspace", "focus", wid)


def _first_pane_of_workspace(wid: str) -> str | None:
    try:
        panes = herdr("pane", "list", "--workspace", wid).get("result", {}).get("panes", [])
    except (RuntimeError, json.JSONDecodeError):
        return None
    return panes[0]["pane_id"] if panes else None


def _first_tab_of_workspace(wid: str) -> str | None:
    try:
        tabs = herdr("tab", "list", "--workspace", wid).get("result", {}).get("tabs", [])
    except (RuntimeError, json.JSONDecodeError):
        return None
    return tabs[0]["tab_id"] if tabs else None


def _run_when_ready(pane_id: str | None, command: str, attempts: int = 20) -> None:
    """`pane run` after the shell settles; retry briefly to avoid the launch race."""
    if not pane_id:
        raise RuntimeError("no target pane to launch into")
    last = None
    for _ in range(attempts):
        try:
            herdr("pane", "run", pane_id, command)
            return
        except RuntimeError as exc:
            last = exc
            time.sleep(0.1)
    raise RuntimeError(f"pane run failed after retries: {last}")


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------

C_RESET = "\033[0m"
C_ACTIVE = "\033[32m"   # green dot for active
C_DIM = "\033[90m"
C_AGENT = "\033[36m"


def available_sources() -> list[tuple[str, object]]:
    """(name, candidate_fn) for each source whose data directory exists.

    A missing source is skipped; only when *every* source is absent is the
    picker empty by construction (callers treat that as an error).
    """
    registry = [
        ("claude", CLAUDE_PROJECTS, claude_candidates),
        ("codex", CODEX_SESSIONS, codex_candidates),
    ]
    return [(name, fn) for name, path, fn in registry if os.path.isdir(path)]


def iter_conversations():
    """Yield enriched conversations from every available source, newest first."""
    cands = []
    for _name, candidate_fn in available_sources():
        cands += candidate_fn()
    cands.sort(key=lambda c: c.mtime, reverse=True)
    index = None
    for conv in cands:
        if conv.agent == "claude":
            claude_enrich(conv)
        else:
            if index is None:
                index = codex_index()
            codex_enrich(conv, index)
        yield conv


def row_cells(conv: Conversation, active: dict, now: float) -> tuple:
    return (
        conv.session_id in active,
        conv.agent,
        rel_time(conv.mtime, now),
        os.path.basename(conv.cwd.rstrip("/")) if conv.cwd else "?",
        conv.label,
    )


def plain_row(cells: tuple) -> str:
    is_active, agent, t, space, label = cells
    return f"{'●' if is_active else '○'} {agent:<6} {t:>4}  {space:<22} {label}"


def filter_rows(rows: list, query: str) -> list:
    """Exact (case-insensitive substring) match against each row's search key."""
    if not query:
        return rows
    q = query.lower()
    return [r for r in rows if q in r[0]]


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


def cmd_list() -> int:
    active = active_session_map()
    now = time.time()
    for conv in iter_conversations():
        is_active, agent, t, space, label = row_cells(conv, active, now)
        dot = f"{C_ACTIVE}●{C_RESET}" if is_active else f"{C_DIM}○{C_RESET}"
        display = (f"{dot} {C_AGENT}{agent:<6}{C_RESET} {t:>4}  "
                   f"{C_DIM}{space:<22}{C_RESET} {label}")
        try:
            sys.stdout.write(f"{display}\t{encode_token(conv)}\n")
            sys.stdout.flush()
        except BrokenPipeError:
            return 0
    return 0


def cmd_preview(token: str) -> int:
    conv = decode_token(token)
    msgs = claude_messages(conv.path) if conv.agent == "claude" else codex_messages(conv.path)
    header = f"{conv.agent}  {conv.cwd or '?'}\n{conv.session_id}\n" + ("─" * 40)
    print(header)
    for role, txt in msgs[-PREVIEW_MESSAGES:]:
        tag = "you" if role == "user" else "ai "
        txt = " ".join(txt.split())
        print(f"\n[{tag}] {txt[:500]}")
    return 0


def _fail(msg: str) -> int:
    """Report an error and, in an interactive overlay, pause so it stays visible."""
    sys.stderr.write(msg + "\n")
    if sys.stdin.isatty():
        try:
            input("(enter to close) ")
        except (EOFError, KeyboardInterrupt):
            pass
    return 1


def cmd_open(token: str) -> int:
    conv = decode_token(token)
    if not conv.cwd:  # token missing cwd (e.g. parse failed at list time) -> recover
        if conv.agent == "claude":
            claude_enrich(conv)
        else:
            codex_enrich(conv, codex_index())
        conv.name = tab_name(conv)  # recompute now that title/label are filled
    action = decide_action(conv, active_session_map(), space_cwd_map())
    if action["kind"] == "focus":
        try:
            perform_action(action, conv)
        except RuntimeError as exc:
            return _fail(f"could not focus the agent: {exc}")
        return 0
    # restore paths need a real directory and the agent's CLI on PATH
    if not action.get("cwd"):
        return _fail("cannot restore: conversation has no working directory")
    if not os.path.isdir(action["cwd"]):
        return _fail(f"cannot restore: directory does not exist: {action['cwd']}")
    if shutil.which(conv.agent) is None:
        return _fail(f"cannot restore: '{conv.agent}' CLI not found on PATH")
    try:
        perform_action(action, conv)
    except (RuntimeError, ValueError) as exc:
        return _fail(f"restore failed: {exc}")
    return 0


def cmd_ui() -> int:
    if not available_sources():
        return _fail("no Claude or Codex conversations found.\n"
                     f"  looked in: {CLAUDE_PROJECTS}\n"
                     f"             {CODEX_SESSIONS}")
    # CONV_PICKER_MODE (from the bound plugin action): auto | fzf | native
    mode = (os.environ.get("CONV_PICKER_MODE") or "auto").strip().lower()
    have_fzf = shutil.which("fzf") is not None
    if mode == "native":
        return _run_python_picker()
    if mode == "fzf":
        if not have_fzf:
            return _fail("CONV_PICKER_MODE=fzf but fzf is not installed.")
        return _run_fzf()
    return _run_fzf() if have_fzf else _run_python_picker()  # auto


def _run_fzf() -> int:
    self_path = os.path.abspath(__file__)
    py = sys.executable or "python3"
    quoted = f"{shlex.quote(py)} {shlex.quote(self_path)}"
    fzf = [
        "fzf", "--ansi", "--no-sort", "--delimiter", "\t", "--with-nth", "1",
        "--prompt", "conversations> ",
        "--preview", f"{quoted} preview {{2}}",
        "--preview-window", "right:50%:wrap",
        "--bind", f"enter:become({quoted} open {{2}})",
        "--header", "● active  ○ inactive   enter: restore",
    ]
    producer = subprocess.Popen([py, self_path, "list"], stdout=subprocess.PIPE)
    try:
        proc = subprocess.Popen(fzf, stdin=producer.stdout)
    except FileNotFoundError:              # fzf vanished between check and exec
        producer.terminate()
        return _run_python_picker()
    if producer.stdout:
        producer.stdout.close()
    return proc.wait()


def _collect_rows() -> list:
    """(search_key, display, token, is_active) for every conversation."""
    active = active_session_map()
    now = time.time()
    rows = []
    for conv in iter_conversations():
        cells = row_cells(conv, active, now)
        search = f"{cells[1]} {cells[3]} {cells[4]}".lower()
        rows.append((search, plain_row(cells), encode_token(conv), cells[0]))
    return rows


def _run_python_picker() -> int:
    """Fallback picker when fzf is missing: curses list + exact substring filter."""
    try:
        import curses  # noqa: F401
    except ImportError:
        return _fail("fzf not found and Python curses is unavailable.")
    import locale
    locale.setlocale(locale.LC_ALL, "")
    rows = _collect_rows()
    if not rows:
        return _fail("no conversations to pick.")
    token = curses.wrapper(_picker_loop, rows)
    if token is None:
        return 0  # cancelled
    return cmd_open(token)


def _picker_loop(stdscr, rows):
    import curses
    try:
        curses.set_escdelay(25)   # make a lone ESC responsive
    except (AttributeError, curses.error):
        pass
    curses.curs_set(1)
    stdscr.keypad(True)
    query, sel, top = "", 0, 0
    while True:
        shown = filter_rows(rows, query)
        sel = min(sel, max(0, len(shown) - 1))
        height, width = stdscr.getmaxyx()
        list_h = max(1, height - 1)
        if sel < top:
            top = sel
        elif sel >= top + list_h:
            top = sel - list_h + 1
        stdscr.erase()
        counter = f" [{len(shown)}/{len(rows)}]"
        try:
            stdscr.addstr(0, 0, _fit_width("› " + query, width - _disp_width(counter) - 1))
            stdscr.addstr(0, max(0, width - _disp_width(counter) - 1), counter, curses.A_DIM)
        except curses.error:
            pass
        for i in range(list_h):
            idx = top + i
            if idx >= len(shown):
                break
            marker = "▌ " if idx == sel else "  "
            attr = curses.A_REVERSE if idx == sel else curses.A_NORMAL
            try:
                stdscr.addstr(1 + i, 0, _fit_width(marker + shown[idx][1], width - 1), attr)
            except curses.error:
                pass
        try:
            stdscr.move(0, min(_disp_width("› " + query), width - 1))
        except curses.error:
            pass
        stdscr.refresh()
        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue
        # get_wch() returns int for special keys, str for text — handle both.
        if ch in (27, "\x1b", 3, "\x03"):                 # ESC / Ctrl-C -> cancel
            return None
        if ch in ("\n", "\r", curses.KEY_ENTER):          # Enter -> select
            return shown[sel][2] if shown else None
        if ch in (curses.KEY_UP, "\x10"):                 # up / Ctrl-P
            sel = max(0, sel - 1)
        elif ch in (curses.KEY_DOWN, "\x0e"):             # down / Ctrl-N
            sel = min(len(shown) - 1, sel + 1) if shown else 0
        elif ch in (curses.KEY_BACKSPACE, "\x7f", "\b", "\x08"):
            query, sel = query[:-1], 0
        elif isinstance(ch, str) and ch.isprintable():
            query, sel = query + ch, 0


USAGE = "usage: conversations.py {list|preview <token>|open <token>|ui}"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(USAGE + "\n")
        return 2
    cmd = argv[1]
    if cmd == "list":
        return cmd_list()
    if cmd == "ui":
        return cmd_ui()
    if cmd == "preview":
        return cmd_preview(argv[2]) if len(argv) > 2 else 2
    if cmd == "open":
        return cmd_open(argv[2]) if len(argv) > 2 else 2
    sys.stderr.write(USAGE + "\n")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:
        sys.exit(0)
