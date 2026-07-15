#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/start-worktree-session.sh [--autonomous] [--codex] [--shell] [--from <branch-or-ref>] [--prompt <text>] [--prompt-file <path>] [--workstream <handle>] <repo-or-alias> <slug>

Examples:
  scripts/start-worktree-session.sh portvs triptych-story
  scripts/start-worktree-session.sh --codex portvs triptych-story
  scripts/start-worktree-session.sh --autonomous --codex --prompt-file /tmp/next-session.md limen next-epoch
  scripts/start-worktree-session.sh --shell --prompt-file /tmp/prompt.md domus package-map
  scripts/start-worktree-session.sh --workstream contributions --prompt 'drain the code lane' limen contrib-run

--workstream pins the worker to ONE purpose channel (contributions/correspondence/… — see
docs/lanes/). It is stamped into the kickoff packet so the session stays single-purpose.

--autonomous requires an explicit prompt and turns the README into the initial Codex prompt. The
packet defines live probes and completion/switch predicates; it never predeclares the ending.

Aliases:
  portvs, portus  /Users/4jp/Workspace/4444J99/portvs
  limen           /Users/4jp/Workspace/limen
  domus           /Users/4jp/Workspace/domus-genoma
  relpipe         /Users/4jp/Workspace/4444J99/relationship-pipeline

Creates or reuses:
  <repo>/.worktrees/<slug> on branch work/<slug>
  <repo>/.worktrees/<slug>/.limen-workstream/README.md as a thin prompt index
  <repo>/.worktrees/<slug>/.limen-workstream/{manifest,intent,runtime,closeout}.md

The target repo's .git/info/exclude is updated so .worktrees/ and the private
capsule never appear as Git noise.
USAGE
}

autonomous=0
launch_codex=0
launch_shell=0
from_ref=""
prompt_text=""
prompt_file=""
workstream=""
write_readme=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --autonomous)
      autonomous=1
      shift
      ;;
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
    --prompt)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --prompt" >&2
        usage >&2
        exit 2
      fi
      prompt_text="$2"
      shift 2
      ;;
    --prompt-file)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --prompt-file" >&2
        usage >&2
        exit 2
      fi
      prompt_file="$2"
      shift 2
      ;;
    --workstream|--ws)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --workstream" >&2
        usage >&2
        exit 2
      fi
      workstream="$2"
      shift 2
      ;;
    --no-readme)
      write_readme=0
      shift
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

if [[ "$autonomous" -eq 1 && "$write_readme" -ne 1 ]]; then
  echo "--autonomous cannot be combined with --no-readme" >&2
  exit 2
fi
if [[ "$autonomous" -eq 1 && -z "$prompt_text" && -z "$prompt_file" ]]; then
  echo "--autonomous requires --prompt or --prompt-file" >&2
  exit 2
fi
if [[ -n "$prompt_file" && ! -f "$prompt_file" ]]; then
  echo "prompt file not found: $prompt_file" >&2
  exit 1
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
  domus|domus-genoma)
    repo="/Users/4jp/Workspace/domus-genoma"
    ;;
  relationship-pipeline|relpipe|maddie)
    repo="/Users/4jp/Workspace/4444J99/relationship-pipeline"
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

if [[ -n "$workstream" ]]; then
  workstream="$(
    printf '%s' "$workstream" \
      | tr '[:upper:]' '[:lower:]' \
      | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
  )"
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
if ! grep -qxF ".limen-workstream/" "$exclude_file"; then
  {
    printf '\n'
    printf '.limen-workstream/\n'
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
[[ -n "$workstream" ]] && echo "workstream: $workstream"

if [[ "$write_readme" -eq 1 ]]; then
  capsule_dir="$wt/.limen-workstream"
  readme="$capsule_dir/README.md"

  if [[ -n "$prompt_file" ]]; then
    prompt_payload="$(cat "$prompt_file")"
  elif [[ -n "$prompt_text" ]]; then
    prompt_payload="$prompt_text"
  else
    prompt_payload="No explicit prompt was supplied. Add one bounded objective and its owner contract before execution."
  fi

  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  # shellcheck source=scripts/lib/workstream-capsule.sh
  source "$script_dir/lib/workstream-capsule.sh"
  render_workstream_capsule \
    "$wt" "$repo" "$slug" "$branch" "$workstream" "$from_ref" "$autonomous" \
    "$prompt_payload" "$script_dir/../spec/continuation-capsule"
fi

if [[ "$launch_codex" -eq 1 ]]; then
  cd "$wt"
  if [[ "$autonomous" -eq 1 ]]; then
    capsule_prompt=""
    IFS= read -r -d '' capsule_prompt < "$readme" || true
    exec codex "$capsule_prompt"
  fi
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
