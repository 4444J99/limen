#!/usr/bin/env bash
# Codex/Claude hook wrapper for repo-local hook scripts.
#
# Resolves the Limen root without assuming CLAUDE_PROJECT_DIR is set, then
# exports both CLAUDE_PROJECT_DIR and CODEX_PROJECT_DIR for the legacy scripts.
# Missing advisory targets are diagnostic no-ops. Mandatory admission retains
# its registered event even when the policy entrypoint is unavailable.
set -uo pipefail

hook_name="${1:-}"
shift 2>/dev/null || true

log() {
  printf 'limen-hook[%s]: %s\n' "${hook_name:-unknown}" "$*" >&2
}

unavailable() {
  log "$1"
  if [[ "$hook_name" == "host-admission" ]]; then
    local registered_event="" previous="" argument
    for argument in "${@:2}"; do
      if [[ "$previous" == "--event" ]]; then registered_event="$argument"; fi
      previous="$argument"
    done
    case "$registered_event" in
      Stop|UserPromptSubmit|SubagentStart) ;;
      *)
        printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Limen mandatory admission entrypoint unavailable"}}'
        ;;
    esac
  fi
  exit 0
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
  unavailable "no project root resolved" "$@"
}

case "$hook_name" in
  session-orient)
    target="$root/scripts/hooks/session-orient.sh"
    ;;
  lint-edited-file)
    target="$root/scripts/hooks/lint-edited-file.sh"
    ;;
  no-hand-poll)
    target="$root/scripts/hooks/no-hand-poll-guard.sh"
    ;;
  host-admission)
    target="$root/scripts/hooks/codex-host-admission.py"
    immutable_target="${LIMEN_IMMUTABLE_ADMISSION_ENTRYPOINT:-$HOME/.local/share/limen/current/source/scripts/hooks/codex-host-admission.py}"
    ;;
  stop-governor)
    # Advisory and fail-open: it never goes through the immutable admission delegate.
    target="$root/scripts/hooks/stop-governor.sh"
    set -- --vendor codex "$@"
    ;;
  *)
    log "unknown hook target; skipping"
    exit 0
    ;;
esac

if [[ ! -f "$target" ]]; then
  unavailable "missing hook script" "$@"
fi

export CLAUDE_PROJECT_DIR="$root"
export CODEX_PROJECT_DIR="${CODEX_PROJECT_DIR:-$root}"

if [[ "$target" == *.py ]]; then
  command -v python3 >/dev/null 2>&1 || unavailable "missing Python interpreter" "$@"
  if [[ "$hook_name" == "host-admission" ]]; then
    exec python3 "$target" --delegate-immutable "$immutable_target" "$@"
  fi
  exec python3 "$target" "$@"
fi

if [[ -x "$target" ]]; then
  exec "$target" "$@"
fi

log "script is not executable, running with bash: $target"
exec bash "$target" "$@"
