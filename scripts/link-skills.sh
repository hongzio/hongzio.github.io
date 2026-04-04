#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_SKILLS_DIR="${REPO_ROOT}/skills"

# Add new target roots here as needed.
DEFAULT_TARGET_ROOTS=(
  "${HOME}/.codex"
  "${HOME}/.claude"
)

usage() {
  cat <<'EOF'
Usage:
  scripts/link-skills.sh link [target-root ...]
  scripts/link-skills.sh unlink [target-root ...]
  scripts/link-skills.sh --help

Link or unlink this repo's skill directories in each existing target root.

Defaults:
  ~/.codex
  ~/.claude

Examples:
  scripts/link-skills.sh link
  scripts/link-skills.sh link ~/.codex ~/.claude
  scripts/link-skills.sh unlink
  scripts/link-skills.sh link ~/.codex ~/.another-tool
EOF
}

log() {
  printf '%s\n' "$*"
}

warn() {
  printf 'warning: %s\n' "$*" >&2
}

prune_stale_links() {
  local target_skills_dir="$1"
  local target_link resolved_link

  [[ -d "${target_skills_dir}" ]] || return 0

  for target_link in "${target_skills_dir}"/*; do
    [[ -L "${target_link}" ]] || continue

    resolved_link="$(readlink "${target_link}")"
    if [[ "${resolved_link}" == "${SOURCE_SKILLS_DIR}/"* && ! -e "${resolved_link}" ]]; then
      rm "${target_link}"
      log "removed stale link: ${target_link}"
    fi
  done
}

if [[ ! -d "${SOURCE_SKILLS_DIR}" ]]; then
  warn "source skills directory not found: ${SOURCE_SKILLS_DIR}"
  exit 1
fi

link_skills() {
  local target_roots=()
  local linked_any_root=0
  local target_root expanded_root target_skills_dir skill_dir skill_name target_link

  if [[ "$#" -gt 0 ]]; then
    target_roots=("$@")
  else
    target_roots=("${DEFAULT_TARGET_ROOTS[@]}")
  fi

  for target_root in "${target_roots[@]}"; do
    expanded_root="${target_root/#\~/${HOME}}"

    if [[ ! -d "${expanded_root}" ]]; then
      log "skip: target root does not exist: ${expanded_root}"
      continue
    fi

    linked_any_root=1
    target_skills_dir="${expanded_root}/skills"
    mkdir -p "${target_skills_dir}"
    log "target: ${target_skills_dir}"
    prune_stale_links "${target_skills_dir}"

    for skill_dir in "${SOURCE_SKILLS_DIR}"/*; do
      [[ -d "${skill_dir}" ]] || continue

      skill_name="$(basename "${skill_dir}")"
      target_link="${target_skills_dir}/${skill_name}"

      if [[ -e "${target_link}" && ! -L "${target_link}" ]]; then
        warn "skip existing non-symlink path: ${target_link}"
        continue
      fi

      ln -sfn "${skill_dir}" "${target_link}"
      log "linked: ${target_link} -> ${skill_dir}"
    done
  done

  if [[ "${linked_any_root}" -eq 0 ]]; then
    warn "no target roots were processed"
    exit 1
  fi
}

unlink_skills() {
  local target_roots=()
  local processed_any_root=0
  local target_root expanded_root target_skills_dir skill_dir skill_name target_link resolved_link

  if [[ "$#" -gt 0 ]]; then
    target_roots=("$@")
  else
    target_roots=("${DEFAULT_TARGET_ROOTS[@]}")
  fi

  for target_root in "${target_roots[@]}"; do
    expanded_root="${target_root/#\~/${HOME}}"

    if [[ ! -d "${expanded_root}" ]]; then
      log "skip: target root does not exist: ${expanded_root}"
      continue
    fi

    processed_any_root=1
    target_skills_dir="${expanded_root}/skills"

    if [[ ! -d "${target_skills_dir}" ]]; then
      log "skip: target skills directory does not exist: ${target_skills_dir}"
      continue
    fi

    log "target: ${target_skills_dir}"

    for skill_dir in "${SOURCE_SKILLS_DIR}"/*; do
      [[ -d "${skill_dir}" ]] || continue

      skill_name="$(basename "${skill_dir}")"
      target_link="${target_skills_dir}/${skill_name}"

      if [[ ! -L "${target_link}" ]]; then
        continue
      fi

      resolved_link="$(readlink "${target_link}")"
      if [[ "${resolved_link}" == "${skill_dir}" ]]; then
        rm "${target_link}"
        log "unlinked: ${target_link}"
      fi
    done
  done

  if [[ "${processed_any_root}" -eq 0 ]]; then
    warn "no target roots were processed"
    exit 1
  fi
}

COMMAND="${1:-link}"

case "${COMMAND}" in
  -h|--help)
    usage
    ;;
  link)
    shift || true
    link_skills "$@"
    ;;
  unlink)
    shift || true
    unlink_skills "$@"
    ;;
  *)
    warn "unknown command: ${COMMAND}"
    usage
    exit 1
    ;;
esac
