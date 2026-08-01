#!/usr/bin/env bash
# heartbeat.sh — one bounded wake/monitor cycle for the canonical campaign.
#
#   closeout drain -> telemetry -> campaign supervisor wake -> lifecycle hygiene -> status.
#
# Designed to be fired by launchd/cron on a timer with NO human present. This legacy
# entrypoint does not choose providers or launch workers. It may only wake the admitted,
# finite institutional campaign, whose canonical supervisor derives live capabilities and
# submits keeper-owned packets. Shares the saturate lock so ticks never overlap.
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
SESSION_END_TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"

# SessionEnd itself is constant-time; this heartbeat-owned drain performs the
# slow closeout consumers with finite retries and bounded receipts.
drain_session_end_breadcrumbs() {
  if [ -n "$SESSION_END_TIMEOUT_BIN" ]; then
    "$SESSION_END_TIMEOUT_BIN" "${LIMEN_SESSION_END_CONSUMER_TIMEOUT:-90}" \
      python3 "$LIMEN_ROOT/scripts/consume-session-end-breadcrumbs.py" \
        --source "$SESSION_END_SOURCE" \
        --max-sessions "${LIMEN_SESSION_END_CONSUMER_BATCH:-8}" \
        --runway-seconds "${LIMEN_SESSION_END_CONSUMER_RUNWAY:-60}" 2>&1 | tail -1 || true
  else
    python3 "$LIMEN_ROOT/scripts/consume-session-end-breadcrumbs.py" \
      --source "$SESSION_END_SOURCE" \
      --max-sessions "${LIMEN_SESSION_END_CONSUMER_BATCH:-8}" \
      --runway-seconds "${LIMEN_SESSION_END_CONSUMER_RUNWAY:-60}" 2>&1 | tail -1 || true
  fi
}

mkdir -p "$LIMEN_ROOT/logs"
LOCK="$LIMEN_ROOT/logs/.saturate.lock"

# single-instance guard, shared with saturate.sh (macOS has no flock -> mkdir fallback)
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK"; flock -n 9 || { echo "$(date '+%F %T') lock held — skip tick"; exit 0; }
else
  mkdir "$LOCK.d" 2>/dev/null || { echo "$(date '+%F %T') lock held — skip tick"; exit 0; }
  trap 'rmdir "$LOCK.d" 2>/dev/null' EXIT
fi

drain_session_end_breadcrumbs

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

CAMPAIGN_WAKE_TIMEOUT="${LIMEN_CAMPAIGN_WAKE_TIMEOUT:-300}"
case "$CAMPAIGN_WAKE_TIMEOUT" in
  ''|*[!0-9]*) CAMPAIGN_WAKE_CEILING=330 ;;
  *)
    if [ "$CAMPAIGN_WAKE_TIMEOUT" -ge 300 ] && [ "$CAMPAIGN_WAKE_TIMEOUT" -le 7200 ]; then
      CAMPAIGN_WAKE_CEILING=$((CAMPAIGN_WAKE_TIMEOUT + 30))
    else
      CAMPAIGN_WAKE_CEILING=330
    fi
    ;;
esac

wake_campaign() {
  if [ -z "$SESSION_END_TIMEOUT_BIN" ]; then
    echo "campaign wake denied: timeout/gtimeout is unavailable"
    return 125
  fi
  "$SESSION_END_TIMEOUT_BIN" -s KILL "$CAMPAIGN_WAKE_CEILING" \
    python3 "$LIMEN_ROOT/scripts/campaign-heartbeat.py" \
      --root "$LIMEN_ROOT" \
      --workstream institutional-omega
}

echo "═══ heartbeat $(date '+%F %T') campaign=institutional-omega ═══"
python3 "$LIMEN_ROOT/scripts/usage-telemetry.py"                    2>&1 | tail -2 || true
python3 "$LIMEN_ROOT/scripts/token-value-gauge.py"                 2>&1 | tail -2 || true
if [ "$MODE" != "dispatch" ]; then
  echo "autonomy mode=$MODE — telemetry/status only; campaign wake skipped"
  python3 "$LIMEN_ROOT/scripts/emit-tick.py" 2>&1 | tail -1 || true
  python3 -m limen doctor 2>&1 | head -10
  echo "═══ heartbeat done $(date '+%F %T') ═══"
  exit 0
fi

wake_campaign 2>&1 | tail -2 || true
echo "── clone lifecycle hygiene (worktree prune + gc --auto + reap-report) ──"
bash "$LIMEN_ROOT/scripts/clone-maintenance.sh" 2>&1 | tail -6 || true
python3 "$LIMEN_ROOT/scripts/emit-tick.py" 2>&1 | tail -1 || true
python3 -m limen doctor 2>&1 | head -10
echo "═══ heartbeat done $(date '+%F %T') ═══"
