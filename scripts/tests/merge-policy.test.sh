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
  *"pr checks"*"--required"*)
    # required-set derivation: emit the canned required checks, or fail like an older
    # gh / API hiccup so the predicate falls back to all-checks counting.
    if [ -n "\${GH_REQUIRED_CHECKS:-}" ]; then printf '%s\n' "\$GH_REQUIRED_CHECKS"; else exit 1; fi ;;
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
# An ARMED rail. This was web/api/main.py until the arming axis landed, at which point every
# "website-sensitive" case below quietly became a non-deploy case — and two of them kept
# passing, because they assert merge MODE rather than classification. A fixture that stops
# meaning what its name says is the failure that does not announce itself, so this points at
# the dashboard rail, which genuinely deploys (CLOUDFLARE_API_TOKEN is set and its Pages step
# executes on every main push).
WEB_FILES='[{"path":"web/app/app/page.tsx"}]'
# The api deploy builds `--source web/api` and its Dockerfile COPYs four files; nothing under
# cli/ reaches the image. `cli/**` sat in deploy-api.yml from the original buildout until
# 2026-08-05, so every cli PR — including a test-only one — was classified WEBSITE-SENSITIVE
# and made to wait on a FULL green rollup for a deploy that could not happen.
CLI_FILES='[{"path":"cli/tests/test_notify_gate_estate.py"},{"path":"cli/src/limen/dispatch.py"}]'
# web/api IS the api rail's build_source — the strongest case for the arming axis. Even the
# path the deploy job literally builds cannot be website-sensitive while the rail is dormant.
API_FILES='[{"path":"web/api/main.py"}]'

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
# Pins the CLASSIFICATION, not just the verdict. Without this the fixture can drift to a
# non-deploy path and every website-sensitive case below keeps passing while testing nothing.
check_output "website-sensitive fixture really is sensitive" 0 "WEBSITE-SENSITIVE"
# The flip the previous revision predicted — reached by a different road than expected. It
# assumed `cli/**` had to leave deploy-api.yml, which needs a workflow-scoped push this fleet
# does not hold. But path membership was only half the question: the api rail is DORMANT
# (GCP_SA_KEY exists nowhere, so every effect-bearing step skips and the run goes green having
# deployed nothing), and a rail that cannot deploy cannot make any path website-sensitive.
# So `cli/**` stays in the workflow, check C keeps its byte-parity, and the misclassification
# is gone anyway. Both of these are now proof the guardrail asks "will merging change what is
# served?" rather than "does this glob match?" — see gates.yaml deploy_triggers.api.arming,
# proven by check-gates K.
mkjson OPEN false CLEAN "$CLI_FILES" "$GREEN"
check_output "cli-only non-deploy (api rail dormant)" 0 "non-deploy — merging will NOT trigger"
mkjson OPEN false CLEAN "$API_FILES" "$GREEN"
check_output "web/api-only non-deploy (api rail dormant)" 0 "non-deploy — merging will NOT trigger"
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

# Required-vs-advisory discrimination (2026-07-24 insights lineage): with a derivable
# required set, NON-DEPLOY verdicts count required checks only — advisory checks are
# reported, never blocking. Website-sensitive PRs still demand the FULL rollup green
# (merging IS the deploy). No GH_REQUIRED_CHECKS in the env ⇒ the stub fails the call
# and every case above already exercises the all-checks fallback.
export GH_REQUIRED_CHECKS='[{"name":"pr-gate","state":"SUCCESS","bucket":"pass"}]'
mkjson OPEN false UNSTABLE "$DOC_FILES" "$PENDING"
check_output "non-deploy: advisory pending, req green" 0 "MERGE-MODE: direct"
mkjson OPEN false UNSTABLE "$DOC_FILES" "$DUP_LATEST_FAIL"
check "non-deploy: advisory failing, req green" 0
mkjson OPEN false UNSTABLE "$WEB_FILES" "$PENDING"
check "website-sensitive: advisory pending holds" 2
export GH_REQUIRED_CHECKS='[{"name":"pr-gate","state":"IN_PROGRESS","bucket":"pending"}]'
mkjson OPEN false UNSTABLE "$DOC_FILES" "$GREEN"
check "non-deploy: required pending holds" 2
mkjson OPEN false BLOCKED "$DOC_FILES" "$GREEN"
check "BLOCKED: required pending waits (HOLD)" 2
export GH_REQUIRED_CHECKS='[{"name":"pr-gate","state":"FAILURE","bucket":"fail"}]'
mkjson OPEN false UNSTABLE "$DOC_FILES" "$GREEN"
check "non-deploy: required failing holds" 2
unset GH_REQUIRED_CHECKS

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
