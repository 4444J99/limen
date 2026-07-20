#!/usr/bin/env bash
# sync-release.test.sh — regression test for the sync-release UNPARK valve.
#
# Proves PRESERVE-THEN-UNPARK (2026-07-09): a live checkout parked on a work branch with tracked
# dirt is neither abandoned nor left stuck. The valve commits+pushes the dirt to origin (the
# operator's standing rule: nothing is abandoned that is not first safe on origin), THEN rests HEAD
# on the release branch and fast-forwards. Guards the 2026-06-29→07-04 incident where the valve
# fail-opened on dirt, "hoped" capture.sh would land it next beat, and nothing did for five days —
# pinning the daemon to stale code 65 commits behind release.
#
# Hermetic: builds a local bare origin + working clone; no network. Exit 0 ⟺ all asserts pass.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
script="$here/../sync-release.sh"
[ -f "$script" ] || { echo "FAIL: cannot find sync-release.sh at $script" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null

git init -q --bare "$tmp/origin.git"
git clone -q "$tmp/origin.git" "$tmp/live" 2>/dev/null
cd "$tmp/live"
git checkout -q -b main
mkdir -p scripts logs docs
echo "v1" > docs/branch-hygiene.md
echo "task" > tasks.yaml
git add -A && git commit -q -m "main v1"
git push -q -u origin main
git --git-dir="$tmp/origin.git" symbolic-ref HEAD refs/heads/main

# park on a work branch: a unique work commit already on origin + uncommitted tracked dirt
git checkout -q -b codex/work
echo "doctrine" > doctrine.md
git add doctrine.md && git commit -q -m "work commit"
git push -q -u origin codex/work
echo "v2-dirty" >> docs/branch-hygiene.md     # tracked dirt beyond tasks.yaml — must be preserved
echo "task2" >> tasks.yaml                     # daemon-owned queue dirt — must NOT be committed here

# advance origin/main so the run also exercises the post-unpark fast-forward
git clone -q "$tmp/origin.git" "$tmp/c2" 2>/dev/null
( cd "$tmp/c2" && git checkout -q main && echo r2 > rel2.md && git add -A && git commit -q -m "release advance" && git push -q origin main )

out="$(LIMEN_ROOT="$tmp/live" LIMEN_RELEASE_BRANCH=main bash "$script" 2>&1)" \
  || { echo "FAIL: sync-release exited nonzero"; echo "$out"; exit 1; }

cur="$(git -C "$tmp/live" symbolic-ref --short HEAD)"
[ "$cur" = codex/work ] || { echo "FAIL: dirty board cache did not fence unpark (HEAD on '$cur')"; echo "$out"; exit 1; }
printf '%s' "$out" | grep -q "local tasks.yaml cache is dirty" \
  || { echo "FAIL: dirty board cache emitted no exact refusal"; echo "$out"; exit 1; }
grep -q v2-dirty "$tmp/live/docs/branch-hygiene.md" \
  || { echo "FAIL: fenced unpark lost parked tracked dirt"; echo "$out"; exit 1; }
grep -q task2 "$tmp/live/tasks.yaml" \
  || { echo "FAIL: fenced unpark changed the dirty board cache"; echo "$out"; exit 1; }

# Once the local cache is clean, the same valve may preserve the unrelated dirt and unpark.
git -C "$tmp/live" checkout -q -- tasks.yaml
out="$(LIMEN_ROOT="$tmp/live" LIMEN_RELEASE_BRANCH=main bash "$script" 2>&1)" \
  || { echo "FAIL: clean-cache sync-release exited nonzero"; echo "$out"; exit 1; }
cur="$(git -C "$tmp/live" symbolic-ref --short HEAD)"
[ "$cur" = main ] || { echo "FAIL: not unparked to main (HEAD on '$cur')"; echo "$out"; exit 1; }

git -C "$tmp/live" fetch -q origin codex/work
git -C "$tmp/live" show origin/codex/work:docs/branch-hygiene.md 2>/dev/null | grep -q v2-dirty \
  || { echo "FAIL: parked dirt not preserved on origin/codex/work"; echo "$out"; exit 1; }

git -C "$tmp/live" cat-file -e origin/codex/work:doctrine.md 2>/dev/null \
  || { echo "FAIL: unique work commit lost from origin"; echo "$out"; exit 1; }

git -C "$tmp/live" cat-file -e HEAD:rel2.md 2>/dev/null \
  || { echo "FAIL: did not fast-forward to the advanced release"; echo "$out"; exit 1; }

# tasks.yaml must NOT have been committed onto the work branch (daemon-owned; preserved as working copy)
if git -C "$tmp/live" show origin/codex/work:tasks.yaml 2>/dev/null | grep -q task2; then
  echo "FAIL: daemon-owned tasks.yaml was wrongly committed to the branch"; echo "$out"; exit 1
fi

# A mutable release override must never reclassify the actual default branch as
# a parked topic branch and push it. Give the override a real remote target so
# the refusal is proving the default-branch guard, not an incidental fetch
# failure.
git -C "$tmp/live" branch release-alt main
git -C "$tmp/live" push -q origin release-alt
main_before="$(git --git-dir="$tmp/origin.git" rev-parse refs/heads/main)"
echo "must-stay-local" >> "$tmp/live/docs/branch-hygiene.md"
override_out="$(LIMEN_ROOT="$tmp/live" LIMEN_RELEASE_BRANCH=release-alt bash "$script" 2>&1)"
main_after="$(git --git-dir="$tmp/origin.git" rev-parse refs/heads/main)"
[ "$main_before" = "$main_after" ] \
  || { echo "FAIL: release override moved the actual default branch"; echo "$override_out"; exit 1; }
grep -q "REFUSED.*origin's default branch" <<<"$override_out" \
  || { echo "FAIL: release override did not fail closed"; echo "$override_out"; exit 1; }
grep -q "must-stay-local" "$tmp/live/docs/branch-hygiene.md" \
  || { echo "FAIL: release override consumed default-branch dirt"; echo "$override_out"; exit 1; }

echo "PASS: preserve-then-unpark + mutable release override cannot write the actual default branch"
