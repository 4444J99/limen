#!/usr/bin/env bash
# Exit-contract test for the loop-body self-load guard in scripts/heartbeat-loop.sh.
#
# WHAT IS UNDER TEST: the single line that decides whether the heartbeat's launchd job exists. That
# decision is not cosmetic. When it answers TRUE the rung kickstarts and returns; when it answers
# FALSE the else-branch clears logs/.loop-update-pending. So a FALSE POSITIVE — some other job
# satisfying the check — takes the true branch, never clears the marker, and turns a rung whose own
# header promises "SELF-LIMITING FOR FREE ... the restart destroys its own trigger" into one that
# retries every beat forever. The failure is a permanent loop, not a one-off stray kickstart.
#
# THE ORIGINAL WAS WRONG TWICE. `launchctl list | grep -q "$label"`:
#   1. treats the label as a REGEX, and the default `com.limen.heartbeat` is mostly dots — so the
#      pattern matches the literal string `comXlimenXheartbeat`;
#   2. matches as a SUBSTRING, so even the obvious `grep -F` patch still says yes to a different
#      job named `com.limen.heartbeat-loop`.
# Case 2 is why this file exists rather than a one-word fix: the fixed-string repair looks correct
# and is not.
#
# IT TESTS THE SHIPPED LINE, NOT A COPY. The condition is extracted from heartbeat-loop.sh at run
# time and evaluated against a stub `launchctl`. A test that re-typed the expression would keep
# passing after the real line regressed, which is the whole failure mode being guarded here.
#
# HERMETIC: a fake `launchctl` on PATH. No launchd, no real jobs, nothing kickstarted.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
LOOP="$ROOT/scripts/heartbeat-loop.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fails=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

# The stub answers only for labels in FAKE_LABELS, exactly as `launchctl list <label>` does: exit 0
# when the job exists, non-zero when it does not. With no argument it prints the PID/Status/Label
# table, so a regressed grep-the-table implementation still runs and still gets its wrong answer —
# the test must be able to observe the OLD behavior, not error out on it.
cat > "$TMP/launchctl" <<'STUB'
#!/usr/bin/env bash
if [ "$#" -eq 0 ] || [ "$1" != "list" ]; then exit 0; fi
if [ "$#" -ge 2 ]; then
  for l in $FAKE_LABELS; do [ "$l" = "$2" ] && exit 0; done
  exit 113
fi
for l in $FAKE_LABELS; do printf -- '-\t0\t%s\n' "$l"; done
STUB
chmod +x "$TMP/launchctl"
export PATH="$TMP:$PATH"

# Pull the real condition out of the shipped script. One line, matched by its distinctive head.
CONDITION="$(grep -n 'if launchctl list' "$LOOP" | head -1 | cut -d: -f2- | sed 's/^ *//; s/^if //; s/; then$//')"
if [ -z "$CONDITION" ]; then
  fail "could not extract the guard condition from heartbeat-loop.sh (did the line change shape?)"
  printf '\nheartbeat-kickstart-guard: %d failure(s)\n' "$fails"
  exit 1
fi
printf 'guard under test: %s\n' "$CONDITION"

# probe <name> <expected 0|1> <label-to-look-for> <labels-launchd-actually-has>
probe() {
  local name="$1" expected="$2" _kick_label="$3"
  export FAKE_LABELS="$4"
  local got=0
  eval "$CONDITION" >/dev/null 2>&1 || got=1
  if [ "$got" = "$expected" ]; then pass "$name"; else
    fail "$name (expected $expected, got $got; label=$_kick_label labels='$4')"
  fi
}

probe "the real label is found when launchd has it" \
  0 "com.limen.heartbeat" "com.limen.heartbeat com.limen.creds-hydrate"

probe "an absent label is reported absent, so the stale marker gets cleared" \
  1 "com.limen.heartbeat" "com.limen.creds-hydrate"

# The two regressions. Both of these passed the original implementation.
probe "dots are not wildcards: comXlimenXheartbeat must NOT satisfy com.limen.heartbeat" \
  1 "com.limen.heartbeat" "comXlimenXheartbeat"

probe "a longer label is a DIFFERENT job: heartbeat-loop must NOT satisfy heartbeat" \
  1 "com.limen.heartbeat" "com.limen.heartbeat-loop"

probe "a custom LIMEN_HEARTBEAT_LABEL is honoured exactly" \
  0 "com.example.beat" "com.example.beat"

printf '\nheartbeat-kickstart-guard: %d failure(s)\n' "$fails"
[ "$fails" -eq 0 ]
