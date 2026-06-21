#!/usr/bin/env bash
# Drain the Jules lane: pull completed remote sessions, LAND them as PRs (#18), harvest-close.
# Env-parameterized so it survives a later relocation of the conductor (set LIMEN_ROOT).
# Idempotent: jules-land skips repos with no checkout + sessions already landed (dup-safe via
# the PR-URL backfill in dispatch_log). Set LIMEN_JULES_LAND=0 for the old pull-only behavior.
# NEVER-"NO" INVARIANT: drain is a sequence of INDEPENDENT best-effort organ steps (jules-land,
# harvest, merge-drain, self-heal). Drop `-e` so one step failing (e.g. a transient pydantic load
# error in `limen harvest`) can NEVER abort the rest — the merge + heal organs must run every beat.
# Keep -u/pipefail for safety; every step is individually guarded with `|| true`.
set -uo pipefail
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
PY="$LIMEN_ROOT/cli/src"

# Runtime organ toggles (LIMEN_SELF_HEAL, LIMEN_MERGE_DRAIN, LIMEN_JULES_LAND, …): the daemon
# re-reads this script fresh each beat, so sourcing ~/.limen.env HERE lets an organ be switched
# on/off live without restarting the heartbeat. Existence-guarded; set -a exports the vars.
[ -f "$HOME/.limen.env" ] && { set -a; . "$HOME/.limen.env"; set +a; }

echo "[drain] pulling completed Jules sessions…"
python3 "$LIMEN_ROOT/scripts/harvest-pull-completed.py" 2>&1 | tail -4 || true

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
PYTHONPATH="$PY" python3 -m limen harvest --agent jules 2>&1 | tail -4 || true

# MERGE the landed/dispatched PRs — the missing autonomic organ. Bounded per beat so it never
# dominates the cycle; merges ONLY mergeable+CI-green, never force-merges; idempotent vs other
# agents (already-merged is counted, not an error). Touches only GitHub, not tasks.yaml/worktrees.
# On by default for the live daemon (already authorized to open PRs); LIMEN_MERGE_DRAIN=0 disables.
if [ "${LIMEN_MERGE_DRAIN:-1}" = "1" ]; then
  echo "[drain] merging READY PRs (scan ${LIMEN_MERGE_SCAN:-30}, limit ${LIMEN_MERGE_LIMIT:-10})…"
  PYTHONPATH="$PY" python3 "$LIMEN_ROOT/scripts/merge-drain.py" \
      --scan "${LIMEN_MERGE_SCAN:-30}" --limit "${LIMEN_MERGE_LIMIT:-10}" 2>&1 | tail -3 || true
fi

# SELF-HEAL — emit targeted heal tasks for the PRs merge-drain just REFUSED (CI-RED / CONFLICT)
# so the dispatcher repairs them in a worktree → they turn mergeable → merge-drain lands them next
# beat → the open-PR floor finally falls. Emits via the same atomic queue-lock path the daemon uses
# (cannot race tasks.yaml); bounded + idempotent. OFF by default — set LIMEN_SELF_HEAL=1 to enable
# live emission (it WRITES heal tasks to the queue); use --dry-run to preview without writing.
if [ "${LIMEN_SELF_HEAL:-0}" = "1" ]; then
  echo "[drain] emitting heal tasks for stuck PRs (scan ${LIMEN_HEAL_SCAN:-30}, limit ${LIMEN_HEAL_LIMIT:-10})…"
  PYTHONPATH="$PY" python3 "$LIMEN_ROOT/scripts/self-heal.py" \
      --scan "${LIMEN_HEAL_SCAN:-30}" --limit "${LIMEN_HEAL_LIMIT:-10}" 2>&1 | tail -3 || true
fi

echo "[drain] board:"
PYTHONPATH="$PY" python3 -m limen doctor 2>&1 | head -9
