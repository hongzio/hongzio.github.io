"""Basic Auth validation + a signed first-factor session cookie + pidfile liveness.

The primary factor is username/password. Rather than the browser's native Basic
Auth dialog, the daemon serves a custom login form; a successful POST sets a signed
cookie so creds aren't re-sent on every request. The cookie is signed with the
credentials themselves (like the TOTP session cookie is signed with its secret), so
rotating the password/username invalidates every live session automatically — no
separate signing-key file. A valid `Authorization: Basic` header is still accepted
as a fallback for programmatic clients. Pure stdlib."""
import base64
import hashlib
import hmac
import os
import secrets

PW_COOKIE_NAME = "herdrweb_login"

def basic_auth_header(username, password):
    raw = ("%s:%s" % (username, password)).encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")

def check_creds(u, p, username, password):
    """Constant-time compare of a supplied (u, p) against the expected creds."""
    ok_u = secrets.compare_digest(u, username)
    ok_p = secrets.compare_digest(p, password)
    return ok_u and ok_p

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
    return check_creds(u, p, username, password)

# --- signed first-factor session cookie ----------------------------------------
# token = "<iat>.<hmac>", signed with the current credentials. It carries no expiry
# (set without Max-Age/Expires -> a browser-session cookie), so the session lasts
# until the browser is closed. `iat` only varies the token; changing the username or
# password changes the signing key and thus invalidates all outstanding tokens.

def _sign(username, password, payload):
    key = ("herdr-web-login:%s:%s" % (username, password)).encode("utf-8")
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()

def make_session(username, password, iat=None):
    import time
    payload = str(int(time.time()) if iat is None else int(iat))
    return "%s.%s" % (payload, _sign(username, password, payload))

def valid_session(username, password, token):
    """True iff `token` was signed by the current creds (constant-time)."""
    if not token or "." not in token:
        return False
    payload, _, sig = token.rpartition(".")
    if not payload:
        return False
    return hmac.compare_digest(_sign(username, password, payload), sig)

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
