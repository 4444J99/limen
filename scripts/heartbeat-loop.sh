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
set -uo pipefail
export HOME="${HOME:-/Users/4jp}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
# Pin the daemon to its OWN python — a STABLE binary path (created with `venv --copies`) so a single
# one-time macOS Full Disk Access grant on that ONE binary survives Homebrew python upgrades and lets the
# usage organ read vendor app-data (~/.codex, ~/.claude, ~/.gemini) WITHOUT the recurring TCC consent
# prompt. Structural, not best-effort: prepend the venv AND verify python3 resolves inside it. If the venv
# is missing we fall back to system python but LOG it loudly — so the daemon never silently runs an
# ungranted interpreter that re-triggers the prompt, and never dead-stops. ([[no-never-happens-again]])
LIMEN_VENV_PY="$LIMEN_ROOT/.venv/bin/python3"
if [ -x "$LIMEN_VENV_PY" ]; then
  export PATH="$LIMEN_ROOT/.venv/bin:$PATH"; hash -r 2>/dev/null || true
  export LIMEN_PY="$LIMEN_VENV_PY"
else
  export LIMEN_PY="$(command -v python3 || echo python3)"
  echo "$(date '+%F %T') WARN: $LIMEN_VENV_PY missing — using system python ($LIMEN_PY); the macOS TCC" \
       "prompt may recur. Recreate the pinned interpreter: python3 -m venv --copies $LIMEN_ROOT/.venv" \
       >> "$LIMEN_ROOT/logs/heartbeat.out.log" 2>/dev/null || true
fi
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
export LIMEN_WORKDIR="${LIMEN_WORKDIR:-$HOME/Workspace}"
export LIMEN_ISOLATION="${LIMEN_ISOLATION:-worktree}"
export GEMINI_CLI_TRUST_WORKSPACE="${GEMINI_CLI_TRUST_WORKSPACE:-true}"
export PYTHONPATH="$LIMEN_ROOT/cli/src"
cd "$LIMEN_ROOT" || exit 1

[ -f "$HOME/.limen.env" ] && { set -a; . "$HOME/.limen.env"; set +a; }
# opencode runs on a Google model → it needs the Google generative-AI key (reuse gemini's)
[ -n "${GEMINI_API_KEY:-}" ] && export GOOGLE_GENERATIVE_AI_API_KEY="${GOOGLE_GENERATIVE_AI_API_KEY:-$GEMINI_API_KEY}"

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

LANES="${LIMEN_LANES:-codex,opencode,agy,claude}"
[ -n "${GEMINI_API_KEY:-}" ] && LANES="$LANES,gemini"
[ -n "${WARP_API_KEY:-}" ] && LANES="$LANES,warp,oz"
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

# base tempo (adaptive) + voice subdivisions (configurable)
MIN="${LIMEN_LOOP_MIN:-120}"; MAX="${LIMEN_LOOP_MAX:-1800}"; beat="$MIN"
# voices subdivide the base tempo — the work-cadence EXPLORE>PLAN>BUILD>VERIFY>HEAL>LEARN>RELAY:
C_BALANCE="${LIMEN_BEAT_BALANCE:-2}"   # PLAN  (route + rebalance)
C_FEED="${LIMEN_BEAT_FEED:-3}"         # EXPLORE (mine the backlog)
C_DRAIN="${LIMEN_BEAT_DRAIN:-3}"       # VERIFY (harvest completed → done; faster recycle)
C_HEAL="${LIMEN_BEAT_HEAL:-6}"         # HEAL  (recover failed/orphaned → fresh cascade)
C_HYGIENE="${LIMEN_BEAT_HYGIENE:-8}"; C_BACKUP="${LIMEN_BEAT_BACKUP:-48}"
C_SYNC="${LIMEN_BEAT_SYNC:-2}"         # SELF-HEAL the substrate (re-converge checkout to the release)
C_CORPUS="${LIMEN_BEAT_CORPUS:-24}"    # CONVERGE (distill his words toward ONE; expensive → rare)
C_WEB="${LIMEN_BEAT_WEB:-4}"           # LEARN (refresh the visualized surfaces)
C_REPORT="${LIMEN_BEAT_REPORT:-12}"    # RELAY (conducting report; self-limits to once per usage-day)
LOCKD="$LIMEN_ROOT/logs/.queue.lock.d"   # shared with supervisory ops (two-scale safety)
c=0
play() { [ $(( c % $1 )) -eq 0 ]; }   # true on this voice's beat
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
cleanup() {
  rmdir "$LOCKD" 2>/dev/null || true
  if [ "$(cat "$DAEMON_LOCK" 2>/dev/null)" = "$$" ]; then
    rm -f "$DAEMON_LOCK" "$LIMEN_ROOT/logs/heartbeat-loop.pid" 2>/dev/null
    rmdir "$DAEMON_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "═══ heartbeat-loop start $(date '+%F %T') tempo=${MIN}-${MAX}s lanes=$LANES ═══"
# ensure the web dashboard is served from the start
bash "$LIMEN_ROOT/scripts/refresh-web.sh" 2>&1 | tail -2 || true
while true; do
  # OWNERSHIP BACKSTOP — if any acquisition race let a second loop through, the one whose
  # pid is NOT in the lockfile exits here. Converges to exactly one daemon within a beat.
  if [ "$(cat "$DAEMON_LOCK" 2>/dev/null)" != "$$" ]; then
    echo "no longer singleton owner (pid in lock != $$) — exiting"; exit 0
  fi
  c=$(( c + 1 ))
  worked=0
  echo "──── beat $c $(date '+%F %T') ────"
  MODE="$(python3 "$LIMEN_ROOT/scripts/autonomy-governor.py" mode 2>/dev/null || echo paused)"
  if [ "$MODE" = "paused" ]; then
    echo "autonomy paused by governor — exiting"
    exit 0
  fi
  # SUBSTRATE SELF-HEAL — re-converge this checkout to the release (origin/main) before doing
  # work, so the beat always runs the latest code (push = deploy). ff-only, data-preserving,
  # fail-open; never exits/re-execs the daemon. Closes the loop: root → leaf → back to root.
  play "$C_SYNC" && bash "$LIMEN_ROOT/scripts/sync-release.sh" 2>&1 | tail -2 || true
  python3 "$LIMEN_ROOT/scripts/usage-telemetry.py" 2>&1 | tail -1 || true   # refresh lane health BEFORE route/dispatch
  EFFECTIVE_LANES="$(healthy_lanes "$LANES")"
  if [ "$EFFECTIVE_LANES" != "$LANES" ]; then
    echo "  lanes: ${EFFECTIVE_LANES:-none} active from requested [$LANES]"
  fi

  if [ "$MODE" != "dispatch" ]; then
    echo "autonomy mode=$MODE — telemetry/status only; queue mutation and dispatch skipped"
    python3 "$LIMEN_ROOT/scripts/emit-tick.py" 2>&1 | tail -1 || true
    play "$C_WEB" && bash "$LIMEN_ROOT/scripts/refresh-web.sh" 2>&1 | tail -2 || true
    beat="$MAX"
    echo "── tempo: observe → ${beat}s ──"
    sleep "$beat"
    continue
  fi

  # acquire the shared queue lock so the BODY never races a SUPERVISOR write to
  # tasks.yaml (two-scale safety). If a supervisor holds it, skip queue-mutation this
  # beat (still emit tick/web below). Wait up to ~20s.
  locked=0
  for _ in $(seq 1 20); do mkdir "$LOCKD" 2>/dev/null && { locked=1; break; }; sleep 1; done

  if [ "$locked" = 1 ]; then
    play "$C_DRAIN"   && { bash "$LIMEN_ROOT/scripts/drain.sh" 2>&1 | tail -2 || true        # VERIFY
                           python3 -m limen release-stale --agent jules --hours 24 --apply 2>&1 | tail -1 || true; }
    play "$C_HEAL"    && python3 "$LIMEN_ROOT/scripts/recover.py" --apply 2>&1 | tail -1 || true   # HEAL
    play "$C_FEED"    && { python3 "$LIMEN_ROOT/scripts/mine-backlog.py" --limit "${LIMEN_MINE_LIMIT:-25}" --apply 2>&1 | tail -1 || true  # EXPLORE
                           python3 "$LIMEN_ROOT/scripts/generate-backlog.py" --apply 2>&1 | tail -1 || true  # SELF-FEED: build-out levers on the ranked tier
                           python3 "$LIMEN_ROOT/scripts/discover-value.py" --apply 2>&1 | tail -1 || true; }  # DISCOVER: no repo stays dark — surface latent value, burn the tank
    play "$C_BALANCE" && { python3 "$LIMEN_ROOT/scripts/route.py" --apply 2>&1 | tail -1 || true   # PLAN
                           if [ -n "$EFFECTIVE_LANES" ]; then
                             python3 "$LIMEN_ROOT/scripts/rebalance.py" --lanes "$EFFECTIVE_LANES" --apply 2>&1 | tail -1 || true
                           else
                             echo "no live local lanes available for rebalance"
                           fi; }

    # #11: RELEASE the queue-lock BEFORE the slow dispatch so supervisors (seed / heal / verify)
    # aren't starved through the multi-minute run. dispatch-parallel.py now self-acquires the
    # SAME lockdir around its reserve AND reloads-fresh+commits under it — so nothing races
    # tasks.yaml, and a seed written mid-run survives instead of being clobbered.
    rmdir "$LOCKD" 2>/dev/null || true

    # BUILD — dispatch every beat. Default = SYNC parallel (reserve→run→commit, beat waits for the
    # slowest agent). Opt in to ASYNC (LIMEN_DISPATCH_ASYNC=1): fire detached workers + harvest
    # finished runs → fast beats, a slow agent never gates the beat (the throughput 10x). Async is
    # OFF by default; flip the env + restart between beats to enable. See dispatch-async.py.
    if [ "${LIMEN_DISPATCH_ASYNC:-0}" = "1" ]; then
      out="$(python3 "$LIMEN_ROOT/scripts/dispatch-async.py" --lanes "$EFFECTIVE_LANES,jules" \
              --per-lane "$LOCAL_LIMIT" --max "${LIMEN_ASYNC_MAX:-12}" 2>&1)"
    else
      out="$(python3 "$LIMEN_ROOT/scripts/dispatch-parallel.py" --lanes "$EFFECTIVE_LANES,jules" \
              --per-lane "$LOCAL_LIMIT" --workers "${LIMEN_WORKERS:-8}" 2>&1)"
    fi
    echo "$out" | tail -8
    echo "$out" | grep -qE "→ PR|dispatched/PR|  dispatched:|launched|harvested" && worked=1
  else
    echo "── queue lock held by a supervisor — skipping mutation this beat ──"
  fi

  # RECONCILE — outside the queue-lock (heal-dispatch self-acquires it, so it must NOT run
  # under the daemon's lock or it would deadlock). Verify claimed dispatches vs real PR state,
  # then flip phantom → done/open so the funnel self-clears and the open pool refills each cycle.
  play "$C_HEAL" && { python3 "$LIMEN_ROOT/scripts/verify-dispatch.py" 2>&1 | tail -1 || true
                      python3 "$LIMEN_ROOT/scripts/heal-dispatch.py" --apply 2>&1 | tail -1 || true
                      # LEDGER — weigh the RETURN on every newly-resolved task (the credit side), then
                      # roll up the value verdict (which lane earns its keep / what was sunk money).
                      python3 "$LIMEN_ROOT/scripts/score-dispatch.py" 2>&1 | tail -1 || true
                      python3 "$LIMEN_ROOT/scripts/ledger.py" 2>&1 | tail -1 || true; }
  play "$C_HYGIENE" && bash "$LIMEN_ROOT/scripts/clone-maintenance.sh" 2>&1 | tail -3 || true
  python3 "$LIMEN_ROOT/scripts/emit-tick.py" 2>&1 | tail -1 || true   # tick voice — every beat
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/usage-telemetry.py" 2>&1 | tail -1 || true   # real per-vendor usage
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/money-view.py" 2>&1 | tail -1 || true   # revenue-first money view (no network, can't time out)
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/corpus-view.py" 2>&1 | tail -1 || true   # knowledge-base view: THE ONE + convergence activity (no network)
  play "$C_WEB"     && python3 "$LIMEN_ROOT/scripts/notify-events.py" 2>&1 | tail -1 || true   # push: your-gate ready / ship milestones
  play "$C_REPORT"  && python3 "$LIMEN_ROOT/scripts/conducting-report.py" 2>&1 | tail -1 || true   # RELAY: did the fleet burn its full force? (once/day push — so you never have to ask)
  play "$C_WEB"     && bash "$LIMEN_ROOT/scripts/refresh-web.sh" 2>&1 | tail -2 || true   # web auto-refresh (best-effort; money.html is primary)
  # CAPTURE — get every workspace repo OFF disk into the canonical universal context (commit+push,
  # additive only). Implements the old backup voice; falls back to a legacy backup.sh if present.
  if play "$C_BACKUP"; then
    if [ -x "$LIMEN_ROOT/scripts/capture.sh" ]; then bash "$LIMEN_ROOT/scripts/capture.sh" 2>&1 | tail -3 || true
    elif [ -x "$LIMEN_ROOT/scripts/backup.sh" ]; then bash "$LIMEN_ROOT/scripts/backup.sh" 2>&1 | tail -2 || true; fi
  fi
  # CONVERGE his WORDS — distill the knowledge base toward ONE. Gated OFF by default
  # (LIMEN_CORPUS_CONVERGE=1); the script self-selects live synthesis (LIMEN_CORPUS_CONVERGE_LIVE=1)
  # + graph shots (LIMEN_CORPUS_GRAPH=1). Bounded + fail-open — never gates the beat.
  play "$C_CORPUS"  && [ "${LIMEN_CORPUS_CONVERGE:-0}" = "1" ] && \
    python3 "$LIMEN_ROOT/scripts/corpus-converge.py" --apply 2>&1 | tail -3 || true

  # adaptive tempo: tighten to MIN whenever work is flowing OR the OPEN QUEUE is non-empty (so a
  # beat that produced no PR this cycle — all no-op / still-running — doesn't back off to 30min
  # while tasks wait); exponential backoff to MAX only when genuinely idle (empty queue, no PR).
  open_n=$(python3 -c "import sys;sys.path.insert(0,'$LIMEN_ROOT/cli/src');from pathlib import Path;from limen.io import load_limen_file;print(sum(1 for t in load_limen_file(Path('$LIMEN_ROOT/tasks.yaml')).tasks if t.status=='open'))" 2>/dev/null || echo 0)
  if [ "$worked" = 1 ] || [ "${open_n:-0}" -gt 0 ]; then beat="$MIN"; echo "── tempo: work pending (open=${open_n}) → ${beat}s ──"
  else beat=$(( beat*2 > MAX ? MAX : beat*2 )); echo "── tempo: idle (queue empty) → ${beat}s ──"; fi
  sleep "$beat"
done
