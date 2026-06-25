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

# Daemon-OWNED live state the capture organ must NEVER commit out-of-band. On the live checkout the
# heartbeat rewrites tasks.yaml every beat UNDER queue_lock; an out-of-band capture commit of a torn /
# transient queue races the daemon and clobbers its writes — the exact failure logged in
# [[self-star-ladder-shipped-live]] ("out-of-band tasks.yaml writes clobbered"). The daemon commits the
# queue deliberately on its own cadence; capture leaves it alone. Pinned to exact names (NOT a broad
# '*.lock', which would wrongly drop legitimate tracked lockfiles like Cargo.lock / poetry.lock).
RUNTIME_GLOBS=( 'tasks.yaml' 'tasks.yaml.lock' )

captured=0 pushed=0 skipped=0 failed=0

_unstage_secrets() {  # belt-and-suspenders: drop anything secret-looking from the index.
  # git pathspecs match the full path (no FNM_PATHNAME), so '*.env' already matches a/b/c.env.
  local pat
  for pat in "${SECRET_GLOBS[@]}"; do
    git reset -q -- "$pat" >/dev/null 2>&1 || true
  done
}

_unstage_runtime() {  # keep the daemon-owned live queue out of capture commits (anti-clobber).
  local pat
  for pat in "${RUNTIME_GLOBS[@]}"; do
    git reset -q -- "$pat" >/dev/null 2>&1 || true
  done
}

# When the current branch is BEHIND its upstream, an in-place capture commit creates UN-PUSHABLE
# divergence: the push is rejected (non-ff) and the stranded local commit then blocks sync-release's
# fast-forward, deadlocking the live checkout (the capture↔sync deadly-embrace that stranded 22 merged
# releases on 2026-06-24). Instead, snapshot the working tree to a pushable SIDE ref WITHOUT moving HEAD
# or touching the working copy — plumbing only (temp index → write-tree → commit-tree → update-ref) — so
# the work still reaches the canonical graph while the branch stays a clean ANCESTOR of origin and
# sync-release can always ff. ([[live-checkout-is-chaotic]] preservation, minus the divergence.)
_capture_side_branch() {
  local name="$1" branch="$2"
  local sideref="capture/${branch}-${STAMP//:/-}"   # git refs forbid ':' — sanitize the ISO stamp
  local tmpidx tree commit pat
  tmpidx="$(mktemp 2>/dev/null)" || return 1
  if ! GIT_INDEX_FILE="$tmpidx" git read-tree HEAD 2>/dev/null; then rm -f "$tmpidx" 2>/dev/null; return 1; fi
  GIT_INDEX_FILE="$tmpidx" git add -A 2>/dev/null || true   # stage the WORKING TREE into the throwaway index
  for pat in "${SECRET_GLOBS[@]}";  do GIT_INDEX_FILE="$tmpidx" git reset -q -- "$pat" >/dev/null 2>&1 || true; done
  for pat in "${RUNTIME_GLOBS[@]}"; do GIT_INDEX_FILE="$tmpidx" git reset -q -- "$pat" >/dev/null 2>&1 || true; done
  tree="$(GIT_INDEX_FILE="$tmpidx" git write-tree 2>/dev/null)"
  rm -f "$tmpidx" 2>/dev/null || true
  [ -n "$tree" ] || return 1
  if [ "$tree" = "$(git rev-parse 'HEAD^{tree}' 2>/dev/null)" ]; then
    echo "[capture] $name: $branch behind origin, nothing left to capture after secret/runtime filter"
    return 1
  fi
  commit="$(git commit-tree "$tree" -p HEAD -m "capture: off-disk sync $STAMP ($branch behind origin → side ref, HEAD untouched)" 2>/dev/null)"
  [ -n "$commit" ] || return 1
  git update-ref "refs/heads/$sideref" "$commit" 2>/dev/null || return 1
  captured=$((captured+1))
  if git push origin "refs/heads/$sideref:refs/heads/$sideref" >/dev/null 2>&1; then
    pushed=$((pushed+1))
    echo "[capture] $name: $branch behind origin → captured working tree to origin/$sideref (no divergence, HEAD untouched)"
    printf '{"ts":"%s","repo":"%s","branch":"%s","side_ref":"%s","committed":1,"pushed":1}\n' \
      "$STAMP" "$name" "$branch" "$sideref" >> "$LOG" 2>/dev/null || true
  else
    echo "[capture] $name: captured to local side ref $sideref but push failed (kept local)"
    failed=$((failed+1))
  fi
  return 0
}

_capture_repo() {
  local dir="$1" name; name="$(basename "$dir")"
  cd "$dir" 2>/dev/null || { failed=$((failed+1)); return; }
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { skipped=$((skipped+1)); return; }
  git remote get-url origin >/dev/null 2>&1 || { skipped=$((skipped+1)); return; }  # no canonical home

  local branch dirty=0 did_commit=0 did_push=0 behind=0
  branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "")"
  [ -n "$(git status --porcelain 2>/dev/null)" ] && dirty=1
  # behind its upstream? committing in place here would strand the checkout (see _capture_side_branch).
  # 0 when detached, no upstream, up-to-date, or ahead — i.e. exactly the safe-to-commit-in-place cases.
  if [ -n "$branch" ]; then behind="$(git rev-list --count "HEAD..@{u}" 2>/dev/null || echo 0)"; fi
  [ -n "$behind" ] || behind=0

  if [ "$dirty" = 1 ]; then
    if [ "$DRY" = 1 ]; then
      if [ "$behind" -gt 0 ] 2>/dev/null; then
        echo "[capture] $name: WOULD capture dirty tree to a SIDE ref ($branch is $behind behind origin — no in-place commit)"
      else
        echo "[capture] $name: WOULD commit dirty tree (branch=${branch:-DETACHED})"
      fi
    elif [ "$behind" -gt 0 ] 2>/dev/null; then
      # behind origin → never commit onto this branch; divert to a pushable side ref and leave HEAD clean
      _capture_side_branch "$name" "$branch"
      return
    else
      git add -A >/dev/null 2>&1 || true
      _unstage_secrets
      _unstage_runtime
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
