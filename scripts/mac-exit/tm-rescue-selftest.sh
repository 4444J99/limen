#!/bin/bash
# End-to-end self-test of the tm-*.sh rescue tools on a throwaway fixture. Touches nothing outside its own temp directory.
#
# WHY: these tools copy the only surviving evidence of unpushed work and then certify the copy. A verifier that cannot fail,
# or a rescue that passes vacuously, is worse than none, so every expectation here has a counter-case: deliberately
# corrupted copies must make the verifier FAIL (for the stated reason, not because of an unrelated refusal), a doctored
# receipt must be refused, and each guard (existing destination, internal disk, free space, bad plan) must fire.
#
# The fixture is a fake Mac home plus two fake Time Machine backups built through the backup-relative-root parameter, a
# fake external volume, real git repositories (unpushed commits, a stash, a detached-HEAD worktree whose parent also
# vanishes, a husk left by a half-finished deletion) and a sweep produced by the real git-sweep.sh. HOME is pointed at the
# fake home for this whole process, the fake backups are made read-only, and the tools run under /bin/bash (3.2 on macOS).
# The mount script is covered against stub diskutil/mount_apfs/mount/umount/id on a PATH that excludes the real ones; it is
# never run against a real volume. Independent oracles (cmp, readlink, git plumbing, shasum -c) check the tools' claims.
#
# usage: scripts/mac-exit/tm-rescue-selftest.sh      # exits 0 only if every expectation held
# shellcheck disable=SC2016,SC2329  # single-quoted `bash -c` bodies expand in the child; helpers are invoked through check()
set -u
here="$(cd "$(dirname "$0")" && pwd)"
BASH_BIN=/bin/bash
[ -x "$BASH_BIN" ] || { echo "FAIL: $BASH_BIN not found" >&2; exit 2; }
base="$(mktemp -d "${TMPDIR:-/tmp}/tm-rescue-selftest.XXXXXX")" || exit 2
base="$(cd -P "$base" && pwd -P)"   # macOS $TMPDIR is under /var, a symlink to /private/var; git and cd -P write the resolved path
export HOME="$base/home"
mkdir -p "$base/tmp"; export TMPDIR="$base/tmp"   # tools that keep evidence on FAIL (verify) keep it inside the fixture
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
export GIT_AUTHOR_NAME=fx GIT_AUTHOR_EMAIL=fx@example.invalid GIT_COMMITTER_NAME=fx GIT_COMMITTER_EMAIL=fx@example.invalid
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
tm="$base/tm"; ext="$base/ext"; stubs="$base/stubs"; W="$HOME/Workspace"
mkdir -p "$W" "$tm" "$ext" "$stubs"

S1=2026-03-01-120000      # older backup
S2=2026-03-01-150000      # newer backup
REL=Data/fx-home          # backup-relative root of the fake home
H1="$tm/$S1.backup/$S1.backup/$REL"
H2="$tm/$S2.backup/$S2.backup/$REL"

pass=0; fail=0; RC=0
ok()  { printf 'ok    %s\n' "$*"; pass=$((pass + 1)); }
bad() { printf 'FAIL  %s\n' "$*"; fail=$((fail + 1)); }
tailout() { tail -n 6 "$base/last.out" 2>/dev/null | tr '\n' '|'; }
rc_is()     { if [ "$RC" = "$2" ]; then ok "$1"; else bad "$1 (exit $RC, wanted $2; output: $(tailout))"; fi; }
out_has()   { if grep -qE -- "$2" "$base/last.out"; then ok "$1"; else bad "$1 (no match for '$2'; output: $(tailout))"; fi; }
check()     { local d="$1"; shift; if "$@"; then ok "$d"; else bad "$d"; fi; }
check_not() { local d="$1"; shift; if "$@"; then bad "$d"; else ok "$d"; fi; }

# ---------------------------------------------------------------- oracles (independent of the tools under test)
EXCL_FIND=( \( -name node_modules -o -name .venv -o -name venv -o -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache -o -name .next \) -prune -o -print )
same_tree() { # SRC DST -> 0 when identical apart from the default excluded names: same listing, cmp on files, readlink on links
  local a="$1" b="$2" la lb p
  la="$(cd "$a" && LC_ALL=C find . "${EXCL_FIND[@]}" | LC_ALL=C sort)" || return 1
  lb="$(cd "$b" && LC_ALL=C find . "${EXCL_FIND[@]}" | LC_ALL=C sort)" || return 1
  [ "$la" = "$lb" ] || return 1
  while IFS= read -r p; do
    if [ -L "$a/$p" ]; then
      [ -L "$b/$p" ] && [ "$(readlink "$a/$p")" = "$(readlink "$b/$p")" ] || return 1
    elif [ -d "$a/$p" ]; then
      [ -d "$b/$p" ] && [ ! -L "$b/$p" ] || return 1
    else
      [ -f "$b/$p" ] && [ ! -L "$b/$p" ] && cmp -s "$a/$p" "$b/$p" || return 1
    fi
  done <<< "$la"
}
fingerprint() { # DIR -> one hash over paths, types, link targets and file contents
  ( cd "$1" && export LC_ALL=C && find . -print | sort | while IFS= read -r p; do
      if [ -L "$p" ]; then printf 'L %s -> %s\n' "$p" "$(readlink "$p")"
      elif [ -d "$p" ]; then printf 'D %s\n' "$p"
      else printf 'F %s %s\n' "$p" "$(shasum -a 256 < "$p" | cut -d' ' -f1)"; fi
    done | shasum -a 256 | cut -d' ' -f1 )
}
res_field() { awk -F'\t' -v r="$2" -v c="$3" 'FNR>1 && $1==r {print $c}' "$1/RESCUE-RESULTS.tsv"; }   # DEST REL COLUMN
rep_field() { awk -F'\t' -v p="$2" -v c="$3" 'FNR>1 && $1==p {print $c}' "$1"; }                       # REPORT PATH COLUMN

# ---------------------------------------------------------------- tool runner
XENV=(); NO_INTERNAL_OVERRIDE=0
run() { # TOOL ARGS... -> output in $base/last.out, exit status in $RC
  local tool="$1"; shift
  local e=( TM_ROOT="$tm" TM_REL_ROOT="$REL" TM_DEST_ROOT="$ext" )
  [ "$NO_INTERNAL_OVERRIDE" = 1 ] || e+=( TM_ALLOW_INTERNAL_DEST=1 )
  env ${e[@]+"${e[@]}"} ${XENV[@]+"${XENV[@]}"} "$BASH_BIN" "$here/$tool" "$@" > "$base/last.out" 2>&1
  RC=$?
}

# ================================================================ fixture
mkrepo() { mkdir -p "$1"; git init -q "$1" 2>/dev/null; git -C "$1" symbolic-ref HEAD refs/heads/main; }
commit_file() { printf '%s\n' "$3" > "$1/$2"; git -C "$1" add -- "$2"; git -C "$1" commit -q -m "$4"; }
set_remote() { git -C "$1" remote add origin https://example.invalid/fx.git; git -C "$1" update-ref refs/remotes/origin/main HEAD; }

mkrepo "$W/alpha";  commit_file "$W/alpha" a.txt one c1;  set_remote "$W/alpha"             # stays on the Mac
mkrepo "$W/zeta";   commit_file "$W/zeta" a.txt one c1;   set_remote "$W/zeta"              # vanishes, nothing exposed
mkrepo "$W/eta";    commit_file "$W/eta" a.txt one c1                                       # vanishes, exposed, rescued up front
mkrepo "$W/gamma";  commit_file "$W/gamma" a.txt one c1;  echo wip > "$W/gamma/wip.txt"     # only in the older backup
mkrepo "$W/delta";  commit_file "$W/delta" a.txt one c1                                     # a husk in the newer backup
mkrepo "$W/lambda"; commit_file "$W/lambda" a.txt one c1; set_remote "$W/lambda"            # swept with an unknown unpushed count
mkrepo "$W/iota";   commit_file "$W/iota" a.txt one c1;   set_remote "$W/iota"              # parent of the detached worktree
git -C "$W/iota" worktree add -q --detach "$W/theta" HEAD
commit_file "$W/theta" t.txt detached-only "a commit on no branch"
THETA_C="$(git -C "$W/theta" rev-parse HEAD)"
mkrepo "$W/kappa";  commit_file "$W/kappa" a.txt one c1;  set_remote "$W/kappa"             # a plain repo left on a detached HEAD
git -C "$W/kappa" checkout -q --detach
commit_file "$W/kappa" k.txt detached-only "a commit on no branch"
KAPPA_C="$(git -C "$W/kappa" rev-parse HEAD)"

B="$W/work area/beta"                                                                       # spaces in the path; unpushed + stash
mkrepo "$B"; commit_file "$B" a.txt alpha-text c1; commit_file "$B" "file with spaces.txt" spaced c2
set_remote "$B"
git -C "$B" checkout -q -b feature; commit_file "$B" f1.txt one f1; commit_file "$B" f2.txt two f2; git -C "$B" checkout -q main
echo wip >> "$B/a.txt"; git -C "$B" stash -q
printf 'dash\n' > "$B/-dash.txt"; printf 'v\n' > "$B/venv.txt"
dd if=/dev/urandom of="$B/blob.bin" bs=1024 count=16 2>/dev/null
mkdir -p "$B/emptydir" "$B/sub/node_modules/x" "$B/.venv/bin" "$B/__pycache__" "$B/.next/cache" "$B/deep/er/venv"
echo js > "$B/sub/node_modules/x/y.js"; echo py > "$B/.venv/bin/py"; echo pyc > "$B/__pycache__/m.pyc"; echo c > "$B/.next/cache/c"
dd if=/dev/zero of="$B/sub/node_modules/x/big.bin" bs=1024 count=512 2>/dev/null   # excluded payload: the free-space estimate must not count it
echo keep > "$B/deep/er/keep.txt"; echo hidden > "$B/deep/er/venv/hidden.txt"
ln -s a.txt "$B/link"; ln -s nowhere-at-all "$B/dangling"

# backups: the older holds the first state; the newer holds the state after one more commit on each of beta's branches
mkdir -p "$H1" "$H2"
cp -a "$HOME/." "$H1/"
commit_file "$B" later.txt later "after the older backup"
git -C "$B" checkout -q feature; commit_file "$B" f3.txt three f3; git -C "$B" checkout -q main
BETA_TIP="$(git -C "$B" rev-parse refs/heads/feature)"
BETA_UNPUSHED="$(git -C "$B" rev-list --count --branches --not --remotes)"
cp -a "$HOME/." "$H2/"
rm -rf "${H2:?}/Workspace/gamma"                    # gone before the newer backup
rm -rf "${H2:?}/Workspace/delta/.git"               # the newer backup caught delta mid-deletion: files, no .git
mkrepo "$W/epsilon"; commit_file "$W/epsilon" a.txt one c1                                  # never backed up at all
git -C "$W/epsilon" checkout -q -b x; commit_file "$W/epsilon" b.txt two c2

# sweep the pre-vanish Mac with the real sweep script, then add the rows a real sweep may also hold
mkdir -p "$base/sweep"
if ! bash "$here/git-sweep.sh" "$base/sweep" > "$base/sweep.log" 2>&1; then echo "FAIL: git-sweep.sh failed in the fixture"; cat "$base/sweep.log"; exit 2; fi
awk -F'\t' -v OFS='\t' -v p="$W/lambda" '$1 == p { $6 = "?" } { print }' "$base/sweep/git.tsv" > "$base/sweep/git.new" && mv "$base/sweep/git.new" "$base/sweep/git.tsv"
printf '%s\trepo\tmain\tNONE\t0\t0\t0\t0\n' "$base/outside/proj" >> "$base/sweep/git.tsv"

# the Mac loses everything except alpha
vanish() { case "$1" in "$HOME"/Workspace/*) rm -rf "$1" ;; *) echo "FAIL: refusing to remove outside the fixture: $1"; exit 2 ;; esac; }
for d in zeta eta gamma delta epsilon lambda theta iota kappa "work area"; do vanish "$W/$d"; done
check "fixture: only alpha is left on the fake Mac" test "$(find "$W" -mindepth 1 -maxdepth 1 -print)" = "$W/alpha"

# the fake backups are read-only: any write by a tool fails loudly
chmod -R a-w "$tm"
sleep 1; touch "$base/marker"
FP_TM="$(fingerprint "$tm")"; FP_HOME="$(fingerprint "$HOME")"
printf 'info  tools run under: %s\n' "$("$BASH_BIN" --version | head -n 1)"

# ================================================================ A. tm-mount-snapshot.sh against stubs only
mkdir -p "$base/mnt"
cat > "$stubs/diskutil" <<'EOF'
#!/bin/bash
case "$1 ${2:-}" in
  "info FXVOL"|"info /dev/disk99s1") echo "   Device Node:               /dev/disk99s1"; echo "   Volume Name:               FXVOL"; exit 0 ;;
  "apfs listSnapshots") if [ "${3:-}" = FXVOL ]; then cat "$FX_SNAPLIST"; exit 0; fi ;;
esac
exit 1
EOF
cat > "$stubs/mount_apfs" <<'EOF'
#!/bin/bash
echo "mount_apfs $*" >> "$FX_LOG"
for last; do :; done
echo "/dev/disk99s1 on $last (apfs, local, read-only, nobrowse)" >> "$FX_MOUNTS"
exit 0
EOF
cat > "$stubs/mount" <<'EOF'
#!/bin/bash
cat "$FX_MOUNTS"
EOF
cat > "$stubs/umount" <<'EOF'
#!/bin/bash
echo "umount $*" >> "$FX_LOG"
grep -vF " on $1 (" "$FX_MOUNTS" > "$FX_MOUNTS.new"; mv "$FX_MOUNTS.new" "$FX_MOUNTS"
exit 0
EOF
cat > "$stubs/id" <<'EOF'
#!/bin/bash
if [ "${1:-}" = "-u" ]; then echo "${FX_UID:-0}"; exit 0; fi
exit 1
EOF
chmod +x "$stubs/diskutil" "$stubs/mount_apfs" "$stubs/mount" "$stubs/umount" "$stubs/id"
cat > "$stubs/snaps" <<'EOF'
Snapshots for disk99s1 (2 found)
|
+-- 11111111-2222-3333-4444-555555555555
|   Name:        com.apple.TimeMachine.2026-03-01-120000.backup
|   XID:         100
|
+-- 66666666-7777-8888-9999-000000000000
    Name:        com.apple.TimeMachine.2026-03-01-150000.backup
    XID:         200
EOF
: > "$stubs/mounts"; : > "$stubs/log"
mnt() { # ARGS... -> PATH is confined to the stubs plus /usr/bin:/bin, so no real diskutil/mount_apfs/mount/umount can run
  env PATH="$stubs:/usr/bin:/bin" FX_MOUNTS="$stubs/mounts" FX_LOG="$stubs/log" FX_SNAPLIST="$stubs/snaps" FX_UID="${FX_UID:-0}" \
    "$BASH_BIN" "$here/tm-mount-snapshot.sh" "$@" > "$base/last.out" 2>&1
  RC=$?
}
check "mount stubs shadow the real tools and the real ones are off PATH" bash -c 'PATH="$1:/usr/bin:/bin"; [ "$(command -v diskutil)" = "$1/diskutil" ] && [ "$(command -v mount_apfs)" = "$1/mount_apfs" ]' _ "$stubs"
MP="$base/mnt/m1"
mnt dry FXVOL "$S1" "$MP"; rc_is "mount dry exits 0" 0
out_has "mount dry names the device" '/dev/disk99s1'
out_has "mount dry names the exact snapshot" "com\.apple\.TimeMachine\.$S1\.backup"
out_has "mount dry shows the read-only flags" 'rdonly,nobrowse'
check "mount dry mounted nothing and created nothing" test ! -e "$MP" -a ! -s "$stubs/log"
mnt dry NOSUCHVOL "$S1" "$MP"; rc_is "mount refuses an unknown volume" 2; out_has "  ...with a clear message" 'not found'
mnt dry FXVOL com.apple.TimeMachine.2026-03-01-15000 "$MP"; rc_is "mount matches the snapshot name exactly (a substring is refused)" 2
out_has "  ...naming the snapshot" 'is not on FXVOL'
mnt dry FXVOL 2026-03-01-999999 "$MP"; rc_is "mount refuses a stamp that is not on the volume" 2
mnt dry FXVOL not-a-stamp "$MP"; rc_is "mount refuses a malformed snapshot argument" 2
mnt dry FXVOL; rc_is "mount refuses a missing SNAPSHOT argument (no default volume or snapshot)" 2
mnt frobnicate; rc_is "mount refuses an unknown mode" 2
FX_UID=501 mnt apply FXVOL "$S1" "$MP"; rc_is "mount apply refuses without root" 2; out_has "  ...saying why" 'needs root'
check "  ...and ran nothing" test ! -s "$stubs/log"
mnt apply FXVOL "$S1" "$MP"; rc_is "mount apply (simulated root) exits 0" 0
check "mount ran mount_apfs read-only on the exact snapshot and device" grep -qx "mount_apfs -o rdonly,nobrowse -s com.apple.TimeMachine.$S1.backup /dev/disk99s1 $MP" "$stubs/log"
check "mount created the mount point private (700)" test "$(stat -f %Lp "$MP")" = 700
mnt apply FXVOL "$S1" "$MP"; rc_is "mount apply again reports already mounted" 0; out_has "  ...as such" 'already mounted'
check "  ...without a second mount_apfs call" test "$(grep -c '^mount_apfs' "$stubs/log")" = 1
mkdir -p "$base/mnt/full"; echo x > "$base/mnt/full/f"
mnt apply FXVOL "$S2" "$base/mnt/full"; rc_is "mount refuses to mount over a non-empty directory" 2; out_has "  ...saying so" 'not empty'
ln -s "$base/mnt/full" "$base/mnt/link"
mnt apply FXVOL "$S2" "$base/mnt/link"; rc_is "mount refuses a symlink as mount point" 2
FX_UID=501 mnt unmount "$MP"; rc_is "mount unmount refuses without root" 2
mnt unmount "$MP"; rc_is "mount unmount (simulated root) exits 0" 0
check "  ...and removed the empty mount point" test ! -e "$MP" -a ! -s "$stubs/mounts"

# ================================================================ B. tm-lib defaults and tm-rescue.sh
r="$(env -u TM_REL_ROOT HOME=/fx/h TM_ROOT="$tm" "$BASH_BIN" -c '. "$1/tm-lib.sh"; tm_init; printf %s "$TM_REL_ROOT"' _ "$here")"
check "TM_REL_ROOT defaults to Data + \$HOME" test "$r" = "Data/fx/h"

planA="$base/plan-a.tsv"
printf 'rel\tsnapshot\n%s\t%s\n%s\t%s\n%s\t%s\n' "Workspace/work area/beta" "$S2" Workspace/gamma "$S1" Workspace/delta "$S1" > "$planA"
DESTA="$ext/recovered-from-tm-$S2-and-earlier"

run tm-rescue.sh dry "$planA"; rc_is "rescue dry exits 0" 0
out_has "rescue dry lists size and git kind per directory" "KiB +repo +$S2 +Workspace/work area/beta"
check "rescue dry created no destination" test ! -e "$DESTA"
printf 'rel\tsnapshot\nWorkspace/not-there\t%s\n' "$S2" > "$base/plan-missing.tsv"
run tm-rescue.sh dry "$base/plan-missing.tsv"; rc_is "rescue dry exits 1 when a directory is missing in its backup" 1; out_has "  ...saying MISSING" 'MISSING'

run tm-rescue.sh apply "$planA"; rc_is "rescue apply (3 dirs from 2 backups) exits 0" 0
out_has "rescue apply reports PASS" 'RESULT: PASS'
check "run directory is named for the newest backup plus 'and-earlier'" test -d "$DESTA"
check "results has exactly 3 green rows" test "$(awk -F'\t' 'FNR>1 && $3=="copied"' "$DESTA/RESCUE-RESULTS.tsv" | wc -l | tr -d ' ')" = 3
check "beta copy equals its backup (independent cmp/readlink oracle)" same_tree "$H2/Workspace/work area/beta" "$DESTA/$S2/Workspace/work area/beta"
check "gamma copy equals the OLDER backup (the only one that has it)" same_tree "$H1/Workspace/gamma" "$DESTA/$S1/Workspace/gamma"
check "delta copy came from the older backup, not the husk" test -f "$DESTA/$S1/Workspace/delta/.git/HEAD"
BC="$DESTA/$S2/Workspace/work area/beta"
check "beta copy has the newer backup's file" test -f "$BC/later.txt"
check "excluded dependency dirs are not copied (nested node_modules, .venv, __pycache__, .next)" test ! -e "$BC/sub/node_modules" -a ! -e "$BC/.venv" -a ! -e "$BC/__pycache__" -a ! -e "$BC/.next"
check "a directory named venv is excluded but venv.txt is kept" test ! -e "$BC/deep/er/venv" -a -f "$BC/venv.txt" -a -f "$BC/deep/er/keep.txt"
check "empty dir, dash-named file, symlink and dangling symlink are preserved" test -d "$BC/emptydir" -a -f "$BC/-dash.txt" -a "$(readlink "$BC/link")" = a.txt -a "$(readlink "$BC/dangling")" = nowhere-at-all
check "unpushed branch tip survived (git plumbing oracle)" test "$(git -C "$BC" rev-parse refs/heads/feature)" = "$BETA_TIP"
check "stash survived" bash -c 'git -C "$1" rev-parse -q --verify refs/stash > /dev/null' _ "$BC"
check "git fsck passes on the copy" git -C "$BC" fsck --connectivity-only
check "unpushed count in the copy equals the original's" test "$(git -C "$BC" rev-list --count --branches --not --remotes)" = "$BETA_UNPUSHED"
check "results record git=repo, the original's unpushed count and fsck=ok for beta" test "$(res_field "$DESTA" 'Workspace/work area/beta' 6)/$(res_field "$DESTA" 'Workspace/work area/beta' 7)/$(res_field "$DESTA" 'Workspace/work area/beta' 8)" = "repo/$BETA_UNPUSHED/ok"
check "receipt records the exact exclude list" grep -qx 'excludes: node_modules .venv venv __pycache__ .pytest_cache .ruff_cache .mypy_cache .next' "$DESTA/RESCUE-RECEIPT.txt"
check "  ...and result: PASS" grep -qx 'result: PASS' "$DESTA/RESCUE-RECEIPT.txt"
check "  ...and the default time budget: deadline_sec: 3600, deadline: met" bash -c 'grep -qx "deadline_sec: 3600" "$1" && grep -qx "deadline: met" "$1"' _ "$DESTA/RESCUE-RECEIPT.txt"
check "run directory is private (700)" test "$(stat -f %Lp "$DESTA")" = 700

FPD="$(fingerprint "$DESTA")"
run tm-rescue.sh apply "$planA"; rc_is "second apply refuses to overwrite the existing destination" 2; out_has "  ...saying so" 'already exists; refusing to overwrite'
check "  ...and left the destination untouched" test "$(fingerprint "$DESTA")" = "$FPD"
XENV=(TM_DEST="$DESTA"); run tm-rescue.sh apply "$planA"; XENV=()
rc_is "apply into an explicit existing TM_DEST refuses too" 2; out_has "  ...saying so" 'already exists; refusing to overwrite'
NO_INTERNAL_OVERRIDE=1; XENV=(TM_DEST="$ext/internal-try"); run tm-rescue.sh apply "$planA"; XENV=(); NO_INTERNAL_OVERRIDE=0
rc_is "apply refuses a destination on the same device as \$HOME" 2; out_has "  ...saying so" 'same device as'
check "  ...and created nothing" test ! -e "$ext/internal-try"
XENV=(TM_DEST_ROOT="$base/no-such-volume"); run tm-rescue.sh apply "$planA"; XENV=()
rc_is "apply refuses when the destination volume is not there" 2; out_has "  ...saying so" 'parent does not exist'
check "  ...and created nothing on the internal disk" test ! -e "$base/no-such-volume"
XENV=(TM_DEST_ROOT=); run tm-rescue.sh apply "$planA"; XENV=()
rc_is "apply refuses when no destination is given" 2; out_has "  ...saying so" 'no destination'
mkdir -p "$base/dfstub"
cat > "$base/dfstub/df" <<'EOF'
#!/bin/bash
echo "Filesystem 1024-blocks Used Available Capacity Mounted"
echo "fx 100 90 ${FX_DF_AVAIL:-10} 90% /fx"
EOF
chmod +x "$base/dfstub/df"
XENV=(PATH="$base/dfstub:$PATH" TM_DEST="$ext/space-try"); run tm-rescue.sh apply "$planA"; XENV=()
rc_is "apply refuses when the destination lacks free space" 2; out_has "  ...saying so" 'not enough free space'
check "  ...and created nothing" test ! -e "$ext/space-try"
XENV=(PATH="$base/dfstub:$PATH" TM_DEST="$ext/space-try"); run tm-rescue.sh dry "$planA"; XENV=()
rc_is "dry on a tight disk still lists every directory, then reports the refusal (exit 2)" 2
out_has "  ...the listing is there" "KiB +repo +$S2 +Workspace/work area/beta"
out_has "  ...and so is the predicted refusal" 'WOULD REFUSE: not enough free space'
# the estimate must count what will really be copied: excluded dependency directories are usually the biggest part of a tree
raw_kb=0
for p in "$H2/Workspace/work area/beta" "$H1/Workspace/gamma" "$H1/Workspace/delta"; do raw_kb=$((raw_kb + $(du -sk "$p" | awk '{print $1}'))); done
copy_kb="$(du -sk "$DESTA" | awk '{print $1}')"
mid_kb=$(( (raw_kb + copy_kb) / 2 ))
check "fixture: the excluded payload makes the raw size clearly larger than what is copied" test "$raw_kb" -gt $((copy_kb + 300))
XENV=(PATH="$base/dfstub:$PATH" FX_DF_AVAIL="$mid_kb" TM_DEST="$ext/space-ok"); run tm-rescue.sh apply "$planA"; XENV=()
rc_is "apply proceeds when free space covers the copied size although it is below the raw size" 0
check "  ...and made the destination" test -d "$ext/space-ok"
printf 'rel\tsnapshot\n../escape\t%s\n' "$S2" > "$base/plan-bad1.tsv"
run tm-rescue.sh apply "$base/plan-bad1.tsv"; rc_is "plan with a .. path is refused" 2; out_has "  ...as unsafe" 'unsafe or empty path'
printf 'rel\tsnapshot\n/etc/hosts\t%s\n' "$S2" > "$base/plan-bad2.tsv"
run tm-rescue.sh apply "$base/plan-bad2.tsv"; rc_is "plan with an absolute path outside \$HOME is refused" 2; out_has "  ...as outside HOME" 'outside \$HOME'
printf 'rel\tsnapshot\nWorkspace/gamma\tyesterday\n' > "$base/plan-bad3.tsv"
run tm-rescue.sh apply "$base/plan-bad3.tsv"; rc_is "plan with a malformed snapshot is refused" 2
printf 'rel\tsnapshot\nWorkspace/gamma\t2030-01-01-000000\n' > "$base/plan-bad4.tsv"
run tm-rescue.sh apply "$base/plan-bad4.tsv"; rc_is "plan naming an unreadable backup is refused before anything is created" 2; out_has "  ...saying so" 'not readable'
printf 'rel\tsnapshot\n' > "$base/plan-empty.tsv"
run tm-rescue.sh apply "$base/plan-empty.tsv"; rc_is "empty plan is refused (a vacuous run is not a pass)" 2; out_has "  ...saying so" 'vacuous'
run tm-rescue.sh apply "$base/no-such-plan.tsv"; rc_is "missing plan file is refused" 2
printf 'Workspace/gamma\n' > "$base/plan-bare.tsv"
XENV=(TM_STAMP="$S1" TM_DEST="$ext/bare"); run tm-rescue.sh apply "$base/plan-bare.tsv"; XENV=()
rc_is "a bare plan line uses TM_STAMP" 0
XENV=(TM_DEST="$ext/bare2"); run tm-rescue.sh apply "$base/plan-bare.tsv"; XENV=()
rc_is "a bare plan line without TM_STAMP is refused" 2
check "  ...and created nothing" test ! -e "$ext/bare2"

# a linked worktree is only rescued when its parent repository comes along
printf 'rel\tsnapshot\nWorkspace/theta\t%s\n' "$S2" > "$base/plan-wt-only.tsv"
XENV=(TM_DEST="$ext/wt-only"); run tm-rescue.sh apply "$base/plan-wt-only.tsv"; XENV=()
rc_is "worktree without its parent in the run exits 1" 1
check "  ...row status is copied-worktree-parent-missing" test "$(res_field "$ext/wt-only" Workspace/theta 3)" = copied-worktree-parent-missing
check "  ...naming the parent it needs" test "$(res_field "$ext/wt-only" Workspace/theta 9)" = Workspace/iota
check "  ...and the destination is kept for inspection" test -d "$ext/wt-only/$S2/Workspace/theta"
printf 'rel\tsnapshot\nWorkspace/theta\t%s\nWorkspace/iota\t%s\n' "$S2" "$S2" > "$base/plan-wt-both.tsv"
XENV=(TM_DEST="$ext/wt-both"); run tm-rescue.sh apply "$base/plan-wt-both.tsv"; XENV=()
rc_is "worktree plus its parent exits 0" 0
check "  ...the detached commit is in the rescued parent's object store (git oracle)" git -C "$ext/wt-both/$S2/Workspace/iota" cat-file -e "$THETA_C^{commit}"
# the parent must come from the SAME snapshot: a copy of iota from the older backup does not hold the newer worktree's commits
printf 'rel\tsnapshot\nWorkspace/theta\t%s\nWorkspace/iota\t%s\n' "$S2" "$S1" > "$base/plan-wt-cross.tsv"
XENV=(TM_DEST="$ext/wt-cross"); run tm-rescue.sh apply "$base/plan-wt-cross.tsv"; XENV=()
rc_is "a worktree whose parent was copied from a DIFFERENT backup exits 1" 1
check "  ...theta is copied-worktree-parent-missing while iota itself is copied" test "$(res_field "$ext/wt-cross" Workspace/theta 3)/$(res_field "$ext/wt-cross" Workspace/iota 3)" = copied-worktree-parent-missing/copied

# a snapshot mounted by hand uses the second layout (<stamp>.backup/<rel root>)
mkdir -p "$base/tm-mounted/$S2.backup/Data"; ln -s "$H2" "$base/tm-mounted/$S2.backup/$REL"
XENV=(TM_ROOT="$base/tm-mounted"); run tm-rescue.sh dry "$base/plan-wt-only.tsv"; XENV=()
rc_is "a hand-mounted snapshot layout is read too" 0

# what counts as a complete checkout inside a backup (the husk rule), as a unit test of the library function
hk="$base/hk"; mkdir -p "$hk/husk" "$hk/okwt" "$hk/okrepo/.git" "$hk/badrepo/.git"
echo x > "$hk/husk/file"; echo "gitdir: x" > "$hk/okwt/.git"; echo ref > "$hk/okrepo/.git/HEAD"
tbh() { "$BASH_BIN" -c '. "$1/tm-lib.sh"; tm_backup_has "$2" "$3"' _ "$here" "$1" "$2"; }   # DIR KIND
check_not "a worktree husk (files, no .git) is not a complete copy" tbh "$hk/husk" worktree
check "a worktree with its .git file is complete" tbh "$hk/okwt" worktree
check "a repo with .git/HEAD is complete" tbh "$hk/okrepo" repo
check_not "a repo whose .git has no HEAD is a husk" tbh "$hk/badrepo" repo

# TM_DEADLINE_SEC: a bad value is a usage error (64) that creates nothing; an overrun is a FAIL that keeps its destination
for v in 0 -5 abc 1.5 1234567890 ''; do
  XENV=(TM_DEADLINE_SEC="$v" TM_DEST="$ext/dl-bad"); run tm-rescue.sh apply "$planA"; XENV=()
  rc_is "TM_DEADLINE_SEC='$v' is a usage error" 64
  out_has "  ...naming the variable" 'TM_DEADLINE_SEC must be a positive integer'
done
check "  ...and no bad value created a destination" test ! -e "$ext/dl-bad"
XENV=(TM_DEADLINE_SEC=abc); run tm-rescue.sh dry "$planA"; XENV=()
rc_is "a bad TM_DEADLINE_SEC is a usage error in dry mode too" 64
# the slow copy: a stub rsync that waits before the real one; FX_REAL_RSYNC is resolved before PATH is overridden. One perl
# process sleeps then execs rsync, so the budget's alarm kills the whole stub and no sleep is left behind.
mkdir -p "$base/slowstub"; real_rsync="$(command -v rsync)"
cat > "$base/slowstub/rsync" <<'EOF'
#!/bin/bash
exec perl -e 'select(undef, undef, undef, shift); exec @ARGV' "${FX_SLOW_SEC:-1}" "$FX_REAL_RSYNC" "$@"
EOF
chmod +x "$base/slowstub/rsync"
slow() { XENV=(PATH="$base/slowstub:$PATH" FX_REAL_RSYNC="$real_rsync" FX_SLOW_SEC="$1" TM_DEADLINE_SEC="$2" TM_DEST="$3"); run tm-rescue.sh apply "$planA"; XENV=(); }   # SLEEP BUDGET DEST
slow 6 2 "$ext/dl-over"
rc_is "a copy that outlives TM_DEADLINE_SEC exits 1" 1
check_not "  ...and is never reported as PASS" grep -q 'RESULT: PASS' "$base/last.out"
out_has "  ...saying deadline: exceeded" 'deadline: exceeded'
check "  ...the copy in flight was killed: rsync-timeout" test "$(res_field "$ext/dl-over" 'Workspace/work area/beta' 3)" = rsync-timeout
check "  ...the rows behind it were never started: deadline-not-started" test "$(res_field "$ext/dl-over" Workspace/gamma 3)/$(res_field "$ext/dl-over" Workspace/delta 3)" = deadline-not-started/deadline-not-started
check "  ...and copied nothing" test ! -e "$ext/dl-over/$S1"
check "  ...the receipt records result: FAIL, deadline: exceeded and the budget" bash -c 'grep -qx "result: FAIL" "$1" && grep -qx "deadline: exceeded" "$1" && grep -qx "deadline_sec: 2" "$1"' _ "$ext/dl-over/RESCUE-RECEIPT.txt"
check "  ...and the destination is kept for inspection" test -f "$ext/dl-over/RESCUE-RESULTS.tsv" -a -d "$ext/dl-over/$S2/Workspace/work area/beta"
slow 1 0120 "$ext/dl-ok"
rc_is "the same slow copy inside a generous budget (0120 is decimal 120) exits 0" 0
out_has "  ...PASS" 'RESULT: PASS'
check "  ...with three green rows" test "$(awk -F'\t' 'FNR>1 && $3=="copied"' "$ext/dl-ok/RESCUE-RESULTS.tsv" | wc -l | tr -d ' ')" = 3
check "  ...and the receipt says deadline_sec: 120, deadline: met" bash -c 'grep -qx "deadline_sec: 120" "$1" && grep -qx "deadline: met" "$1"' _ "$ext/dl-ok/RESCUE-RECEIPT.txt"

# ================================================================ C. tm-rescue-verify.sh
run tm-rescue-verify.sh dry "$DESTA"; rc_is "verify dry on a good rescue exits 0" 0
out_has "  ...PASS" 'RESULT: PASS'
check "  ...and wrote nothing in the destination" test ! -e "$DESTA/RESCUE-MANIFEST.sha256" -a ! -e "$DESTA/RESCUE-VERIFY.txt"
run tm-rescue-verify.sh apply "$DESTA"; rc_is "verify apply exits 0" 0
check "verify apply wrote the manifest and the verification receipt" test -s "$DESTA/RESCUE-MANIFEST.sha256" -a -s "$DESTA/RESCUE-VERIFY.txt"
check "manifest is checkable with plain shasum -c" bash -c 'cd "$1" && shasum -a 256 -c RESCUE-MANIFEST.sha256 > /dev/null' _ "$DESTA"
check "manifest covers a file with spaces and a dash-named file" bash -c 'grep -q "work area/beta/file with spaces.txt$" "$1" && grep -q "work area/beta/-dash.txt$" "$1"' _ "$DESTA/RESCUE-MANIFEST.sha256"
run tm-rescue-verify.sh apply "$DESTA"; rc_is "second verify apply refuses to overwrite its proof files" 2; out_has "  ...saying so" 'already exists; refusing to overwrite'

# deliberately damaged copies: each must FAIL for the stated reason, and must not get a manifest
FRESH="$ext/fresh"
XENV=(TM_DEST="$FRESH"); run tm-rescue.sh apply "$planA"; XENV=(); rc_is "second, unverified rescue for the damage tests" 0
variant() { rsync -a "$FRESH/" "$base/var-$1/" && chmod -R u+w "$base/var-$1"; }   # NAME -> writable copy of the unverified rescue
vb() { printf '%s' "$base/var-$1/$S2/Workspace/work area/beta"; }
verify_fails() { # NAME DESC EVIDENCE-PATTERN [mode]
  run tm-rescue-verify.sh "${4:-apply}" "$base/var-$1"
  rc_is "$2: verify exits 1" 1
  out_has "$2: MISMATCH is reported for the damaged row" "MISMATCH +$S2/Workspace/work area/beta"
  out_has "$2: ...with the evidence" "$3"
  out_has "$2: ...and RESULT: FAIL" 'RESULT: FAIL'
}
variant content;  printf 'Z' | dd of="$(vb content)/a.txt" bs=1 seek=0 conv=notrunc 2>/dev/null
check "content damage keeps the same size" test "$(wc -c < "$(vb content)/a.txt")" = "$(wc -c < "$H2/Workspace/work area/beta/a.txt")"
verify_fails content "one changed byte" 'a\.txt'
check "  no manifest was written for a failed verify" test ! -e "$base/var-content/RESCUE-MANIFEST.sha256" -a ! -e "$base/var-content/RESCUE-VERIFY.txt"
variant deleted;  rm "$(vb deleted)/venv.txt"
verify_fails deleted "a deleted file" 'venv\.txt'
variant extra;    echo stray > "$(vb extra)/stray.txt"
verify_fails extra "an extra file" 'stray\.txt'
variant linkmod;  ln -sfn other-target "$(vb linkmod)/link"
verify_fails linkmod "a retargeted symlink" 'link'
variant dirmod;   rmdir "$(vb dirmod)/emptydir"
verify_fails dirmod "a removed empty directory" 'emptydir'
variant gitobj;   obj="$(find "$(vb gitobj)/.git/objects" -type f -path '*/??/*' | head -n 1)"; : > "$obj"
verify_fails gitobj "a truncated git object" '\.git/objects'
variant forged;   printf 'Z' | dd of="$(vb forged)/a.txt" bs=1 seek=0 conv=notrunc 2>/dev/null
( cd "$base/var-forged" && find . -type f ! -name 'RESCUE-*' -print0 | sort -z | xargs -0 shasum -a 256 | sed 's#  \./#  #' > RESCUE-MANIFEST.sha256 )
check "forged manifest (made from the damaged copy) passes its own shasum -c" bash -c 'cd "$1" && shasum -a 256 -c RESCUE-MANIFEST.sha256 >/dev/null 2>&1' _ "$base/var-forged"
verify_fails forged "a self-consistent forged manifest" 'a\.txt' dry
variant exclhide; printf 'Z' | dd of="$(vb exclhide)/a.txt" bs=1 seek=0 conv=notrunc 2>/dev/null
sed -i.bak 's/^excludes: .*/excludes: node_modules a.txt/' "$base/var-exclhide/RESCUE-RECEIPT.txt" && rm -f "$base/var-exclhide/RESCUE-RECEIPT.txt.bak"
run tm-rescue-verify.sh dry "$base/var-exclhide"; rc_is "a receipt widened to hide the damaged file is refused" 2
out_has "  ...because the name is not in the default exclude list" 'not in the default exclude list'
variant exclgone; sed -i.bak 's/^excludes: .*/excludes: /' "$base/var-exclgone/RESCUE-RECEIPT.txt" && rm -f "$base/var-exclgone/RESCUE-RECEIPT.txt.bak"
run tm-rescue-verify.sh dry "$base/var-exclgone"; rc_is "a receipt that drops the excludes compares more and FAILS (the safe direction)" 1
out_has "  ...with MISMATCH" 'MISMATCH'

# vacuous and structural cases must not read as a pass
variant nocopy;   rm -rf "$base/var-nocopy/$S2/Workspace/work area/beta"
run tm-rescue-verify.sh dry "$base/var-nocopy"; rc_is "a row whose copy is gone is a MISMATCH, not 'identical, 0 files'" 1
out_has "  ...the copy is missing" 'the copy is missing'
variant nobackup; sed -i.bak "s/$S2/2031-01-01-000000/g" "$base/var-nobackup/RESCUE-RESULTS.tsv" && rm -f "$base/var-nobackup/RESCUE-RESULTS.tsv.bak"
run tm-rescue-verify.sh dry "$base/var-nobackup"; rc_is "a row whose backup is unreadable is a MISMATCH" 1
out_has "  ...saying so" 'unreadable'
variant selfref
selfhome="$base/selfroot/$S2.backup/$S2.backup/$REL"; mkdir -p "$(dirname "$selfhome")"; ln -s "$base/var-selfref/$S2" "$selfhome"
XENV=(TM_ROOT="$base/selfroot"); run tm-rescue-verify.sh dry "$base/var-selfref"; XENV=()
rc_is "pointing the 'backup' at the copy itself is refused as a reference" 1
out_has "  ...saying so" 'resolves inside the destination'
# a directory that holds nothing but excluded names has no files: rescuing it is not green, and "identical, 0 files" is no proof
tm3="$base/tm3"; mkdir -p "$tm3/$S2.backup/$S2.backup/$REL/Workspace/onlyexcl/node_modules/x"
printf 'rel\tsnapshot\nWorkspace/onlyexcl\t%s\n' "$S2" > "$base/plan-onlyexcl.tsv"
XENV=(TM_ROOT="$tm3" TM_DEST="$ext/onlyexcl"); run tm-rescue.sh apply "$base/plan-onlyexcl.tsv"; XENV=()
rc_is "rescue of a directory with no files exits 1" 1
check "  ...row status is empty-source" test "$(res_field "$ext/onlyexcl" Workspace/onlyexcl 3)" = empty-source
mkdir -p "$base/var-zero/$S2/Workspace/onlyexcl"; cp "$FRESH/RESCUE-RECEIPT.txt" "$base/var-zero/"
printf 'rel\tsnapshot\tstatus\tfiles_src\tfiles_dst\tgit\tunpushed_dst\tfsck\tparent_rel\nWorkspace/onlyexcl\t%s\tcopied\t0\t0\t-\t-\t-\t-\n' "$S2" > "$base/var-zero/RESCUE-RESULTS.tsv"
XENV=(TM_ROOT="$tm3"); run tm-rescue-verify.sh dry "$base/var-zero"; XENV=()
rc_is "verify refuses to call an empty row identical" 1
out_has "  ...as a MISMATCH with no files to compare" "MISMATCH +$S2/Workspace/onlyexcl.*no files to compare"
# a plan entry that is a symlink in the backup is never followed (it could point anywhere); needs a writable backup root (tm3)
t3h="$tm3/$S2.backup/$S2.backup/$REL"
mkdir -p "$t3h/Workspace/realdir"; echo f > "$t3h/Workspace/realdir/f.txt"; ln -s realdir "$t3h/Workspace/linkdir"
printf 'rel\tsnapshot\nWorkspace/linkdir\t%s\n' "$S2" > "$base/plan-linkdir.tsv"
XENV=(TM_ROOT="$tm3" TM_DEST="$ext/linkdir"); run tm-rescue.sh apply "$base/plan-linkdir.tsv"; XENV=()
rc_is "a plan entry that is a symlink in the backup is refused, exit 1" 1
check "  ...row status is missing-in-backup" test "$(res_field "$ext/linkdir" Workspace/linkdir 3)" = missing-in-backup
check "  ...and nothing was copied through the link" test ! -e "$ext/linkdir/$S2/Workspace/linkdir"
XENV=(TM_DEST="$ext/empty-rescue"); run tm-rescue.sh apply "$base/plan-missing.tsv"; XENV=()
rc_is "a rescue whose only row is missing in its backup exits 1 and keeps its destination" 1
run tm-rescue-verify.sh dry "$ext/empty-rescue"; rc_is "verify of a rescue with no copied rows FAILs (nothing verified)" 1
out_has "  ...saying nothing was verified" 'nothing was verified'
run tm-rescue-verify.sh dry "$base/no-dir"; rc_is "verify of a non-destination is refused" 2
run tm-rescue-verify.sh dry "$ext/bare"; rc_is "verify of a rescue made from a single, older backup passes" 0
variant partial
printf 'Workspace/never\t%s\tmissing-in-backup\t-\t-\t-\t-\t-\t-\n' "$S2" >> "$base/var-partial/RESCUE-RESULTS.tsv"
run tm-rescue-verify.sh apply "$base/var-partial"; rc_is "verify with a never-copied row is PARTIAL and exits 1" 1
out_has "  ...RESULT: PARTIAL" 'RESULT: PARTIAL'
check "  ...but the proof files for the copied rows were written" test -s "$base/var-partial/RESCUE-MANIFEST.sha256" -a -s "$base/var-partial/RESCUE-VERIFY.txt"

# custom excludes: a subset of the defaults is fine; a name outside the defaults must be confirmed in the environment
XENV=(TM_EXCLUDES=node_modules TM_DEST="$ext/custom1"); run tm-rescue.sh apply "$planA"; XENV=()
rc_is "rescue with a narrower exclude list exits 0" 0
check "  ...it copied .venv this time" test -f "$ext/custom1/$S2/Workspace/work area/beta/.venv/bin/py"
run tm-rescue-verify.sh dry "$ext/custom1"; rc_is "verify of a narrower exclude list passes without any environment" 0
XENV=(TM_EXCLUDES="node_modules blob.bin" TM_DEST="$ext/custom2"); run tm-rescue.sh apply "$planA"; XENV=()
rc_is "rescue with a custom exclude name exits 0" 0
run tm-rescue-verify.sh dry "$ext/custom2"; rc_is "verify of a custom exclude name needs confirmation" 2; out_has "  ...saying so" 'not in the default exclude list'
XENV=(TM_EXCLUDES="node_modules blob.bin"); run tm-rescue-verify.sh dry "$ext/custom2"; XENV=()
rc_is "  ...and passes once TM_EXCLUDES matches the receipt" 0
XENV=(TM_EXCLUDES="node_modules"); run tm-rescue-verify.sh dry "$ext/custom2"; XENV=()
rc_is "  ...a different TM_EXCLUDES than the receipt is refused" 2

# the backup itself changing, or becoming unreadable, after the rescue must be noticed (writable copy of the backups)
if [ "$(id -u)" != 0 ]; then
  tm2="$base/tm2"; rsync -a "$tm/" "$tm2/" && chmod -R u+w "$tm2"
  echo tampered >> "$tm2/$S2.backup/$S2.backup/$REL/Workspace/work area/beta/venv.txt"
  XENV=(TM_ROOT="$tm2"); run tm-rescue-verify.sh dry "$DESTA"; XENV=()
  rc_is "verify compares against the backup: a changed backup file FAILs an untouched copy" 1
  out_has "  ...naming the file" 'venv\.txt'
  rsync -a "$tm/" "$tm2/" && chmod -R u+w "$tm2"
  chmod 000 "$tm2/$S2.backup/$S2.backup/$REL/Workspace/work area/beta/blob.bin"
  XENV=(TM_ROOT="$tm2"); run tm-rescue-verify.sh dry "$DESTA"; XENV=()
  rc_is "an unreadable backup file FAILs verify (it can never read as 'absent on both sides')" 1
  out_has "  ...saying a file could not be read" 'could not be read'
  XENV=(TM_ROOT="$tm2" TM_DEST="$ext/unreadable-try"); run tm-rescue.sh apply "$planA"; XENV=()
  rc_is "an unreadable backup file makes the rescue FAIL, not pass" 1
  out_has "  ...with a non-green row" 'NOT GREEN'
  chmod -R u+w "$tm2"
else
  echo "skip  unreadable-file tests (running as root: permission bits do not bind)"
fi

# ================================================================ D. tm-vanished.sh
XENV=(TM_DEST="$ext/eta-dest"); printf 'rel\tsnapshot\nWorkspace/eta\t%s\n' "$S2" > "$base/plan-eta.tsv"; run tm-rescue.sh apply "$base/plan-eta.tsv"; XENV=()
rc_is "earlier rescue of eta (the 'already rescued' input)" 0
VOUT="$base/vout"; REP="$VOUT/vanished.tsv"; PLAN="$VOUT/rescue-plan.tsv"
n_ext="$(find "$ext" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
XENV=(TM_SWEEP_TSV="$base/sweep/git.tsv" TM_OUT="$VOUT" TM_ALREADY="$ext/eta-dest"); run tm-vanished.sh dry; XENV=()
rc_is "vanished dry with exposed repos in no backup exits 1" 1
out_has "  ...as a dry prediction" 'RESULT: DRY'
check "alpha is live, so it is not in the report" test -z "$(rep_field "$REP" "$W/alpha" 1)"
check "beta: exposed, found in the NEWER backup" test "$(rep_field "$REP" "$W/work area/beta" 8)/$(rep_field "$REP" "$W/work area/beta" 11)" = "yes/$S2"
check "beta's reasons name the dirty tree, the unpushed commits and the stash" bash -c 'case "$1" in *dirty*unpushed*stash*) exit 0;; esac; exit 1' _ "$(rep_field "$REP" "$W/work area/beta" 9)"
check "gamma: exposed, found only in the OLDER backup (newest-first fallback)" test "$(rep_field "$REP" "$W/gamma" 8)/$(rep_field "$REP" "$W/gamma" 11)" = "yes/$S1"
check "delta: the newer backup holds a husk without .git, so the older complete copy is chosen" test "$(rep_field "$REP" "$W/delta" 11)" = "$S1"
check "epsilon: exposed but in no backup, so not planned" test "$(rep_field "$REP" "$W/epsilon" 8)/$(rep_field "$REP" "$W/epsilon" 11)/$(rep_field "$REP" "$W/epsilon" 13)" = "yes/none/no"
check "zeta: vanished but not exposed, so not planned" test "$(rep_field "$REP" "$W/zeta" 8)/$(rep_field "$REP" "$W/zeta" 13)" = "no/no"
check "theta: a detached-HEAD worktree on no remote branch is exposed by that rule alone" test "$(rep_field "$REP" "$W/theta" 8)/$(rep_field "$REP" "$W/theta" 9)" = "yes/detached-head-on-no-remote-branch"
check "iota: the clean parent is not exposed by itself" test "$(rep_field "$REP" "$W/iota" 8)" = no
check "kappa: a plain REPO on a detached HEAD that no remote branch contains is exposed too, and planned" test "$(rep_field "$REP" "$W/kappa" 8)/$(rep_field "$REP" "$W/kappa" 9)/$(rep_field "$REP" "$W/kappa" 13)" = "yes/detached-head-on-no-remote-branch/yes"
check "kappa: it was clean, with no stash and nothing unpushed (only the detached rule can catch it)" test "$(rep_field "$REP" "$W/kappa" 5)/$(rep_field "$REP" "$W/kappa" 6)/$(rep_field "$REP" "$W/kappa" 7)" = "0/0/0"
check "lambda: an UNKNOWN unpushed count counts as exposed" test "$(rep_field "$REP" "$W/lambda" 8)/$(rep_field "$REP" "$W/lambda" 9)" = "yes/unpushed-unknown"
check "a path outside \$HOME is reported outside-home, not mistaken for a relative path" test "$(rep_field "$REP" "$base/outside/proj" 11)" = outside-home
check "eta is marked already rescued and not planned" test "$(rep_field "$REP" "$W/eta" 12)/$(rep_field "$REP" "$W/eta" 13)" = "yes/no"
check "plan: beta, gamma, delta, theta, lambda, kappa, plus the worktree's parent iota" test "$(awk -F'\t' 'FNR>1{print $1}' "$PLAN" | LC_ALL=C sort | tr '\n' '|')" = "Workspace/delta|Workspace/gamma|Workspace/iota|Workspace/kappa|Workspace/lambda|Workspace/theta|Workspace/work area/beta|"
check "plan: the parent is taken from the worktree's own backup and labelled" grep -qx "Workspace/iota"$'\t'"$S2"$'\t'"parent-of-worktree" "$PLAN"
out_has "summary: 12 swept, 11 vanished, 9 exposed" 'swept entries: 12; vanished from the Mac: 11; carrying exposed work: 9'
out_has "summary: two exposed entries are unrescuable" 'UNRESCUABLE: 2|exposed but UNRESCUABLE: 2'
out_has "  ...epsilon is listed" 'epsilon'
out_has "  ...and the outside path is listed" 'outside/proj'
check "dry created nothing on the external volume" test "$(find "$ext" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')" = "$n_ext"

XENV=(TM_SWEEP_TSV="$base/sweep/git.tsv" TM_OUT="$VOUT"); run tm-vanished.sh dry; XENV=()
check "without TM_ALREADY eta is planned again" test "$(rep_field "$REP" "$W/eta" 12)/$(rep_field "$REP" "$W/eta" 13)" = "no/yes"
printf 'path\treasons\n%s\tx\n' "$W/work area/beta" > "$base/real.tsv"
XENV=(TM_SWEEP_TSV="$base/sweep/git.tsv" TM_OUT="$VOUT" TM_REAL_TSV="$base/real.tsv" TM_STAMPS="$S1"); run tm-vanished.sh dry; XENV=()
check "TM_REAL_TSV adds in_real_list (yes for a listed path, no otherwise)" test "$(rep_field "$REP" "$W/work area/beta" 10)/$(rep_field "$REP" "$W/gamma" 10)" = "yes/no"
check "TM_STAMPS restricts the search: beta now resolves to the older backup" test "$(rep_field "$REP" "$W/work area/beta" 11)" = "$S1"
mkdir -p "$ext/notrescue"
XENV=(TM_SWEEP_TSV="$base/sweep/git.tsv" TM_OUT="$VOUT" TM_ALREADY="$ext/notrescue"); run tm-vanished.sh dry; XENV=()
rc_is "a TM_ALREADY entry that is not a rescue destination is refused" 2
printf 'path\tkind\n' > "$base/sweep-bad.tsv"
XENV=(TM_SWEEP_TSV="$base/sweep-bad.tsv" TM_OUT="$VOUT"); run tm-vanished.sh dry; XENV=()
rc_is "a sweep TSV lacking required columns is refused" 2; out_has "  ...naming the missing column" 'lacks column'
head -n 1 "$base/sweep/git.tsv" > "$base/sweep-empty.tsv"
XENV=(TM_SWEEP_TSV="$base/sweep-empty.tsv" TM_OUT="$VOUT"); run tm-vanished.sh dry; XENV=()
rc_is "a sweep with no rows is refused (no vacuous pass)" 2

# apply: rescue everything rescuable, report the rest
n_ext="$(find "$ext" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')"
XENV=(TM_SWEEP_TSV="$base/sweep/git.tsv" TM_OUT="$VOUT" TM_ALREADY="$ext/eta-dest" TM_DEST_ROOT=); run tm-vanished.sh apply; XENV=()
rc_is "vanished apply without a destination exits 2" 2; out_has "  ...saying so" 'no destination'
check "  ...and created nothing on the external volume" test "$(find "$ext" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')" = "$n_ext"
mkdir -p "$ext/v"
XENV=(TM_SWEEP_TSV="$base/sweep/git.tsv" TM_OUT="$VOUT" TM_ALREADY="$ext/eta-dest" TM_DEST_ROOT="$ext/v"); run tm-vanished.sh apply; XENV=()
rc_is "vanished apply exits 1 because two exposed entries cannot be rescued" 1
out_has "  ...the rescue itself passed" 'RESULT: PASS'
out_has "  ...and the unrescuable ones are called out" 'RESULT: FAIL -- 2 exposed'
VD="$ext/v/recovered-from-tm-$S2-and-earlier"
check "rescue destination holds seven green rows" test "$(awk -F'\t' 'FNR>1 && $3=="copied"' "$VD/RESCUE-RESULTS.tsv" | wc -l | tr -d ' ')" = 7
check "kappa's detached commit is in the rescued copy (git oracle)" git -C "$VD/$S2/Workspace/kappa" cat-file -e "$KAPPA_C^{commit}"
check "beta came from the newer backup (has later.txt)" test -f "$VD/$S2/Workspace/work area/beta/later.txt"
check "gamma came from the older backup and keeps its uncommitted file" test -f "$VD/$S1/Workspace/gamma/wip.txt"
check "delta has its .git (the husk was skipped)" test -d "$VD/$S1/Workspace/delta/.git"
check "theta and its parent iota were rescued together" test -f "$VD/$S2/Workspace/theta/t.txt" -a -d "$VD/$S2/Workspace/iota/.git"
check "zeta, eta and epsilon were not copied" test ! -e "$VD/$S2/Workspace/zeta" -a ! -e "$VD/$S2/Workspace/eta" -a ! -e "$VD/$S2/Workspace/epsilon"
check "each copy equals its backup (independent oracle): beta" same_tree "$H2/Workspace/work area/beta" "$VD/$S2/Workspace/work area/beta"
check "  ...gamma" same_tree "$H1/Workspace/gamma" "$VD/$S1/Workspace/gamma"
check "  ...delta" same_tree "$H1/Workspace/delta" "$VD/$S1/Workspace/delta"
check "  ...theta" same_tree "$H2/Workspace/theta" "$VD/$S2/Workspace/theta"
check "  ...iota" same_tree "$H2/Workspace/iota" "$VD/$S2/Workspace/iota"
check "  ...lambda" same_tree "$H2/Workspace/lambda" "$VD/$S2/Workspace/lambda"
check "  ...kappa" same_tree "$H2/Workspace/kappa" "$VD/$S2/Workspace/kappa"
XENV=(TM_SWEEP_TSV="$base/sweep/git.tsv" TM_OUT="$VOUT" TM_ALREADY="$ext/eta-dest" TM_DEST_ROOT="$ext/v"); run tm-vanished.sh apply; XENV=()
rc_is "a second vanished apply refuses to overwrite the run directory" 2; out_has "  ...saying so" 'already exists; refusing to overwrite'
run tm-rescue-verify.sh apply "$VD"; rc_is "verify of the vanished-rescue destination passes" 0
check "  ...with a shasum -c checkable manifest" bash -c 'cd "$1" && shasum -a 256 -c RESCUE-MANIFEST.sha256 > /dev/null' _ "$VD"

# ================================================================ E. the fixture's backups and Mac were only read
check "the fake backups are unchanged (paths, types, link targets, contents)" test "$(fingerprint "$tm")" = "$FP_TM"
check "the fake Mac is unchanged" test "$(fingerprint "$HOME")" = "$FP_HOME"
check "nothing in the backups or on the Mac was created or modified after the fixture was built" test -z "$(find "$tm" "$HOME" -newer "$base/marker" 2>/dev/null)"

total=$((pass + fail))
chmod -R u+w "$base" 2>/dev/null
if [ "$fail" = 0 ]; then
  case "$base" in */tm-rescue-selftest.*) rm -rf "$base" ;; esac
  echo "RESULT: PASS ($pass checks)"; exit 0
fi
echo "RESULT: FAIL ($fail of $total checks failed; fixture kept for inspection: $base)"; exit 1
