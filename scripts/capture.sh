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

# DATA_ONLY push guard (issue #872 / PREC-2026-07-10-direct-push-lane-rots-main). When capture would
# commit to a repo's `main` AND that repo gates PRs (`.github/workflows/pr-gate.yml` exists), it must
# NEVER stage SOURCE — code/config that belongs behind pr-gate. Otherwise an uncommitted `.py` sitting
# in the live checkout on main gets `git add -A`'d and pushed straight to protected main, un-CI'd (the
# primary leak). SOURCE files are unstaged (LEFT ON DISK, never deleted) and the refusal is surfaced.
# The lane's legitimate cargo — tasks.yaml, receipts, logs, other data — is untouched. Self-configuring:
# repos without pr-gate.yml, and non-main branches (feature/worktree work correctly preserves source),
# keep current behavior. Escape hatch: LIMEN_PUSH_GUARD=off disables (default = enforce).
SOURCE_GLOBS=( '*.py' '*.sh' '*.ts' '*.js' '*.mjs' '*.cjs' '*.tsx' '*.jsx' '*.rs' '*.go' \
               '*.toml' '*.cfg' '*Makefile' '*Dockerfile' '.github/*' \
               '.github/*.yml' '.github/*.yaml' 'cli/*.yml' 'cli/*.yaml' \
               'web/*.yml' 'web/*.yaml' 'institutio/*.yml' 'institutio/*.yaml' \
               'scripts/*.yml' 'scripts/*.yaml' )

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

# DATA_ONLY guard: refuse to stage SOURCE onto a pr-gated repo's main. Honours GIT_INDEX_FILE so it
# serves both the in-place index and the side-branch temp index (mirrors _unstage_oversized). Only
# fires when: branch == main AND .github/workflows/pr-gate.yml exists in this repo AND the guard is not
# disabled. Refused source is unstaged (stays on disk) and named in a REFUSED line — route via PR.
_unstage_source() {  # $1 = branch being committed
  local branch="${1:-}"
  [ "${LIMEN_PUSH_GUARD:-on}" = "off" ] && return 0
  [ "$branch" = "main" ] || return 0
  [ -f ".github/workflows/pr-gate.yml" ] || return 0
  local pat refused
  # Enumerate staged source BEFORE resetting so we can name it in the warning.
  refused="$(git diff --cached --name-only -z --diff-filter=AM -- "${SOURCE_GLOBS[@]}" 2>/dev/null | tr '\0' ' ')"
  for pat in "${SOURCE_GLOBS[@]}"; do
    git reset -q -- "$pat" >/dev/null 2>&1 || true
  done
  refused="$(echo "$refused" | tr -s ' ')"; refused="${refused# }"; refused="${refused% }"
  if [ -n "$refused" ]; then
    echo "[capture] ${name:-?}: REFUSED source on main: $refused — route via PR (pr-gate)"
    printf '{"ts":"%s","repo":"%s","branch":"main","refused_source":"%s"}\n' \
      "$STAMP" "${name:-?}" "$refused" >> "$LOG" 2>/dev/null || true
  fi
}

# GitHub HARD-rejects any non-LFS file over 100MB (pre-receive hook), so staging one guarantees the
# push is refused — regardless of divergence — leaving a permanently un-pushable, un-reapable commit
# that pins disk (e.g. a repo that doesn't .gitignore node_modules → a 116MB .node binary gets `git
# add -A`'d and can never reach origin). An organ whose whole purpose is to PUSH must never stage what
# GitHub will reject: drop over-limit files from the index (they stay on disk, untracked) so capture
# always produces a pushable commit. Honours GIT_INDEX_FILE, so it serves both the in-place index and
# the side-branch temp index. LFS repos are unaffected (their large blobs are small pointer files).
GITHUB_FILE_LIMIT=$((100 * 1024 * 1024))
_unstage_oversized() {
  local f sz
  while IFS= read -r -d '' f; do
    [ -f "$f" ] || continue
    sz="$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)"
    if [ "${sz:-0}" -ge "$GITHUB_FILE_LIMIT" ] 2>/dev/null; then
      git reset -q -- "$f" >/dev/null 2>&1 || true
      echo "[capture] ${name:-?}: skipped un-pushable $((sz / 1024 / 1024))MB file (exceeds GitHub 100MB limit): $f"
    fi
  done < <(git diff --cached --name-only -z --diff-filter=AM 2>/dev/null)
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
  GIT_INDEX_FILE="$tmpidx" _unstage_source "$branch"
  GIT_INDEX_FILE="$tmpidx" _unstage_oversized
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
  # A busy fleet advances these remotes constantly, so the local tracking ref (@{u}) goes STALE between
  # beats. The behind-check below is the sole guard that keeps an in-place commit off a diverged branch —
  # but reading a stale @{u} makes it report behind=0 on a branch that is really behind, so we commit onto
  # a stale base → non-ff push rejection → a stranded in-place commit that blocks reap AND sync-release
  # (the capture↔sync deadly-embrace this guard exists to prevent). FRESHEN the ref first. Fetch only when
  # dirty (i.e. about to commit) so clean/in-sync repos stay a cheap no-op; low-speed limits bound a
  # stalled fetch without an external `timeout` dependency (matches the push path's own network calls).
  # A fetch mutates only the remote-tracking ref (never the working tree), so it is safe in DRY too and
  # makes the dry-run preview accurate.
  if [ -n "$branch" ] && [ "$dirty" = 1 ]; then
    git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15 fetch --quiet origin "$branch" >/dev/null 2>&1 || true
  fi
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
      _unstage_source "$branch"
      _unstage_oversized
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
# RECURSE (maxdepth 3), not just depth-1: the fleet clones repos NESTED under org dirs
# (~/Workspace/organvm/*, a-organvm/*, 4444J99/*), and a depth-1 loop never pushed them — so their
# work piled up unpushable-and-unreapable and the disk crept to full. Every .git (clone dir OR linked
# worktree file) under the workspace now reaches its canonical origin. Paths are absolute, so the cd
# inside _capture_repo drifting cwd is harmless; no subshell — counters must accumulate in this shell.
# Throwaway / co-tenant / interactive roots are somebody else's lifecycle → skipped here.
while IFS= read -r g; do
  d="$(dirname "$g")"
  case "$d" in
    *.claude/worktrees*|*.limen-worktrees*|*.home-cartridge*|*/node_modules/*) continue;;
  esac
  _capture_repo "$d"
done < <(find "$WORKSPACE" -maxdepth 3 -name .git 2>/dev/null)

echo "[capture] done — committed=$captured pushed=$pushed skipped=$skipped failed=$failed (dry-run=$DRY)"
