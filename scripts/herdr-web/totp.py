"""RFC 6238 TOTP (second auth factor) + a signed browser-session cookie. Pure stdlib.

The web daemon uses HTTP Basic Auth as the first factor. When a TOTP secret is
provisioned, a one-time 6-digit code establishes a session; the browser then carries
a signed cookie so the code isn't re-typed on every request. The cookie is signed
with the TOTP secret itself, so regenerating the secret invalidates every live
session automatically — no separate signing-key file to manage.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

DIGITS = 6
PERIOD = 30       # seconds per step (RFC 6238 default)
SKEW = 1          # accept ±1 step so a slightly-off client clock still verifies
COOKIE_NAME = "herdrweb_session"


def generate_secret(nbytes=20):
    """A random base32 secret (default 160-bit, the RFC 4226 recommendation),
    unpadded so it pastes cleanly into authenticator apps."""
    return base64.b32encode(secrets.token_bytes(nbytes)).decode("ascii").rstrip("=")


def _b32decode(secret):
    """Decode a user-facing base32 secret, tolerant of spaces/case/missing padding."""
    s = (secret or "").strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(key, counter, digits=DIGITS):
    """RFC 4226 HOTP: dynamic-truncated HMAC-SHA1 of the 8-byte counter."""
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    val = struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF
    return str(val % (10 ** digits)).zfill(digits)


def totp_at(secret, when, period=PERIOD, digits=DIGITS):
    """The TOTP code for `secret` at unix time `when` (used by tests/vectors)."""
    return hotp(_b32decode(secret), int(when // period), digits)


def verify(secret, code, when=None, skew=SKEW, period=PERIOD, digits=DIGITS):
    """True iff `code` is a valid TOTP for `secret` within ±skew steps of now.
    Rejects non-numeric / wrong-length input up front and swallows a malformed
    secret so a bad code or bad enrollment can never raise into the request path."""
    if when is None:
        when = time.time()
    code = (code or "").strip()
    if not (code.isdigit() and len(code) == digits):
        return False
    try:
        key = _b32decode(secret)
    except Exception:
        return False
    counter = int(when // period)
    for c in range(counter - skew, counter + skew + 1):
        if c >= 0 and hmac.compare_digest(hotp(key, c, digits), code):
            return True
    return False


def provisioning_uri(secret, account, issuer="herdr-web"):
    """An otpauth:// URI for enrolling `secret` in an authenticator app."""
    label = quote("%s:%s" % (issuer, account), safe=":")  # keep the issuer:account colon literal
    params = urlencode({"secret": secret, "issuer": issuer,
                        "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD})
    return "otpauth://totp/%s?%s" % (label, params)


# --- signed browser-session cookie ---------------------------------------------
# token = "<iat>.<hmac>", signed with the TOTP secret. It carries no expiry: the
# cookie is set without Max-Age/Expires (a browser-session cookie), so the session
# lasts until the browser is closed. `iat` only varies the token; regenerating the
# secret changes the signing key and thus invalidates all outstanding tokens.

def _sign(secret, payload):
    key = ("herdr-web-session:" + secret).encode("utf-8")
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_session(secret, iat=None):
    payload = str(int(time.time()) if iat is None else int(iat))
    return "%s.%s" % (payload, _sign(secret, payload))


def valid_session(secret, token):
    """True iff `token` was signed by the current `secret` (constant-time)."""
    if not secret or not token or "." not in token:
        return False
    payload, _, sig = token.rpartition(".")
    if not payload:
        return False
    return hmac.compare_digest(_sign(secret, payload), sig)
