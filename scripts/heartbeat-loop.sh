#!/usr/bin/env bash
# heartbeat-loop.sh — the conductor as a CONTINUOUS, POLYRHYTHMIC daemon.
#
# One base tempo (the loop), multiple voices each subdividing it at its own cadence —
# like a drum kit over one BPM. Replaces the fixed 3h StartInterval (one instrument,
# one note). Tempo is ADAPTIVE: tighten when work flows, back off when idle. Total
# provider work is owned by finite keeper-backed campaigns, never this daemon. flock
# in each step prevents overlap; near-zero cost while idle; resumes instantly on wake (run
# under a launchd KeepAlive daemon, NOT a StartInterval timer).
#
#   VOICE          cadence (beats)   what plays
#   campaign       every 1 (kick)    wake the admitted canonical supervisor
#   tick           every 1           emit logs/ticks.jsonl (portal pulse)
#   balance        every 2 (snare)   route + rebalance the queue across lanes
#   feed           every 3           mine the GitHub backlog
#   drain          every 5           pull+close completed jules, release stale
#   hygiene        every 8           clone-maintenance (gc/prune/reap-report)
#   capture        every 48          commit+push every workspace repo → off disk, into canonical
#   corpus         every 24          CONVERGE his words: distill the knowledge base toward ONE
#   media          every 24          ATOMIZE his docs → Shot atoms (strand D; gated LIMEN_MEDIA_ATOMIZE=1)
#   mail           every 6           COMMS: sweep inbound mail (flag fires/archive noise) + rebuild obligations ledger/faces
#   continuation   every 6           KEEP GOING: reduce worktrees, advance Photos proof, refresh creative proxy
set -uo pipefail
export HOME="${HOME:-/Users/4jp}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
# Pin the daemon to its OWN python — a STABLE binary path (created with `venv --copies`) so a single
# one-time macOS Full Disk Access grant on that ONE binary survives Homebrew python upgrades and lets the
# usage organ read vendor app-data (~/.codex, ~/.claude, ~/.gemini) WITHOUT the recurring TCC consent
# prompt. Structural, not best-effort: prepend the venv AND verify python3 resolves inside it.
# If the venv is missing or unhealthy, SELF-HEAL first (573 WARNs 2026-07-09→07-14 while the
# prescribed remedy sat unrun — a sensor without an effector); only if the bootstrap fails do we
# fall back to system python, LOGGED loudly, so the daemon never silently runs an ungranted
# interpreter and never dead-stops. ([[no-never-happens-again]])
LIMEN_VENV_PY="$LIMEN_ROOT/.venv/bin/python3"
# Healthy = the pinned binary imports the limen package. A bare -x check passes a partial
# bootstrap (venv created, pip failed) while every `python3 -m limen` beat step dies.
venv_ok() { [ -x "$LIMEN_VENV_PY" ] && "$LIMEN_VENV_PY" -c "import limen, yaml" >/dev/null 2>&1; }
if ! venv_ok; then
  echo "$(date '+%F %T') INFO: pinned interpreter missing/unhealthy — bootstrapping $LIMEN_ROOT/.venv" \
       >> "$LIMEN_ROOT/logs/heartbeat.out.log" 2>/dev/null || true
  python3 -m venv --copies "$LIMEN_ROOT/.venv" >> "$LIMEN_ROOT/logs/heartbeat.out.log" 2>&1 || true
  "$LIMEN_ROOT/.venv/bin/pip" install --quiet --editable "$LIMEN_ROOT/cli" pyyaml \
       >> "$LIMEN_ROOT/logs/heartbeat.out.log" 2>&1 || true
fi
if venv_ok; then
  export PATH="$LIMEN_ROOT/.venv/bin:$PATH"; hash -r 2>/dev/null || true
  export LIMEN_PY="$LIMEN_VENV_PY"
else
  export LIMEN_PY="$(command -v python3 || echo python3)"
  echo "$(date '+%F %T') WARN: $LIMEN_VENV_PY missing — using system python ($LIMEN_PY); the macOS TCC" \
       "prompt may recur. Recreate the pinned interpreter: python3 -m venv --copies $LIMEN_ROOT/.venv" \
       >> "$LIMEN_ROOT/logs/heartbeat.out.log" 2>/dev/null || true
fi
# NON-BYPASSABLE Claude model chokepoint. Capture the REAL `claude` (resolved via the PATH set
# above) BEFORE prepending the shim dir, then put the shim FIRST so every fleet-spawned `claude`
# — dispatch lanes, quicken, converge, subagent fan-out — routes through it. The shim injects the
# earned floor when a spawn carries no --model, so nothing silently inherits the account-default
# Opus 4.8 (+auto-1M) that drove the 6/25 usage bleed; spawns that earned more pass --model and
# ride through untouched. Interactive shells never run this script, so the human's Opus is
# untouched. The shim is fail-open (any error → real claude, original argv). ([[fleet-model-floor-bleed]])
export LIMEN_REAL_CLAUDE="${LIMEN_REAL_CLAUDE:-$(command -v claude 2>/dev/null || echo "$HOME/.local/bin/claude")}"
export PATH="$LIMEN_ROOT/scripts/shims:$PATH"; hash -r 2>/dev/null || true
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
export LIMEN_WORKDIR="${LIMEN_WORKDIR:-$HOME/Workspace}"
export LIMEN_ISOLATION="${LIMEN_ISOLATION:-worktree}"
export GEMINI_CLI_TRUST_WORKSPACE="${GEMINI_CLI_TRUST_WORKSPACE:-true}"
export PYTHONPATH="$LIMEN_ROOT/cli/src"
# macOS 26.6 fork-safety mitigation — defuse Apple's Network.framework atfork child
# handler that SIGSEGVs in os_log on the child side of fork()+exec() (any subprocess with
# cwd=/preexec_fn). Must precede every python in the daemon loop; see metabolize.sh for the
# full note and fork-oslog crash report 2026-07-09. Mechanism-cure = posix_spawn (no cwd=).
export OS_ACTIVITY_MODE="${OS_ACTIVITY_MODE:-disable}"
cd "$LIMEN_ROOT" || exit 1

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
# opencode runs on a Google model → it needs the Google generative-AI key (reuse gemini's)
[ -n "${GEMINI_API_KEY:-}" ] && export GOOGLE_GENERATIVE_AI_API_KEY="${GOOGLE_GENERATIVE_AI_API_KEY:-$GEMINI_API_KEY}"
# TABVLARIVS single-writer CUTOVER (Step 2.1, watched draining before flip): the fleet routes its
# task-CREATION writers (mine/ingest-backlog, generate-backlog/-revenue/-organ, discover-value)
# through the record-keeper's ticket inbox instead of each direct-writing tasks.yaml. Default ON for
# the fleet; set LIMEN_TICKETS_PRODUCE=0 in ~/.limen.env to revert instantly. The keeper (organ at
# the top of the beat) folds the tickets next beat; the status-mutator tier stays direct (Step 2.2).
export LIMEN_TICKETS_PRODUCE="${LIMEN_TICKETS_PRODUCE:-1}"
# INSIGHT-ROUTE armed: the insights→owners route organ (insight-route.py, after insight-cadence in
# the beat) routes the latest report per tier to its durable owner — his-hand levers, keeper upsert
# tickets (board echoes skipped, capped per pass), organ residual inboxes. Default ON; set
# LIMEN_INSIGHT_ROUTE_APPLY=0 in ~/.limen.env to make it observe-only (dry-run prints).
export LIMEN_INSIGHT_ROUTE_APPLY="${LIMEN_INSIGHT_ROUTE_APPLY:-1}"

# ── RUNG RUNNER — a rung that fails on every beat must not read as a quiet one ──────────
# Every organ call in this loop used to end `2>&1 | tail -1 || true`, and that idiom has
# three defects that compound into total blindness:
#
#   1. The status is DISCARDED — corrected 2026-08-07, this comment first said "destroyed".
#      This script sets `pipefail` (line 23), so the pipeline really does exit with the
#      ORGAN's status (measured: rc=9 through `| tail -1` with pipefail, rc=0 without it).
#      The trailing `|| true` was therefore load-bearing, and what it bore was throwing
#      that status away at the call site. Nothing captured it, so NOTHING downstream could
#      distinguish a hard failure from a clean run. Same blindness, different cause — and
#      the cause is what picks the fix: the status has to be RECORDED, not merely rescued
#      from tail. (Drop `pipefail` and tail does destroy it, which is why the idiom stays
#      forbidden outright rather than merely discouraged.)
#   2. `tail -1` of a Python traceback is the last line of the exception's own repr. For an
#      HTTP error carrying a JSON body that is a bare `}`. The diagnostic is destroyed at
#      exactly the moment it is the only thing worth keeping.
#   3. No outcome is recorded anywhere, so a rung can fail on every beat forever while
#      every observable — beat log, enactment audit, organ health — stays green.
#
# Measured 2026-08-07: `heal-board.py --canonical` (the #2014 canonical-heal rung) failed on
# EVERY beat with `conduct broker rejected request (500): Exceeded allowed rows written in
# Durable Objects free tier`, emitting 61 diagnostic lines. The beat log received `}`, and
# neither "Durable Objects" nor "rejected request" appeared in ANY log file estate-wide.
# That is the "signal with no effector" class the loop-body self-load rung (#2023) exists to
# close, reappearing one level up: the failure had no reader.
#
# beat_run keeps the happy path byte-identical — one line, the organ's own last line, so log
# volume does not change — and on failure prints a banner plus the real tail. Either way it
# appends the outcome to logs/beat-rungs.jsonl so scripts/enactment-audit.py can turn "this
# rung has failed N consecutive beats" into a RED rung instead of a silence. It always
# returns 0: the beat stays fail-open, which is the one thing `|| true` was actually doing.
BEAT_RUNG_LOG="${LIMEN_BEAT_RUNG_LOG:-$LIMEN_ROOT/logs/beat-rungs.jsonl}"
beat_run() {
  _br_label="$1"; shift
  _br_out="$LIMEN_ROOT/logs/.beat-rung.$$.out"
  "$@" >"$_br_out" 2>&1
  _br_rc=$?
  if [ "$_br_rc" -eq 0 ]; then
    tail -1 "$_br_out" 2>/dev/null
  else
    # The whole point: show what actually broke, not the last line of its repr.
    echo "── RUNG FAIL [$_br_label] exit=$_br_rc ── last ${LIMEN_RUNG_FAIL_LINES:-15} lines ──"
    tail -n "${LIMEN_RUNG_FAIL_LINES:-15}" "$_br_out" 2>/dev/null
    echo "── end RUNG FAIL [$_br_label] ──"
  fi
  printf '{"ts":"%s","rung":"%s","exit":%d}\n' \
    "$(date -u +%FT%TZ)" "$_br_label" "$_br_rc" >> "$BEAT_RUNG_LOG" 2>/dev/null || true
  rm -f "$_br_out" 2>/dev/null || true
  return 0
}

# Bound the outcome ledger. The audit only ever reads the recent tail, so trimming to the
# last LIMEN_BEAT_RUNG_LOG_KEEP records loses nothing it consumes.
trim_beat_rung_log() {
  [ -f "$BEAT_RUNG_LOG" ] || return 0
  _brl_lines="$(wc -l < "$BEAT_RUNG_LOG" 2>/dev/null | tr -d ' ')"
  case "$_brl_lines" in ''|*[!0-9]*) return 0 ;; esac
  [ "$_brl_lines" -gt "${LIMEN_BEAT_RUNG_LOG_MAX:-20000}" ] || return 0
  tail -n "${LIMEN_BEAT_RUNG_LOG_KEEP:-4000}" "$BEAT_RUNG_LOG" > "$BEAT_RUNG_LOG.trim" 2>/dev/null \
    && mv "$BEAT_RUNG_LOG.trim" "$BEAT_RUNG_LOG" 2>/dev/null
  rm -f "$BEAT_RUNG_LOG.trim" 2>/dev/null || true
  return 0
}

# BOUNDED WAKE — the legacy loop may invoke only the canonical campaign adapter.
# The adapter bounds the supervisor evaluation; this outer SIGKILL ceiling also
# bounds capsule discovery and remote-default preflight. Without timeout(1), the
# campaign wake fails closed while other monitoring voices continue.
DISPATCH_TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
: "${LIMEN_CAMPAIGN_WAKE_TIMEOUT:=300}"
case "$LIMEN_CAMPAIGN_WAKE_TIMEOUT" in
  ''|*[!0-9]*) CAMPAIGN_WAKE_CEILING=330 ;;
  *)
    if [ "$LIMEN_CAMPAIGN_WAKE_TIMEOUT" -ge 300 ] && [ "$LIMEN_CAMPAIGN_WAKE_TIMEOUT" -le 7200 ]; then
      CAMPAIGN_WAKE_CEILING=$((LIMEN_CAMPAIGN_WAKE_TIMEOUT + 30))
    else
      CAMPAIGN_WAKE_CEILING=330
    fi
    ;;
esac
export LIMEN_CAMPAIGN_WAKE_TIMEOUT
[ -n "$DISPATCH_TIMEOUT_BIN" ] || echo "$(date '+%F %T') WARN: no timeout/gtimeout on PATH — campaign wake denied;" \
  "monitoring remains live. brew install coreutils to restore the bounded wake." \
  >> "$LIMEN_ROOT/logs/heartbeat.out.log" 2>/dev/null || true
campaign_wake_bounded() {
  if [ -z "$DISPATCH_TIMEOUT_BIN" ]; then
    echo "campaign wake denied: timeout/gtimeout is unavailable"
    return 125
  fi
  "$DISPATCH_TIMEOUT_BIN" -s KILL "$CAMPAIGN_WAKE_CEILING" "$@"
}

SESSION_END_SOURCE="${LIMEN_SESSION_END_BREADCRUMBS:-${XDG_STATE_HOME:-$HOME/.local/state}/limen/session-end-breadcrumbs.jsonl}"
drain_session_end_breadcrumbs() {
  if [ -n "$DISPATCH_TIMEOUT_BIN" ]; then
    beat_run consume-session-end-breadcrumbs \
      "$DISPATCH_TIMEOUT_BIN" "${LIMEN_SESSION_END_CONSUMER_TIMEOUT:-90}" \
      python3 "$LIMEN_ROOT/scripts/consume-session-end-breadcrumbs.py" \
        --source "$SESSION_END_SOURCE" \
        --max-sessions "${LIMEN_SESSION_END_CONSUMER_BATCH:-8}" \
        --runway-seconds "${LIMEN_SESSION_END_CONSUMER_RUNWAY:-60}" || true
  else
    beat_run consume-session-end-breadcrumbs \
      python3 "$LIMEN_ROOT/scripts/consume-session-end-breadcrumbs.py" \
      --source "$SESSION_END_SOURCE" \
      --max-sessions "${LIMEN_SESSION_END_CONSUMER_BATCH:-8}" \
      --runway-seconds "${LIMEN_SESSION_END_CONSUMER_RUNWAY:-60}" || true
  fi
}

# SINGLETON GUARD (ATOMIC) — only one heartbeat-loop may run. mkdir is atomic, so two
# near-simultaneous launchd respawns cannot both win (the pidfile read-then-write did).
# Stale-lock (dead holder) is recovered with a single rmdir+retry; lose that race → exit.
DAEMON_DIR="$LIMEN_ROOT/logs/.daemon.lock.d"
DAEMON_LOCK="$DAEMON_DIR/pid"
if ! mkdir "$DAEMON_DIR" 2>/dev/null; then
  _old=$(cat "$DAEMON_LOCK" 2>/dev/null || echo "")
  # EMPTY pidfile = the holder just won mkdir and hasn't written its pid yet → it's
  # alive, back off (do NOT rmdir, or we'd steal a starting holder's lock = the dup bug).
  if [ -z "$_old" ] || kill -0 "$_old" 2>/dev/null; then
    echo "heartbeat-loop already running (pid ${_old:-starting}) — singleton guard, exiting"; exit 0
  fi
  # pidfile has a DEAD pid → genuinely stale (e.g. prior SIGKILL bypassed the EXIT trap);
  # remove the pidfile FIRST (rmdir fails on a non-empty dir), then take over once.
  rm -f "$DAEMON_LOCK" 2>/dev/null
  rmdir "$DAEMON_DIR" 2>/dev/null
  mkdir "$DAEMON_DIR" 2>/dev/null || { echo "lost stale-lock takeover race — exiting"; exit 0; }
fi
echo $$ > "$DAEMON_LOCK"
echo $$ > "$LIMEN_ROOT/logs/heartbeat-loop.pid"

LANES="${LIMEN_LANES:-auto}"   # planner input only; campaign execution derives live broker capabilities

# base tempo (adaptive) + voice subdivisions (configurable)
MIN="${LIMEN_LOOP_MIN:-120}"; MAX="${LIMEN_LOOP_MAX:-1800}"; beat="$MIN"
FAST_WAVE_SECONDS="${LIMEN_VITALS_SAMPLE_SECONDS:-300}"
case "$FAST_WAVE_SECONDS" in ''|*[!0-9]*) FAST_WAVE_SECONDS=300 ;; esac
[ "$FAST_WAVE_SECONDS" -gt 0 ] || FAST_WAVE_SECONDS=300
VITALS_SAMPLE_GRACE_SECONDS="${LIMEN_VITALS_SAMPLE_GRACE_SECONDS:-5}"
case "$VITALS_SAMPLE_GRACE_SECONDS" in ''|*[!0-9]*) VITALS_SAMPLE_GRACE_SECONDS=5 ;; esac
[ "$VITALS_SAMPLE_GRACE_SECONDS" -gt 0 ] || VITALS_SAMPLE_GRACE_SECONDS=5
VITALS_SAMPLE_TIMEOUT_SECONDS="${LIMEN_VITALS_SAMPLE_TIMEOUT:-30}"
case "$VITALS_SAMPLE_TIMEOUT_SECONDS" in ''|*[!0-9]*) VITALS_SAMPLE_TIMEOUT_SECONDS=30 ;; esac
[ "$VITALS_SAMPLE_TIMEOUT_SECONDS" -gt 0 ] || VITALS_SAMPLE_TIMEOUT_SECONDS=30
FAST_WAVE_BEAT=0
FAST_WAVE_LOG="$LIMEN_ROOT/logs/vigilia/fast-wave.log"
FAST_WAVE_AUX_LOG="$LIMEN_ROOT/logs/vigilia/fast-wave-aux.log"
FAST_WAVE_PID_FILE="$LIMEN_ROOT/logs/vigilia/fast-wave.pid"
HOST_PRESSURE_WATCHDOG_LOG="$LIMEN_ROOT/logs/vigilia/host-pressure-watchdog.log"
HOST_PRESSURE_WATCHDOG_PID_FILE="$LIMEN_ROOT/logs/vigilia/host-pressure-watchdog.pid"
PAUSED_BEAT="${LIMEN_HEARTBEAT_PAUSED_SECONDS:-300}"
case "$PAUSED_BEAT" in
  ''|*[!0-9]*) PAUSED_BEAT=300 ;;
esac
if [ "$PAUSED_BEAT" -lt 60 ]; then PAUSED_BEAT=60; fi
# voices subdivide the base tempo — the work-cadence EXPLORE>PLAN>BUILD>VERIFY>HEAL>LEARN>RELAY:
C_BALANCE="${LIMEN_BEAT_BALANCE:-2}"   # PLAN  (route + rebalance)
C_FEED="${LIMEN_BEAT_FEED:-3}"         # EXPLORE (mine the backlog)
C_DRAIN="${LIMEN_BEAT_DRAIN:-3}"       # VERIFY (harvest completed → done; faster recycle)
C_HEAL="${LIMEN_BEAT_HEAL:-6}"         # HEAL  (recover failed/orphaned → fresh cascade)
C_HYGIENE="${LIMEN_BEAT_HYGIENE:-8}"; C_BACKUP="${LIMEN_BEAT_BACKUP:-48}"
C_SYNC="${LIMEN_BEAT_SYNC:-2}"         # SELF-HEAL the substrate (re-converge checkout to the release)
C_CORPUS="${LIMEN_BEAT_CORPUS:-24}"    # CONVERGE (distill his words toward ONE; expensive → rare)
C_CORPUS_FEED="${LIMEN_BEAT_CORPUS_FEED:-8}"  # FEED (atomize live Claude Code prompts into the manifest, BEFORE converge)
C_WEB="${LIMEN_BEAT_WEB:-4}"           # LEARN (refresh the visualized surfaces)
C_NOMENCLATOR="${LIMEN_BEAT_NOMENCLATOR:-4}"     # NOMENCLATOR (INDEX·NOMINVM — hold names to the naming canon)
C_CENSOR="${LIMEN_BEAT_CENSOR:-4}"     # CENSOR (insights→actions; hourly/daily/weekly tiers self-gate on wall-clock)
C_MAIL="${LIMEN_BEAT_MAIL:-6}"         # COMMS (sweep inbound mail + rebuild the obligations ledger/faces)
C_CONTINUATION="${LIMEN_BEAT_CONTINUATION:-6}" # KEEP GOING (reduction -> photos proof -> creative proxy -> reduction)
C_REPORT="${LIMEN_BEAT_REPORT:-12}"    # RELAY (conducting report; self-limits to once per usage-day)
C_INSIGHT_CADENCE="${LIMEN_BEAT_INSIGHT_CADENCE:-4}" # INSIGHT-CADENCE (auto-reports on four tiers)
C_QUICKEN="${LIMEN_BEAT_QUICKEN:-4}"   # QUICKEN (give stalled FleetView sessions life to finish)
C_POSITIONING="${LIMEN_BEAT_POSITIONING:-12}"  # POSITIONING (refresh inbound-magnet surfaces; gated OFF)
C_AVTOPOIESIS="${LIMEN_BEAT_AVTOPOIESIS:-12}"  # AVTOPOIESIS (is each door alive? past/present/future — distance-from-ideal; gated OFF)
C_EVOCATOR="${LIMEN_BEAT_EVOCATOR:-6}"   # EVOCATOR (the summoner — keep canonical truths present in every channel: FLAME/beat, corpus, memory)
C_HEALTH="${LIMEN_BEAT_HEALTH:-6}"       # CARE (refresh the personal health office: chart digest + visit-prep + clinical-loop chase; PII off-repo)
C_MAT="${LIMEN_BEAT_MAT:-8}"             # MAT (daily-engine keeper: session pull + card pre-compose + roadblocks; ~20h self-throttle in-organ; counts-only off-repo)
C_LIFE="${LIMEN_BEAT_LIFE:-6}"           # STEWARD (refresh the digital-life office: accounts/assets/subscription purge clock; PII off-repo)
C_GOVERNANCE="${LIMEN_BEAT_GOVERNANCE:-8}" # GOVERN (run the cursus honorum seed validator + governance standing report)
C_FINANCIAL="${LIMEN_BEAT_FINANCIAL:-8}"   # FINANCE (run the financial-office consolidator + advance maturity)
C_PUBPOLICY="${LIMEN_BEAT_PUBPOLICY:-8}" # DISCLOSE (verify the content-disposition engine: redactor owner-scoped, matrix + classifier intact)
C_WALLS="${LIMEN_BEAT_WALLS:-12}"        # WALLS (regenerate the credential Wall #320 + his-hand Wall #330 so they never drift)
C_CVSTOS="${LIMEN_BEAT_CVSTOS:-24}"      # KEEP (CVSTOS — host stays factory: chat-app/local debt census + factory-invariant + reaper proprioception; filesystem walk ⇒ rare)
C_VVLTVS="${LIMEN_BEAT_VVLTVS:-24}"      # FACE (VVLTVS — verify the public face reflects the live SSOT: profile/portfolio drift + contribution-mix radar; offline read ⇒ cheap)
C_CONTRIB="${LIMEN_BEAT_CONTRIB:-12}"    # MIRROR (SPECVLVM — re-render the contributions proof surface from hub-ledger outputs; offline read ⇒ cheap)
LOCKD="$LIMEN_ROOT/logs/.queue.lock.d"   # shared with supervisory ops (two-scale safety)
c=0
play() { [ $(( c % $1 )) -eq 0 ]; }   # true on this voice's beat
# PROPRIOCEPTION — stamp the instant a voice plays so organ-health.py can read GROUND TRUTH
# (did this rung actually fire?) instead of inferring liveness from a downstream artifact's mtime.
# One tiny file per voice, overwritten each fire (no growth, single writer = the daemon). Fail-open:
# a stamp failure never touches the beat. ([[no-never-happens-again]])
VOICED="$LIMEN_ROOT/logs/.voice"; mkdir -p "$VOICED" 2>/dev/null || true
stamp() { printf '%s\n' "$(date -u +%FT%TZ)" > "$VOICED/$1" 2>/dev/null || true; }
due_voice() {
  # True on the modulo cadence OR when the last observed fire is already older than
  # its worst-case cadence. This closes the restart/reset hole: a daemon repeatedly
  # kicked before beat 6/8 must not starve HEAL/EVOCATOR/HEALTH/LIFE/HYGIENE forever.
  local voice="${1:?voice}" cadence="${2:-1}" stamp_path now last expected
  case "$cadence" in ''|*[!0-9]*) cadence=1 ;; esac
  play "$cadence" && return 0
  stamp_path="$VOICED/$voice"
  [ -e "$stamp_path" ] || return 0
  now="$(date +%s)"
  last="$(stat -f %m "$stamp_path" 2>/dev/null || echo "")"
  case "$last" in ''|*[!0-9]*) last="$(stat -c %Y "$stamp_path" 2>/dev/null || echo "")" ;; esac
  [ -n "$last" ] || return 0
  expected=$(( cadence * MAX ))
  [ $(( now - last )) -ge "$expected" ]
}
# METABOLIZE PASS THROTTLE — wall-clock, not beats: the adaptive tempo swings 120s..1800s, so a
# beat-modulo cadence would run the metabolize sensor pass anywhere from 48x to 3x its intent.
# One pass per LIMEN_METABOLIZE_SENSORS_SECS (default hourly — the old 4-hourly cron's spirit at
# beat granularity). Fail-open like due_voice: an unreadable stamp means due.
metabolize_pass_due() {
  local stamp_path="$VOICED/metabolize_pass" now last
  [ -e "$stamp_path" ] || return 0
  now="$(date +%s)"
  last="$(stat -f %m "$stamp_path" 2>/dev/null || echo "")"
  case "$last" in ''|*[!0-9]*) last="$(stat -c %Y "$stamp_path" 2>/dev/null || echo "")" ;; esac
  [ -n "$last" ] || return 0
  [ $(( now - last )) -ge "${LIMEN_METABOLIZE_SENSORS_SECS:-3600}" ]
}
# FAST WAVE — a dedicated sample clock plus a single-flight auxiliary tier. The sample
# never waits for diurnal or organ-health, so their bounded work cannot consume its next slot.
fast_wave_bounded() {
  _fw_timeout="$1"; shift
  python3 - "$_fw_timeout" "$@" <<'PY'
import os
import signal
import subprocess
import sys

process = None


def terminate_group(signum, _frame):
    if process is not None and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except OSError:
                pass
    raise SystemExit(128 + signum)


signal.signal(signal.SIGHUP, terminate_group)
signal.signal(signal.SIGINT, terminate_group)
signal.signal(signal.SIGTERM, terminate_group)

try:
    ceiling = float(sys.argv[1])
    process = subprocess.Popen(sys.argv[2:], start_new_session=True)
    try:
        code = process.wait(timeout=ceiling)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        code = 124
except (OSError, TypeError, ValueError) as exc:
    print(f"fast-wave timeout wrapper: {exc}", file=sys.stderr)
    code = 125
raise SystemExit(code)
PY
}

_fast_wave_kill_tree() {
  local _fw_tree_root="$1"
  local _fw_descendant
  for _fw_descendant in $(pgrep -P "$_fw_tree_root" 2>/dev/null || true); do
    _fast_wave_kill_tree "$_fw_descendant"
    kill "$_fw_descendant" 2>/dev/null || true
  done
}

# Use one interruptible timer per cadence. Bash delivers the resident loop's TERM trap
# while sleep is active, so there is no per-second process churn across the two permanent loops.
_interruptible_sleep() {
  _sleep_remaining="$1"
  case "$_sleep_remaining" in
    ''|*[!0-9]*) return 2 ;;
  esac
  [ "$_sleep_remaining" -gt 0 ] || return 0
  # A background timer makes wait interruptible by the resident loop's TERM/HUP traps.
  sleep "$_sleep_remaining" &
  _sleep_pid=$!
  wait "$_sleep_pid"
  _sleep_status=$?
  if kill -0 "$_sleep_pid" 2>/dev/null; then
    kill "$_sleep_pid" 2>/dev/null || true
    wait "$_sleep_pid" 2>/dev/null || true
  fi
  return "$_sleep_status"
}

_fast_wave_due_beat() {
  _fw_cadence="$1"
  case "$_fw_cadence" in
    ''|*[!0-9]*) _fw_cadence=1 ;;
  esac
  [ "$_fw_cadence" -gt 0 ] || _fw_cadence=1
  _fw_candidate_beat="$2"
  if [ "$_fw_cadence" -le 1 ] || [ $((_fw_candidate_beat % _fw_cadence)) -eq 0 ]; then
    return 0
  fi
  return 1
}

fast_wave_sample_once() {
  # Initialize before any redirection: an unwritable temp log must not kill the resident loop under set -u.
  _fw_sample_rc=125
  _fw_tmp="$FAST_WAVE_LOG.$$.$FAST_WAVE_BEAT.tmp"
  if mkdir -p "$(dirname "$FAST_WAVE_LOG")" 2>/dev/null && : >"$_fw_tmp" 2>/dev/null; then
    {
      echo "fast-wave: sample start beat=$FAST_WAVE_BEAT $(date -u +%FT%TZ)"
      if [ "${LIMEN_VIGILIA:-1}" = "1" ]; then
        fast_wave_bounded "$VITALS_SAMPLE_TIMEOUT_SECONDS" python3 -m limen.vigilia sample
        _fw_sample_rc=$?
      else
        echo "fast-wave: VIGILIA disabled — sample skipped"
        _fw_sample_rc=0
      fi
      echo "fast-wave: sample finish beat=$FAST_WAVE_BEAT $(date -u +%FT%TZ) rc=$_fw_sample_rc"
    } >"$_fw_tmp" 2>&1 || true
    mv "$_fw_tmp" "$FAST_WAVE_LOG" 2>/dev/null || true
  else
    # Preserve the sample even when the log directory or temp file is briefly unavailable.
    echo "fast-wave: sample log unavailable — running without capture" >&2 || true
    if [ "${LIMEN_VIGILIA:-1}" = "1" ]; then
      fast_wave_bounded "$VITALS_SAMPLE_TIMEOUT_SECONDS" python3 -m limen.vigilia sample
      _fw_sample_rc=$?
    else
      _fw_sample_rc=0
    fi
  fi
  return "$_fw_sample_rc"
}

fast_wave_aux_once() {
  _fw_aux_kind="${1:-both}"
  if [ "$_fw_aux_kind" = "diurnal" ] || [ "$_fw_aux_kind" = "health" ] || [ "$_fw_aux_kind" = "both" ]; then
    _fw_aux_beat="${2:-$FAST_WAVE_BEAT}"
  else
    # Legacy callers passed only the beat; normalize that form to the compatibility wrapper.
    _fw_aux_beat="$_fw_aux_kind"
    _fw_aux_kind="both"
  fi

  # The one-argument form remains a compatibility wrapper; the loop below launches each
  # bounded sensor independently so a slow organ-health run cannot suppress diurnal work.
  if [ "$_fw_aux_kind" = "both" ]; then
    fast_wave_aux_once diurnal "$_fw_aux_beat" &
    _fw_diurnal_pid=$!
    fast_wave_aux_once health "$_fw_aux_beat" &
    _fw_health_pid=$!
    _fw_diurnal_rc=0
    wait "$_fw_diurnal_pid" || _fw_diurnal_rc=$?
    _fw_health_rc=0
    wait "$_fw_health_pid" || _fw_health_rc=$?
    [ "$_fw_diurnal_rc" -eq 0 ] || return "$_fw_diurnal_rc"
    return "$_fw_health_rc"
  fi

  _fw_aux_tmp="$FAST_WAVE_AUX_LOG.$_fw_aux_kind.$$.$_fw_aux_beat.tmp"
  _fw_aux_output="/dev/null"
  if mkdir -p "$(dirname "$FAST_WAVE_AUX_LOG")" 2>/dev/null && : >"$_fw_aux_tmp" 2>/dev/null; then
    _fw_aux_output="$_fw_aux_tmp"
  fi
  _fw_aux_rc=0

  if [ "$_fw_aux_kind" = "diurnal" ]; then
    if [ "${LIMEN_BEAT_DERIVE:-1}" = "1" ]; then
      fast_wave_bounded "${LIMEN_FAST_WAVE_SENSOR_TIMEOUT:-260}" python3 "$LIMEN_ROOT/scripts/beat-sensors.py" --run --source fast-wave --scheduled-only --beat "$_fw_aux_beat" --loop-max "$FAST_WAVE_SECONDS" --voice-dir "$VOICED" >"$_fw_aux_output" 2>&1
      _fw_aux_rc=$?
    else
      echo "fast-wave: derived sensors disabled" >"$_fw_aux_output" 2>&1 || true
    fi
  elif [ "$_fw_aux_kind" = "health" ]; then
    fast_wave_bounded "${LIMEN_ORGAN_HEALTH_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/organ-health.py" >"$_fw_aux_output" 2>&1
    _fw_aux_rc=$?
  else
    echo "fast-wave: unknown auxiliary sensor kind=$_fw_aux_kind" >&2 || true
    return 2
  fi

  if [ "$_fw_aux_output" = "$_fw_aux_tmp" ]; then
    {
      echo "fast-wave: aux start kind=$_fw_aux_kind beat=$_fw_aux_beat $(date -u +%FT%TZ)"
      cat "$_fw_aux_tmp" 2>/dev/null || true
      echo "fast-wave: aux finish kind=$_fw_aux_kind beat=$_fw_aux_beat rc=$_fw_aux_rc"
    } >>"$FAST_WAVE_AUX_LOG" 2>/dev/null || true
    rm -f "$_fw_aux_tmp" 2>/dev/null || true
  else
    echo "fast-wave: aux log unavailable kind=$_fw_aux_kind — sensor completed without capture" >&2 || true
  fi
  return "$_fw_aux_rc"
}

stale_watchdog_loop() {
  _watchdog_parent_pid="$1"
  trap 'exit 0' HUP INT TERM
  while kill -0 "$_watchdog_parent_pid" 2>/dev/null; do
    # Let the fast-wave producer complete its boundary write before reading the seat.
    _interruptible_sleep "$((FAST_WAVE_SECONDS + VITALS_SAMPLE_TIMEOUT_SECONDS + VITALS_SAMPLE_GRACE_SECONDS))" || exit 0
    kill -0 "$_watchdog_parent_pid" 2>/dev/null || exit 0
    if [ "${LIMEN_HOST_PRESSURE_STALE:-1}" = "1" ]; then
      _watchdog_output="/dev/null"
      if mkdir -p "$(dirname "$HOST_PRESSURE_WATCHDOG_LOG")" 2>/dev/null \
        && : >>"$HOST_PRESSURE_WATCHDOG_LOG" 2>/dev/null; then
        _watchdog_output="$HOST_PRESSURE_WATCHDOG_LOG"
      fi
      if [ "$_watchdog_output" = "$HOST_PRESSURE_WATCHDOG_LOG" ]; then
        fast_wave_bounded "${LIMEN_HOST_PRESSURE_WATCHDOG_TIMEOUT:-30}" \
          python3 "$LIMEN_ROOT/scripts/host-pressure-stale.py" \
          >>"$_watchdog_output" 2>&1 || true
      else
        echo "fast-wave: watchdog log unavailable — running stale probe without capture" >&2 || true
        fast_wave_bounded "${LIMEN_HOST_PRESSURE_WATCHDOG_TIMEOUT:-30}" \
          python3 "$LIMEN_ROOT/scripts/host-pressure-stale.py" || true
      fi
    else
      echo "host-pressure watchdog disabled" >>"$HOST_PRESSURE_WATCHDOG_LOG"
    fi
  done
}


fast_wave_loop() {
  _fw_parent_pid="$1"
  _fw_diurnal_pid=""
  _fw_health_pid=""
  _fw_diurnal_pending=""
  _fw_health_pending=""
  _fast_wave_cleanup() {
    for _fw_child_pid in "$_fw_diurnal_pid" "$_fw_health_pid"; do
      if [ -n "$_fw_child_pid" ] && kill -0 "$_fw_child_pid" 2>/dev/null; then
        _fast_wave_kill_tree "$_fw_child_pid"
        kill "$_fw_child_pid" 2>/dev/null || true
        wait "$_fw_child_pid" 2>/dev/null || true
      fi
    done
  }
  trap _fast_wave_cleanup EXIT
  trap 'exit 0' HUP INT TERM
  while kill -0 "$_fw_parent_pid" 2>/dev/null; do
    _fw_started="$(date +%s)"
    FAST_WAVE_BEAT=$(( FAST_WAVE_BEAT + 1 ))
    fast_wave_sample_once || true

    # Diurnal and organ-health are independent single-flight workers. If a bounded run is still
    # active, retain the latest scheduled beat and launch it as soon as that worker is free.
    if [ -n "$_fw_diurnal_pid" ] && kill -0 "$_fw_diurnal_pid" 2>/dev/null; then
      # Prefer a later beat that is due by cadence; retain the first non-due beat
      # only as an age-based fallback when no due visit has appeared.
      if _fast_wave_due_beat "${LIMEN_BEAT_DIURNAL:-1}" "$FAST_WAVE_BEAT"; then
        _fw_diurnal_pending="$FAST_WAVE_BEAT"
      else
        [ -n "$_fw_diurnal_pending" ] || _fw_diurnal_pending="$FAST_WAVE_BEAT"
      fi
    else
      [ -z "$_fw_diurnal_pid" ] || wait "$_fw_diurnal_pid" 2>/dev/null || true
      if _fast_wave_due_beat "${LIMEN_BEAT_DIURNAL:-1}" "$FAST_WAVE_BEAT"; then
        _fw_diurnal_beat="$FAST_WAVE_BEAT"
      else
        _fw_diurnal_beat="${_fw_diurnal_pending:-$FAST_WAVE_BEAT}"
      fi
      _fw_diurnal_pending=""
      fast_wave_aux_once diurnal "$_fw_diurnal_beat" &
      _fw_diurnal_pid=$!
    fi

    if [ -n "$_fw_health_pid" ] && kill -0 "$_fw_health_pid" 2>/dev/null; then
      # Keep the earliest pending visit for the same single-flight invariant as diurnal.
      [ -n "$_fw_health_pending" ] || _fw_health_pending="$FAST_WAVE_BEAT"
    else
      [ -z "$_fw_health_pid" ] || wait "$_fw_health_pid" 2>/dev/null || true
      _fw_health_beat="${_fw_health_pending:-$FAST_WAVE_BEAT}"
      _fw_health_pending=""
      fast_wave_aux_once health "$_fw_health_beat" &
      _fw_health_pid=$!
    fi

    _fw_elapsed=$(( $(date +%s) - _fw_started ))
    _fw_wait=$(( FAST_WAVE_SECONDS - _fw_elapsed ))
    [ "$_fw_wait" -gt 0 ] || _fw_wait=1
    _interruptible_sleep "$_fw_wait" || exit 0
  done
}

# NETWORK REACH — one definition, used by the connectivity gate AND by paused-beat sensing.
# True when the host the cycle depends on answers; true (fail-open) when the preflight is disabled.
net_up() {
  [ "${LIMEN_NET_PREFLIGHT:-1}" = "1" ] || return 0
  python3 -c "import socket; socket.create_connection(('${LIMEN_NET_HOST:-api.github.com}', 443), timeout=${LIMEN_NET_TIMEOUT:-3}).close()" 2>/dev/null
}
# MONITORING SENSORS + the comms sweep — read-only telemetry, extracted to a function because it
# must run from TWO call sites: the live body, and the paused branch above it.
#
# A pause must stop the fleet ACTING. It must never stop the fleet SENSING. Before this, the
# `paused` branch `continue`d ~80 lines above this block, so arming any marker silently switched
# off drift monitors, the mail sweep, and every scheduled sensor. On 2026-07-27 an agent-armed
# marker did exactly that: four days blind, during which the live checkout drifted to 27 commits
# behind origin/main with check-live-checkout.py sitting at exit 1 that nobody was asking for, and
# the inbox sweep that would have reported an already-answered thread never ran. The 2026-07-21
# hoist fixed the same shape one split down (observe), which is why this read as already-fixed.
# Cheap, cadence-gated, timeout-bounded per sensors.yaml — safe on a paused beat by construction.
run_monitoring() {
  if [ "${LIMEN_BEAT_DERIVE:-1}" = "1" ]; then
    python3 "$LIMEN_ROOT/scripts/beat-sensors.py" --run --source heartbeat --scheduled-only \
      --beat "$c" --loop-max "$MAX" --voice-dir "$VOICED" || true
  fi
  # COMMS monitoring — inbox sweep + obligations-ledger rebuild is monitoring, NOT queue mutation
  # (it flags/archives reversibly and writes its own ledger, never tasks.yaml; the send stays gated
  # by LIMEN_MAIL_SEND inside mail-beat.sh). Safe while paused for the same reason.
  play "$C_MAIL" && { bash "$LIMEN_ROOT/scripts/mail-beat.sh" 2>&1 | tail -3 || true; stamp mail; }
}
# SUBSTRATE COHERENCE — re-converge this checkout to the release. Extracted for the same reason
# run_monitoring was: it must run from the live body AND from the paused branch above it.
#
# A pause withdraws the authority to act ON THE WORLD — dispatch, spend, send, merge. Fast-forwarding
# the daemon's own checkout to already-merged trunk is not that; it is the machine keeping its own
# body coherent, the same category as sensing. Leaving it below the paused `continue` created a
# deadlock that ate its own tail: the 2026-07-21 maintenance blocker's resume_predicate requires
# "live root exact origin/main and clean", and the ONLY rung that produces that state ran solely
# when NOT paused. The halt could therefore never self-clear. Measured on 2026-07-31: a hand-run
# sync brought the tree to exact-origin at 12:04; twenty-five minutes later origin had moved and
# check-live-checkout.py was back to exit 1, naming this very script as its owner.
#
# Safe by sync-release.sh's own contract: fast-forward ONLY (never force/reset/merge-commit), fails
# open always, never exits or re-execs the daemon, and untracked runtime state — including the
# governor gate that holds the pause itself — is untouched, because a ff only advances committed
# history. A paused fleet running stale code is strictly worse: that is the state which ran a broken
# mail organ 27 commits behind origin for four days.
#
# The tradeoff this accepts: if a pause was armed BECAUSE trunk is bad, syncing while paused pulls
# that code in. Set LIMEN_PAUSED_SYNC=0 to freeze code for the duration of such a pause.
run_release_sync() {
  play "$C_SYNC" && bash "$LIMEN_ROOT/scripts/sync-release.sh" 2>&1 | tail -2 || true
}
planning_lanes() {
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
cleanup() {
  for _background_pid in "${FAST_WAVE_PID:-}" "${HOST_PRESSURE_WATCHDOG_PID:-}"; do
    if [ -n "$_background_pid" ] && kill -0 "$_background_pid" 2>/dev/null; then
      kill "$_background_pid" 2>/dev/null || true
      wait "$_background_pid" 2>/dev/null || true
    fi
  done
  rm -f "$FAST_WAVE_PID_FILE" "$HOST_PRESSURE_WATCHDOG_PID_FILE" 2>/dev/null || true
  # beat_run's capture buffer. Named by pid, reused for every rung, and removed after each — so it
  # only survives if the daemon dies mid-rung. launchd's SIGTERM (which the self-load rung relies on
  # to restart the loop) runs this trap, so the ordinary case is covered here; a SIGKILL is what the
  # startup sweep below exists for.
  rm -f "$LIMEN_ROOT/logs/.beat-rung.$$.out" 2>/dev/null || true
  rmdir "$LOCKD" 2>/dev/null || true
  if [ "$(cat "$DAEMON_LOCK" 2>/dev/null)" = "$$" ]; then
    rm -f "$DAEMON_LOCK" "$LIMEN_ROOT/logs/heartbeat-loop.pid" 2>/dev/null
    rmdir "$DAEMON_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "═══ heartbeat-loop start $(date '+%F %T') tempo=${MIN}-${MAX}s planning_lanes=$LANES campaign=institutional-omega ═══"
# This freshly-started loop IS running the current body, so any prior "loop body changed —
# kickstart pending" marker is now satisfied. sync-release only ever SETS this flag (on a
# loop-body ff) and nothing else clears it, so without this it stays set forever and the
# "kickstart needed" signal goes permanently stale. Clearing it on startup keeps the signal true.
rm -f "$LIMEN_ROOT/logs/.loop-update-pending" 2>/dev/null || true
# Sweep beat_run capture buffers left by a generation that was SIGKILLed mid-rung (jetsam on a
# 16GB host does exactly this). The EXIT trap covers every graceful death including launchd's
# SIGTERM; only a hard kill leaks, and only one file per generation — but logs/ is a watched
# directory and slow litter there is still litter. Safe as a broad glob because the atomic
# singleton guard has already been WON by this point (this process wrote its own pid well above),
# so there is no concurrent loop whose live buffer could be swept out from under it.
rm -f "$LIMEN_ROOT"/logs/.beat-rung.*.out 2>/dev/null || true
# ensure the web dashboard is served from the start
bash "$LIMEN_ROOT/scripts/refresh-web.sh" >>"$LIMEN_ROOT/logs/refresh-web.log" 2>&1 || true  # NO pipe: refresh-web backgrounds the http.server, which can inherit a pipe's write-end and block `tail` on EOF forever → wedged the whole daemon before the first beat (2026-06-23). Redirect to a log instead.
mkdir -p "$(dirname "$FAST_WAVE_PID_FILE")" 2>/dev/null || true
fast_wave_loop "$$" &
FAST_WAVE_PID=$!
printf '%s\n' "$FAST_WAVE_PID" > "$FAST_WAVE_PID_FILE" 2>/dev/null || true
stale_watchdog_loop "$$" &
HOST_PRESSURE_WATCHDOG_PID=$!
printf '%s\n' "$HOST_PRESSURE_WATCHDOG_PID" > "$HOST_PRESSURE_WATCHDOG_PID_FILE" 2>/dev/null || true
while true; do
  # OWNERSHIP BACKSTOP — if any acquisition race let a second loop through, the one whose
  # pid is NOT in the lockfile exits here. Converges to exactly one daemon within a beat.
  if [ "$(cat "$DAEMON_LOCK" 2>/dev/null)" != "$$" ]; then
    echo "no longer singleton owner (pid in lock != $$) — exiting"; exit 0
  fi
  c=$(( c + 1 ))
  worked=0
  VITALS_PRESSURE=0
  echo "──── beat $c $(date '+%F %T') ────"
  # The launchd heartbeat and its self-kickstart doctrine are retired. A manual invocation
  # executes exactly the checked-out source; bounded sensing is `limen observe --once`.
  # Drain local SessionEnd work while this process owns the singleton, even when
  # autonomy is paused or the network is offline. The consumer remains bounded
  # and fail-open so lifecycle work cannot wedge the daemon.
  drain_session_end_breadcrumbs
  MODE="$(python3 "$LIMEN_ROOT/scripts/autonomy-governor.py" mode 2>/dev/null || echo paused)"
  if [ "$MODE" = "paused" ]; then
    # Stay the singleton owner. Exiting here made launchd KeepAlive respawn a fresh
    # process every minute, so a pause paradoxically created repeated startup probes.
    #
    # SENSING SURVIVES THE PAUSE. A pause withdraws the fleet's authority to ACT; it has never
    # been a decision to stop LOOKING, and conflating the two is what made an unauthorized marker
    # cost four blind days (see run_monitoring's header). Read-only telemetry runs here, gated on
    # network reach because every sensor in it talks to a remote. The receipt is no longer
    # byte-stable across paused beats — that was a property of doing nothing, and doing nothing is
    # precisely the defect.
    if [ "${LIMEN_PAUSED_SENSING:-1}" = "1" ] && net_up; then
      echo "  paused — acting withdrawn, sensing continues"
      run_monitoring
      # And the machine keeps its own body coherent — see run_release_sync's header. Without this the
      # maintenance blocker's resume_predicate ("live root exact origin/main and clean") is
      # unsatisfiable by construction, because the only rung that satisfies it sat below this branch.
      [ "${LIMEN_PAUSED_SYNC:-1}" = "1" ] && run_release_sync
    fi
    python3 "$LIMEN_ROOT/scripts/heartbeat-paused-receipt.py" \
      --write --cadence-seconds "$PAUSED_BEAT" >/dev/null 2>&1 || true
    echo "autonomy paused by governor — stable idle receipt; next check in ${PAUSED_BEAT}s"
    sleep "$PAUSED_BEAT"
    continue
  fi
  python3 "$LIMEN_ROOT/scripts/heartbeat-paused-receipt.py" --clear >/dev/null 2>&1 || true
  # CONNECTIVITY GATE — leaving the house / Starlink not joined is a NORMAL idle beat, NOT an
  # incident. The whole body (sync-release → drain → mine → route → dispatch) needs GitHub; with
  # no network EVERY lane's gh/claude/codex call falls through to a silent-auth failure → login
  # flap → interactive sign-in tab (the overnight tab-flood + torn-write root cause). So when the
  # one host the cycle depends on is unreachable, skip the work voices and idle at MAX tempo —
  # self-heals the instant the network returns, with no file, no flag, no human. The probe is the
  # same DNS+TCP:443 reach the CLIs' own silent refresh needs; offline it caps at the short timeout
  # (and offline beats are exactly the ones we want to short-circuit). Set LIMEN_NET_PREFLIGHT=0 to
  # disable. Mirrors the per-lane _oauth_unreachable_lanes() gate, one scale up (whole beat).
  if ! net_up; then
    echo "  offline — ${LIMEN_NET_HOST:-api.github.com} unreachable; idle beat (self-heals when network returns)"
    beat_run emit-tick python3 "$LIMEN_ROOT/scripts/emit-tick.py" || true
    beat="$MAX"
    echo "── tempo: offline → ${beat}s ──"
    sleep "$beat"
    continue
  fi
  # VITALS GATE (VIGILIA build #1) — memory pressure is a NORMAL condition, not a crash.
  # The autonomic CFO remains a monitoring and reclaim gate. Provider admission now belongs
  # exclusively to the campaign supervisor and keeper, which can still route safe off-box work
  # under local pressure. VITALS also sheds ollama. Fail-OPEN: sensor fault → 'ok'.
  if [ "${LIMEN_VIGILIA:-1}" = "1" ]; then
    _vitals="$(python3 -m limen.vigilia vitals-gate 2>/dev/null || echo ok)"
    if [ "$_vitals" = "shed" ]; then
      echo "  vitals: memory pressure ≥ critical — local reclaim census deferred; campaign admission remains keeper-owned"
      VITALS_PRESSURE=1
    elif [ "$_vitals" = "throttle" ]; then
      echo "  vitals: memory pressure ≥ warn — campaign admission remains keeper-owned"
    fi
  fi
  EFFECTIVE_LANES="$LANES"
  if [ "$VITALS_PRESSURE" = "1" ]; then
    echo "── vitals-pressure: local hygiene reduced; canonical campaign wake remains live ──"
  fi
    # SUBSTRATE SELF-HEAL — re-converge this checkout to the release (origin/main) before doing
    # work, so the beat always runs the latest code (push = deploy). ff-only, data-preserving,
    # fail-open; never exits/re-execs the daemon. Closes the loop: root → leaf → back to root.
    # The block itself now lives in run_release_sync() so the paused branch above can call it too.
    run_release_sync
    # BOARD-INTEGRITY self-heal — if the SSOT queue is unloadable or collapsed (a clobber that
    # slipped past the save-time guard, or external corruption), restore it from HEAD BEFORE the
    # body tries to load it, so a dead board self-recovers instead of idling the fleet for hours
    # (the 2026-06-26 halt). Idempotent: a healthy board is a fast no-op, no network. See
    # heal-board.py + the limen.io collapse-guard — "fix the handoff so it ain't broken".
    # PRIVATE-BOARD CUSTODY — refresh the off-repo full board from the authenticated keeper
    # BEFORE anything reads board state this beat. After the partition cutover the public
    # tasks.yaml is a counts-only aggregate, and every consumer resolves through
    # private_board.operational_board_path(): stale custody means stale CAS preconditions
    # ("exact revision moved"), and MISSING custody is a loud error, never an empty board.
    # Pre-cutover this is a cheap no-op — the rung self-arms off the public file's shape.
    [ "${LIMEN_BOARD_PRIVATE_HYDRATE:-1}" = "1" ] \
      && beat_run hydrate-private-board bash "$LIMEN_ROOT/scripts/hydrate-private-board.sh" || true
    beat_run heal-board python3 "$LIMEN_ROOT/scripts/heal-board.py" || true
    # TABVLARIVS RELAY — submit the lock-free ticket inbox to the authenticated remote conduct
    # keeper. Archive only tickets with canonical projection receipts; broker outages leave the
    # unacknowledged suffix pending. The local tasks.yaml is read-only cache evidence, never a
    # lifecycle writer. Idempotent: an empty inbox is an instant no-op.
    [ "${LIMEN_TABVLARIVS:-1}" = "1" ] && beat_run tabularius-organ python3 "$LIMEN_ROOT/scripts/tabularius-organ.py" || true
    # CANONICAL BOARD RECONCILE — the BOARD-INTEGRITY preflight above reads tasks.yaml, which
    # mirrors the keeper only after a board-publication PR merges to main. When that merge stalls,
    # canonical drift lands somewhere NO self-heal rung can see, and each one reports a healthy
    # board while looking at a stale copy of it. Measured 2026-08-07: twelve needs-human-labelled
    # ASK-quicken-* tasks (login/credential/delete/send) sat at `open` on the keeper's published
    # projection while main had them correctly at needs_human — so heal-board found nothing wrong
    # while the canonical board was the one offering human-gated levers to the fleet, AND that same
    # drift held main red on validate-task-board.py (needs-human-in-open), blocking the very
    # publication merge that would have refreshed the mirror. A closed loop where the drift
    # protects itself from the repair; this line is what opens it. Submits through the authenticated
    # relay with the published board as the explicit compare-and-swap base, never writes locally,
    # and no-ops when the publication ref is unreadable. Fail-open like its siblings.
    # ORDER: this runs BEFORE the publication rung below, because the drift it repairs is exactly
    # what holds validate-task-board red on the publication PR. Heal-then-publish converges in one
    # beat; publish-then-heal opens a red PR and waits for the next one.
    [ "${LIMEN_BOARD_CANONICAL_HEAL:-1}" = "1" ] && beat_run heal-board-canonical python3 "$LIMEN_ROOT/scripts/heal-board.py" --canonical || true
    # BOARD PUBLICATION — open the PR that carries the keeper's published projection into main. The
    # PR-opening half of preserve_board_projection was retired with the local publication writer and
    # never replaced (BOARD_PUBLICATION_TITLE has been a dead constant since), so the keeper kept
    # publishing to tabularius/board-projection and nothing carried it to main. Last publication
    # merged 2026-07-26 (#1569) — exactly the track.date the board was then frozen at for 12 days,
    # while the local tasks.yaml was byte-identical to origin/main (current checkout, dead rung). The
    # frozen copy is what dispatch SELECTS from, what every receipt's compare-and-swap precondition
    # is computed from, and what lane_throughput_window counts 0 dispatches in — pinning jules in
    # bootstrap at 25/day and putting 100/day out of reach (#1995). Opens or reports only; never
    # merges, never pushes. Idempotent and fail-open.
    [ "${LIMEN_BOARD_PUBLISH_PR:-1}" = "1" ] && beat_run publish-board-pr bash "$LIMEN_ROOT/scripts/publish-board-pr.sh" || true
    # ENACTMENT — surface any declared-ON fleet flag that is dark/stale in THIS running beat (memory:
    # enacted-not-declared). THE LIVE-LOOP HOME: metabolize.sh has the same advisory but the daemon
    # never runs metabolize (only saturate.sh does — route.py:208), so this line is what makes the
    # check actually fire on the fleet. Spawned fresh each beat like the organs above → deploys on the
    # next sync-release ff; but adding THIS line is a loop-body edit, so it needs a kickstart to load.
    # Fail-open, log-only (never chat), like creds/link health in metabolize §0d.
    [ "${LIMEN_ENACTMENT_CHECK:-1}" = "1" ] && beat_run enactment-audit-check python3 "$LIMEN_ROOT/scripts/enactment-audit.py" --check || true
    beat_run usage-telemetry python3 "$LIMEN_ROOT/scripts/usage-telemetry.py" || true   # refresh lane health before planning/campaign wake
    beat_run codex-token-accounting python3 "$LIMEN_ROOT/scripts/codex-token-accounting.py" \
      --since-hours "${LIMEN_CODEX_TOKEN_REPORT_HOURS:-6}" \
      --limit-sessions "${LIMEN_CODEX_TOKEN_REPORT_LIMIT:-25}" \
      --output "$LIMEN_ROOT/logs/codex-token-report.json" || true   # visible session spend report
    beat_run claude-usage python3 "$LIMEN_ROOT/scripts/claude-usage.py" || true   # claude usage: multi-avenue cascade → logs/claude-usage.json
    EFFECTIVE_LANES="$(planning_lanes "$LANES")"
    if [ "$EFFECTIVE_LANES" != "$LANES" ]; then
      echo "  planning lanes: ${EFFECTIVE_LANES:-none} active from selector [$LANES]"
    fi

    # MONITORING SENSORS — hoisted ABOVE the observe/dispatch split so read-only telemetry (mail
    # sweep, inbound-opportunity detect, launch-agent liveness, drift monitors) runs on EVERY live
    # beat, observe mode included. Previously this block sat below the observe branch's `continue`,
    # so whenever the session-value-gate throttled MODE→observe the whole monitoring apparatus went
    # dark: 2026-07-21 → 22h blind (opportunity + all scheduled sensors 22-24h stale while the beat
    # idled at MAX tempo). Monitoring must NOT be gated by dispatch mode. Cheap, cadence-gated, and
    # timeout-bounded per sensors.yaml; the expensive dispatch/mine/route work stays gated below.
    # This legacy loop is explicit-only; bounded sensing uses `limen observe --once`.
    # The block itself now lives in run_monitoring() so the paused branch above can call it too.
    run_monitoring

    # METABOLIZE SENSOR PASS — the source:[metabolize] registry sensors (jules-quota/-supply,
    # dispatch-continuity, lane-fitness, jules-dispatch, capacity refreshes, …) had NO live
    # caller since metabolize.sh lost its schedulers (unreachable-runners-baseline). This rung
    # is their runner. Placed ABOVE the observe short-circuit ON PURPOSE: the pass carries the
    # starvation alarm and the quota/supply gauges, which must fire precisely when the estate
    # is observing (the 15-day outage was an observe-mode outage) — while dispatch itself stays
    # impossible in observe because the jules-dispatch rung self-gates on
    # `autonomy-governor.py dispatch-ok` (logs/autonomy-policy.json is the single valve).
    # Wall-clock throttled (hourly), per-sensor timeout-bounded by the registry, `|| true`
    # guarded: a failing sensor never fails the beat.
    #
    # THE PASS'S OUTPUT IS THE PRODUCT — it must not be piped away. 57 sensors emit well over a
    # hundred lines here and `| tail -5` kept five, so every finding from every sensor but the last
    # was produced and then discarded. Measured 2026-08-07: the review-harvest sensor (§0g3a, line
    # 32 of the pass) ran in the 17:49 pass carrying unresolved agent findings, and no log anywhere
    # in the estate recorded a word of it — the organ built to prove a finding gets CONSUMED had its
    # own finding thrown away by its runner. beat-sensors.py persists nothing itself: a voice stamp
    # records that a sensor VISITED, never what it said, which is the same liveness-for-consumption
    # substitution one layer down. This redirect is the only durable home.
    #
    # Truncating (`>`) rather than appending keeps it bounded with no rotation organ to maintain:
    # the pass re-runs hourly and reports CURRENT state, so the latest pass is the whole answer.
    # The beat log stays exactly as terse as before — the same five lines, now read back from the
    # file rather than being all that survived. `|| true` still guards the python, not a pipeline,
    # so the rung's own exit code is the sensor runner's and never `tail`'s.
    if [ "${LIMEN_BEAT_DERIVE:-1}" = "1" ] && metabolize_pass_due; then
      python3 "$LIMEN_ROOT/scripts/beat-sensors.py" --run --source metabolize \
        --beat "$c" --loop-max "$MAX" --voice-dir "$VOICED" \
        >"$LIMEN_ROOT/logs/metabolize-sensors.log" 2>&1 || true
      tail -5 "$LIMEN_ROOT/logs/metabolize-sensors.log" 2>/dev/null || true
      stamp metabolize_pass
    fi

    if [ "$MODE" != "dispatch" ]; then
      echo "autonomy mode=$MODE — telemetry/status only; queue mutation and campaign wake skipped"
      # HANDOFF — even an observe-only beat refreshes the warm-resume packet.  The heartbeat does
      # not invoke metabolize.sh, so this direct seam is required to keep continuity truthful.
      beat_run handoff-relay python3 "$LIMEN_ROOT/scripts/handoff-relay.py" || true
      beat_run emit-tick python3 "$LIMEN_ROOT/scripts/emit-tick.py" || true
      play "$C_WEB" && bash "$LIMEN_ROOT/scripts/refresh-web.sh" >>"$LIMEN_ROOT/logs/refresh-web.log" 2>&1 || true  # NO pipe: refresh-web backgrounds the http.server, which can inherit a pipe's write-end and block `tail` on EOF forever → wedged the whole daemon before the first beat (2026-06-23). Redirect to a log instead.
      beat="$MAX"
      echo "── tempo: observe → ${beat}s ──"
      sleep "$beat"
      continue
    fi

    # acquire the shared queue lock so the BODY never races a SUPERVISOR write to
    # tasks.yaml (two-scale safety). If a supervisor holds it, skip queue-mutation this
    # beat (still emit tick/web below). Wait up to ~20s.
    locked=0
    for _ in $(seq 1 20); do
      if mkdir "$LOCKD" 2>/dev/null; then
        printf '%s\n' "$$" > "$LOCKD/pid" 2>/dev/null || true
        date -u '+%Y-%m-%dT%H:%M:%SZ' > "$LOCKD/created_at" 2>/dev/null || true
        locked=1
        break
      fi
      sleep 1
    done

    if [ "$locked" = 1 ]; then
      export LIMEN_QUEUE_LOCK_HELD=1
      DRAIN_VOICE_DUE=0
      due_voice drain "$C_DRAIN"   && { DRAIN_VOICE_DUE=1
                                       bash "$LIMEN_ROOT/scripts/drain.sh" 2>&1 | tail -2 || true        # VERIFY
                                       beat_run limen-release-stale python3 -m limen release-stale --hours 24 --apply || true; }
      due_voice heal "$C_HEAL"     && beat_run recover python3 "$LIMEN_ROOT/scripts/recover.py" --apply || true   # HEAL

      # Release the broad heartbeat mutex before producer/planner voices. Those scripts either submit
      # Tabularius tickets or acquire their own short queue_lock, so a slow feed/rebalance pass cannot
      # starve supervisors and high-value async claims for minutes.
      unset LIMEN_QUEUE_LOCK_HELD
      rm -f "$LOCKD/pid" "$LOCKD/created_at" 2>/dev/null || true
      rmdir "$LOCKD" 2>/dev/null || true
      locked=0

      play "$C_FEED"               && { beat_run mine-backlog env LIMEN_TICKETS_PRODUCE=1 python3 "$LIMEN_ROOT/scripts/mine-backlog.py" --limit "${LIMEN_MINE_LIMIT:-25}" --apply || true  # EXPLORE
                                       [ "${LIMEN_REVENUE_BACKLOG:-1}" = "1" ] && beat_run generate-revenue-backlog env LIMEN_TICKETS_PRODUCE=1 timeout "${LIMEN_REVENUE_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-revenue-backlog.py" --apply || true  # REVENUE FIRST: ladder→tasks so win-class capacity builds products, not busywork (default-ON; floor-gated)
                                       [ "${LIMEN_ORGAN_BACKLOG:-1}" = "1" ] && beat_run generate-organ-backlog env LIMEN_TICKETS_PRODUCE=1 timeout "${LIMEN_ORGAN_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-organ-backlog.py" --apply || true  # ORGANS (VLTIMA): organ-ladder->tasks so idle capacity builds the institutional pillars (legal/financial/education/...), not busywork (default-ON; floor-gated)
                                       beat_run generate-backlog env LIMEN_TICKETS_PRODUCE=1 timeout "${LIMEN_GENERATE_BACKLOG_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-backlog.py" --apply || true  # SELF-FEED: build-out levers on the ranked tier
                                       [ "${LIMEN_STUDIUM:-0}" = "1" ] && beat_run ingest-backlog timeout "${LIMEN_STUDIUM_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/ingest-backlog.py" --apply || true  # STUDIUM: re-emit the staged canon-breadth content tasks each beat so they SURVIVE the prune (a one-shot hand-apply gets clobbered; idempotent, gated, lockless)
                                       beat_run discover-value python3 "$LIMEN_ROOT/scripts/discover-value.py" --apply || true; }  # DISCOVER: no repo stays dark — surface latent value, burn the tank
      # Routing is a live claim-time decision. target_agent is durable eligibility/ownership
      # metadata, so a balance beat may inspect the plan but must never rewrite the tracked board.
      play "$C_BALANCE"            && { beat_run route python3 "$LIMEN_ROOT/scripts/route.py" || true   # PLAN
                                       if [ -n "$EFFECTIVE_LANES" ]; then
                                         beat_run rebalance python3 "$LIMEN_ROOT/scripts/rebalance.py" --lanes "$EFFECTIVE_LANES" || true
                                       else
                                         echo "no live local lanes available for rebalance"
                                       fi; }
      # proprioception stamps — record that these voices played this beat (route rides the balance voice)
      due_voice drain "$C_DRAIN"   && stamp drain
      play "$C_FEED"               && stamp feed
      play "$C_BALANCE"            && stamp balance

      # The queue lock was already released before feed/balance; dispatch self-acquires the SAME
      # lockdir around reserve and reloads-fresh+commits under it.

      # RECLAIM is intentionally outside the queue lock. It can spend minutes scanning
      # worktrees with git status/cherry; holding the board mutex there starves harvest/refill.
      if [ "${DRAIN_VOICE_DUE:-0}" = "1" ] && [ "${LIMEN_RECLAIM:-1}" = "1" ]; then
        reclaim_apply_args=()
        [ "${LIMEN_RECLAIM_APPLY:-1}" = "1" ] && reclaim_apply_args+=(--apply)
        # The cheap generated-only pass (just-finished lanes) ALWAYS runs — it closes this beat's own
        # worktree debt at negligible cost. The FULL estate census (git status/cherry across every
        # worktree — the git storm over ~71 roots) is deferred while VITALS is SHEDDING (memory/swap
        # ≥ critical), so the beat never thrashes an already-starved host to relieve worktree debt.
        # It resumes the next unpressured beat. The shared controller bounds each whole cycle and
        # makes the full pass an exact check(JSON)+SHA-validated apply transaction. This live loop
        # explicitly scans repo-local and registered worktrees even though LIMEN_WORKTREE_ROOT is
        # set; library callers and isolated tests retain worktree_roots.py's "auto" semantics.
        LIMEN_RECLAIM_REPO_LOCAL_WT=1 LIMEN_RECLAIM_REGISTERED_WT=1 \
          PYTHONPATH="$PYTHONPATH" python3 "$LIMEN_ROOT/scripts/reclaim-cycle.py" \
            --timeout "${LIMEN_RECLAIM_GENERATED_TIMEOUT:-120}" \
            "${reclaim_apply_args[@]}" --generated-only || \
          echo "  reclaim: generated-only cycle failed — next beat retries"
        if [ "$VITALS_PRESSURE" != "1" ]; then
          LIMEN_RECLAIM_REPO_LOCAL_WT=1 LIMEN_RECLAIM_REGISTERED_WT=1 \
            PYTHONPATH="$PYTHONPATH" python3 "$LIMEN_ROOT/scripts/reclaim-cycle.py" \
              --timeout "${LIMEN_RECLAIM_TIMEOUT:-300}" "${reclaim_apply_args[@]}" || \
            echo "  reclaim: full cycle failed — next beat retries"
        else
          echo "  reclaim: full estate census deferred — vitals shedding (memory/swap critical)"
        fi
      fi

      # LIFECYCLE PRESSURE — refresh the counts-only worktree-debt cache on the existing drain
      # cadence, after any accepted reclaim. The generator's own throttle avoids repeating the
      # estate-wide git census on fast beats; the outer timeout bounds this non-hot-path producer.
      # always-working.py derives freshness from this exact cadence + throttle + timeout, so a
      # zero-debt receipt remains green until the next scheduled refresh while stale/missing state
      # fails closed. This never runs in the per-candidate dispatch path.
      if [ "${DRAIN_VOICE_DUE:-0}" = "1" ]; then
        timeout "${LIMEN_RECLAIM_TIMEOUT:-300}" \
          python3 "$LIMEN_ROOT/scripts/session-lifecycle-pressure.py" --write \
            --throttle "${LIMEN_LIFECYCLE_PRESSURE_THROTTLE:-1800}" 2>&1 | tail -2 || true
      fi

    else
      echo "── queue lock held by a supervisor — skipping mutation this beat ──"
    fi

  # BUILD WAKE — the heartbeat never chooses a provider or reserves work itself.
  # It invokes one admitted finite campaign through the canonical supervisor. The
  # adapter re-proves exact remote-default state, capsule custody, conductor identity,
  # and the bounded campaign result. Broker capability discovery owns all routing.
  _campaign_t0=$SECONDS
  out="$(campaign_wake_bounded \
    python3 "$LIMEN_ROOT/scripts/campaign-heartbeat.py" \
      --root "$LIMEN_ROOT" \
      --workstream institutional-omega 2>&1)"
  _campaign_rc=$?
  if [ "$_campaign_rc" = 137 ] || [ "$_campaign_rc" = 124 ]; then
    echo "── ⚠ CAMPAIGN WAKE CEILING HIT after ${CAMPAIGN_WAKE_CEILING}s (wake took $((SECONDS-_campaign_t0))s); no fallback provider launch occurred ──"
  fi
  echo "$out" | tail -4
  echo "$out" | grep -qE '"boundary"[[:space:]]*:[[:space:]]*"continue"' && worked=1
  stamp campaign

  # RECONCILE — outside the queue-lock (heal-dispatch self-acquires it, so it must NOT run
  # under the daemon's lock or it would deadlock). Verify claimed dispatches vs real PR state,
  # then flip phantom → done/open so the funnel self-clears and the open pool refills each cycle.
  due_voice heal "$C_HEAL" && { beat_run verify-dispatch python3 "$LIMEN_ROOT/scripts/verify-dispatch.py" || true
                      beat_run heal-dispatch python3 "$LIMEN_ROOT/scripts/heal-dispatch.py" --apply || true
                      # LEDGER — weigh the RETURN on every newly-resolved task (the credit side), then
                      # roll up the value verdict (which lane earns its keep / what was sunk money).
                      beat_run score-dispatch python3 "$LIMEN_ROOT/scripts/score-dispatch.py" || true
                      beat_run ledger python3 "$LIMEN_ROOT/scripts/ledger.py" || true
                      # SELF-HEAL — the repair FACTORY (complements heal-dispatch's phantom-reconcile): classify the
                      # fleet's REFUSED PRs (CI-red / conflicting) and emit HEAL-cifix / HEAL-rebase tasks so the
                      # router+dispatcher fix them and merge-drain then LANDS them. merge-drain is the bouncer; THIS is
                      # the factory. Silent since 2026-06-30 — the machine worked, but no beat ever turned the crank, so
                      # DIRTY/BLOCKED PRs piled up read as "blockers" instead of becoming work. Bounded rotating --scan
                      # window + already-queued dedup = idempotent; self-acquires the queue-lock (safe outside the daemon
                      # lock, like heal-dispatch) and skips cleanly when the daemon holds it; network → timeout-wrapped,
                      # fail-open. Redirects existing budgeted dispatch from receipt-churn to real PR repair; off with
                      # LIMEN_SELF_HEAL=0.
                      [ "${LIMEN_SELF_HEAL:-1}" = "1" ] && beat_run self-heal-scan timeout "${LIMEN_SELF_HEAL_TIMEOUT:-300}" python3 "$LIMEN_ROOT/scripts/self-heal.py" --scan "${LIMEN_SELF_HEAL_SCAN:-30}" || true; }
  due_voice heal "$C_HEAL"    && stamp heal
  # Scheduled registry sensors (cadence/timeout/argv/gate all from sensors.yaml, no sensor names in
  # the runner) were HOISTED above the observe/dispatch split — see the block right before
  # `if [ "$MODE" != "dispatch" ]`. They must run every live beat (observe mode included), not only
  # on dispatch beats; the 2026-07-21 22h-blind incident was exactly this block sitting below the
  # observe-branch `continue`. Do not re-add a dispatch-gated copy here.
  # DISK PRESSURE — when the live resource envelope is negative, run hygiene (clone-maintenance:
  # capture→reap→node_modules) EVERY beat, not just every C_HYGIENE, until it drains back under
  # target. Reclaim intensity tracks real fullness instead of a fixed clock (the "creeps back to
  # full" fix). Cheap df probe; off with LIMEN_DISK_PRESSURE_ESCALATE=0.
  HYG_CAD="$C_HYGIENE"
  if [ "${LIMEN_DISK_PRESSURE_ESCALATE:-1}" = "1" ]; then
    # ABSOLUTE free (GiB), not df% — df counts ~100GB of purgeable-but-reclaimable APFS space as
    # "used", so a 95%-by-percent disk with ~120GB effectively free would falsely ramp hygiene to
    # EVERY beat and slow the whole beat (clone-maintenance runs each tick). Ramp only when raw free
    # genuinely drops below the graph-derived requirement. ([[meter-lie-and-dead-daemon-incident]])
    _dfree="$(df -Pk "${LIMEN_WORKDIR:-$HOME/Workspace}" 2>/dev/null | awk 'NR==2 {print int($4/1048576)}')"
    _required_free="$(PYTHONPATH="$LIMEN_ROOT/cli/src" python3 -m limen.resource_envelope 2>/dev/null || true)"
    # Memory-shed OVERRIDES the disk-pressure ramp: never ramp the clone-maintenance git storm to
    # EVERY beat to relieve DISK while MEMORY/swap is critical — that trades a slow disk for a
    # thrashing host. Under shed, hold the normal cadence (and the git voices below skip anyway).
    if [ "$VITALS_PRESSURE" != "1" ]; then
      if [ -z "$_dfree" ] || [ -z "$_required_free" ]; then
        HYG_CAD=1
      elif awk -v free="$_dfree" -v required="$_required_free" 'BEGIN {exit !(free < required)}'; then
        HYG_CAD=1
      fi
    fi
  fi
  # clone-maintenance (git gc/prune across every repo) + reap-clones are local git storms; skip BOTH
  # while VITALS is shedding so the beat adds no git load to a memory/swap-critical host. They resume
  # the next unpressured beat. heal-claude-update-marker (below) is cheap and still runs.
  if [ "$VITALS_PRESSURE" != "1" ]; then
    due_voice hygiene "$HYG_CAD" && bash "$LIMEN_ROOT/scripts/clone-maintenance.sh" 2>&1 | tail -3 || true
  else
    due_voice hygiene "$HYG_CAD" && echo "  hygiene: clone-maintenance + reap-clones deferred — vitals shedding"
  fi
  # CLONE-REAP — the actual eviction. clone-maintenance.sh only *reports* reapable clones; reap-clones.py
  # removes the loss-free pushed-mirror class (adversarially-audited gate + standing grant). Beat-wired
  # 2026-07-09 so the reclaim engine is ALIVE instead of a script that never ran (the round-two storage
  # deadlock: ~/Workspace crept back because nothing autonomously reaped it). Self-gates on disk pressure
  # + idle age; intensity follows the live envelope. Disarm --apply with LIMEN_REAP_CLONES_APPLY=0.
  REAP_CLONES_ARG=""; [ "${LIMEN_REAP_CLONES_APPLY:-1}" = "1" ] && REAP_CLONES_ARG="--apply"
  [ "$VITALS_PRESSURE" != "1" ] && due_voice hygiene "$HYG_CAD" && timeout "${LIMEN_REAP_CLONES_TIMEOUT:-300}" python3 "$LIMEN_ROOT/scripts/reap-clones.py" $REAP_CLONES_ARG 2>&1 | tail -3 || true
  due_voice hygiene "$HYG_CAD" && beat_run heal-claude-update-marker bash "$LIMEN_ROOT/scripts/heal-claude-update-marker.sh" || true
  # heal-claude-lsregister.sh / heal-hook-drift.sh / heal-claude-cask.sh are NO LONGER hand-wired here:
  # they run as the registry-derived `dialogs-silenced` sensor (institutio/governance/sensors.yaml 0g8b)
  # on the scheduled heartbeat derive lane above (beat-sensors.py --run --source heartbeat
  # --scheduled-only, cadence LIMEN_BEAT_DIALOGS=8 == this hygiene cadence), then verified by
  # dialogs-silenced.sh --agent-curable-only. Hand-wiring them too would double-run; adding a new dialog
  # effector is now one sensors.yaml step, not a shell line here.
  due_voice hygiene "$HYG_CAD" && stamp hygiene
  beat_run emit-tick python3 "$LIMEN_ROOT/scripts/emit-tick.py" || true   # tick voice — every beat
  stamp tick
  # PROPRIOCEPTION for the DISCOVERED organs that fire every beat but never stamped, so the health
  # face read "unknown" for them (sync/web/censor/insight_cadence/report/quicken/corpus_feed). `play`
  # is a pure due-check (the green organs already call it a 2nd time to stamp, e.g. `play "$C_FEED" &&
  # stamp feed`), so this records real liveness on each organ's own cadence. Placed BEFORE the render
  # below so the tick greens them the SAME beat. Fail-open like every other stamp. ([[no-never-happens-again]])
  play "$C_SYNC"             && stamp sync
  play "$C_WEB"              && stamp web
  play "$C_CENSOR"           && stamp censor
  play "$C_INSIGHT_CADENCE"  && stamp insight_cadence
  play "$C_REPORT"           && stamp report
  play "$C_QUICKEN"          && stamp quicken
  play "$C_CORPUS_FEED"      && stamp corpus_feed
  [ "${LIMEN_VIGILIA:-1}" = "1" ] && { beat_run vigilia python3 -m limen.vigilia beat || true; stamp vigilia; }   # VIGILIA autonomic executive — record vitals/continuity/integrity to the seat (read-only, fail-open)
  play "$C_WEB"     && beat_run usage-telemetry python3 "$LIMEN_ROOT/scripts/usage-telemetry.py" || true   # real per-vendor usage
  play "$C_WEB"     && beat_run codex-token-accounting python3 "$LIMEN_ROOT/scripts/codex-token-accounting.py" --since-hours "${LIMEN_CODEX_TOKEN_REPORT_HOURS:-6}" --limit-sessions "${LIMEN_CODEX_TOKEN_REPORT_LIMIT:-25}" --output "$LIMEN_ROOT/logs/codex-token-report.json" || true   # per-session Codex spend report
  play "$C_WEB"     && beat_run claude-usage python3 "$LIMEN_ROOT/scripts/claude-usage.py" || true   # claude usage: multi-avenue cascade gauge
  play "$C_WEB"     && beat_run money-view python3 "$LIMEN_ROOT/scripts/money-view.py" || true   # revenue-first money view (no network, can't time out)
  play "$C_WEB"     && beat_run corpus-view python3 "$LIMEN_ROOT/scripts/corpus-view.py" || true   # knowledge-base view: THE ONE + convergence activity (no network)
  play "$C_WEB"     && beat_run ingest-coverage python3 "$LIMEN_ROOT/scripts/ingest-coverage.py" || true   # diagnostic: are we at 100% context? sources + freshness + adapter gaps (read-only over the manifest)
  play "$C_WEB"     && beat_run omni-view python3 "$LIMEN_ROOT/scripts/omni-view.py" || true   # THE ONE SURFACE: value verdict + board + fleet + revenue + everything, past/present/future (no network)
  play "$C_WEB"     && beat_run obligations-view python3 "$LIMEN_ROOT/scripts/obligations-view.py" || true   # mail obligations face refresh (no network)
  play "$C_WEB"     && beat_run pillars-view python3 "$LIMEN_ROOT/scripts/pillars-view.py" || true   # platform-of-pillars convergence map: program ladder + per-pillar live/stale status (no network)
  # (COMMS mail voice was HOISTED above the observe/dispatch split — see the block right before
  # `if [ "$MODE" != "dispatch" ]` — so the inbox sweep runs every live beat, observe mode included.
  # Do not re-add a dispatch-gated copy here.)
  due_voice continuation "$C_CONTINUATION" && [ "${LIMEN_CONTINUATION:-1}" = "1" ] && \
    { if [ -n "$DISPATCH_TIMEOUT_BIN" ]; then
        "$DISPATCH_TIMEOUT_BIN" -s KILL "${LIMEN_CONTINUATION_TIMEOUT:-600}" python3 "$LIMEN_ROOT/scripts/continuation-beat.py" --apply 2>&1 | tail -6 || true
      else
        python3 "$LIMEN_ROOT/scripts/continuation-beat.py" --apply 2>&1 | tail -6 || true
      fi
      stamp continuation; }
  play "$C_WEB"     && beat_run notify-events python3 "$LIMEN_ROOT/scripts/notify-events.py" || true   # push: your-gate ready / ship milestones
  # CENSOR — the insights→actions institution. Records its decisions + renders censor.html EVERY
  # run so it is observable BEFORE it is autonomous; the executive only acts when armed
  # (LIMEN_CENSOR_APPLY=1). Tiers (hourly/daily/weekly) self-gate on wall-clock. Bounded + fail-open.
  play "$C_CENSOR"  && beat_run censor python3 "$LIMEN_ROOT/scripts/censor.py" $([ "${LIMEN_CENSOR_APPLY:-0}" = "1" ] && echo --apply) || true
  play "$C_WEB"     && beat_run censor-view python3 "$LIMEN_ROOT/scripts/censor-view.py" || true   # the Censor's face (no network, can't time out)
  play "$C_WEB"     && [ "${LIMEN_STUDIUM:-0}" = "1" ] && beat_run studium-daily python3 "$LIMEN_ROOT/scripts/studium.py" --daily || true   # daily transmission-curriculum face (gated; advances once/day, no network, can't time out)
  play "$C_INSIGHT_CADENCE" && beat_run insight-cadence-once python3 "$LIMEN_ROOT/scripts/insight-cadence.py" --once || true  # INSIGHT-CADENCE: draft insight reports at four wall-clock cadences
  play "$C_INSIGHT_CADENCE" && beat_run insight-route python3 "$LIMEN_ROOT/scripts/insight-route.py" || true  # INSIGHT-ROUTE: latest report per tier → durable owner (levers / keeper tickets / organ residuals)
  # CENSOR-ISSUES — mirror live censor residuals → public `censor` GitHub issues (auto-open on
  # warning, auto-close when the lineage clears, human closes vetoed forever, capped per pass).
  # Observable before autonomous: dry-runs each beat until LIMEN_CENSOR_ISSUES_APPLY=1 arms it
  # (the same constitutional pattern as LIMEN_CENSOR_APPLY on the censor itself).
  play "$C_CENSOR"  && beat_run sync-censor-issues python3 "$LIMEN_ROOT/scripts/sync-censor-issues.py" $([ "${LIMEN_CENSOR_ISSUES_APPLY:-0}" = "1" ] && echo --apply) || true
  # HEALTH — the personal health office (chart digest + visit-prep + clinical-loop chase; PII stays
  # local, off-repo; lockless, read-only). Refreshes the office every C_HEALTH beats. Fail-open.
  due_voice health "$C_HEALTH"  && { beat_run health-organ python3 "$LIMEN_ROOT/scripts/health-organ.py" || true; stamp health; }
  # MAT — the daily-engine keeper (private-tree session pull + day-card pre-compose + roadblocks
  # queue; organ self-throttles to ~1 fire/day; counts-only state, PII stays off-repo). Fail-open.
  due_voice mat "$C_MAT"        && { beat_run mat-organ python3 "$LIMEN_ROOT/scripts/mat-organ.py" || true; stamp mat; }
  # LIFE — the digital-life office (accounts/assets/subscriptions; PII stays local, off-repo;
  # lockless, read-only). Refreshes the life briefing + open-actions + derives the subscription
  # purge clock every C_LIFE beats. Fail-open.
  due_voice life "$C_LIFE"    && { beat_run life-organ python3 "$LIMEN_ROOT/scripts/life-organ.py" || true; stamp life; }
  # GOVERNANCE — run the cursus honorum seed validator + governance standing report every C_GOVERNANCE
  # beats. Operationalizes the governance rules (cvrsvs-honorvm) as an autonomous beat: validates
  # every seed.yaml in the estate, stamps the governance voice for proprioception. Read-only,
  # lockless, idempotent, fail-open — never gates the beat. Gate off with LIMEN_GOVERNANCE=0.
  due_voice governance "$C_GOVERNANCE" && [ "${LIMEN_GOVERNANCE:-1}" = "1" ] && \
    { beat_run governance-organ python3 "$LIMEN_ROOT/scripts/governance-organ.py" || true; stamp governance; }
  # FINANCE — run the financial-office consolidator (regenerate balance-sheet, cash-flow, STATUS from
  # entity data) + assess maturity + advance organ-ladder.json as slices land. Lockless, idempotent,
  # fail-open — never gates the beat. Gate off with LIMEN_FINANCIAL=0.
  due_voice financial "$C_FINANCIAL" && [ "${LIMEN_FINANCIAL:-1}" = "1" ] && \
    { beat_run financial-organ python3 "$LIMEN_ROOT/scripts/financial-organ.py" || true; stamp financial; }
  # DISCLOSE — verify the publication-policy engine (the ONE content-disposition decision) stays sound
  # every C_PUBPOLICY beats: redactor owner-scoped (never eats product emails / placeholders / 555
  # fixtures), disposition matrix + classifier intact. Read-only self-test, stamps the pubpolicy voice.
  # Idempotent, fail-open — never gates the beat. Gate off with LIMEN_PUBPOLICY=0.
  due_voice pubpolicy "$C_PUBPOLICY" && [ "${LIMEN_PUBPOLICY:-1}" = "1" ] && \
    { beat_run publication-policy-verify python3 "$LIMEN_ROOT/scripts/publication-policy.py" --verify || true; stamp pubpolicy; }
  # CVSTOS — the keeper of the host. Every C_CVSTOS beats: census the chat-app/local debt (all
  # vendors, not just Claude), measure the factory-host invariant (nothing truly on PATH/local), and
  # give the scattered reapers one liveness face. READ-ONLY (surface) — the regenerable-cache reclaim
  # (--apply) stays a human lever until he classifies what's safe to purge. Lockless, fail-open —
  # never gates the beat. Gate off with LIMEN_CVSTOS=0.
  due_voice cvstos "$C_CVSTOS" && [ "${LIMEN_CVSTOS:-1}" = "1" ] && \
    { beat_run cvstos-organ timeout "${LIMEN_RECLAIM_TIMEOUT:-300}" python3 "$LIMEN_ROOT/scripts/cvstos-organ.py" || true; stamp cvstos; }
  # VVLTVS — the countenance (sibling of CVSTOS: CVSTOS faces the machine, VVLTVS faces the world).
  # Every C_VVLTVS beats: verify the public face reflects the live SSOT — the profile bio + portfolio
  # copies vs organvm-corpvs-testamentvm/system-metrics.json — and surface the contribution-mix radar
  # (the ~0.6% code-review tell). OFFLINE on the beat (reads the SSOT + face files + cached mix; never
  # hits `gh api` per beat unless LIMEN_VVLTVS_REFRESH=1). READ-ONLY — never writes his public face;
  # the re-stamp (--apply prints the plan) stays his lever. Lockless, fail-open. Gate off LIMEN_VVLTVS=0.
  due_voice vvltvs "$C_VVLTVS" && [ "${LIMEN_VVLTVS:-1}" = "1" ] && \
    { beat_run vvltvs-organ python3 "$LIMEN_ROOT/scripts/vvltvs-organ.py" || true; stamp vvltvs; }
  # SPECVLVM — the contributions mirror (the OSPO organ: outward to learn inward; proof, never
  # outreach). Every C_CONTRIB beats: re-render organs/contributions/MIRROR.md + the
  # logs/contributions.json signal from hub-ledger outputs (organvm/contrib LEDGER or the committed
  # cache). OFFLINE on the beat — never hits `gh api` unless LIMEN_CONTRIB_REFRESH=1. NEVER sends:
  # no comments, bumps, PRs, or posts — outbound stays his hand (the PLAN-06 planner decision).
  # Lockless, idempotent (writes only on change), fail-open. Gate off with LIMEN_CONTRIB=0.
  due_voice contrib "$C_CONTRIB" && [ "${LIMEN_CONTRIB:-1}" = "1" ] && \
    { beat_run contributions-organ python3 "$LIMEN_ROOT/scripts/contributions-organ.py" || true; stamp contrib; }
  # WALLS — regenerate the credential Wall (#320) + his-hand aggregate Wall (#330) every C_WALLS beats
  # so the published walls never drift from reality. Idempotent (writes only on change), fail-open.
  play "$C_WALLS"   && { beat_run credential-wall-sync python3 "$LIMEN_ROOT/scripts/credential-wall.py" --sync || true
                        beat_run sync-hishand-issues-wall python3 "$LIMEN_ROOT/scripts/sync-hishand-issues.py" --wall --apply || true
                        stamp walls; }
  play "$C_REPORT"  && beat_run conducting-report python3 "$LIMEN_ROOT/scripts/conducting-report.py" || true   # RELAY: did the fleet burn its full force? (once/day push — so you never have to ask)
  play "$C_WEB"     && bash "$LIMEN_ROOT/scripts/refresh-web.sh" >>"$LIMEN_ROOT/logs/refresh-web.log" 2>&1 || true  # NO pipe: refresh-web backgrounds the http.server, which can inherit a pipe's write-end and block `tail` on EOF forever → wedged the whole daemon before the first beat (2026-06-23). Redirect to a log instead.   # web auto-refresh (best-effort; money.html is primary)
  # QUICKEN — a session has a lifecycle that ends in COMPLETION; a sitting (no-movement) FleetView
  # session is stalled work, not a thing to file away. --apply records the lifecycle + deduped
  # residue every beat (read-only on sessions, no spend). Breathing — headless `claude --resume` to
  # finish a stalled purpose — is a token spend, so it is gated OFF behind LIMEN_QUICKEN_BREATHE=1
  # (his knob); deploy alone never auto-fires resumes. Bounded + fail-open — never gates the beat.
  if play "$C_QUICKEN"; then
    python3 "$LIMEN_ROOT/scripts/quicken.py" --apply 2>&1 | tail -2 || true
    [ "${LIMEN_QUICKEN_BREATHE:-0}" = "1" ] && \
      python3 "$LIMEN_ROOT/scripts/quicken.py" --breathe all 2>&1 | tail -3 || true
  fi
  # POSITIONING — keep the inbound-magnet surfaces fresh as seeds/repos drift: the form/operation
  # buyer pages + the two-door front door + the discoverability recommendations. No --fetch (no
  # network, can't time out on a stuck API); writes ONLY the public docs/positioning artifacts, and
  # the no-price guard refuses any page that leaks a currency token. Gated OFF behind LIMEN_POSITIONING=1
  # (his knob) so the surfaces auto-refresh only once he arms it — generation alone never publishes.
  # Runs just before CAPTURE so a refreshed surface is committed+pushed the same beat. Bounded + fail-open.
  if play "$C_POSITIONING" && [ "${LIMEN_POSITIONING:-0}" = "1" ]; then
    beat_run generate-positioning timeout "${LIMEN_POSITIONING_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-positioning.py" --apply || true
    beat_run generate-positioning-frontdoor timeout "${LIMEN_POSITIONING_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-positioning.py" --frontdoor --apply || true
    beat_run generate-positioning-discoverability timeout "${LIMEN_POSITIONING_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-positioning.py" --discoverability --apply || true
    stamp positioning
  fi
  # CAPTURE — get every workspace repo OFF disk into the canonical universal context (commit+push,
  # additive only). Implements the old backup voice; falls back to a legacy backup.sh if present.
  if play "$C_BACKUP"; then
    if [ -x "$LIMEN_ROOT/scripts/capture.sh" ]; then bash "$LIMEN_ROOT/scripts/capture.sh" 2>&1 | tail -3 || true
    elif [ -x "$LIMEN_ROOT/scripts/backup.sh" ]; then bash "$LIMEN_ROOT/scripts/backup.sh" 2>&1 | tail -2 || true; fi
    # LIBRARY PRESERVE — process ~/Library toward ideal form WITHOUT his hand: preserve the
    # irreplaceable sliver to Archive4T (copy→verify, Backblaze-offsite), census regenerable
    # caches, and propose reversible iCloud local-cache levers. Physical cache removal is separate
    # acceptance-gated work; preservation fails open if Archive4T is unmounted.
    LIMEN_LIB_APPLY="${LIMEN_LIB_APPLY:-1}" python3 "$LIMEN_ROOT/scripts/library-preserve.py" 2>&1 | tail -4 || true
    stamp backup
  fi
  # FEED his WORDS — atomize his FULL multi-provider transcript corpus (Claude Code,
  # codex, opencode, + gemini/chatgpt once re-hydrated) into the SINGLE session-meta
  # manifest+atoms, BEFORE converge, so the conductor holds his ENTIRE prompt corpus
  # across every agent (the structural answer to "I am not repeating myself again").
  # Canonical producer = session-meta's ingest/refresh-atoms.sh: it DERIVES providers at
  # run time (a source dir is walked only if present, so new providers auto-join) and
  # routes opencode through the atomize DB-extractor. --merge preserves the offloaded
  # historical index; redaction is enforced at ingest. Until refresh-atoms.sh has synced
  # into the session-meta tree it falls back to the legacy single-source command, so the
  # cutover is zero-gap. Default-ON (LIMEN_CORPUS_FEED=1; set 0 to roll back). Content-
  # addressed + idempotent → cheap re-run. The WHOLE feed is timeout-bounded so it can
  # NEVER wedge the beat (the prior wedge bug); the multi-provider rescan is heavier than
  # the old one-provider run, hence the larger default budget.
  if play "$C_CORPUS_FEED" && [ "${LIMEN_CORPUS_FEED:-1}" = "1" ]; then
    timeout "${LIMEN_CORPUS_FEED_OUTER_TIMEOUT:-900}" python3 "$LIMEN_ROOT/scripts/corpus-feed.py" 2>&1 | tail -6 || true
    stamp corpus_feed
  fi
  # CONVERGE his WORDS — distill the knowledge base toward ONE. Gated OFF by default
  # (LIMEN_CORPUS_CONVERGE=1); the script self-selects live synthesis (LIMEN_CORPUS_CONVERGE_LIVE=1)
  # + graph shots (LIMEN_CORPUS_GRAPH=1). Bounded + fail-open — never gates the beat.
  play "$C_CORPUS"  && [ "${LIMEN_CORPUS_CONVERGE:-0}" = "1" ] && \
    { python3 "$LIMEN_ROOT/scripts/corpus-converge.py" --apply 2>&1 | tail -3 || true; stamp corpus; }
  # ATOMIZE his personal MEDIA — strand D slice 1: docs (from the durable Archive4T copy) → first-class
  # Shot atoms in the SAME converge engine, so his media remixes with his words. Gated OFF by default
  # (LIMEN_MEDIA_ATOMIZE=1); bounded + fail-open; READ-ONLY on sources (never deletes/evicts in slice 1).
  play "$C_CORPUS"  && [ "${LIMEN_MEDIA_ATOMIZE:-0}" = "1" ] && \
    python3 "$LIMEN_ROOT/scripts/media-atomize.py" --apply 2>&1 | tail -3 || true
  # NOMENCLATOR — hold the roll of names (INDEX·NOMINVM) to the canon. --apply records liveness for
  # organ-health. Gated OFF by default (LIMEN_NOMENCLATOR=1) so estate-wide enforcement is your knob;
  # the CI gate already protects the canon on every PR. Bounded + fail-open — never gates the beat.
  play "$C_NOMENCLATOR"  && [ "${LIMEN_NOMENCLATOR:-0}" = "1" ] && \
    python3 "$LIMEN_ROOT/scripts/nomenclator.py" --apply 2>&1 | tail -2 || true

  # AVTOPOIESIS — does each door (heartbeat beat) actually live in all three tenses (past/present/
  # future)? Reports distance-from-ideal; discovers its door-list from THIS loop and includes itself
  # (operational closure). Gated OFF by default (LIMEN_AVTOPOIESIS=1 your knob); never gates the beat.
  play "$C_AVTOPOIESIS"  && [ "${LIMEN_AVTOPOIESIS:-0}" = "1" ] && \
    python3 "$LIMEN_ROOT/scripts/avtopoiesis.py" 2>&1 | tail -3 || true

  # EVOCATOR — the SVMMONER: keep every canonical truth (spec/evocator/canon.yaml) present in every
  # channel a found truth must live in — FLAME (so every beat holds it — the reach the memory dir and
  # corpus never had), the knowledge-corpus collection (so it converges into THE ONE), and a read-only
  # verify of the memory dir (per-session channel) — and self-heal drift. "find" = build this portal:
  # register one truth, it lands everywhere, forever. Idempotent (writes only on change → NO git churn),
  # no network, no tokens, can't time out. Default-ON (LIMEN_EVOCATOR=1; set 0 to roll back) — a portal
  # that doesn't run isn't a portal. Bounded + fail-open — never gates the beat.
  if due_voice evocator "$C_EVOCATOR" && [ "${LIMEN_EVOCATOR:-1}" = "1" ]; then
    python3 "$LIMEN_ROOT/scripts/evocator.py" --apply 2>&1 | tail -2 || true
    stamp evocator
  fi
  # HANDOFF — final read after this beat's board, usage, reconciliation, and provider mutations.
  # metabolize.sh has its own caller, but the live heartbeat never invokes metabolize.
  beat_run handoff-relay python3 "$LIMEN_ROOT/scripts/handoff-relay.py" || true
  # adaptive tempo: tighten to MIN whenever work is flowing OR the OPEN QUEUE is non-empty (so a
  # beat that produced no PR this cycle — all no-op / still-running — doesn't back off to 30min
  # while tasks wait); exponential backoff to MAX only when genuinely idle (empty queue, no PR).
  open_n=$(python3 -c "import sys;sys.path.insert(0,'$LIMEN_ROOT/cli/src');from pathlib import Path;from limen.io import load_limen_file;print(sum(1 for t in load_limen_file(Path('$LIMEN_ROOT/tasks.yaml')).tasks if t.status=='open'))" 2>/dev/null || echo 0)
  if [ "$worked" = 1 ] || [ "${open_n:-0}" -gt 0 ]; then beat="$MIN"; echo "── tempo: work pending (open=${open_n}) → ${beat}s ──"
  else beat=$(( beat*2 > MAX ? MAX : beat*2 )); echo "── tempo: idle (queue empty) → ${beat}s ──"; fi
  sleep "$beat"
done
