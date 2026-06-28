#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/start-worktree-session.sh [--codex] [--shell] [--from <branch-or-ref>] <repo-or-alias> <slug>

Examples:
  scripts/start-worktree-session.sh portvs triptych-story
  scripts/start-worktree-session.sh --codex portvs triptych-story

Aliases:
  portvs, portus  /Users/4jp/Workspace/4444J99/portvs
  limen           /Users/4jp/Workspace/limen

Creates or reuses:
  <repo>/.worktrees/<slug> on branch work/<slug>

The target repo's .git/info/exclude is updated so .worktrees/ never appears as noise.
USAGE
}

launch_codex=0
launch_shell=0
from_ref=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --codex)
      launch_codex=1
      shift
      ;;
    --shell)
      launch_shell=1
      shift
      ;;
    --from)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --from" >&2
        usage >&2
        exit 2
      fi
      from_ref="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -ne 2 ]]; then
  usage >&2
  exit 2
fi

repo_arg="$1"
raw_slug="$2"

case "$repo_arg" in
  portvs|portus)
    repo="/Users/4jp/Workspace/4444J99/portvs"
    ;;
  limen)
    repo="/Users/4jp/Workspace/limen"
    ;;
  *)
    if [[ -d "$repo_arg" ]]; then
      repo="$repo_arg"
    elif [[ -d "/Users/4jp/Workspace/$repo_arg" ]]; then
      repo="/Users/4jp/Workspace/$repo_arg"
    elif [[ -d "/Users/4jp/Workspace/4444J99/$repo_arg" ]]; then
      repo="/Users/4jp/Workspace/4444J99/$repo_arg"
    else
      echo "repo not found: $repo_arg" >&2
      exit 1
    fi
    ;;
esac

repo="$(cd "$repo" && pwd -P)"
if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not a git repo: $repo" >&2
  exit 1
fi

slug="$(
  printf '%s' "$raw_slug" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//'
)"
if [[ -z "$slug" ]]; then
  echo "slug collapsed to empty: $raw_slug" >&2
  exit 1
fi

branch="work/$slug"
wt="$repo/.worktrees/$slug"

git_info_dir="$(git -C "$repo" rev-parse --path-format=absolute --git-path info)"
mkdir -p "$git_info_dir"
exclude_file="$git_info_dir/exclude"
touch "$exclude_file"
if ! grep -qxF ".worktrees/" "$exclude_file"; then
  {
    printf '\n'
    printf '.worktrees/\n'
  } >> "$exclude_file"
fi

if [[ -z "$from_ref" ]]; then
  origin_head="$(git -C "$repo" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [[ -n "$origin_head" ]]; then
    from_ref="$origin_head"
  elif git -C "$repo" show-ref --verify --quiet refs/remotes/origin/main; then
    from_ref="origin/main"
  else
    from_ref="$(git -C "$repo" branch --show-current)"
  fi
fi

mkdir -p "$(dirname "$wt")"

if [[ -d "$wt" ]]; then
  if ! git -C "$wt" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "path exists but is not a git worktree: $wt" >&2
    exit 1
  fi
  created="reused"
elif git -C "$repo" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$repo" worktree add "$wt" "$branch" >/dev/null
  created="created"
else
  git -C "$repo" worktree add -b "$branch" "$wt" "$from_ref" >/dev/null
  created="created"
fi

echo "$created worktree: $wt"
echo "branch: $branch"

if [[ "$launch_codex" -eq 1 ]]; then
  cd "$wt"
  exec codex
fi

if [[ "$launch_shell" -eq 1 ]]; then
  cd "$wt"
  exec "${SHELL:-/bin/zsh}" -l
fi

echo
echo "Next:"
echo "  cd $wt"
echo "  codex"
