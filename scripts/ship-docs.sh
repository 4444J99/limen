#!/usr/bin/env bash
# ship-docs.sh — one-shot PR-native shipping for docs-class changes.
#
# THE SIDE-DOOR CLOSER. The `docs: review … run` append class was landing as direct
# commits to main (35 of 40 recent main commits bypassed PRs) because no tool made
# the charter's branch cadence a single command. This does: it stages ONLY the named
# files onto a fresh branch cut from origin/main inside an isolated worktree — your
# current checkout (branch, dirt, daemon contention) is never touched — opens the PR,
# and self-merges the moment scripts/merge-policy.sh clears it (the standing grant).
#
#   scripts/ship-docs.sh <slug> "<commit msg>" <file> [file…]
#   e.g. scripts/ship-docs.sh agent-review "docs: review codex exporter run" docs/agent-code-diff-review.md
#
# Guardrails:
#   • named files only — never `git add -A` (charter § Edits Policy);
#   • refuses website-sensitive deploy-trigger paths (those need the full worktree
#     flow + green CI — keep this list in lockstep with merge-policy.sh + deploy*.yml);
#   • refuses tasks.yaml — the board is single-writer via the keeper (#594);
#   • exit 0 = merged · 2 = PR open awaiting policy (HOLD/BLOCKED) · 1 = refused/failed.
set -euo pipefail

die() { echo "ship-docs: $*" >&2; exit 1; }

[ "$#" -ge 3 ] || die "usage: ship-docs.sh <slug> \"<commit msg>\" <file> [file…]"
slug="$1"; msg="$2"; shift 2
case "$slug" in *[!a-zA-Z0-9._-]*) die "slug must be [a-zA-Z0-9._-]" ;; esac

root="$(git rev-parse --show-toplevel)"
for f in "$@"; do
  case "$f" in
    /*) die "paths must be repo-relative: $f" ;;
    web/app/*|web/api/*|cli/*|firebase.json|.github/workflows/deploy.yml|.github/workflows/deploy-api.yml|scripts/preflight-cloud-run.sh)
      die "website-sensitive path '$f' — use the full worktree flow with green CI, not ship-docs" ;;
    tasks.yaml) die "the board is single-writer via the keeper — never ship tasks.yaml by hand" ;;
  esac
  [ -f "$root/$f" ] || die "no such file in checkout: $f"
done

git -C "$root" fetch origin main --quiet
br="docs/${slug}-$(date -u +%Y%m%d%H%M%S)"
if [ -n "${LIMEN_WORKTREES:-}" ]; then
  wt_root="$LIMEN_WORKTREES"
elif [ -d /Volumes/Scratch ] && [ -w /Volumes/Scratch ]; then
  wt_root="/Volumes/Scratch/limen-worktrees"
else
  wt_root="${LIMEN_WORKDIR:-$HOME/Workspace}/.limen-worktrees"
fi
mkdir -p "$wt_root"
tmp="$wt_root/ship-docs-${slug}-$(date -u +%Y%m%d%H%M%S)-$$"
cleanup() {
  echo "ship-docs: retained local worktree $tmp"
  echo "ship-docs: retained local/remote branch $br"
  echo "ship-docs: cleanup delegated to docs/worktree-reclaim-acceptance.jsonl + reclaim-worktrees.py and docs/branch-reap-acceptance.jsonl + reap-branches.py"
}
trap cleanup EXIT

git -C "$root" worktree add --quiet -b "$br" "$tmp" origin/main
for f in "$@"; do
  mkdir -p "$tmp/$(dirname "$f")"
  cp "$root/$f" "$tmp/$f"
  git -C "$tmp" add -- "$f"
done
if git -C "$tmp" diff --cached --quiet; then
  echo "ship-docs: named files are identical to origin/main — nothing to ship"
  exit 0
fi
git -C "$tmp" commit --quiet -m "$msg"
git -C "$tmp" push --quiet -u origin "$br"

pr_url="$(cd "$tmp" && gh pr create --title "$msg" \
  --body "Shipped via \`scripts/ship-docs.sh\` — the PR-native path for the docs-append class (charter § Merge & Branch Protocol, \"No side doors\").")"
pr_num="${pr_url##*/}"
echo "ship-docs: opened PR #$pr_num ($pr_url)"

if "$root/scripts/merge-policy.sh" "$pr_num"; then
  # Record the adjudication as a review (self-authored → --comment; GitHub forbids self-approve).
  # The merge-policy verdict IS the review; recording it makes the code-review work visible.
  gh pr review "$pr_num" --comment --body \
    "Adjudicated by merge-policy.sh: CLEARED (non-deploy or green-CI website path). Squash-merge per the standing grant (CLAUDE.md § Merge & Branch Protocol)." \
    >/dev/null 2>&1 || true
  gh pr merge "$pr_num" --squash
  echo "ship-docs: merged #$pr_num (merge-policy CLEARED; branch retained)"
  exit 0
else
  rc=$?
  echo "ship-docs: PR #$pr_num left open — merge-policy exit $rc (HOLD=wait for green, BLOCKED=rebase)"
  exit 2
fi
