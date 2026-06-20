#!/usr/bin/env bash
# merge-ready.sh — ship the fleet's CLEAN PRs in priority order, the moment merging is authorized.
#
# The fleet builds ~hundreds of PRs; ~half are CLEAN (green CI, no conflicts) but mass cross-org
# merge is auto-mode-classifier-GATED. This is the prepared one-command crossing: it queries the
# user's open PRs LIVE (so the CLEAN set is always current as CIFIX greens more), filters to
# mergeStateStatus=CLEAN, EXCLUDES known junk/dup (test fixtures + obvious re-dispatch dups),
# orders revenue-first (the a-i-chat--exporter chain ships first), and merges.
#
# SAFE: dry-run by DEFAULT (prints the plan). --apply actually merges. Even with --apply this is
# the user's authorized action — run it yourself, or grant `Bash(gh pr merge:*)` so the agent may.
# Per-PR --squash keeps history clean; a failed merge is logged and skipped (never aborts the run).
#
# Usage:  bash scripts/merge-ready.sh            # dry-run plan
#         bash scripts/merge-ready.sh --apply    # actually merge the clean set
#         bash scripts/merge-ready.sh --apply --limit 8   # ship just the first N (e.g. exporter)
set -euo pipefail
APPLY=0; LIMIT=0
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --limit) shift; ;;            # handled below
    --limit=*) LIMIT="${a#*=}" ;;
  esac
done
# allow "--limit N" form
prev=""; for a in "$@"; do [ "$prev" = "--limit" ] && LIMIT="$a"; prev="$a"; done

# Revenue repos merge FIRST (ship dollars before archives). Extend freely.
PRIORITY_REPOS="a-organvm/a-i-chat--exporter a-organvm/public-record-data-scrapper a-organvm/mirror-mirror 4444J99/domus-genoma"
# Title patterns that mark junk/dup (never merge these) — test fixtures + the known leak.
JUNK_RE='Open Codex task (one|two|three)'

tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
echo "→ querying your open PRs + merge state (live)…" >&2
# paginated: gh search caps at 100, so use the search API
gh api -X GET search/issues --paginate -f q="is:pr is:open author:@me" \
  --jq '.items[] | [(.repository_url|sub(".*/repos/";"")), .number, .title] | @tsv' 2>/dev/null \
  | while IFS=$'\t' read -r repo num title; do
      [ -z "$repo" ] && continue
      echo "$title" | grep -qE "$JUNK_RE" && continue   # skip junk
      state=$(gh pr view "$num" --repo "$repo" --json mergeStateStatus -q .mergeStateStatus 2>/dev/null || echo "?")
      [ "$state" = "CLEAN" ] && printf '%s\t%s\t%s\n' "$repo" "$num" "$title" >> "$tmp"
    done

# order: priority repos first (in listed order), then the rest
order_file="$(mktemp)"; trap 'rm -f "$tmp" "$order_file"' EXIT
for r in $PRIORITY_REPOS; do grep -P "^${r}\t" "$tmp" 2>/dev/null >> "$order_file" || true; done
for r in $PRIORITY_REPOS; do grep -vP "^${r}\t" "$tmp" > "${tmp}.x" 2>/dev/null && mv "${tmp}.x" "$tmp" || true; done
cat "$tmp" >> "$order_file"

total=$(wc -l < "$order_file" | tr -d ' ')
echo "→ $total CLEAN, non-junk PRs ready to merge (revenue-first order):" >&2
n=0
while IFS=$'\t' read -r repo num title; do
  [ -z "$repo" ] && continue
  n=$((n+1))
  [ "$LIMIT" -gt 0 ] && [ "$n" -gt "$LIMIT" ] && { echo "  …(stopped at --limit $LIMIT)"; break; }
  if [ "$APPLY" = 1 ]; then
    if gh pr merge "$num" --repo "$repo" --squash --delete-branch >/dev/null 2>&1; then
      echo "  ✓ merged  $repo#$num  $title"
    else
      echo "  ✗ FAILED  $repo#$num (skipped — check manually)"
    fi
  else
    echo "  would merge  $repo#$num  $title"
  fi
done < "$order_file"
[ "$APPLY" = 0 ] && echo "→ dry-run. Re-run with --apply to merge (or grant Bash(gh pr merge:*))." >&2
