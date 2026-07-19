#!/usr/bin/env bash
# await-pr.sh — the ONE sanctioned synchronous waiter on a PR merge gate.
#
# Sessions used to hand-roll background poll loops (`for i in $(seq 1 40); do gh pr …; sleep 45; done`)
# to babysit merge gates — bespoke, silent on FAIL, and invisible once the session died (the
# 2026-07-15 endless-watcher incident: four concurrent hand-rolled pollers, one a 28-min silent
# stall). This script replaces every such loop with a bounded, loud, single-instance wait:
#
#   - polls scripts/merge-policy.sh — the ONE merge predicate, never a duplicated verdict
#   - hard deadline (LIMEN_AWAIT_PR_TIMEOUT, default 1200 s); every poll prints a loud one-liner,
#     and every terminal path prints an `AWAIT-PR <n>: <VERDICT>` line — there is no silent exit
#   - CI-red and BLOCKED are terminal FAILURES, never waited out (a red check needs a fix, a
#     BLOCKED merge needs a rebase — more waiting cannot clear either)
#   - refuses to start while logs/AUTONOMY_PAUSED prohibits merges (no --force: a paused estate
#     waits for the operator, and so does every session in it)
#   - single instance per PR (mkdir lock under logs/); a second waiter exits ALREADY-WATCHED
#   - --merge completes the standing grant on CLEARED using merge-policy's declared mode:
#       direct -> one exact-head squash merge
#       queue  -> one exact-head enqueue, then a bounded wait for the actual MERGED state
#     A successful queue command is QUEUED, never a false MERGED receipt, and is never re-issued.
#
# Anything longer than the deadline belongs to the beat's merge rung (scripts/merge-drain.py via
# scripts/drain.sh): hand off and end the session — never re-arm the waiter in a loop.
#
# Usage:  scripts/await-pr.sh <PR#> [--repo OWNER/NAME] [--timeout SECS] [--interval SECS] [--merge]
#
# Exit codes:
#   0  CLEARED (and actually MERGED with      2  TIMEOUT — deadline elapsed, still HOLD/QUEUED
#      --merge)
#   1  FAILED — BLOCKED verdict, CI checks    3  REFUSED-PAUSED — pause marker prohibits merges
#      failing, or gh pr merge itself failed  4  ALREADY-WATCHED — live lock held for this PR
#                                            64  usage error
set -uo pipefail

ROOT="${LIMEN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
POLICY="${LIMEN_MERGE_POLICY_BIN:-$ROOT/scripts/merge-policy.sh}"

PR=""; REPO=""; MERGE=0
TIMEOUT="${LIMEN_AWAIT_PR_TIMEOUT:-1200}"
INTERVAL="${LIMEN_AWAIT_PR_INTERVAL:-45}"
usage() { sed -n '22,28p' "$0"; exit 64; }
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --repo=*) REPO="${1#*=}"; shift ;;
    --timeout) TIMEOUT="${2:-}"; shift 2 ;;
    --timeout=*) TIMEOUT="${1#*=}"; shift ;;
    --interval) INTERVAL="${2:-}"; shift 2 ;;
    --interval=*) INTERVAL="${1#*=}"; shift ;;
    --merge) MERGE=1; shift ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) PR="$1"; shift ;;
  esac
done
case "$PR" in (*[!0-9]*|"") usage ;; esac
case "$TIMEOUT" in (*[!0-9]*|"") usage ;; esac
case "$INTERVAL" in (*[!0-9]*|"") usage ;; esac
repo_args=(); [ -n "$REPO" ] && repo_args=(--repo "$REPO")
# bash 3.2 (macOS /bin/bash): "${repo_args[@]+"${repo_args[@]}"}" at each call site — an empty
# array expands to nothing under set -u, a populated one to its elements.

QUEUE_OWNER=""; QUEUE_NAME=""
resolve_queue_repo() {
  local repo_id
  if [ -n "$REPO" ]; then
    repo_id="$REPO"
  else
    repo_id="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" || return 1
  fi
  case "$repo_id" in
    */*)
      QUEUE_OWNER="${repo_id%%/*}"
      QUEUE_NAME="${repo_id#*/}"
      ;;
    *) return 1 ;;
  esac
  # The documented --repo contract is OWNER/NAME. Reject a hostname-prefixed or otherwise
  # ambiguous value instead of querying the wrong repository after an enqueue.
  [ -n "$QUEUE_OWNER" ] && [ -n "$QUEUE_NAME" ] && case "$QUEUE_NAME" in */*) false ;; *) true ;; esac
}

mkdir -p "$ROOT/logs" 2>/dev/null || true
finish() { # exit_code — the single exit path after the lock is held: log one summary line, exit.
  printf '%s await-pr pr=%s exit=%s polls=%s last=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PR" "$1" "${i:-0}" "${last:-none}" \
    >> "$ROOT/logs/await-pr.log" 2>/dev/null || true
  exit "$1"
}

# ── pause refusal — before the lock, before the first poll ─────────────────────────────────────
# A pause marker whose prohibitions mention merge binds every session, not just the beat: no
# watcher, no merge, until the operator releases it. (The governor completes PR-owned releases
# itself; an operator pause has no compliant wait to offer, so refuse instead of spinning.)
MARKER="$ROOT/logs/AUTONOMY_PAUSED"
if [ -f "$MARKER" ] && grep -qi '^prohibitions:.*merge' "$MARKER" 2>/dev/null; then
  reason="$(grep -i '^reason:' "$MARKER" 2>/dev/null | head -1)"
  echo "AWAIT-PR $PR: REFUSED — autonomy paused: ${reason#*: }"
  grep -i '^prohibitions:' "$MARKER" 2>/dev/null | head -1 | sed 's/^/  /'
  echo "  no waiter runs under a merge-prohibiting pause; resume autonomy first (logs/AUTONOMY_PAUSED)."
  last="REFUSED-PAUSED"; finish 3
fi

# ── single instance per PR — mkdir lock (atomic; flock is absent on stock macOS) ───────────────
LOCK="$ROOT/logs/.await-pr-$PR.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  holder="$(cat "$LOCK/pid" 2>/dev/null || true)"
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
    echo "AWAIT-PR $PR: ALREADY-WATCHED by pid $holder"
    exit 4
  fi
  rm -rf "$LOCK" 2>/dev/null
  mkdir "$LOCK" 2>/dev/null || { echo "AWAIT-PR $PR: ALREADY-WATCHED (lock contention)"; exit 4; }
fi
printf '%s\n' "$$" > "$LOCK/pid" 2>/dev/null || true
trap 'rm -rf "$LOCK" 2>/dev/null' EXIT

# ── the bounded, loud poll loop ─────────────────────────────────────────────────────────────────
start="$(date +%s)"; deadline=$((start + TIMEOUT)); i=0; last=""
queued=0; queued_head=""
while :; do
  # Once enqueued, observe GitHub state directly. Never invoke merge-policy or `gh pr merge`
  # again: a successful enqueue is not a merge receipt, and this waiter does not auto re-enqueue
  # after queue removal/failure.
  if [ "$queued" = 1 ]; then
    i=$((i + 1))
    # gh pr view does not expose isInMergeQueue even when GitHub's GraphQL schema does.
    # Query GraphQL directly so explicit queue membership wins over the transient
    # mergeStateStatus=CLEAN + autoMergeRequest=null surface.
    queue_state="$(gh api graphql \
      -f query='query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){state headRefOid mergeStateStatus autoMergeRequest{enabledAt} isInMergeQueue}}}' \
      -F owner="$QUEUE_OWNER" -F name="$QUEUE_NAME" -F number="$PR" \
      --jq '[.data.repository.pullRequest.state, .data.repository.pullRequest.headRefOid, .data.repository.pullRequest.mergeStateStatus, (if .data.repository.pullRequest.autoMergeRequest == null then "none" else "armed" end), (if .data.repository.pullRequest.isInMergeQueue then "in-queue" else "not-in-queue" end)] | @tsv' \
      2>/dev/null)"
    queue_rc=$?
    if [ "$queue_rc" -ne 0 ] || [ -z "$queue_state" ]; then
      echo "AWAIT-PR $PR: QUEUE-FAILED — cannot observe queued PR state"
      last="QUEUE-OBSERVATION-FAILED"; finish 1
    fi
    state="$(printf '%s\n' "$queue_state" | awk -F '	' '{print $1}')"
    head_now="$(printf '%s\n' "$queue_state" | awk -F '	' '{print $2}')"
    merge_state="$(printf '%s\n' "$queue_state" | awk -F '	' '{print $3}')"
    auto_state="$(printf '%s\n' "$queue_state" | awk -F '	' '{print $4}')"
    queue_membership="$(printf '%s\n' "$queue_state" | awk -F '	' '{print $5}')"
    if [ -z "$head_now" ] || [ "$head_now" != "$queued_head" ]; then
      echo "AWAIT-PR $PR: QUEUE-FAILED — exact head changed (expected $queued_head, got ${head_now:-unknown}); not re-enqueueing"
      last="QUEUE-HEAD-CHANGED"; finish 1
    fi
    if [ "$state" = "MERGED" ]; then
      echo "AWAIT-PR $PR: MERGED (queue, head $queued_head)"
      last="MERGED"; finish 0
    fi
    if [ "$state" != "OPEN" ]; then
      echo "AWAIT-PR $PR: QUEUE-FAILED — PR became $state without merging; not re-enqueueing"
      last="QUEUE-PR-$state"; finish 1
    fi
    if [ "$queue_membership" != "in-queue" ] && [ "$merge_state" != "QUEUED" ] && [ "$auto_state" != "armed" ]; then
      echo "AWAIT-PR $PR: QUEUE-REMOVED — exact head is still open but no queue/auto-merge request remains; not re-enqueueing"
      last="QUEUE-REMOVED"; finish 1
    fi
    last="QUEUED"
    now="$(date +%s)"
    if [ "$now" -ge "$deadline" ]; then
      echo "AWAIT-PR $PR: TIMEOUT after $((now - start))s — exact head $queued_head remains QUEUED"
      echo "  the queue owns continuation; this waiter will not re-enqueue."
      finish 2
    fi
    echo "AWAIT-PR $PR: poll $i — QUEUED (exact head $queued_head; waiting for actual MERGED)"
    sleep "$INTERVAL"
    continue
  fi

  i=$((i + 1))
  out="$("$POLICY" "$PR" "${repo_args[@]+"${repo_args[@]}"}" 2>&1)"; rc=$?
  last="$(printf '%s\n' "$out" | grep -m1 '^VERDICT:' || printf '%s\n' "$out" | tail -1)"
  last="${last#VERDICT: }"
  case "$rc" in
    0)
      echo "AWAIT-PR $PR: CLEARED — $last"
      sha="$(printf '%s\n' "$out" | sed -n 's/^MERGE-HEAD: \([0-9a-f][0-9a-f]*\).*/\1/p' | head -1)"
      mode="$(printf '%s\n' "$out" | awk '/^MERGE-MODE: (queue|direct)$/ {print $2; exit}')"
      if [ "$MERGE" = 1 ]; then
        if [ -z "$sha" ] || [ -z "$mode" ]; then
          echo "AWAIT-PR $PR: MERGE-CMD-FAILED — CLEARED without an exact MERGE-HEAD and MERGE-MODE"
          finish 1
        fi
        if [ "$mode" = "queue" ]; then
          if ! resolve_queue_repo; then
            echo "AWAIT-PR $PR: QUEUE-CMD-FAILED — cannot resolve repository as OWNER/NAME for queue observation"
            last="QUEUE-REPOSITORY-UNRESOLVED"; finish 1
          fi
          if gh pr merge "$PR" "${repo_args[@]+"${repo_args[@]}"}" --auto --match-head-commit "$sha"; then
            queued=1; queued_head="$sha"; last="QUEUED"
            echo "AWAIT-PR $PR: QUEUED (head $sha) — waiting for actual MERGED"
            continue
          fi
          echo "AWAIT-PR $PR: QUEUE-CMD-FAILED — gh pr merge --auto exited non-zero"
          finish 1
        else
          if gh pr merge "$PR" "${repo_args[@]+"${repo_args[@]}"}" --squash --match-head-commit "$sha"; then
            echo "AWAIT-PR $PR: MERGED (squash, head $sha)"
            finish 0
          fi
          echo "AWAIT-PR $PR: MERGE-CMD-FAILED — gh pr merge exited non-zero"
          finish 1
        fi
      fi
      if [ -n "$sha" ] && [ "$mode" = "queue" ]; then
        echo "  enqueue with: gh pr merge $PR${REPO:+ --repo $REPO} --auto --match-head-commit $sha"
      elif [ -n "$sha" ]; then
        echo "  merge with: gh pr merge $PR${REPO:+ --repo $REPO} --squash --match-head-commit $sha"
      fi
      finish 0 ;;
    3)
      echo "AWAIT-PR $PR: FAILED — $last"
      finish 1 ;;
    2)
      case "$out" in
        *"check(s) failing"*)
          echo "AWAIT-PR $PR: FAILED — $last"
          echo "  CI is RED: a failing check needs a fix, not a longer wait."
          finish 1 ;;
      esac ;;
    *)
      echo "AWAIT-PR $PR: FAILED — merge-policy exited $rc unexpectedly: $last"
      finish 1 ;;
  esac
  now="$(date +%s)"
  if [ "$now" -ge "$deadline" ]; then
    echo "AWAIT-PR $PR: TIMEOUT after $((now - start))s — last state: $last"
    echo "  hand off to the beat's merge rung (scripts/merge-drain.py via scripts/drain.sh) and end — never re-arm a loop."
    finish 2
  fi
  echo "AWAIT-PR $PR: poll $i — HOLD ($last)"
  sleep "$INTERVAL"
done
