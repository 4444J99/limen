#!/usr/bin/env bash
# heartbeat.sh — the autonomic cycle (rung 1: self-sustaining + self-feeding).
#
#   drain -> mine -> route -> rebalance -> release-stale -> dispatch(jules + all live
#   local lanes) -> board.
#
# Designed to be fired by launchd/cron on a timer with NO human present. Every local
# dispatch is worktree-isolated -> reviewable PR, never touches a live checkout.
# Outward volume is bounded by the per-day budgets in tasks.yaml (jules 100, locals 50
# each); firing more often cannot exceed them. Shares the saturate lock so ticks never
# overlap each other or a manual saturate run.
set -uo pipefail
export HOME="${HOME:-/Users/4jp}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
export LIMEN_WORKDIR="${LIMEN_WORKDIR:-$HOME/Workspace}"
export LIMEN_ISOLATION="${LIMEN_ISOLATION:-worktree}"
export PYTHONPATH="$LIMEN_ROOT/cli/src"
export GEMINI_CLI_TRUST_WORKSPACE="${GEMINI_CLI_TRUST_WORKSPACE:-true}"  # gemini runs headless in throwaway worktrees
cd "$LIMEN_ROOT" || exit 1

SESSION_END_SOURCE="${LIMEN_SESSION_END_BREADCRUMBS:-${XDG_STATE_HOME:-$HOME/.local/state}/limen/session-end-breadcrumbs.jsonl}"

# SessionEnd itself is constant-time; this heartbeat-owned drain performs the
# slow closeout consumers with finite retries and bounded receipts.
timeout "${LIMEN_SESSION_END_CONSUMER_TIMEOUT:-90}" \
  python3 "$LIMEN_ROOT/scripts/consume-session-end-breadcrumbs.py" \
    --source "$SESSION_END_SOURCE" \
    --max-sessions "${LIMEN_SESSION_END_CONSUMER_BATCH:-8}" \
    --runway-seconds "${LIMEN_SESSION_END_CONSUMER_RUNWAY:-60}" 2>&1 | tail -1 || true

MODE="$(python3 "$LIMEN_ROOT/scripts/autonomy-governor.py" mode 2>/dev/null || echo paused)"
if [ "$MODE" = "paused" ]; then
  echo "heartbeat paused by autonomy governor"
  exit 0
fi

# load local secrets (gemini key, etc.) from the single un-committed secrets file
[ -f "$HOME/.limen.env" ] && { set -a; . "$HOME/.limen.env"; set +a; }
if [ -z "${LIMEN_WORKTREES:-}" ]; then
  if [ -d /Volumes/Scratch ] && [ -w /Volumes/Scratch ]; then
    export LIMEN_WORKTREES="/Volumes/Scratch/limen-worktrees"
  else
    export LIMEN_WORKTREES="$LIMEN_WORKDIR/.limen-worktrees"
  fi
else
  export LIMEN_WORKTREES
fi
export LIMEN_WORKTREE_ROOT="${LIMEN_WORKTREE_ROOT:-$LIMEN_WORKTREES}"
mkdir -p "$LIMEN_WORKTREES" "$LIMEN_WORKTREE_ROOT" 2>/dev/null || true

LANES="${LIMEN_LANES:-codex,opencode,agy,claude,gemini}"   # local-lane preference/display
DISPATCH_LANES="${LIMEN_DISPATCH_LANES:-auto}"
LOCAL_LIMIT="${LIMEN_LOCAL_LIMIT:-50}"
JULES_LIMIT="${LIMEN_JULES_LIMIT:-100}"
MINE_LIMIT="${LIMEN_MINE_LIMIT:-25}"
mkdir -p "$LIMEN_ROOT/logs"
LOCK="$LIMEN_ROOT/logs/.saturate.lock"

# single-instance guard, shared with saturate.sh (macOS has no flock -> mkdir fallback)
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK"; flock -n 9 || { echo "$(date '+%F %T') lock held — skip tick"; exit 0; }
else
  mkdir "$LOCK.d" 2>/dev/null || { echo "$(date '+%F %T') lock held — skip tick"; exit 0; }
  trap 'rmdir "$LOCK.d" 2>/dev/null' EXIT
fi

resolve_dispatch_lanes() {
  python3 - "$1" <<'PY'
import os
import sys
from pathlib import Path
from limen.capacity import select_lanes
from limen.dispatch import _down_lanes
from limen.io import load_limen_file

root = Path(os.environ.get("LIMEN_ROOT", str(Path.home() / "Workspace" / "limen")))
tasks = Path(os.environ.get("LIMEN_TASKS", str(root / "tasks.yaml")))
try:
    board = load_limen_file(tasks)
except Exception:
    board = None
print(",".join(select_lanes(sys.argv[1], board, down_lanes=_down_lanes())))
PY
}

echo "═══ heartbeat $(date '+%F %T') lanes=$LANES dispatch_lanes=$DISPATCH_LANES ═══"
python3 "$LIMEN_ROOT/scripts/usage-telemetry.py"                    2>&1 | tail -2 || true
python3 "$LIMEN_ROOT/scripts/token-value-gauge.py"                 2>&1 | tail -2 || true
if [ "$MODE" != "dispatch" ]; then
  echo "autonomy mode=$MODE — telemetry/status only; queue mutation and dispatch skipped"
  python3 "$LIMEN_ROOT/scripts/emit-tick.py" 2>&1 | tail -1 || true
  python3 -m limen doctor 2>&1 | head -10
  echo "═══ heartbeat done $(date '+%F %T') ═══"
  exit 0
fi

bash   "$LIMEN_ROOT/scripts/drain.sh"                              2>&1 | tail -3 || true
python3 "$LIMEN_ROOT/scripts/mine-backlog.py" --limit "$MINE_LIMIT" --apply 2>&1 | tail -3 || true
python3 "$LIMEN_ROOT/scripts/route.py" --apply                    2>&1 | tail -3 || true
python3 "$LIMEN_ROOT/scripts/rebalance.py" --lanes "$LANES" --apply 2>&1 | tail -2 || true
python3 -m limen release-stale --agent jules --hours 24 --apply   2>&1 | tail -2 || true
EFFECTIVE_DISPATCH_LANES="$(resolve_dispatch_lanes "$DISPATCH_LANES")"
echo "── dispatch selector $DISPATCH_LANES -> ${EFFECTIVE_DISPATCH_LANES:-none} ──"
IFS=',' read -ra A <<< "$EFFECTIVE_DISPATCH_LANES"
for v in "${A[@]}"; do
  echo "── lane $v ──"
  if [ "$v" = "jules" ]; then
    python3 -m limen dispatch --agent "$v" --live --limit "$JULES_LIMIT" 2>&1 | tail -4 || true
  else
    python3 -m limen dispatch --agent "$v" --live --limit "$LOCAL_LIMIT" 2>&1 | tail -4 || true
  fi
done
echo "── clone lifecycle hygiene (worktree prune + gc --auto + reap-report) ──"
bash "$LIMEN_ROOT/scripts/clone-maintenance.sh" 2>&1 | tail -6 || true
python3 "$LIMEN_ROOT/scripts/emit-tick.py" 2>&1 | tail -1 || true
python3 -m limen doctor 2>&1 | head -10
echo "═══ heartbeat done $(date '+%F %T') ═══"
