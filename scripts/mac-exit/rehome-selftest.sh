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

# VolA is a normal volume; VolReplica stands for the independent replica that must never be converted. rehome.sh learns
# that only through REHOME_SKIP_VOLUMES (SKIP below), never from a name.
SKIP=VolReplica
disc="$base/discovery.tsv"
printf 'volume\tworktree\tadmin_dir\tparent_repo\tadmin_id\tadmin_exists\n' > "$disc"
row() { printf 'VolA\t%s\t%s\t%s\t%s\tyes\n' "$1" "$2/.git/worktrees/$3" "$2" "$3" >> "$disc"; }
row "$A1" "$base/mac/alpha" alpha-feat; row "$A2" "$base/mac/alpha" alpha-detached
row "$B1" "$base/mac/beta" beta-feat;   row "$D1" "$base/mac/beta" -dashed
printf 'VolReplica\t%s\t%s\t%s\t%s\tyes\n' "$base/ext/replica-skip" "x" "$base/mac/alpha" "replica-skip" >> "$disc"
printf 'VolA\t%s\t%s\t?\t%s\tno\n' "$base/ext/orphan" "x" "orphan" >> "$disc"

pointer() { cat "$1/.git"; }
P_A1="$(pointer "$A1")"; P_A2="$(pointer "$A2")"; P_B1="$(pointer "$B1")"; P_D1="$(pointer "$D1")"
st() { printf '%s|%s' "$(git -C "$1" rev-parse HEAD)" "$(git -C "$1" status --porcelain=v1 -z | shasum -a 256 | cut -d' ' -f1)"; }
S_A1="$(st "$A1")"; S_A2="$(st "$A2")"; S_B1="$(st "$B1")"; S_D1="$(st "$D1")"
same_state() { [ "$(st "$A1")" = "$S_A1" ] && [ "$(st "$A2")" = "$S_A2" ] && [ "$(st "$B1")" = "$S_B1" ] && [ "$(st "$D1")" = "$S_D1" ]; }

# 1. dry run writes nothing and sees exactly the 4 live worktrees on volumes that are not skipped
dry="$(REHOME_SKIP_VOLUMES="$SKIP" bash "$here/rehome.sh" "$disc" "$base/stores" dry "$base/out" 2>&1)"
[ -e "$base/stores" ] && bad "dry run created the store root" || ok "dry run wrote nothing"
case "$dry" in *"would convert 4 worktree(s)"*) ok "dry run plans exactly 4 conversions (skipped-volume + orphan rows excluded)";; *) bad "dry run plan wrong: $dry";; esac

# 2. apply
REHOME_SKIP_VOLUMES="$SKIP" bash "$here/rehome.sh" "$disc" "$base/stores" apply "$base/out" > "$base/apply.log" 2>&1 && ok "apply exit 0 (RESULT: PASS)" || bad "apply failed: $(tail -n 5 "$base/apply.log")"
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
REHOME_SKIP_VOLUMES="$SKIP" bash "$here/rehome.sh" "$disc" "$base/stores" apply "$base/out2" > "$base/apply2.log" 2>&1 && bad "second apply claimed PASS over existing stores" || ok "second apply refuses (stores exist) and exits non-zero"

# 6. the parameter, not the name, decides. Same row shape on two volumes: G1 on the volume the sections above skipped,
# G2 on another. Skipping the OTHER volume must convert G1 (so the name VolReplica carries no meaning of its own), and
# with the skip list set but empty both rows are planned.
mkrepo gamma
G1="$base/ext/gamma-one"; G2="$base/ext/gamma-two"
git -C "$base/mac/gamma" worktree add -q "$G1" feat
git -C "$base/mac/gamma" worktree add -q --detach "$G2" HEAD
P_G1="$(pointer "$G1")"; P_G2="$(pointer "$G2")"
disc3="$base/discovery-param.tsv"
printf 'volume\tworktree\tadmin_dir\tparent_repo\tadmin_id\tadmin_exists\n' > "$disc3"
printf 'VolReplica\t%s\t%s\t%s\t%s\tyes\n' "$G1" "$base/mac/gamma/.git/worktrees/gamma-one" "$base/mac/gamma" gamma-one >> "$disc3"
printf 'VolOther\t%s\t%s\t%s\t%s\tyes\n' "$G2" "$base/mac/gamma/.git/worktrees/gamma-two" "$base/mac/gamma" gamma-two >> "$disc3"
dry_all="$(REHOME_SKIP_VOLUMES='' bash "$here/rehome.sh" "$disc3" "$base/stores3" dry "$base/out3" 2>&1)"
case "$dry_all" in *"would convert 2 worktree(s)"*) ok "skip list set but empty: nothing is skipped, both rows planned";; *) bad "empty skip list still skipped something: $dry_all";; esac
dry_one="$(REHOME_SKIP_VOLUMES=VolOther bash "$here/rehome.sh" "$disc3" "$base/stores3" dry "$base/out3" 2>&1)"
case "$dry_one" in *"would convert 1 worktree(s)"*"$G1"*|*"$G1"*"would convert 1 worktree(s)"*) ok "skipping VolOther plans the VolReplica row";; *) bad "skip plan wrong: $dry_one";; esac
case "$dry_one" in *"$G2"*) bad "skipped volume's worktree still planned";; *) ok "skipped volume's worktree is not planned";; esac
REHOME_SKIP_VOLUMES=VolOther bash "$here/rehome.sh" "$disc3" "$base/stores3" apply "$base/out3" > "$base/apply3.log" 2>&1 && ok "apply with VolOther skipped exits 0" || bad "apply with VolOther skipped failed: $(tail -n 5 "$base/apply3.log")"
[ "$(pointer "$G1")" != "$P_G1" ] && ok "VolReplica row converted: only the skip list decides, not the name" || bad "VolReplica row was not converted"
[ "$(pointer "$G2")" = "$P_G2" ] && ok "VolOther row left untouched" || bad "skipped VolOther row was converted"

# 7. fail closed: an UNSET skip list refuses both modes (exit 64) and writes nothing. Set-but-empty is allowed (section 6).
# G2 has not been converted, so it is the live row an unguarded run would have rewritten.
env -u REHOME_SKIP_VOLUMES bash "$here/rehome.sh" "$disc3" "$base/stores4" dry "$base/out4" > "$base/unset-dry.log" 2>&1; rc_dry=$?
env -u REHOME_SKIP_VOLUMES bash "$here/rehome.sh" "$disc3" "$base/stores4" apply "$base/out4" > "$base/unset-apply.log" 2>&1; rc_apply=$?
[ "$rc_dry" = 64 ] && ok "unset REHOME_SKIP_VOLUMES: dry refuses with exit 64" || bad "unset skip list, dry exited $rc_dry (want 64)"
[ "$rc_apply" = 64 ] && ok "unset REHOME_SKIP_VOLUMES: apply refuses with exit 64" || bad "unset skip list, apply exited $rc_apply (want 64)"
grep -q 'REHOME_SKIP_VOLUMES' "$base/unset-dry.log" "$base/unset-apply.log" && ok "the refusal names the variable" || bad "refusal does not name REHOME_SKIP_VOLUMES"
{ [ ! -e "$base/stores4" ] && [ ! -e "$base/out4" ]; } && ok "unset skip list wrote nothing (no store root, no out dir)" || bad "refused run still wrote something"
[ "$(pointer "$G2")" = "$P_G2" ] && ok "unset skip list left the live worktree untouched" || bad "unset skip list converted a worktree"

if [ "$fail" = 0 ]; then rm -rf "$base"; echo "RESULT: PASS"; exit 0; fi
echo "RESULT: FAIL (fixture kept for inspection: $base)"; exit 1
