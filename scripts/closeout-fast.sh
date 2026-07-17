#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AMBIENT_PYTHONPATH="${PYTHONPATH:-}"
PYTHONPATH_VALUE="$ROOT/cli/src${AMBIENT_PYTHONPATH:+:$AMBIENT_PYTHONPATH}"
export LIMEN_ROOT="${LIMEN_ROOT:-$ROOT}"
export PYTHONPATH="$PYTHONPATH_VALUE"

TMP_FILES=()
QUEUE_LOCK_HELD=0
cleanup() {
  if ((${#TMP_FILES[@]})); then
    rm -f "${TMP_FILES[@]}"
  fi
  release_queue_lock
}
trap cleanup EXIT

step() {
  printf '\n==> %s\n' "$*"
}

run_and_require_ready() {
  local label="$1"
  shift
  local receipt
  receipt="$(mktemp "${TMPDIR:-/tmp}/limen-closeout-fast.XXXXXX")"
  TMP_FILES+=("$receipt")
  "$@" | tee "$receipt"
  if ! grep -Fq 'Status: `ready`' "$receipt"; then
    printf '\n%s did not report Status: `ready`\n' "$label" >&2
    return 1
  fi
}

acquire_queue_lock() {
  local lockd="$ROOT/logs/.queue.lock.d"
  local waited
  for waited in $(seq 1 "${LIMEN_CLOSEOUT_QUEUE_LOCK_TIMEOUT:-30}"); do
    if mkdir "$lockd" 2>/dev/null; then
      printf '%s\n' "$$" > "$lockd/pid" 2>/dev/null || true
      date -u '+%Y-%m-%dT%H:%M:%SZ' > "$lockd/created_at" 2>/dev/null || true
      QUEUE_LOCK_HELD=1
      return 0
    fi
    sleep 1
  done
  printf 'closeout-fast: queue lock unavailable after %ss\n' "${LIMEN_CLOSEOUT_QUEUE_LOCK_TIMEOUT:-30}" >&2
  return 1
}

release_queue_lock() {
  local lockd="$ROOT/logs/.queue.lock.d"
  if [[ "$QUEUE_LOCK_HELD" == "1" ]]; then
    if [[ "$(cat "$lockd/pid" 2>/dev/null || true)" == "$$" ]]; then
      rm -f "$lockd/pid" "$lockd/created_at" 2>/dev/null || true
      rmdir "$lockd" 2>/dev/null || true
    fi
    QUEUE_LOCK_HELD=0
  fi
}

cd "$ROOT"

step "Validate task board"
acquire_queue_lock
python3 scripts/validate-task-board.py --tasks tasks.yaml

step "Check TABVLARIVS ticket inbox"
python3 scripts/tabularius-organ.py --check

step "Check live-root gate"
run_and_require_ready "live-root-gate" python3 scripts/live-root-gate.py
release_queue_lock

step "Probe dispatch health"
python3 scripts/dispatch-health.py --probe-async

step "Check branch reap debt"
python3 scripts/reap-branches.py --check

step "Check parameter registry"
python3 scripts/check-params.py

step "Run closeout smoke tests"
python3 -m py_compile cli/src/limen/worktree_debt.py scripts/session-lifecycle-pressure.py
python3 -m pytest \
  cli/tests/test_worktree_debt.py::test_reachable_from_remote_uses_single_contains_query \
  -q

if [[ "${LIMEN_CLOSEOUT_RUN_LIFECYCLE_TESTS:-0}" == "1" ]]; then
  step "Run opt-in lifecycle regression tests"
  timeout "${LIMEN_CLOSEOUT_LIFECYCLE_TEST_TIMEOUT:-90}" \
    python3 -m pytest cli/tests/test_worktree_debt.py cli/tests/test_session_lifecycle_pressure.py -q
else
  step "Skip opt-in lifecycle regression tests"
  printf 'set LIMEN_CLOSEOUT_RUN_LIFECYCLE_TESTS=1 to run the slower lifecycle pytest tranche\n'
fi

step "Reconcile closeout claims (claimed-done vs ground truth)"
if [[ "${LIMEN_SESSION_CLOSEOUT:-0}" == "1" ]]; then
  python3 scripts/reconcile-closeouts.py --check
else
  python3 scripts/reconcile-closeouts.py --doctor >/dev/null \
    && printf '  (closeout-reconcile dark; classifier OK — set LIMEN_SESSION_CLOSEOUT=1 to enforce --check)\n'
fi

printf '\nFast closeout verification passed\n'
