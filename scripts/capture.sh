#!/usr/bin/env bash
# capture.sh — the CAPTURE organ. Get work OFF disk into the canonical universal context.
#
# Disk is a disposable working copy; the knowledge base lives in the distributed graph. This organ
# makes that true continuously: for every git repo under the workspace it auto-commits dirty/untracked
# work and PUSHES the current branch to origin, so nothing important ever lives only on a bouncing
# local checkout. ([[live-checkout-is-chaotic]], [[no-never-happens-again]])
#
# Anthony's decision (2026-06-21): AUTO-PUSH EVERYTHING — knowledge AND code/product branches. The old
# "push is his lever" stance is retired for push. Send / wipe / large-spend remain his levers; MERGE is
# the merge-organ's / his call — this organ NEVER merges.
#
# SAFETY INVARIANTS (additive only — capture can never lose or clobber):
#   • never force-push, never delete remote refs, never merge, never rebase, never touch other branches
#   • SECRET GUARD: untracked secrets (.env, *.pem, *.key, id_*, credentials…) are unstaged before
#     commit even if .gitignore misses them — they never get committed/pushed
#   • idempotent: a clean + in-sync repo is a no-op; detached HEAD commits locally but skips push
#   • per-repo `|| true` isolation: one repo failing (auth, unreachable remote) NEVER aborts the rest
#
# Toggles: LIMEN_CAPTURE_DRY=1 (or --dry-run) previews without committing/pushing.
#          LIMEN_WORKSPACE overrides the scan root (default ~/Workspace).
set -uo pipefail
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
WORKSPACE="${LIMEN_WORKSPACE:-$HOME/Workspace}"
[ -f "$HOME/.limen.env" ] && { set -a; . "$HOME/.limen.env"; set +a; }

DRY=0
[ "${LIMEN_CAPTURE_DRY:-0}" = "1" ] && DRY=1
[ "${1:-}" = "--dry-run" ] && DRY=1

# derive at runtime — never pin ([[derive-never-pin-hardcodes]])
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOG="$LIMEN_ROOT/logs/capture-log.jsonl"
mkdir -p "$LIMEN_ROOT/logs" 2>/dev/null || true

# Untracked files matching these are NEVER committed (secret guard; .gitignore is the first line).
SECRET_GLOBS=( '*.env' '.env' '.env.*' '*.pem' '*.key' 'id_rsa*' 'id_ed25519*' '*.secret' \
               '*credentials*' '*.p12' '*.pfx' '*token*' )

captured=0 pushed=0 skipped=0 failed=0

_unstage_secrets() {  # belt-and-suspenders: drop anything secret-looking from the index.
  # git pathspecs match the full path (no FNM_PATHNAME), so '*.env' already matches a/b/c.env.
  local pat
  for pat in "${SECRET_GLOBS[@]}"; do
    git reset -q -- "$pat" >/dev/null 2>&1 || true
  done
}

_capture_repo() {
  local dir="$1" name; name="$(basename "$dir")"
  cd "$dir" 2>/dev/null || { failed=$((failed+1)); return; }
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { skipped=$((skipped+1)); return; }
  git remote get-url origin >/dev/null 2>&1 || { skipped=$((skipped+1)); return; }  # no canonical home

  local branch dirty=0 did_commit=0 did_push=0
  branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "")"
  [ -n "$(git status --porcelain 2>/dev/null)" ] && dirty=1

  if [ "$dirty" = 1 ]; then
    if [ "$DRY" = 1 ]; then
      echo "[capture] $name: WOULD commit dirty tree (branch=${branch:-DETACHED})"
    else
      git add -A >/dev/null 2>&1 || true
      _unstage_secrets
      if ! git diff --cached --quiet 2>/dev/null; then
        git commit -q -m "capture: autonomic off-disk sync $STAMP" >/dev/null 2>&1 && did_commit=1
      fi
    fi
  fi

  # push only when there is something to push and we are on a real branch (never detached, never force)
  if [ -z "$branch" ]; then
    [ "$did_commit" = 1 ] && echo "[capture] $name: committed on DETACHED HEAD — push skipped (no branch)"
  else
    local upstream ahead=0
    upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo "")"
    if [ -n "$upstream" ]; then
      ahead="$(git rev-list --count '@{u}'..HEAD 2>/dev/null || echo 0)"
      if [ "${ahead:-0}" -gt 0 ]; then
        if [ "$DRY" = 1 ]; then echo "[capture] $name: WOULD push $ahead commit(s) → origin/$branch"
        else git push origin "$branch" >/dev/null 2>&1 && did_push=1 || { echo "[capture] $name: push failed (kept local)"; failed=$((failed+1)); }; fi
      fi
    else  # no upstream yet — establish it so this branch joins the canonical graph
      if [ "$DRY" = 1 ]; then echo "[capture] $name: WOULD push -u origin/$branch (new upstream)"
      else git push -u origin "$branch" >/dev/null 2>&1 && did_push=1 || { echo "[capture] $name: push -u failed (kept local)"; failed=$((failed+1)); }; fi
    fi
  fi

  [ "$did_commit" = 1 ] && captured=$((captured+1))
  [ "$did_push" = 1 ] && pushed=$((pushed+1))
  [ "$did_commit" = 1 ] || [ "$did_push" = 1 ] && \
    echo "[capture] $name: committed=$did_commit pushed=$did_push branch=${branch:-DETACHED}"

  if [ "$DRY" = 0 ] && { [ "$did_commit" = 1 ] || [ "$did_push" = 1 ]; }; then
    printf '{"ts":"%s","repo":"%s","branch":"%s","committed":%s,"pushed":%s}\n' \
      "$STAMP" "$name" "${branch:-DETACHED}" "$did_commit" "$did_push" >> "$LOG" 2>/dev/null || true
  fi
}

echo "[capture] scanning $WORKSPACE (dry-run=$DRY) …"
# The glob expands once up-front, so cwd drift across iterations is harmless. No subshell — counters
# must accumulate in this shell; per-repo isolation comes from set +e + guarded git calls, not a fork.
for d in "$WORKSPACE"/*/; do
  [ -e "${d%/}/.git" ] || continue   # plain repo (dir) or linked worktree (.git file)
  _capture_repo "${d%/}"
done

echo "[capture] done — committed=$captured pushed=$pushed skipped=$skipped failed=$failed (dry-run=$DRY)"
