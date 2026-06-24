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
#   exit 3  BLOCKED — not mergeable as-is: conflicts (DIRTY) or stale base (BEHIND). Rebase
#                     onto current main first (the PR#111 silent-revert guard), then re-run.
#
# Usage:  scripts/merge-policy.sh [PR_NUMBER] [--repo OWNER/NAME]
#         (no PR number → resolves the PR open for the current branch)
set -euo pipefail

PR=""; REPO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --repo=*) REPO="${1#*=}"; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) PR="$1"; shift ;;
  esac
done

repo_args=(); [ -n "$REPO" ] && repo_args=(--repo "$REPO")

# Deploy-trigger paths — kept in lockstep with .github/workflows/deploy*.yml `on.push.paths`.
# A push/merge to `main` that touches one of these auto-deploys the live public site/API.
DASHBOARD_RE='^web/app/|^firebase\.json$|^tasks\.yaml$|^\.github/workflows/deploy\.yml$'
API_RE='^web/api/|^cli/|^scripts/preflight-cloud-run\.sh$|^\.github/workflows/deploy-api\.yml$'
DEPLOY_RE="(${DASHBOARD_RE}|${API_RE})"

# --- staleness guard: never let this hardcoded list silently rot away from the workflows. ---
# Re-read each deploy workflow's `paths:` globs; if one isn't covered by DEPLOY_RE, warn AND
# fail toward caution (force website-sensitive) — a bad live deploy is the irreversible risk.
STALE=0
_check_workflow_paths() {
  local wf="$1"
  [ -f "$wf" ] || return 0
  local globs g sample
  globs=$(awk '
    /^[[:space:]]*paths:[[:space:]]*$/ {f=1; next}
    f && /^[[:space:]]*-[[:space:]]*/ {gsub(/["'\'' ]/,""); sub(/^-/,""); print; next}
    f && /^[[:space:]]*[A-Za-z_]+:/ {f=0}
  ' "$wf")
  while IFS= read -r g; do
    [ -z "$g" ] && continue
    case "$g" in
      *'/**') sample="${g%/**}/_probe" ;;
      *'**')  sample="${g%\**}_probe" ;;
      *)      sample="$g" ;;
    esac
    if ! printf '%s\n' "$sample" | grep -qE "$DEPLOY_RE"; then
      echo "merge-policy: STALE GUARD — $wf lists deploy path '$g' not covered by DEPLOY_RE; update both together." >&2
      STALE=1
    fi
  done <<< "$globs"
}
# Resolve workflow dir relative to this script so it works from any CWD.
_wf_dir="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/.github/workflows"
_check_workflow_paths "$_wf_dir/deploy.yml"
_check_workflow_paths "$_wf_dir/deploy-api.yml"

# Resolve the PR for the current branch when not given.
if [ -z "$PR" ]; then
  PR="$(gh pr view "${repo_args[@]}" --json number -q .number 2>/dev/null || true)"
  [ -z "$PR" ] && { echo "merge-policy: no PR number given and none open for the current branch." >&2; exit 3; }
fi

j="$(mktemp)"; trap 'rm -f "$j"' EXIT
gh pr view "$PR" "${repo_args[@]}" \
  --json number,title,url,state,isDraft,mergeStateStatus,baseRefName,headRefName,files,statusCheckRollup \
  > "$j" 2>/dev/null || { echo "merge-policy: cannot read PR #$PR (wrong repo?)." >&2; exit 3; }

title=$(jq -r '.title' "$j")
url=$(jq -r '.url' "$j")
state=$(jq -r '.state' "$j")
base=$(jq -r '.baseRefName' "$j")
mss=$(jq -r '.mergeStateStatus' "$j")
draft=$(jq -r '.isDraft' "$j")

# Only an OPEN PR can be merged — guard against a false CLEARED on an already-merged/closed PR.
if [ "$state" != "OPEN" ]; then
  echo "PR #$PR — $title"
  echo "  $url"
  echo "VERDICT: BLOCKED — PR is $state, nothing to merge."
  exit 3
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
echo "  base=$base  mergeState=$mss  draft=$draft"
if [ "$sensitive" = 1 ]; then
  if [ -n "$deploy_hits" ]; then
    echo "  WEBSITE-SENSITIVE — diff touches deploy-trigger paths:"
    printf '%s\n' "$deploy_hits" | sed 's/^/      /'
  else
    echo "  WEBSITE-SENSITIVE — forced by staleness guard (deploy path list may have drifted)"
  fi
else
  echo "  non-deploy — merging will NOT trigger a live website/API deploy"
fi
echo "  checks: total=$total_checks failing=$failing pending=$pending"

# --- verdict ---
case "$mss" in
  DIRTY)  echo "VERDICT: BLOCKED — merge conflicts. Rebase onto origin/$base, then re-run."; exit 3 ;;
  BEHIND) echo "VERDICT: BLOCKED — stale base (branch is behind $base). Rebase onto current $base first (PR#111 silent-revert guard), then re-run."; exit 3 ;;
esac
if [ "$draft" = "true" ]; then
  echo "VERDICT: HOLD — PR is a draft. Mark ready, then re-run."; exit 2
fi
if [ "$failing" -gt 0 ]; then
  echo "VERDICT: HOLD — $failing CI check(s) failing. Fix before merge."; exit 2
fi
if [ "$sensitive" = 1 ]; then
  if [ "$pending" -gt 0 ] || [ "$total_checks" -eq 0 ]; then
    echo "VERDICT: HOLD — website-sensitive: a live deploy fires on merge and CI is not GREEN+COMPLETE (${pending} pending, ${total_checks} total). Wait for green; never blind-merge a deploy."
    exit 2
  fi
  echo "VERDICT: CLEARED — website-sensitive, but CI is fully green. Safe to self-merge; the live deploy is verified."
  exit 0
fi
if [ "$pending" -gt 0 ]; then
  echo "VERDICT: HOLD — ${pending} non-deploy check(s) still running. Merge once green."; exit 2
fi
echo "VERDICT: CLEARED — non-deploy PR, mergeable, no failing checks. Self-merge per the standing grant."
exit 0
