#!/bin/bash
# Observation-only: emit one line when PR #1892 (G) reaches a terminal/actionable state.
while true; do
  s=$(gh pr view 1892 --repo organvm/limen --json state --jq '.state' 2>/dev/null || echo POLL-FAIL)
  if [ "$s" = "MERGED" ]; then echo "G-1892-MERGED"; break; fi
  if [ "$s" = "CLOSED" ]; then echo "G-1892-CLOSED-UNMERGED"; break; fi
  q=$(gh api graphql -f query='{repository(owner:"organvm",name:"limen"){mergeQueue(branch:"main"){entries(first:12){nodes{state pullRequest{number}}}}}}' --jq '[.data.repository.mergeQueue.entries.nodes[] | "\(.pullRequest.number):\(.state)"] | join(" ")' 2>/dev/null || echo "")
  case "$q" in *"1892:UNMERGEABLE"*) echo "G-1892-UNMERGEABLE-IN-QUEUE $q"; break;; esac
  if [ -n "$q" ] && ! printf '%s' "$q" | grep -q "1892:"; then echo "G-1892-GONE-FROM-QUEUE queue=$q state=$s"; break; fi
  sleep 60
done
