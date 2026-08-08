#!/usr/bin/env bash
# Hermetic exit-contract matrix for scripts/check-review-harvest.py — the predicate that asks
# whether a review finding was CONSUMED, not merely received.
#
# WHY THE EXIT CODES ARE THE DELIVERABLE. This predicate runs as an advisory beat sensor, which
# means nobody reads its prose on a green beat — only the code is consumed. So the three states
# have to be distinguishable by exit alone, and one of them is a trap:
#
#   0 + "no findings"   nothing owed
#   1 + findings        merged with a finding unread
#   0 + SKIP            could not look
#
# The trap is the third. "I read nothing" and "I found nothing" both produce zero findings, and a
# count cannot tell them apart (CLAUDE.md, Data Grounding). If SKIP ever printed the green line, an
# expired `gh` token would silently report a clean estate forever. That case is tested first.
#
# HERMETIC: a fake `gh` on PATH serving fixtures. No network, no auth, no real PR. The stub answers
# both surfaces the predicate uses — `gh pr list --json number` and `gh api graphql` — so the whole
# path is exercised, not mocked out at the top.
#
# `set -uo pipefail`, NOT `set -euo pipefail`. This file accumulates failures and reports every
# probe, so `-e` would abort at the first one and hide the rest — the same reason its siblings
# preflight-thread-state.test.sh and outbound-preflight-guard.test.sh omit it. `pipefail` needed one
# real change to be safe: the window assertions used to pipe `run` straight into grep, and this
# predicate exits 1 whenever findings exist, so the pipeline reported failure for a run that behaved
# exactly as intended. Output is captured first now — exit status and printed text are different
# questions and a pipeline was answering both at once.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
PREDICATE="$ROOT/scripts/check-review-harvest.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fails=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

cat > "$TMP/gh" <<'STUB'
#!/usr/bin/env bash
# $GH_MODE selects the fixture. Unset behaves like a broken gh, which is the SKIP path.
case "${GH_MODE:-broken}" in
  broken) exit 1 ;;
esac
# Two distinct GraphQL calls share the `graphql` verb, so dispatch on the query body, not the verb.
for a in "$@"; do
  case "$a" in
    *totalCount*) printf '{"data":{"repository":{"pullRequests":{"totalCount":%s}}}}\n' "${GH_TOTAL:-1}"; exit 0 ;;
    *reviewThreads*) cat "$GH_THREADS"; exit 0 ;;
    # The resolve mutation the predicate PRINTS, executed back against this stub. The echoed query
    # goes out as a PLAIN TEXT line, not a JSON field: the query itself contains double quotes
    # (threadId:"…"), so interpolating it into `{"sent":"%s"}` emitted invalid JSON. Nothing parses
    # it today — the caller greps it — but a stub that emits malformed JSON is a trap primed for the
    # first assertion that does parse it.
    *resolveReviewThread*)
      printf '{"data":{"resolveReviewThread":{"thread":{"isResolved":true}}}}\n'
      printf 'sent: %s\n' "$a"
      exit 0 ;;
  esac
done
# `gh pr list ... --json number`
printf '[{"number":1}]\n'
STUB
chmod +x "$TMP/gh"
export PATH="$TMP:$PATH"

thread() { # thread <resolved> <outdated> <login> <body>
  cat > "$TMP/threads.json" <<JSON
{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[
  {"id":"PRRT_fixture","isResolved":$1,"isOutdated":$2,
   "comments":{"nodes":[{"author":{"login":"$3"},"path":"scripts/x.py","body":"$4"}]}}
]}}}}}
JSON
  export GH_THREADS="$TMP/threads.json"
}

run() { GH_MODE=ok python3 "$PREDICATE" --repo fixture/repo --sample 1 "$@" 2>&1; }

# --- the trap, first and hardest -----------------------------------------------------------------
out="$(GH_MODE=broken python3 "$PREDICATE" --repo fixture/repo --sample 1 2>&1)"; rc=$?
[ "$rc" = "0" ] && printf '%s' "$out" | grep -q "SKIP" \
  && pass "unreadable is SKIP at exit 0, and SAYS skip — never the green line" \
  || fail "unreadable must print SKIP and exit 0 (got rc=$rc: $out)"

printf '%s' "$out" | grep -q "no unresolved agent findings" \
  && fail "SKIP printed the GREEN line — 'I read nothing' is masquerading as 'I found nothing'" \
  || pass "SKIP does not print the green line"

# --- the finding case ----------------------------------------------------------------------------
thread false false "coderabbitai" "Make accepted baseline writes atomic."
out="$(run)"; rc=$?
[ "$rc" = "1" ] && pass "an unresolved agent thread on a merged PR exits 1" \
  || fail "unresolved agent thread must exit 1 (got $rc)"
# THE PRINTED COMMAND IS RUN, not pattern-matched. The gate note and the module docstring both
# promise "the exact command that closes it", and a substring grep for `resolveReviewThread` cannot
# tell a working mutation from a mangled one — which is not hypothetical: a reviewer on #2033 read
# the trailing `}}}` as an unbalanced brace and filed the command as malformed. It is balanced (and
# five real threads were closed with it), but nothing MECHANICAL could settle that. So extract the
# line the predicate emits, strip the `resolve: ` label, and eval it against the stub.
# `[[:space:]]*` rather than literal spaces, and POSIX `head -n 1` rather than the obsolescent
# `head -1`: the extraction should not be the thing that breaks when the predicate reflows its
# indentation or this runs on a stricter head(1).
resolve_cmd="$(printf '%s' "$out" | sed -n 's/^[[:space:]]*resolve:[[:space:]]*//p' | head -n 1)"
[ -n "$resolve_cmd" ] \
  && pass "the finding carries a resolve command" \
  || fail "no resolve command in output"

if [ -n "$resolve_cmd" ]; then
  # GH_MODE is set per-invocation by run(); the stub defaults to `broken`, so the eval must arm it
  # explicitly or this measures the offline path instead of the mutation.
  sent="$(GH_MODE=ok eval "$resolve_cmd" 2>&1)"; rc=$?
  [ "$rc" = "0" ] \
    && pass "the printed command EXECUTES — it is a runnable mutation, not just a matching string" \
    || fail "the printed resolve command failed to execute: $sent"

  printf '%s' "$sent" | grep -q "PRRT_fixture" \
    && pass "the thread id survives into the executed mutation intact" \
    || fail "the executed mutation lost or mangled the thread id: $sent"
fi

# --- what must NOT be a finding ------------------------------------------------------------------
thread true false "coderabbitai" "already dealt with"
run >/dev/null 2>&1 && pass "a RESOLVED thread is not a finding" || fail "resolved thread still flagged"

thread false true "coderabbitai" "the code moved on"
run >/dev/null 2>&1 && pass "an OUTDATED thread decays instead of nagging" || fail "outdated thread still flagged"

thread false false "4444J99" "a human comment"
run >/dev/null 2>&1 && pass "a human's thread is out of scope for this predicate" || fail "human thread flagged"

# --- the [bot] spelling seam ---------------------------------------------------------------------
# AGENT_LOGINS is written in REST spelling (`coderabbitai[bot]`); GraphQL returns the bare login.
# If this seam breaks, the predicate silently finds NOTHING — the worst possible failure for a
# check whose green means "nothing owed".
thread false false "copilot-pull-request-reviewer" "regex label match"
run >/dev/null 2>&1 && fail "GraphQL bare login not matched against REST [bot] spelling — predicate would go silently green" \
  || pass "bare GraphQL login matches the REST [bot] spelling in AGENT_LOGINS"

# --- the sliding window must never truncate silently -----------------------------------------------
# `--sample N` takes the NEWEST N merged PRs, so every merge pushes the oldest out of scope. Observed
# on the live estate: the finding count fell 17 -> 11 while only 5 threads had been resolved, because
# three PRs carrying seven findings aged out underneath it. A number that shrinks because you looked
# at LESS reads exactly like progress. The bound must therefore print on BOTH verdicts, never only
# the red one — a green that does not say what it skipped is the more dangerous of the two.
# Output is CAPTURED, then matched — never `run | grep`. Piping conflates two different questions:
# this predicate exits 1 whenever findings exist, which is the expected state for half these cases,
# so under `pipefail` the pipeline reports failure for a run that behaved perfectly. Separating them
# is what lets this file carry `pipefail` at all (see the header).
thread false false "coderabbitai" "still open"
out="$(GH_TOTAL=1394 run)"
printf '%s' "$out" | grep -q "1393 older NOT sampled" \
  && pass "a red run reports how many merged PRs were NOT sampled" \
  || fail "red run does not report the unsampled remainder"

thread true false "coderabbitai" "resolved"
out="$(GH_TOTAL=1394 run)"
printf '%s' "$out" | grep -q "1393 older NOT sampled" \
  && pass "a GREEN run reports the unsampled remainder too" \
  || fail "green run hides the window — 'no findings' would read as 'nothing owed anywhere'"

thread true false "coderabbitai" "resolved"
out="$(GH_TOTAL=1 run)"
printf '%s' "$out" | grep -q "coverage is total" \
  && pass "when the window covers every merged PR it says so, rather than naming a remainder of 0" \
  || fail "full coverage is not distinguished from a truncated sweep"

# The remainder must come from an exact aggregate, not a capped list walk. The first version counted
# `pr list --limit 1000` and reported "990 older" on a repo with 1394 merged PRs — a truncation
# reporter truncated by its own cap, and the understated figure looked entirely plausible.
# Matched on the argv token as Python spells it, not on prose: the docstring above deliberately
# NAMES the old `pr list --limit 1000` so the trap is recorded, and a looser pattern would flag that
# explanation as the defect it warns about.
grep -q '"--limit", "1000"' "$PREDICATE" \
  && fail "the unsampled remainder is derived from a capped list walk — it will understate on a large repo" \
  || pass "the remainder comes from an exact totalCount, not a capped list"

grep -q "totalCount" "$PREDICATE" \
  && pass "the exact merged total is queried as an aggregate" \
  || fail "no totalCount query — the remainder cannot be exact"

# --- reuse, not a copy ---------------------------------------------------------------------------
grep -q "check-review-engine.py" "$PREDICATE" \
  && pass "AGENT_LOGINS is imported from check-review-engine.py, not duplicated" \
  || fail "AGENT_LOGINS appears to be copied — the two organs can now disagree about what an agent is"

printf '\ncheck-review-harvest: %d failure(s)\n' "$fails"
[ "$fails" -eq 0 ]
