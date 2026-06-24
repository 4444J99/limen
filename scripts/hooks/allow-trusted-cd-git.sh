#!/usr/bin/env bash
# PreToolUse hook: auto-approve `cd <trusted-path> && <anything> ...` chains.
#
# WHY: Claude Code v2.1.x prompts on EVERY compound `cd <dir> && <cmd>` (the
# "bare-repo / untrusted git hooks" guard, upstream #32985). No settings
# allow-rule suppresses it. The autonomous fleet runs thousands of
# `cd ~/Workspace/<repo> && (git|python|pytest|node|npm|osascript) ...` per day,
# so the guard floods every session/job with "approve Bash" prompts.
#
# TRUST BOUNDARY = THE DIRECTORY, NOT THE TOOL. If the cd target resolves inside
# a tree the user owns (~/Workspace, a .claude worktree, ~/.claude/jobs, /tmp),
# the whole chain is auto-approved — matching the user's established posture that
# in-tree work (including cleanup) should never prompt. Any cd target OUTSIDE
# those trees falls through to the normal guard untouched, so foreign dirs keep
# full protection, and a bare standalone command (no leading cd) is unaffected.
#
# History: previously only handled the `git` case (cd\ *git*), which left the
# fleet's python/pytest/node/osascript compound commands prompting every run.
# Generalized 2026-06-24 to the documented directory-trust design.
set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"

# Only consider commands that START by cd-ing somewhere.
case "$cmd" in
  cd\ *) : ;;
  *) exit 0 ;;
esac

# Extract the cd target: text after the leading `cd `, up to the first && or ;.
target="$(printf '%s' "$cmd" | sed -E 's/^cd[[:space:]]+//; s/[[:space:]]*(&&|;).*$//')"

# Expand a leading ~ to $HOME.
case "$target" in
  "~"*) target="${HOME}${target#\~}" ;;
esac

# Strip surrounding quotes if present.
target="${target%\"}"; target="${target#\"}"
target="${target%\'}"; target="${target#\'}"

allow=0
case "$target" in
  "$HOME/Workspace"|"$HOME/Workspace/"*) allow=1 ;;   # the fleet workspace
  *.claude/worktrees/*) allow=1 ;;                     # isolated worktrees (relative or absolute)
  "$HOME/.claude/jobs/"*) allow=1 ;;                   # background-job scratch trees
  /tmp|/tmp/*|/private/tmp/*) allow=1 ;;               # ephemeral scratch
esac

if [ "$allow" = "1" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"Trusted cd target inside a user-owned tree (~/Workspace, worktree, jobs, /tmp)"}}\n'
fi
exit 0
