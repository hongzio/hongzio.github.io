"""Messenger notifications for herdr-web: on a new public (tunnel) URL, push the
server info to enabled messengers. Pure stdlib (urllib), macOS-only like the rest.

Only Telegram ships today, but everything hangs off the TYPES registry so adding
Slack/Discord/a generic webhook later is a matter of one more entry — the panel,
config normalization, and the send loop all iterate TYPES.
"""
import json
import socket
import urllib.error
import urllib.request

import config

_TIMEOUT = 10  # seconds; bounds a hung messenger so it can't stall the watch loop


# --- HTTP helpers --------------------------------------------------------------

def _post_json(url, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read()

def _get(url):
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
        return resp.read()


# --- Telegram ------------------------------------------------------------------

def _telegram_api(token, method):
    return "https://api.telegram.org/bot%s/%s" % (token.strip(), method)

def _telegram_error(exc):
    """Pull Telegram's human 'description' out of an HTTPError body if present."""
    try:
        data = json.loads(exc.read())
        desc = data.get("description")
        return ": %s" % desc if desc else ""
    except Exception:
        return ""

def _send_telegram(cfg, text):
    token = (cfg.get("bot_token") or "").strip()
    chat_id = (cfg.get("chat_id") or "").strip()
    if not token or not chat_id:
        return (False, "bot_token and chat_id required")
    payload = {"chat_id": chat_id, "text": text}
    topic = (cfg.get("topic_id") or "").strip()
    if topic:  # optional forum-topic thread; API wants an int message_thread_id
        try:
            payload["message_thread_id"] = int(topic)
        except ValueError:
            return (False, "topic_id must be a number")
    try:
        _post_json(_telegram_api(token, "sendMessage"), payload)
        return (True, "sent")
    except urllib.error.HTTPError as e:
        return (False, "HTTP %s%s" % (e.code, _telegram_error(e)))
    except (urllib.error.URLError, OSError) as e:
        return (False, str(getattr(e, "reason", e)))

def _fetch_telegram_ids(cfg):
    """Resolve chat_id (and topic_id if the latest message is in a forum topic) from
    the bot's recent updates via getUpdates. Requires the user to have messaged the
    bot first (bots can't see chats they weren't spoken to) — and, for a topic, to
    have sent that message inside the target topic. Returns (ok, fields_or_error,
    label): on success a {chat_id[, topic_id]} dict, else an error string."""
    token = (cfg.get("bot_token") or "").strip()
    if not token:
        return (False, "bot_token required", "")
    try:
        data = json.loads(_get(_telegram_api(token, "getUpdates")))
    except urllib.error.HTTPError as e:
        return (False, "HTTP %s%s" % (e.code, _telegram_error(e)), "")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return (False, str(getattr(e, "reason", e)), "")
    # Newest update last; scan back for the most recent thing carrying a chat.
    for upd in reversed(data.get("result") or []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is None:
            continue
        fields = {"chat_id": str(cid)}
        tid = msg.get("message_thread_id")
        if tid is not None and msg.get("is_topic_message"):
            fields["topic_id"] = str(tid)
        label = (chat.get("title") or chat.get("username")
                 or chat.get("first_name") or "")
        return (True, fields, label)
    return (False, "no chats found — send a message to the bot first", "")


# --- type registry -------------------------------------------------------------
# fields: (key, label, secret). send: (cfg, text) -> (ok, msg).
# fetch:  optional (cfg) -> (ok, value_or_error, label); powers "Fetch chat id".

TYPES = {
    "telegram": {
        "label": "Telegram",
        "fields": [
            ("bot_token", "Bot token", True),
            ("chat_id", "Chat id", False),
            ("topic_id", "Topic id (opt)", False),
        ],
        "fetch_label": "chat/topic id",
        "fetch": _fetch_telegram_ids,
        "send": _send_telegram,
    },
}

# Stable display order for the panel / send loop (dict order, but explicit).
TYPE_IDS = list(TYPES.keys())


# --- config normalization ------------------------------------------------------

def _blank(type_id):
    m = {"enabled": False}
    for key, _label, _secret in TYPES[type_id]["fields"]:
        m[key] = ""
    return m

def normalize(data):
    """Coerce a raw dict (possibly {}) into the full {options, messengers} shape,
    filling defaults so callers never KeyError on a missing type/field."""
    data = data if isinstance(data, dict) else {}
    opts = data.get("options")
    opts = opts if isinstance(opts, dict) else {}
    raw = data.get("messengers")
    raw = raw if isinstance(raw, dict) else {}
    messengers = {}
    for type_id in TYPE_IDS:
        cur = raw.get(type_id) if isinstance(raw.get(type_id), dict) else {}
        m = {"enabled": bool(cur.get("enabled", False))}
        for key, _label, _secret in TYPES[type_id]["fields"]:
            m[key] = str(cur.get(key, "") or "")
        messengers[type_id] = m
    return {
        "options": {"include_password": bool(opts.get("include_password", False))},
        "messengers": messengers,
    }

def load(config_dir):
    return normalize(config.load_notify(config_dir))

def save(config_dir, data):
    config.save_notify(config_dir, data)


# --- message rendering + dispatch ----------------------------------------------

def render_message(public_url, username, password=None):
    """Fixed server-info format. Password line only when a password is passed
    (the panel's 'Include password' toggle decides whether to pass one)."""
    lines = [
        "\U0001F514 herdr-web on %s" % socket.gethostname(),
        "Public: %s" % public_url,
        "User: %s" % username,
    ]
    if password:
        lines.append("Password: %s" % password)
    return "\n".join(lines)

def send(type_id, cfg, text):
    spec = TYPES.get(type_id)
    if not spec:
        return (False, "unknown messenger")
    return spec["send"](cfg, text)

def fetch(type_id, cfg):
    spec = TYPES.get(type_id)
    fn = spec.get("fetch") if spec else None
    if not fn:
        return (False, "not supported", "")
    return fn(cfg)

def on_public_url(public_url, config_dir, state_dir):
    """Called from the tunnel watcher when a fresh public URL is published. Sends
    the server info to every enabled messenger; each send is isolated so one
    failure never blocks the others. Returns [(type_id, ok, msg), ...]."""
    conf = load(config_dir)
    username = config.load_settings(config_dir).username
    password = (config.load_or_create_password(state_dir)
                if conf["options"]["include_password"] else None)
    text = render_message(public_url, username, password)
    results = []
    for type_id, cfg in conf["messengers"].items():
        if not cfg.get("enabled"):
            continue
        try:
            ok, msg = send(type_id, cfg, text)
        except Exception as e:  # never let a messenger bug escape into the daemon
            ok, msg = False, str(e)
        results.append((type_id, ok, msg))
    return results
