#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/start-worktree-session.sh [--autonomous] [--agent auto|<canonical-lane>] [--conduct] [--shell] [--from <branch-or-ref>] [--prompt <text>] [--prompt-file <path>] [--runway <duration>] [--workstream <handle>] <repo-or-alias> <slug>

Examples:
  scripts/start-worktree-session.sh portvs triptych-story
  scripts/start-worktree-session.sh --agent claude portvs triptych-story
  scripts/start-worktree-session.sh --autonomous --agent auto --conduct --runway 8h --prompt-file /tmp/next-session.md limen next-epoch
  scripts/start-worktree-session.sh --shell --prompt-file /tmp/prompt.md domus package-map
  scripts/start-worktree-session.sh --workstream contributions --prompt 'drain the code lane' limen contrib-run

--agent selects and launches a native agent CLI. "auto" derives an available installed CLI from the
canonical Limen census. Omitting --agent creates the capsule without launching; its kickstart uses
the same live-derived Auto selection with a login-shell fallback.

--conduct registers the launched direct session with the shared broker as human-protected. Broker
credentials are read from the environment, never written into the capsule or command line, and
removed before the native agent process starts.

--workstream pins the worker to ONE purpose channel (contributions/correspondence/… — see
docs/lanes/). It is stamped into the kickoff packet so the session stays single-purpose.

--runway sets the finite workstream admission window (15m..30d; default 1d). The clock starts at the
first kickstart, survives successor sessions, and is never silently reset by a rerender.

--autonomous requires an explicit prompt and turns the README into the selected agent's initial prompt. The
packet defines live probes and completion/switch predicates; it never predeclares the ending.

Aliases:
  portvs, portus  /Users/4jp/Workspace/4444J99/portvs
  limen           /Users/4jp/Workspace/limen
  domus           /Users/4jp/Workspace/domus-genoma
  relpipe         /Users/4jp/Workspace/4444J99/relationship-pipeline

Creates or reuses:
  <repo>/.worktrees/<slug> on branch work/<slug>
  <repo>/.worktrees/<slug>/.limen-workstream/README.md as a thin prompt index
  <repo>/.worktrees/<slug>/.limen-workstream/{manifest,workstream,intent,runtime,closeout}.md
  <repo>/.worktrees/<slug>/docs/continuations/<slug>/workstream.json as a tracked redacted receipt

The target repo's .git/info/exclude is updated so .worktrees/ and the private
capsule never appear as Git noise. The receipt remains visible for commit and remote custody.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/lib/workstream-capsule.sh
source "$script_dir/lib/workstream-capsule.sh"

autonomous=0
launch_agent=0
launch_shell=0
conduct=0
requested_agent=""
from_ref=""
prompt_text=""
prompt_file=""
runway=""
runway_explicit=0
workstream=""
write_readme=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --autonomous)
      autonomous=1
      shift
      ;;
    --agent)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --agent" >&2
        usage >&2
        exit 2
      fi
      requested_agent="$2"
      launch_agent=1
      shift 2
      ;;
    --conduct)
      conduct=1
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
    --runway)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --runway" >&2
        usage >&2
        exit 2
      fi
      runway="$2"
      runway_explicit=1
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
if [[ "$launch_agent" -eq 1 && "$write_readme" -ne 1 ]]; then
  echo "--agent cannot be combined with --no-readme because launch requires a validated contract" >&2
  exit 2
fi
if [[ "$conduct" -eq 1 && "$write_readme" -ne 1 ]]; then
  echo "--conduct cannot be combined with --no-readme" >&2
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

contract_helper="$script_dir/../cli/src/limen/workstream_contract.py"
if [[ ! -f "$contract_helper" ]]; then
  echo "workstream contract helper not found: $contract_helper" >&2
  exit 1
fi
if [[ "$runway_explicit" -eq 1 ]]; then
  if ! normalized_runway="$(python3 "$contract_helper" normalize "$runway")"; then
    exit 2
  fi
  runway="${normalized_runway%%:*}"
fi

agent=""
registry_binary=""
agent_capabilities=""
allow_shell_fallback=1
if [[ -n "$requested_agent" ]]; then
  allow_shell_fallback=0
fi
agent_resolution="$(
  PYTHONPATH="$script_dir/../cli/src${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - "${requested_agent:-auto}" <<'PY'
import os
import shutil
import sys

from limen.census import VENDORS, by_name, canonical


def candidates(vendor):
    env_key = f"LIMEN_{vendor.name.upper().replace('-', '_')}_BIN"
    override = os.environ.get(env_key, "").strip()
    values = (override, vendor.name, vendor.binary if vendor.binary == vendor.name else "")
    return tuple(dict.fromkeys(value for value in values if value))


def direct_native(vendor):
    profile = getattr(vendor, "execution", None)
    if profile is None:
        return vendor.local_checkout
    return profile.transport == "native-cli" or profile.transport.startswith("ianva-")


requested = sys.argv[1].strip().lower()
if requested == "auto":
    preferred = canonical(os.environ.get("LIMEN_AGENT"))
    ordered = list(VENDORS)
    if preferred and by_name(preferred):
        ordered.sort(key=lambda vendor: vendor.name != preferred)
    eligible = [
        vendor
        for vendor in ordered
        if vendor.status.available and vendor.status.state == "live" and direct_native(vendor)
    ]
    selected = next(
        (
            (vendor, binary)
            for vendor in eligible
            for binary in candidates(vendor)
            if shutil.which(binary)
        ),
        None,
    )
    if selected is None:
        if not eligible:
            raise SystemExit("no live canonical Limen lane supports native execution")
        vendor = eligible[0]
        binary = next(iter(candidates(vendor)), vendor.name)
    else:
        vendor, binary = selected
else:
    name = canonical(requested)
    vendor = by_name(name)
    if vendor is None:
        allowed = ", ".join(item.name for item in VENDORS)
        raise SystemExit(f"unknown Limen agent lane {requested!r}; canonical lanes: {allowed}")
    binary = next((item for item in candidates(vendor) if shutil.which(item)), vendor.name)

print(vendor.name)
print(binary)
profile = getattr(vendor, "execution", None)
capabilities = profile.capabilities if profile is not None else frozenset({"code", "conduct", "review"})
print(" ".join(sorted(capabilities)))
PY
)"
agent="$(printf '%s\n' "$agent_resolution" | sed -n '1p')"
registry_binary="$(printf '%s\n' "$agent_resolution" | sed -n '2p')"
agent_capabilities="$(printf '%s\n' "$agent_resolution" | sed -n '3p')"
if [[ "$launch_agent" -eq 1 ]] && ! workstream_native_binary "$agent" "$registry_binary" >/dev/null; then
  echo "native CLI not found for canonical lane $agent" >&2
  exit 127
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
echo "agent: $agent"
[[ "$conduct" -eq 1 ]] && echo "conduct: human-protected direct session"

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

  render_workstream_capsule \
    "$wt" "$repo" "$slug" "$branch" "$workstream" "$from_ref" "$autonomous" \
    "$prompt_payload" "$script_dir/../spec/continuation-capsule" "$runway" "$contract_helper" \
    "$agent" "$registry_binary" "$conduct" "$allow_shell_fallback" "$agent_capabilities"
fi

if [[ "$launch_agent" -eq 1 ]]; then
  exec bash "$wt/.limen-workstream/kickstart.sh"
fi

if [[ "$launch_shell" -eq 1 ]]; then
  cd "$wt"
  exec "${SHELL:-/bin/zsh}" -l
fi

echo
echo "Next:"
echo "  cd $wt"
if [[ "$write_readme" -eq 1 ]]; then
  echo "  bash $wt/.limen-workstream/kickstart.sh"
else
  echo "  $registry_binary"
fi
