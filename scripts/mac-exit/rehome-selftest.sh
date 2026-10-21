#!/bin/bash
# End-to-end self-test of rehome.sh on a throwaway fixture. Touches nothing outside its own temp directory.
#
# WHY: rehome.sh rewrites the .git pointer of worktrees that live on an external drive. It must be proven on a fixture,
# including its refusal paths and its auto-rollback, before it ever touches real data. Several earlier versions passed
# vacuously (zero conversions reported as PASS), so this test asserts the pointers actually changed.
set -u
export GIT_OPTIONAL_LOCKS=0
here="$(cd "$(dirname "$0")" && pwd)"
base="$(mktemp -d "${TMPDIR:-/tmp}/rehome-selftest.XXXXXX")"
base="$(cd -P "$base" && pwd -P)"   # macOS $TMPDIR is under /var, a symlink to /private/var; git writes the resolved path
mkdir -p "$base/mac" "$base/ext" "$base/out"
fail=0
ok()  { printf 'ok    %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fail=1; }

mkrepo() { # name -> creates $base/mac/<name> with two commits
  local r="$base/mac/$1"
  git init -q "$r"; git -C "$r" config user.email t@example.invalid; git -C "$r" config user.name t
  echo one > "$r/a.txt"; git -C "$r" add a.txt; git -C "$r" commit -qm one
  git -C "$r" branch feat
  echo two > "$r/b.txt"; git -C "$r" add b.txt; git -C "$r" commit -qm two
}
mkrepo alpha; mkrepo beta
git -C "$base/mac/alpha" remote add origin https://user:topsecret@example.invalid/alpha.git
echo wip > "$base/mac/alpha/c.txt"; git -C "$base/mac/alpha" add c.txt; git -C "$base/mac/alpha" stash -q

A1="$base/ext/alpha-feat"; A2="$base/ext/alpha-detached"; B1="$base/ext/beta-feat"; D1="$base/ext/-dashed"
git -C "$base/mac/alpha" worktree add -q "$A1" feat
git -C "$base/mac/alpha" worktree add -q --detach "$A2" HEAD
git -C "$base/mac/beta"  worktree add -q "$B1" feat
git -C "$base/mac/beta"  worktree add -q -b dashed "$D1"        # an admin id that begins with a dash
echo untracked > "$A1/dirty.txt"; echo changed >> "$A2/a.txt"

disc="$base/discovery.tsv"
printf 'volume\tworktree\tadmin_dir\tparent_repo\tadmin_id\tadmin_exists\n' > "$disc"
row() { printf 'Archive4T\t%s\t%s\t%s\t%s\tyes\n' "$1" "$2/.git/worktrees/$3" "$2" "$3" >> "$disc"; }
row "$A1" "$base/mac/alpha" alpha-feat; row "$A2" "$base/mac/alpha" alpha-detached
row "$B1" "$base/mac/beta" beta-feat;   row "$D1" "$base/mac/beta" -dashed
printf 'T7Recovery\t%s\t%s\t%s\t%s\tyes\n' "$base/ext/t7-skip" "x" "$base/mac/alpha" "t7-skip" >> "$disc"
printf 'Scratch\t%s\t%s\t?\t%s\tno\n' "$base/ext/orphan" "x" "orphan" >> "$disc"

pointer() { cat "$1/.git"; }
P_A1="$(pointer "$A1")"; P_A2="$(pointer "$A2")"; P_B1="$(pointer "$B1")"; P_D1="$(pointer "$D1")"
st() { printf '%s|%s' "$(git -C "$1" rev-parse HEAD)" "$(git -C "$1" status --porcelain=v1 -z | shasum -a 256 | cut -d' ' -f1)"; }
S_A1="$(st "$A1")"; S_A2="$(st "$A2")"; S_B1="$(st "$B1")"; S_D1="$(st "$D1")"
same_state() { [ "$(st "$A1")" = "$S_A1" ] && [ "$(st "$A2")" = "$S_A2" ] && [ "$(st "$B1")" = "$S_B1" ] && [ "$(st "$D1")" = "$S_D1" ]; }

# 1. dry run writes nothing and sees exactly the 4 live non-T7 worktrees
dry="$(bash "$here/rehome.sh" "$disc" "$base/stores" dry "$base/out" 2>&1)"
[ -e "$base/stores" ] && bad "dry run created the store root" || ok "dry run wrote nothing"
case "$dry" in *"would convert 4 worktree(s)"*) ok "dry run plans exactly 4 conversions (T7 + orphan rows skipped)";; *) bad "dry run plan wrong: $dry";; esac

# 2. apply
bash "$here/rehome.sh" "$disc" "$base/stores" apply "$base/out" > "$base/apply.log" 2>&1 && ok "apply exit 0 (RESULT: PASS)" || bad "apply failed: $(tail -n 5 "$base/apply.log")"
[ "$(awk -F'\t' 'NR>1 && $6=="converted"' "$base/out/rehome-results.tsv" | wc -l | tr -d ' ')" = "4" ] && ok "4 worktrees converted (including the dash-named id)" || bad "conversion count wrong"
[ "$(pointer "$A1")" != "$P_A1" ] && [ "$(pointer "$A2")" != "$P_A2" ] && [ "$(pointer "$B1")" != "$P_B1" ] && [ "$(pointer "$D1")" != "$P_D1" ] && ok "all pointers actually changed (real work, not a trivial pass)" || bad "pointer unchanged: nothing was converted"
grep -q "$base/stores" "$A1/.git" && ok "pointer names the standalone store" || bad "pointer does not name the store"
grep -rq topsecret "$base/stores" && bad "credential leaked into the store" || ok "remote-URL credential redacted in the store copy"
same_state && ok "HEAD + status identical for all 4 after convert" || bad "state changed"
[ -z "$(find "$A1" "$A2" "$B1" "$D1" -maxdepth 1 -name '.git.*')" ] && ok "no stray file inside any worktree" || bad "stray file inside a worktree"
git --git-dir="$base/stores/alpha.git" rev-parse --verify -q refs/stash >/dev/null && ok "stash survived in the store" || bad "stash lost"

# 3. the Mac disappears
mv "$base/mac" "$base/mac.erased"
same_state && ok "all 4 worktrees identical with the Mac repos gone" || bad "worktree broken with Mac gone"
git -C "$A2" fsck --connectivity-only >/dev/null 2>&1 && ok "fsck passes with the Mac gone" || bad "fsck broken"

# 4. rollback restores the exact original pointers
mv "$base/mac.erased" "$base/mac"
bash "$base/out/rollback.sh" && ok "rollback script ran" || bad "rollback script failed"
[ "$(pointer "$A1")" = "$P_A1" ] && [ "$(pointer "$A2")" = "$P_A2" ] && [ "$(pointer "$B1")" = "$P_B1" ] && [ "$(pointer "$D1")" = "$P_D1" ] && ok "original pointers restored byte for byte" || bad "pointers differ after rollback"
same_state && ok "state intact after rollback" || bad "state differs after rollback"

# 5. a second apply must refuse to overwrite the existing stores
bash "$here/rehome.sh" "$disc" "$base/stores" apply "$base/out2" > "$base/apply2.log" 2>&1 && bad "second apply claimed PASS over existing stores" || ok "second apply refuses (stores exist) and exits non-zero"

if [ "$fail" = 0 ]; then rm -rf "$base"; echo "RESULT: PASS"; exit 0; fi
echo "RESULT: FAIL (fixture kept for inspection: $base)"; exit 1
