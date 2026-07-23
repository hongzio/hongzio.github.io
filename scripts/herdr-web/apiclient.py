"""herdr JSON socket API client + browser-WS proxy. Pure stdlib, unix-only.

The herdr server speaks newline-delimited JSON over a unix socket
(HERDR_SOCKET_PATH). Requests are {id, method, params}; responses come back as
{id, result} or {id, error}; subscription events arrive unsolicited as
{event, data}. No handshake is needed — connect and send.
"""
import json
import os
import select
import socket

import ws

# Global (unscoped) subscriptions — every type whose Subscription schema needs
# only `type` (no pane_id). Per-pane types (agent_status_changed, scroll_changed,
# output_matched) are deliberately omitted: the native sidebar re-reads the full
# session.snapshot on any of these, so one snapshot is the single source of truth.
GLOBAL_EVENTS = [
    "workspace.created", "workspace.updated", "workspace.metadata_updated",
    "workspace.renamed", "workspace.moved", "workspace.closed", "workspace.focused",
    "worktree.created", "worktree.opened", "worktree.removed",
    "tab.created", "tab.closed", "tab.focused", "tab.renamed", "tab.moved",
    "pane.created", "pane.closed", "pane.updated", "pane.focused", "pane.moved",
    "pane.exited", "pane.agent_detected", "layout.updated",
]


def sock_path():
    return os.environ.get("HERDR_SOCKET_PATH") or os.path.expanduser(
        "~/.config/herdr/herdr.sock")


def open_conn(path=None, timeout=None):
    path = path or sock_path()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    if timeout is not None:
        s.settimeout(timeout)
    s.connect(path)
    return s


def send(sock, obj):
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


def request(method, params=None, path=None, timeout=5.0, req_id="herdr-web-dev"):
    """One-shot request: connect, send, return the `result` dict. Raises on an
    error response or a closed/timed-out socket. Used off the WS path (panel,
    status, one-off snapshot reads)."""
    s = open_conn(path, timeout=timeout)
    try:
        send(s, {"id": req_id, "method": method, "params": params or {}})
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                raise ConnectionError("herdr socket closed before response")
            buf += chunk
        msg = json.loads(buf.split(b"\n", 1)[0])
        if "error" in msg:
            raise RuntimeError((msg["error"] or {}).get("message", "herdr api error"))
        return msg.get("result", {})
    finally:
        s.close()


def snapshot(path=None, timeout=5.0):
    """The live session snapshot (workspaces/tabs/panes/agents/layouts)."""
    return request("session.snapshot", {}, path=path, timeout=timeout).get("snapshot", {})


def oneshot(obj, path=None, timeout=5.0):
    """Send one request on a fresh connection and return its raw response line
    (bytes, no trailing newline), or None on failure. Raw so the proxy forwards
    herdr's exact {id,result|error} envelope to the browser unchanged."""
    try:
        s = open_conn(path, timeout=timeout)
    except OSError:
        return None
    try:
        s.sendall((json.dumps(obj) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                return None
            buf += chunk
        return buf.split(b"\n", 1)[0]
    except OSError:
        return None
    finally:
        s.close()


def proxy_pump(sub_conn, ws_sock, recv_exactly, path=None):
    """Bridge the browser's /api WebSocket to herdr's JSON socket.

    herdr treats a connection as EITHER request/response OR an event stream: once
    you send events.subscribe on a connection it only emits events and stops
    answering requests. So we use two paths:
      - `sub_conn` (persistent): the browser's events.subscribe is forwarded here
        and every line it emits (the ack + all events) is relayed to the browser.
      - one-shot connections: every other browser message (snapshot, focus,
        create, split, ...) is sent on its own fresh connection and its single
        response line relayed back. Cheap and matches how the herdr CLI talks.

    Runs until either side closes."""
    sfd = sub_conn.fileno()
    wfd = ws_sock.fileno()
    subbuf = b""
    while True:
        rlist, _, _ = select.select([sfd, wfd], [], [])
        if sfd in rlist:
            data = sub_conn.recv(65536)
            if not data:
                return  # herdr closed the event stream (server gone)
            subbuf += data
            while b"\n" in subbuf:
                line, subbuf = subbuf.split(b"\n", 1)
                if line.strip():
                    ws_sock.sendall(ws.encode_frame(line, ws.OP_TEXT))
        if wfd in rlist:
            opcode, payload = ws.read_frame(recv_exactly)
            if opcode == ws.OP_CLOSE:
                return
            if opcode == ws.OP_PING:
                ws_sock.sendall(ws.encode_frame(payload, ws.OP_PONG))
                continue
            if opcode != ws.OP_TEXT or not payload.strip():
                continue
            try:
                msg = json.loads(payload)
            except (ValueError, TypeError):
                continue
            if isinstance(msg, dict) and msg.get("method") == "events.subscribe":
                sub_conn.sendall(payload.rstrip(b"\n") + b"\n")
            else:
                resp = oneshot(msg, path=path)
                if resp is not None:
                    ws_sock.sendall(ws.encode_frame(resp, ws.OP_TEXT))
