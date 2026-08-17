#!/bin/bash
# Observation-only: emit the terminal conclusion of the rerun of pr-gate run 31129073800.
while true; do
  c=$(gh run view 31129073800 --repo organvm/limen --json status,conclusion --jq '"\(.status):\(.conclusion)"' 2>/dev/null || echo poll-fail)
  case "$c" in
    completed:success) echo "G-PRGATE-RERUN-SUCCESS"; exit 0;;
    completed:*) echo "G-PRGATE-RERUN-TERMINAL $c"; exit 0;;
  esac
  sleep 60
done
