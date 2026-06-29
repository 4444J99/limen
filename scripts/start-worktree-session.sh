#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/start-worktree-session.sh [--codex] [--shell] [--from <branch-or-ref>] [--prompt <text>] [--prompt-file <path>] <repo-or-alias> <slug>

Examples:
  scripts/start-worktree-session.sh portvs triptych-story
  scripts/start-worktree-session.sh --codex portvs triptych-story
  scripts/start-worktree-session.sh --shell --prompt-file /tmp/prompt.md domus package-map

Aliases:
  portvs, portus  /Users/4jp/Workspace/4444J99/portvs
  limen           /Users/4jp/Workspace/limen
  domus           /Users/4jp/Workspace/domus-genoma
  relpipe         /Users/4jp/Workspace/4444J99/relationship-pipeline

Creates or reuses:
  <repo>/.worktrees/<slug> on branch work/<slug>
  <repo>/.worktrees/<slug>/.limen-workstream/README.md

The target repo's .git/info/exclude is updated so .worktrees/ and the private
workstream README never appear as Git noise.
USAGE
}

launch_codex=0
launch_shell=0
from_ref=""
prompt_text=""
prompt_file=""
write_readme=1

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

if [[ "$write_readme" -eq 1 ]]; then
  readme_dir="$wt/.limen-workstream"
  readme="$readme_dir/README.md"
  kickstart="$readme_dir/kickstart.sh"
  mkdir -p "$readme_dir"

  if [[ -n "$prompt_file" ]]; then
    if [[ ! -f "$prompt_file" ]]; then
      echo "prompt file not found: $prompt_file" >&2
      exit 1
    fi
    prompt_payload="$(cat "$prompt_file")"
  elif [[ -n "$prompt_text" ]]; then
    prompt_payload="$prompt_text"
  else
    prompt_payload="No explicit prompt was supplied. Add the current ask, constraints, and evidence links here before starting long work."
  fi

  now_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  head_short="$(git -C "$wt" rev-parse --short HEAD)"
  upstream_ref="$(git -C "$wt" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  origin_url="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
  status_line="$(git -C "$wt" status --short --branch | head -n 1)"
  readme_action="wrote"

  cat > "$readme" <<EOF
# Workstream: $slug

Created: $now_utc

## Location

- Repo: \`$repo\`
- Worktree: \`$wt\`
- Branch: \`$branch\`
- Base ref: \`$from_ref\`
- HEAD: \`$head_short\`
- Upstream: \`${upstream_ref:-none yet}\`
- Origin: \`${origin_url:-none}\`
- Status at kickoff: \`$status_line\`

## Kickstart Command

\`\`\`bash
bash "$kickstart"
\`\`\`

That command works from Terminal, Kitty, Ghostty, Warp, or any normal shell. The expanded command is:

\`\`\`bash
cd "$wt"
if git remote get-url origin >/dev/null 2>&1; then
  git fetch --prune
fi
git status --short --branch
codex
\`\`\`

For a plain shell instead of Codex:

\`\`\`bash
cd "$wt"
\${SHELL:-/bin/zsh} -l
\`\`\`

## Prompt Packet

$prompt_payload

## First Five Minutes

1. Re-read the nearest \`AGENTS.md\` or project instruction file.
2. Check local/remote state: \`git status --short --branch\`, \`git branch -vv\`, \`git remote -v\`.
3. Identify generated/heavy directories before running builds.
4. Write the smallest source diff that moves the workstream.
5. Commit and push source work before deleting or reclaiming local state.

## Closeout Rules

- Do not leave Git-visible generated files unclassified.
- Push useful source commits or create a remote receipt before local cleanup.
- First source push from a new workstream branch: \`git push -u origin HEAD\`.
- Keep private data in ignored/private paths; summarize evidence instead of pasting secrets or personal content.
- If the workstream creates large media, write a manifest first, then choose archive/offload/regenerate policy before deleting.
- Final report must include changed paths, verification command, local/remote status, and any deletion/offload decision still waiting on the human.
EOF
  cat > "$kickstart" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$wt"
if git remote get-url origin >/dev/null 2>&1; then
  git fetch --prune
fi
git status --short --branch
if command -v codex >/dev/null 2>&1; then
  exec codex
fi
exec "\${SHELL:-/bin/zsh}" -l
EOF
  chmod +x "$kickstart"

  echo "workstream readme: $readme ($readme_action)"
  echo "kickstart command: bash $kickstart"
fi

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
