"""herdr-web daemon: HTTP + WebSocket -> pty.fork(herdr). Pure stdlib."""
import fcntl
import getpass
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import authstate
import config
import notify
import ptybridge
import ws

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

# herdr exports these inside a pane; if the pty child sees them, `herdr` refuses
# to start ("nested herdr"). HERDR_SOCKET_PATH is deliberately NOT listed so the
# attaching client still finds the running server.
_HERDR_NESTING_VARS = ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID")

def pty_argv(settings, exposed):
    if exposed and settings.require_os_auth:
        return ["ssh", "%s@localhost" % getpass.getuser()]
    return ["herdr"]

def toast(message):
    try:
        subprocess.run(["herdr", "notification", "show", message],
                       check=False, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _rt():
    """Per-herdr-instance runtime dir (pidfile/port/tunnel_url)."""
    return config.instance_state_dir(config.state_dir_default())

def _paths():
    return os.path.join(_rt(), "web.pid")

def _make_handler(settings):
    realm = 'Basic realm="herdr-web"'
    config_dir = config.config_dir_default()
    rt = config.instance_state_dir(config.state_dir_default())  # per-instance password

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _authed(self):
            # read creds fresh each request so the panel's live edits apply to
            # new connections without a restart (which would change the URL).
            user, pw = config.current_creds(config_dir, rt)
            if authstate.check_basic_auth(self.headers.get("Authorization"), user, pw):
                return True
            self.send_response(401)
            self.send_header("WWW-Authenticate", realm)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False

        def _send_file(self, path, ctype):
            with open(path, "rb") as fh:
                body = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            # never cache: the page/creds are dynamic and auth-gated, and a stale
            # cached index.html silently keeps old client behavior after updates.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._authed():
                return
            if self.path == "/" or self.path == "/index.html":
                return self._send_file(os.path.join(STATIC, "index.html"), "text/html; charset=utf-8")
            if self.path.startswith("/static/"):
                name = os.path.basename(self.path)
                ctype = "text/css" if name.endswith(".css") else "application/javascript"
                fpath = os.path.join(STATIC, name)
                if os.path.isfile(fpath):
                    return self._send_file(fpath, ctype)
                self.send_error(404)
                return
            if self.path == "/ws":
                return self._do_ws()
            self.send_error(404)

        def _do_ws(self):
            key = self.headers.get("Sec-WebSocket-Key")
            if not key:
                self.send_error(400)
                return
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", ws.accept_key(key))
            self.end_headers()
            sock = self.connection

            # Read WS frames straight from the raw socket so pump()'s select()
            # on the socket fd stays in sync — a buffered reader would pull bytes
            # into userspace where select can't see them, stalling interactive
            # input. The bundled browser client never sends frames before the 101
            # handshake response, so nothing is left buffered in self.rfile here.
            def recv_exactly(n):
                out = b""
                while len(out) < n:
                    chunk = sock.recv(n - len(out))
                    if not chunk:
                        raise ConnectionError("eof")
                    out += chunk
                return out

            # herdr sets HERDR_ENV/PANE/TAB/WORKSPACE inside a pane; passing them
            # to the pty child makes `herdr` think it's nested and refuse to start.
            # Strip them (keep HERDR_SOCKET_PATH so the client still finds the
            # server) so the web terminal attaches as a fresh top-level client.
            env = {k: v for k, v in os.environ.items() if k not in _HERDR_NESTING_VARS}
            env["TERM"] = "xterm-256color"
            # read tunnel state live: when exposed + require_os_auth, the pty runs
            # ssh localhost for a second auth layer.
            exposed = config.load_settings(config_dir).tunnel_enabled
            pid, master_fd = ptybridge.spawn(pty_argv(settings, exposed), env)
            try:
                ptybridge.pump(master_fd, sock, recv_exactly)
            except (ConnectionError, OSError):
                pass
            finally:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass

        def log_message(self, *a):
            pass

    return Handler

def _bind(host, preferred, handler):
    """Bind the preferred port; if it's busy, fall back to an OS-assigned free
    port. Returns (httpd, actual_port), or (None, None) if nothing could bind."""
    try:
        return ThreadingHTTPServer((host, preferred), handler), preferred
    except OSError:
        pass
    try:
        httpd = ThreadingHTTPServer((host, 0), handler)
        return httpd, httpd.server_address[1]
    except OSError:
        return None, None

def _herdr_server_pid(sockpath):
    """pid of the process listening on the herdr socket (its server), via lsof.
    Never connects to the socket, so it can't interfere with herdr's shutdown."""
    try:
        out = subprocess.run(["lsof", "-nP", "-t", "--", sockpath],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    pids = []
    for tok in out.split():
        try:
            pids.append(int(tok))
        except ValueError:
            pass
    for pid in pids:
        try:
            cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)],
                                 capture_output=True, text=True, timeout=5).stdout
        except Exception:
            cmd = ""
        if "herdr" in cmd and "serve.py" not in cmd:
            return pid
    return pids[0] if pids else None

def _watch_herdr(sockpath, poll=5.0):
    """herdr has no shutdown event, so find our herdr server's pid (once, via
    lsof) and self-terminate — which tears down the tunnel — when it exits.
    os.kill(pid, 0) polling never touches herdr's socket, so unlike connecting
    it can't keep herdr from shutting down."""
    pid = None
    for _ in range(6):
        pid = _herdr_server_pid(sockpath)
        if pid:
            break
        time.sleep(1)
    if not pid:
        return
    while True:
        time.sleep(poll)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            os.kill(os.getpid(), signal.SIGTERM)
            return
        except OSError:
            pass  # e.g. PermissionError -> the process still exists

def run():
    settings = config.load_settings(config.config_dir_default())
    rt = _rt()  # per-instance runtime dir (pidfile/port/tunnel_url/password)
    os.makedirs(rt, exist_ok=True)

    # Serialize concurrent starts. herdr fires many events on restore (each spawns
    # `ensure`), and the free-port fallback means a racing loser would bind a
    # *different* port instead of failing to bind — so without this lock we'd end up
    # with several daemons. Hold it across the is-running check + bind + pidfile write.
    lockfd = os.open(os.path.join(rt, "run.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(lockfd, fcntl.LOCK_EX)
    try:
        if authstate.is_running(_paths()):
            return  # another daemon already started for this herdr instance
        password = config.startup_password(rt)  # rotate unless the user pinned one
        config.clear_tunnel_url(rt)  # drop stale state from a prior run
        config.clear_tunnel_status(rt)
        config.clear_port(rt)
        handler = _make_handler(settings)
        httpd, port = _bind(settings.bind, settings.port, handler)
        if httpd is None:
            toast("herdr-web: cannot bind %s (no free port available)" % settings.bind)
            return
        authstate.write_pid(_paths(), os.getpid())
        config.save_port(rt, port)
    finally:
        fcntl.flock(lockfd, fcntl.LOCK_UN)
        os.close(lockfd)
    if port != settings.port:
        toast("herdr-web: port %d busy — using %d instead" % (settings.port, port))

    # tunnel supervisor: start/stop cloudflared to match [tunnel] enabled (read live),
    # so the panel can toggle the tunnel without restarting the daemon.
    tunnel = {"proc": None}
    threading.Thread(target=_tunnel_supervisor,
                     args=(port, rt, config.config_dir_default(), tunnel), daemon=True).start()

    # SIGTERM (sent by `serve.py stop`) must unwind through the finally below so
    # the cloudflared tunnel is torn down; without a handler the default SIGTERM
    # kills the process and orphans the tunnel, leaving the public URL live.
    def _on_term(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, _on_term)

    # herdr has no shutdown event, so watch our instance's socket and exit (which
    # tears the tunnel down) when that herdr goes away — e.g. `herdr server stop`.
    sockpath = os.environ.get("HERDR_SOCKET_PATH")
    if sockpath:
        threading.Thread(target=_watch_herdr, args=(sockpath,), daemon=True).start()

    local_url = "http://%s:%d" % (settings.bind, port)
    toast("herdr-web: %s  (user %s / pw %s)" % (local_url, settings.username, password))
    try:
        httpd.serve_forever()
    finally:
        config.clear_tunnel_url(rt)
        config.clear_tunnel_status(rt)
        config.clear_port(rt)
        config.clear_tunnel_pid(rt)
        if tunnel["proc"]:
            tunnel["proc"].terminate()

def _tunnel_supervisor(port, rt, config_dir, state, poll=3.0):
    """Keep cloudflared matching [tunnel] enabled (re-read each poll). Lets the panel
    toggle the tunnel live without restarting the daemon; stores the proc in `state`
    so run()'s finally can tear it down on exit."""
    give_up = False  # stop retrying if cloudflared is missing (avoid toast spam)
    while True:
        want = config.load_settings(config_dir).tunnel_enabled
        proc = state.get("proc")
        running = proc is not None and proc.poll() is None
        if want and not running and not give_up:
            state["proc"] = _start_tunnel(port, rt)
            give_up = state["proc"] is None
        elif not want:
            give_up = False
            if running:
                proc.terminate()
                state["proc"] = None
            config.clear_tunnel_url(rt)
            config.clear_tunnel_pid(rt)
            config.clear_tunnel_status(rt)
        time.sleep(poll)

def _start_tunnel(port, rt):
    from shutil import which
    if not which("cloudflared"):
        # Record the reason so the panel shows it instead of a forever "starting..."
        # (the supervisor gives up, so nothing else will ever clear this state).
        config.save_tunnel_status(rt, "cloudflared not found — brew install cloudflared")
        toast("herdr-web: cloudflared not found; local-only")
        return None
    config.clear_tunnel_status(rt)  # started OK; drop any stale error from a prior try
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://127.0.0.1:%d" % port],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        bufsize=1, universal_newlines=True,
    )
    config.save_tunnel_pid(rt, proc.pid)  # so the panel can show the cloudflared pid

    # cloudflared logs "Requesting new quick Tunnel on trycloudflare.com..."
    # before it prints the actual URL, so match a full https://…trycloudflare.com
    # URL rather than any line/token mentioning the domain.
    url_re = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

    def watch():
        announced = False
        # Keep draining cloudflared's output for the life of the process; if we
        # stopped reading after the URL, the stdout pipe would eventually fill
        # and block cloudflared, stalling the tunnel.
        for line in proc.stdout:
            if not announced:
                m = url_re.search(line)
                if m:
                    config.save_tunnel_url(rt, m.group(0))
                    toast("herdr-web tunnel: %s" % m.group(0))
                    # push the new public URL to enabled messengers (once per URL,
                    # guarded by `announced`). Off-thread so a slow/hung messenger
                    # send (up to _TIMEOUT each) can't stall this loop, whose job is
                    # to keep draining cloudflared's stdout; and wrapped so a notify
                    # error can't kill the watcher.
                    def _notify(url=m.group(0)):
                        try:
                            notify.on_public_url(url, config.config_dir_default(), rt)
                        except Exception:
                            pass
                    threading.Thread(target=_notify, daemon=True).start()
                    announced = True
    threading.Thread(target=watch, daemon=True).start()
    return proc

def ensure():
    if not config.is_local_enabled(_rt()):
        return  # user turned local off via the panel; stay off until re-enabled
    if authstate.is_running(_paths()):
        return
    # detach: setsid + re-exec `run`
    if os.fork() != 0:
        return
    os.setsid()
    if os.fork() != 0:
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    run()
    os._exit(0)

def status():
    rt = _rt()
    settings = config.load_settings(config.config_dir_default())
    password = config.load_or_create_password(rt)
    pid = authstate.is_running(_paths())
    state = "running (pid %s)" % pid if pid else "stopped"
    port = (config.load_port(rt) if pid else None) or settings.port
    tunnel = config.load_tunnel_url(rt) if pid else None
    msg = "herdr-web %s: http://%s:%d  user %s / pw %s" % (
        state, settings.bind, port, settings.username, password)
    if tunnel:
        msg += "  |  tunnel %s" % tunnel
    toast(msg)

def stop():
    pid = authstate.is_running(_paths())
    if pid:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    rt = _rt()
    config.clear_tunnel_url(rt)
    config.clear_tunnel_status(rt)
    config.clear_port(rt)
    config.clear_tunnel_pid(rt)
    toast("herdr-web stopped")

def restart():
    stop()
    for _ in range(50):
        if authstate.is_running(_paths()) is None:
            break
        time.sleep(0.1)
    ensure()

def main(argv):
    cmd = argv[1] if len(argv) > 1 else "ensure"
    {"ensure": ensure, "run": run, "status": status, "stop": stop, "restart": restart}.get(cmd, ensure)()

if __name__ == "__main__":
    main(sys.argv)
