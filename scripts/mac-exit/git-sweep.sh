#!/usr/bin/env bash
# READ-ONLY sweep of every git repo and worktree on the internal disk, for the "leave the Mac empty" exit.
#
# WHY: deleting a local copy because "the remote has it" needs per-repo evidence, and the Mac is live, so the
# evidence goes stale the moment it is taken. Run this immediately before any reset, then classify the TSV with
# scripts/mac-exit/classify-git-sweep.py. It never writes inside a repo (GIT_OPTIONAL_LOCKS=0 keeps `git status`
# from taking index locks that could collide with a running session).
#
# Columns (a LOCAL view; remote-tracking refs may lag, so deletion still needs a fresh `git ls-remote` proof):
#   dirty                  uncommitted or untracked entries (in no commit, on no remote)
#   unpushed               commits on local branches reachable from no remote-tracking ref (repo-wide)
#   stashes                stash entries, never pushed (repo-wide)
#   head_remote_branches   remote-tracking branches containing HEAD; 0 on a detached HEAD means it is on none
#
# Gotcha: `find` on this host may be bfs, which rejects the BSD `-x` flag; use `-xdev` and keep stderr.
#
# usage: scripts/mac-exit/git-sweep.sh [OUT_DIR]     # default: $TMPDIR/mac-exit-git-sweep

set -u
export GIT_OPTIONAL_LOCKS=0

out="${1:-${TMPDIR:-/tmp}/mac-exit-git-sweep}"
mkdir -p "$out"
log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }

# ~/.local/share is a root on purpose: a first version pruned it as "cache" and missed a real repository there (and the parent of three
# swept worktrees). Its regenerable clones classify as safe; ~/.cache stays out.
roots=("$HOME/Workspace" "$HOME/Documents" "$HOME/Desktop" "$HOME/Downloads" "$HOME/Developer" "$HOME/Code" "$HOME/edu" "$HOME/limen-lanes" "$HOME/.local/share")
prune=(\( -name node_modules -o -name .venv -o -name site-packages -o -name .tox -o -name Pods \) -prune -o)

list="$out/git-entries.zlist"
: > "$list"
: > "$out/find.err"
for r in "${roots[@]}"; do
  [[ -d "$r" ]] || continue
  find "$r" -xdev -maxdepth 9 "${prune[@]}" -name .git -print0 -prune >> "$list" 2>> "$out/find.err"
done
# Strays directly under $HOME, skipping the heavy roots handled above.
find "$HOME" -xdev -maxdepth 3 \
  \( -path "$HOME/Library" -o -path "$HOME/Workspace" -o -path "$HOME/.Trash" -o -path "$HOME/.cache" \
     -o -path "$HOME/.npm" -o -path "$HOME/.cargo" -o -path "$HOME/.rustup" -o -path "$HOME/.local/share" \) -prune -o \
  -name .git -print0 -prune >> "$list" 2>> "$out/find.err"
sort -z -u "$list" > "$list.sorted"
log "find stderr lines: $(wc -l < "$out/find.err" | tr -d ' ')"

tsv="$out/git.tsv"
printf 'path\tkind\tbranch\tremote\tdirty\tunpushed\tstashes\thead_remote_branches\n' > "$tsv"
n=0
while IFS= read -r -d '' g; do
  repo="$(dirname "$g")"
  [[ "$repo" == */.git/* ]] && continue
  if [[ -d "$g" ]]; then kind=repo; else kind=worktree; fi
  branch=$(git -C "$repo" symbolic-ref --short -q HEAD 2>/dev/null || echo "(detached)")
  remote=$(git -C "$repo" config --get remote.origin.url 2>/dev/null || true)
  [[ -z "$remote" ]] && remote="NONE"
  dirty=$(git -C "$repo" status --porcelain=v1 --untracked-files=normal 2>/dev/null | wc -l | tr -d ' ')
  unpushed=$(git -C "$repo" rev-list --count --branches --not --remotes 2>/dev/null || echo "?")
  stashes=$(git -C "$repo" stash list 2>/dev/null | wc -l | tr -d ' ')
  headrem=$(git -C "$repo" branch -r --contains HEAD 2>/dev/null | wc -l | tr -d ' ')
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$repo" "$kind" "$branch" "$remote" "$dirty" "$unpushed" "$stashes" "$headrem" >> "$tsv"
  n=$((n + 1))
done < "$list.sorted"
log "git sweep complete: $n entries -> $tsv"
