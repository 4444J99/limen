#!/usr/bin/env bash
# cells.sh — parallel work CELLS: run multiple ideas (and multiple conductors) at once,
# each isolated in its own worktree, with the full lifecycle baked in so nothing leaks.
#
# WHY: worktrees were created ad-hoc (`git worktree add ../<id>`) off a DRIFTED local HEAD,
# which (a) bred stale-base forks (the #347 thicket) and (b) leaked ~50GB because no organ
# reaped .claude/worktrees. A "cell" fixes both: it is always branched from origin/main, it
# lives under the reclaim organ's sweep, and `reap` tears it down loss-free.
#
# A CELL = one parallel idea = one worktree (.claude/worktrees/<slug>) on branch cell/<slug>,
# optionally registering its own scoped conductor capability with the canonical broker.
# Conductors are isolated: own worktree, branch namespace, pidfile + log. They share the
# authenticated keeper and never create a second mutable task-board authority.
#
# Usage:
#   cell new   <slug>            # create a cell (worktree off origin/main) → prints its path
#   cell ls                      # list cells: branch · ahead/behind · dirty · conductor · size
#   cell cd    <slug>            # print the cell path (use: cd "$(cell cd foo)")
#   cell conduct <slug> [--loop] [--workstream <handle>]  # start this cell's scoped conductor (bg).
#                                # --loop = refresh registration. --workstream passes one purpose
#                                # channel to the native adapter (one-worker-one-lane).
#   cell stop  <slug>            # stop this cell's conductor
#   cell merge <slug>            # push + open/merge its PR via merge-policy (the standing grant)
#   cell reap  <slug>            # stop + hand off removal to receipt-backed reclaim/reap organs
#   cell reap-dead               # reclaim every provably-dead cell (clean+content-preserved+idle)
#   cell help
#
# Safe by construction: `new` always fetches and branches from origin/main; `reap` refuses to
# drop a dirty/unpushed cell and never force-discards; conductors default to a SCOPED loop
# (build/verify within the cell), never fleet-wide merges, so two cells never fight over main.
set -uo pipefail

LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
WT_DIR="$LIMEN_ROOT/.claude/worktrees"
CELL_LOGS="$LIMEN_ROOT/logs/cells"
BRANCH_PREFIX="cell/"
SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"
mkdir -p "$CELL_LOGS"

die() { echo "cell: $*" >&2; exit 1; }
slug_ok() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "bad slug '$1' (use letters/digits/._-)"; }
cell_path() { echo "$WT_DIR/$1"; }
cell_branch() { echo "${BRANCH_PREFIX}$1"; }
pidfile() { echo "$CELL_LOGS/$1.pid"; }
receipt_value() {
  local receipt="${1:?receipt_value needs a receipt}" key="${2:?receipt_value needs a key}"
  [ -f "$receipt" ] || return 1
  awk -F= -v wanted="$key" '
    $1 == wanted {
      print substr($0, length($1) + 2)
      exit
    }
  ' "$receipt"
}
process_start_identity() {
  ps -p "${1:?process_start_identity needs a pid}" -o lstart= 2>/dev/null \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}
process_command_identity() {
  # -ww: unlimited width on both procps and BSD ps. Without it, procps falls
  # back to 80 columns when it cannot determine a terminal size (e.g. under a
  # pytest-xdist worker), truncating the argv before the owner token and making
  # every ownership proof read as foreign-process.
  ps -ww -p "${1:?process_command_identity needs a pid}" -o command= 2>/dev/null \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}
write_cell_receipt() {
  local slug="${1:?write_cell_receipt needs a slug}"
  local state="${2:?write_cell_receipt needs a state}"
  local registration_status="${3:?write_cell_receipt needs registration status}"
  local cpid="${4:?write_cell_receipt needs a pid}"
  local start_identity="${5:-}"
  local owner_token="${6:?write_cell_receipt needs an owner token}"
  local session_id="${7:?write_cell_receipt needs a session id}"
  local agent="${8:?write_cell_receipt needs an agent}"
  local surface="${9:?write_cell_receipt needs a surface}"
  local p="${10:?write_cell_receipt needs a cell path}"
  local loop="${11:?write_cell_receipt needs a loop flag}"
  local workstream="${12:-}"
  local run_id="${13:-}"
  local run_owner_session_id="${14:-}"
  local human_protected="${15:-0}"
  local receipt tmp
  receipt="$(pidfile "$slug")"
  tmp="${receipt}.tmp.$$"
  (
    umask 077
    printf '%s\n' \
      "schema=limen.cell_registration.v1" \
      "state=$state" \
      "registration_status=$registration_status" \
      "pid=$cpid" \
      "start_identity=$start_identity" \
      "owner_token=$owner_token" \
      "script_path=$SCRIPT_PATH" \
      "slug=$slug" \
      "session_id=$session_id" \
      "agent=$agent" \
      "surface=$surface" \
      "cell_path=$p" \
      "loop=$loop" \
      "workstream=$workstream" \
      "run_id=$run_id" \
      "run_owner_session_id=$run_owner_session_id" \
      "human_protected=$human_protected" > "$tmp"
  )
  mv "$tmp" "$receipt"
}
process_ownership_status() {
  local slug="${1:?process_ownership_status needs a slug}" receipt state cpid expected_start actual_start
  local owner_token command_identity
  receipt="$(pidfile "$slug")"
  [ -f "$receipt" ] || { echo "missing"; return 0; }
  [ "$(receipt_value "$receipt" schema)" = "limen.cell_registration.v1" ] \
    || { echo "invalid-receipt"; return 0; }
  state="$(receipt_value "$receipt" state)"
  case "$state" in
    exited|failed|stopped) echo "terminal"; return 0 ;;
    starting|registered) ;;
    *) echo "invalid-state"; return 0 ;;
  esac
  cpid="$(receipt_value "$receipt" pid)"
  [[ "$cpid" =~ ^[1-9][0-9]*$ ]] || { echo "invalid-pid"; return 0; }
  kill -0 "$cpid" 2>/dev/null || { echo "dead"; return 0; }
  expected_start="$(receipt_value "$receipt" start_identity)"
  actual_start="$(process_start_identity "$cpid")"
  [ -n "$expected_start" ] && [ "$actual_start" = "$expected_start" ] \
    || { echo "stale-start"; return 0; }
  owner_token="$(receipt_value "$receipt" owner_token)"
  [ -n "$owner_token" ] || { echo "invalid-token"; return 0; }
  command_identity="$(process_command_identity "$cpid")"
  [[ "$command_identity" == *"$SCRIPT_PATH _registration-loop $slug "* ]] \
    && [[ "$command_identity" == *" $owner_token "* || "$command_identity" == *" $owner_token" ]] \
    || { echo "foreign-process"; return 0; }
  echo "owned"
}
conductor_running() { [ "$(process_ownership_status "$1")" = "owned" ]; }
conductor_pid() { receipt_value "$(pidfile "$1")" pid; }
current_branch() { git -C "$1" rev-parse --abbrev-ref HEAD 2>/dev/null || true; }
require_cell() {
  local slug="${1:?require_cell needs a slug}" p b expected
  p="$(cell_path "$slug")"; expected="$(cell_branch "$slug")"
  [ -d "$p" ] || die "no cell '$slug' (run: cell new $slug)"
  b="$(current_branch "$p")"
  [ "$b" = "$expected" ] || die "'$slug' is not a cell (branch: ${b:-unknown}; expected: $expected). Use reclaim-worktrees.py for non-cell worktrees."
}

cmd_new() {
  local slug="${1:-}"; [ -n "$slug" ] || die "usage: cell new <slug>"
  slug_ok "$slug"
  local p b; p="$(cell_path "$slug")"; b="$(cell_branch "$slug")"
  [ -e "$p" ] && die "cell '$slug' already exists at $p"
  echo "cell: fetching origin (branch from origin/main — never local HEAD)…" >&2
  git -C "$LIMEN_ROOT" fetch origin --quiet || die "fetch failed"
  git -C "$LIMEN_ROOT" worktree add "$p" -b "$b" origin/main >/dev/null \
    || die "worktree add failed (branch $b may already exist — try a new slug)"
  echo "cell '$slug' ready on $b (off origin/main)" >&2
  echo "$p"   # stdout = path, so: cd \"\$(cell new foo)\"
}

cmd_cd() {
  local slug="${1:?usage: cell cd <slug>}" p
  require_cell "$slug"
  p="$(cell_path "$slug")"
  echo "$p"
}

cmd_ls() {
  printf "%-26s %-22s %-12s %-6s %-10s %-7s\n" "CELL" "BRANCH" "AHEAD/BEHIND" "DIRTY" "CONDUCTOR" "SIZE"
  [ -d "$WT_DIR" ] || return 0
  local p slug b ab dirty cond size head behind ahead
  for p in "$WT_DIR"/*/; do
    [ -d "$p" ] || continue
    p="${p%/}"; slug="$(basename "$p")"
    b="$(git -C "$p" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
    [ "$b" = "$(cell_branch "$slug")" ] || continue
    ahead="$(git -C "$p" rev-list --count origin/main..HEAD 2>/dev/null || echo '?')"
    behind="$(git -C "$p" rev-list --count HEAD..origin/main 2>/dev/null || echo '?')"
    ab="+${ahead}/-${behind}"
    dirty="$([ -n "$(git -C "$p" status --porcelain 2>/dev/null)" ] && echo yes || echo no)"
    case "$(process_ownership_status "$slug")" in
      owned) cond="PID $(conductor_pid "$slug")" ;;
      invalid-*|stale-start|foreign-process) cond="REFUSED" ;;
      *) cond="—" ;;
    esac
    size="$(du -sh "$p" 2>/dev/null | cut -f1)"
    printf "%-26s %-22s %-12s %-6s %-10s %-7s\n" "$slug" "$b" "$ab" "$dirty" "$cond" "$size"
  done
}

cmd_conduct() {
  local slug="${1:-}"; shift || true; [ -n "$slug" ] || die "usage: cell conduct <slug> [--loop] [--workstream <handle>]"
  local p b; p="$(cell_path "$slug")"; b="$(cell_branch "$slug")"
  require_cell "$slug"
  local ownership_status
  ownership_status="$(process_ownership_status "$slug")"
  case "$ownership_status" in
    owned) die "conductor for '$slug' already running (PID $(conductor_pid "$slug"))" ;;
    invalid-*|stale-start|foreign-process)
      die "refusing to overwrite untrusted registration receipt for '$slug' ($ownership_status)"
      ;;
  esac
  local loop=0 workstream=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --loop) loop=1; shift ;;
      --workstream|--ws) workstream="${2:-}"; [ -n "$workstream" ] || die "--workstream needs a handle"; shift 2 ;;
      *) die "cell conduct: unknown option '$1' (want: --loop, --workstream <handle>)" ;;
    esac
  done
  local agent="${LIMEN_AGENT:-}"
  local surface="cell${workstream:+:$workstream}"
  local run_id="${LIMEN_RUN_ID:-}"
  local run_owner_session_id="${LIMEN_CONDUCTOR_SESSION_ID:-${LIMEN_SESSION_ID:-}}"
  local human_protected="${LIMEN_HUMAN_PROTECTED:-0}"
  local origin="direct"
  [ -n "$agent" ] || die "cell conduct requires LIMEN_AGENT; executor identity is never inherited or guessed"
  [ "$human_protected" = "0" ] || [ "$human_protected" = "1" ] \
    || die "LIMEN_HUMAN_PROTECTED must be 0 or 1"
  if [ -n "$run_id" ]; then
    origin="dispatched"
    [ -n "$run_owner_session_id" ] \
      || die "a conducted LIMEN_RUN_ID requires LIMEN_CONDUCTOR_SESSION_ID for cooperative stop"
  fi
  if [ -z "${LIMEN_CONDUCT_URL:-}" ] && [ -z "${LIMEN_CONDUCT_STATE:-}" ]; then
    die "cell conduct requires the canonical broker (set LIMEN_CONDUCT_URL or explicit test LIMEN_CONDUCT_STATE)"
  fi
  local log="$CELL_LOGS/$slug.conduct.log"
  local canonical_root="$LIMEN_ROOT"
  local owner_token
  owner_token="$(
    printf '%s' "$slug:$$:$RANDOM:$(date +%s)" \
      | shasum -a 256 \
      | awk '{print $1}'
  )"
  # A cell is an isolated worktree/view. Registration and every lifecycle mutation go through the
  # same canonical broker; no tasks.cell.yaml projection is emitted or writable by the cell.
  bash "$SCRIPT_PATH" _registration-loop \
    "$slug" "$agent" "$surface" "$p" "$canonical_root" "$loop" "$workstream" \
    "$owner_token" "$run_id" "$run_owner_session_id" "$human_protected" "$origin" \
    >"$log" 2>&1 &
  local cpid=$!
  local receipt_ready=0 _
  for _ in {1..50}; do
    if [ "$(receipt_value "$(pidfile "$slug")" owner_token 2>/dev/null || true)" = "$owner_token" ]; then
      receipt_ready=1
      break
    fi
    kill -0 "$cpid" 2>/dev/null || break
    sleep 0.02
  done
  [ "$receipt_ready" = "1" ] \
    || die "registration loop for '$slug' did not establish an exact PID identity receipt"
  echo "cell '$slug' conductor started (PID $cpid, $([ "$loop" = 1 ] && echo loop || echo single-beat)$([ -n "$workstream" ] && echo ", workstream=$workstream")) → $log"
}

cmd_stop() {
  local slug="${1:?usage: cell stop <slug>}" receipt ownership_status
  receipt="$(pidfile "$slug")"
  [ -f "$receipt" ] || { echo "cell '$slug': no conductor registration receipt"; return 0; }
  ownership_status="$(process_ownership_status "$slug")"
  case "$ownership_status" in
    terminal|dead)
      echo "cell '$slug': no live conductor registration loop (receipt retained)"
      return 0
      ;;
    owned) ;;
    *)
      die "ownership proof failed for '$slug' ($ownership_status); refusing to signal recorded PID"
      ;;
  esac
  [ "$(receipt_value "$receipt" human_protected)" != "1" ] \
    || die "cell '$slug' is human-protected; autonomous stop may not signal it"
  local run_id run_owner_session_id cpid
  run_id="$(receipt_value "$receipt" run_id)"
  run_owner_session_id="$(receipt_value "$receipt" run_owner_session_id)"
  cpid="$(receipt_value "$receipt" pid)"
  if [ -n "$run_id" ]; then
    [ -n "$run_owner_session_id" ] \
      || die "cell '$slug' owns run '$run_id' but has no conductor session for cooperative stop"
    limen conduct request-stop "$run_id" --session-id "$run_owner_session_id" \
      || die "broker rejected cooperative stop for cell '$slug' run '$run_id'"
    echo "cell '$slug' cooperative stop requested for run '$run_id'; local registration loop remains owned"
    return 0
  fi
  kill -TERM "$cpid" 2>/dev/null \
    || die "exact owned registration loop PID $cpid could not receive graceful TERM"
  local _
  for _ in {1..20}; do
    kill -0 "$cpid" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "$cpid" 2>/dev/null; then
    echo "cell '$slug' graceful stop is still pending for exact PID $cpid; no force signal sent" >&2
    return 2
  fi
  echo "cell '$slug' registration loop stopped gracefully (was PID $cpid; receipt retained)"
}

registration_loop() {
  local slug="${1:?registration loop needs a slug}"
  local agent="${2:?registration loop needs an agent}"
  local surface="${3:?registration loop needs a surface}"
  local p="${4:?registration loop needs a cell path}"
  local canonical_root="${5:?registration loop needs the canonical root}"
  local loop="${6:?registration loop needs a loop flag}"
  local workstream="${7:-}"
  local owner_token="${8:?registration loop needs an owner token}"
  local run_id="${9:-}"
  local run_owner_session_id="${10:-}"
  local human_protected="${11:-0}"
  local origin="${12:-direct}"
  local session_id="cell-$slug"
  local cpid="$$"
  local start_identity registration_status="pending" registration_final_state="exited"
  start_identity="$(process_start_identity "$cpid")"
  write_cell_receipt \
    "$slug" "starting" "$registration_status" "$cpid" "$start_identity" "$owner_token" \
    "$session_id" "$agent" "$surface" "$p" "$loop" "$workstream" "$run_id" \
    "$run_owner_session_id" "$human_protected"
  trap 'registration_final_state="stopped"; exit 0' TERM INT
  trap 'write_cell_receipt "$slug" "$registration_final_state" "$registration_status" "$cpid" "$start_identity" "$owner_token" "$session_id" "$agent" "$surface" "$p" "$loop" "$workstream" "$run_id" "$run_owner_session_id" "$human_protected"' EXIT
  cd "$p" || { registration_status="failed"; registration_final_state="failed"; return 1; }
  export LIMEN_ROOT="$p"
  export LIMEN_LIVE_ROOT="$canonical_root"
  export LIMEN_AGENT="$agent"
  export LIMEN_SESSION_ID="$session_id"
  export LIMEN_WORKTREE="$p"
  export LIMEN_BRANCH_PREFIX="cell-$slug-"
  export LIMEN_MERGE_DRAIN=0 LIMEN_JULES_LAND=0
  if [ -n "$workstream" ]; then
    export LIMEN_WORKSTREAM="$workstream"
  fi
  local -a register_args=(
    conduct register
    --agent "$agent"
    --surface "$surface"
    --session-id "$session_id"
    --origin "$origin"
    --worktree "$p"
  )
  if [ -n "$run_id" ]; then
    register_args+=(--native-run-id "$run_id")
  fi
  if [ "$human_protected" = "1" ]; then
    register_args+=(--human-protected)
  fi
  local _
  while true; do
    if ! limen "${register_args[@]}"; then
      registration_status="failed"
      registration_final_state="failed"
      return 1
    fi
    registration_status="accepted"
    write_cell_receipt \
      "$slug" "registered" "$registration_status" "$cpid" "$start_identity" "$owner_token" \
      "$session_id" "$agent" "$surface" "$p" "$loop" "$workstream" "$run_id" \
      "$run_owner_session_id" "$human_protected"
    [ "$loop" = "1" ] || return 0
    for _ in {1..30}; do
      sleep 1
    done
  done
}

cmd_merge() {
  local slug="${1:?usage: cell merge <slug>}"; local p b; p="$(cell_path "$slug")"; b="$(cell_branch "$slug")"
  require_cell "$slug"
  [ -n "$(git -C "$p" status --porcelain)" ] && die "cell '$slug' has uncommitted changes — commit first"
  git -C "$p" push -u origin "$b" 2>&1 | tail -2
  echo "cell: run the standing merge grant →  scripts/merge-policy.sh <PR#>  (open the PR if none yet: gh pr create)"
}

cmd_reap() {
  local slug="${1:-}"; shift || true; [ -n "$slug" ] || die "usage: cell reap <slug>"
  [ "${1:-}" = "--force" ] && die "cell reap --force is retired; archive/merge/preserve first, then use receipt-backed reclaim"
  [ $# -eq 0 ] || die "cell reap: unexpected argument '$1'"
  local p b; p="$(cell_path "$slug")"; b="$(cell_branch "$slug")"
  require_cell "$slug"
  local ownership_status
  ownership_status="$(process_ownership_status "$slug")"
  case "$ownership_status" in
    owned)
      cmd_stop "$slug" || die "cell '$slug' did not reach a graceful stop boundary"
      conductor_running "$slug" \
        && die "cell '$slug' still owns a live registration loop; wait for the cooperative run stop receipt"
      ;;
    invalid-*|stale-start|foreign-process)
      die "cell '$slug' has an untrusted registration receipt ($ownership_status); liveness owner must reconcile it"
      ;;
  esac
  [ -n "$(git -C "$p" status --porcelain 2>/dev/null)" ] && die "cell '$slug' is DIRTY — commit/push before reclaim"
  local head; head="$(git -C "$p" rev-parse HEAD 2>/dev/null)"
  if [ -n "$head" ] && ! git -C "$p" for-each-ref --format='%(refname)' refs/remotes | while read -r r; do
       git -C "$p" merge-base --is-ancestor "$head" "$r" 2>/dev/null && { echo found; break; }; done | grep -q found; then
    die "cell '$slug' has UNPUSHED commits — 'cell merge $slug' first, then receipt-backed reclaim"
  fi
  echo "cell '$slug' is a clean preserved reclaim candidate at $p"
  echo "cell: physical removal is delegated to docs/worktree-reclaim-acceptance.jsonl + reclaim-worktrees.py"
  echo "cell: branch cleanup is delegated to docs/branch-reap-acceptance.jsonl + reap-branches.py"
  python3 "$LIMEN_ROOT/scripts/reclaim-worktrees.py" --force
}

cmd_reap_dead() {
  echo "cell: delegating to the SPRAWL-RECLAIM organ (loss-free: clean+content-preserved+idle only)…"
  echo "      (dry-run by default — pass --apply to actually reclaim)"
  python3 "$LIMEN_ROOT/scripts/reclaim-worktrees.py" "$@"
}

case "${1:-help}" in
  _registration-loop) shift; registration_loop "$@" ;;
  new)        shift; cmd_new "$@" ;;
  cd)         shift; cmd_cd "$@" ;;
  ls|list)    shift; cmd_ls "$@" ;;
  conduct)    shift; cmd_conduct "$@" ;;
  stop)       shift; cmd_stop "$@" ;;
  merge)      shift; cmd_merge "$@" ;;
  reap|rm)    shift; cmd_reap "$@" ;;
  reap-dead)  shift; cmd_reap_dead "$@" ;;
  help|-h|--help) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown command '${1:-}'. Try: cell help" ;;
esac
