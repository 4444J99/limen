#!/usr/bin/env bash
# merge-policy.sh — the executable predicate for "may Claude self-merge this PR?"
#
# Standing grant (CLAUDE.md › Merge & Branch Protocol): Claude merges its OWN green PRs into
# `main` WITHOUT asking. The single guardrail is the live public website: a merge to `main`
# auto-deploys the site/API *only* when the diff touches a deploy-trigger path. This script
# decides — by logic, never by memory — whether a given PR is cleared to merge.
#
#   exit 0  CLEARED — safe to `gh pr merge`. (A non-deploy PR that is mergeable, or a
#                     deploy-touching PR whose CI is fully GREEN + COMPLETE.)
#   exit 2  HOLD    — website-sensitive AND CI not yet green/complete, or the PR is a draft,
#                     or a non-deploy PR still has checks running. Wait for green; never
#                     blind-merge a live deploy.
#   exit 3  BLOCKED — GitHub itself refuses the merge right now: conflicts (DIRTY), stale base
#                     (BEHIND), or a branch-protection gate not satisfied (BLOCKED — e.g. the
#                     required `pr-gate` check hasn't run on a pre-existing PR). Rebase onto
#                     current main (the PR#111 silent-revert guard; also retriggers required
#                     checks), then re-run. Distinct from HOLD: HOLD means GitHub would allow
#                     the merge but the website-safety policy says wait; BLOCKED means it can't.
#
# Usage:  scripts/merge-policy.sh [PR_NUMBER] [--repo OWNER/NAME] [--expected-head SHA]
#         (no PR number → resolves the PR open for the current branch)
set -euo pipefail

PR=""; REPO=""; EXPECTED_HEAD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --repo=*) REPO="${1#*=}"; shift ;;
    --expected-head) EXPECTED_HEAD="${2:-}"; shift 2 ;;
    --expected-head=*) EXPECTED_HEAD="${1#*=}"; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) PR="$1"; shift ;;
  esac
done

repo_args=(); [ -n "$REPO" ] && repo_args=(--repo "$REPO")
# bash 3.2 (macOS /bin/bash) errors on a bare empty-array expansion under `set -u`. Use the
# array-plus idiom at each call site below, which expands to nothing for an empty array and to
# the elements otherwise — safe in bash 3.2 and 4+.

# Deploy-trigger classification — DERIVED from the GATES registry (institutio/governance/
# gates.yaml). check-gates.py holds the registry in exact set-parity with the deploy*.yml
# `on.push.paths` on every PR, so the old hardcoded regexes and their awk staleness guard
# are gone: one source of truth, one drift predicate. A push/merge to `main` touching a
# derived path auto-deploys the live public site/API.
#
# Fail toward caution: if derivation fails (missing python3/PyYAML/registry), STALE=1
# forces website-sensitive — a broken environment can only HOLD, never blind-deploy.
STALE=0
_root="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
DEPLOY_RE="$(python3 "$_root/scripts/verify.py" --deploy-regex 2>/dev/null || true)"
if [ -z "$DEPLOY_RE" ]; then
  echo "merge-policy: cannot derive the deploy regex from the GATES registry — treating the PR as website-sensitive (fail toward caution)." >&2
  STALE=1
  DEPLOY_RE='^$'
fi

# Resolve the PR for the current branch when not given.
if [ -z "$PR" ]; then
  PR="$(gh pr view "${repo_args[@]+"${repo_args[@]}"}" --json number -q .number 2>/dev/null || true)"
  [ -z "$PR" ] && { echo "merge-policy: no PR number given and none open for the current branch." >&2; exit 3; }
fi

j="$(mktemp)"; trap 'rm -f "$j"' EXIT
gh pr view "$PR" "${repo_args[@]+"${repo_args[@]}"}" \
  --json number,title,url,state,isDraft,mergeStateStatus,baseRefName,headRefName,headRefOid,files,statusCheckRollup \
  > "$j" 2>/dev/null || { echo "merge-policy: cannot read PR #$PR (wrong repo?)." >&2; exit 3; }

title=$(jq -r '.title' "$j")
url=$(jq -r '.url' "$j")
state=$(jq -r '.state' "$j")
base=$(jq -r '.baseRefName' "$j")
mss=$(jq -r '.mergeStateStatus' "$j")
draft=$(jq -r '.isDraft' "$j")
head=$(jq -r '.headRefOid // empty' "$j")

# Only an OPEN PR can be merged — guard against a false CLEARED on an already-merged/closed PR.
if [ "$state" != "OPEN" ]; then
  echo "PR #$PR — $title"
  echo "  $url"
  echo "VERDICT: BLOCKED — PR is $state, nothing to merge."
  exit 3
fi

# Bind the rollup above to one exact PR head. A push racing this predicate invalidates the
# association between the checks we inspected and the code GitHub would merge; fail closed and let
# the next invocation inspect the new head. Missing head identity is equally non-authoritative.
if [ -z "$head" ]; then
  echo "VERDICT: HOLD — PR head identity is unavailable; cannot associate checks with exact code."
  exit 2
fi
if [ -n "$EXPECTED_HEAD" ] && [ "$head" != "$EXPECTED_HEAD" ]; then
  echo "VERDICT: HOLD — expected PR head $EXPECTED_HEAD but GitHub reports $head; re-run on the new head."
  exit 2
fi
head_now=$(gh pr view "$PR" "${repo_args[@]+"${repo_args[@]}"}" --json headRefOid -q .headRefOid 2>/dev/null || true)
if [ -z "$head_now" ] || [ "$head_now" != "$head" ]; then
  echo "VERDICT: HOLD — PR head changed while checks were inspected; re-run on the new exact head."
  exit 2
fi

deploy_hits=$(jq -r '.files[].path' "$j" | grep -E "$DEPLOY_RE" || true)
sensitive=0
[ -n "$deploy_hits" ] && sensitive=1
[ "$STALE" = 1 ] && sensitive=1   # fail-safe: uncertain classification ⇒ treat as a live deploy

# CI rollup: count failing / pending across CheckRuns (conclusion/status) and StatusContexts (state).
failing=$(jq '[.statusCheckRollup[]? | (.conclusion // .state // "" | ascii_upcase)
             | select(.=="FAILURE" or . =="CANCELLED" or . =="TIMED_OUT" or . =="ERROR"
                      or . =="ACTION_REQUIRED" or . =="STARTUP_FAILURE")] | length' "$j")
pending=$(jq '[.statusCheckRollup[]?
             | ((.status // "" | ascii_upcase) as $s | (.state // "" | ascii_upcase) as $st
                | select($s=="QUEUED" or $s=="IN_PROGRESS" or $s=="PENDING" or $st=="PENDING" or $st=="EXPECTED"))]
             | length' "$j")
total_checks=$(jq '[.statusCheckRollup[]?] | length' "$j")

echo "PR #$PR — $title"
echo "  $url"
echo "  base=$base  head=${head:0:12}  mergeState=$mss  draft=$draft"
if [ "$sensitive" = 1 ]; then
  if [ -n "$deploy_hits" ]; then
    echo "  WEBSITE-SENSITIVE — diff touches deploy-trigger paths:"
    printf '%s\n' "$deploy_hits" | sed 's/^/      /'
  else
    echo "  WEBSITE-SENSITIVE — forced: deploy classification could not be derived from the GATES registry"
  fi
else
  echo "  non-deploy — merging will NOT trigger a live website/API deploy"
fi
echo "  checks: total=$total_checks failing=$failing pending=$pending"

# --- verdict ---
# GitHub's mergeStateStatus is authoritative on whether a merge is even POSSIBLE. Handle every
# not-mergeable / indeterminate state explicitly; NEVER fall through to CLEARED on an unhandled
# state (an UNKNOWN-during-recompute or a future enum value must not read as "safe to merge").
case "$mss" in
  DIRTY)  echo "VERDICT: BLOCKED — merge conflicts. Rebase onto origin/$base, then re-run."; exit 3 ;;
  BEHIND) echo "VERDICT: BLOCKED — stale base (branch is behind $base). Rebase onto current $base first (PR#111 silent-revert guard), then re-run."; exit 3 ;;
  BLOCKED)
    # BLOCKED means branch protection won't merge yet — but it covers two cases. If a required
    # check is still RUNNING, the remedy is simply to wait (HOLD); only when nothing is pending is
    # it genuinely stuck (required check never ran, or a required review is missing → action needed).
    if [ "$pending" -gt 0 ]; then
      echo "VERDICT: HOLD — branch protection is waiting on $pending required check(s) still running. Wait for green, then re-run."; exit 2
    fi
    echo "VERDICT: BLOCKED — branch protection won't allow the merge: a required check never ran, or a required review is missing. For a PR opened before a required check was added this is almost always the missing 'pr-gate' context, which only runs after the head is pushed/rebased — rebase onto origin/$base to retrigger it, then re-run. If it persists after a rebase with green checks, a required review or admin merge is needed: surface to human, don't force it."; exit 3 ;;
  UNKNOWN) echo "VERDICT: HOLD — GitHub is still computing mergeability (mergeState=UNKNOWN); this is transient. Re-run in a few seconds."; exit 2 ;;
esac
if [ "$draft" = "true" ]; then
  echo "VERDICT: HOLD — PR is a draft. Mark ready, then re-run."; exit 2
fi
if [ "$failing" -gt 0 ]; then
  echo "VERDICT: HOLD — $failing CI check(s) failing. Fix before merge."; exit 2
fi
# --- optional review gate (LIMEN_REVIEW_GATE=1; DEFAULT OFF) ---
# The merge half of the multi-agent review engine: HOLD while unresolved review threads remain.
# Ships dark — 300 repos of unresolved bot threads would jam the estate; flip conductor-first once
# self-heal's REVIEW-FEEDBACK tasks demonstrably drain threads. Fail-OPEN on any read error: the
# gate is advisory until proven, and a GraphQL hiccup must never freeze the merge lane.
if [ "${LIMEN_REVIEW_GATE:-0}" = "1" ]; then
  nwo=$(printf '%s' "$url" | sed -E 's#https://github.com/([^/]+/[^/]+)/pull/.*#\1#')
  if [ -n "$nwo" ] && [ "$nwo" != "$url" ]; then
    unresolved=$(gh api graphql \
      -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100){nodes{isResolved}}}}}' \
      -F o="${nwo%%/*}" -F r="${nwo##*/}" -F n="$PR" \
      --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved|not)] | length' 2>/dev/null || true)
    if [ -n "$unresolved" ] && [ "$unresolved" -gt 0 ] 2>/dev/null; then
      echo "VERDICT: HOLD — $unresolved unresolved review thread(s) (LIMEN_REVIEW_GATE=1). Address + resolve them (self-heal's REVIEW-FEEDBACK tasks own the loop), then re-run."; exit 2
    fi
  fi
fi
# Past the not-mergeable states: only an explicitly mergeable state may proceed toward CLEARED.
case "$mss" in
  CLEAN|UNSTABLE|HAS_HOOKS) : ;;  # GitHub will permit the merge
  *) echo "VERDICT: HOLD — unrecognized merge state '$mss'; refusing to clear on an unhandled state. Re-run, or inspect the PR manually."; exit 2 ;;
esac
if [ "$sensitive" = 1 ]; then
  if [ "$pending" -gt 0 ] || [ "$total_checks" -eq 0 ]; then
    echo "VERDICT: HOLD — website-sensitive: a live deploy fires on merge and CI is not GREEN+COMPLETE (${pending} pending, ${total_checks} total). Wait for green; never blind-merge a deploy."
    exit 2
  fi
  echo "VERDICT: CLEARED — website-sensitive, but CI is fully green. Safe to self-merge; the live deploy is verified."
  echo "MERGE-HEAD: $head (use gh pr merge --match-head-commit $head)"
  exit 0
fi
if [ "$pending" -gt 0 ]; then
  echo "VERDICT: HOLD — ${pending} non-deploy check(s) still running. Merge once green."; exit 2
fi
echo "VERDICT: CLEARED — non-deploy PR, mergeable, no failing checks. Self-merge per the standing grant."
echo "MERGE-HEAD: $head (use gh pr merge --match-head-commit $head)"
exit 0
