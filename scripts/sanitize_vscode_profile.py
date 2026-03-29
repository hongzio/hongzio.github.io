#!/usr/bin/env python3
"""Sanitize sensitive state from a VS Code profile export."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SETTINGS_KEY = "settings"
GLOBAL_STATE_KEY = "globalState"

SENSITIVE_SETTING_KEYS = {
    "dbcode.connections",
}

SENSITIVE_SETTING_PREFIXES = (
    "remote.tunnels.toRestore",
    "remote.tunnels.toRestoreExpiration",
)

SENSITIVE_STORAGE_PATTERNS = (
    re.compile(r"^github-[A-Za-z0-9_.-]+$"),
    re.compile(r"^__GitHub\.copilot-chat-[A-Za-z0-9_.-]+$"),
    re.compile(r"^remote\.tunnels\.toRestore(?:Expiration)?(?:\.|$)"),
)

FORBIDDEN_TEXT_PATTERNS = (
    re.compile(r'"globalState"\s*:', re.IGNORECASE),
    re.compile(r'"dbcode\.connections"\s*:', re.IGNORECASE),
    re.compile(
        r'"remote\.tunnels\.toRestore(?:Expiration)?[^"]*"\s*:',
        re.IGNORECASE,
    ),
    re.compile(r'"__GitHub\.copilot-chat-[A-Za-z0-9_.-]+"\s*:', re.IGNORECASE),
    re.compile(r'"github-[A-Za-z0-9_.-]+"\s*:', re.IGNORECASE),
    re.compile(r"platformdb\.internal", re.IGNORECASE),
    re.compile(r'"password"\s*:', re.IGNORECASE),
    re.compile(r'"savePassword"\s*:', re.IGNORECASE),
    re.compile(r'"salt"\s*:', re.IGNORECASE),
)


def strip_jsonc_comments(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    in_line_comment = False
    in_block_comment = False
    i = 0

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        if ch == '"':
            in_string = True

        out.append(ch)
        i += 1

    return "".join(out)


def remove_trailing_commas(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    i = 0

    while i < len(text):
        ch = text[i]

        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == ",":
            j = i + 1
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j < len(text) and text[j] in "}]":
                i += 1
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def parse_jsonc(text: str) -> object:
    return json.loads(remove_trailing_commas(strip_jsonc_comments(text)))


def should_remove_setting_key(key: str) -> bool:
    return key in SENSITIVE_SETTING_KEYS or any(
        key.startswith(prefix) for prefix in SENSITIVE_SETTING_PREFIXES
    )


def should_remove_storage_key(key: str) -> bool:
    return any(pattern.match(key) for pattern in SENSITIVE_STORAGE_PATTERNS)


def sanitize_settings_blob(raw: str) -> tuple[str, list[str]]:
    wrapper = json.loads(raw)
    inner_text = wrapper.get("settings")
    if not isinstance(inner_text, str):
        return raw, []

    settings = parse_jsonc(inner_text)
    if not isinstance(settings, dict):
        raise ValueError("profile.settings.settings is not an object")

    removed = [key for key in list(settings) if should_remove_setting_key(key)]
    for key in removed:
        settings.pop(key, None)

    wrapper["settings"] = json.dumps(settings, indent=2, ensure_ascii=False)
    return json.dumps(wrapper, ensure_ascii=False, separators=(",", ":")), removed


def find_forbidden_patterns(text: str) -> list[str]:
    return [pattern.pattern for pattern in FORBIDDEN_TEXT_PATTERNS if pattern.search(text)]


def sanitize_profile(path: Path, check_only: bool) -> int:
    try:
        profile = json.loads(path.read_text())
    except FileNotFoundError:
        print(f"[sanitize-vscode-profile] skipped: {path} does not exist", file=sys.stderr)
        return 0

    removed: list[str] = []

    if isinstance(profile.get(SETTINGS_KEY), str):
        profile[SETTINGS_KEY], removed_settings = sanitize_settings_blob(profile[SETTINGS_KEY])
        removed.extend(f"settings:{key}" for key in removed_settings)

    if GLOBAL_STATE_KEY in profile:
        profile.pop(GLOBAL_STATE_KEY, None)
        removed.append("globalState:*")

    rendered = json.dumps(profile, ensure_ascii=False, separators=(",", ":")) + "\n"
    forbidden_hits = find_forbidden_patterns(rendered)

    changed = rendered != path.read_text()
    if check_only:
        if removed or forbidden_hits or changed:
            print("[sanitize-vscode-profile] profile needs sanitization", file=sys.stderr)
            for item in removed:
                print(f"  removed: {item}", file=sys.stderr)
            for item in forbidden_hits:
                print(f"  forbidden: {item}", file=sys.stderr)
            return 1
        print("[sanitize-vscode-profile] clean", file=sys.stderr)
        return 0

    if changed:
        path.write_text(rendered)

    if removed:
        print("[sanitize-vscode-profile] removed sensitive entries:", file=sys.stderr)
        for item in removed:
            print(f"  - {item}", file=sys.stderr)
    else:
        print("[sanitize-vscode-profile] no targeted entries removed", file=sys.stderr)

    if forbidden_hits:
        print("[sanitize-vscode-profile] forbidden patterns remain after sanitize:", file=sys.stderr)
        for item in forbidden_hits:
            print(f"  - {item}", file=sys.stderr)
        return 1

    if changed:
        print(f"[sanitize-vscode-profile] updated {path}", file=sys.stderr)
    else:
        print(f"[sanitize-vscode-profile] {path} already clean", file=sys.stderr)

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove sensitive state from a VS Code profile export."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="vscode.code-profile",
        help="Path to the VS Code profile export file.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the file would be modified or forbidden patterns remain.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return sanitize_profile(Path(args.path), args.check)


if __name__ == "__main__":
    raise SystemExit(main())
