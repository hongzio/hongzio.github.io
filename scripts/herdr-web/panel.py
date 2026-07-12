#!/usr/bin/env python3
"""herdr-web connection panel: show URLs (read-only) + edit username/password live.

The daemon reads credentials fresh on each request (see serve.py), so edits saved
here apply to new connections immediately, without a restart — the URL stays fixed.
"""
import curses
import sys

import config


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


_VALUE_COL = 13  # ">" + " " + "%-9s" label + ": "


def _draw(stdscr, local_url, public_url, fields, focus, msg):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    header = [
        ("herdr-web", curses.A_BOLD),
        ("", 0),
        ("  Local URL : %s" % local_url, 0),
        ("  Public URL: %s" % (public_url or "(tunnel off)"), 0),
        ("", 0),
    ]
    for y, (text, attr) in enumerate(header):
        stdscr.addnstr(y, 0, text, w - 1, attr)
    base = len(header)
    for i, (label, f) in enumerate(zip(("Username", "Password"), fields)):
        marker = ">" if i == focus else " "
        stdscr.addnstr(base + i, 0, "%s %-9s: " % (marker, label), w - 1,
                       curses.A_BOLD if i == focus else 0)
        stdscr.addnstr(base + i, _VALUE_COL, f.value, max(1, w - _VALUE_COL - 1))
    stdscr.addnstr(base + 3, 0, "Tab/↑↓ move   Ctrl-G random pw   Enter save   Esc cancel",
                   w - 1, curses.A_DIM)
    if msg:
        stdscr.addnstr(base + 5, 0, msg, w - 1, curses.A_BOLD)
    stdscr.move(base + focus, min(_VALUE_COL + fields[focus].cur, w - 1))
    stdscr.refresh()


def _ui(stdscr):
    curses.curs_set(1)
    stdscr.keypad(True)
    config_dir = config.config_dir_default()
    state_dir = config.state_dir_default()
    settings = config.load_settings(config_dir)
    rt = config.instance_state_dir(state_dir)  # this herdr instance's runtime state
    username, password = config.current_creds(config_dir, rt)  # per-instance password
    port = config.load_port(rt) or settings.port  # actual bound port if running
    local_url = "http://%s:%d" % (settings.bind, port)
    public_url = config.load_tunnel_url(rt)
    fields = [Field(username), Field(password)]
    focus = 0
    msg = ""
    while True:
        _draw(stdscr, local_url, public_url, fields, focus, msg)
        ch = stdscr.getch()
        if ch == 27:  # Esc: cancel
            return
        if ch == 9:  # Tab
            focus = (focus + 1) % len(fields)
        elif ch == curses.KEY_UP:
            focus = (focus - 1) % len(fields)
        elif ch == curses.KEY_DOWN:
            focus = (focus + 1) % len(fields)
        elif ch == 7:  # Ctrl-G: regenerate password (unsaved until Enter)
            fields[1] = Field(config.generate_password())
            msg = "generated new password — press Enter to save"
        elif ch in (10, 13, curses.KEY_ENTER):
            user = fields[0].value.strip()
            pw = fields[1].value
            if not user or not pw:
                msg = "username and password must not be empty"
                continue
            config.set_username(config_dir, user)   # username is a shared setting
            config.save_password(rt, pw)             # password is per-instance
            msg = "saved — applies to new connections"
            _draw(stdscr, local_url, public_url, fields, focus, msg)
            curses.napms(800)
            return
        else:
            fields[focus].handle(ch)
            msg = ""


def main(argv):
    if len(argv) > 1 and argv[1] == "ui":
        curses.wrapper(_ui)
    else:
        sys.stderr.write("usage: panel.py ui\n")
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
