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
set -u

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
for a in "$@"; do
  if [ "$a" = "graphql" ]; then cat "$GH_THREADS"; exit 0; fi
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
printf '%s' "$out" | grep -q "resolveReviewThread" \
  && pass "the finding carries the exact command that closes it" \
  || fail "no resolve command in output"

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

# --- reuse, not a copy ---------------------------------------------------------------------------
grep -q "check-review-engine.py" "$PREDICATE" \
  && pass "AGENT_LOGINS is imported from check-review-engine.py, not duplicated" \
  || fail "AGENT_LOGINS appears to be copied — the two organs can now disagree about what an agent is"

printf '\ncheck-review-harvest: %d failure(s)\n' "$fails"
[ "$fails" -eq 0 ]
