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
cd "$stubdir"
printf "%s\n" "caller-owned" > err.txt
trap 'rm -rf "$stubdir"' EXIT
cat > "$stubdir/gh" <<STUB
#!/usr/bin/env bash
# fake gh: emit the current fixture for any 'pr view ... --json ...' call.
# GraphQL-unavailable mode (Claude Code cloud sessions): the session proxy answers every GraphQL-backed
# gh command with one 403 (the text is the test's GRAPHQL_403) while REST (api repos/...) keeps working.
if [ -n "\${GH_GRAPHQL_BLOCKED:-}" ]; then
  case "\$*" in
    *"api graphql"*|*"pr view"*|*"pr checks"*|*"issue view"*) printf '%s\n' "\$GH_GRAPHQL_BLOCKED" >&2; exit 1 ;;
  esac
fi
# Opt-in REST twin of the GraphQL fixture (GH_REST=1): serves what GitHub's REST API would report for the
# same PR, so one fixture drives both transports. Off by default: the cases above pin the GraphQL-only world.
if [ -n "\${GH_REST:-}" ]; then
  case "\$*" in
    *"api"*"repos/o/r/pulls"*|*"api"*"repos/o/r/commits/"*) exec bash "$stubdir/restgh" "\$@" ;;
  esac
fi
# A branch whose protection names required contexts (REST policy read behind --contexts).
if [ -n "\${GH_REQUIRED_CONTEXTS:-}" ]; then
  case "\$*" in
    *"api repos/o/r/rules/branches/main"*) printf '%s\n' '[]'; exit 0 ;;
    *"api repos/o/r/branches/main"*)
      printf '{"name":"main","protected":true,"protection":{"required_status_checks":{"contexts":%s,"checks":[]}}}\n' "\$GH_REQUIRED_CONTEXTS"
      exit 0 ;;
  esac
fi
if [[ "\$*" == *"pr view"* ]] && [ -n "\${GH_PR_VIEW_ERROR:-}" ]; then
  printf '%s\n' "\$GH_PR_VIEW_ERROR" >&2
  exit 1
fi
case "\$*" in
  *"api repos/o/r/rules/branches/main"*)
    case "\${GH_NO_REQUIRED_POLICY:-unknown}" in
      verified) printf '%s\n' '[{"type":"pull_request"}]' ;;
      required) printf '%s\n' '[{"type":"required_status_checks"}]' ;;
      *) exit 1 ;;
    esac ;;
  *"api repos/o/r/branches/main"*)
    case "\${GH_NO_REQUIRED_POLICY:-unknown}" in
      verified|required) printf '%s\n' '{"name":"main","protected":true,"protection":{"required_status_checks":{"contexts":[],"checks":[]}}}' ;;
      *) exit 1 ;;
    esac ;;
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

# REST routes for the same fixture. The fixture is in `gh pr view --json` (GraphQL) shape; this maps it
# to the REST shapes (lower-case enums, snake_case timestamps) so the verdict logic is exercised through
# scripts/_gh_rest.py rather than through a second hand-written fixture.
cat > "$stubdir/restgh" <<'RESTSTUB'
#!/usr/bin/env bash
fx="$GH_FIXTURE"
endpoint="${*: -1}"
case "$endpoint" in
  repos/o/r/pulls/1/files*)
    jq '[.files[] | {filename: .path, status: "modified"}]' "$fx" ;;
  repos/o/r/pulls/1/ccr/review_threads)
    if [ -n "${GH_CCR_THREADS:-}" ]; then printf '%s\n' "$GH_CCR_THREADS"; else echo "gh: Not Found (HTTP 404)" >&2; exit 1; fi ;;
  repos/o/r/pulls/1)
    if [ -n "${GH_REST_PULL_ERROR:-}" ]; then printf '%s\n' "$GH_REST_PULL_ERROR" >&2; exit 1; fi
    n=$(( $(cat "$fx.calls" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$fx.calls"
    sha_override=""
    if [ "$n" -ge 2 ] && [ -n "${GH_RECHECK_HEAD:-}" ]; then sha_override="$GH_RECHECK_HEAD"; fi
    jq --arg sha "$sha_override" '{
      number, title, html_url: .url,
      state: (if .state == "OPEN" then "open" else "closed" end),
      merged: (.state == "MERGED"), draft: .isDraft,
      mergeable: (if .mergeStateStatus == "UNKNOWN" then null elif .mergeStateStatus == "DIRTY" then false else true end),
      mergeable_state: (.mergeStateStatus | ascii_downcase),
      changed_files: (.files | length),
      base: {ref: .baseRefName},
      head: {ref: .headRefName, sha: (if $sha != "" then $sha else .headRefOid end)}
    }' "$fx" ;;
  repos/o/r/pulls\?head=*)
    if [ -n "${GH_NO_OPEN_PR:-}" ]; then echo '[]'; else echo '[{"number":1}]'; fi ;;
  repos/o/r/commits/*/check-runs*)
    jq '{check_runs: [.statusCheckRollup[]? | select(.name) | {
      name, status: (.status | ascii_downcase),
      conclusion: (if .conclusion == null then null else (.conclusion | ascii_downcase) end),
      started_at: .startedAt, completed_at: .completedAt}]}' "$fx" ;;
  repos/o/r/commits/*/status*)
    jq '{state: "success", statuses: [.statusCheckRollup[]? | select(.context) | {context, state: (.state | ascii_downcase)}]}' "$fx" ;;
  *) echo "restgh: unrouted endpoint $endpoint" >&2; exit 1 ;;
esac
RESTSTUB
chmod +x "$stubdir/restgh"
export GH_FIXTURE="$fixture"

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

mkjson() { # state isDraft mss files rollup  (FIXTURE_URL overrides the PR url; default is not a GitHub URL)
  printf '{"number":1,"title":"t","url":"'"${FIXTURE_URL:-http://x}"'","state":"%s","isDraft":%s,"mergeStateStatus":"%s","baseRefName":"main","headRefName":"f","headRefOid":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","files":%s,"statusCheckRollup":%s}\n' \
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

check_bare_output() { # name expected_exit required_substring  (NO --repo: the documented bare form)
  local name="$1" want="$2" required="$3" got out
  set +e
  out=$(PATH="$stubdir:$PATH" bash "$policy" 1 2>&1)
  got=$?
  set -e
  if [ "$got" = "$want" ] && [[ "$out" == *"$required"* ]]; then
    printf '  ok   %-34s exit=%s\n' "$name" "$got"; pass=$((pass+1))
  else
    printf '  FAIL %-34s want=%s got=%s required=%q\n' "$name" "$want" "$got" "$required"
    printf '%s\n' "$out" | sed 's/^/       /'
    fail=$((fail+1))
  fi
}

echo "merge-policy.sh verdict matrix:"

# CLEARED (exit 0) — only genuinely-mergeable, policy-safe states
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check_output "clean non-deploy + green" 0 "MERGE-MODE: direct"
export GH_NO_REQUIRED_POLICY=verified
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"
check_output "proven no required: advisory failure" 0 "scope=required failing=0 pending=0"
mkjson OPEN false UNSTABLE "$WEB_FILES" "$FAILING"
check "no required still protects live deploy" 2
# The documented bare form must judge the same policy as --repo: the repository comes from the
# canonical PR URL. Keying the proof on --repo alone HELD an advisory-red PR the --repo run CLEARED
# (2026-10-18, #3043 / witness-contract). Absent a derivable repo it must stay cautious.
FIXTURE_URL=https://github.com/o/r/pull/1
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"
check_bare_output "bare: proven no required clears" 0 "scope=required failing=0 pending=0"
mkjson OPEN false UNSTABLE "$WEB_FILES" "$FAILING"
set +e; PATH="$stubdir:$PATH" bash "$policy" 1 >/dev/null 2>&1; bare_web=$?; set -e
if [ "$bare_web" = 2 ]; then printf '  ok   %-34s exit=%s\n' "bare: live deploy still held" "$bare_web"; pass=$((pass+1))
else printf '  FAIL %-34s want=2 got=%s\n' "bare: live deploy still held" "$bare_web"; fail=$((fail+1)); fi
unset FIXTURE_URL
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"
check_bare_output "bare: no derivable repo stays cautious" 2 "scope=all"
export GH_NO_REQUIRED_POLICY=unknown
FIXTURE_URL=https://github.com/o/r/pull/1
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"
check_bare_output "bare: unprovable policy stays cautious" 2 "scope=all"
unset FIXTURE_URL
export GH_NO_REQUIRED_POLICY=required
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"
check "rules require checks: cannot prove absence" 2
export GH_NO_REQUIRED_POLICY=unknown
check "unavailable policy: fail closed on red" 2
unset GH_NO_REQUIRED_POLICY
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

# GitHub transport/quota failures are HOLDs, never BLOCKED, and stderr must stay in a
# temporary file rather than leaving a repository-root err.txt behind.
rate_limit_case() {
  local message="$1"
  local want="${2:-2}"
  local mode="${3:-explicit}"
  local pr_arg=1
  [ "$mode" = explicit ] || pr_arg=""
  export GH_PR_VIEW_ERROR="$message"
  set +e
  PATH="$stubdir:$PATH" bash "$policy" $pr_arg --repo o/r >/dev/null 2>&1
  local got=$?
  set -e
  if [ "$got" = "$want" ] && [ "$(cat err.txt)" = "caller-owned" ]; then
    printf '  ok   %-34s exit=%s\n' "rate-limit: $message" "$got"
    pass=$((pass+1))
  else
    printf '  FAIL %-34s want=2 got=%s residue=%s\n' "rate-limit: $message" "$got" "$(cat err.txt)"
    fail=$((fail+1))
  fi
  unset GH_PR_VIEW_ERROR
}
rate_limit_case "rate limit exceeded"
rate_limit_case "API quota exhausted"
rate_limit_case "HTTP 403 from api.github.com" 3
rate_limit_case "HTTP 429 Too Many Requests"
rate_limit_case "fetch exhausted after retries"
rate_limit_case "API quota exhausted" 2 auto
rate_limit_case "HTTP 403 forbidden" 3 auto
rate_limit_case "HTTP 401 unauthorized" 3 auto
# #2147: transient transport failures are HOLDs (exit 2), never BLOCKED merge verdicts.
# Auth/permission errors stay BLOCKED (pinned above); only the transport class moves.
transport_case() {
  local message="$1"
  export GH_PR_VIEW_ERROR="$message"
  set +e
  PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r >/dev/null 2>&1
  local got=$?
  set -e
  if [ "$got" = "2" ] && [ "$(cat err.txt)" = "caller-owned" ]; then
    printf '  ok   %-34s exit=%s\n' "transport: $message" "$got"
    pass=$((pass+1))
  else
    printf '  FAIL %-34s want=2 got=%s residue=%s\n' "transport: $message" "$got" "$(cat err.txt)"
    fail=$((fail+1))
  fi
  unset GH_PR_VIEW_ERROR
}
transport_case "HTTP 502 Bad Gateway"
transport_case "HTTP 503 Service Unavailable"
transport_case "HTTP 504 Gateway Timeout"
transport_case "HTTP 500 Internal Server Error"
transport_case "dial tcp 140.82.114.6:443: i/o timeout"
transport_case "could not resolve host: api.github.com"
transport_case "connection reset by peer"
transport_case "network is unreachable"
# negative control: a genuinely unreadable PR stays BLOCKED
export GH_PR_VIEW_ERROR="HTTP 404 Not Found"
set +e
PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r >/dev/null 2>&1
got=$?
set -e
if [ "$got" = "3" ]; then
  printf '  ok   %-34s exit=%s\n' "transport-negative: 404 stays BLOCKED" "$got"
  pass=$((pass+1))
else
  printf '  FAIL %-34s want=3 got=%s\n' "transport-negative: 404 stays BLOCKED" "$got"
  fail=$((fail+1))
fi
unset GH_PR_VIEW_ERROR
export GH_PR_VIEW_ERROR="repository not found"
set +e
PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r >/dev/null 2>&1
got=$?
set -e
if [ "$got" = 3 ]; then
  printf '  ok   %-34s exit=%s\n' "ordinary gh read error" "$got"
  pass=$((pass+1))
else
  printf '  FAIL %-34s want=3 got=%s\n' "ordinary gh read error" "$got"
  fail=$((fail+1))
fi
unset GH_PR_VIEW_ERROR

# 2026-10-17: an unclassified lookup failure must SURFACE its gh diagnostic (bounded, scrubbed)
# on the BLOCKED path, and must never leak a credential shape into the verdict output.
export GH_PR_VIEW_ERROR="HTTP 404 Not Found token ghp_abcdefghijklmnopqrstuvwxyz0123456789"  # allow-secret: synthetic fixture
check_output "blocked: diagnostic surfaces" 3 "HTTP 404 Not Found" "ghp_abcdef"
unset GH_PR_VIEW_ERROR
export GH_PR_VIEW_ERROR="$(printf 'LEADING-MARKER-%0400d tail-marker' 0)"
check_output "blocked: diagnostic is bounded" 3 "tail-marker" "LEADING-MARKER"
unset GH_PR_VIEW_ERROR

# The check rollup must remain attached to the exact head captured in the first PR snapshot.
export GH_RECHECK_HEAD=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"; check "head changed during predicate" 2
unset GH_RECHECK_HEAD
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
jq '.headRefOid = ""' "$fixture" > "$fixture.tmp" && mv "$fixture.tmp" "$fixture"
check "head identity unavailable" 2
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check "expected head mismatch" 2 --expected-head bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

# ── GraphQL unavailable (Claude Code cloud sessions) — gap G4 ─────────────────────────────────────────
# The cloud-session proxy answers EVERY GraphQL-backed gh command with one HTTP 403, so `gh pr view` could
# not read any PR and the predicate said "cannot read PR" for PRs that were perfectly readable over REST
# (2026-10-24, 4444J99/limen#3171: non-draft, mergeable, pr-gate green — BLOCKED anyway). The facts now fall
# back to the REST API in the same shape and are judged by the SAME rules, so every verdict below must equal
# what the GraphQL transport reports for the same PR.
GRAPHQL_403='HTTP 403: GitHub GraphQL is not available from Claude Code sessions; use the REST API (gh api repos/{owner}/{repo}/...). For review threads, auto-merge, and draft/ready-for-review use the CCR routes on api.github.com: GET /repos/{owner}/{repo}/pulls/{n}/ccr/review_threads, POST /repos/{owner}/{repo}/pulls/{n}/ccr/ready_for_review, POST /repos/{owner}/{repo}/pulls/{n}/ccr/convert_to_draft. (https://api.github.com/graphql)'

run_rest() { # [policy args...] — GraphQL blocked, REST serving the fixture; honors exported GH_* knobs
  rm -f "$fixture.calls"
  GH_GRAPHQL_BLOCKED="$GRAPHQL_403" GH_REST=1 LIMEN_GH_REST_MERGEABLE_DELAY=0 \
    PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r "$@" 2>&1
}
check_rest() { # name expected_exit required_substring [forbidden_substring]
  local name="$1" want="$2" required="$3" forbidden="${4:-}" got out
  set +e
  out=$(run_rest)
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
parity() { # name expected_exit — GraphQL and REST transports must agree, and both must equal expected
  local name="$1" want="$2" g r
  set +e
  PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r >/dev/null 2>&1; g=$?
  run_rest >/dev/null; r=$?
  set -e
  if [ "$g" = "$want" ] && [ "$r" = "$want" ]; then
    printf '  ok   %-34s graphql=%s rest=%s\n' "$name" "$g" "$r"; pass=$((pass+1))
  else
    printf '  FAIL %-34s want=%s graphql=%s rest=%s\n' "$name" "$want" "$g" "$r"; fail=$((fail+1))
  fi
}

# The reported case: GraphQL 403, REST says clean + non-draft + green on a non-deploy path.
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check_rest "REST: clean green non-deploy CLEARED" 0 "VERDICT: CLEARED" "BLOCKED"
check_rest "REST: binds the exact MERGE-HEAD" 0 \
  "MERGE-HEAD: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa (use gh pr merge --match-head-commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)"
check_rest "REST: direct mode, non-deploy" 0 "MERGE-MODE: direct" "MERGE-MODE: queue"
check_rest "REST: states the read path" 0 "read-path=rest"
check_output "GraphQL path: no rest marker" 0 "VERDICT: CLEARED" "read-path=rest"

# Verdict parity: one fixture, two transports, one answer.
for mss in CLEAN UNSTABLE; do
  mkjson OPEN false "$mss" "$DOC_FILES" "$GREEN"; parity "parity $mss + green" 0
done
mkjson OPEN false BEHIND  "$DOC_FILES" "$GREEN";   parity "parity BEHIND (no queue)" 3
mkjson OPEN false DIRTY   "$DOC_FILES" "$GREEN";   parity "parity DIRTY" 3
mkjson OPEN false BLOCKED "$DOC_FILES" "$GREEN";   parity "parity BLOCKED, nothing pending" 3
mkjson OPEN false UNKNOWN "$DOC_FILES" "$GREEN";   parity "parity UNKNOWN (still computing)" 2
mkjson OPEN true  CLEAN   "$DOC_FILES" "$GREEN";   parity "parity DRAFT" 2
mkjson MERGED false CLEAN "$DOC_FILES" "$GREEN";   parity "parity MERGED guard" 3
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"; parity "parity failing check" 2
mkjson OPEN false UNSTABLE "$DOC_FILES" "$DUP_LATEST_FAIL"; parity "parity dup, latest FAILURE" 2
mkjson OPEN false UNSTABLE "$DOC_FILES" "$SUPERSEDED_OK"; parity "parity superseded run is ignored" 0
mkjson OPEN false UNSTABLE "$DOC_FILES" "$PENDING"; parity "parity non-deploy + pending" 2
mkjson OPEN false CLEAN   "$DOC_FILES" "$NONE";    parity "parity non-deploy + 0 checks" 0
mkjson OPEN false CLEAN   "$WEB_FILES" "$GREEN";   parity "parity deploy path + green" 0
mkjson OPEN false UNSTABLE "$WEB_FILES" "$PENDING"; parity "parity deploy path + pending" 2
mkjson OPEN false CLEAN   "$WEB_FILES" "$NONE";    parity "parity deploy path + 0 checks" 2
mkjson OPEN false UNSTABLE "$WEB_FILES" "$FAILING"; parity "parity deploy path + failing" 2

# Failure modes: when neither transport can read the PR the verdict stays BLOCKED (fail toward caution)
# and BOTH scrubbed diagnostics surface; transport trouble on either path is a HOLD, never BLOCKED.
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
export GH_REST_PULL_ERROR="gh: Not Found (HTTP 404) token ghp_abcdefghijklmnopqrstuvwxyz0123456789"  # allow-secret: synthetic fixture
check_rest "both paths fail: BLOCKED" 3 "VERDICT: BLOCKED — cannot read PR" "ghp_abcdef"
check_rest "both paths fail: graphql diagnostic" 3 "merge-policy: gh diagnostic (scrubbed"
check_rest "both paths fail: rest diagnostic" 3 "REST fallback diagnostic (scrubbed, last 300B): _gh_rest: gh: Not Found (HTTP 404)" "ghp_abcdef"
export GH_REST_PULL_ERROR="gh: Bad Gateway (HTTP 502)"
check_rest "graphql 403 + rest 502: HOLD" 2 "transient transport error" "BLOCKED"
unset GH_REST_PULL_ERROR
# Quota/transport trouble on the GraphQL side HOLDs BEFORE the fallback is tried. REST would have cleared
# this PR (GH_REST=1 and a green fixture), so exit 2 proves it was never consulted.
for message in "rate limit exceeded" "HTTP 502 Bad Gateway"; do
  set +e
  out=$(GH_PR_VIEW_ERROR="$message" GH_REST=1 PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r 2>&1)
  got=$?
  set -e
  if [ "$got" = 2 ] && [[ "$out" != *"read-path=rest"* ]]; then
    printf '  ok   %-34s exit=%s\n' "graphql '$message' holds first" "$got"; pass=$((pass+1))
  else
    printf '  FAIL %-34s want=2 got=%s\n' "graphql '$message' holds first" "$got"; fail=$((fail+1))
  fi
done
# A non-quota GraphQL failure that is not the 403 (here a plain read error) also reaches the REST reader.
set +e
out=$(GH_PR_VIEW_ERROR="repository not found" GH_REST=1 PATH="$stubdir:$PATH" bash "$policy" 1 --repo o/r 2>&1)
got=$?
set -e
if [ "$got" = 0 ] && [[ "$out" == *"read-path=rest"* ]]; then
  printf '  ok   %-34s exit=%s\n' "other graphql failure -> rest" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-34s want=0 got=%s\n' "other graphql failure -> rest" "$got"; fail=$((fail+1))
fi

# The head must stay bound across the read: REST re-reads it after the rollup, like the GraphQL path.
export GH_RECHECK_HEAD=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
check_rest "REST: head changed during predicate" 2 "PR head changed while checks were inspected"
unset GH_RECHECK_HEAD

# Required-vs-advisory over REST: `gh pr checks --required` is GraphQL too, so the required set is read from
# branch protection + rulesets and the same rollup rules are applied to just those names. An unreadable or
# unknown policy keeps the conservative all-checks counts.
REQ_OK_ADV_RED='[{"name":"pr-gate","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"nightly","status":"COMPLETED","conclusion":"FAILURE"}]'
REQ_RED='[{"name":"pr-gate","status":"COMPLETED","conclusion":"FAILURE"},{"name":"nightly","status":"COMPLETED","conclusion":"SUCCESS"}]'
REQ_PENDING='[{"name":"pr-gate","status":"IN_PROGRESS","conclusion":null},{"name":"nightly","status":"COMPLETED","conclusion":"SUCCESS"}]'
ADV_PENDING='[{"name":"pr-gate","status":"COMPLETED","conclusion":"SUCCESS"},{"name":"nightly","status":"IN_PROGRESS","conclusion":null}]'
export GH_REQUIRED_CONTEXTS='["pr-gate"]'
mkjson OPEN false UNSTABLE "$DOC_FILES" "$REQ_OK_ADV_RED"
check_rest "REST required set: advisory red passes" 0 "required checks: scope=required failing=0 pending=0"
mkjson OPEN false UNSTABLE "$DOC_FILES" "$REQ_RED"
check_rest "REST required set: required red holds" 2 "1 required check(s) failing (required scope)"
mkjson OPEN false UNSTABLE "$DOC_FILES" "$REQ_PENDING"
check_rest "REST required set: required pending" 2 "required check(s) still running"
mkjson OPEN false UNSTABLE "$DOC_FILES" "$ADV_PENDING"
check_rest "REST required set: advisory pending ok" 0 "advisory (non-required) check(s) still running"
mkjson OPEN false UNSTABLE "$WEB_FILES" "$ADV_PENDING"
check_rest "REST required set: deploy needs all" 2 "website-sensitive"
# Same branch when only `gh pr checks` is unavailable (GraphQL transport otherwise fine).
mkjson OPEN false UNSTABLE "$DOC_FILES" "$REQ_OK_ADV_RED"
check_output "gh pr checks down: contexts used" 0 "required checks: scope=required failing=0"
unset GH_REQUIRED_CONTEXTS
mkjson OPEN false UNSTABLE "$DOC_FILES" "$REQ_OK_ADV_RED"
check_rest "REST unmeasured policy: all checks" 2 "scope=all"

# LIMEN_REVIEW_GATE=1 reads review threads over the CCR route when GraphQL is unavailable, and stays fail-open.
FIXTURE_URL=https://github.com/o/r/pull/1 mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
export LIMEN_REVIEW_GATE=1
export GH_CCR_THREADS='[{"resolved":true},{"resolved":false,"outdated":true}]'
check_rest "REST review gate: unresolved holds" 2 "1 unresolved review thread(s)"
export GH_CCR_THREADS='[{"resolved":true}]'
check_rest "REST review gate: all resolved clears" 0 "VERDICT: CLEARED"
unset GH_CCR_THREADS
check_rest "REST review gate: unreadable fails open" 0 "VERDICT: CLEARED"
unset LIMEN_REVIEW_GATE

# No PR number: the open PR for the checked-out branch is found over REST too.
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
mkdir -p "$stubdir/work" && git init -q "$stubdir/work" && git -C "$stubdir/work" symbolic-ref HEAD refs/heads/feature
set +e
out=$(cd "$stubdir/work" && rm -f "$fixture.calls" && GH_GRAPHQL_BLOCKED="$GRAPHQL_403" GH_REST=1 LIMEN_GH_REST_MERGEABLE_DELAY=0 \
  PATH="$stubdir:$PATH" bash "$policy" --repo o/r 2>&1)
got=$?
set -e
if [ "$got" = 0 ] && [[ "$out" == *"PR #1"* ]] && [[ "$out" == *"VERDICT: CLEARED"* ]]; then
  printf '  ok   %-34s exit=%s\n' "REST: PR found from branch" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-34s want=0 got=%s\n' "REST: PR found from branch" "$got"; printf '%s\n' "$out" | sed 's/^/       /'; fail=$((fail+1))
fi
set +e
out=$(cd "$stubdir/work" && GH_NO_OPEN_PR=1 GH_GRAPHQL_BLOCKED="$GRAPHQL_403" GH_REST=1 PATH="$stubdir:$PATH" bash "$policy" --repo o/r 2>&1)
got=$?
set -e
if [ "$got" = 3 ] && [[ "$out" == *"no open PR for current branch"* ]]; then
  printf '  ok   %-34s exit=%s\n' "REST: no open PR for branch" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-34s want=3 got=%s\n' "REST: no open PR for branch" "$got"; printf '%s\n' "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

# Resolver unavailable ⇒ website-sensitive (fail toward caution). With a broken python3 the
# deploy regex cannot derive from the GATES registry, so a docs-only PR with zero checks —
# normally CLEARED — must HOLD instead of risking an unclassified live deploy. The gate-python
# resolver would otherwise route around the stub to another python on PATH, so the inherited override
# is cleared and the candidate list names nothing that exists: "no usable interpreter" is the case, and
# merge-policy then falls back to the bare (stubbed) python3 whose derivation fails.
cat > "$stubdir/python3" <<'STUB'
#!/usr/bin/env bash
exit 1
STUB
chmod +x "$stubdir/python3"
mkjson OPEN false CLEAN "$DOC_FILES" "$NONE"
LIMEN_GATE_PYTHON="" LIMEN_GATE_PYTHON_CANDIDATES=limen-no-such-python check "resolver unavailable (forced sensitive)" 2
rm -f "$stubdir/python3"

# Single-owner fast lane (issue #2895; operator fact 2026-10-17: private-repo Actions are billing-locked,
# so remote checks never run and are never evidence). The class is DERIVED from estate.yaml — the
# 4444J99/domus-genoma-private override is operation_private, which declares single_owner_fast_lane.
# GitHub-reported mergeability and drafts still bind; limen's own deploy rails are untouched.
check_repo_output() { # name expected_exit repo required_substring [forbidden_substring]
  local name="$1" want="$2" repo="$3" required="$4" forbidden="${5:-}" got out
  set +e
  out=$(PATH="$stubdir:$PATH" bash "$policy" 1 --repo "$repo" 2>&1)
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
PRIVATE_REPO=4444J99/domus-genoma-private
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"
check_repo_output "private fast lane: failing checks advisory" 0 "$PRIVATE_REPO" "MERGE-MODE: direct" "MERGE-MODE: queue"
check_repo_output "private fast lane: binds exact head" 0 "$PRIVATE_REPO" \
  "MERGE-HEAD: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
check_repo_output "private fast lane: states checks advisory" 0 "$PRIVATE_REPO" "remote checks are advisory" "WEBSITE-SENSITIVE"
mkjson OPEN false UNSTABLE "$WEB_FILES" "$FAILING"
check_repo_output "private fast lane: limen deploy paths moot" 0 "$PRIVATE_REPO" "MERGE-MODE: direct" "WEBSITE-SENSITIVE"
mkjson OPEN false UNSTABLE "$DOC_FILES" "$PENDING"
check_repo_output "private fast lane: pending checks advisory" 0 "$PRIVATE_REPO" "MERGE-MODE: direct"
mkjson OPEN false CLEAN "$DOC_FILES" "$NONE"
check_repo_output "private fast lane: zero checks (no Actions)" 0 "$PRIVATE_REPO" "MERGE-MODE: direct"
mkjson OPEN false DIRTY "$DOC_FILES" "$GREEN"
check_repo_output "private fast lane: conflicts BLOCKED" 3 "$PRIVATE_REPO" "VERDICT: BLOCKED"
mkjson OPEN false BEHIND "$DOC_FILES" "$GREEN"
check_repo_output "private fast lane: stale base BLOCKED" 3 "$PRIVATE_REPO" "VERDICT: BLOCKED"
mkjson OPEN true CLEAN "$DOC_FILES" "$GREEN"
check_repo_output "private fast lane: draft HOLD" 2 "$PRIVATE_REPO" "VERDICT: HOLD"
mkjson OPEN false UNKNOWN "$DOC_FILES" "$GREEN"
check_repo_output "private fast lane: UNKNOWN HOLD" 2 "$PRIVATE_REPO" "VERDICT: HOLD"
mkjson MERGED false CLEAN "$DOC_FILES" "$GREEN"
check_repo_output "private fast lane: closed-PR guard" 3 "$PRIVATE_REPO" "VERDICT: BLOCKED"
# limen is a fast-lane class too, but its deploy rails stay governed by GATES: a failing check
# still holds, and a deploy-trigger path is still website-sensitive.
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"
check_repo_output "limen: failing check still holds" 2 4444J99/limen "VERDICT: HOLD" "fast lane"
mkjson OPEN false UNSTABLE "$WEB_FILES" "$PENDING"
check_repo_output "limen: deploy path still sensitive" 2 4444J99/limen "WEBSITE-SENSITIVE" "fast lane"
mkjson OPEN false UNSTABLE "$DOC_FILES" "$FAILING"
check_repo_output "limen alias: failing check holds" 2 organvm/limen "VERDICT: HOLD" "fast lane"
# A public governed repo is not a fast lane: failing checks keep their conservative meaning.
check_repo_output "public repo: failing check holds" 2 organvm/some-public-repo "VERDICT: HOLD" "fast lane"
# The class cannot be derived (the stub `gh repo view` fails, and o/r has no override): fail toward caution.
check_repo_output "class unresolved: caution kept" 2 o/r "cannot derive the estate class" "fast lane"

# Personal relay cannot fall through a standalone policy helper even with a
# passing duplicate context, --repo case variation, or canonical URL discovery.
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check "relay governor required" 2 --repo 4444J99/organvm-ci-relay
check "relay case-folded identity" 2 --repo 4444j99/ORGANVM-CI-RELAY
jq '.url="https://github.com/4444J99/organvm-ci-relay/pull/1"' "$fixture" > "$stubdir/canonical.json"
mv "$stubdir/canonical.json" "$fixture"
check "relay canonical URL guard" 2

mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"
check "portfolio unavailable evidence holds" 2 --repo organvm-vii-kerygma/portfolio
check "UCC unavailable evidence holds" 2 --repo organvm-iii-ergon/public-record-data-scrapper
check "portfolio previous name holds" 2 --repo 4444J99/portfolio
jq '.url="https://github.com/organvm-vii-kerygma/portfolio/pull/234"' "$fixture" > "$stubdir/canonical.json"
mv "$stubdir/canonical.json" "$fixture"
check "dependency canonical URL guard" 2

# --- AUTONOMY-PAUSED chokepoint (#1079) ---
# A sandbox repo root carries the REAL governor so the chokepoint exercises the live
# release semantics (expiry, merged-owner). The pause check runs before any `gh` call,
# so the held case needs no network fixture; the override case reuses the gh stub.
pause_root="$(mktemp -d)"
mkdir -p "$pause_root/scripts" "$pause_root/logs"
cp "$policy" "$pause_root/scripts/merge-policy.sh"
cp "$(dirname "$policy")/autonomy-governor.py" "$pause_root/scripts/autonomy-governor.py"
pause_policy="$pause_root/scripts/merge-policy.sh"
trap 'rm -rf "$stubdir" "$pause_root"' EXIT
mkjson OPEN false CLEAN "$DOC_FILES" "$GREEN"

pause_run() { # [extra env assignments...] — run the sandboxed policy, echo "exit|output"
  set +e
  out=$(env "$@" PATH="$stubdir:$PATH" bash "$pause_policy" 1 --repo o/r 2>&1)
  got=$?
  set -e
  printf '%s|%s' "$got" "$out"
}

# 1. A live pause marker holds the merge lane even when the PR is green.
cat > "$pause_root/logs/AUTONOMY_PAUSED" <<'MARKER'
armed_at: 2026-09-26T00:00:00Z
owner_surface: merge-policy.test.sh pause case
prohibitions: dispatch, merge, rebase, PR mutation, worktree reclaim, Claude-lane action
release_predicate: explicit test resume
MARKER
res="$(pause_run)"; got="${res%%|*}"; out="${res#*|}"
if [ "$got" = "2" ] && printf '%s' "$out" | grep -q "autonomy is PAUSED" \
    && printf '%s' "$out" | grep -qi "prohibitions: dispatch, merge"; then
  printf '  ok   %-34s exit=%s\n' "paused marker holds merge lane" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-34s want=2 got=%s\n' "paused marker holds merge lane" "$got"
  printf '%s\n' "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

# 2. The operator's explicit override releases the chokepoint; the predicate's
#    normal verdict (green non-deploy → CLEARED) still runs underneath.
res="$(pause_run LIMEN_FORCE_AUTONOMY=1)"; got="${res%%|*}"; out="${res#*|}"
if [ "$got" = "0" ] && printf '%s' "$out" | grep -q "MERGE-MODE: direct"; then
  printf '  ok   %-34s exit=%s\n' "force-autonomy override releases pause" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-34s want=0 got=%s\n' "force-autonomy override releases pause" "$got"
  printf '%s\n' "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

# 3. A governor that cannot run means HOLD, never CLEARED (fail toward caution).
mv "$pause_root/scripts/autonomy-governor.py" "$pause_root/scripts/autonomy-governor.py.bak"
res="$(pause_run LIMEN_FORCE_AUTONOMY=1)"; got="${res%%|*}"; out="${res#*|}"
mv "$pause_root/scripts/autonomy-governor.py.bak" "$pause_root/scripts/autonomy-governor.py"
if [ "$got" = "2" ] && printf '%s' "$out" | grep -q "reported no mode"; then
  printf '  ok   %-34s exit=%s\n' "unreadable governor holds" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-34s want=2 got=%s\n' "unreadable governor holds" "$got"
  printf '%s\n' "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

# 4. No logs/ directory at all (fresh checkout, nothing could be paused) skips the
#    chokepoint entirely — the normal verdict runs.
rm -rf "$pause_root/logs"
res="$(pause_run)"; got="${res%%|*}"; out="${res#*|}"
if [ "$got" = "0" ] && printf '%s' "$out" | grep -q "MERGE-MODE: direct"; then
  printf '  ok   %-34s exit=%s\n' "no logs dir skips chokepoint" "$got"; pass=$((pass+1))
else
  printf '  FAIL %-34s want=0 got=%s\n' "no logs dir skips chokepoint" "$got"
  printf '%s\n' "$out" | sed 's/^/       /'; fail=$((fail+1))
fi

echo
echo "passed=$pass failed=$fail"
if [ "$fail" -eq 0 ]; then
  echo "merge-policy regression test PASSED"; exit 0
else
  echo "merge-policy regression test FAILED"; exit 1
fi
