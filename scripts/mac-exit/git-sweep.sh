#!/usr/bin/env bash
# READ-ONLY sweep of every git repo and worktree on the internal disk, for the "leave the Mac empty" exit.
#
# WHY: deleting a local copy because "the remote has it" needs per-repo evidence, and the Mac is live, so the
# evidence goes stale the moment it is taken. Run this immediately before any reset, then classify the TSV with
# scripts/mac-exit/classify-git-sweep.py. It never writes inside a repo (GIT_OPTIONAL_LOCKS=0 keeps `git status`
# from taking index locks that could collide with a running session).
#
# Columns (a LOCAL view; remote-tracking refs may lag, so deletion still needs a fresh `git ls-remote` proof):
#   kind                   derived from git, never from the shape of `.git`: bare when `git rev-parse --is-bare-repository`
#                          is true; repo when --absolute-git-dir equals the realpath of --git-common-dir (a main checkout,
#                          including a submodule checkout and a separate-git-dir checkout, whose `.git` is a file); worktree
#                          otherwise. A `.git` entry git cannot resolve falls back to repo (a directory) or worktree (a file).
#   dirty                  uncommitted or untracked entries (in no commit, on no remote); 0 for a bare repository
#   unpushed               commits on local branches reachable from no remote-tracking ref (repo-wide)
#   stashes                stash entries, never pushed (repo-wide); counted from the refs/stash reflog in a bare repository
#   head_remote_branches   remote-tracking branches containing HEAD; 0 on a detached HEAD means it is on none
#
# Discovery is a superset on purpose: a repository the sweep cannot see is a repository nobody checks. There is no depth
# bound and no name prune (node_modules, .venv and friends are walked), `.git` matches case-insensitively, and bare
# repositories (a directory holding HEAD, objects/ and refs/ that git calls bare) are found as well. Only -xdev limits the
# walk; keep stderr, because a directory the walk could not read is a directory it did not sweep.
#
# Roots: with no ROOT arguments, every directory directly under $HOME except Library, .Trash, .cache, .npm, .cargo and
# .rustup, plus $HOME/.local/share (a first version pruned it as "cache" and missed a real repository there), and a
# `.git` directly in $HOME itself. Explicit ROOT arguments replace those defaults and must exist. Either way the realpath
# of every root actually walked is written to OUT_DIR/git.roots, one per line, then a completion row `#END rows=N`; the
# readiness predicate walks exactly those roots when it looks for repositories this sweep missed.
#
# Gotcha: `find` on this host may be bfs, which rejects the BSD `-x` flag; use `-xdev` and keep stderr.
#
# usage: scripts/mac-exit/git-sweep.sh [OUT_DIR [ROOT ...]]     # default OUT_DIR: $TMPDIR/mac-exit-git-sweep

set -u
export GIT_OPTIONAL_LOCKS=0
export LC_ALL=C
unset CDPATH

out="${1:-${TMPDIR:-/tmp}/mac-exit-git-sweep}"
[ $# -gt 0 ] && shift
log() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
die() {
  echo "git-sweep: $2" >&2
  exit "$1"
}
real() { (cd -P "$1" 2> /dev/null && pwd -P); }

mkdir -p "$out" || die 73 "cannot create $out"
# A roots file left by an earlier run would vouch for this run's coverage while it is still walking.
rm -f "$out/git.roots"

roots=()
add_root() { # dir: a directory to walk, kept once, as its realpath
  local r seen
  r=$(real "$1") || return 1
  case "$r" in *$'\t'* | *$'\r'* | *$'\n'*) die 64 "a root with TAB, CR or LF in its path cannot be written to the roots file: $1" ;; esac
  for seen in ${roots[@]+"${roots[@]}"}; do [ "$seen" = "$r" ] && return 0; done
  roots+=("$r")
}

default_roots=0
home=""
if [ $# -gt 0 ]; then
  for r in "$@"; do
    [ -d "$r" ] || die 66 "no such root directory: $r"
    add_root "$r"
  done
else
  default_roots=1
  home=$(real "${HOME:?HOME unset}") || die 66 "cannot resolve \$HOME"
  while IFS= read -r -d '' d; do
    case "${d##*/}" in Library | .Trash | .cache | .npm | .cargo | .rustup) continue ;; esac
    add_root "$d"
  done < <(find "$home" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
  [ -d "$home/.local/share" ] && add_root "$home/.local/share"
fi
[ "${#roots[@]}" -gt 0 ] || die 66 "no root directories to sweep"

list="$out/git-entries.zlist"
: > "$list"
: > "$out/find.err"
for r in "${roots[@]}"; do
  # `.git` (a directory or a gitfile) is printed and not descended into; a regular file named HEAD outside any `.git`
  # marks a bare-repository candidate, confirmed below.
  find "$r" -xdev \( -iname .git -print0 -prune \) -o \( -type f -iname HEAD -print0 \) >> "$list" 2>> "$out/find.err"
done
if [ "$default_roots" = 1 ]; then
  # A repository rooted at $HOME itself: not a root (walking $HOME would walk Library), so look one level deep only.
  find "$home" -xdev -maxdepth 1 -iname .git -print0 -prune >> "$list" 2>> "$out/find.err"
fi
sort -z -u "$list" > "$list.sorted"
log "find stderr lines: $(wc -l < "$out/find.err" | tr -d ' ')"

derive_kind() { # dir dot-git-entry: bare, repo or worktree, from git itself
  local d=$1 dotgit=$2 isbare agd cdir
  isbare=$(git -C "$d" rev-parse --is-bare-repository 2> /dev/null) || isbare=""
  if [ "$isbare" = true ]; then
    echo bare
    return
  fi
  agd=$(git -C "$d" rev-parse --absolute-git-dir 2> /dev/null) || agd=""
  cdir=$(git -C "$d" rev-parse --path-format=absolute --git-common-dir 2> /dev/null) || cdir=""
  if [ -n "$agd" ] && [ -n "$cdir" ]; then
    agd=$(real "$agd") || agd=""
    cdir=$(real "$cdir") || cdir=""
    if [ -n "$agd" ] && [ "$agd" = "$cdir" ]; then echo repo; else echo worktree; fi
    return
  fi
  if [ -d "$dotgit" ]; then echo repo; else echo worktree; fi
}

is_bare_dir() { # dir: holds objects/ and refs/, git says bare, and git's own git dir is this very directory
  local d=$1 isbare agd rd
  [ -d "$d/objects" ] && [ -d "$d/refs" ] || return 1
  if ! isbare=$(git -C "$d" rev-parse --is-bare-repository 2> /dev/null); then
    echo "git-sweep: git cannot read $d, which looks like a bare repository; it is not swept" >> "$out/find.err"
    return 1
  fi
  [ "$isbare" = true ] || return 1
  agd=$(git -C "$d" rev-parse --absolute-git-dir 2> /dev/null) || return 1
  agd=$(real "$agd") || return 1
  rd=$(real "$d") || return 1
  [ "$agd" = "$rd" ]
}

# Pass 1: the checkouts (every `.git` entry) and the bare repositories (confirmed HEAD candidates).
row_dir=()
row_dotgit=()
bare_dirs=()
while IFS= read -r -d '' g; do
  case "${g##*/}" in
    [Hh][Ee][Aa][Dd])
      d=$(dirname "$g")
      is_bare_dir "$d" && bare_dirs+=("$d")
      ;;
    *)
      repo=$(dirname "$g")
      case "$repo/" in */.[gG][iI][tT]/*) continue ;; esac # inside a git dir, not a checkout
      row_dir+=("$repo")
      row_dotgit+=("$g")
      ;;
  esac
done < "$list.sorted"
# A directory inside an accepted bare repository (a submodule git dir under modules/, say) is part of that repository.
for d in ${bare_dirs[@]+"${bare_dirs[@]}"}; do
  nested=0
  for b in "${bare_dirs[@]}"; do
    if [ "$b" != "$d" ] && [[ "$d" == "$b"/* ]]; then nested=1; fi
  done
  if [ "$nested" = 0 ]; then
    row_dir+=("$d")
    row_dotgit+=("")
  fi
done

tsv="$out/git.tsv"
printf 'path\tkind\tbranch\tremote\tdirty\tunpushed\tstashes\thead_remote_branches\n' > "$tsv"
n=0
i=0
while [ "$i" -lt "${#row_dir[@]}" ]; do
  repo="${row_dir[$i]}"
  g="${row_dotgit[$i]}"
  i=$((i + 1))
  if [ -z "$g" ]; then kind=bare; else kind=$(derive_kind "$repo" "$g"); fi
  branch=$(git -C "$repo" symbolic-ref --short -q HEAD 2> /dev/null || echo "(detached)")
  remote=$(git -C "$repo" config --get remote.origin.url 2> /dev/null || true)
  [[ -z "$remote" ]] && remote="NONE"
  if [ "$kind" = bare ]; then
    dirty=0 # no working tree to be dirty
  else
    dirty=$(git -C "$repo" status --porcelain=v1 --untracked-files=normal 2> /dev/null | wc -l | tr -d ' ')
  fi
  unpushed=$(git -C "$repo" rev-list --count --branches --not --remotes 2> /dev/null || echo "?")
  if [ "$kind" = bare ]; then
    # `git stash list` refuses to run without a work tree; the stash entries are the reflog of refs/stash all the same
    stashes=$(git -C "$repo" log -g --format=%H refs/stash 2> /dev/null | wc -l | tr -d ' ')
  else
    stashes=$(git -C "$repo" stash list 2> /dev/null | wc -l | tr -d ' ')
  fi
  headrem=$(git -C "$repo" branch -r --contains HEAD 2> /dev/null | wc -l | tr -d ' ')
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$repo" "$kind" "$branch" "$remote" "$dirty" "$unpushed" "$stashes" "$headrem" >> "$tsv"
  n=$((n + 1))
done
log "git sweep complete: $n entries -> $tsv"

# Written last: a sweep that stopped early leaves a git.tsv with no roots file, which the predicate refuses.
{
  for r in "${roots[@]}"; do printf '%s\n' "$r"; done
  printf '#END rows=%d\n' "${#roots[@]}"
} > "$out/git.roots"
log "roots walked: ${#roots[@]} -> $out/git.roots"
