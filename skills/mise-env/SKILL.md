---
name: mise-env
description: Use when the user wants project-local environment settings derived from tools already declared in mise.toml. Read mise.toml first, then apply Go env settings when Go is configured, Python virtualenv settings when Python is configured, and add node_modules/.bin to PATH when Node is configured.
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

5. If Python is configured and a `pyproject.toml` exists in the project root, also ensure `mise.toml` contains this exact `[env]` entry so `uv` uses the same environment by default:

```toml
[env]
UV_PROJECT_ENVIRONMENT = ".mise/python/venv"
```

6. If Node is configured, ensure `mise.toml` adds `node_modules/.bin` to `PATH` via `[env]`. Prefer an `_.path` value that includes `node_modules/.bin`, preserving any existing path entries. This should match `direnv layout node`, which only prepends `node_modules/.bin`.
7. If Go, Python, and Node are configured together, apply all required entries in the same `[env]` table.
8. If an `[env]` table already exists, add or update only the required keys and preserve unrelated settings.
9. If `_.path` already exists, preserve existing entries and ensure required additions are present without dropping unrelated paths.
10. If the task also sets or changes tool versions, run `mise use <tool>@<version>` from the project root as needed.
11. If the configured toolchain or virtualenv should exist immediately, run `mise install` only when required, then verify the configured paths resolve under `.mise/go` and `.mise/python/venv`.

## Defaults

- Use `{{config_root}}/.mise/go` for `GOPATH`.
- Use `{{config_root}}/.mise/go/bin` for both `GOBIN` and `_.path`.
- Use `.mise/python/venv` for the Python virtualenv path.
- If `pyproject.toml` exists, use `.mise/python/venv` for `UV_PROJECT_ENVIRONMENT` too.
- Use `node_modules/.bin` as the Node path entry, matching `direnv layout node`.
- Prefer these exact settings unless the repo already uses a different local layout:

```toml
GOPATH = "{{config_root}}/.mise/go"
GOBIN = "{{config_root}}/.mise/go/bin"
_.path = "{{config_root}}/.mise/go/bin"
UV_PROJECT_ENVIRONMENT = ".mise/python/venv"
_.python.venv = { path = ".mise/python/venv", create = true }
```

- If both Go and Node are configured, prefer an `_.path` value that contains both entries, for example:

```toml
_.path = ["{{config_root}}/.mise/go/bin", "node_modules/.bin"]
```

## Notes

- Read `mise.toml` before deciding what to apply.
- Apply Go settings only when Go is configured.
- Apply Python settings only when Python is configured.
- If `pyproject.toml` exists, add `UV_PROJECT_ENVIRONMENT = ".mise/python/venv"` alongside the Python venv setting.
- Apply Node path settings only when Node is configured.
- Apply all relevant settings when multiple tools are configured.
- Preserve unrelated `mise.toml` settings.
- Prefer updating the existing `[env]` table instead of rewriting the file.
- When updating `_.path`, preserve existing entries and add missing required paths.
- If `mise.toml` does not exist, create one only when the task explicitly requires it.
