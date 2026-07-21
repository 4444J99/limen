#!/usr/bin/env bash
# heartbeat-loop.sh — the conductor as a CONTINUOUS, POLYRHYTHMIC daemon.
#
# One base tempo (the loop), multiple voices each subdividing it at its own cadence —
# like a drum kit over one BPM. Replaces the fixed 3h StartInterval (one instrument,
# one note). Tempo is ADAPTIVE: tighten when work flows, back off when idle. Total
# output is bounded by per-day budgets AND by real token/rate limits (the dispatcher
# cools a lane on its actual rate-limit signal, not a guessed count). flock in each
# step prevents overlap; near-zero cost while idle; resumes instantly on wake (run
# under a launchd KeepAlive daemon, NOT a StartInterval timer).
#
#   VOICE          cadence (beats)   what plays
#   dispatch       every 1 (kick)    use idle capacity across all 6 lanes
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

# HARD DISPATCH CEILING — a shell-level backstop so ONE hung agent run can never freeze the whole
# beat. The synchronous beat waits for the slowest lane; the per-lane Python timeout (LIMEN_LANE_TIMEOUT,
# enforced in dispatch.py via _run_capture) is SUPPOSED to bound each run, but a 2026-06-23 incident saw
# an `opencode run` blow ~3× past it (87min vs the 30min cap) and dark the daemon for ~91min — no tick,
# the whole organism frozen, recovered only by luck when the agent finally died. A SIGKILL ceiling around
# the entire dispatch GUARANTEES the beat is bounded regardless of any Python-timeout hole. It is
# wedge-SAFE: dispatch.py's _run_capture pipes each agent's stdout into its OWN pipe (never this
# command-substitution pipe), so SIGKILLing dispatch closes the substitution pipe cleanly — no tail-EOF
# hang ([[no-never-happens-again]]). Ceiling DERIVED from the per-lane cap + slack, never pinned.
DISPATCH_TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
: "${LIMEN_LANE_TIMEOUT:=1800}"
: "${LIMEN_DISPATCH_CEILING:=$(( LIMEN_LANE_TIMEOUT + ${LIMEN_DISPATCH_CEILING_SLACK:-600} ))}"
export LIMEN_LANE_TIMEOUT LIMEN_DISPATCH_CEILING
[ -n "$DISPATCH_TIMEOUT_BIN" ] || echo "$(date '+%F %T') WARN: no timeout/gtimeout on PATH — dispatch runs" \
  "UNBOUNDED (fail-open; a hung lane could freeze the beat). brew install coreutils to restore the ceiling." \
  >> "$LIMEN_ROOT/logs/heartbeat.out.log" 2>/dev/null || true
dispatch_bounded() {  # dispatch_bounded <cmd...> — run dispatch under the SIGKILL ceiling (fail-open if no timeout bin)
  if [ -n "$DISPATCH_TIMEOUT_BIN" ]; then
    "$DISPATCH_TIMEOUT_BIN" -s KILL "$LIMEN_DISPATCH_CEILING" "$@"
  else
    "$@"
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

LANES="${LIMEN_LANES:-codex,opencode,agy,claude,gemini}"   # local-lane preference/display; not the fleet boundary
DISPATCH_LANES="${LIMEN_DISPATCH_LANES:-auto}"
# per-lane tasks PER BEAT kept low so no single lane hogs a beat — lanes rotate fast
# (the safe throughput fix; real braking is the rate-limit detector in dispatch.py).
LOCAL_LIMIT="${LIMEN_LOCAL_LIMIT:-3}"; JULES_LIMIT="${LIMEN_JULES_LIMIT:-100}"
case "$LOCAL_LIMIT" in
  ''|*[!0-9]*) LOCAL_LIMIT=3 ;;
esac
if [ "$LOCAL_LIMIT" -gt 3 ] && [ "${LIMEN_ALLOW_HIGH_LOCAL_LIMIT:-0}" != "1" ]; then
  echo "  local limit capped: requested $LOCAL_LIMIT -> 3 (set LIMEN_ALLOW_HIGH_LOCAL_LIMIT=1 to override)"
  LOCAL_LIMIT=3
fi

# Local TOTAL concurrency derives from the live host. The per-lane bound above prevents one lane
# from monopolizing it, VITALS applies memory backpressure, and remote lanes consume neither value.
_host_local_ceiling="$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 1)"
case "$_host_local_ceiling" in
  ''|*[!0-9]*|0) _host_local_ceiling=1 ;;
esac
HOST_LOCAL_CEILING="${LIMEN_ASYNC_MAX:-$_host_local_ceiling}"
case "$HOST_LOCAL_CEILING" in
  ''|*[!0-9]*|0) HOST_LOCAL_CEILING="$_host_local_ceiling" ;;
esac

# base tempo (adaptive) + voice subdivisions (configurable)
MIN="${LIMEN_LOOP_MIN:-120}"; MAX="${LIMEN_LOOP_MAX:-1800}"; beat="$MIN"
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
healthy_lanes() {
  python3 - "$1" <<'PY'
import sys
from limen.dispatch import _down_lanes

down = _down_lanes()
seen = []
for lane in sys.argv[1].split(","):
    lane = lane.strip()
    if lane and lane not in down and lane not in seen:
        seen.append(lane)
print(",".join(seen))
PY
}
dispatch_lanes() {
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
  rmdir "$LOCKD" 2>/dev/null || true
  if [ "$(cat "$DAEMON_LOCK" 2>/dev/null)" = "$$" ]; then
    rm -f "$DAEMON_LOCK" "$LIMEN_ROOT/logs/heartbeat-loop.pid" 2>/dev/null
    rmdir "$DAEMON_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "═══ heartbeat-loop start $(date '+%F %T') tempo=${MIN}-${MAX}s lanes=$LANES dispatch_lanes=$DISPATCH_LANES ═══"
# This freshly-started loop IS running the current body, so any prior "loop body changed —
# kickstart pending" marker is now satisfied. sync-release only ever SETS this flag (on a
# loop-body ff) and nothing else clears it, so without this it stays set forever and the
# "kickstart needed" signal goes permanently stale. Clearing it on startup keeps the signal true.
rm -f "$LIMEN_ROOT/logs/.loop-update-pending" 2>/dev/null || true
# ensure the web dashboard is served from the start
bash "$LIMEN_ROOT/scripts/refresh-web.sh" >>"$LIMEN_ROOT/logs/refresh-web.log" 2>&1 || true  # NO pipe: refresh-web backgrounds the http.server, which can inherit a pipe's write-end and block `tail` on EOF forever → wedged the whole daemon before the first beat (2026-06-23). Redirect to a log instead.
while true; do
  # OWNERSHIP BACKSTOP — if any acquisition race let a second loop through, the one whose
  # pid is NOT in the lockfile exits here. Converges to exactly one daemon within a beat.
  if [ "$(cat "$DAEMON_LOCK" 2>/dev/null)" != "$$" ]; then
    echo "no longer singleton owner (pid in lock != $$) — exiting"; exit 0
  fi
  c=$(( c + 1 ))
  worked=0
  VITALS_PRESSURE=0
  VITALS_THROTTLE=0
  echo "──── beat $c $(date '+%F %T') ────"
  MODE="$(python3 "$LIMEN_ROOT/scripts/autonomy-governor.py" mode 2>/dev/null || echo paused)"
  if [ "$MODE" = "paused" ]; then
    # Stay the singleton owner. Exiting here made launchd KeepAlive respawn a fresh
    # process every minute, so a pause paradoxically created repeated startup probes.
    # The receipt is byte-stable: the first paused beat writes it and later beats do
    # no filesystem work until the governor resumes.
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
  if [ "${LIMEN_NET_PREFLIGHT:-1}" = "1" ] && \
     ! python3 -c "import socket; socket.create_connection(('${LIMEN_NET_HOST:-api.github.com}', 443), timeout=${LIMEN_NET_TIMEOUT:-3}).close()" 2>/dev/null; then
    echo "  offline — ${LIMEN_NET_HOST:-api.github.com} unreachable; idle beat (self-heals when network returns)"
    python3 "$LIMEN_ROOT/scripts/emit-tick.py" 2>&1 | tail -1 || true
    beat="$MAX"
    echo "── tempo: offline → ${beat}s ──"
    sleep "$beat"
    continue
  fi
  # VITALS GATE (VIGILIA build #1) — memory pressure is a NORMAL condition, not a crash.
  # The autonomic CFO, graduated: at >= warn dispatch CONTINUES at a reduced cap (a 16 GB host
  # lives at warn under normal load — a full idle beat here starved the fleet for a night,
  # 2026-07-08: 273 skipped beats with budget unused). At critical, local admission sheds while
  # off-box lanes continue; VITALS also sheds ollama. Fail-OPEN: any sensor fault → 'ok'.
  if [ "${LIMEN_VIGILIA:-1}" = "1" ]; then
    _vitals="$(python3 -m limen.vigilia vitals-gate 2>/dev/null || echo ok)"
    if [ "$_vitals" = "shed" ]; then
      echo "  vitals: memory pressure ≥ critical — shed local work; off-box lanes remain eligible"
      VITALS_PRESSURE=1
    elif [ "$_vitals" = "throttle" ]; then
      echo "  vitals: memory pressure ≥ warn — dispatch throttled (cap ÷ ${LIMEN_VITALS_THROTTLE_DIVISOR:-2})"
      VITALS_THROTTLE=1
    fi
  fi
  EFFECTIVE_LANES="$LANES"
  EFFECTIVE_DISPATCH_LANES="$DISPATCH_LANES"
  if [ "$VITALS_PRESSURE" = "1" ]; then
    echo "── vitals-pressure: local admission shed; remote dispatch remains live ──"
  fi
    # SUBSTRATE SELF-HEAL — re-converge this checkout to the release (origin/main) before doing
    # work, so the beat always runs the latest code (push = deploy). ff-only, data-preserving,
    # fail-open; never exits/re-execs the daemon. Closes the loop: root → leaf → back to root.
    play "$C_SYNC" && bash "$LIMEN_ROOT/scripts/sync-release.sh" 2>&1 | tail -2 || true
    # BOARD-INTEGRITY self-heal — if the SSOT queue is unloadable or collapsed (a clobber that
    # slipped past the save-time guard, or external corruption), restore it from HEAD BEFORE the
    # body tries to load it, so a dead board self-recovers instead of idling the fleet for hours
    # (the 2026-06-26 halt). Idempotent: a healthy board is a fast no-op, no network. See
    # heal-board.py + the limen.io collapse-guard — "fix the handoff so it ain't broken".
    python3 "$LIMEN_ROOT/scripts/heal-board.py" 2>&1 | tail -1 || true
    # SESSION-END DRAIN — Claude's hook writes only a constant-time breadcrumb.
    # Slow handoff, watcher, claim, model-audit, and lifecycle consumers resume
    # here with finite retries and per-session receipts.
    SESSION_END_SOURCE="${LIMEN_SESSION_END_BREADCRUMBS:-${XDG_STATE_HOME:-$HOME/.local/state}/limen/session-end-breadcrumbs.jsonl}"
    timeout "${LIMEN_SESSION_END_CONSUMER_TIMEOUT:-90}" \
      python3 "$LIMEN_ROOT/scripts/consume-session-end-breadcrumbs.py" \
        --source "$SESSION_END_SOURCE" \
        --max-sessions "${LIMEN_SESSION_END_CONSUMER_BATCH:-8}" \
        --runway-seconds "${LIMEN_SESSION_END_CONSUMER_RUNWAY:-60}" 2>&1 | tail -1 || true
    # TABVLARIVS RELAY — submit the lock-free ticket inbox to the authenticated remote conduct
    # keeper. Archive only tickets with canonical projection receipts; broker outages leave the
    # unacknowledged suffix pending. The local tasks.yaml is read-only cache evidence, never a
    # lifecycle writer. Idempotent: an empty inbox is an instant no-op.
    [ "${LIMEN_TABVLARIVS:-1}" = "1" ] && python3 "$LIMEN_ROOT/scripts/tabularius-organ.py" 2>&1 | tail -1 || true
    # ENACTMENT — surface any declared-ON fleet flag that is dark/stale in THIS running beat (memory:
    # enacted-not-declared). THE LIVE-LOOP HOME: metabolize.sh has the same advisory but the daemon
    # never runs metabolize (only saturate.sh does — route.py:208), so this line is what makes the
    # check actually fire on the fleet. Spawned fresh each beat like the organs above → deploys on the
    # next sync-release ff; but adding THIS line is a loop-body edit, so it needs a kickstart to load.
    # Fail-open, log-only (never chat), like creds/link health in metabolize §0d.
    [ "${LIMEN_ENACTMENT_CHECK:-1}" = "1" ] && python3 "$LIMEN_ROOT/scripts/enactment-audit.py" --check 2>&1 | tail -1 || true
    python3 "$LIMEN_ROOT/scripts/usage-telemetry.py" 2>&1 | tail -1 || true   # refresh lane health BEFORE route/dispatch
    python3 "$LIMEN_ROOT/scripts/codex-token-accounting.py" \
      --since-hours "${LIMEN_CODEX_TOKEN_REPORT_HOURS:-6}" \
      --limit-sessions "${LIMEN_CODEX_TOKEN_REPORT_LIMIT:-25}" \
      --output "$LIMEN_ROOT/logs/codex-token-report.json" 2>&1 | tail -1 || true   # visible session spend report
    python3 "$LIMEN_ROOT/scripts/claude-usage.py" 2>&1 | tail -1 || true   # claude usage: multi-avenue cascade → logs/claude-usage.json
    EFFECTIVE_LANES="$(healthy_lanes "$LANES")"
    if [ "$EFFECTIVE_LANES" != "$LANES" ]; then
      echo "  lanes: ${EFFECTIVE_LANES:-none} active from requested [$LANES]"
    fi
    EFFECTIVE_DISPATCH_LANES="$(dispatch_lanes "$DISPATCH_LANES")"
    echo "  dispatch lanes: ${EFFECTIVE_DISPATCH_LANES:-none} from selector [$DISPATCH_LANES]"

    if [ "$MODE" != "dispatch" ]; then
      echo "autonomy mode=$MODE — telemetry/status only; queue mutation and dispatch skipped"
      # HANDOFF — even an observe-only beat refreshes the warm-resume packet.  The heartbeat does
      # not invoke metabolize.sh, so this direct seam is required to keep continuity truthful.
      python3 "$LIMEN_ROOT/scripts/handoff-relay.py" 2>&1 | tail -1 || true
      python3 "$LIMEN_ROOT/scripts/emit-tick.py" 2>&1 | tail -1 || true
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
                                       python3 -m limen release-stale --agent jules --hours 24 --apply 2>&1 | tail -1 || true; }
      due_voice heal "$C_HEAL"     && python3 "$LIMEN_ROOT/scripts/recover.py" --apply 2>&1 | tail -1 || true   # HEAL

      # Release the broad heartbeat mutex before producer/planner voices. Those scripts either submit
      # Tabularius tickets or acquire their own short queue_lock, so a slow feed/rebalance pass cannot
      # starve supervisors and high-value async claims for minutes.
      unset LIMEN_QUEUE_LOCK_HELD
      rm -f "$LOCKD/pid" "$LOCKD/created_at" 2>/dev/null || true
      rmdir "$LOCKD" 2>/dev/null || true
      locked=0

      play "$C_FEED"               && { LIMEN_TICKETS_PRODUCE=1 python3 "$LIMEN_ROOT/scripts/mine-backlog.py" --limit "${LIMEN_MINE_LIMIT:-25}" --apply 2>&1 | tail -1 || true  # EXPLORE
                                       [ "${LIMEN_REVENUE_BACKLOG:-1}" = "1" ] && LIMEN_TICKETS_PRODUCE=1 timeout "${LIMEN_REVENUE_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-revenue-backlog.py" --apply 2>&1 | tail -1 || true  # REVENUE FIRST: ladder→tasks so win-class capacity builds products, not busywork (default-ON; floor-gated)
                                       [ "${LIMEN_ORGAN_BACKLOG:-1}" = "1" ] && LIMEN_TICKETS_PRODUCE=1 timeout "${LIMEN_ORGAN_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-organ-backlog.py" --apply 2>&1 | tail -1 || true  # ORGANS (VLTIMA): organ-ladder->tasks so idle capacity builds the institutional pillars (legal/financial/education/...), not busywork (default-ON; floor-gated)
                                       LIMEN_TICKETS_PRODUCE=1 timeout "${LIMEN_GENERATE_BACKLOG_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-backlog.py" --apply 2>&1 | tail -1 || true  # SELF-FEED: build-out levers on the ranked tier
                                       [ "${LIMEN_STUDIUM:-0}" = "1" ] && timeout "${LIMEN_STUDIUM_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/ingest-backlog.py" --apply 2>&1 | tail -1 || true  # STUDIUM: re-emit the staged canon-breadth content tasks each beat so they SURVIVE the prune (a one-shot hand-apply gets clobbered; idempotent, gated, lockless)
                                       python3 "$LIMEN_ROOT/scripts/discover-value.py" --apply 2>&1 | tail -1 || true; }  # DISCOVER: no repo stays dark — surface latent value, burn the tank
      play "$C_BALANCE"            && { python3 "$LIMEN_ROOT/scripts/route.py" --apply 2>&1 | tail -1 || true   # PLAN
                                       if [ -n "$EFFECTIVE_LANES" ]; then
                                         python3 "$LIMEN_ROOT/scripts/rebalance.py" --lanes "$EFFECTIVE_LANES" --apply 2>&1 | tail -1 || true
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
        reclaim_args=()
        [ "${LIMEN_RECLAIM_APPLY:-1}" = "1" ] && reclaim_args+=(--apply)
        # The cheap generated-only pass (just-finished lanes) ALWAYS runs — it closes this beat's own
        # worktree debt at negligible cost. The FULL estate census (git status/cherry across every
        # worktree — the git storm over ~71 roots) is deferred while VITALS is SHEDDING (memory/swap
        # ≥ critical), so the beat never thrashes an already-starved host to relieve worktree debt.
        # It resumes the next unpressured beat. Under mere throttle/warn it still runs (LIMEN_RECLAIM_TIMEOUT-bounded).
        PYTHONPATH="$PYTHONPATH" timeout "${LIMEN_RECLAIM_GENERATED_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/reclaim-worktrees.py" --generated-only "${reclaim_args[@]}" 2>&1 | tail -4 || true
        if [ "$VITALS_PRESSURE" != "1" ]; then
          PYTHONPATH="$PYTHONPATH" timeout "${LIMEN_RECLAIM_TIMEOUT:-300}" python3 "$LIMEN_ROOT/scripts/reclaim-worktrees.py" "${reclaim_args[@]}" 2>&1 | tail -4 || true
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

      # BUILD — dispatch every beat. Default = SYNC parallel (reserve→run→commit, beat waits for the
      # slowest agent). Opt in to ASYNC (LIMEN_DISPATCH_ASYNC=1): fire detached workers + harvest
      # finished runs → fast beats, a slow agent never gates the beat (the throughput 10x). Async is
      # OFF by default; flip the env + restart between beats to enable. See dispatch-async.py.
      _dt0=$SECONDS
      _async_max="$HOST_LOCAL_CEILING"
      _sync_workers="${LIMEN_WORKERS:-$HOST_LOCAL_CEILING}"
      case "$_sync_workers" in
        ''|*[!0-9]*|0) _sync_workers="$HOST_LOCAL_CEILING" ;;
      esac
      if [ "$VITALS_THROTTLE" = "1" ]; then
        _async_max=$(( _async_max / ${LIMEN_VITALS_THROTTLE_DIVISOR:-2} ))
        _sync_workers=$(( _sync_workers / ${LIMEN_VITALS_THROTTLE_DIVISOR:-2} ))
        [ "$_async_max" -lt 1 ] && _async_max=1
        [ "$_sync_workers" -lt 1 ] && _sync_workers=1
      fi
      # At critical pressure the Python admission snapshot blocks every census-local candidate;
      # the dispatcher still runs so Jules/GitHub Actions/other off-box lanes keep producing.
      if [ "${LIMEN_DISPATCH_ASYNC:-0}" = "1" ]; then
        out="$(dispatch_bounded python3 "$LIMEN_ROOT/scripts/dispatch-async.py" --lanes "$DISPATCH_LANES" \
                --per-lane "$LOCAL_LIMIT" --max "$_async_max" 2>&1)"; _drc=$?
      else
        out="$(dispatch_bounded python3 "$LIMEN_ROOT/scripts/dispatch-parallel.py" --lanes "$DISPATCH_LANES" \
                --per-lane "$LOCAL_LIMIT" --workers "$_sync_workers" 2>&1)"; _drc=$?
      fi
      # timeout(1) exits 124 (TERM) or 128+9=137 (our -s KILL) when the ceiling fires → a lane run
      # blew past its per-lane bound and dispatch.py's Python timeout failed to kill it. SURFACE it
      # loudly so the regression is visible in the beat log (and to the watchdog) instead of a silent
      # ~90min dark window; the beat is already UNBLOCKED (dispatch was SIGKILLed). ([[no-never-happens-again]])
      if [ "$_drc" = 137 ] || [ "$_drc" = 124 ]; then
        echo "── ⚠ DISPATCH CEILING HIT after ${LIMEN_DISPATCH_CEILING}s (beat dispatch took $((SECONDS-_dt0))s) — a lane run exceeded its bound and was SIGKILLed; beat unblocked. Per-lane timeout failed to fire → investigate dispatch.py _run_capture. ──"
      fi
      echo "$out" | tail -8
      echo "$out" | grep -qE "→ PR|dispatched/PR|  dispatched:|launched [1-9][0-9]*" && worked=1
      stamp dispatch
    else
      echo "── queue lock held by a supervisor — skipping mutation this beat ──"
    fi

  # RECONCILE — outside the queue-lock (heal-dispatch self-acquires it, so it must NOT run
  # under the daemon's lock or it would deadlock). Verify claimed dispatches vs real PR state,
  # then flip phantom → done/open so the funnel self-clears and the open pool refills each cycle.
  due_voice heal "$C_HEAL" && { python3 "$LIMEN_ROOT/scripts/verify-dispatch.py" 2>&1 | tail -1 || true
                      python3 "$LIMEN_ROOT/scripts/heal-dispatch.py" --apply 2>&1 | tail -1 || true
                      # LEDGER — weigh the RETURN on every newly-resolved task (the credit side), then
                      # roll up the value verdict (which lane earns its keep / what was sunk money).
                      python3 "$LIMEN_ROOT/scripts/score-dispatch.py" 2>&1 | tail -1 || true
                      python3 "$LIMEN_ROOT/scripts/ledger.py" 2>&1 | tail -1 || true
                      # SELF-HEAL — the repair FACTORY (complements heal-dispatch's phantom-reconcile): classify the
                      # fleet's REFUSED PRs (CI-red / conflicting) and emit HEAL-cifix / HEAL-rebase tasks so the
                      # router+dispatcher fix them and merge-drain then LANDS them. merge-drain is the bouncer; THIS is
                      # the factory. Silent since 2026-06-30 — the machine worked, but no beat ever turned the crank, so
                      # DIRTY/BLOCKED PRs piled up read as "blockers" instead of becoming work. Bounded rotating --scan
                      # window + already-queued dedup = idempotent; self-acquires the queue-lock (safe outside the daemon
                      # lock, like heal-dispatch) and skips cleanly when the daemon holds it; network → timeout-wrapped,
                      # fail-open. Redirects existing budgeted dispatch from receipt-churn to real PR repair; off with
                      # LIMEN_SELF_HEAL=0.
                      [ "${LIMEN_SELF_HEAL:-1}" = "1" ] && timeout "${LIMEN_SELF_HEAL_TIMEOUT:-150}" python3 "$LIMEN_ROOT/scripts/self-heal.py" --scan "${LIMEN_SELF_HEAL_SCAN:-30}" 2>&1 | tail -1 || true; }
  due_voice heal "$C_HEAL"    && stamp heal
  # Scheduled registry sensors — cadence, timeout, conditional argv, voice id, and gate all come
  # from sensors.yaml. The runner knows no sensor names, so a rename or a newly-declared scheduled
  # sensor needs no shell edit. Default-ON: the fallback matches the parameter-panel default and
  # metabolize.sh (the :-0/:-1/"1" three-way drift kept this lane dark — github-estate-reconcile and
  # the 0g4 liveness rung never executed live). Released by the 2026-07-13 canary receipts (dry +
  # one live-parity pass; PR #1013 body). Loop-body edit:
  # takes effect only after `launchctl kickstart -k gui/$(id -u)/com.limen.heartbeat`.
  if [ "${LIMEN_BEAT_DERIVE:-1}" = "1" ]; then
    python3 "$LIMEN_ROOT/scripts/beat-sensors.py" --run --source heartbeat --scheduled-only \
      --beat "$c" --loop-max "$MAX" --voice-dir "$VOICED" || true
  fi
  # DISK PRESSURE — when the data volume is past high-water, run hygiene (clone-maintenance:
  # capture→reap→node_modules) EVERY beat, not just every C_HYGIENE, until it drains back under
  # target. Reclaim intensity tracks real fullness instead of a fixed clock (the "creeps back to
  # full" fix). Cheap df probe; off with LIMEN_DISK_PRESSURE_ESCALATE=0.
  HYG_CAD="$C_HYGIENE"
  if [ "${LIMEN_DISK_PRESSURE_ESCALATE:-1}" = "1" ]; then
    # ABSOLUTE free (GiB), not df% — df counts ~100GB of purgeable-but-reclaimable APFS space as
    # "used", so a 95%-by-percent disk with ~120GB effectively free would falsely ramp hygiene to
    # EVERY beat and slow the whole beat (clone-maintenance runs each tick). Ramp only when raw free
    # genuinely drops below the floor. ([[meter-lie-and-dead-daemon-incident]])
    _dfree="$(df -Pk "${LIMEN_WORKDIR:-$HOME/Workspace}" 2>/dev/null | awk 'NR==2 {print int($4/1048576)}')"
    # Memory-shed OVERRIDES the disk-pressure ramp: never ramp the clone-maintenance git storm to
    # EVERY beat to relieve DISK while MEMORY/swap is critical — that trades a slow disk for a
    # thrashing host. Under shed, hold the normal cadence (and the git voices below skip anyway).
    [ -n "$_dfree" ] && [ "$_dfree" -le "${LIMEN_DISK_FREE_FLOOR_GIB:-15}" ] 2>/dev/null \
      && [ "$VITALS_PRESSURE" != "1" ] && HYG_CAD=1
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
  # + idle age; inert above the free-floor. Disarm --apply with LIMEN_REAP_CLONES_APPLY=0.
  REAP_CLONES_ARG=""; [ "${LIMEN_REAP_CLONES_APPLY:-1}" = "1" ] && REAP_CLONES_ARG="--apply"
  [ "$VITALS_PRESSURE" != "1" ] && due_voice hygiene "$HYG_CAD" && timeout "${LIMEN_REAP_CLONES_TIMEOUT:-300}" python3 "$LIMEN_ROOT/scripts/reap-clones.py" $REAP_CLONES_ARG 2>&1 | tail -3 || true
  due_voice hygiene "$HYG_CAD" && bash "$LIMEN_ROOT/scripts/heal-claude-update-marker.sh" 2>&1 | tail -1 || true
  # heal-claude-lsregister.sh / heal-hook-drift.sh / heal-claude-cask.sh are NO LONGER hand-wired here:
  # they run as the registry-derived `dialogs-silenced` sensor (institutio/governance/sensors.yaml 0g8b)
  # on the scheduled heartbeat derive lane above (beat-sensors.py --run --source heartbeat
  # --scheduled-only, cadence LIMEN_BEAT_DIALOGS=8 == this hygiene cadence), then verified by
  # dialogs-silenced.sh --agent-curable-only. Hand-wiring them too would double-run; adding a new dialog
  # effector is now one sensors.yaml step, not a shell line here.
  due_voice hygiene "$HYG_CAD" && stamp hygiene
  python3 "$LIMEN_ROOT/scripts/emit-tick.py" 2>&1 | tail -1 || true   # tick voice — every beat
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
  python3 "$LIMEN_ROOT/scripts/organ-health.py" 2>&1 | tail -1 || true   # PROPRIOCEPTION — EVERY beat: the health face must never lag the organs it watches. route stamps on C_BALANCE=2, feed on C_FEED=3, but C_WEB=4, so on the old web cadence the face showed stale "unknown" for rungs that were already green (and a restart-to-beat-2 froze it until beat 4). Cheapest renderer: read-only, no network, can't time out — belongs with the tick.
  [ "${LIMEN_VIGILIA:-1}" = "1" ] && { python3 -m limen.vigilia beat 2>&1 | tail -1 || true; stamp vigilia; }   # VIGILIA autonomic executive — record vitals/continuity/integrity to the seat (read-only, fail-open)
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/usage-telemetry.py" 2>&1 | tail -1 || true   # real per-vendor usage
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/codex-token-accounting.py" --since-hours "${LIMEN_CODEX_TOKEN_REPORT_HOURS:-6}" --limit-sessions "${LIMEN_CODEX_TOKEN_REPORT_LIMIT:-25}" --output "$LIMEN_ROOT/logs/codex-token-report.json" 2>&1 | tail -1 || true   # per-session Codex spend report
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/claude-usage.py" 2>&1 | tail -1 || true   # claude usage: multi-avenue cascade gauge
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/money-view.py" 2>&1 | tail -1 || true   # revenue-first money view (no network, can't time out)
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/corpus-view.py" 2>&1 | tail -1 || true   # knowledge-base view: THE ONE + convergence activity (no network)
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/ingest-coverage.py" 2>&1 | tail -1 || true   # diagnostic: are we at 100% context? sources + freshness + adapter gaps (read-only over the manifest)
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/omni-view.py" 2>&1 | tail -1 || true   # THE ONE SURFACE: value verdict + board + fleet + revenue + everything, past/present/future (no network)
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/obligations-view.py" 2>&1 | tail -1 || true   # mail obligations face refresh (no network)
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/pillars-view.py" 2>&1 | tail -1 || true   # platform-of-pillars convergence map: program ladder + per-pillar live/stale status (no network)
  play "$C_MAIL"    && { bash "$LIMEN_ROOT/scripts/mail-beat.sh" 2>&1 | tail -3 || true; stamp mail; }   # COMMS: sweep inbound (flag fires/archive noise, reversible) + rebuild obligations ledger
  due_voice continuation "$C_CONTINUATION" && [ "${LIMEN_CONTINUATION:-1}" = "1" ] && \
    { if [ -n "$DISPATCH_TIMEOUT_BIN" ]; then
        "$DISPATCH_TIMEOUT_BIN" -s KILL "${LIMEN_CONTINUATION_TIMEOUT:-600}" python3 "$LIMEN_ROOT/scripts/continuation-beat.py" --apply 2>&1 | tail -6 || true
      else
        python3 "$LIMEN_ROOT/scripts/continuation-beat.py" --apply 2>&1 | tail -6 || true
      fi
      stamp continuation; }
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/notify-events.py" 2>&1 | tail -1 || true   # push: your-gate ready / ship milestones
  # CENSOR — the insights→actions institution. Records its decisions + renders censor.html EVERY
  # run so it is observable BEFORE it is autonomous; the executive only acts when armed
  # (LIMEN_CENSOR_APPLY=1). Tiers (hourly/daily/weekly) self-gate on wall-clock. Bounded + fail-open.
  play "$C_CENSOR"  && python3 "$LIMEN_ROOT/scripts/censor.py" $([ "${LIMEN_CENSOR_APPLY:-0}" = "1" ] && echo --apply) 2>&1 | tail -1 || true
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/censor-view.py" 2>&1 | tail -1 || true   # the Censor's face (no network, can't time out)
  play "$C_WEB"     && [ "${LIMEN_STUDIUM:-0}" = "1" ] && python3 "$LIMEN_ROOT/scripts/studium.py" --daily 2>&1 | tail -1 || true   # daily transmission-curriculum face (gated; advances once/day, no network, can't time out)
  play "$C_INSIGHT_CADENCE" && python3 "$LIMEN_ROOT/scripts/insight-cadence.py" --once 2>&1 | tail -1 || true  # INSIGHT-CADENCE: draft insight reports at four wall-clock cadences
  play "$C_INSIGHT_CADENCE" && python3 "$LIMEN_ROOT/scripts/insight-route.py" 2>&1 | tail -1 || true  # INSIGHT-ROUTE: latest report per tier → durable owner (levers / keeper tickets / organ residuals)
  # CENSOR-ISSUES — mirror live censor residuals → public `censor` GitHub issues (auto-open on
  # warning, auto-close when the lineage clears, human closes vetoed forever, capped per pass).
  # Observable before autonomous: dry-runs each beat until LIMEN_CENSOR_ISSUES_APPLY=1 arms it
  # (the same constitutional pattern as LIMEN_CENSOR_APPLY on the censor itself).
  play "$C_CENSOR"  && python3 "$LIMEN_ROOT/scripts/sync-censor-issues.py" $([ "${LIMEN_CENSOR_ISSUES_APPLY:-0}" = "1" ] && echo --apply) 2>&1 | tail -1 || true
  # HEALTH — the personal health office (chart digest + visit-prep + clinical-loop chase; PII stays
  # local, off-repo; lockless, read-only). Refreshes the office every C_HEALTH beats. Fail-open.
  due_voice health "$C_HEALTH"  && { python3 "$LIMEN_ROOT/scripts/health-organ.py" 2>&1 | tail -1 || true; stamp health; }
  # MAT — the daily-engine keeper (private-tree session pull + day-card pre-compose + roadblocks
  # queue; organ self-throttles to ~1 fire/day; counts-only state, PII stays off-repo). Fail-open.
  due_voice mat "$C_MAT"        && { python3 "$LIMEN_ROOT/scripts/mat-organ.py" 2>&1 | tail -1 || true; stamp mat; }
  # LIFE — the digital-life office (accounts/assets/subscriptions; PII stays local, off-repo;
  # lockless, read-only). Refreshes the life briefing + open-actions + derives the subscription
  # purge clock every C_LIFE beats. Fail-open.
  due_voice life "$C_LIFE"    && { python3 "$LIMEN_ROOT/scripts/life-organ.py" 2>&1 | tail -1 || true; stamp life; }
  # GOVERNANCE — run the cursus honorum seed validator + governance standing report every C_GOVERNANCE
  # beats. Operationalizes the governance rules (cvrsvs-honorvm) as an autonomous beat: validates
  # every seed.yaml in the estate, stamps the governance voice for proprioception. Read-only,
  # lockless, idempotent, fail-open — never gates the beat. Gate off with LIMEN_GOVERNANCE=0.
  due_voice governance "$C_GOVERNANCE" && [ "${LIMEN_GOVERNANCE:-1}" = "1" ] && \
    { python3 "$LIMEN_ROOT/scripts/governance-organ.py" 2>&1 | tail -1 || true; stamp governance; }
  # FINANCE — run the financial-office consolidator (regenerate balance-sheet, cash-flow, STATUS from
  # entity data) + assess maturity + advance organ-ladder.json as slices land. Lockless, idempotent,
  # fail-open — never gates the beat. Gate off with LIMEN_FINANCIAL=0.
  due_voice financial "$C_FINANCIAL" && [ "${LIMEN_FINANCIAL:-1}" = "1" ] && \
    { python3 "$LIMEN_ROOT/scripts/financial-organ.py" 2>&1 | tail -1 || true; stamp financial; }
  # DISCLOSE — verify the publication-policy engine (the ONE content-disposition decision) stays sound
  # every C_PUBPOLICY beats: redactor owner-scoped (never eats product emails / placeholders / 555
  # fixtures), disposition matrix + classifier intact. Read-only self-test, stamps the pubpolicy voice.
  # Idempotent, fail-open — never gates the beat. Gate off with LIMEN_PUBPOLICY=0.
  due_voice pubpolicy "$C_PUBPOLICY" && [ "${LIMEN_PUBPOLICY:-1}" = "1" ] && \
    { python3 "$LIMEN_ROOT/scripts/publication-policy.py" --verify 2>&1 | tail -1 || true; stamp pubpolicy; }
  # CVSTOS — the keeper of the host. Every C_CVSTOS beats: census the chat-app/local debt (all
  # vendors, not just Claude), measure the factory-host invariant (nothing truly on PATH/local), and
  # give the scattered reapers one liveness face. READ-ONLY (surface) — the regenerable-cache reclaim
  # (--apply) stays a human lever until he classifies what's safe to purge. Lockless, fail-open —
  # never gates the beat. Gate off with LIMEN_CVSTOS=0.
  due_voice cvstos "$C_CVSTOS" && [ "${LIMEN_CVSTOS:-1}" = "1" ] && \
    { timeout "${LIMEN_RECLAIM_TIMEOUT:-300}" python3 "$LIMEN_ROOT/scripts/cvstos-organ.py" 2>&1 | tail -1 || true; stamp cvstos; }
  # VVLTVS — the countenance (sibling of CVSTOS: CVSTOS faces the machine, VVLTVS faces the world).
  # Every C_VVLTVS beats: verify the public face reflects the live SSOT — the profile bio + portfolio
  # copies vs organvm-corpvs-testamentvm/system-metrics.json — and surface the contribution-mix radar
  # (the ~0.6% code-review tell). OFFLINE on the beat (reads the SSOT + face files + cached mix; never
  # hits `gh api` per beat unless LIMEN_VVLTVS_REFRESH=1). READ-ONLY — never writes his public face;
  # the re-stamp (--apply prints the plan) stays his lever. Lockless, fail-open. Gate off LIMEN_VVLTVS=0.
  due_voice vvltvs "$C_VVLTVS" && [ "${LIMEN_VVLTVS:-1}" = "1" ] && \
    { python3 "$LIMEN_ROOT/scripts/vvltvs-organ.py" 2>&1 | tail -1 || true; stamp vvltvs; }
  # SPECVLVM — the contributions mirror (the OSPO organ: outward to learn inward; proof, never
  # outreach). Every C_CONTRIB beats: re-render organs/contributions/MIRROR.md + the
  # logs/contributions.json signal from hub-ledger outputs (organvm/contrib LEDGER or the committed
  # cache). OFFLINE on the beat — never hits `gh api` unless LIMEN_CONTRIB_REFRESH=1. NEVER sends:
  # no comments, bumps, PRs, or posts — outbound stays his hand (the PLAN-06 planner decision).
  # Lockless, idempotent (writes only on change), fail-open. Gate off with LIMEN_CONTRIB=0.
  due_voice contrib "$C_CONTRIB" && [ "${LIMEN_CONTRIB:-1}" = "1" ] && \
    { python3 "$LIMEN_ROOT/scripts/contributions-organ.py" 2>&1 | tail -1 || true; stamp contrib; }
  # WALLS — regenerate the credential Wall (#320) + his-hand aggregate Wall (#330) every C_WALLS beats
  # so the published walls never drift from reality. Idempotent (writes only on change), fail-open.
  play "$C_WALLS"   && { python3 "$LIMEN_ROOT/scripts/credential-wall.py" --sync 2>&1 | tail -1 || true
                        python3 "$LIMEN_ROOT/scripts/sync-hishand-issues.py" --wall --apply 2>&1 | tail -1 || true
                        stamp walls; }
  play "$C_REPORT"  && python3 "$LIMEN_ROOT/scripts/conducting-report.py" 2>&1 | tail -1 || true   # RELAY: did the fleet burn its full force? (once/day push — so you never have to ask)
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
    timeout "${LIMEN_POSITIONING_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-positioning.py" --apply 2>&1 | tail -1 || true
    timeout "${LIMEN_POSITIONING_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-positioning.py" --frontdoor --apply 2>&1 | tail -1 || true
    timeout "${LIMEN_POSITIONING_TIMEOUT:-120}" python3 "$LIMEN_ROOT/scripts/generate-positioning.py" --discoverability --apply 2>&1 | tail -1 || true
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
  python3 "$LIMEN_ROOT/scripts/handoff-relay.py" 2>&1 | tail -1 || true
  # adaptive tempo: tighten to MIN whenever work is flowing OR the OPEN QUEUE is non-empty (so a
  # beat that produced no PR this cycle — all no-op / still-running — doesn't back off to 30min
  # while tasks wait); exponential backoff to MAX only when genuinely idle (empty queue, no PR).
  open_n=$(python3 -c "import sys;sys.path.insert(0,'$LIMEN_ROOT/cli/src');from pathlib import Path;from limen.io import load_limen_file;print(sum(1 for t in load_limen_file(Path('$LIMEN_ROOT/tasks.yaml')).tasks if t.status=='open'))" 2>/dev/null || echo 0)
  if [ "$worked" = 1 ] || [ "${open_n:-0}" -gt 0 ]; then beat="$MIN"; echo "── tempo: work pending (open=${open_n}) → ${beat}s ──"
  else beat=$(( beat*2 > MAX ? MAX : beat*2 )); echo "── tempo: idle (queue empty) → ${beat}s ──"; fi
  sleep "$beat"
done
