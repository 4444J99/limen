#!/usr/bin/env bash
# pre-build-excavate.sh — the executable predicate for "did a parallel session already SHIP this?"
#
# This is a LIVE multi-agent fleet: many sessions build against the same repos at once. On
# 2026-07-03 a session built an entire MONETA payment-rail PR (#108) on `a-i-chat--exporter`
# for a rail another session had ALREADY merged as #107 — because it mapped the repo's *code*
# but never checked its *PR/commit stream* first. That whole build was wasted and reverted.
# See memory `excavate-before-redoing-solved-work`.
#
# The lesson used to live only as prose. This is its enforceable form: run it BEFORE you build
# or edit anything substantive on a shared fleet repo. It surfaces what already shipped or is
# in flight, so you read that FIRST instead of rebuilding it. Cheap: a few `gh`/`git` reads.
#
#   exit 0  CLEAR      — enumerated the streams; no supplied keyword matched an existing PR or
#                        recent commit. Safe to build (still read the lists it printed).
#   exit 3  LIKELY-DUP — a supplied keyword matched an open/merged/closed PR title or a recent
#                        commit subject. STOP and read those before building — you may be about
#                        to rebuild shipped or in-flight work.
#   exit 2  DEGRADED   — could not reach the repo (gh unauthenticated/offline, bad repo name).
#                        Fail-open: it does NOT clear you, but it does not hard-block either.
#                        Resolve the tooling and re-run before trusting a CLEAR.
#
# Usage:  scripts/pre-build-excavate.sh <owner/repo> [keyword ...]
#         scripts/pre-build-excavate.sh organvm/a-i-chat--exporter moneta checkout licence
#         (keywords are optional; with none it is informational and always exits 0/2)
set -euo pipefail

REPO="${1:-}"
if [ -z "$REPO" ] || [ "$REPO" = "-h" ] || [ "$REPO" = "--help" ]; then
  sed -n '2,27p' "$0"
  [ -z "$REPO" ] && exit 2 || exit 0
fi
shift || true
KEYWORDS="$*"

command -v gh >/dev/null 2>&1 || { echo "DEGRADED: gh CLI not found — cannot check the PR stream." >&2; exit 2; }

# One cheap call per stream; tolerate any failure by degrading rather than raising (fleet ethos).
OPEN_PRS="$(gh pr list --repo "$REPO" --state open  --limit 50 \
              --json number,title,author --jq '.[] | "#\(.number)\t[open]\t@\(.author.login)\t\(.title)"' 2>/dev/null)" || OPEN_PRS=""
DONE_PRS="$(gh pr list --repo "$REPO" --state all   --limit 40 \
              --json number,title,state,mergedAt --jq '.[] | select(.state!="OPEN") | "#\(.number)\t[\(.state|ascii_downcase)]\t\(.title)"' 2>/dev/null)" || DONE_PRS=""
COMMITS="$(gh api "repos/$REPO/commits?per_page=20" \
              --jq '.[] | "\(.sha[0:7])\t\(.commit.message | split("\n")[0])"' 2>/dev/null)" || COMMITS=""

# If every stream came back empty AND gh itself errors on the repo, we could not reach it.
if [ -z "$OPEN_PRS$DONE_PRS$COMMITS" ]; then
  if ! gh repo view "$REPO" >/dev/null 2>&1; then
    echo "DEGRADED: could not reach '$REPO' (unauthenticated, offline, or wrong name)." >&2
    exit 2
  fi
  # Reachable but genuinely empty (brand-new repo): fall through as CLEAR.
fi

hr() { printf '%s\n' "----------------------------------------------------------------------"; }
echo "EXCAVATION — $REPO"
[ -n "$KEYWORDS" ] && echo "keywords: $KEYWORDS"
hr
echo "OPEN PRs (in flight — a parallel session may be shipping your idea RIGHT NOW):"
printf '%s\n' "${OPEN_PRS:-  (none)}"
hr
echo "RECENTLY MERGED / CLOSED PRs (already shipped or already rejected):"
printf '%s\n' "${DONE_PRS:-  (none)}"
hr
echo "RECENT COMMITS on the default branch:"
printf '%s\n' "${COMMITS:-  (none)}"
hr

# With keywords, become a real gate: any hit → LIKELY-DUP (exit 3). bash 3.2 safe, case-insensitive.
if [ -n "$KEYWORDS" ]; then
  HAYSTACK="$(printf '%s\n%s\n%s\n' "$OPEN_PRS" "$DONE_PRS" "$COMMITS")"
  HITS=""
  for kw in $KEYWORDS; do
    match="$(printf '%s\n' "$HAYSTACK" | grep -i -- "$kw" 2>/dev/null || true)"
    [ -n "$match" ] && HITS="$HITS"$'\n'"── matches for '$kw' ──"$'\n'"$match"
  done
  if [ -n "$HITS" ]; then
    echo "LIKELY-DUP: a keyword matched existing PR/commit history. READ THESE BEFORE BUILDING:"
    printf '%s\n' "$HITS"
    hr
    exit 3
  fi
  echo "CLEAR: no keyword matched the PR/commit stream. Safe to build (still skim the lists above)."
fi
exit 0
