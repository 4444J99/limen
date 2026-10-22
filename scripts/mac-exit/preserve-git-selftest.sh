#!/usr/bin/env bash
# End-to-end self-test of the git producer chain on throwaway fixtures: git-sweep.sh -> merge-sweeps.py ->
# classify-git-sweep.py -> preserve-git.sh -> verify-preserve.sh. Touches nothing outside its own temp directory.
#
# WHY: the readiness predicate's own self-test builds its sweep rows by hand and hands the producer a real.tsv, so a
# sweep that cannot see a bare repository, a producer that drops a reflog-only commit from its copy, or a verifier that
# trusts both would all pass it. This test runs the real tools against fixtures that hold exactly the work a bundle
# loses, then corrupts the run in the ways a bad copy would be corrupt and requires the verifier to say FAIL.
#
# Fixtures (every repository has no remote, so every one is real exposure and gets preserved):
#   reflogonly   a commit left reachable only from the reflog (reset --hard)       -> gitdir-tar (reflog-only)
#   wtmain       refs/worktree/* in the main worktree, refs/bisect/* in a linked    -> gitdir-tar (per-worktree-refs)
#                worktree, both commits created without a reflog
#   lfslocal     an LFS object under .git/lfs/objects                               -> gitdir-tar (lfs-objects)
#   lfsreloc     lfs.storage pointing outside the git dir                           -> lfs-storage-tar, no gitdir-tar
#   super, lib   a superproject and its submodule checkout (.git file, modules/)    -> kind repo; gitdir-tar (submodule-gitdirs)
#   sepgit       a checkout whose git dir lives elsewhere (--separate-git-dir)      -> kind repo, not a bare repository
#   filtered     tracked paths with filter= attributes, working-tree bytes that     -> filtered-tar
#                differ from the blob (clean filter, filter=lfs, a credential name)
#   mybare.git   a bare repository, with an LFS object                              -> kind bare; bundle + gitdir-tar
#   plain        nothing special                                                    -> bundle only (no extra copy at all)
#   upper, deep, node_modules, spaces, .local/share  discovery: a `.GIT` spelling, a repository beyond depth 9, one under
#                node_modules, roots and paths with spaces, the default roots under a fixture $HOME
# Negative controls corrupt a copy of the good run (a missing object, ref file, LFS file, modules entry, filtered file, a
# truncated LFS store tar, a dropped item) and a roots file (bad completion row); each must be refused.
#
# usage: preserve-git-selftest.sh [--scripts-dir DIR]
#   --scripts-dir DIR      take all five tools from DIR (a copy of an older tree, to see what a check does on old code)
#   SELFTEST_SWEEP, SELFTEST_MERGE, SELFTEST_CLASSIFY, SELFTEST_PRESERVE, SELFTEST_VERIFY
#                          take one tool from an explicit file instead
# Prints `RESULT: PASS (N checks)` and exits 0, or `RESULT: FAIL ...` and exits 1. Run it through the host lock wrapper.
# shellcheck disable=SC2015 # `test && ok || bad` is safe here: ok and bad always return 0
set -u
here=$(cd -P "$(dirname "$0")" && pwd -P)
scripts=$here
if [ "${1:-}" = --scripts-dir ]; then
  [ -d "${2:-}" ] || { echo "usage: $0 [--scripts-dir DIR]" >&2; exit 64; }
  scripts=$(cd -P "$2" && pwd -P)
fi
SWEEP=${SELFTEST_SWEEP:-$scripts/git-sweep.sh}
MERGE=${SELFTEST_MERGE:-$scripts/merge-sweeps.py}
CLASSIFY=${SELFTEST_CLASSIFY:-$scripts/classify-git-sweep.py}
PRESERVE=${SELFTEST_PRESERVE:-$scripts/preserve-git.sh}
VERIFY=${SELFTEST_VERIFY:-$scripts/verify-preserve.sh}
for tool in "$SWEEP" "$MERGE" "$CLASSIFY" "$PRESERVE" "$VERIFY"; do
  [ -f "$tool" ] || { echo "self-test cannot run: no such tool: $tool" >&2; exit 66; }
done

base=$(mktemp -d "${TMPDIR:-/tmp}/preserve-git-selftest.XXXXXX") || exit 70
base=$(cd -P "$base" && pwd -P) # macOS $TMPDIR is under /var, a symlink to /private/var
# One fresh directory holds HOME, TMPDIR, scratch and the destination, so a path bug lands on fixture data only.
export HOME="$base/home" TMPDIR="$base/tmp"
unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_STATE_HOME XDG_CACHE_HOME GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR \
  GIT_NAMESPACE GIT_CEILING_DIRECTORIES GIT_DISCOVERY_ACROSS_FILESYSTEM CDPATH
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0 GIT_OPTIONAL_LOCKS=0
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid
export GIT_AUTHOR_DATE="2001-01-01T00:00:00Z" GIT_COMMITTER_DATE="2001-01-01T00:00:00Z"
# The fixtures live on the same disk as $HOME, which the producer refuses by design; opt out for this test only.
export PRESERVE_ALLOW_SAME_DEVICE=1 PRESERVE_MIN_FREE_GIB=0 PRESERVE_SCRATCH="$base/pscratch"
case "$HOME" in "$base"/*) ;; *)
  echo "refusing to run: HOME is not inside the fixture directory" >&2
  exit 70
  ;;
esac
mkdir -p "$HOME" "$TMPDIR" "$PRESERVE_SCRATCH" "$base/work"

fail=0
passes=0
skips=0
ok() {
  printf 'ok    %s\n' "$*"
  passes=$((passes + 1))
}
bad() {
  printf 'FAIL  %s\n' "$*"
  fail=1
}
skip() {
  printf 'skip  %s\n' "$*"
  skips=$((skips + 1))
}
check() { # description, command...: ok when the command exits 0
  local d=$1
  shift
  if "$@" > "$base/work/check.out" 2>&1; then ok "$d"; else bad "$d: $(head -c 300 "$base/work/check.out")"; fi
}

g() { command git -c init.defaultBranch=main -c protocol.file.allow=always -c advice.detachedHead=false "$@"; }
mkrepo() { # dir: a repository with one commit
  g init -q "$1" && printf 'one\n' > "$1/f.txt" && g -C "$1" add f.txt && g -C "$1" commit -q -m one
}
slug_of() { # path: the slug the tools derive (independent implementation)
  python3 -I -c 'import hashlib, os, sys
p = sys.argv[1]
home = os.environ["HOME"]
rel = p[len(home) + 1:] if p.startswith(home + "/") else p.lstrip("/")
print(rel.replace("/", "__")[:150] + "-" + hashlib.sha256(p.encode()).hexdigest()[:8])' "$1"
}
# mfield <run> <kind> <slug> <column name>: a MANIFEST.tsv field of the first matching item ("" when there is none)
mfield() {
  awk -F'\t' -v k="$2" -v s="$3" -v c="$4" '
    NR == 1 { for (i = 1; i <= NF; i++) col[$i] = i; next }
    $1 == k && $3 == s { print $(col[c]); exit }' "$1/MANIFEST.tsv"
}
mcount() { awk -F'\t' -v k="$2" 'NR > 1 && $1 == k { n++ } END { print n + 0 }' "$1/MANIFEST.tsv"; }
tar_members() { tar -tf "$1" 2> /dev/null; }
tar_has() { tar_members "$1" | grep -Fxq -- "$2"; }
rowkind() { awk -F'\t' -v p="$2" '$1 == p { print $2; exit }' "$1"; }
rowcol() { # tsv, path, column name: one field of a sweep or real.tsv row
  awk -F'\t' -v p="$2" -v c="$3" 'NR == 1 { for (i = 1; i <= NF; i++) col[$i] = i; next } $1 == p { print $(col[c]); exit }' "$1"
}
has_row() { awk -F'\t' -v p="$2" '$1 == p { n++ } END { exit n ? 0 : 1 }' "$1"; }

# ------------------------------------------------------------------------------------------------------------ fixtures
W="$HOME/Workspace"
mkdir -p "$W" "$HOME/Library/Cached" "$HOME/.cache/x" "$HOME/.local/share/late" "$HOME/Odd Name" "$W/gitdirs" "$base/outside"

mkrepo "$W/plain"

mkrepo "$W/reflogonly"
printf 'two\n' > "$W/reflogonly/g.txt"
g -C "$W/reflogonly" add g.txt
g -C "$W/reflogonly" commit -q -m two
REFLOG_SHA=$(g -C "$W/reflogonly" rev-parse HEAD)
g -C "$W/reflogonly" reset -q --hard HEAD~1
CRED_URL="https://user:pw@example.invalid/x.git" # a credential in a config the raw copy must leave out
g -C "$W/reflogonly" remote add credtop "$CRED_URL"

mkrepo "$W/wtmain"
g -C "$W/wtmain" worktree add -q "$W/wtlinked" -b wtbranch
MAIN_REF_SHA=$(g -C "$W/wtmain" commit-tree -p HEAD -m main-only 'HEAD^{tree}')
g -C "$W/wtmain" update-ref --no-deref refs/worktree/keep "$MAIN_REF_SHA"
LINKED_REF_SHA=$(g -C "$W/wtlinked" commit-tree -p HEAD -m linked-only 'HEAD^{tree}')
g -C "$W/wtlinked" update-ref --no-deref refs/bisect/bad "$LINKED_REF_SHA"
WT_ID=$(ls "$W/wtmain/.git/worktrees")
g -C "$W/wtmain" config extensions.worktreeConfig true
g -C "$W/wtlinked" config --worktree remote.credwt.url "$CRED_URL"

mkrepo "$W/lfslocal"
LFS_OID=$(printf 'lfs payload one' | shasum -a 256 | cut -d' ' -f1)
mkdir -p "$W/lfslocal/.git/lfs/objects/${LFS_OID:0:2}/${LFS_OID:2:2}"
printf 'lfs payload one' > "$W/lfslocal/.git/lfs/objects/${LFS_OID:0:2}/${LFS_OID:2:2}/$LFS_OID"

mkrepo "$W/annexed"
ANNEX_KEY="SHA256E-s5--0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
mkdir -p "$W/annexed/.git/annex/objects/ab/cd/$ANNEX_KEY"
printf 'annex' > "$W/annexed/.git/annex/objects/ab/cd/$ANNEX_KEY/$ANNEX_KEY"

mkrepo "$W/wtgone"
g -C "$W/wtgone" worktree add -q "$W/wtgone-linked" -b gonebranch
GONE_REF_SHA=$(g -C "$W/wtgone-linked" commit-tree -p HEAD -m gone-only 'HEAD^{tree}')
g -C "$W/wtgone-linked" update-ref --no-deref refs/bisect/gone "$GONE_REF_SHA"
GONE_ID=$(ls "$W/wtgone/.git/worktrees")
rm -rf "$W/wtgone-linked" # the checkout is gone; its admin directory, and the ref in it, are not

mkrepo "$W/lfsreloc"
STORE="$base/outside/lfs-store"
RELOC_OID=$(printf 'lfs payload two' | shasum -a 256 | cut -d' ' -f1)
mkdir -p "$STORE/objects/${RELOC_OID:0:2}/${RELOC_OID:2:2}"
printf 'lfs payload two' > "$STORE/objects/${RELOC_OID:0:2}/${RELOC_OID:2:2}/$RELOC_OID"
g -C "$W/lfsreloc" config lfs.storage "$STORE"

mkrepo "$base/outside/subsrc"
mkrepo "$W/super"
g -C "$W/super" submodule add -q "$base/outside/subsrc" lib > /dev/null 2>&1
g -C "$W/super" commit -q -m "add submodule"
printf 'edited in the submodule\n' >> "$W/super/lib/f.txt"
g -C "$W/super/lib" remote add credmod "$CRED_URL" # lands in .git/modules/lib/config

mkdir -p "$W/gitdirs"
g init -q --separate-git-dir="$W/gitdirs/sepgit.git" "$W/sepgit"
printf 'sep\n' > "$W/sepgit/s.txt"
g -C "$W/sepgit" add s.txt
g -C "$W/sepgit" commit -q -m sep

mkrepo "$W/filtered"
g -C "$W/filtered" config filter.redact.clean "sed s/secret/XXXXXX/"
g -C "$W/filtered" config filter.redact.smudge cat
printf 'nb.txt filter=redact\na.key filter=redact\nbig.bin filter=lfs diff=lfs merge=lfs -text\n' > "$W/filtered/.gitattributes"
printf 'secret\n' > "$W/filtered/nb.txt"
printf 'k-secret\n' > "$W/filtered/a.key"
printf 'pointer-less lfs content\n' > "$W/filtered/big.bin"
printf 'not filtered\n' > "$W/filtered/plain.txt"
g -C "$W/filtered" add .gitattributes nb.txt a.key big.bin plain.txt
g -C "$W/filtered" commit -q -m filtered

mkrepo "$base/outside/bsrc"
for n in 1 2; do # two commits that will become stash entries of the bare repository below
  g -C "$base/outside/bsrc" checkout -q -b "stash$n" main
  printf 'stash %s\n' "$n" > "$base/outside/bsrc/s$n.txt"
  g -C "$base/outside/bsrc" add "s$n.txt"
  g -C "$base/outside/bsrc" commit -q -m "stash $n"
done
g -C "$base/outside/bsrc" checkout -q main
g clone -q --bare "$base/outside/bsrc" "$W/mybare.git"
g -C "$W/mybare.git" remote remove origin
# `git stash` needs a work tree, so give the bare repository stash entries by hand: refs/stash and its reflog
g --git-dir="$W/mybare.git" update-ref --create-reflog -m "stash 1" refs/stash "$(g --git-dir="$W/mybare.git" rev-parse stash1)"
g --git-dir="$W/mybare.git" update-ref --create-reflog -m "stash 2" refs/stash "$(g --git-dir="$W/mybare.git" rev-parse stash2)"
g --git-dir="$W/mybare.git" branch -q -D stash1 stash2
BARE_OID=$(printf 'lfs payload three' | shasum -a 256 | cut -d' ' -f1)
mkdir -p "$W/mybare.git/lfs/objects/${BARE_OID:0:2}/${BARE_OID:2:2}"
printf 'lfs payload three' > "$W/mybare.git/lfs/objects/${BARE_OID:0:2}/${BARE_OID:2:2}/$BARE_OID"

g clone -q "$base/outside/subsrc" "$W/detrepo" # a main checkout with a remote, on a detached HEAD holding a commit no ref names
g -C "$W/detrepo" checkout -q --detach
printf 'detached work\n' > "$W/detrepo/d.txt"
g -C "$W/detrepo" add d.txt
g -C "$W/detrepo" commit -q -m "detached work"

# clean rows the sweep alone calls safe (a remote, nothing unpushed, nothing dirty), for classify --remote-held
mkrepo "$base/outside/rnseed"
g clone -q --bare "$base/outside/rnseed" "$base/outside/rn.git"
g clone -q --bare "$base/outside/rnseed" "$base/outside/rn2.git" # a remote of its own, so two pushes cannot collide
for n in absent proven gap unproven filter; do g clone -q "$base/outside/rn.git" "$W/rn_$n"; done
g clone -q "$base/outside/rn2.git" "$W/rn_same"
g -C "$W/rn_filter" config filter.redact.clean "sed s/secret/XXXXXX/"
g -C "$W/rn_filter" config filter.redact.smudge cat
printf 'nb.txt filter=redact\n' > "$W/rn_filter/.gitattributes"
printf 'secret\n' > "$W/rn_filter/nb.txt"
g -C "$W/rn_filter" add .gitattributes nb.txt
g -C "$W/rn_filter" commit -q -m "filtered notebook"
g -C "$W/rn_filter" push -q origin main
g -C "$W/rn_same" config filter.ident.clean cat # a filter attribute whose output equals the working-tree bytes
g -C "$W/rn_same" config filter.ident.smudge cat
printf 'same.txt filter=ident\n' > "$W/rn_same/.gitattributes"
printf 'identical\n' > "$W/rn_same/same.txt"
g -C "$W/rn_same" add .gitattributes same.txt
g -C "$W/rn_same" commit -q -m "identity filter"
g -C "$W/rn_same" push -q origin main

mkrepo "$W/upper"
CASE_INSENSITIVE=0
if mv "$W/upper/.git" "$W/upper/.GIT" && [ -d "$W/upper/.git" ]; then CASE_INSENSITIVE=1; else mv "$W/upper/.GIT" "$W/upper/.git"; fi
mkdir -p "$W/web/node_modules"
mkrepo "$W/web/node_modules/dep"
deep="$W/a1/a2/a3/a4/a5/a6/a7/a8/a9/a10/a11"
mkdir -p "$deep"
mkrepo "$deep/deep-repo"
mkrepo "$HOME/Odd Name/sp ace repo"
mkrepo "$HOME/Odd Name/two  spaces"
mkrepo "$HOME/.local/share/late/r"
mkrepo "$HOME/Library/Cached/hidden"
mkrepo "$HOME/.cache/x/hidden2"
echo "fixtures built under $base"

# ------------------------------------------------------------------------------------------------------ static checks
# shellcheck disable=SC2016 # the pattern and the substitution match a literal $HOME in the sweep's source
bad_names=$(grep -oE '\$HOME/[A-Za-z._][A-Za-z0-9._/-]*' "$SWEEP" | sed 's#^\$HOME/##' | sort -u | grep -vxE 'Library|\.Trash|\.cache|\.npm|\.cargo|\.rustup|\.local/share' || true)
[ -z "$bad_names" ] && ok "[PS-13] the sweep names no personal directory (only the generic exclusions and .local/share)" \
  || bad "[PS-13] the sweep names these \$HOME directories: $(printf '%s' "$bad_names" | tr '\n' ' ')"
grep -nE '(^|[^a-zA-Z])find .* -x( |$)' "$SWEEP" > /dev/null && bad "the sweep uses find -x, which bfs rejects" || ok "the sweep uses -xdev, never the BSD -x"

# --------------------------------------------------------------------------------------- sweep with explicit roots
OUT1="$base/sweep1"
SWEEP_OUT=$(bash "$SWEEP" "$OUT1" "$W" "$HOME/Odd Name" 2>&1)
SWEEP_RC=$?
[ "$SWEEP_RC" = 0 ] && ok "sweep with explicit roots exits 0" || bad "sweep exited $SWEEP_RC: $(printf '%s' "$SWEEP_OUT" | tail -n 3)"
TSV="$OUT1/git.tsv"
[ -s "$TSV" ] || bad "no git.tsv"
[ ! -s "$OUT1/find.err" ] && ok "the sweep's find printed nothing on stderr" || bad "find.err: $(head -c 300 "$OUT1/find.err")"
expect_kind() { # description, expected kind, path
  local k
  k=$(rowkind "$TSV" "$3")
  [ "$k" = "$2" ] && ok "$1: $3 is kind=$2" || bad "$1: $3 is kind '${k:-<no row>}', expected $2"
}
expect_kind "[H-SWEEP-KIND-SUBMODULE/INT-6] a submodule checkout is a repo, not a worktree" repo "$W/super/lib"
expect_kind "[H-SWEEP-KIND-SUBMODULE/INT-6] a separate-git-dir checkout is a repo" repo "$W/sepgit"
expect_kind "a main checkout is a repo" repo "$W/super"
expect_kind "a linked worktree is a worktree" worktree "$W/wtlinked"
expect_kind "[FP-DISCOVERY-BLIND/§12] a bare repository is swept as kind=bare" bare "$W/mybare.git"
[ "$(rowcol "$TSV" "$W/mybare.git" stashes)" = 2 ] && ok "[§12] a bare repository's stashes column counts the refs/stash reflog (git stash list refuses without a work tree)" \
  || bad "[§12] the bare repository's stashes column is '$(rowcol "$TSV" "$W/mybare.git" stashes)', expected 2"
[ "$(rowcol "$TSV" "$W/mybare.git" dirty)" = 0 ] && ok "[§12] ...and its dirty column is 0" || bad "[§12] the bare repository's dirty column is not 0"
expect_kind "a main checkout on a detached HEAD is a repo" repo "$W/detrepo"
[ "$(rowcol "$TSV" "$W/detrepo" branch)" = "(detached)" ] && [ "$(rowcol "$TSV" "$W/detrepo" head_remote_branches)" = 0 ] \
  && ok "(fixture) the detached main checkout's HEAD is on no remote branch" || bad "(fixture) the detached main checkout is not detached on no remote branch"
has_row "$TSV" "$W/gitdirs/sepgit.git" && bad "a separate git dir was swept as if it were a bare repository" \
  || ok "a separate git dir (core.worktree set) is not mistaken for a bare repository"
expect_kind "[FP-DISCOVERY-BLIND] a repository under node_modules is swept (no name prune)" repo "$W/web/node_modules/dep"
expect_kind "[FP-DISCOVERY-BLIND] a repository deeper than depth 9 is swept (no depth bound)" repo "$deep/deep-repo"
if [ "$CASE_INSENSITIVE" = 1 ]; then
  expect_kind "[FP-DISCOVERY-BLIND] a .GIT spelling is swept (case-insensitive match)" repo "$W/upper"
else
  skip "case-sensitive filesystem: a .GIT directory is not a repository to git, so there is nothing to find"
fi
expect_kind "a root path with spaces: a checkout below it is swept" repo "$HOME/Odd Name/sp ace repo"
expect_kind "a path with two consecutive spaces is swept as is" repo "$HOME/Odd Name/two  spaces"
check "the roots file lists the roots walked, then a matching #END row" python3 -I -c '
import sys
lines = open(sys.argv[1]).read().split("\n")
assert lines[-1] == "" and lines[-2] == "#END rows=%d" % (len(lines) - 2), lines
assert lines[:-2] == [sys.argv[2], sys.argv[3]], lines
' "$OUT1/git.roots" "$W" "$HOME/Odd Name"
if [ -x /bin/bash ] && [ "$(/bin/bash -c 'echo ${BASH_VERSINFO[0]}')" != "$(bash -c 'echo ${BASH_VERSINFO[0]}')" ]; then
  /bin/bash "$SWEEP" "$base/sweep1-sysbash" "$W" "$HOME/Odd Name" > /dev/null 2>&1
  cmp -s "$TSV" "$base/sweep1-sysbash/git.tsv" && ok "the sweep gives the same rows under /bin/bash (bash $(/bin/bash -c 'echo $BASH_VERSION'))" \
    || bad "the sweep differs under /bin/bash"
else
  skip "no second bash version to compare the sweep under"
fi
bash "$SWEEP" "$base/sweep-noroot" "$base/does-not-exist" > /dev/null 2>&1
rc=$?
[ "$rc" = 66 ] && [ ! -e "$base/sweep-noroot/git.roots" ] && ok "an explicit root that does not exist is refused (exit 66), no roots file" \
  || bad "a missing root was accepted (exit $rc)"

# ------------------------------------------------------------------------- sweep with the default roots (fixture $HOME)
OUT2="$base/sweep2"
bash "$SWEEP" "$OUT2" > /dev/null 2>&1
check "[INT-4/FP-DISCOVERY-ROOT-DRIFT/PS-13] the default roots are the generic ones, .local/share included" python3 -I -c '
import os, sys
home = sys.argv[2]
lines = open(sys.argv[1]).read().split("\n")
assert lines[-1] == "" and lines[-2] == "#END rows=%d" % (len(lines) - 2), lines
roots = set(lines[:-2])
want = {home + "/Workspace", home + "/Odd Name", home + "/.local", home + "/.local/share"}
assert roots == want, (sorted(roots), sorted(want))
' "$OUT2/git.roots" "$HOME"
has_row "$OUT2/git.tsv" "$HOME/.local/share/late/r" && ok "[INT-4] a repository under .local/share is swept by default" || bad "[INT-4] a repository under .local/share was not swept"
has_row "$OUT2/git.tsv" "$HOME/Library/Cached/hidden" && bad "a repository under Library was swept" || ok "Library is excluded from the default roots"
has_row "$OUT2/git.tsv" "$HOME/.cache/x/hidden2" && bad "a repository under .cache was swept" || ok ".cache is excluded from the default roots"
has_row "$OUT2/git.tsv" "$W/mybare.git" && has_row "$OUT2/git.tsv" "$HOME/Odd Name/sp ace repo" && ok "the default roots also reach the workspace and the spaced directory" \
  || bad "the default roots missed fixture repositories"

# ------------------------------------------------------------------------------------------------------ merge-sweeps
OLD="$base/old/git.tsv"
mkdir -p "$base/old"
cp "$TSV" "$OLD"
VANISHED="$W/van\"ished"
printf '%s\trepo\tmain\tNONE\t0\t1\t0\t0\n' "$VANISHED" >> "$OLD"
MISSED="$base/outside/missed-checkout"
mkdir -p "$MISSED"
printf '%s\trepo\tmain\tNONE\t0\t1\t0\t0\n' "$MISSED" >> "$OLD"
printf '%s\n%s\n#END rows=2\n' "$W" "$base/outside/old-only-root" > "$base/old/git.roots"
MERGED="$base/merged/merged.tsv"
mkdir -p "$base/merged"
MERGE_OUT=$(python3 -I "$MERGE" "$TSV" "$OLD" "$MERGED" 2>&1)
MERGE_RC=$?
[ "$MERGE_RC" = 0 ] && ok "merge-sweeps exits 0 on two sweeps with valid roots files" || bad "merge-sweeps exited $MERGE_RC: $MERGE_OUT"
check "[INT-4/§12] merge-sweeps writes merged.roots holding the union of both roots files" python3 -I -c '
import sys
lines = open(sys.argv[1]).read().split("\n")
assert lines[-1] == "" and lines[-2] == "#END rows=%d" % (len(lines) - 2), lines
assert set(lines[:-2]) == {sys.argv[2], sys.argv[3], sys.argv[4]} and len(lines) - 2 == 3, lines
' "$base/merged/merged.roots" "$W" "$HOME/Odd Name" "$base/outside/old-only-root"
VANISHED_ROW=$(printf '%s\trepo\tmain\tNONE\t0\t1\t0\t0' "$VANISHED")
check "merge-sweeps keeps a vanished row byte for byte (a path holding a quote is not rewritten)" grep -Fxq -- "$VANISHED_ROW" "$MERGED"
check "merge-sweeps keeps a row the fresh sweep missed while the path still exists" grep -Fq "$MISSED" "$MERGED"
bad_roots() { # description, file contents (printf format), pass a file text
  local d=$1 text=$2 dir
  dir=$(mktemp -d "$base/work/badroots.XXXXXX")
  cp "$TSV" "$dir/git.tsv"
  cp "$OLD" "$dir/old.tsv"
  printf '%s\n%s\n#END rows=2\n' "$W" "$base/outside/old-only-root" > "$dir/old.roots"
  # shellcheck disable=SC2059 # the caller passes a printf format on purpose
  printf "$text" "$W" "$HOME/Odd Name" > "$dir/git.roots"
  python3 -I "$MERGE" "$dir/git.tsv" "$dir/old.tsv" "$dir/out.tsv" > "$dir/stdout" 2> "$dir/stderr"
  local rc=$?
  if [ "$rc" != 0 ] && [ ! -e "$dir/out.tsv" ] && [ ! -e "$dir/out.roots" ]; then ok "$d: refused (exit $rc), nothing written"; else bad "$d: exit $rc, out.tsv $([ -e "$dir/out.tsv" ] && echo written || echo absent)"; fi
}
bad_roots "[§12 negative control] a roots file with no #END row" '%s\n%s\n'
bad_roots "[§12 negative control] a roots file whose #END count is wrong" '%s\n%s\n#END rows=5\n'
bad_roots "[§12 negative control] a roots file with a duplicated #END row" '%s\n%s\n#END rows=2\n#END rows=2\n'
bad_roots "[§12 negative control] a roots file whose #END row is not last" '%s\n#END rows=1\n%s\n'
dir=$(mktemp -d "$base/work/noroots.XXXXXX")
cp "$TSV" "$dir/git.tsv"
cp "$OLD" "$dir/old.tsv"
python3 -I "$MERGE" "$dir/git.tsv" "$dir/old.tsv" "$dir/out.tsv" > /dev/null 2>&1
rc=$?
[ "$rc" != 0 ] && [ ! -e "$dir/out.tsv" ] && ok "[§12 negative control] merge-sweeps refuses when a roots file is missing altogether" || bad "merge-sweeps accepted sweeps without roots files (exit $rc)"
# a previous sweep from before roots files existed: refused unless the legacy switch is set, and only for a MISSING file
legacy() { # name, then the environment assignments for the run; sets L_RC, L_DIR, L_ERR
  L_DIR=$(mktemp -d "$base/work/legacy-$1.XXXXXX")
  shift
  cp "$TSV" "$L_DIR/git.tsv"
  cp "$OLD" "$L_DIR/old.tsv"
  printf '%s\n%s\n#END rows=2\n' "$W" "$HOME/Odd Name" > "$L_DIR/git.roots"
  env "$@" python3 -I "$MERGE" "$L_DIR/git.tsv" "$L_DIR/old.tsv" "$L_DIR/out.tsv" > "$L_DIR/stdout" 2> "$L_DIR/stderr"
  L_RC=$?
  L_ERR=$(cat "$L_DIR/stderr")
}
legacy refused X=1
[ "$L_RC" != 0 ] && [ ! -e "$L_DIR/out.tsv" ] && [ ! -e "$L_DIR/out.roots" ] && ok "[legacy] a previous sweep with no roots file is refused without MERGE_SWEEPS_LEGACY_OLD" \
  || bad "[legacy] a previous sweep with no roots file was accepted (exit $L_RC)"
legacy accepted MERGE_SWEEPS_LEGACY_OLD=1
[ "$L_RC" = 0 ] && [ -s "$L_DIR/out.tsv" ] && ok "[legacy] ...and accepted with MERGE_SWEEPS_LEGACY_OLD=1" || bad "[legacy] the legacy switch did not carry the old sweep forward (exit $L_RC): $L_ERR"
[ "$(printf '%s\n' "$L_ERR" | wc -l | tr -d ' ')" = 1 ] && case "$L_ERR" in *"roots are unknown"*) true ;; *) false ;; esac \
  && ok "[legacy] ...with exactly one stderr line saying the old sweep's roots were unknown" || bad "[legacy] stderr is not the one expected line: $L_ERR"
[ "$(cat "$L_DIR/out.roots" 2> /dev/null)" = "$(printf '%s\n%s\n#END rows=2' "$W" "$HOME/Odd Name")" ] && ok "[legacy] ...and the merged roots are the fresh sweep's only" \
  || bad "[legacy] merged roots: $(cat "$L_DIR/out.roots" 2> /dev/null)"
legacy malformed MERGE_SWEEPS_LEGACY_OLD=1
printf '%s\n' "$W" > "$L_DIR/old.roots"
rm -f "$L_DIR/out.tsv" "$L_DIR/out.roots"
env MERGE_SWEEPS_LEGACY_OLD=1 python3 -I "$MERGE" "$L_DIR/git.tsv" "$L_DIR/old.tsv" "$L_DIR/out.tsv" > /dev/null 2>&1
rc=$?
[ "$rc" != 0 ] && [ ! -e "$L_DIR/out.tsv" ] && [ ! -e "$L_DIR/out.roots" ] && ok "[legacy negative control] a previous roots file that exists but is malformed is refused even with the switch" \
  || bad "[legacy negative control] a malformed previous roots file was accepted with the switch (exit $rc)"
legacy nofresh MERGE_SWEEPS_LEGACY_OLD=1
rm -f "$L_DIR/git.roots" "$L_DIR/out.tsv" "$L_DIR/out.roots"
env MERGE_SWEEPS_LEGACY_OLD=1 python3 -I "$MERGE" "$L_DIR/git.tsv" "$L_DIR/old.tsv" "$L_DIR/out.tsv" > /dev/null 2>&1
rc=$?
[ "$rc" != 0 ] && [ ! -e "$L_DIR/out.tsv" ] && ok "[legacy negative control] the fresh sweep must have a valid roots file even with the switch" || bad "[legacy negative control] a fresh sweep without roots was accepted with the switch (exit $rc)"

# ------------------------------------------------------------------------------------------------------------ classify
REAL="$base/real.tsv"
CLASS_OUT=$(python3 -I "$CLASSIFY" "$TSV" --out "$REAL" 2>&1)
CLASS_RC=$?
[ "$CLASS_RC" = 0 ] && ok "classify exits 0 on a sweep with a bare row" || bad "classify exited $CLASS_RC: $(printf '%s' "$CLASS_OUT" | tail -n 2)"
has_row "$REAL" "$W/mybare.git" && ok "[§12] a bare repository with no remote is real exposure" || bad "[§12] the bare repository is missing from real.tsv"
has_row "$REAL" "$W/detrepo" && case "$(rowcol "$REAL" "$W/detrepo" reasons)" in *detached-head-on-no-remote-branch*) true ;; *) false ;; esac \
  && ok "[live-lane §4] a detached HEAD on no remote branch is a reason for a main checkout too, not only a worktree" \
  || bad "[live-lane §4] the detached main checkout is not listed for its detached HEAD"
has_row "$REAL" "$W/super/lib" && ok "the dirty submodule checkout is real exposure" || bad "the dirty submodule checkout is missing from real.tsv"
has_row "$REAL" "$W/wtlinked" && bad "a clean linked worktree was classified as real exposure" || ok "a clean linked worktree is not listed (its repository is)"

# --------------------------------------------------------------------------------------------------------- preserve
DEST="$base/dest"
DRY_OUT=$(bash "$PRESERVE" "$REAL" "$DEST" dry 2>&1)
DRY_RC=$?
[ "$DRY_RC" = 0 ] && [ ! -e "$DEST" ] && ok "dry run exits 0 and creates no destination" || bad "dry run: exit $DRY_RC, destination $([ -e "$DEST" ] && echo created || echo absent)"
case "$DRY_OUT" in *"GITDIR required=reflog-only"*) ok "dry run reports the reflog-only raw copy" ;; *) bad "dry run does not report GITDIR required=reflog-only" ;; esac
case "$DRY_OUT" in *"LFS-STORAGE "*"$STORE"*) ok "dry run reports the relocated LFS store" ;; *) bad "dry run does not report the relocated LFS store" ;; esac
case "$DRY_OUT" in *"FILTERED paths=3 $W/filtered"*) ok "dry run reports the filter-attribute paths of the filtered checkout" ;; *) bad "dry run does not report FILTERED paths=3" ;; esac

APPLY_OUT=$(bash "$PRESERVE" "$REAL" "$DEST" apply 2>&1)
APPLY_RC=$?
[ "$APPLY_RC" = 0 ] && ok "apply exits 0" || bad "apply exited $APPLY_RC: $(printf '%s' "$APPLY_OUT" | tail -n 3)"
RUN=$(find "$DEST" -maxdepth 1 -type d -name 'run-*' 2> /dev/null | sort | tail -n 1)
[ -d "$RUN" ] || { bad "no run directory"; echo "RESULT: FAIL ($passes checks passed; fixture kept for inspection: $base)"; exit 1; }
REAL_ROWS=$(awk 'END { print NR - 1 }' "$REAL")
[ "$(mcount "$RUN" bundle)" = "$REAL_ROWS" ] && [ "$REAL_ROWS" = 18 ] && ok "one bundle item per real row, each its own common dir ($REAL_ROWS)" \
  || bad "bundle items: $(mcount "$RUN" bundle), real rows: $REAL_ROWS (expected 18 distinct common dirs)"

# item expectations -----------------------------------------------------------------------------------------------
gitdir_tar_of() { mfield "$RUN" gitdir-tar "$(slug_of "$1")" file; }
status_of() { mfield "$RUN" "$1" "$(slug_of "$2")" status; }
note_of() { mfield "$RUN" "$1" "$(slug_of "$2")" note; }

C_PLAIN="$W/plain/.git"
for c in "$C_PLAIN" "$W/filtered/.git" "$W/lfsreloc/.git" "$W/gitdirs/sepgit.git" "$W/web/node_modules/dep/.git" "$W/super/.git/modules/lib"; do
  [ -z "$(gitdir_tar_of "$c")" ] && ok "no raw git-dir copy where nothing needs one: ${c#"$HOME/"}" || bad "an unneeded raw git-dir copy was made for ${c#"$HOME/"}"
done
[ "$(status_of bundle "$C_PLAIN")" = ok ] && ok "the plain repository is bundled" || bad "the plain repository has no ok bundle"
[ -z "$(status_of lfs-storage-tar "$C_PLAIN")" ] && [ -z "$(mfield "$RUN" filtered-tar "$(slug_of "$W/plain")" status)" ] \
  && ok "a plain repository gets no lfs-storage-tar and no filtered-tar" || bad "a plain repository got an LFS store or filtered copy"

T=$(gitdir_tar_of "$W/reflogonly/.git")
[ "$(status_of gitdir-tar "$W/reflogonly/.git")" = ok ] && ok "[P7/H-REFLOG-ONLY/INT-2] a reflog-only commit makes a raw git-dir copy required, and it is made" \
  || bad "[P7/H-REFLOG-ONLY/INT-2] no ok gitdir-tar for the repository with a reflog-only commit"
case "$(note_of gitdir-tar "$W/reflogonly/.git")" in *reflog-only*) ok "[P7] ...and its note names the reason: reflog-only" ;; *) bad "[P7] the gitdir-tar note does not name reflog-only" ;; esac
[ -n "$T" ] && tar_has "$RUN/$T" ".git/objects/${REFLOG_SHA:0:2}/${REFLOG_SHA:2}" && ok "[P7] ...and the reflog-only commit's object is in it" \
  || bad "[P7] the reflog-only commit's object is not in the raw git-dir copy"
git --git-dir="$W/reflogonly/.git" rev-list --branches --tags --remotes | grep -q "$REFLOG_SHA" \
  && bad "fixture error: the commit is reachable from a ref" || ok "(fixture) the commit is reachable from no ref, so a bundle cannot hold it"

T=$(gitdir_tar_of "$W/wtmain/.git")
[ "$(status_of gitdir-tar "$W/wtmain/.git")" = ok ] && ok "[P7/P3] per-worktree refs make a raw git-dir copy required, and it is made" \
  || bad "[P7/P3] no ok gitdir-tar for the repository with per-worktree refs"
case "$(note_of gitdir-tar "$W/wtmain/.git")" in *per-worktree-refs*) ok "[P7] ...and its note names the reason: per-worktree-refs" ;; *) bad "[P7] the gitdir-tar note does not name per-worktree-refs" ;; esac
[ -n "$T" ] && tar_has "$RUN/$T" ".git/worktrees/$WT_ID/refs/bisect/bad" && tar_has "$RUN/$T" ".git/refs/worktree/keep" \
  && ok "[P7] ...and both per-worktree ref files are in it" || bad "[P7] a per-worktree ref file is missing from the raw git-dir copy"
[ -n "$T" ] && tar_has "$RUN/$T" ".git/objects/${LINKED_REF_SHA:0:2}/${LINKED_REF_SHA:2}" && tar_has "$RUN/$T" ".git/objects/${MAIN_REF_SHA:0:2}/${MAIN_REF_SHA:2}" \
  && ok "[P7] ...and so are the commits only those refs hold" || bad "[P7] a per-worktree-only commit is missing from the raw git-dir copy"

T=$(gitdir_tar_of "$W/wtgone/.git")
[ "$(status_of gitdir-tar "$W/wtgone/.git")" = ok ] && [ -n "$T" ] && tar_has "$RUN/$T" ".git/worktrees/$GONE_ID/refs/bisect/gone" \
  && tar_has "$RUN/$T" ".git/objects/${GONE_REF_SHA:0:2}/${GONE_REF_SHA:2}" \
  && ok "[P7/P3] a per-worktree ref of a linked worktree whose checkout is gone still makes the raw copy required, and holds it" \
  || bad "[P7/P3] the per-worktree ref of a worktree whose checkout is gone is not in a raw git-dir copy"

T=$(gitdir_tar_of "$W/annexed/.git")
[ "$(status_of gitdir-tar "$W/annexed/.git")" = ok ] && [ -n "$T" ] && tar_has "$RUN/$T" ".git/annex/objects/ab/cd/$ANNEX_KEY/$ANNEX_KEY" \
  && ok "[P9] git-annex objects under .git/annex/objects make a raw git-dir copy required, and it holds them" \
  || bad "[P9] the git-annex object is not in a raw git-dir copy"

T=$(gitdir_tar_of "$W/lfslocal/.git")
[ "$(status_of gitdir-tar "$W/lfslocal/.git")" = ok ] && ok "[INT-2/FP-UNSTORED-CONTENT] LFS objects under .git/lfs make a raw git-dir copy required, and it is made" \
  || bad "[INT-2] no ok gitdir-tar for the repository with local LFS objects"
[ -n "$T" ] && tar_has "$RUN/$T" ".git/lfs/objects/${LFS_OID:0:2}/${LFS_OID:2:2}/$LFS_OID" && ok "[INT-2] ...and the LFS object file is in it" \
  || bad "[INT-2] the LFS object is not in the raw git-dir copy"

T=$(mfield "$RUN" lfs-storage-tar "$(slug_of "$W/lfsreloc/.git")" file)
[ "$(status_of lfs-storage-tar "$W/lfsreloc/.git")" = ok ] && ok "[P9] a relocated lfs.storage gets an lfs-storage-tar item" || bad "[P9] no ok lfs-storage-tar for the relocated LFS store"
[ "$(mfield "$RUN" lfs-storage-tar "$(slug_of "$W/lfsreloc/.git")" source)" = "$STORE" ] && ok "[P9] ...whose source is the storage directory" || bad "[P9] the lfs-storage-tar source is not the storage directory"
[ -n "$T" ] && tar_has "$RUN/$T" "lfs-store/objects/${RELOC_OID:0:2}/${RELOC_OID:2:2}/$RELOC_OID" && ok "[P9] ...and holds the relocated LFS object" || bad "[P9] the relocated LFS object is not in the tar"

T=$(gitdir_tar_of "$W/super/.git")
[ "$(status_of gitdir-tar "$W/super/.git")" = ok ] && ok "[§6] submodule git dirs make a raw git-dir copy required, and it is made" || bad "[§6] no ok gitdir-tar for the superproject"
case "$(note_of gitdir-tar "$W/super/.git")" in *submodule-gitdirs*) ok "[§6] ...and its note names the reason: submodule-gitdirs" ;; *) bad "[§6] the gitdir-tar note does not name submodule-gitdirs" ;; esac
[ -n "$T" ] && tar_has "$RUN/$T" ".git/modules/lib/HEAD" && ok "[§6] ...and modules/lib is in it" || bad "[§6] modules/lib/HEAD is not in the raw git-dir copy"
LIB_COMMON=$(cd -P "$W/super/.git/modules/lib" && pwd -P)
[ "$(status_of bundle "$LIB_COMMON")" = ok ] && ok "the submodule checkout's own git dir (modules/lib) is bundled" || bad "the submodule checkout has no ok bundle of modules/lib"
[ "$(status_of tracked-patch "$W/super/lib")" = ok ] && ok "the submodule checkout's uncommitted edit is preserved as a tracked patch" || bad "no tracked patch for the dirty submodule checkout"

T=$(mfield "$RUN" filtered-tar "$(slug_of "$W/filtered")" file)
[ "$(mfield "$RUN" filtered-tar "$(slug_of "$W/filtered")" status)" = ok ] && ok "[FP-UNSTORED-CONTENT] a checkout with filter-attribute paths gets a filtered-tar (clean row, not dirty)" \
  || bad "[FP-UNSTORED-CONTENT] no ok filtered-tar for the filtered checkout"
if [ -n "$T" ]; then
  [ "$(tar_members "$RUN/$T" | sort | tr '\n' ' ')" = "big.bin nb.txt " ] && ok "[FP-UNSTORED-CONTENT] ...holding exactly the filter-attribute files that may be copied (not the credential-pattern name, not plain.txt)" \
    || bad "[FP-UNSTORED-CONTENT] filtered-tar members are: $(tar_members "$RUN/$T" | tr '\n' ' ')"
  [ "$(tar -xOf "$RUN/$T" nb.txt 2> /dev/null)" = secret ] && [ "$(g -C "$W/filtered" cat-file blob HEAD:nb.txt)" = XXXXXX ] \
    && ok "[FP-UNSTORED-CONTENT] ...with working-tree bytes that differ from the blob git stores" || bad "[FP-UNSTORED-CONTENT] the filtered file does not hold the working-tree bytes"
else
  bad "[FP-UNSTORED-CONTENT] no filtered-tar file to read"
fi
[ -z "$(g -C "$W/filtered" status --porcelain)" ] && ok "(fixture) git status calls the filtered checkout clean, so no status-driven snapshot could hold it" || bad "(fixture) the filtered checkout is not clean"

T=$(gitdir_tar_of "$W/mybare.git")
[ "$(status_of bundle "$W/mybare.git")" = ok ] && ok "[§12] a bare repository is bundled (common dir = the bare directory)" || bad "[§12] the bare repository has no ok bundle"
[ "$(status_of stash-reflog "$W/mybare.git")" = ok ] && [ "$(status_of stash-patch "$W/mybare.git")" = ok ] \
  && ok "[§12] ...and its lower stash entry is preserved as a patch with the refs/stash reflog" || bad "[§12] the bare repository's stash entries are not preserved"
[ "$(status_of head-bundle "$W/detrepo")" = ok ] && ok "[live-lane §4] a detached main checkout gets a head bundle" || bad "[live-lane §4] the detached main checkout has no ok head-bundle"
[ "$(status_of gitdir-tar "$W/mybare.git")" = ok ] && [ -n "$T" ] && tar_has "$RUN/$T" "mybare.git/lfs/objects/${BARE_OID:0:2}/${BARE_OID:2:2}/$BARE_OID" \
  && ok "[§12/§6] ...and, because it holds LFS objects, a raw git-dir copy with them" || bad "[§12/§6] the bare repository's LFS object is not in a raw git-dir copy"

# ---------------------------------------------------------------------------------------------------------- verify
verify() { # run dir [real.tsv]: runs the verifier, sets V_RC and V_RESULT (RESULT.txt text)
  bash "$VERIFY" "${2:-$REAL}" "$1" > "$base/work/verify.out" 2>&1
  V_RC=$?
  V_RESULT=$(cat "$1/RESULT.txt" 2> /dev/null)
}
verify "$RUN"
[ "$V_RC" = 0 ] && [ "$(printf '%s' "$V_RESULT" | head -n 1)" = PASS ] && ok "verify-preserve.sh says PASS on the good run" || bad "verify on the good run: rc $V_RC: $(printf '%s' "$V_RESULT" | sed -n '/FAILURES/,$p' | head -n 6)"
case "$V_RESULT" in *"raw_git_dir_copies_required=7 verified=7;"*) ok "[§6] the verifier recomputed and verified all 7 required raw git-dir copies" ;; *) bad "[§6] verifier result lacks raw_git_dir_copies_required=7 verified=7: $(printf '%s' "$V_RESULT" | grep raw_git_dir || echo none)" ;; esac
case "$V_RESULT" in *"lfs_stores_outside_git_dir=1 verified=1;"*) ok "[P9] ...and the relocated LFS store" ;; *) bad "[P9] verifier result lacks lfs_stores_outside_git_dir=1 verified=1" ;; esac
case "$V_RESULT" in *"checkouts_with_filtered_paths=1 verified=1"*) ok "[FP-UNSTORED-CONTENT] ...and the filtered checkout" ;; *) bad "[FP-UNSTORED-CONTENT] verifier result lacks checkouts_with_filtered_paths=1 verified=1" ;; esac
EXPECT_GITDIR=$(for r in reflogonly wtmain wtgone annexed lfslocal super; do slug_of "$W/$r/.git"; done; slug_of "$W/mybare.git")
ACTUAL_GITDIR=$(awk -F'\t' '$1 == "gitdir-tar" && $2 == "ok" { print $3 }' "$RUN/MANIFEST.tsv")
[ "$(printf '%s\n' "$EXPECT_GITDIR" | sort)" = "$(printf '%s\n' "$ACTUAL_GITDIR" | sort)" ] && ok "the producer made a raw git-dir copy for exactly the repositories the verifier requires one for" \
  || bad "raw git-dir copies made: $(printf '%s' "$ACTUAL_GITDIR" | wc -l | tr -d ' ') vs expected $(printf '%s' "$EXPECT_GITDIR" | wc -l | tr -d ' ')"

RUN_LINE=$(printf '%s\n' "$V_RESULT" | grep -n '^run=' | head -n 1 | cut -d: -f1)
[ -n "$RUN_LINE" ] && [ "$(printf '%s\n' "$V_RESULT" | sed -n "$((RUN_LINE + 1))p")" = "manifest_sha256=$(shasum -a 256 "$RUN/MANIFEST.tsv" | cut -d' ' -f1)" ] \
  && ok "[integrator] RESULT.txt carries manifest_sha256=<sha256 of MANIFEST.tsv> right after the run= line" \
  || bad "[integrator] RESULT.txt lacks a matching manifest_sha256 line after the run= line"

# credentials in a copied git dir: every config / config.worktree with a user:password@ URL stays out and is listed -------
cred_listed() { # slug, path: is there a gitdir-tar line for it in credential-skipped.txt
  awk -F'\t' -v s="$1" -v p="$2" '$1 == "gitdir-tar" && $2 == s && $3 == p { n++ } END { exit n ? 0 : 1 }' "$RUN/dirty/credential-skipped.txt"
}
T=$(gitdir_tar_of "$W/reflogonly/.git")
! tar_has "$RUN/$T" ".git/config" && cred_listed "$(slug_of "$W/reflogonly/.git")" ".git/config" \
  && ok "[integrator] the top-level config with a credential URL is left out of the raw copy and listed" || bad "[integrator] the top-level credential config is in the copy or not listed"
T=$(gitdir_tar_of "$W/wtmain/.git")
! tar_has "$RUN/$T" ".git/worktrees/$WT_ID/config.worktree" && cred_listed "$(slug_of "$W/wtmain/.git")" ".git/worktrees/$WT_ID/config.worktree" \
  && tar_has "$RUN/$T" ".git/config" && ok "[integrator] worktrees/<id>/config.worktree with a credential URL is left out and listed; the clean config is kept" \
  || bad "[integrator] the credential config.worktree is in the copy, unlisted, or the clean config went missing"
T=$(gitdir_tar_of "$W/super/.git")
! tar_has "$RUN/$T" ".git/modules/lib/config" && cred_listed "$(slug_of "$W/super/.git")" ".git/modules/lib/config" && tar_has "$RUN/$T" ".git/modules/lib/HEAD" \
  && ok "[integrator] modules/<name>/config with a credential URL is left out and listed; the rest of modules/ is kept" \
  || bad "[integrator] the submodule's credential config is in the copy, unlisted, or the module went missing"
T=$(gitdir_tar_of "$W/lfslocal/.git")
tar_has "$RUN/$T" ".git/config" && ok "a config with no credential URL is kept in the raw copy" || bad "a clean config was left out of the raw copy"
grep -rqF 'user:pw@' "$RUN" && bad "[integrator] a credential URL is somewhere in the run" || ok "[integrator] no credential URL is anywhere in the run"

# negative controls -------------------------------------------------------------------------------------------------
MUT="$base/work/mutate.py"
cat > "$MUT" <<'PY'
import hashlib
import io
import os
import sys
import tarfile

run, op, kind, slug = sys.argv[1:5]
args = sys.argv[5:]
mf = os.path.join(run, "MANIFEST.tsv")
with open(mf, newline="") as fh:
    lines = fh.read().split("\n")
cols = lines[0].split("\t")
ix = {c: i for i, c in enumerate(cols)}
hit = None
for n, ln in enumerate(lines[1:], start=1):
    f = ln.split("\t")
    if len(f) == len(cols) and f[ix["item_kind"]] == kind and f[ix["slug"]] == slug:
        hit = n
if hit is None:
    sys.exit("no manifest item %s %s" % (kind, slug))
f = lines[hit].split("\t")
path = os.path.join(run, f[ix["file"]]) if f[ix["file"]] else None


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


if op == "drop-item":
    if path:
        os.remove(path)
    del lines[hit]
elif op == "drop-member":
    kept = []
    with tarfile.open(path) as src:
        for m in src.getmembers():
            if any(m.name == a or m.name.endswith("/" + a) for a in args):
                continue
            kept.append((m, src.extractfile(m).read() if m.isreg() else None))
    if len(kept) == 0:
        sys.exit("dropped everything")
    with tarfile.open(path, "w") as dst:
        for m, data in kept:
            dst.addfile(m, io.BytesIO(data) if data is not None else None)
    f[ix["entries"]] = str(len(kept))
    f[ix["bytes"]] = str(os.path.getsize(path))
    f[ix["sha256"]] = sha(path)
    lines[hit] = "\t".join(f)
elif op == "add-member":
    src, name = args
    with tarfile.open(path, "a") as dst:
        dst.add(src, arcname=name)
    with tarfile.open(path) as check:
        f[ix["entries"]] = str(len(check.getmembers()))
    f[ix["bytes"]] = str(os.path.getsize(path))
    f[ix["sha256"]] = sha(path)
    lines[hit] = "\t".join(f)
elif op == "truncate":
    size = os.path.getsize(path)
    with open(path, "r+b") as fh:
        fh.truncate(size // 2)
    f[ix["bytes"]] = str(os.path.getsize(path))
    f[ix["sha256"]] = sha(path)
    lines[hit] = "\t".join(f)
else:
    sys.exit("unknown op " + op)
with open(mf, "w", newline="") as fh:
    fh.write("\n".join(lines))
PY
mutate() { python3 -I "$MUT" "$@"; }
copy_run() { # name: a fresh copy of the good run
  rm -rf "$base/work/$1"
  cp -R "$RUN" "$base/work/$1"
  rm -f "$base/work/$1/RESULT.txt"
}
expect_refused() { # description, run copy, substring the FAILURES list must contain
  verify "$2"
  if [ "$V_RC" = 1 ] && [ "$(printf '%s' "$V_RESULT" | head -n 1)" = FAIL ] && printf '%s' "$V_RESULT" | grep -Fq -- "$3"; then ok "$1: refused"
  else bad "$1: expected FAIL mentioning '$3', got rc $V_RC, '$(printf '%s' "$V_RESULT" | head -n 1)': $(printf '%s' "$V_RESULT" | sed -n '/FAILURES/,$p' | head -n 3)"; fi
}

copy_run n0
verify "$base/work/n0"
[ "$V_RC" = 0 ] && ok "(control) an unmodified copy of the run verifies" || bad "(control) the unmodified copy does not verify"

copy_run n1
mutate "$base/work/n1" drop-member gitdir-tar "$(slug_of "$W/reflogonly/.git")" ".git/objects/${REFLOG_SHA:0:2}/${REFLOG_SHA:2}"
expect_refused "[P7 negative control] a gitdir-tar missing the reflog-only commit's object" "$base/work/n1" "reflog-only commit(s) are not in the raw git-dir copy"

copy_run n2
mutate "$base/work/n2" drop-member gitdir-tar "$(slug_of "$W/wtmain/.git")" ".git/worktrees/$WT_ID/refs/bisect/bad"
expect_refused "[P7 negative control] a gitdir-tar missing a linked worktree's per-worktree ref file" "$base/work/n2" "per-worktree ref refs/bisect/bad"

copy_run n3
mutate "$base/work/n3" drop-member gitdir-tar "$(slug_of "$W/wtmain/.git")" ".git/objects/${LINKED_REF_SHA:0:2}/${LINKED_REF_SHA:2}"
expect_refused "[P7 negative control] a gitdir-tar missing the commit a per-worktree ref holds" "$base/work/n3" "object"

copy_run n4
mutate "$base/work/n4" drop-member gitdir-tar "$(slug_of "$W/lfslocal/.git")" ".git/lfs/objects/${LFS_OID:0:2}/${LFS_OID:2:2}/$LFS_OID"
expect_refused "[INT-2 negative control] a gitdir-tar missing an LFS object file" "$base/work/n4" "LFS/annex object file(s) are not in the raw git-dir copy"

copy_run n5
mutate "$base/work/n5" drop-member gitdir-tar "$(slug_of "$W/super/.git")" ".git/modules/lib/HEAD"
expect_refused "[§6 negative control] a gitdir-tar missing a modules/ entry" "$base/work/n5" "entr(ies) of modules/ are not in the raw git-dir copy"

copy_run n14
mutate "$base/work/n14" add-member gitdir-tar "$(slug_of "$W/super/.git")" "$W/super/.git/modules/lib/config" ".git/modules/lib/config"
expect_refused "[integrator negative control] a raw git-dir copy that holds a config with a credential URL" "$base/work/n14" "must be left out"

copy_run n12
mutate "$base/work/n12" drop-member gitdir-tar "$(slug_of "$W/annexed/.git")" ".git/annex/objects/ab/cd/$ANNEX_KEY/$ANNEX_KEY"
expect_refused "[P9 negative control] a gitdir-tar missing a git-annex object file" "$base/work/n12" "LFS/annex object file(s) are not in the raw git-dir copy"

copy_run n13
mutate "$base/work/n13" drop-member gitdir-tar "$(slug_of "$W/wtgone/.git")" ".git/worktrees/$GONE_ID/refs/bisect/gone"
expect_refused "[P7 negative control] a gitdir-tar missing the per-worktree ref of a worktree whose checkout is gone" "$base/work/n13" "per-worktree ref refs/bisect/gone"

copy_run n6
mutate "$base/work/n6" drop-member filtered-tar "$(slug_of "$W/filtered")" "big.bin"
expect_refused "[FP-UNSTORED-CONTENT negative control] a filtered-tar missing a file" "$base/work/n6" "lacks 1 of the 2 filter-attribute file(s)"

copy_run n7
mutate "$base/work/n7" truncate lfs-storage-tar "$(slug_of "$W/lfsreloc/.git")"
expect_refused "[P9 negative control] a truncated lfs-storage-tar" "$base/work/n7" ".lfs-storage.tar"

copy_run n8
mutate "$base/work/n8" drop-item gitdir-tar "$(slug_of "$W/reflogonly/.git")"
expect_refused "[P7 negative control] the run has no gitdir-tar item for a repository that needs one" "$base/work/n8" "no usable gitdir-tar item"

copy_run n9
mutate "$base/work/n9" drop-item filtered-tar "$(slug_of "$W/filtered")"
expect_refused "[FP-UNSTORED-CONTENT negative control] the run has no filtered-tar item for a checkout with filter paths" "$base/work/n9" "no filtered-tar item"

copy_run n10
mutate "$base/work/n10" drop-item lfs-storage-tar "$(slug_of "$W/lfsreloc/.git")"
expect_refused "[P9 negative control] the run has no lfs-storage-tar item for a relocated LFS store" "$base/work/n10" "no lfs-storage-tar item"

copy_run n11
mutate "$base/work/n11" drop-member lfs-storage-tar "$(slug_of "$W/lfsreloc/.git")" "lfs-store/objects/${RELOC_OID:0:2}/${RELOC_OID:2:2}/$RELOC_OID"
expect_refused "[P9 negative control] an lfs-storage-tar missing the stored object" "$base/work/n11" "file(s) of the LFS store"

# ------------------------------------------------------------------- classify --remote-held (the prover's proof)
# The shape is the prover's remote-held.tsv: one row per repository, the columns below, a full-width `#END rows=N` row last.
cat > "$base/work/mkheld.py" <<'PY'
import sys

COLS = ["repo", "common_dir", "remotes", "branches_total", "exact", "ancestor", "merged_pr", "unproven", "dirty_entries",
        "stashes", "verdict", "first_reason", "tags_total", "tags_unproven", "other_unproven", "detached_total",
        "detached_unproven", "worktrees", "dirty_worktrees", "rows", "scope", "seconds", "paths", "branches_verdict",
        "superseded_bot", "all_reasons", "notes", "gaps"]
out, mode = sys.argv[1:3]
cols = [c for c in COLS if not (mode == "nogaps" and c == "gaps")]
rows = []
for spec in sys.argv[3:]:
    path, verdict, gaps = spec.split("|")
    cell = dict.fromkeys(cols, "")
    cell.update(repo=path, common_dir=path + "/.git", verdict=verdict, paths=path, gaps=gaps)
    rows.append("\t".join(cell[c] for c in cols))
end = "\t".join([f"#END rows={len(rows) + (1 if mode == 'wrongcount' else 0)}"] + ["#END"] * (len(cols) - 1))
if mode == "shortend":
    end = f"#END rows={len(rows)}"
lines = ["\t".join(cols), *rows]
if mode == "dupend":
    lines += [end, end]
elif mode == "endnotlast":
    lines += [end, rows[0]]
elif mode != "noend":
    lines.append(end)
with open(out, "w", newline="") as fh:
    fh.write("\n".join(lines) + ("" if mode == "nonl" else "\n"))
PY
mkheld() { python3 -I "$base/work/mkheld.py" "$@"; }
HELD="$base/work/remote-held.tsv"
mkheld "$HELD" ok "$W/rn_proven|PROVEN-ALL|" "$W/rn_gap|PROVEN-ALL|NONGITHUB-HISTORY-ASSUMED" "$W/rn_unproven|UNPROVEN|" \
  "$W/rn_filter|PROVEN-ALL|" "$W/rn_same|PROVEN-ALL|"
REAL_H="$base/real-held.tsv"
CH_OUT=$(python3 -I "$CLASSIFY" "$TSV" --out "$REAL_H" --remote-held "$HELD" 2>&1)
CH_RC=$?
[ "$CH_RC" = 0 ] && ok "classify --remote-held exits 0 on a well-formed remote-held.tsv" || bad "classify --remote-held exited $CH_RC: $(printf '%s' "$CH_OUT" | tail -n 2)"
reasons_of() { rowcol "$REAL_H" "$W/$1" reasons; }
[ "$(reasons_of rn_absent)" = remote-not-proven ] && ok "[§5 integrator] a clean pushed row absent from remote-held.tsv enters real.tsv with remote-not-proven" \
  || bad "[§5 integrator] rn_absent reasons: '$(reasons_of rn_absent)'"
has_row "$REAL_H" "$W/rn_proven" && bad "[§5 integrator] a PROVEN-ALL row with empty gaps was listed" || ok "[§5 integrator] a PROVEN-ALL row with empty gaps is not listed"
[ "$(reasons_of rn_gap)" = remote-not-proven ] && ok "[§5 integrator] PROVEN-ALL with a gap enters real.tsv with remote-not-proven" || bad "[§5 integrator] rn_gap reasons: '$(reasons_of rn_gap)'"
[ "$(reasons_of rn_unproven)" = remote-not-proven ] && ok "[§5 integrator] a row whose verdict is UNPROVEN enters real.tsv" || bad "[§5 integrator] rn_unproven reasons: '$(reasons_of rn_unproven)'"
[ "$(reasons_of rn_filter)" = filtered-content ] && ok "[§7 integrator] a PROVEN-ALL row whose filter attribute drops bytes enters real.tsv with filtered-content (only)" \
  || bad "[§7 integrator] rn_filter reasons: '$(reasons_of rn_filter)'"
has_row "$REAL_H" "$W/rn_same" && bad "[§7 integrator] a filter attribute whose output equals the working-tree bytes was listed" \
  || ok "[§7 integrator] a filter attribute whose bytes equal the stored blob is not a difference"
for n in absent proven gap unproven filter same; do
  has_row "$REAL" "$W/rn_$n" && bad "[integrator] without --remote-held rn_$n was listed: classify no longer behaves as today"
done
has_row "$REAL" "$W/rn_filter" || ok "[integrator] without --remote-held none of the clean pushed rows is listed: classify behaves as today"
for mode in noend wrongcount dupend endnotlast nogaps shortend nonl; do
  mkheld "$base/work/held-$mode.tsv" "$mode" "$W/rn_proven|PROVEN-ALL|" "$W/rn_gap|PROVEN-ALL|"
  rm -f "$base/work/out-$mode.tsv"
  python3 -I "$CLASSIFY" "$TSV" --out "$base/work/out-$mode.tsv" --remote-held "$base/work/held-$mode.tsv" > /dev/null 2>&1
  rc=$?
  [ "$rc" = 65 ] && [ ! -e "$base/work/out-$mode.tsv" ] && ok "[integrator negative control] remote-held.tsv ($mode): refused with exit 65, nothing written" \
    || bad "[integrator negative control] remote-held.tsv ($mode): exit $rc, output $([ -e "$base/work/out-$mode.tsv" ] && echo written || echo absent)"
done
# the rows classify added reach the producer and the verifier: the filtered row gets its filtered-tar
awk -F'\t' 'NR == 1 || $1 ~ /\/rn_/' "$REAL_H" > "$base/real-rn.tsv"
DEST2="$base/dest2"
bash "$PRESERVE" "$base/real-rn.tsv" "$DEST2" apply > "$base/work/apply2.out" 2>&1
RUN2=$(find "$DEST2" -maxdepth 1 -type d -name 'run-*' 2> /dev/null | sort | tail -n 1)
if [ -d "$RUN2" ]; then
  T=$(mfield "$RUN2" filtered-tar "$(slug_of "$W/rn_filter")" file)
  [ "$(mfield "$RUN2" filtered-tar "$(slug_of "$W/rn_filter")" status)" = ok ] && [ "$(tar -xOf "$RUN2/$T" nb.txt 2> /dev/null)" = secret ] \
    && ok "[§7 integrator] preserve-git writes the filtered-tar of the row classify listed for filtered-content, with the working-tree bytes" \
    || bad "[§7 integrator] no ok filtered-tar holding the working-tree bytes for rn_filter"
  [ "$(mcount "$RUN2" filtered-tar)" = 1 ] && ok "[§7 integrator] ...and only for that row" || bad "[§7 integrator] filtered-tar items: $(mcount "$RUN2" filtered-tar)"
  verify "$RUN2" "$base/real-rn.tsv"
  [ "$V_RC" = 0 ] && ok "[integrator] verify-preserve.sh says PASS on the run made from the classify --remote-held rows" || bad "[integrator] verify on the held rows: rc $V_RC: $(printf '%s' "$V_RESULT" | sed -n '/FAILURES/,$p' | head -n 4)"
else
  bad "[integrator] preserve-git.sh made no run from the classify --remote-held rows"
fi

# ---------------------------------------------------------------------------------------------------------- finish
if [ "$fail" = 0 ]; then
  rm -rf "$base"
  [ "$skips" = 0 ] || echo "($skips check(s) skipped on this host)"
  echo "RESULT: PASS ($passes checks)"
  exit 0
fi
echo "RESULT: FAIL ($passes checks passed; fixture kept for inspection: $base)"
exit 1
