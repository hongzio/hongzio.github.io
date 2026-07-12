"""PTY <-> WebSocket bridge. Pure stdlib (unix-only)."""
import fcntl
import json
import os
import pty
import select
import struct
import termios

import ws

def parse_control(payload):
    try:
        msg = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if isinstance(msg, dict) and msg.get("type") == "resize":
        try:
            return int(msg["cols"]), int(msg["rows"])
        except (KeyError, ValueError, TypeError):
            return None
    return None

def winsize_bytes(rows, cols):
    return struct.pack("HHHH", rows, cols, 0, 0)

def set_winsize(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize_bytes(rows, cols))

def spawn(argv, env):
    """pty.fork() and exec argv in the child with exactly `env` as its environment."""
    pid, master_fd = pty.fork()
    if pid == 0:  # child
        try:
            os.execvpe(argv[0], argv, env)
        except OSError:
            os._exit(127)
    return pid, master_fd

def pump(master_fd, sock, recv_exactly):
    """Bridge until EOF on either side. recv_exactly reads client WS frames."""
    sock_fd = sock.fileno()
    while True:
        rlist, _, _ = select.select([master_fd, sock_fd], [], [])
        if master_fd in rlist:
            try:
                data = os.read(master_fd, 65536)
            except OSError:
                data = b""
            if not data:
                return
            sock.sendall(ws.encode_frame(data, ws.OP_BINARY))
        if sock_fd in rlist:
            opcode, payload = ws.read_frame(recv_exactly)
            if opcode == ws.OP_CLOSE:
                return
            if opcode == ws.OP_TEXT:
                ctrl = parse_control(payload)
                if ctrl:
                    cols, rows = ctrl
                    set_winsize(master_fd, rows, cols)
                continue
            if opcode == ws.OP_BINARY:
                os.write(master_fd, payload)
