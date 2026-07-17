#!/usr/bin/env python3
"""herdr-web connection panel: URLs (read-only), local/tunnel on-off toggles + pid,
and live-editable username/password.

The daemon reads credentials and [tunnel] enabled fresh, so panel changes take effect
without restarting it — the local URL stays fixed while the daemon stays up.
"""
import curses
import fcntl
import os
import subprocess
import sys

import authstate
import config

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


def _tunnel_state(local_on, tunnel_enabled, public_url, tpid):
    """(tunnel row text, public-URL display) from live state. While the tunnel is
    coming up — enabled but no URL published yet — show 'starting...'; once the URL
    is up that indicator disappears."""
    if not local_on or not tunnel_enabled:
        return "OFF", "(tunnel off)"
    if public_url:                       # URL published -> fully up
        return (("ON  (pid %s)" % tpid) if tpid else "ON"), public_url
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


def _draw(stdscr, local_url, public_disp, local_on, pid, tunnel_txt, fields, focus, msg):
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
    ]
    for i, (label, val) in enumerate(rows):
        marker = ">" if i == focus else " "
        stdscr.addnstr(base + i, 0, "%s %-16s: " % (marker, label), w - 1,
                       curses.A_BOLD if i == focus else 0)
        stdscr.addnstr(base + i, _VALUE_COL, val, max(1, w - _VALUE_COL - 1))
    stdscr.addnstr(base + 5, 0,
                   "Tab/↑↓ move   Space toggle   Ctrl-Y copy   Ctrl-G rand pw   Enter save creds   Esc close",
                   w - 1, curses.A_DIM)
    if msg:
        stdscr.addnstr(base + 7, 0, msg, w - 1, curses.A_BOLD)
    if focus in (2, 3):
        stdscr.move(base + focus, min(_VALUE_COL + fields[focus - 2].cur, w - 1))
    else:
        stdscr.move(base + focus, _VALUE_COL)
    stdscr.refresh()


def _ui(stdscr):
    curses.curs_set(1)
    stdscr.keypad(True)
    # keypad mode makes curses wait ESCDELAY (default ~1s) after a bare ESC to see if
    # it's an escape sequence (arrow keys start with ESC); shrink it so Esc closes fast.
    try:
        curses.set_escdelay(25)
    except (AttributeError, curses.error):
        pass
    stdscr.timeout(1000)  # getch returns -1 each second so we refresh live state
    config_dir = config.config_dir_default()
    state_dir = config.state_dir_default()
    rt = config.instance_state_dir(state_dir)
    pidfile = os.path.join(rt, "web.pid")
    username, password = config.current_creds(config_dir, rt)
    fields = [Field(username), Field(password)]  # 0=username, 1=password
    focus = 0  # 0=Local toggle, 1=Tunnel toggle, 2=Username, 3=Password
    msg = ""
    while True:
        pid = authstate.is_running(pidfile)
        local_on = pid is not None
        settings = config.load_settings(config_dir)
        tunnel_enabled = settings.tunnel_enabled
        port = (config.load_port(rt) if local_on else None) or settings.port
        local_url = "http://%s:%d" % (settings.bind, port)
        public_url = config.load_tunnel_url(rt) if local_on else None
        tpid = authstate.is_running(config.tunnel_pid_path(rt)) if local_on else None
        tunnel_txt, public_disp = _tunnel_state(local_on, tunnel_enabled, public_url, tpid)

        _draw(stdscr, local_url, public_disp, local_on, pid, tunnel_txt, fields, focus, msg)
        ch = stdscr.getch()
        if ch == -1:  # timeout tick: just refresh
            continue
        if ch == 27:  # Esc: close
            return
        if ch in (9, curses.KEY_DOWN):
            focus = (focus + 1) % 4
        elif ch == curses.KEY_UP:
            focus = (focus - 1) % 4
        elif ch == 25:  # Ctrl-Y: copy the focused row's text to the clipboard.
            # Handled before the focus-specific branches so it works on every row:
            # toggle rows copy their associated URL, cred rows copy the field value.
            if focus == 0:
                label, text = "local URL", local_url
            elif focus == 1:
                label, text = "public URL", (public_url or "")
            elif focus == 2:
                label, text = "username", fields[0].value
            else:
                label, text = "password", fields[1].value
            if not text:
                msg = "nothing to copy"
            elif _copy(text):
                msg = "copied %s to clipboard" % label
            else:
                msg = "copy failed"
        elif focus == 0:  # Local toggle
            if ch == ord(" "):
                # persist the preference so auto-start events respect it across
                # herdr restarts / panel reopens.
                config.set_local_enabled(rt, not local_on)
                _run_serve("stop" if local_on else "ensure")
                msg = "stopping local (stays off)..." if local_on else "starting local..."
        elif focus == 1:  # Tunnel toggle
            if ch == ord(" "):
                if not local_on:
                    msg = "start local first"
                else:
                    config.set_tunnel_enabled(config_dir, not tunnel_enabled)
                    msg = "turning tunnel off..." if tunnel_enabled else "turning tunnel on..."
        elif ch == 7:  # Ctrl-G: regenerate password (unsaved until Enter)
            fields[1] = Field(config.generate_password())
            msg = "generated new password — press Enter to save"
        elif ch in (10, 13, curses.KEY_ENTER):  # save creds
            user = fields[0].value.strip()
            pw = fields[1].value
            if not user or not pw:
                msg = "username and password must not be empty"
                continue
            config.set_username(config_dir, user)   # shared setting
            config.save_password(rt, pw)             # per-instance, pinned
            msg = "saved — applies to new connections"
        else:  # typing into username/password
            fields[focus - 2].handle(ch)
            msg = ""


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
