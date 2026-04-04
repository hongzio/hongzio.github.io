---
name: mise-env
description: Use when the user wants project-local environment settings derived from tools already declared in mise.toml. Read mise.toml first, then apply Go env settings when Go is configured and apply Python virtualenv settings when Python is configured. If both Go and Python are present, apply both.
---

# Mise Env

Use this skill when a task involves `mise.toml` and the repo should automatically get local environment settings based on configured tools.

## Workflow

1. Inspect `mise.toml` if it exists.
2. Detect which tools are already configured under `[tools]` or equivalent mise settings.
3. If Go is configured, ensure `mise.toml` contains these exact `[env]` entries:

```toml
[env]
GOPATH = "{{config_root}}/.mise/go"
GOBIN = "{{config_root}}/.mise/go/bin"
_.path = "{{config_root}}/.mise/go/bin"
```

4. If Python is configured, ensure `mise.toml` contains this exact `[env]` entry:

```toml
[env]
_.python.venv = { path = ".mise/python/venv", create = true }
```

5. If both Go and Python are configured, apply both sets of entries in the same `[env]` table.
6. If an `[env]` table already exists, add or update only the required keys and preserve unrelated settings.
7. If the task also sets or changes tool versions, run `mise use <tool>@<version>` from the project root as needed.
8. If the configured toolchain or virtualenv should exist immediately, run `mise install` only when required, then verify the configured paths resolve under `.mise/go` and `.mise/python/venv`.

## Defaults

- Use `{{config_root}}/.mise/go` for `GOPATH`.
- Use `{{config_root}}/.mise/go/bin` for both `GOBIN` and `_.path`.
- Use `.mise/python/venv` for the Python virtualenv path.
- Prefer these exact settings unless the repo already uses a different local layout:

```toml
GOPATH = "{{config_root}}/.mise/go"
GOBIN = "{{config_root}}/.mise/go/bin"
_.path = "{{config_root}}/.mise/go/bin"
_.python.venv = { path = ".mise/python/venv", create = true }
```

## Notes

- Read `mise.toml` before deciding what to apply.
- Apply Go settings only when Go is configured.
- Apply Python settings only when Python is configured.
- Apply both when both tools are configured.
- Preserve unrelated `mise.toml` settings.
- Prefer updating the existing `[env]` table instead of rewriting the file.
- If `mise.toml` does not exist, create one only when the task explicitly requires it.
