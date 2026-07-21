"""Config + secret provisioning for herdr-web. Pure stdlib (py3.9, no tomllib)."""
import hashlib
import json
import os
import re
import secrets
from collections import namedtuple

HOME = os.path.expanduser("~")
Settings = namedtuple("Settings", "port bind username tunnel_enabled require_os_auth")

DEFAULT_CONFIG = (
    "# herdr-web config.\n"
    "[server]\n"
    "port = 8022\n"
    'bind = "127.0.0.1"\n'
    "[auth]\n"
    'username = "herdr"\n'
    "# password auto-generated on first run (stored in state dir, 0600)\n"
    "[tunnel]\n"
    "enabled = false\n"
    "# when exposed, false = Basic Auth only (relies on the strong random\n"
    "# password); true adds an OS login by exec'ing ssh localhost (needs Remote\n"
    "# Login enabled).\n"
    "require_os_auth = false\n"
)

def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v

def parse_config(text):
    """Tolerant nested {section: {key: value}} parser. Ignores comments/junk."""
    cfg = {}
    section = None
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            cfg.setdefault(section, {})
            continue
        if section is None or "=" not in line:
            continue
        key, _, val = line.partition("=")
        cfg[section][key.strip()] = _unquote(val)
    return cfg

def _as_bool(v, default):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")

def _as_int(v, default):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default

def config_dir_default():
    return os.environ.get(
        "HERDR_PLUGIN_CONFIG_DIR",
        os.path.join(HOME, ".config", "herdr", "plugins", "config", "web"),
    )

def state_dir_default():
    return os.environ.get(
        "HERDR_PLUGIN_STATE_DIR",
        os.path.join(HOME, ".local", "state", "herdr", "plugins", "web"),
    )

def load_settings(config_dir):
    os.makedirs(config_dir, exist_ok=True)
    path = os.path.join(config_dir, "config.toml")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as fh:
        cfg = parse_config(fh.read())
    server = cfg.get("server", {})
    auth = cfg.get("auth", {})
    tunnel = cfg.get("tunnel", {})
    return Settings(
        port=_as_int(server.get("port"), 8022),
        bind=server.get("bind", "127.0.0.1"),
        username=auth.get("username", "herdr"),
        tunnel_enabled=_as_bool(tunnel.get("enabled"), False),
        require_os_auth=_as_bool(tunnel.get("require_os_auth"), False),
    )

def load_or_create_password(state_dir):
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, "password")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            existing = fh.read().strip()
        if existing:
            return existing
    pw = secrets.token_urlsafe(18)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(pw)
    os.chmod(path, 0o600)
    return pw

# --- live-editable credential + tunnel-url state -------------------------------

def password_path(state_dir):
    return os.path.join(state_dir, "password")

def tunnel_url_path(state_dir):
    return os.path.join(state_dir, "tunnel_url")

def tunnel_pid_path(state_dir):
    return os.path.join(state_dir, "tunnel.pid")

def save_tunnel_pid(state_dir, pid):
    os.makedirs(state_dir, exist_ok=True)
    _atomic_write(tunnel_pid_path(state_dir), str(pid), 0o600)

def clear_tunnel_pid(state_dir):
    try:
        os.remove(tunnel_pid_path(state_dir))
    except OSError:
        pass

def local_enabled_path(state_dir):
    return os.path.join(state_dir, "local_enabled")

def is_local_enabled(state_dir):
    """Whether the local daemon should auto-start. Absent (fresh install) -> True,
    so a brand-new plugin defaults to ON; only an explicit off from the panel sticks."""
    try:
        with open(local_enabled_path(state_dir), encoding="utf-8") as fh:
            return fh.read().strip().lower() not in ("0", "false")
    except OSError:
        return True

def set_local_enabled(state_dir, enabled):
    os.makedirs(state_dir, exist_ok=True)
    _atomic_write(local_enabled_path(state_dir), "1" if enabled else "0", 0o600)

def generate_password():
    return secrets.token_urlsafe(18)

def _atomic_write(path, data, mode):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.chmod(tmp, mode)
    os.replace(tmp, path)

def password_pinned_path(state_dir):
    return os.path.join(state_dir, "password.pinned")

def is_password_pinned(state_dir):
    return os.path.exists(password_pinned_path(state_dir))

def save_password(state_dir, pw):
    """Atomically write the password (0600) AND pin it: a password set here (via
    the panel) is an explicit choice, so it survives daemon restarts."""
    os.makedirs(state_dir, exist_ok=True)
    _atomic_write(password_path(state_dir), pw, 0o600)
    _atomic_write(password_pinned_path(state_dir), "", 0o600)

def rotate_password(state_dir):
    """Generate a fresh (unpinned) auto password and store it."""
    os.makedirs(state_dir, exist_ok=True)
    pw = generate_password()
    _atomic_write(password_path(state_dir), pw, 0o600)
    try:
        os.remove(password_pinned_path(state_dir))
    except OSError:
        pass
    return pw

def startup_password(state_dir):
    """Password a starting daemon should use: keep it if the user pinned it via the
    panel, otherwise rotate so each session gets fresh credentials (like the URL)."""
    if is_password_pinned(state_dir):
        return load_or_create_password(state_dir)
    return rotate_password(state_dir)

def set_username(config_dir, username):
    """Replace the [auth] username in config.toml, preserving the rest of the file."""
    os.makedirs(config_dir, exist_ok=True)
    path = os.path.join(config_dir, "config.toml")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = DEFAULT_CONFIG
    line = 'username = "%s"' % username
    if re.search(r"(?m)^\s*username\s*=", text):
        text = re.sub(r"(?m)^\s*username\s*=.*$", lambda m: line, text)
    elif re.search(r"(?m)^\s*\[auth\]\s*$", text):
        text = re.sub(r"(?m)^(\s*\[auth\]\s*)$", lambda m: m.group(1) + "\n" + line, text)
    else:
        text = text.rstrip("\n") + "\n[auth]\n" + line + "\n"
    _atomic_write(path, text, 0o644)

def set_tunnel_enabled(config_dir, enabled):
    """Set [tunnel] enabled in config.toml (the daemon's tunnel supervisor reads it
    live), preserving the rest of the file."""
    os.makedirs(config_dir, exist_ok=True)
    path = os.path.join(config_dir, "config.toml")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = DEFAULT_CONFIG
    line = "enabled = %s" % ("true" if enabled else "false")
    if re.search(r"(?m)^\s*enabled\s*=", text):
        text = re.sub(r"(?m)^\s*enabled\s*=.*$", lambda m: line, text)
    elif re.search(r"(?m)^\s*\[tunnel\]\s*$", text):
        text = re.sub(r"(?m)^(\s*\[tunnel\]\s*)$", lambda m: m.group(1) + "\n" + line, text)
    else:
        text = text.rstrip("\n") + "\n[tunnel]\n" + line + "\n"
    _atomic_write(path, text, 0o644)

def save_tunnel_url(state_dir, url):
    os.makedirs(state_dir, exist_ok=True)
    _atomic_write(tunnel_url_path(state_dir), url, 0o600)

def load_tunnel_url(state_dir):
    try:
        with open(tunnel_url_path(state_dir), encoding="utf-8") as fh:
            u = fh.read().strip()
        return u or None
    except OSError:
        return None

def clear_tunnel_url(state_dir):
    try:
        os.remove(tunnel_url_path(state_dir))
    except OSError:
        pass

# --- tunnel error state --------------------------------------------------------
# When the tunnel is enabled but can't come up (e.g. cloudflared not installed),
# the supervisor records a short reason here so the panel can show it instead of
# a permanent "starting..." that never resolves.

def tunnel_status_path(state_dir):
    return os.path.join(state_dir, "tunnel_status")

def save_tunnel_status(state_dir, msg):
    os.makedirs(state_dir, exist_ok=True)
    _atomic_write(tunnel_status_path(state_dir), msg, 0o600)

def load_tunnel_status(state_dir):
    try:
        with open(tunnel_status_path(state_dir), encoding="utf-8") as fh:
            m = fh.read().strip()
        return m or None
    except OSError:
        return None

def clear_tunnel_status(state_dir):
    try:
        os.remove(tunnel_status_path(state_dir))
    except OSError:
        pass

def instance_key():
    """Stable key for the herdr instance this daemon belongs to, from its server
    socket path, so each instance gets its own runtime state (pidfile/port/tunnel).
    Falls back to 'default' when there is no socket (e.g. --no-session)."""
    sock = os.environ.get("HERDR_SOCKET_PATH", "")
    if not sock:
        return "default"
    return hashlib.sha1(sock.encode("utf-8")).hexdigest()[:12]

def instance_state_dir(state_dir):
    """Per-herdr-instance runtime dir (pidfile/port/tunnel_url live here); config
    and password stay in the shared state_dir root."""
    return os.path.join(state_dir, "instances", instance_key())

def port_path(state_dir):
    return os.path.join(state_dir, "port")

def save_port(state_dir, port):
    """Record the port the daemon actually bound (may differ from config if it
    fell back to a free port), so status/panel can show the real local URL."""
    os.makedirs(state_dir, exist_ok=True)
    _atomic_write(port_path(state_dir), str(port), 0o600)

def load_port(state_dir):
    try:
        with open(port_path(state_dir), encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None

def clear_port(state_dir):
    try:
        os.remove(port_path(state_dir))
    except OSError:
        pass

def current_creds(config_dir, state_dir):
    """(username, password) read fresh — used by the daemon's per-request auth."""
    return load_settings(config_dir).username, load_or_create_password(state_dir)

# --- notification (messenger) config -------------------------------------------
# Shared like username (lives in config_dir, applies to every herdr instance), but
# stored as JSON rather than in config.toml: the messenger list is a multi-record,
# multi-field structure that the flat TOML parser/regex-setters can't represent
# cleanly. notify.py owns the schema; this layer just reads/writes the whole blob.

def notify_path(config_dir):
    return os.path.join(config_dir, "notify.json")

def load_notify(config_dir):
    """Return the raw notify config dict, or {} when missing/corrupt (notify.py
    normalizes it against its type registry)."""
    try:
        with open(notify_path(config_dir), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def save_notify(config_dir, data):
    """Atomically persist the whole notify config (0600 — it holds bot tokens)."""
    _atomic_write(notify_path(config_dir), json.dumps(data, indent=2), 0o600)
