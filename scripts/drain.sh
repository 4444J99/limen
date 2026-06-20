#!/usr/bin/env bash
# Drain the Jules lane: pull completed remote sessions, LAND them as PRs (#18), harvest-close.
# Env-parameterized so it survives a later relocation of the conductor (set LIMEN_ROOT).
# Idempotent: jules-land skips repos with no checkout + sessions already landed (dup-safe via
# the PR-URL backfill in dispatch_log). Set LIMEN_JULES_LAND=0 for the old pull-only behavior.
set -euo pipefail
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
PY="$LIMEN_ROOT/cli/src"

echo "[drain] pulling completed Jules sessions…"
python3 "$LIMEN_ROOT/scripts/harvest-pull-completed.py"

# #18: LAND completed jules sessions as PRs (the jules→PR gap). Bounded per beat so it never
# dominates the cycle; skips repos with no local checkout (clone-maintenance handles those).
# Same isolation keystone as local dispatch (throwaway worktree). On by default for the live
# daemon (already authorized to open PRs via dispatch); set LIMEN_JULES_LAND=0 to disable.
if [ "${LIMEN_JULES_LAND:-1}" = "1" ]; then
  echo "[drain] landing completed jules sessions as PRs (limit ${LIMEN_JULES_LAND_LIMIT:-3})…"
  PYTHONPATH="$PY" python3 "$LIMEN_ROOT/scripts/jules-land.py" --apply --recover \
      --limit "${LIMEN_JULES_LAND_LIMIT:-3}" 2>&1 | tail -4 || true
fi

echo "[drain] harvesting…"
PYTHONPATH="$PY" python3 -m limen harvest --agent jules

echo "[drain] board:"
PYTHONPATH="$PY" python3 -m limen doctor 2>&1 | head -9
