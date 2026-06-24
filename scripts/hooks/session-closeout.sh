#!/usr/bin/env bash
# session-closeout.sh — SessionEnd hook. The closeout ritual's "this session is done" signal.
#
# A session cannot reap its OWN worktree (git refuses to remove the cwd you are standing in), so the
# actual reversible reap is done from OUTSIDE by the live C_QUICKEN daemon rung (scripts/quicken.py
# --apply). This hook's only job is to drop a breadcrumb so that reap happens on the NEXT beat instead
# of waiting out the 18h idle window — i.e. you ctrl+x, and within a few beats the spent, merged
# worktree is gone with zero commands typed.
#
# Safe by construction (mirrors insights-capture.sh):
#   - no-op unless we are inside a limen isolation worktree  (nothing to reap)
#   - append-only breadcrumb; the reaper still re-verifies clean + fully-merged before removing
#   - never blocks session end                               (always exit 0)
set -u

CWD="$(pwd -P 2>/dev/null || pwd)"
case "$CWD" in
  */.claude/worktrees/*|*/.worktrees/*|*/.limen-worktrees/*) : ;;
  *) exit 0 ;;                       # not an isolation worktree — nothing for closeout to do
esac

# Resolve the limen root (the live main checkout) by stripping the worktree suffix.
ROOT="${CWD%%/.claude/worktrees/*}"
ROOT="${ROOT%%/.worktrees/*}"
ROOT="${ROOT%%/.limen-worktrees/*}"
LOG="$ROOT/logs/session-closeout.jsonl"
[ -d "$ROOT/logs" ] || mkdir -p "$ROOT/logs" 2>/dev/null || exit 0

SID="${CLAUDE_SESSION_ID:-unknown}"
BRANCH="$(git -C "$CWD" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
TS="$(date +%s 2>/dev/null || echo 0)"

# append-only breadcrumb; quicken.py:_ended_sids() reads it and marks the session CLOSED next beat.
printf '{"ts":%s,"sid":"%s","cwd":"%s","branch":"%s"}\n' \
  "$TS" "$SID" "$CWD" "$BRANCH" >>"$LOG" 2>/dev/null || true
exit 0
