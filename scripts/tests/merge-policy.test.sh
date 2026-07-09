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
  *"pr view"*"--json"*) cat "$fixture" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$stubdir/gh"

GREEN='[{"name":"python","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"web","status":"COMPLETED","conclusion":"SUCCESS"}]'
FAILING='[{"name":"python","status":"COMPLETED","conclusion":"FAILURE"}]'
PENDING='[{"name":"python","status":"IN_PROGRESS","conclusion":null}]'
NONE='[]'
DOC_FILES='[{"path":"docs/x.md"}]'
WEB_FILES='[{"path":"web/api/main.py"}]'

mkjson() { # state isDraft mss files rollup
  printf '{"number":1,"title":"t","url":"http://x","state":"%s","isDraft":%s,"mergeStateStatus":"%s","baseRefName":"main","headRefName":"f","files":%s,"statusCheckRollup":%s}\n' \
    "$1" "$2" "$3" "$4" "$5" > "$fixture"
}

pass=0; fail=0
check() { # name expected_exit  (fixture already written)
  local name="$1" want="$2" got
  set +e
  PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r >/dev/null 2>&1
  got=$?
  set -e
  if [ "$got" = "$want" ]; then
    printf '  ok   %-34s exit=%s\n' "$name" "$got"; pass=$((pass+1))
  else
    printf '  FAIL %-34s want=%s got=%s\n' "$name" "$want" "$got"; fail=$((fail+1))
  fi
}

echo "merge-policy.sh verdict matrix:"

# CLEARED (exit 0) — only genuinely-mergeable, policy-safe states
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN";  check "clean non-deploy + green"        0
mkjson OPEN false CLEAN "$WEB_FILES" "$GREEN";  check "clean website-sensitive + green" 0
mkjson OPEN false HAS_HOOKS "$DOC_FILES" "$GREEN"; check "has_hooks non-deploy + green" 0

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
mkjson OPEN false UNSTABLE "$WEB_FILES" "$PENDING"; check "website-sensitive + pending" 2
mkjson OPEN false CLEAN    "$WEB_FILES" "$NONE";    check "website-sensitive + 0 checks" 2
mkjson OPEN false UNSTABLE "$DOC_FILES" "$PENDING"; check "non-deploy + pending"        2
mkjson OPEN false WEIRDNEW "$DOC_FILES" "$GREEN";   check "unrecognized state (fail-safe)" 2

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
