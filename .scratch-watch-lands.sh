#!/bin/bash
# Observation-only: emit one line per terminal state of PRs 1892 (G) and 1907 (rail),
# plus one line if either dispatched pr-gate run ends non-success (incident kill signature).
g_done=""
r_done=""
run1_done=""
run2_done=""
while true; do
  if [ -z "$g_done" ]; then
    s=$(gh pr view 1892 --repo organvm/limen --json state --jq '.state' 2>/dev/null || echo POLL-FAIL)
    if [ "$s" = "MERGED" ]; then echo "G-1892-MERGED"; g_done=1; fi
    if [ "$s" = "CLOSED" ]; then echo "G-1892-CLOSED-UNMERGED"; g_done=1; fi
  fi
  if [ -z "$r_done" ]; then
    s=$(gh pr view 1907 --repo organvm/limen --json state --jq '.state' 2>/dev/null || echo POLL-FAIL)
    if [ "$s" = "MERGED" ]; then echo "RAIL-1907-MERGED"; r_done=1; fi
    if [ "$s" = "CLOSED" ]; then echo "RAIL-1907-CLOSED-UNMERGED"; r_done=1; fi
  fi
  if [ -z "$run1_done" ]; then
    c=$(gh run view 31129073800 --repo organvm/limen --json status,conclusion --jq '"\(.status):\(.conclusion)"' 2>/dev/null || echo poll-fail)
    case "$c" in
      completed:success) run1_done=1;;
      completed:*) echo "G-PRGATE-RUN-31129073800 $c"; run1_done=1;;
    esac
  fi
  if [ -z "$run2_done" ]; then
    c=$(gh run view 31129006111 --repo organvm/limen --json status,conclusion --jq '"\(.status):\(.conclusion)"' 2>/dev/null || echo poll-fail)
    case "$c" in
      completed:success) run2_done=1;;
      completed:*) echo "RAIL-PRGATE-RUN-31129006111 $c"; run2_done=1;;
    esac
  fi
  if [ -n "$g_done" ] && [ -n "$r_done" ]; then exit 0; fi
  sleep 60
done
