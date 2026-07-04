#!/usr/bin/env bash
# PreToolUse hook: auto-approve safe `cd <trusted-path> && <cmd> ...` chains.
#
# WHY: Claude Code v2.1.x prompts on EVERY compound `cd <dir> && <cmd>` (the
# "bare-repo / untrusted git hooks" guard, upstream #32985). No settings
# allow-rule suppresses it — not even Bash(*) — and worktree/fleet sessions run
# under `--permission-mode auto` (which overrides settings.defaultMode:
# bypassPermissions), so the guard is live and floods every job with "approve
# Bash" prompts. The autonomous fleet runs thousands of
# `cd <repo> && (git|python|pytest|node|npm|osascript) ...` per day.
#
# TRUST BOUNDARY = THE DIRECTORY, WITH A TAIL GUARD. If the cd target resolves
# inside a tree the user owns (~/Workspace, ~/Code, ~/.claude, a .claude
# worktree, ~/.claude/jobs, /tmp) OR is an in-tree relative path (the fleet only
# ever runs from an already-trusted cwd), normal read/build/test/git chains are
# auto-approved. Obvious destructive tails still fall through to Claude's normal
# guard, even in trusted directories. Any cd target OUTSIDE those trees — an
# absolute foreign dir, a `..` escape, or an unresolved variable we can't place
# — also falls through untouched, and a bare standalone command is unaffected.
#
# History:
#  - originally only handled the `git` case (cd\ *git*).
#  - 2026-06-24 generalized to the documented directory-trust design (absolute
#    trusted roots only).
#  - 2026-07-01 closed the fall-through prompts measured across fleet
#    transcripts: added ~/Code and ~/.claude to the trusted roots (the real
#    speech-score-engine lives at ~/Code and was 23/27 of all misses), taught it
#    to resolve $HOME / $CLAUDE_JOB_DIR / $CLAUDE_PROJECT_DIR targets instead of
#    matching them literally, trusted bare home (`cd ~`), and trusted in-tree
#    relative targets (`cd cli`, `cd web/app`) that carry no `..` escape and no
#    unresolved variable.
set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"

# Only consider commands that START by cd-ing somewhere.
case "$cmd" in
  cd\ *) : ;;
  *) exit 0 ;;
esac

# Extract the cd target from the FIRST physical line only: text after the
# leading `cd `, up to the first && or ; (later lines / clauses are irrelevant
# to where the shell lands).
first="$(printf '%s' "$cmd" | head -1)"
target="$(printf '%s' "$first" | sed -E 's/^cd[[:space:]]+//; s/[[:space:]]*(&&|;).*$//')"
tail_cmd=""
case "$first" in
  *"&&"*) tail_cmd="${first#*&&}" ;;
  *";"*)  tail_cmd="${first#*;}" ;;
esac
tail_cmd="$(printf '%s' "$tail_cmd" | sed -E 's/^[[:space:]]+//')"

# Strip surrounding quotes if present.
target="${target%\"}"; target="${target#\"}"
target="${target%\'}"; target="${target#\'}"

allow=0

# 1) Known-trusted env-var prefixes. Their value always resolves in-tree
#    ($CLAUDE_JOB_DIR -> ~/.claude/jobs/..., $CLAUDE_PROJECT_DIR -> the repo/
#    worktree), so trust the literal prefix without needing the value in-hook.
case "$target" in
  '$CLAUDE_JOB_DIR'|'$CLAUDE_JOB_DIR/'*|'${CLAUDE_JOB_DIR}'|'${CLAUDE_JOB_DIR}/'*) allow=1 ;;
  '$CLAUDE_PROJECT_DIR'|'$CLAUDE_PROJECT_DIR/'*|'${CLAUDE_PROJECT_DIR}'|'${CLAUDE_PROJECT_DIR}/'*) allow=1 ;;
esac

# 2) Controlled expansion of leading ~ and $HOME/${HOME} to the real home.
if [ "$allow" = 0 ]; then
  case "$target" in
    "~"*)        target="${HOME}${target#\~}" ;;
    '$HOME'*)    target="${HOME}${target#\$HOME}" ;;
    '${HOME}'*)  target="${HOME}${target#\$\{HOME\}}" ;;
  esac

  case "$target" in
    # Absolute trusted roots.
    "$HOME"|"$HOME/Workspace"|"$HOME/Workspace/"*) allow=1 ;;
    "$HOME/Code"|"$HOME/Code/"*)                   allow=1 ;;
    "$HOME/.claude"|"$HOME/.claude/"*)             allow=1 ;;
    *.claude/worktrees/*)                          allow=1 ;;  # relative or absolute
    /tmp|/tmp/*|/private/tmp/*)                     allow=1 ;;
    # Beyond the trusted roots: decide by shape.
    /*)     : ;;   # other absolute path -> foreign, stays protected
    *'$'*)  : ;;   # unresolved variable -> can't place it, stays protected
    *..*)   : ;;   # path escape -> stays protected
    *)      allow=1 ;;  # plain in-tree relative target (cwd is already trusted)
  esac
fi

# Destructive tails do not get auto-approved. They are not blocked here; they
# simply fall back to Claude's ordinary approval path.
danger=0
if [ -n "$tail_cmd" ]; then
  if printf '%s\n' "$tail_cmd" | grep -Eiq '(^|[;&|[:space:]])sudo([[:space:]]|$)|(^|[;&|[:space:]])rm[[:space:]]+-[^;&|[:space:]]*[rR][^;&|[:space:]]*|git[[:space:]]+reset[[:space:]]+--hard|git[[:space:]]+clean[[:space:]]+-[^;&|[:space:]]*[xdf]|(^|[;&|[:space:]])dd[[:space:]].*of=|(^|[;&|[:space:]])mkfs|(^|[;&|[:space:]])chmod[[:space:]]+-R|(^|[;&|[:space:]])chown[[:space:]]+-R|(curl|wget)[^;&]*[|][[:space:]]*(sh|bash)'; then
    danger=1
  fi
fi

if [ "$allow" = "1" ] && [ "$danger" = "0" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"Trusted cd target inside a user-owned tree (~/Workspace, ~/Code, ~/.claude, worktree, jobs, /tmp) or an in-tree relative path"}}\n'
fi
exit 0
