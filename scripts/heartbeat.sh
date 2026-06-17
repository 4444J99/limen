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
cd "$LIMEN_ROOT" || exit 1

# load local secrets (gemini key, etc.) from the single un-committed secrets file
[ -f "$HOME/.limen.env" ] && { set -a; . "$HOME/.limen.env"; set +a; }

LANES="${LIMEN_LANES:-codex,opencode,agy,claude}"   # gemini auto-joins below iff its key is present
[ -n "${GEMINI_API_KEY:-}" ] && LANES="$LANES,gemini"
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

echo "═══ heartbeat $(date '+%F %T') lanes=$LANES ═══"
bash   "$LIMEN_ROOT/scripts/drain.sh"                              2>&1 | tail -3 || true
python3 "$LIMEN_ROOT/scripts/mine-backlog.py" --limit "$MINE_LIMIT" --apply 2>&1 | tail -3 || true
python3 "$LIMEN_ROOT/scripts/route.py" --apply                    2>&1 | tail -3 || true
python3 "$LIMEN_ROOT/scripts/rebalance.py" --lanes "$LANES" --apply 2>&1 | tail -2 || true
python3 -m limen release-stale --agent jules --hours 24 --apply   2>&1 | tail -2 || true
python3 -m limen dispatch --agent jules --live --limit "$JULES_LIMIT" 2>&1 | tail -4 || true
IFS=',' read -ra A <<< "$LANES"
for v in "${A[@]}"; do
  echo "── lane $v ──"
  python3 -m limen dispatch --agent "$v" --live --limit "$LOCAL_LIMIT" 2>&1 | tail -4 || true
done
python3 -m limen doctor 2>&1 | head -10
echo "═══ heartbeat done $(date '+%F %T') ═══"
