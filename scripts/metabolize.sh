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
# macOS 26.6 fork-safety mitigation. Apple's Network.framework (loaded at startup into
# EVERY python here — 3.14/3.13/3.9 alike) registers a pthread_atfork child handler
# (nw_settings_child_has_forked) that SIGSEGVs in os_log on the child side of a
# fork()+exec() — i.e. any subprocess call that passes cwd=/preexec_fn (~32 fleet files).
# It's a timing race, so it kills a fraction of the thousands of fork+exec/beat. Quieting
# os_activity defuses the os_log path the handler crashes in. Must be set BEFORE any python
# launches (the framework loads before user code runs), so it lives here, above the first
# python invocation. Mechanism-certain cure = keep subprocess on posix_spawn (no cwd=);
# this env var is the zero-blast-radius mitigation. See fork-oslog crash report 2026-07-09.
export OS_ACTIVITY_MODE="${OS_ACTIVITY_MODE:-disable}"
cd "$LIMEN_ROOT" || exit 1
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

echo "═══ metabolize $(date '+%F %T') — dispatch=${LIMEN_DISPATCH:-0} isolation=$LIMEN_ISOLATION ═══"

# ── beat sensors (continuous-runtime axis of the VIGILIA spine) ────────────────────────────────
# The beat's sensors (0a … 0j) are declared data in institutio/governance/sensors.yaml; this DERIVES the
# whole loop from that registry via one call to scripts/beat-sensors.py — adding a sensor is one registry
# entry, not a shell edit in three places. The prior 20 hand-wired `── 0x ──` blocks were deleted once the
# derive path was proven byte-equivalent (23-script equivalence test + an observed real-sensor run); it is
# now the default. Parity held by scripts/check-sensors.py (its D-check accepts this derive-runner call).
# LIMEN_BEAT_DERIVE=0 skips the sensor pass entirely — an escape hatch, not a fallback. See
# docs/IDEAL-FORMS-LEDGER.md → IF-SENSOR-REGISTRY.
if [ "${LIMEN_BEAT_DERIVE:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/beat-sensors.py" --run --source metabolize
  # beat-sensors ran creds-hydrate + its declared reload_env internally; the PARENT shell still needs the
  # cred cache sourced for the NON-sensor dispatch stages below (route.py, the agent CLIs).
  if [ -f "$HOME/.limen.env" ]; then set -a; . "$HOME/.limen.env"; set +a; fi
fi  # ── end beat sensors (derived from sensors.yaml; LIMEN_BEAT_DERIVE=0 to skip) ──

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

echo "── 5b. insight-cadence (proposal-only auto-reporting) ──"
# Generates reports at 4 tiers (hourly/daily/weekly/monthly). Self-gates behind
# elapsed wall-clock time internally, but --once forces it to run if due.
if [ "${LIMEN_INSIGHT_CADENCE:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/insight-cadence.py" --once || echo "  (insight-cadence skipped)"
  # Route the latest report per tier to its durable owner (his-hand levers / keeper upsert
  # tickets / organ residual inboxes). Armed by the same default as the heartbeat
  # (LIMEN_INSIGHT_ROUTE_APPLY=1); board echoes are skipped, new tasks capped per pass.
  LIMEN_INSIGHT_ROUTE_APPLY="${LIMEN_INSIGHT_ROUTE_APPLY:-1}" \
    python3 "$LIMEN_ROOT/scripts/insight-route.py" | tail -3 || echo "  (insight-route skipped)"
  # Mirror live censor residuals → public `censor` GitHub issues (auto-open/auto-close, capped).
  # Observable before autonomous: dry-run until LIMEN_CENSOR_ISSUES_APPLY=1 arms it.
  python3 "$LIMEN_ROOT/scripts/sync-censor-issues.py" \
    $([ "${LIMEN_CENSOR_ISSUES_APPLY:-0}" = "1" ] && echo --apply) | tail -3 || echo "  (censor-issues skipped)"
fi

echo "── 5c. arca (encrypted private-estate vault) ──"
# ARCA — off-machine durability for the private estate: every ~/Workspace/_*-private store,
# AES-256-encrypted (key ONLY in the macOS Keychain, never in any repo or env file) and pushed
# as ciphertext to a private GitHub repo (organvm/arca). The containment inverse of the public
# lanes: GitHub never sees a plaintext byte. Change-detected + roundtrip-verified; no-ops in
# seconds when nothing changed. Fails soft (headless Keychain / offline). LIMEN_ARCA=0 disables.
if [ "${LIMEN_ARCA:-1}" = "1" ]; then
  bash "$LIMEN_ROOT/scripts/arca.sh" backup || echo "  (arca skipped — keychain locked, offline, or vault unconfigured)"
fi

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

# ── 7. handoff-relay — write the seam-survival packet so the next session/vendor/beat
# resumes WARM (open lanes, in-flight claims, last blocker, budget, next action). Keystone of
# the walk-away loop (retro 2026-07-08). Read-only over the board; never writes tasks.yaml.
python3 "$LIMEN_ROOT/scripts/handoff-relay.py" || echo "  (handoff-relay skipped)"

echo "═══ metabolize done $(date '+%F %T') ═══"
