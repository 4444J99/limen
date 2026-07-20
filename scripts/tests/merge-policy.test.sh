#!/usr/bin/env bash
# merge-policy.test.sh — regression test for scripts/merge-policy.sh
#
# The predicate must NEVER return CLEARED (exit 0) on a state GitHub won't actually merge, or on
# an indeterminate state. This test stubs `gh` with canned PR JSON and asserts the exit code for
# every mergeStateStatus, the closed-PR guard, the website-sensitive gate, and the failing/pending
# paths. Deterministic + idempotent: exit 0 ⟺ all cases pass.
#
# Guards two real bugs found 2026-06-24:
#   - mss=BLOCKED (required check not run on a pre-existing PR) was wrongly CLEARED.
#   - mss=UNKNOWN (GitHub still computing mergeability) was wrongly CLEARED.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
policy="$here/../merge-policy.sh"
[ -f "$policy" ] || { echo "FAIL: cannot find merge-policy.sh at $policy" >&2; exit 1; }

# --- stub `gh` so the predicate reads our fixture instead of the network ---
stubdir="$(mktemp -d)"
fixture="$stubdir/pr.json"
trap 'rm -rf "$stubdir"' EXIT
cat > "$stubdir/gh" <<STUB
#!/usr/bin/env bash
# fake gh: emit the current fixture for any 'pr view ... --json ...' call.
case "\$*" in
  *"api graphql"*)
    case "\${GH_QUEUE_CAPABILITY:-unknown}" in
      active) printf '%s\n' '{"data":{"repository":{"mergeQueue":{"id":"MQ_fixture"}}}}' ;;
      absent) printf '%s\n' '{"data":{"repository":{"mergeQueue":null}}}' ;;
      unknown) printf '%s\n' '{"errors":[{"message":"field unavailable"}]}'; exit 1 ;;
      *) exit 1 ;;
    esac ;;
  *"pr view"*"--json headRefOid"*"-q .headRefOid"*)
    if [ -n "\${GH_RECHECK_HEAD:-}" ]; then printf '%s\n' "\$GH_RECHECK_HEAD"; else jq -r .headRefOid "$fixture"; fi ;;
  *"pr view"*"--json"*) cat "$fixture" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$stubdir/gh"

GREEN='[{"name":"python","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"web","status":"COMPLETED","conclusion":"SUCCESS"}]'
FAILING='[{"name":"python","status":"COMPLETED","conclusion":"FAILURE"}]'
PENDING='[{"name":"python","status":"IN_PROGRESS","conclusion":null}]'
NONE='[]'
# Dedupe fixtures: GitHub attaches every re-run of a check to the same commit, so the rollup can
# carry a stale run AND a fresh run of the same check name. The predicate must judge by the LATEST
# run per name (recency by completedAt/startedAt), matching GitHub's own mergeability.
SUPERSEDED_OK='[{"name":"review","status":"COMPLETED","conclusion":"CANCELLED","startedAt":"2026-07-18T00:00:00Z"},{"name":"review","status":"COMPLETED","conclusion":"SUCCESS","startedAt":"2026-07-18T05:00:00Z"},{"name":"python","status":"COMPLETED","conclusion":"SUCCESS","startedAt":"2026-07-18T00:00:00Z"}]'
DUP_LATEST_FAIL='[{"name":"review","status":"COMPLETED","conclusion":"SUCCESS","startedAt":"2026-07-18T00:00:00Z"},{"name":"review","status":"COMPLETED","conclusion":"FAILURE","startedAt":"2026-07-18T05:00:00Z"},{"name":"python","status":"COMPLETED","conclusion":"SUCCESS","startedAt":"2026-07-18T00:00:00Z"}]'
DOC_FILES='[{"path":"docs/x.md"}]'
WEB_FILES='[{"path":"web/api/main.py"}]'

mkjson() { # state isDraft mss files rollup
  printf '{"number":1,"title":"t","url":"http://x","state":"%s","isDraft":%s,"mergeStateStatus":"%s","baseRefName":"main","headRefName":"f","headRefOid":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","files":%s,"statusCheckRollup":%s}\n' \
    "$1" "$2" "$3" "$4" "$5" > "$fixture"
}

pass=0; fail=0
check() { # name expected_exit [extra policy args...]  (fixture already written)
  local name="$1" want="$2" got
  shift 2
  set +e
  PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r "$@" >/dev/null 2>&1
  got=$?
  set -e
  if [ "$got" = "$want" ]; then
    printf '  ok   %-34s exit=%s\n' "$name" "$got"; pass=$((pass+1))
  else
    printf '  FAIL %-34s want=%s got=%s\n' "$name" "$want" "$got"; fail=$((fail+1))
  fi
}

check_output() { # name expected_exit required_substring [forbidden_substring]
  local name="$1" want="$2" required="$3" forbidden="${4:-}" got out
  set +e
  out=$(PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r 2>&1)
  got=$?
  set -e
  if [ "$got" = "$want" ] && [[ "$out" == *"$required"* ]] \
      && { [ -z "$forbidden" ] || [[ "$out" != *"$forbidden"* ]]; }; then
    printf '  ok   %-34s exit=%s\n' "$name" "$got"; pass=$((pass+1))
  else
    printf '  FAIL %-34s want=%s got=%s required=%q forbidden=%q\n' \
      "$name" "$want" "$got" "$required" "$forbidden"
    printf '%s\n' "$out" | sed 's/^/       /'
    fail=$((fail+1))
  fi
}

echo "merge-policy.sh verdict matrix:"

# CLEARED (exit 0) — only genuinely-mergeable, policy-safe states
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check_output "clean non-deploy + green" 0 "MERGE-MODE: direct"
mkjson OPEN false CLEAN "$WEB_FILES" "$GREEN"
check_output "clean website-sensitive + green" 0 "MERGE-MODE: direct"
mkjson OPEN false HAS_HOOKS "$DOC_FILES" "$GREEN"; check "has_hooks non-deploy + green" 0
mkjson OPEN false CLEAN "$DOC_FILES" "$SUPERSEDED_OK"; check "superseded CANCELLED, latest SUCCESS" 0

# BLOCKED (exit 3) — GitHub itself refuses the merge
mkjson OPEN false DIRTY   "$DOC_FILES" "$GREEN"; check "DIRTY (conflicts)"              3
mkjson OPEN false BEHIND  "$DOC_FILES" "$GREEN"; check "BEHIND (stale base)"            3
mkjson OPEN false BLOCKED "$WEB_FILES" "$GREEN"; check "BLOCKED, no pending (stuck)"     3   # bug #1
mkjson MERGED false CLEAN "$DOC_FILES" "$GREEN"; check "MERGED (closed-PR guard)"       3
mkjson CLOSED false CLEAN "$DOC_FILES" "$GREEN"; check "CLOSED (closed-PR guard)"       3

# HOLD (exit 2) — mergeable per GitHub but not yet safe / indeterminate
mkjson OPEN false UNKNOWN  "$DOC_FILES" "$GREEN";   check "UNKNOWN (still computing)"   2   # bug #2
mkjson OPEN false BLOCKED  "$WEB_FILES" "$PENDING"; check "BLOCKED + pending (wait)"    2
mkjson OPEN true  CLEAN    "$DOC_FILES" "$GREEN";   check "DRAFT"                        2
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"; check "failing check"               2
mkjson OPEN false UNSTABLE "$DOC_FILES" "$DUP_LATEST_FAIL"; check "dup check, latest FAILURE (not masked)" 2
mkjson OPEN false UNSTABLE "$WEB_FILES" "$PENDING"; check "website-sensitive + pending" 2
mkjson OPEN false CLEAN    "$WEB_FILES" "$NONE";    check "website-sensitive + 0 checks" 2
mkjson OPEN false UNSTABLE "$DOC_FILES" "$PENDING"; check "non-deploy + pending"        2
mkjson OPEN false WEIRDNEW "$DOC_FILES" "$GREEN";   check "unrecognized state (fail-safe)" 2

# Queue routing is enabled only by a positive live GraphQL capability. BEHIND stays blocked when
# the queue is absent or unverifiable; active queues accept exact-head-green BEHIND/CLEAN PRs only
# as queue work (never as a direct merge).
export GH_QUEUE_CAPABILITY=active
mkjson OPEN false BEHIND "$DOC_FILES" "$GREEN"
check_output "active queue + BEHIND + green" 0 "MERGE-MODE: queue" "Safe to self-merge"
check_output "active queue binds exact head" 0 \
  "MERGE-HEAD: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check_output "active queue + CLEAN + green" 0 "MERGE-MODE: queue"
mkjson OPEN false BEHIND "$DOC_FILES" "$PENDING"
check_output "active queue + BEHIND pending" 2 "VERDICT: HOLD"
mkjson OPEN false DIRTY "$DOC_FILES" "$GREEN"
check_output "active queue + DIRTY" 3 "VERDICT: BLOCKED"

export GH_QUEUE_CAPABILITY=absent
mkjson OPEN false BEHIND "$DOC_FILES" "$GREEN"
check_output "absent queue + BEHIND" 3 "merge queue capability is absent"
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check_output "absent queue + CLEAN" 0 "MERGE-MODE: direct" "MERGE-MODE: queue"

export GH_QUEUE_CAPABILITY=unknown
mkjson OPEN false BEHIND "$DOC_FILES" "$GREEN"
check_output "unknown queue + BEHIND" 3 "merge queue capability is unknown"
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check_output "unknown queue + CLEAN" 0 "MERGE-MODE: direct" "MERGE-MODE: queue"
unset GH_QUEUE_CAPABILITY

# The check rollup must remain attached to the exact head captured in the first PR snapshot.
export GH_RECHECK_HEAD=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"; check "head changed during predicate" 2
unset GH_RECHECK_HEAD
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
jq '.headRefOid = ""' "$fixture" > "$fixture.tmp" && mv "$fixture.tmp" "$fixture"
check "head identity unavailable" 2
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check "expected head mismatch" 2 --expected-head bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

# Resolver unavailable ⇒ website-sensitive (fail toward caution). With a broken python3 the
# deploy regex cannot derive from the GATES registry, so a docs-only PR with zero checks —
# normally CLEARED — must HOLD instead of risking an unclassified live deploy.
cat > "$stubdir/python3" <<'STUB'
#!/usr/bin/env bash
exit 1
STUB
chmod +x "$stubdir/python3"
mkjson OPEN false CLEAN "$DOC_FILES" "$NONE"; check "resolver unavailable (forced sensitive)" 2
rm -f "$stubdir/python3"

echo
echo "passed=$pass failed=$fail"
if [ "$fail" -eq 0 ]; then
  echo "merge-policy regression test PASSED"; exit 0
else
  echo "merge-policy regression test FAILED"; exit 1
fi
