#!/usr/bin/env bash
# capture.sh — the CAPTURE organ. Get work OFF disk into the canonical universal context.
#
# Disk is a disposable working copy; the knowledge base lives in the distributed graph. This organ
# makes that true continuously: for every git repo under the workspace it preserves dirty/untracked
# work on a remote branch, so nothing important ever lives only on a bouncing local checkout.
# Non-default topic branches keep their normal commit/push path. A live default-branch checkout is
# snapshot to one stable, coalescing side ref and is never committed or pushed directly.
# ([[live-checkout-is-chaotic]], [[no-never-happens-again]])
#
# Anthony's decision (2026-06-21): AUTO-PUSH EVERYTHING — knowledge AND code/product branches. The old
# "push is his lever" stance is retired for push. Send / wipe / large-spend remain his levers; MERGE is
# the merge-organ's / his call — this organ NEVER merges.
#
# SAFETY INVARIANTS (additive only — capture can never lose or clobber):
#   • never force-push, never delete remote refs, never merge, never rebase, never push the origin default
#   • SECRET GUARD: untracked secrets (.env, *.pem, *.key, id_*, credentials…) are unstaged before
#     commit even if .gitignore misses them — they never get committed/pushed
#   • idempotent: a clean + in-sync repo is a no-op; detached HEAD snapshots route to a stable side ref
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

# Legacy direct-push guard (issue #872 / PREC-2026-07-10-direct-push-lane-rots-main). It remains as a
# fail-closed backstop for topic behavior and older deployments. Current default-branch snapshots route
# wholesale to a stable off-default custody ref, where the PR/ruleset rail owns integration safety.
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
GIT_NETWORK_TIMEOUT="${LIMEN_CAPTURE_GIT_TIMEOUT:-60}"

_bounded_git() {
  local seconds="$GIT_NETWORK_TIMEOUT"
  case "$seconds" in
    ''|*[!0-9]*) seconds=60;;
  esac
  [ "$seconds" -gt 0 ] 2>/dev/null || seconds=60
  if command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" git "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$seconds" git "$@"
  else
    # `alarm` survives exec. This is the portable macOS fallback when coreutils
    # is absent; every network operation still has a finite wall-clock bound.
    perl -e '$seconds = shift; alarm $seconds; exec @ARGV or exit 127' \
      "$seconds" git "$@"
  fi
}

_origin_default_branch() {
  local symbolic listing
  symbolic="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [[ "$symbolic" = origin/* ]]; then
    printf '%s\n' "${symbolic#origin/}"
    return 0
  fi
  if ! listing="$(_bounded_git ls-remote --symref origin HEAD 2>/dev/null)"; then
    return 1
  fi
  symbolic="$(awk '$1 == "ref:" && $3 == "HEAD" {sub("^refs/heads/", "", $2); print $2; exit}' <<<"$listing")"
  [ -n "$symbolic" ] || return 1
  printf '%s\n' "$symbolic"
}

_capture_side_ref() {
  printf 'capture/%s-deferred\n' "$1"
}

_capture_local_ref() {
  printf 'refs/limen/capture/%s-deferred\n' "$1"
}

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

# DATA_ONLY guard: refuse to stage SOURCE onto a pr-gated repo's default branch. Honours GIT_INDEX_FILE so it
# serves both the in-place index and the side-branch temp index (mirrors _unstage_oversized). Only
# fires when the current branch equals origin's default and pr-gate.yml exists, unless the guard is
# disabled. Refused source is unstaged (stays on disk) and named in a REFUSED line — route via PR.
_unstage_source() {  # $1 = branch being committed; $2 = origin default branch
  local branch="${1:-}"
  local default_branch="${2:-}"
  [ "${LIMEN_PUSH_GUARD:-on}" = "off" ] && return 0
  [ -n "$default_branch" ] && [ "$branch" = "$default_branch" ] || return 0
  [ -f ".github/workflows/pr-gate.yml" ] || return 0
  local pat refused
  # Enumerate staged source BEFORE resetting so we can name it in the warning.
  refused="$(git diff --cached --name-only -z --diff-filter=AM -- "${SOURCE_GLOBS[@]}" 2>/dev/null | tr '\0' ' ')"
  for pat in "${SOURCE_GLOBS[@]}"; do
    git reset -q -- "$pat" >/dev/null 2>&1 || true
  done
  refused="$(echo "$refused" | tr -s ' ')"; refused="${refused# }"; refused="${refused% }"
  if [ -n "$refused" ]; then
    echo "[capture] ${name:-?}: REFUSED source on default branch $branch: $refused — route via PR (pr-gate)"
    printf '{"ts":"%s","repo":"%s","branch":"%s","refused_source":"%s"}\n' \
      "$STAMP" "${name:-?}" "$branch" "$refused" >> "$LOG" 2>/dev/null || true
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
  local name="$1" branch="$2" snapshot_worktree="${3:-1}"
  local sideref remote_ref="" remote_parent="" local_ref="" local_parent="" origin_parent="" parent="" head=""
  local tmpidx="" tree commit pat parent_tree needs_commit=0 candidate
  local expected current race_commit zero sealed=0 attempt
  local -a parents
  # Every diverted branch has one stable ref. Dirty, behind topic branches no
  # longer leak a timestamped remote branch on every heartbeat.
  sideref="$(_capture_side_ref "$branch")"
  remote_ref="refs/remotes/origin/$sideref"
  local_ref="$(_capture_local_ref "$branch")"
  _bounded_git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15 fetch --quiet origin \
    "+refs/heads/$sideref:$remote_ref" >/dev/null 2>&1 || true
  remote_parent="$(git rev-parse --verify "$remote_ref" 2>/dev/null || true)"
  local_parent="$(git rev-parse --verify "$local_ref" 2>/dev/null || true)"
  origin_parent="$(git rev-parse --verify "refs/remotes/origin/$branch" 2>/dev/null || true)"
  head="$(git rev-parse HEAD 2>/dev/null || true)"
  [ -n "$head" ] || return 1
  parent="${local_parent:-${remote_parent:-$head}}"
  if [ "$snapshot_worktree" = 1 ]; then
    tmpidx="$(mktemp 2>/dev/null)" || return 1
    if ! GIT_INDEX_FILE="$tmpidx" git read-tree "$parent" 2>/dev/null; then
      rm -f "$tmpidx" 2>/dev/null
      return 1
    fi
    GIT_INDEX_FILE="$tmpidx" git add -A 2>/dev/null || true
    for pat in "${SECRET_GLOBS[@]}";  do GIT_INDEX_FILE="$tmpidx" git reset -q -- "$pat" >/dev/null 2>&1 || true; done
    for pat in "${RUNTIME_GLOBS[@]}"; do GIT_INDEX_FILE="$tmpidx" git reset -q -- "$pat" >/dev/null 2>&1 || true; done
    # This tree is bound for an off-default custody ref. Preserve source as
    # well as data; the PR/ruleset rail owns integration safety.
    GIT_INDEX_FILE="$tmpidx" _unstage_source "$sideref" ""
    GIT_INDEX_FILE="$tmpidx" _unstage_oversized
    tree="$(GIT_INDEX_FILE="$tmpidx" git write-tree 2>/dev/null)"
    rm -f "$tmpidx" 2>/dev/null || true
  else
    # A clean worktree must not erase a snapshot whose earlier push failed.
    # Retry the exact pending tree instead of rebuilding it from clean files.
    tree="$(git rev-parse "${parent}^{tree}" 2>/dev/null || true)"
  fi
  [ -n "$tree" ] || return 1
  parent_tree="$(git rev-parse "${parent}^{tree}" 2>/dev/null || true)"
  parents=(-p "$parent")
  for candidate in "$remote_parent" "$origin_parent" "$head"; do
    [ -n "$candidate" ] || continue
    [ "$candidate" = "$parent" ] && continue
    if ! git merge-base --is-ancestor "$candidate" "$parent" >/dev/null 2>&1; then
      parents+=(-p "$candidate")
      needs_commit=1
    fi
  done
  if [ "$tree" = "$parent_tree" ]; then
    if [ -z "$remote_parent" ] && [ -z "$local_parent" ]; then
      # A clean local default may still carry commits not yet in origin. Preserve that exact head
      # under the side ref without manufacturing a content-identical commit.
      commit="$head"
    elif [ "$needs_commit" = 1 ]; then
      # The remote/default history advanced since the previous local snapshot.
      # Join every custody parent so no failed-push snapshot becomes dangling.
      commit="$(git commit-tree "$tree" "${parents[@]}" \
        -m "capture: coalesce default preservation $STAMP (HEAD untouched)" 2>/dev/null)"
    elif [ -n "$local_parent" ] && [ "$remote_parent" != "$local_parent" ]; then
      # The tree is already sealed locally, but the last push failed (or the
      # remote ref is behind). Retry that exact custody commit instead of
      # treating local-only state as remotely coalesced.
      commit="$local_parent"
    else
      echo "[capture] $name: $sideref already preserves the selected working tree (coalesced)"
      return 0
    fi
  else
    commit="$(git commit-tree "$tree" "${parents[@]}" \
      -m "capture: off-disk sync $STAMP ($branch → $sideref, HEAD untouched)" 2>/dev/null)"
  fi
  [ -n "$commit" ] || return 1
  # Failure custody lives outside refs/heads so it can never collide with a
  # human worktree. Compare-and-swap prevents concurrent capture processes
  # from silently overwriting one another. A bounded reconciliation preserves
  # both commits when a race is observed.
  zero="$(git hash-object --stdin </dev/null 2>/dev/null | sed 's/./0/g')"
  expected="$local_parent"
  if [ "$commit" = "$local_parent" ]; then
    sealed=1
  else
    for attempt in 1 2 3; do
      if git update-ref "$local_ref" "$commit" "${expected:-$zero}" >/dev/null 2>&1; then
        sealed=1
        break
      fi
      current="$(git rev-parse --verify "$local_ref" 2>/dev/null || true)"
      [ -n "$current" ] || break
      if git merge-base --is-ancestor "$commit" "$current" >/dev/null 2>&1; then
        commit="$current"
        sealed=1
        break
      fi
      race_commit="$(git commit-tree "$tree" -p "$current" -p "$commit" \
        -m "capture: reconcile concurrent custody $STAMP (HEAD untouched)" 2>/dev/null || true)"
      [ -n "$race_commit" ] || break
      expected="$current"
      commit="$race_commit"
    done
  fi
  if [ "$sealed" != 1 ]; then
    echo "[capture] $name: DEFERRED local custody CAS conflict for $sideref"
    failed=$((failed+1))
    return 1
  fi
  [ "$commit" != "$head" ] && captured=$((captured+1))
  if _bounded_git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15 \
    push origin "$commit:refs/heads/$sideref" >/dev/null 2>&1; then
    pushed=$((pushed+1))
    # Delete only the exact local retry ref we published. If another process
    # advanced it concurrently, its newer pending custody remains intact.
    git update-ref -d "$local_ref" "$commit" >/dev/null 2>&1 || true
    echo "[capture] $name: preserved $branch through origin/$sideref (default/HEAD untouched)"
    printf '{"ts":"%s","repo":"%s","branch":"%s","status":"preserved-off-default","side_ref":"%s","committed":1,"pushed":1}\n' \
      "$STAMP" "$name" "$branch" "$sideref" >> "$LOG" 2>/dev/null || true
  else
    echo "[capture] $name: DEFERRED remote preservation; coalesced local side ref $sideref retained"
    printf '{"ts":"%s","repo":"%s","branch":"%s","status":"deferred","reason":"side-ref-push-failed","side_ref":"%s"}\n' \
      "$STAMP" "$name" "$branch" "$sideref" >> "$LOG" 2>/dev/null || true
    failed=$((failed+1))
    return 1
  fi
  return 0
}

_capture_repo() {
  local dir="$1" name; name="$(basename "$dir")"
  cd "$dir" 2>/dev/null || { failed=$((failed+1)); return; }
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { skipped=$((skipped+1)); return; }
  git remote get-url origin >/dev/null 2>&1 || { skipped=$((skipped+1)); return; }  # no canonical home

  local branch capture_branch default_branch upstream origin_ref dirty=0 did_commit=0 did_push=0 behind=0
  branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "")"
  if [ -n "$branch" ]; then
    default_branch="$(_origin_default_branch 2>/dev/null || true)"
    if [ -z "$default_branch" ]; then
      echo "[capture] $name: DEFERRED — origin default branch is unresolved"
      failed=$((failed+1))
      return
    fi
  fi
  [ -n "$(git status --porcelain 2>/dev/null)" ] && dirty=1
  if [ -z "$branch" ]; then
    capture_branch="detached-$(git rev-parse --short=12 HEAD 2>/dev/null || echo unresolved)"
    if git rev-parse --verify "$(_capture_local_ref "$capture_branch")" >/dev/null 2>&1 ||
       [ "$dirty" = 1 ]; then
      if [ "$DRY" = 1 ]; then
        echo "[capture] $name: WOULD preserve detached HEAD through origin/$(_capture_side_ref "$capture_branch")"
      else
        _capture_side_branch "$name" "$capture_branch" "$dirty"
      fi
    fi
    return
  fi
  # A busy fleet advances these remotes constantly, so the local tracking ref (@{u}) goes STALE between
  # beats. The behind-check below is the sole guard that keeps an in-place commit off a diverged branch —
  # but reading a stale @{u} makes it report behind=0 on a branch that is really behind, so we commit onto
  # a stale base → non-ff push rejection → a stranded in-place commit that blocks reap AND sync-release
  # (the capture↔sync deadly-embrace this guard exists to prevent). FRESHEN the ref first. Fetch only when
  # dirty (i.e. about to commit) so clean/in-sync repos stay a cheap no-op; low-speed limits bound a
  # stalled fetch without an external `timeout` dependency (matches the push path's own network calls).
  # A fetch mutates only the remote-tracking ref (never the working tree), so it is safe in DRY too and
  # makes the dry-run preview accurate.
  upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  origin_ref="refs/remotes/origin/$branch"
  if [ -n "$branch" ] && [ "$dirty" = 1 ] &&
     { [ -n "$upstream" ] || git rev-parse --verify "$origin_ref" >/dev/null 2>&1; }; then
    if ! _bounded_git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15 \
      fetch --quiet origin "$branch" >/dev/null 2>&1; then
      echo "[capture] $name: DEFERRED — bounded origin/$branch fetch failed"
      failed=$((failed+1))
      return
    fi
  fi
  # behind its upstream? committing in place here would strand the checkout (see _capture_side_branch).
  # 0 when detached, no upstream, up-to-date, or ahead — i.e. exactly the safe-to-commit-in-place cases.
  if [ -n "$branch" ]; then behind="$(git rev-list --count "HEAD..$origin_ref" 2>/dev/null || echo 0)"; fi
  [ -n "$behind" ] || behind=0

  # Retry local custody even after the worktree was cleaned. The nonstandard
  # ref exists only while a previous remote preservation is pending.
  if [ -n "$branch" ] &&
     git rev-parse --verify "$(_capture_local_ref "$branch")" >/dev/null 2>&1; then
    if [ "$DRY" = 1 ]; then
      echo "[capture] $name: WOULD retry pending custody through origin/$(_capture_side_ref "$branch")"
    else
      _capture_side_branch "$name" "$branch" "$dirty"
    fi
    return
  fi

  # The derived origin default branch is an integration target, never a
  # heartbeat writer target.
  if [ "$branch" = "$default_branch" ]; then
    local default_ahead=0
    default_ahead="$(git rev-list --count "$origin_ref..HEAD" 2>/dev/null || echo 0)"
    [ -n "$default_ahead" ] || default_ahead=0
    if [ "$dirty" = 1 ] || [ "$default_ahead" -gt 0 ] 2>/dev/null; then
      if [ "$DRY" = 1 ]; then
        echo "[capture] $name: WOULD preserve $default_branch through origin/$(_capture_side_ref "$branch") (default/HEAD untouched)"
      else
        _capture_side_branch "$name" "$branch" 1
      fi
    fi
    return
  fi

  if [ "$dirty" = 1 ]; then
    if [ "$DRY" = 1 ]; then
      if [ "$behind" -gt 0 ] 2>/dev/null; then
        echo "[capture] $name: WOULD capture dirty tree to a SIDE ref ($branch is $behind behind origin — no in-place commit)"
      else
        echo "[capture] $name: WOULD commit dirty tree (branch=${branch:-DETACHED})"
      fi
    elif [ "$behind" -gt 0 ] 2>/dev/null; then
      # behind origin → never commit onto this branch; divert to a pushable side ref and leave HEAD clean
      _capture_side_branch "$name" "$branch" 1
      return
    else
      git add -A >/dev/null 2>&1 || true
      _unstage_secrets
      _unstage_runtime
      _unstage_source "$branch" "$default_branch"
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
        else _bounded_git push origin "HEAD:refs/heads/$branch" >/dev/null 2>&1 && did_push=1 || { echo "[capture] $name: push failed (kept local)"; failed=$((failed+1)); }; fi
      fi
    else  # no upstream yet — establish it so this branch joins the canonical graph
      if [ "$DRY" = 1 ]; then echo "[capture] $name: WOULD push -u origin/$branch (new upstream)"
      else _bounded_git push -u origin "HEAD:refs/heads/$branch" >/dev/null 2>&1 && did_push=1 || { echo "[capture] $name: push -u failed (kept local)"; failed=$((failed+1)); }; fi
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
if [ "$failed" -gt 0 ] 2>/dev/null; then
  exit 1
fi
