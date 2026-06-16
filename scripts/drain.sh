#!/usr/bin/env bash
# Drain the Jules lane: pull completed remote sessions, then harvest-close them.
# Env-parameterized so it survives a later relocation of the conductor (set LIMEN_ROOT).
# Safe/idempotent: pulls diffs (no --apply), closes completed tasks, never dispatches.
set -euo pipefail
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
PY="$LIMEN_ROOT/cli/src"

echo "[drain] pulling completed Jules sessions…"
python3 "$LIMEN_ROOT/scripts/harvest-pull-completed.py"

echo "[drain] harvesting…"
PYTHONPATH="$PY" python3 -m limen harvest --agent jules

echo "[drain] board:"
PYTHONPATH="$PY" python3 -m limen doctor 2>&1 | head -9
