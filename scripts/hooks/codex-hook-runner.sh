#!/usr/bin/env bash
# Codex/Claude hook wrapper for repo-local hook scripts.
#
# Resolves the Limen root without assuming CLAUDE_PROJECT_DIR is set, then
# exports both CLAUDE_PROJECT_DIR and CODEX_PROJECT_DIR for the legacy scripts.
# Missing targets are diagnostic no-ops so startup/edit hooks stay fail-open.
set -uo pipefail

hook_name="${1:-}"
shift 2>/dev/null || true

log() {
  printf 'limen-hook[%s]: %s\n' "${hook_name:-unknown}" "$*" >&2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
script_root="$(cd -- "$script_dir/../.." >/dev/null 2>&1 && pwd -P)"

resolve_root() {
  local candidate
  for candidate in \
    "${CODEX_PROJECT_DIR:-}" \
    "${CLAUDE_PROJECT_DIR:-}" \
    "$(git rev-parse --show-toplevel 2>/dev/null || true)" \
    "$script_root"; do
    if [[ -n "$candidate" && -d "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

root="$(resolve_root)" || {
  log "no project root resolved; skipping"
  exit 0
}

case "$hook_name" in
  session-orient)
    target="$root/scripts/hooks/session-orient.sh"
    ;;
  lint-edited-file)
    target="$root/scripts/hooks/lint-edited-file.sh"
    ;;
  host-admission)
    target="$root/scripts/hooks/codex-host-admission.py"
    ;;
  *)
    log "unknown hook target; skipping"
    exit 0
    ;;
esac

if [[ ! -f "$target" ]]; then
  log "missing script: $target"
  exit 0
fi

export CLAUDE_PROJECT_DIR="$root"
export CODEX_PROJECT_DIR="${CODEX_PROJECT_DIR:-$root}"

if [[ "$target" == *.py ]]; then
  exec python3 "$target" "$@"
fi

if [[ -x "$target" ]]; then
  exec "$target" "$@"
fi

log "script is not executable, running with bash: $target"
exec bash "$target" "$@"
