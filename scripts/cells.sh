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
# optionally running its own scoped conductor (a heartbeat loop bound to that worktree).
# Conductors are isolated: own LIMEN_ROOT, own tasks file, own branch namespace, own pidfile
# + lock + log — so you can run several at once without them racing each other or the daemon.
#
# Usage:
#   cell new   <slug>            # create a cell (worktree off origin/main) → prints its path
#   cell ls                      # list cells: branch · ahead/behind · dirty · conductor · size
#   cell cd    <slug>            # print the cell path (use: cd "$(cell cd foo)")
#   cell conduct <slug> [--loop] [--workstream <handle>]  # start this cell's scoped conductor (bg).
#                                # --loop = continuous. --workstream pins the cell to ONE channel:
#                                # the conductor sees only that channel's board (one-worker-one-lane).
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
mkdir -p "$CELL_LOGS"

die() { echo "cell: $*" >&2; exit 1; }
write_empty_board() {
  local out="${1:?write_empty_board needs a path}"
  # Write atomically (temp in the same dir + rename) so a reader — the daemon, or a test polling
  # for the board to appear — never observes the empty/partial window between create and flush that
  # a plain `cat > "$out"` leaves. mv within one filesystem is atomic: the board appears complete or
  # not at all. (Fixes the intermittent test_cells.py None-read: `yaml.safe_load` of a half-written
  # board returned None → data["tasks"] TypeError.)
  local tmp="$out.tmp.$$"
  cat > "$tmp" <<'YAML'
version: "1.0"
portal:
  name: scoped-empty
tasks: []
YAML
  mv -f "$tmp" "$out"
}
slug_ok() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "bad slug '$1' (use letters/digits/._-)"; }
cell_path() { echo "$WT_DIR/$1"; }
cell_branch() { echo "${BRANCH_PREFIX}$1"; }
pidfile() { echo "$CELL_LOGS/$1.pid"; }
conductor_running() { local pf; pf="$(pidfile "$1")"; [ -f "$pf" ] && kill -0 "$(cat "$pf")" 2>/dev/null; }
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
    cond="$(conductor_running "$slug" && echo "PID $(cat "$(pidfile "$slug")")" || echo '—')"
    size="$(du -sh "$p" 2>/dev/null | cut -f1)"
    printf "%-26s %-22s %-12s %-6s %-10s %-7s\n" "$slug" "$b" "$ab" "$dirty" "$cond" "$size"
  done
}

cmd_conduct() {
  local slug="${1:-}"; shift || true; [ -n "$slug" ] || die "usage: cell conduct <slug> [--loop] [--workstream <handle>]"
  local p b; p="$(cell_path "$slug")"; b="$(cell_branch "$slug")"
  require_cell "$slug"
  conductor_running "$slug" && die "conductor for '$slug' already running (PID $(cat "$(pidfile "$slug")"))"
  local loop=0 workstream=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --loop) loop=1; shift ;;
      --workstream|--ws) workstream="${2:-}"; [ -n "$workstream" ] || die "--workstream needs a handle"; shift 2 ;;
      *) die "cell conduct: unknown option '$1' (want: --loop, --workstream <handle>)" ;;
    esac
  done
  local log="$CELL_LOGS/$slug.conduct.log"
  local cell_board="$p/tasks.cell.yaml"
  # Scoped + isolated: own LIMEN_ROOT (the cell), own tasks file, own branch namespace.
  # Fleet-wide merge/dispatch beats are OFF by default so parallel conductors never race main
  # or each other; the cell conductor builds/verifies within its own branch.
  (
    cd "$p" || exit 1
    export LIMEN_ROOT="$p"
    export LIMEN_BRANCH_PREFIX="cell-$slug-"
    export LIMEN_MERGE_DRAIN=0 LIMEN_JULES_LAND=0   # no fleet-wide GitHub merges from a cell
    if [ -n "$workstream" ]; then
      # ONE-WORKER-ONE-WORKSTREAM invariant: feed the conductor ONLY this channel's tasks, so it
      # structurally cannot mix purposes (the cure for 10-20 mixed PRs per session). Read the full
      # board ($p/tasks.yaml) and emit the filtered subset to the cell board.
      export LIMEN_WORKSTREAM="$workstream"
      if ! LIMEN_TASKS="$p/tasks.yaml" limen channels --scope "$workstream" --emit "$cell_board" >/dev/null 2>&1; then
        echo "cell: scoped board emit failed for workstream '$workstream'; writing empty board to preserve isolation" >&2
        write_empty_board "$cell_board"
      fi
    else
      [ -f "$cell_board" ] || cp "$p/tasks.yaml" "$cell_board" 2>/dev/null || write_empty_board "$cell_board"
    fi
    export LIMEN_TASKS="$cell_board"
    if [ "$loop" = "1" ]; then
      exec bash "$p/scripts/heartbeat-loop.sh"          # continuous (while-true) conductor
    else
      bash "$p/scripts/heartbeat.sh" 2>&1 || true       # single one-shot beat (cheap, inspectable)
    fi
  ) >"$log" 2>&1 &
  local cpid=$!
  echo "$cpid" > "$(pidfile "$slug")"
  echo "cell '$slug' conductor started (PID $cpid, $([ "$loop" = 1 ] && echo loop || echo single-beat)$([ -n "$workstream" ] && echo ", workstream=$workstream")) → $log"
}

cmd_stop() {
  local slug="${1:?usage: cell stop <slug>}"; local pf; pf="$(pidfile "$slug")"
  conductor_running "$slug" || { echo "cell '$slug': no conductor running"; rm -f "$pf"; return 0; }
  local cpid; cpid="$(cat "$pf")"
  kill "$cpid" 2>/dev/null; sleep 1; kill -9 "$cpid" 2>/dev/null || true
  rm -f "$pf"; echo "cell '$slug' conductor stopped (was PID $cpid)"
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
  conductor_running "$slug" && cmd_stop "$slug"
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
