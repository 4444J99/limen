#!/usr/bin/env bash
# Hermetic deny/pass matrix for scripts/hooks/no-hand-poll-guard.sh. The NEGATIVE cases are
# the deliverable: the guard exists to kill hand-rolled PR poll loops without ever blocking
# the sanctioned waiter, bounded retries, build sleeps, or multi-PR iteration.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$ROOT/scripts/hooks/no-hand-poll-guard.sh"

payload() { python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]},"cwd":"/tmp"}))' "$1"; }
decision() { payload "$1" | "$HOOK"; }

assert_denied() { local out; out="$(decision "$1")"
  printf '%s' "$out" | grep -q '"permissionDecision":"deny"' || { printf 'expected deny: %s\nout: %s\n' "$1" "$out" >&2; exit 1; }; }
assert_passes() { local out; out="$(decision "$1")"
  [ -z "$out" ] || { printf 'expected silent pass: %s\nout: %s\n' "$1" "$out" >&2; exit 1; }; }

# THE banned shape — loop + gh state probe + sleep in one command string
assert_denied 'for i in $(seq 60); do gh pr checks 1872; sleep 30; done'
assert_denied 'while ! gh pr view 1 --json state -q .state | grep -q MERGED; do sleep 10; done'
assert_denied 'until gh pr view 1842 --json mergedAt -q .mergedAt | grep -qv null; do sleep 60; done'
assert_denied 'while true; do gh run view 123; sleep 5; done'
assert_denied 'while :; do gh api repos/o/r/pulls/7; sleep 15; done'
assert_denied '(while true; do gh pr checks 9; sleep 20; done) &'

# Legitimate lanes — must never block (the deliverable)
assert_passes 'scripts/await-pr.sh 1872 --merge'                       # the sanctioned waiter
assert_passes 'bash scripts/await-pr.sh 1879 --merge'
assert_passes 'sleep 5'                                                # bare sleep
assert_passes 'gh pr view 1872 --json state'                           # bare probe
assert_passes 'gh pr checks 1872'
assert_passes 'for pr in 1 2 3; do gh pr view $pr; done'               # iteration, no sleep
assert_passes 'while ! curl -sf localhost:8080/health; do sleep 2; done'  # sleep loop, no gh
assert_passes 'npm run build && sleep 2 && npm run check'              # build wait
assert_passes 'echo "while gh pr sleep done"'                          # tokens without the shape
assert_passes 'git log --grep "sleep"'                                 # prefilter tail
assert_passes 'ls -la'                                                 # no sleep token at all

# Escape hatch
out="$(payload 'while true; do gh pr checks 9; sleep 20; done' | LIMEN_ALLOW_PR_POLL=1 "$HOOK")"
[ -z "$out" ] || { printf 'expected escape hatch to pass\nout: %s\n' "$out" >&2; exit 1; }

# Fail-open: undecodable payload exits 0 silently
out="$(printf 'not-json' | "$HOOK")"
[ -z "$out" ] || { printf 'expected fail-open on bad payload\nout: %s\n' "$out" >&2; exit 1; }

echo "no-hand-poll-guard.test: OK (6 deny, 11 pass, hatch + fail-open)"
