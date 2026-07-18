#!/usr/bin/env bash
# session-lifecycle-pressure.sh — SessionEnd hook for local/remote lifecycle pressure.
#
# Refreshes ignored logs/session-lifecycle-pressure.{json,md} so the next session's
# orientation can show whether local disk pressure is returning to lean after work
# has been preserved remotely. Fail-open and non-blocking by construction.
set -u

SCRIPT_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")/../.." rev-parse --show-toplevel 2>/dev/null || true)"
ROOT="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$ROOT" ] || [ ! -f "$ROOT/scripts/session-lifecycle-pressure.py" ]; then
  ROOT="$SCRIPT_ROOT"
fi
[ -z "$ROOT" ] && exit 0
GEN="$ROOT/scripts/session-lifecycle-pressure.py"
[ -f "$GEN" ] || exit 0
LOCK_DIR="${TMPDIR:-/tmp}/limen-session-lifecycle-pressure.lock"
HOOK_TIMEOUT="${LIMEN_SESSION_LIFECYCLE_TIMEOUT:-45}"
DEBT_TIMEOUT="${LIMEN_SESSION_WORKTREE_DEBT_TIMEOUT:-30}"
[[ "$HOOK_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || HOOK_TIMEOUT=45
[[ "$DEBT_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || DEBT_TIMEOUT=30

acquire_pressure_lock() {
  local owner_pid created_at now
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "${BASHPID:-$$}" > "$LOCK_DIR/pid"
    date +%s > "$LOCK_DIR/created_at"
    return 0
  fi
  owner_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ "$owner_pid" =~ ^[0-9]+$ ]] && kill -0 "$owner_pid" 2>/dev/null; then
    return 1
  fi
  created_at="$(cat "$LOCK_DIR/created_at" 2>/dev/null || true)"
  now="$(date +%s)"
  if [[ "$owner_pid" =~ ^[0-9]+$ ]] || \
     { [[ "$created_at" =~ ^[0-9]+$ ]] && ((now - created_at > HOOK_TIMEOUT * 2)); }; then
    rm -f "$LOCK_DIR/pid" "$LOCK_DIR/created_at" 2>/dev/null || true
    rmdir "$LOCK_DIR" 2>/dev/null || return 1
    mkdir "$LOCK_DIR" 2>/dev/null || return 1
    printf '%s\n' "${BASHPID:-$$}" > "$LOCK_DIR/pid"
    date +%s > "$LOCK_DIR/created_at"
    return 0
  fi
  return 1
}

release_pressure_lock() {
  if [[ "$(cat "$LOCK_DIR/pid" 2>/dev/null || true)" == "${BASHPID:-$$}" ]]; then
    rm -f "$LOCK_DIR/pid" "$LOCK_DIR/created_at" 2>/dev/null || true
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
}

run_pressure_bounded() {
  python3 - "$HOOK_TIMEOUT" "$@" <<'PY'
import os
import signal
import subprocess
import sys

timeout = int(sys.argv[1])
process = subprocess.Popen(sys.argv[2:], start_new_session=True)
try:
    raise SystemExit(process.wait(timeout=timeout))
except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    raise SystemExit(124)
PY
}

(
  acquire_pressure_lock || exit 0
  trap release_pressure_lock EXIT
  if command -v python3 >/dev/null 2>&1; then
    export LIMEN_WORKTREE_DEBT_TIMEOUT="$DEBT_TIMEOUT"
    run_pressure_bounded nice -n 10 python3 "$GEN" --write || true
  fi
) >/dev/null 2>&1 </dev/null &

exit 0
