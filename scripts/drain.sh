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
stamp_voice() {
  mkdir -p "$LIMEN_ROOT/logs/.voice" 2>/dev/null || true
  printf '%s\n' "$(date -u +%FT%TZ)" > "$LIMEN_ROOT/logs/.voice/$1" 2>/dev/null || true
}

if [ "${1:-}" = "--census" ]; then
  python3 - "$LIMEN_ROOT" "$LIMEN_TASKS" <<'PY'
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
tasks_path = Path(sys.argv[2])


def enabled(name: str, default: str) -> bool:
    return os.environ.get(name, default) == "1"


status_counts = {}
try:
    import yaml

    data = yaml.safe_load(tasks_path.read_text()) or {}
    tasks = data.get("tasks", []) if isinstance(data, dict) else []
    for task in tasks:
        if isinstance(task, dict):
            status = str(task.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
except Exception:
    try:
        for line in tasks_path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("status:"):
                status = stripped.split(":", 1)[1].strip() or "unknown"
                status_counts[status] = status_counts.get(status, 0) + 1
    except Exception:
        status_counts = {}

print(
    json.dumps(
        {
            "tasks_present": tasks_path.exists(),
            "task_status_counts": status_counts,
            "logs_present": (root / "logs").exists(),
            "voice_dir_present": (root / "logs" / ".voice").exists(),
            "jules_land_enabled": enabled("LIMEN_JULES_LAND", "1"),
            "merge_drain_enabled": enabled("LIMEN_MERGE_DRAIN", "1"),
            "self_heal_enabled": enabled("LIMEN_SELF_HEAL", "1"),
            "converge_enabled": enabled("LIMEN_CONVERGE", "0"),
            "reclaim_enabled": enabled("LIMEN_RECLAIM", "1"),
            "reclaim_apply_enabled": enabled("LIMEN_RECLAIM_APPLY", "1"),
        },
        indent=2,
        sort_keys=True,
    )
)
PY
  exit 0
fi

echo "[drain] pulling completed Jules sessions…"
python3 "$LIMEN_ROOT/scripts/harvest-pull-completed.py" 2>&1 | tail -4 || true

# #18: LAND completed jules sessions as PRs (the jules→PR gap). Bounded per beat so it never
# dominates the cycle; skips repos with no local checkout (clone-maintenance handles those).
# Same isolation keystone as local dispatch. The isolated root is retained after PR creation and
# later reclaimed only by the receipt-backed reclaim/reap organs; set LIMEN_JULES_LAND=0 to disable.
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
  stamp_voice merge
fi

# SELF-HEAL — emit targeted heal tasks for the PRs merge-drain just REFUSED (CI-RED / CONFLICT)
# so the dispatcher repairs them in a worktree → they turn mergeable → merge-drain lands them next
# beat → the open-PR floor finally falls. Emits via the same atomic queue-lock path the daemon uses
# (cannot race tasks.yaml); bounded (limit 10) + idempotent (same id = no dup). ON by default — this
# is what closes the HEAL rung (the dispatcher is already authorized to open PRs); set
# LIMEN_SELF_HEAL=0 to disable, or run self-heal.py --dry-run to preview without writing.
if [ "${LIMEN_SELF_HEAL:-1}" = "1" ] && [ "${LIMEN_QUEUE_LOCK_HELD:-0}" != "1" ]; then
  echo "[drain] emitting heal tasks for stuck PRs (scan ${LIMEN_HEAL_SCAN:-30}, limit ${LIMEN_HEAL_LIMIT:-10})…"
  PYTHONPATH="$PY" python3 "$LIMEN_ROOT/scripts/self-heal.py" \
      --scan "${LIMEN_HEAL_SCAN:-30}" --limit "${LIMEN_HEAL_LIMIT:-10}" 2>&1 | tail -3 || true
elif [ "${LIMEN_SELF_HEAL:-1}" = "1" ]; then
  echo "[drain] self-heal skipped under queue lock; heartbeat runs it after release"
fi

# CONVERGE — the alchemical rung that completes the self-* ladder. Finds "multiverses" (one idea a
# task with >=2 divergent PRs from different lanes), distills them via limen.converge, and emits the
# gap-finder's next_shots as bounded NEW work. Offline by default (no network); only writes bounded
# gap-tasks + logs/converge-log.jsonl under the queue lock — NEVER closes/merges PRs (his/merge gate).
# OFF by default (newest organ) — set LIMEN_CONVERGE=1 to enable; LIMEN_CONVERGE_LIVE=1 for real
# Anthropic synthesis. ([[alchemical-convergence-method]], [[distillation-not-reduction]])
if [ "${LIMEN_CONVERGE:-0}" = "1" ]; then
  echo "[drain] converge: distilling multiverses (limit ${LIMEN_CONVERGE_LIMIT:-2})…"
  PYTHONPATH="$PY" python3 "$LIMEN_ROOT/scripts/converge-organ.py" --apply \
      --limit "${LIMEN_CONVERGE_LIMIT:-2}" 2>&1 | tail -3 || true
fi

# RECLAIM — remove provably-dead fleet worktrees (clean + content-preserved-on-default + idle)
# from every known worktree root, so session clones cannot silently accumulate.
# Visibility is ON by default. Safe removal is ON by default; set LIMEN_RECLAIM_APPLY=0 for
# preview-only operation. ([[known-owned-pervasive-then-idgaf]], [[storage-autonomic-solve]])
if [ "${LIMEN_RECLAIM:-1}" = "1" ]; then
  if [ "${LIMEN_QUEUE_LOCK_HELD:-0}" = "1" ]; then
    echo "[drain] reclaim skipped under queue lock; heartbeat runs it after release"
  else
    reclaim_args=()
    [ "${LIMEN_RECLAIM_APPLY:-1}" = "1" ] && reclaim_args+=(--apply)
    PYTHONPATH="$PY" python3 "$LIMEN_ROOT/scripts/reclaim-worktrees.py" --generated-only "${reclaim_args[@]}" 2>&1 | tail -4 || true
    PYTHONPATH="$PY" python3 "$LIMEN_ROOT/scripts/reclaim-worktrees.py" "${reclaim_args[@]}" 2>&1 | tail -4 || true
  fi
fi

echo "[drain] board:"
PYTHONPATH="$PY" python3 -m limen doctor 2>&1 | head -9
