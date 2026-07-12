"""Basic Auth validation + pidfile liveness. Pure stdlib."""
import base64
import os
import secrets

def basic_auth_header(username, password):
    raw = ("%s:%s" % (username, password)).encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")

def check_basic_auth(header, username, password):
    if not header or not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except Exception:
        return False
    u, sep, p = raw.partition(":")
    if not sep:
        return False
    ok_u = secrets.compare_digest(u, username)
    ok_p = secrets.compare_digest(p, password)
    return ok_u and ok_p

def read_pid(pidfile):
    try:
        with open(pidfile, encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None

def is_running(pidfile):
    pid = read_pid(pidfile)
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        return pid
    return pid

def write_pid(pidfile, pid):
    with open(pidfile, "w", encoding="utf-8") as fh:
        fh.write(str(pid))
