#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AMBIENT_PYTHONPATH="${PYTHONPATH:-}"
PYTHONPATH_VALUE="$ROOT/cli/src${AMBIENT_PYTHONPATH:+:$AMBIENT_PYTHONPATH}"
export LIMEN_ROOT="${LIMEN_ROOT:-$ROOT}"
export PYTHONPATH="$PYTHONPATH_VALUE"

step() {
  printf '\n==> %s\n' "$*"
}

cd "$ROOT"

step "Validate task board"
python3 scripts/validate-task-board.py --tasks tasks.yaml

step "Check TABVLARIVS ticket inbox"
python3 scripts/tabularius-organ.py --check

step "Check live-root gate"
python3 scripts/live-root-gate.py

step "Probe dispatch health"
python3 scripts/dispatch-health.py --probe-async

step "Check branch reap debt"
python3 scripts/reap-branches.py --check

step "Check parameter registry"
python3 scripts/check-params.py

step "Run focused lifecycle tests"
python3 -m pytest cli/tests/test_worktree_debt.py cli/tests/test_session_lifecycle_pressure.py -q

printf '\nFast closeout verification passed\n'
