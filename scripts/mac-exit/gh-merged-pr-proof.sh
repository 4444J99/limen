#!/usr/bin/env bash
# READ-ONLY GitHub lookups that prove a local commit is already held by the repository, without fetching anything.
#
# WHY: two real shapes defeat local ancestry. (1) A squash- or rebase-merged branch never becomes an ancestor of the
# default branch, so the old "unpushed commit count" reported finished, merged work as unpushed. (2) A clone whose
# remote-tracking refs are behind (the remote moved forward since the last fetch) cannot prove, from local objects,
# that its tip is an ancestor of the remote's *new* tip. Both are answered by asking GitHub about the exact commit in
# the exact repository: branch names alone prove nothing. Python never builds gh arguments: it passes OWNER/REPO, a
# 40-hex SHA and plain branch names here, and validates what comes back.
#
# usage: gh-merged-pr-proof.sh OWNER/REPO SHA40 [DEFAULT_BRANCH|-] [CANDIDATE_BRANCH ...]
#
# Order of proof (first hit wins):
#   1. compare SHA...branch for each candidate branch (a remote head Python saw containing the tip), then the
#      default branch: status `ahead` or `identical` means the tip is an ancestor of that branch tip.
#      A 404 on the default-branch compare means GitHub has never seen this commit OR the token cannot read the
#      repository (GitHub answers both with 404): nothing else can prove it, and the reason says so.
#   2. a merged pull request in this repository whose head SHA equals SHA exactly, with the PR's merge commit on the
#      default branch (compare merge...default is `ahead`/`identical`).
#
# Exactly one TAB-separated line on stdout:
#   ANCESTOR <repo> <sha> <branch> <default_branch>                               exit 0
#   PROVEN   <repo> <sha> <pr_number> <merge_commit_sha> <default_branch>         exit 0
#   NONE     <repo> <sha> <reason> [<default_branch>]                             exit 1  (looked, no proof)
#   ERROR    <repo> <sha> <reason>                                                exit 2  (could not look: network,
#                                                                                         auth, rate limit, bad args)
# The caller must treat ERROR as "unknown": never as "not merged" and never as "merged".
#
# Only GETs: `gh pr list`, `gh api repos/...` (no -X, no -f/-F). Nothing is written to GitHub or to disk.

set -u

usage() {
  cat <<'USAGE'
usage: gh-merged-pr-proof.sh OWNER/REPO SHA40 [DEFAULT_BRANCH|-] [CANDIDATE_BRANCH ...]

Read-only GitHub lookups: is the commit SHA40 already held by OWNER/REPO (an ancestor of a branch, or the head of a
merged pull request)? One TAB-separated line on stdout:
  ANCESTOR <repo> <sha> <branch> <default_branch>                         exit 0
  PROVEN   <repo> <sha> <pr_number> <merge_commit_sha> <default_branch>   exit 0
  NONE     <repo> <sha> <reason> [<default_branch>]                       exit 1  (looked, no proof)
  ERROR    <repo> <sha> <reason>                                          exit 2  (could not look, or bad arguments)
USAGE
}
case "${1:-}" in
  -h | --help)
    usage
    exit 0
    ;;
esac

repo="${1:-}"
sha="${2:-}"
default_branch="${3:--}"
shift $(($# > 3 ? 3 : $#))
candidates=("$@")

emit() { # status, then the remaining fields; tabs and newlines inside fields are flattened
  local status="$1"
  shift
  local fields=() f
  for f in "$@"; do
    f="${f//$'\t'/ }"
    f="${f//$'\n'/ }"
    fields+=("${f:0:200}")
  done
  local IFS=$'\t'
  printf '%s\t%s\n' "$status" "${fields[*]}"
}

re_repo='^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9._-]+$'
re_sha='^[0-9a-f]{40}$'
re_branch='^[A-Za-z0-9._/-]+$'
if ! [[ "$repo" =~ $re_repo ]] || ! [[ "$sha" =~ $re_sha ]]; then
  usage >&2
  emit ERROR "${repo:-?}" "${sha:-?}" "bad-arguments"
  exit 2
fi
if [[ "$default_branch" == "-" ]]; then default_branch=""; fi
if [[ -n "$default_branch" ]] && ! [[ "$default_branch" =~ $re_branch ]]; then
  emit ERROR "$repo" "$sha" "bad-default-branch"
  exit 2
fi
valid_candidates=()
for b in "${candidates[@]+"${candidates[@]}"}"; do
  [[ "$b" =~ $re_branch ]] || continue
  valid_candidates+=("$b")
  [[ ${#valid_candidates[@]} -ge 3 ]] && break
done

export GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1 GH_SPINNER_DISABLED=1 NO_COLOR=1

is_404() { [[ "$1" == *"HTTP 404"* || "$1" == *"Not Found"* || "$1" == *"Could not resolve to a Repository"* ]]; }

# A failed gh call is a definite negative only for a 404; anything else (rate limit, 5xx, auth, DNS, timeout) means
# we did not get an answer. GitHub answers 404 both for "no such object" and for "a private repository you cannot
# read", so a 404 is labelled as either: it still proves nothing (NONE keeps the caller UNPROVEN) and never reads as
# "the work is not on GitHub".
fail() { # text
  local first
  first="$(printf '%s' "$1" | head -n 1)"
  if is_404 "$1"; then
    emit NONE "$repo" "$sha" "not-found-or-no-access: $first" "$default_branch"
    exit 1
  fi
  emit ERROR "$repo" "$sha" "gh: $first"
  exit 2
}

resolve_default() {
  [[ -n "$default_branch" ]] && return 0
  local out
  out="$(gh api "repos/$repo" --jq .default_branch 2>&1)"
  local rc=$?
  [[ $rc -eq 0 ]] || fail "$out"
  if ! [[ "$out" =~ $re_branch ]]; then
    emit ERROR "$repo" "$sha" "unparseable-default-branch"
    exit 2
  fi
  default_branch="$out"
}

# compare BASE...HEAD -> sets cmp_status; returns 0, or 4 for a 404; any other failure exits via fail().
# (Not called in a command substitution: fail() must be able to exit the script itself.)
cmp_status=""
compare_status() { # base head
  local out rc
  cmp_status=""
  out="$(gh api "repos/$repo/compare/$1...$2" --jq .status 2>&1)"
  rc=$?
  if [[ $rc -ne 0 ]]; then
    is_404 "$out" && return 4
    fail "$out"
  fi
  cmp_status="$out"
}

# 1. ancestry through GitHub, branch by branch: candidates first, then the default branch.
for b in "${valid_candidates[@]+"${valid_candidates[@]}"}"; do
  compare_status "$sha" "$b"
  rc=$?
  if [[ $rc -eq 0 && ( "$cmp_status" == "ahead" || "$cmp_status" == "identical" ) ]]; then
    emit ANCESTOR "$repo" "$sha" "$b" "$default_branch"
    exit 0
  fi
done
resolve_default
compare_status "$sha" "$default_branch"
rc=$?
if [[ $rc -eq 4 ]]; then
  emit NONE "$repo" "$sha" "commit-unknown-to-github-or-no-access" "$default_branch"
  exit 1
fi
if [[ "$cmp_status" == "ahead" || "$cmp_status" == "identical" ]]; then
  emit ANCESTOR "$repo" "$sha" "$default_branch" "$default_branch"
  exit 0
fi

# 2. squash/rebase-merged: --search matches any PR that *contains* the commit, so the head SHA is re-checked exactly.
out="$(gh pr list --repo "$repo" --state merged --search "$sha" --limit 20 --json number,headRefOid,mergeCommit \
  --jq ".[] | select(.headRefOid == \"$sha\") | select(.mergeCommit.oid != null) | [.number, .mergeCommit.oid] | @tsv" 2>&1)"
rc=$?
[[ $rc -eq 0 ]] || fail "$out"
if [[ -z "$out" ]]; then
  emit NONE "$repo" "$sha" "no-merged-pr-with-this-head-sha" "$default_branch"
  exit 1
fi

re_num='^[0-9]+$'
seen_merge=0
while IFS=$'\t' read -r number merge; do
  [[ "$number" =~ $re_num && "$merge" =~ $re_sha ]] || continue
  seen_merge=1
  # The merge commit must be an ancestor of (or equal to) the default branch tip. `behind` / `diverged` mean it is on
  # some other branch (a stacked PR not yet landed); a 404 means the merge commit is unknown (rewritten history).
  compare_status "$merge" "$default_branch"
  rc=$?
  [[ $rc -eq 4 ]] && continue
  if [[ "$cmp_status" == "ahead" || "$cmp_status" == "identical" ]]; then
    emit PROVEN "$repo" "$sha" "$number" "$merge" "$default_branch"
    exit 0
  fi
done <<<"$out"

if [[ $seen_merge -eq 1 ]]; then
  emit NONE "$repo" "$sha" "merge-commit-not-on-default-branch" "$default_branch"
else
  emit NONE "$repo" "$sha" "merged-pr-has-no-merge-commit" "$default_branch"
fi
exit 1
