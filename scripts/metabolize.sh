#!/usr/bin/env bash
# metabolize.sh — one full metabolism cycle of the conductor (the heartbeat).
#
#   drain (close completed) → mine (refill queue) → route (assign cheapest
#   vendor) → [dispatch] → board.
#
# This is the body the local cron AND the remote 4-hourly auto-scaler run to keep
# idle multi-vendor capacity producing. Idempotent + bounded.
#
# SAFE BY DEFAULT: without LIMEN_DISPATCH=1 it only drains/mines/routes/reports —
# all reversible local writes, nothing outward. With LIMEN_DISPATCH=1 it also:
#   - dispatches local lanes (codex/opencode/agy/claude) which, via worktree
#     isolation, only ever produce reviewable PRs — never touch a live tree;
#   - dispatches jules within its daily budget.
#
# Knobs: LIMEN_MINE_LIMIT (15)  LIMEN_LOCAL_LIMIT (3)  LIMEN_JULES_LIMIT (10)
set -uo pipefail
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
export LIMEN_WORKDIR="${LIMEN_WORKDIR:-$HOME/Workspace}"
export LIMEN_ISOLATION="${LIMEN_ISOLATION:-worktree}"
export PYTHONPATH="$LIMEN_ROOT/cli/src"
cd "$LIMEN_ROOT" || exit 1

echo "═══ metabolize $(date '+%F %T') — dispatch=${LIMEN_DISPATCH:-0} isolation=$LIMEN_ISOLATION ═══"

echo "── 0a. hydrate credentials (1Password → ~/.limen.env → every lane; never re-login) ──"
# Refresh fleet creds from the ONE source of truth so a one-time login never has to be repeated
# (lapsed tokens / fresh worktrees self-heal). Fail-open: skips silently if op is locked/absent.
if [ "${LIMEN_CREDS_HYDRATE:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/creds-hydrate.py" --apply || echo "  (creds-hydrate skipped — op locked/absent)"
fi
# Source the cred cache so THIS shell + every child (route.py, the agent CLIs) inherit the keys.
if [ -f "$HOME/.limen.env" ]; then set -a; . "$HOME/.limen.env"; set +a; fi

echo "── 0. refresh usage telemetry / lane health ──"
python3 "$LIMEN_ROOT/scripts/usage-telemetry.py" || echo "  (usage telemetry skipped)"

echo "── 1. drain (close completed Jules) ──"
bash "$LIMEN_ROOT/scripts/drain.sh" || echo "  (drain skipped/failed — continuing)"

echo "── 2. mine (refill queue from GitHub backlog) ──"
python3 "$LIMEN_ROOT/scripts/mine-backlog.py" --limit "${LIMEN_MINE_LIMIT:-15}" --apply || echo "  (mine skipped)"

echo "── 2b. generate (self-feed build-out tasks if mining left the queue below floor) ──"
# the SELF-FEEDING guarantee: when the GitHub backlog is exhausted and mining returns nothing,
# this tops the queue to LIMEN_BACKLOG_FLOOR with useful per-product work so `open` never hits 0
# and the loop never idles. No-ops when the queue is already healthy.
python3 "$LIMEN_ROOT/scripts/generate-backlog.py" --apply || echo "  (generate skipped)"

echo "── 3. route (assign cheapest-capable vendor) ──"
python3 "$LIMEN_ROOT/scripts/route.py" --apply || echo "  (route skipped)"

if [ "${LIMEN_DISPATCH:-0}" = "1" ]; then
  echo "── 4a. dispatch local lanes → PRs (worktree-isolated, live tree untouched) ──"
  for v in codex opencode agy claude; do
    python3 -m limen dispatch --agent "$v" --live --limit "${LIMEN_LOCAL_LIMIT:-3}" || true
  done
  echo "── 4b. dispatch jules (within daily budget) ──"
  python3 -m limen dispatch --agent jules --live --limit "${LIMEN_JULES_LIMIT:-10}" || true
else
  echo "── 4. dispatch SKIPPED (set LIMEN_DISPATCH=1 to enable outward dispatch) ──"
fi

echo "── 5. board ──"
python3 -m limen doctor 2>&1 | head -12

# ── 6. self-improve (LOW cadence) — the last rung of the self-* ladder ──
# Reads the loop's own dispatch_log track record and emits a re-plan PROPOSAL to
# logs/self-improve-proposal.json (down-weight 0%-lanes, retire chronic-fail
# patterns, boost what ships). Proposal-only + read-only — never writes tasks.yaml.
# It's a slow-moving signal, so run it only every Nth beat, not per-beat.
# Wired live: low-cadence voice (every LIMEN_SI_CADENCE hours) — the last rung that closes the ladder.
N="${LIMEN_SI_CADENCE:-10}"
if [ "$(( $(date +%s) / 3600 % N ))" = "0" ]; then
  python3 "$LIMEN_ROOT/scripts/self-improve.py" || echo "  (self-improve skipped)"
fi

echo "═══ metabolize done $(date '+%F %T') ═══"
