#!/usr/bin/env bash
# done-jules-lane.sh — predicate: the jules conductor lane dispatches AUTONOMOUSLY and the
# dispatch->harvest loop closes. The bug this guards forever: `jules new` routes through the
# web-UI plan-approval flow, stranding every headless dispatch at "Awaiting User Feedback" — and
# the jules CLI has NO approve/reply verb, so a stalled session is unrecoverable. The fix dispatches
# via `jules remote new` (autonomous VM), leads the prompt with a hard "do NOT ask for feedback"
# directive, and captures the session id from stdout into dispatch_log so harvest matches by id,
# never the truncated/directive-led session title.
#
# Exit 0 <=> all four wiring invariants hold AND the jules-lane unit tests pass. Tests the checkout
# this script lives in (not $LIMEN_ROOT), so it is correct inside a worktree.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || { echo "FAIL: cannot cd to repo root"; exit 1; }
D="cli/src/limen/dispatch.py"
fail() { echo "FAIL: $*"; exit 1; }

# 1. dispatch uses `jules remote new` (autonomous), feeding the task via --session
grep -Fq '"remote", "new", "--repo", repo, "--session"' "$D" \
  || fail "_call_jules must dispatch via: jules remote new --repo <r> --session <prompt>"

# 2. the stale stranding call is GONE (would route through the web plan-approval flow)
grep -Fq '"new", "--repo", repo, prompt]' "$D" \
  && fail "stale 'jules new' positional dispatch still present (strands at Awaiting User Feedback)"

# 3. every jules prompt leads with the hard anti-stall directive
grep -Fq 'Do NOT ask for feedback or approval' "$D" \
  || fail "jules anti-stall directive missing"

# 4. the session id is captured from `jules remote new` stdout (ID: line) -> durable harvest match
grep -Fq 'ID:\s*(\d{6,})' "$D" \
  || fail "session-id capture (ID: line) missing — harvest would have no durable match key"

# 5. the jules-lane unit tests pass
log="$(mktemp)"
if ! PYTHONPATH=cli/src python3 -m pytest cli/tests/test_flame_kernel.py -q \
     -k "jules or session_id" >"$log" 2>&1; then
  cat "$log"; rm -f "$log"; fail "jules-lane unit tests"
fi
rm -f "$log"

echo "jules-lane verification passed"
