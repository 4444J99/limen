#!/usr/bin/env bash
# Hermetic deny/pass matrix for scripts/hooks/no-hand-poll-guard.sh. The NEGATIVE cases are
# the deliverable: the guard kills retired synchronous waiters and hand-rolled PR poll loops
# without blocking bounded retries, build sleeps, or multi-PR iteration.
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

# The retired compatibility path is mechanically denied even before its own fail-closed exit.
assert_denied 'scripts/await-pr.sh 1872 --merge'
assert_denied 'bash scripts/await-pr.sh 1879 --merge'
assert_denied './scripts/await-pr.sh'
assert_denied 'timeout 60 scripts/await-pr.sh 1'
assert_denied 'env X=1 scripts/await-pr.sh 1'
assert_denied 'nohup scripts/await-pr.sh 1 &'
assert_denied "bash -c 'scripts/await-pr.sh 1'"
assert_denied 'ls x; scripts/await-pr.sh 1'
assert_denied 'cd scripts && ./await-pr.sh 1'
assert_denied $'echo start\nscripts/await-pr.sh 1'                      # second line of a multi-line command
# Wrappers, shells and compound heads (best-effort grammar: the script also exits 64 on its own)
assert_denied '/bin/bash scripts/await-pr.sh 1'
assert_denied '/usr/bin/env bash scripts/await-pr.sh 1'
assert_denied 'bash -o pipefail scripts/await-pr.sh 1'
assert_denied 'sh scripts/await-pr.sh 1'
assert_denied 'source scripts/await-pr.sh 1'
assert_denied '. scripts/await-pr.sh 1'
assert_denied '{ scripts/await-pr.sh 1; }'
assert_denied 'if scripts/await-pr.sh 1; then echo ok; fi'
assert_denied 'while scripts/await-pr.sh 1; do :; done'
assert_denied 'for i in 1 2; do scripts/await-pr.sh $i; done'
assert_denied 'env -i scripts/await-pr.sh 1'
assert_denied 'env -u SOME_VAR scripts/await-pr.sh 1'
assert_denied 'nice -n 10 scripts/await-pr.sh 1'
assert_denied 'timeout -s KILL 60 scripts/await-pr.sh 1'
assert_denied 'timeout --foreground 60 scripts/await-pr.sh 1'
assert_denied 'sudo -u root scripts/await-pr.sh 1'
assert_denied 'setsid -f scripts/await-pr.sh 1'
assert_denied 'xargs -I{} scripts/await-pr.sh {}'
assert_denied 'exec scripts/await-pr.sh 1'
assert_denied 'time scripts/await-pr.sh 1'
assert_denied 'x=1 y=2 scripts/await-pr.sh 1'
assert_denied 'nohup nice -n 5 scripts/await-pr.sh 1 &'
assert_denied 'eval "scripts/await-pr.sh 1"'
assert_denied "bash -c 'nohup scripts/await-pr.sh 1 &'"
assert_denied 'echo a | scripts/await-pr.sh 1'
assert_denied 'scripts/await-pr.sh;'
assert_denied 'scripts/await-pr.sh|cat'

# Legitimate lanes — must never block (the deliverable)
assert_passes 'scripts/merge-drain.py --repo o/r --pr 7 --expected-head aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
assert_passes 'sleep 5'                                                # bare sleep
assert_passes 'gh pr view 1872 --json state'                           # bare probe
assert_passes 'gh pr checks 1872'
assert_passes 'for pr in 1 2 3; do gh pr view $pr; done'               # iteration, no sleep
assert_passes 'while ! curl -sf localhost:8080/health; do sleep 2; done'  # sleep loop, no gh
assert_passes 'npm run build && sleep 2 && npm run check'              # build wait
assert_passes 'echo "while gh pr sleep done"'                          # tokens without the shape
assert_passes 'git log --grep "sleep"'                                 # prefilter tail
assert_passes 'ls -la'                                                 # no sleep token at all

# Mentioning the retired waiter is not invoking it — read-only diagnostics, edits and prose must pass
assert_passes 'ls scripts/await-pr.sh'
assert_passes 'ls scripts | grep await-pr.sh'
assert_passes 'grep -n await-pr.sh CLAUDE.md'
assert_passes 'git log --oneline -- scripts/await-pr.sh'
assert_passes 'cat scripts/await-pr.sh'
assert_passes "git commit -m 'retire await-pr.sh waiter'"
assert_passes 'gh pr create --title t --body "never use scripts/await-pr.sh"'
assert_passes $'cat <<EOF\nsee scripts/await-pr.sh for the retired path\nEOF'   # heredoc prose
# Quoted / backticked / parenthesised / alternation mentions in commit, PR and doc text must pass
assert_passes "git commit -m 'retire \`scripts/await-pr.sh\` waiter'"
assert_passes "gh pr create --body 'Retires the waiter (scripts/await-pr.sh).'"
assert_passes "grep -rnE 'merge-drain|await-pr.sh' docs/"
assert_passes "git log --grep='merge-drain|await-pr.sh'"
assert_passes 'x=$(cat scripts/await-pr.sh)'
assert_passes "git commit -m 'x && scripts/await-pr.sh'"
assert_passes 'echo "a|await-pr.sh"'
assert_passes $'cat >> AGENTS.md <<\'EOF\'\n| \`await-pr.sh\` | retired |\nEOF'   # backticked table cell in a doc patch
assert_passes 'bash -n scripts/await-pr.sh'                                       # syntax check, not a run
assert_passes 'scripts/await-pr.sh --help'                                        # documented to exit 0
assert_passes 'scripts/await-pr.sh.bak'                                           # a different file
assert_passes 'scripts/await-pr.sh-old'

# Linear time: separator / newline / wrapper runs once made the matcher cubic or exponential (200 KB hung it)
for unit in ';' $'\n' '(' 'env -a ' 'x=1 ' 'timeout 1 '; do
  big="$(python3 -c 'import json,sys; u=sys.argv[1]; print(json.dumps({"tool_input":{"command":(u*(100000//len(u)+1))[:100000]+" sleep 1"},"cwd":"/tmp"}))' "$unit")"
  out="$(printf '%s' "$big" | timeout 30 "$HOOK")" || { printf 'hook hung or failed on a 100 KB run of %q\n' "$unit" >&2; exit 1; }
  [ -z "$out" ] || { printf 'unexpected output on a 100 KB run of %q: %s\n' "$unit" "$out" >&2; exit 1; }
done

# Escape hatch
out="$(payload 'while true; do gh pr checks 9; sleep 20; done' | LIMEN_ALLOW_PR_POLL=1 "$HOOK")"
[ -z "$out" ] || { printf 'expected escape hatch to pass\nout: %s\n' "$out" >&2; exit 1; }
out="$(payload 'scripts/await-pr.sh 9 --merge' | LIMEN_ALLOW_PR_POLL=1 "$HOOK")"
printf '%s' "$out" | grep -q '"permissionDecision":"deny"' || { printf 'retired waiter escaped hatch\n' >&2; exit 1; }

# Fail-open: undecodable payload exits 0 silently
out="$(printf 'not-json' | "$HOOK")"
[ -z "$out" ] || { printf 'expected fail-open on bad payload\nout: %s\n' "$out" >&2; exit 1; }

echo "no-hand-poll-guard.test: OK (43 deny, 30 pass, linear-time runs, bounded hatch + fail-open)"
