#!/usr/bin/env bash
# Hermetic deny/pass matrix for scripts/hooks/worktree-commit-guard.sh — builds its own fake
# live root in mktemp so it never depends on the real checkout's branch state; CI-safe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$ROOT/scripts/hooks/worktree-commit-guard.sh"

FIX="$(mktemp -d)"
trap 'git -C "$FIX/limen" worktree prune >/dev/null 2>&1 || true; rm -rf "$FIX"' EXIT

LIVE="$FIX/limen"                                  # fake live checkout on main
git init -q -b main "$LIVE"
git -C "$LIVE" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
mkdir -p "$LIVE/cli"
git -C "$LIVE" worktree add -q -b feat/x "$LIVE/.claude/worktrees/wt" main
WT="$LIVE/.claude/worktrees/wt"
OTHER="$FIX/other"                                 # unrelated repo, also on main
git init -q -b main "$OTHER"
git -C "$OTHER" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init

payload() { python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]},"cwd":sys.argv[2]}))' "$1" "$2"; }
decision() { payload "$1" "$2" | LIMEN_LIVE_ROOT="$LIVE" "$HOOK"; }

assert_denied() { local out; out="$(decision "$1" "$2")"
  printf '%s' "$out" | grep -q '"permissionDecision":"deny"' || { printf 'expected deny: %s (cwd %s)\nout: %s\n' "$1" "$2" "$out" >&2; exit 1; }; }
assert_passes() { local out; out="$(decision "$1" "$2")"
  [ -z "$out" ] || { printf 'expected silent pass: %s (cwd %s)\nout: %s\n' "$1" "$2" "$out" >&2; exit 1; }; }

# THE dangerous lane: live checkout, main
assert_denied 'git commit -m x'                              "$LIVE"
assert_denied 'git add f && git commit -m x'                 "$LIVE"
assert_denied 'git commit --amend --no-edit'                 "$LIVE"
assert_denied 'git commit -m x'                              "$LIVE/cli"        # subdir → live toplevel
assert_denied "cd $LIVE && git commit -m x"                  "$WT"              # cd back into live from a worktree
assert_denied "git -C $WT commit -m safe && git -C $LIVE commit -m unsafe" "$WT" # every compound invocation is checked

# A path segment that merely looks like an isolation root is not proof of a linked
# worktree. Git still resolves this ordinary directory to the live checkout.
FAKE_WT="$LIVE/.worktrees/not-a-worktree"
mkdir -p "$FAKE_WT"
assert_denied 'git commit -m x'                              "$FAKE_WT"

# Legitimate lanes — must never block
assert_passes 'git commit -m x'                              "$WT"              # worktree session
assert_passes "cd $WT && git commit -m x"                    "$LIVE"            # cd-into-worktree compound
assert_passes 'cd .claude/worktrees/wt && git commit -m x'   "$LIVE"            # relative cd
assert_passes "git -C $WT commit -m x"                       "$LIVE"            # -C pins the dir
assert_passes "git -C $WT commit -m x && git -C $OTHER commit -m y" "$LIVE"     # every compound target is non-live
assert_passes 'git commit -m x'                              "$OTHER"           # other repo, even on main
assert_passes 'ls -la'                                       "$LIVE"            # non-git → prefilter
assert_passes 'git status --short && git log -1'             "$LIVE"            # git, no commit
assert_passes 'git log --grep "git commit"'                  "$LIVE"            # token inside quotes
assert_passes 'echo "git commit"'                            "$LIVE"
assert_passes 'scripts/ship-docs.sh slug "docs: x" docs/y.md' "$LIVE"           # ship-docs lane
assert_passes 'cd $SOMEWHERE && git commit -m x'             "$LIVE"            # unresolved var → fail open

# Project settings execute the guard from an isolation worktree with LIMEN_ROOT
# pointed at that worktree.  The guard must still derive the primary checkout from
# the shared Git directory when no explicit LIMEN_LIVE_ROOT is supplied.
DERIVED_HOOK="$WT/scripts/hooks/worktree-commit-guard.sh"
mkdir -p "$(dirname "$DERIVED_HOOK")"
cp "$HOOK" "$DERIVED_HOOK"
chmod +x "$DERIVED_HOOK"
out="$(payload "git -C $LIVE commit -m x" "$WT" | LIMEN_ROOT="$WT" LIMEN_LIVE_ROOT= "$DERIVED_HOOK")"
printf '%s' "$out" | grep -q '"permissionDecision":"deny"' || {
  printf 'expected derived-live-root deny; out: %s\n' "$out" >&2
  exit 1
}

# Parked live checkout (topic branch) → not this guard's lane
git -C "$LIVE" checkout -q -b chore/parked
assert_passes 'git commit -m x'                              "$LIVE"
git -C "$LIVE" checkout -q main

# Escape hatch
out="$(payload 'git commit -m x' "$LIVE" | LIMEN_LIVE_ROOT="$LIVE" LIMEN_ALLOW_LIVE_COMMIT=1 "$HOOK")"
[ -z "$out" ] || { echo "escape hatch failed: $out" >&2; exit 1; }

printf 'worktree-commit-guard.test: ok\n'
