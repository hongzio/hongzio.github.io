#!/usr/bin/env python3
"""herdr-web connection panel: URLs (read-only), local/tunnel on-off toggles + pid,
live-editable username/password, and messenger notifications (server info pushed on
a new public URL).

The daemon reads credentials and [tunnel] enabled fresh, so panel changes take effect
without restarting it — the local URL stays fixed while the daemon stays up.

Screens form a stack: main -> notifications list -> messenger detail. Esc backs out
one level (or closes from main).
"""
import curses
import fcntl
import os
import subprocess
import sys
import threading

import authstate
import config
import notify

SERVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py")


class Field:
    """A minimal single-line text field with a cursor."""

    def __init__(self, value=""):
        self.value = value
        self.cur = len(value)

    def handle(self, ch):
        if ch == curses.KEY_LEFT:
            self.cur = max(0, self.cur - 1)
        elif ch == curses.KEY_RIGHT:
            self.cur = min(len(self.value), self.cur + 1)
        elif ch == curses.KEY_HOME:
            self.cur = 0
        elif ch == curses.KEY_END:
            self.cur = len(self.value)
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if self.cur > 0:
                self.value = self.value[:self.cur - 1] + self.value[self.cur:]
                self.cur -= 1
        elif ch == curses.KEY_DC:
            if self.cur < len(self.value):
                self.value = self.value[:self.cur] + self.value[self.cur + 1:]
        elif ch == 21:  # Ctrl-U: clear
            self.value = ""
            self.cur = 0
        elif 32 <= ch <= 126:
            self.value = self.value[:self.cur] + chr(ch) + self.value[self.cur:]
            self.cur += 1


_VALUE_COL = 20  # ">" + " " + "%-16s" label + ": "


def _tunnel_state(local_on, tunnel_enabled, public_url, tpid, status=None):
    """(tunnel row text, public-URL display) from live state. While the tunnel is
    coming up — enabled but no URL published yet — show 'starting...'; once the URL
    is up that indicator disappears. If the supervisor recorded a failure reason
    (e.g. cloudflared missing), show that instead of a stuck 'starting...'."""
    if not local_on or not tunnel_enabled:
        return "OFF", "(tunnel off)"
    if public_url:                       # URL published -> fully up
        return (("ON  (pid %s)" % tpid) if tpid else "ON"), public_url
    if status and not tpid:              # enabled but the tunnel couldn't start
        return "unavailable", "(%s)" % status
    return (("starting...  (pid %s)" % tpid) if tpid else "starting..."), "(coming up...)"


def _run_serve(cmd):
    """Fire `serve.py <cmd>` (ensure/stop) in the background; ignore its output."""
    try:
        subprocess.Popen([sys.executable, SERVE, cmd],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _copy(text):
    """Copy text to the macOS clipboard via pbcopy. Returns True on success.
    web is macOS-only (platforms=["macos"]), so pbcopy is always present."""
    try:
        p = subprocess.run(["pbcopy"], input=text.encode(), timeout=5)
        return p.returncode == 0
    except Exception:
        return False


def _row(stdscr, y, w, focus, i, label, val):
    """Draw one focusable 'label: value' row; returns nothing."""
    marker = ">" if i == focus else " "
    stdscr.addnstr(y, 0, "%s %-16s: " % (marker, label), w - 1,
                   curses.A_BOLD if i == focus else 0)
    stdscr.addnstr(y, _VALUE_COL, val, max(1, w - _VALUE_COL - 1))


# --- main screen ---------------------------------------------------------------

def _notif_summary(config_dir):
    """Short 'what's on' string for the main-screen Notifications row."""
    conf = notify.load(config_dir)
    on = [notify.TYPES[t]["label"] for t in notify.TYPE_IDS
          if conf["messengers"][t]["enabled"]]
    return ("%s  ▸" % ", ".join(on)) if on else "off  ▸"


def _main_screen(stdscr, ctx):
    """Returns the next screen: None to close, 'notify' to open the messenger list."""
    config_dir, rt, pidfile = ctx["config_dir"], ctx["rt"], ctx["pidfile"]
    fields = ctx["cred_fields"]          # [username, password] — persist across screens
    focus = ctx.get("main_focus", 0)     # 0=Local 1=Tunnel 2=User 3=Pass 4=Notifications
    msg = ""
    N = 5
    while True:
        pid = authstate.is_running(pidfile)
        local_on = pid is not None
        settings = config.load_settings(config_dir)
        tunnel_enabled = settings.tunnel_enabled
        port = (config.load_port(rt) if local_on else None) or settings.port
        local_url = "http://%s:%d" % (settings.bind, port)
        public_url = config.load_tunnel_url(rt) if local_on else None
        tpid = authstate.is_running(config.tunnel_pid_path(rt)) if local_on else None
        tunnel_status = config.load_tunnel_status(rt) if local_on else None
        tunnel_txt, public_disp = _tunnel_state(
            local_on, tunnel_enabled, public_url, tpid, tunnel_status)

        stdscr.erase()
        h, w = stdscr.getmaxyx()
        header = [
            ("herdr-web", curses.A_BOLD),
            ("", 0),
            ("  Local URL : %s" % local_url, 0),
            ("  Public URL: %s" % public_disp, 0),
            ("", 0),
        ]
        for y, (text, attr) in enumerate(header):
            stdscr.addnstr(y, 0, text, w - 1, attr)
        base = len(header)
        rows = [
            ("Local (serve.py)", ("ON  (pid %s)" % pid) if local_on else "OFF"),
            ("Tunnel", tunnel_txt),
            ("Username", fields[0].value),
            ("Password", fields[1].value),
            ("Notifications", _notif_summary(config_dir)),
        ]
        for i, (label, val) in enumerate(rows):
            _row(stdscr, base + i, w, focus, i, label, val)
        stdscr.addnstr(base + N + 1, 0,
                       "Tab/↑↓ move  Space toggle  Ctrl-Y copy  Ctrl-G rand pw  "
                       "Enter save/open  Esc close", w - 1, curses.A_DIM)
        if msg:
            stdscr.addnstr(base + N + 3, 0, msg, w - 1, curses.A_BOLD)
        if focus in (2, 3):
            stdscr.move(base + focus, min(_VALUE_COL + fields[focus - 2].cur, w - 1))
        else:
            stdscr.move(base + focus, _VALUE_COL)
        stdscr.refresh()

        ch = stdscr.getch()
        ctx["main_focus"] = focus
        if ch == -1:
            continue
        if ch == 27:  # Esc: close panel
            return None
        if ch in (9, curses.KEY_DOWN):
            focus = (focus + 1) % N
        elif ch == curses.KEY_UP:
            focus = (focus - 1) % N
        elif ch == 25:  # Ctrl-Y: copy the focused row's associated text
            if focus == 0:
                label, text = "local URL", local_url
            elif focus == 1:
                label, text = "public URL", (public_url or "")
            elif focus == 2:
                label, text = "username", fields[0].value
            elif focus == 3:
                label, text = "password", fields[1].value
            else:
                label, text = "", ""
            if not text:
                msg = "nothing to copy"
            elif _copy(text):
                msg = "copied %s to clipboard" % label
            else:
                msg = "copy failed"
        elif ch == 7:  # Ctrl-G: regenerate password (unsaved until Enter)
            fields[1] = Field(config.generate_password())
            msg = "generated new password — press Enter to save"
        elif ch == ord(" "):
            if focus == 0:  # Local toggle (persist so auto-start respects it)
                config.set_local_enabled(rt, not local_on)
                _run_serve("stop" if local_on else "ensure")
                msg = "stopping local (stays off)..." if local_on else "starting local..."
            elif focus == 1:  # Tunnel toggle
                if not local_on:
                    msg = "start local first"
                else:
                    config.set_tunnel_enabled(config_dir, not tunnel_enabled)
                    msg = "turning tunnel off..." if tunnel_enabled else "turning tunnel on..."
        elif ch in (10, 13, curses.KEY_ENTER):
            if focus == 4:  # open the notifications list
                return "notify"
            user = fields[0].value.strip()  # save creds
            pw = fields[1].value
            if not user or not pw:
                msg = "username and password must not be empty"
                continue
            config.set_username(config_dir, user)
            config.save_password(rt, pw)
            msg = "saved — applies to new connections"
        elif focus in (2, 3):  # typing into username/password
            fields[focus - 2].handle(ch)
            msg = ""


# --- notifications list screen -------------------------------------------------

def _notify_list_screen(stdscr, ctx):
    """Global 'include password' toggle + one row per messenger (Space toggles
    enabled, Enter opens its detail form). Returns 'main' or a messenger type id."""
    config_dir = ctx["config_dir"]
    conf = notify.load(config_dir)
    focus = 0  # 0 = include-password option, 1.. = messengers
    msg = ""
    N = 1 + len(notify.TYPE_IDS)
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(0, 0, "herdr-web — Notifications", w - 1, curses.A_BOLD)
        stdscr.addnstr(2, 0,
                       "Server info is pushed to enabled messengers when a new public "
                       "URL is created.", w - 1, curses.A_DIM)
        base = 4
        _row(stdscr, base, w, focus, 0, "Include password",
             "ON" if conf["options"]["include_password"] else "OFF")
        for j, tid in enumerate(notify.TYPE_IDS):
            state = "[ON]" if conf["messengers"][tid]["enabled"] else "[OFF]"
            _row(stdscr, base + 1 + j, w, focus, 1 + j,
                 notify.TYPES[tid]["label"], "%s  ▸" % state)
        stdscr.addnstr(base + N + 1, 0,
                       "Tab/↑↓ move  Space toggle  Enter configure  Esc back",
                       w - 1, curses.A_DIM)
        if msg:
            stdscr.addnstr(base + N + 3, 0, msg, w - 1, curses.A_BOLD)
        stdscr.move(base + focus, _VALUE_COL)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch == -1:
            continue
        if ch == 27:  # Esc: back to main
            return "main"
        if ch in (9, curses.KEY_DOWN):
            focus = (focus + 1) % N
        elif ch == curses.KEY_UP:
            focus = (focus - 1) % N
        elif ch == ord(" "):
            if focus == 0:
                conf["options"]["include_password"] = not conf["options"]["include_password"]
                notify.save(config_dir, conf)
                msg = "password %s in messages" % (
                    "included" if conf["options"]["include_password"] else "excluded")
            else:
                tid = notify.TYPE_IDS[focus - 1]
                conf["messengers"][tid]["enabled"] = not conf["messengers"][tid]["enabled"]
                notify.save(config_dir, conf)
                msg = "%s %s" % (notify.TYPES[tid]["label"],
                                 "enabled" if conf["messengers"][tid]["enabled"] else "disabled")
        elif ch in (10, 13, curses.KEY_ENTER):
            if focus >= 1:
                return notify.TYPE_IDS[focus - 1]


# --- messenger detail screen ---------------------------------------------------

def _detail_rows(spec):
    """Build the focusable row model for a messenger's detail form."""
    rows = [("toggle", "Enabled")]
    for key, label, secret in spec["fields"]:
        rows.append(("field", key, label, secret))
    if spec.get("fetch"):
        rows.append(("fetch", "Fetch %s" % spec.get("fetch_label", "id")))
    rows.append(("test", "Test message"))
    return rows


def _test_text(ctx):
    """Server-info preview for a test send: real username, password iff the toggle
    is on, and the live public URL when there is one (else a placeholder)."""
    config_dir, rt = ctx["config_dir"], ctx["rt"]
    conf = notify.load(config_dir)
    username = config.load_settings(config_dir).username
    pw = config.load_or_create_password(rt) if conf["options"]["include_password"] else None
    url = config.load_tunnel_url(rt) or "https://example.trycloudflare.com"
    return "\U0001F9EA test\n" + notify.render_message(url, username, pw)


def _notify_detail_screen(stdscr, ctx, type_id):
    """Edit one messenger: enabled toggle, transport fields, Fetch (getUpdates) and
    Test actions. Fetch/Test run off-thread so the UI stays live. Returns 'notify'."""
    config_dir = ctx["config_dir"]
    spec = notify.TYPES[type_id]
    conf = notify.load(config_dir)
    m = conf["messengers"][type_id]
    enabled = m["enabled"]
    order = [key for key, _l, _s in spec["fields"]]
    fields = {key: Field(m[key]) for key in order}
    rows = _detail_rows(spec)
    focus = 0
    N = len(rows)
    async_state = {"busy": False, "msg": "", "fetched": None}

    def cur_cfg():
        return {key: fields[key].value for key in order}

    def persist(status=None):
        conf["messengers"][type_id] = dict(cur_cfg(), enabled=enabled)
        notify.save(config_dir, conf)
        return status

    while True:
        # apply an async fetch result (thread can't touch curses/fields safely)
        if async_state["fetched"] is not None:
            for key, val in async_state["fetched"].items():
                if key in fields:
                    fields[key] = Field(val)
            async_state["fetched"] = None

        stdscr.erase()
        h, w = stdscr.getmaxyx()
        stdscr.addnstr(0, 0, "herdr-web — %s" % spec["label"], w - 1, curses.A_BOLD)
        base = 2
        field_line = {}
        for i, row in enumerate(rows):
            y = base + i
            kind = row[0]
            if kind == "toggle":
                _row(stdscr, y, w, focus, i, "Enabled", "ON" if enabled else "OFF")
            elif kind == "field":
                _, key, label, secret = row
                f = fields[key]
                val = f.value if (focus == i or not secret) else ("•" * len(f.value))
                _row(stdscr, y, w, focus, i, label, val)
                field_line[i] = (y, f)
            else:  # fetch / test action row: full-width line, no value column, so
                # a long label ("Fetch chat/topic id") isn't clipped by the value.
                marker = ">" if focus == i else " "
                stdscr.addnstr(y, 0, "%s %s  (enter)" % (marker, row[1]), w - 1,
                               curses.A_BOLD if focus == i else 0)
        hint = ("Tab/↑↓ move  Space toggle  Enter save/run  Esc back"
                if not async_state["busy"] else "working…")
        stdscr.addnstr(base + N + 1, 0, hint, w - 1, curses.A_DIM)
        line = async_state["msg"]
        if line:
            stdscr.addnstr(base + N + 3, 0, line, w - 1, curses.A_BOLD)
        if focus in field_line:
            y, f = field_line[focus]
            stdscr.move(y, min(_VALUE_COL + f.cur, w - 1))
        else:
            stdscr.move(base + focus, _VALUE_COL)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch == -1:
            continue
        if ch == 27:  # Esc: save + back to list
            persist()
            return "notify"
        if ch in (9, curses.KEY_DOWN):
            focus = (focus + 1) % N
            continue
        if ch == curses.KEY_UP:
            focus = (focus - 1) % N
            continue
        kind = rows[focus][0]
        if ch == ord(" ") and kind == "toggle":
            enabled = not enabled
            persist()
            async_state["msg"] = "enabled" if enabled else "disabled"
        elif ch in (10, 13, curses.KEY_ENTER):
            if kind == "field":
                persist()
                async_state["msg"] = "saved"
            elif kind == "fetch":
                if not async_state["busy"]:
                    _spawn_fetch(async_state, type_id, cur_cfg())
            elif kind == "test":
                persist()
                if not async_state["busy"]:
                    _spawn_test(async_state, type_id, cur_cfg(), _test_text(ctx))
        elif kind == "field":
            fields[rows[focus][1]].handle(ch)
            async_state["msg"] = ""


def _spawn_test(state, type_id, cfg, text):
    state["busy"] = True
    state["msg"] = "sending…"

    def go():
        try:
            ok, m = notify.send(type_id, cfg, text)
        except Exception as e:
            ok, m = False, str(e)
        state["msg"] = ("sent ✓" if ok else "error: %s" % m)
        state["busy"] = False
    threading.Thread(target=go, daemon=True).start()


def _spawn_fetch(state, type_id, cfg):
    state["busy"] = True
    state["msg"] = "fetching…"

    def go():
        try:
            ok, result, label = notify.fetch(type_id, cfg)
        except Exception as e:
            ok, result, label = False, str(e), ""
        if ok:
            state["fetched"] = result  # {field: value} applied on the main thread
            found = ", ".join("%s %s" % (k, v) for k, v in result.items())
            state["msg"] = "%s%s" % (found, (" (%s)" % label if label else ""))
        else:
            state["msg"] = "error: %s" % result
        state["busy"] = False
    threading.Thread(target=go, daemon=True).start()


# --- screen dispatcher ---------------------------------------------------------

def _ui(stdscr):
    curses.curs_set(1)
    stdscr.keypad(True)
    # keypad mode makes curses wait ESCDELAY (default ~1s) after a bare ESC to see if
    # it's an escape sequence (arrow keys start with ESC); shrink it so Esc backs out fast.
    try:
        curses.set_escdelay(25)
    except (AttributeError, curses.error):
        pass
    stdscr.timeout(1000)  # getch returns -1 each second so we refresh live state
    config_dir = config.config_dir_default()
    state_dir = config.state_dir_default()
    rt = config.instance_state_dir(state_dir)
    username, password = config.current_creds(config_dir, rt)
    ctx = {
        "config_dir": config_dir,
        "rt": rt,
        "pidfile": os.path.join(rt, "web.pid"),
        "cred_fields": [Field(username), Field(password)],
    }
    screen = "main"
    while screen is not None:
        if screen == "main":
            screen = _main_screen(stdscr, ctx)
        elif screen == "notify":
            screen = _notify_list_screen(stdscr, ctx)
        elif screen in notify.TYPES:
            screen = _notify_detail_screen(stdscr, ctx, screen)
        else:
            screen = None


def _focus_existing(rt):
    """A panel is already open — focus its pane instead of opening a duplicate."""
    try:
        with open(os.path.join(rt, "panel.pane"), encoding="utf-8") as fh:
            pane = fh.read().strip()
    except OSError:
        pane = ""
    if pane:
        herdr = os.environ.get("HERDR_BIN_PATH") or "herdr"
        try:
            subprocess.run([herdr, "plugin", "pane", "focus", pane],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass


def main(argv):
    if not (len(argv) > 1 and argv[1] == "ui"):
        sys.stderr.write("usage: panel.py ui\n")
        sys.exit(2)
    rt = config.instance_state_dir(config.state_dir_default())
    os.makedirs(rt, exist_ok=True)
    # single-instance: if a panel is already open for this herdr instance, focus it
    # and exit so re-invoking web.panel doesn't stack duplicate overlays.
    lockfd = os.open(os.path.join(rt, "panel.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _focus_existing(rt)
        os.close(lockfd)
        return
    pane_file = os.path.join(rt, "panel.pane")
    try:
        with open(pane_file, "w", encoding="utf-8") as fh:
            fh.write(os.environ.get("HERDR_PANE_ID", ""))  # this overlay's pane id
        curses.wrapper(_ui)
    finally:
        try:
            os.remove(pane_file)
        except OSError:
            pass
        fcntl.flock(lockfd, fcntl.LOCK_UN)
        os.close(lockfd)


if __name__ == "__main__":
    main(sys.argv)
