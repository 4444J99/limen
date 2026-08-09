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
# Overridable so the A/B that PROVES a regression test — run it against the parent commit's script
# and require a FAIL — is one command rather than a hand-edited copy. A test that has only ever been
# seen to pass has not been shown to test anything.
script="${LIMEN_SYNC_RELEASE_SCRIPT:-$here/../sync-release.sh}"
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

# A clean committed tasks.yaml-only divergence is regenerable, including when
# the daemon exports the authoritative parameter-panel default.
panel_receipt_globs="$(
  env -u LIMEN_SYNC_RECEIPT_GLOBS \
    LIMEN_ROOT="$here/../.." \
    PYTHONPATH="$here/../../cli/src" \
    python3 -c 'from limen.vigilia import params; print(params.get("LIMEN_SYNC_RECEIPT_GLOBS", ""))'
)"
[ -n "$panel_receipt_globs" ] \
  || { echo "FAIL: LIMEN_SYNC_RECEIPT_GLOBS has no parameter-panel default"; exit 1; }

git init -q --bare "$tmp/diverged-origin.git"
git clone -q "$tmp/diverged-origin.git" "$tmp/diverged-live" 2>/dev/null
git -C "$tmp/diverged-live" checkout -q -b main
mkdir -p "$tmp/diverged-live/docs"
printf 'task-v1\n' > "$tmp/diverged-live/tasks.yaml"
printf 'base\n' > "$tmp/diverged-live/docs/base.md"
git -C "$tmp/diverged-live" add -A
git -C "$tmp/diverged-live" commit -q -m "divergence base"
git -C "$tmp/diverged-live" push -q -u origin main
git --git-dir="$tmp/diverged-origin.git" symbolic-ref HEAD refs/heads/main
git clone -q "$tmp/diverged-origin.git" "$tmp/diverged-peer" 2>/dev/null

printf 'task-local-only\n' > "$tmp/diverged-live/tasks.yaml"
git -C "$tmp/diverged-live" add tasks.yaml
git -C "$tmp/diverged-live" commit -q -m "local tasks projection"
printf 'release-one\n' > "$tmp/diverged-peer/release-one.md"
git -C "$tmp/diverged-peer" add release-one.md
git -C "$tmp/diverged-peer" commit -q -m "release advance one"
git -C "$tmp/diverged-peer" push -q origin main

receipt_out="$(LIMEN_ROOT="$tmp/diverged-live" LIMEN_RELEASE_BRANCH=main \
  LIMEN_SYNC_RECEIPT_GLOBS="$panel_receipt_globs" bash "$script" 2>&1)" \
  || { echo "FAIL: tasks-only divergence sync exited nonzero"; echo "$receipt_out"; exit 1; }
remote_head="$(git --git-dir="$tmp/diverged-origin.git" rev-parse refs/heads/main)"
[ "$(git -C "$tmp/diverged-live" rev-parse HEAD)" = "$remote_head" ] \
  || { echo "FAIL: tasks-only divergence did not re-converge"; echo "$receipt_out"; exit 1; }
grep -Fq "local commit(s) touch ONLY regenerable receipts" <<<"$receipt_out" \
  || { echo "FAIL: tasks-only divergence emitted no receipt-valve reason"; echo "$receipt_out"; exit 1; }
[ "$(git -C "$tmp/diverged-live" show HEAD:tasks.yaml)" = "task-v1" ] \
  || { echo "FAIL: tasks-only divergence did not restore the remote projection"; echo "$receipt_out"; exit 1; }

# Mixed local history is genuine work even when one path is tasks.yaml; it must
# retain the exact local head and fail open.
printf 'task-local-mixed\n' > "$tmp/diverged-live/tasks.yaml"
printf 'local-real-work\n' > "$tmp/diverged-live/docs/real-work.md"
git -C "$tmp/diverged-live" add tasks.yaml docs/real-work.md
git -C "$tmp/diverged-live" commit -q -m "mixed local work"
mixed_head="$(git -C "$tmp/diverged-live" rev-parse HEAD)"
printf 'release-two\n' > "$tmp/diverged-peer/release-two.md"
git -C "$tmp/diverged-peer" add release-two.md
git -C "$tmp/diverged-peer" commit -q -m "release advance two"
git -C "$tmp/diverged-peer" push -q origin main

mixed_out="$(LIMEN_ROOT="$tmp/diverged-live" LIMEN_RELEASE_BRANCH=main \
  LIMEN_SYNC_RECEIPT_GLOBS="$panel_receipt_globs" bash "$script" 2>&1)" \
  || { echo "FAIL: mixed divergence sync exited nonzero"; echo "$mixed_out"; exit 1; }
[ "$(git -C "$tmp/diverged-live" rev-parse HEAD)" = "$mixed_head" ] \
  || { echo "FAIL: mixed divergence moved the local head"; echo "$mixed_out"; exit 1; }
grep -Fq "with UNIQUE local work — fail open" <<<"$mixed_out" \
  || { echo "FAIL: mixed divergence emitted no fail-open reason"; echo "$mixed_out"; exit 1; }
grep -q "local-real-work" "$tmp/diverged-live/docs/real-work.md" \
  || { echo "FAIL: mixed divergence lost genuine local work"; echo "$mixed_out"; exit 1; }


# --check: a real predicate, not the informational --census. Fresh clone at HEAD==origin/main
# with default RECEIPT_GLOBS (no override) proves the shipped defaults, not just the test panel's.
git clone -q "$tmp/origin.git" "$tmp/check-live" 2>/dev/null
( cd "$tmp/check-live" && git checkout -q main )
check_rc=0
check_out="$(LIMEN_ROOT="$tmp/check-live" LIMEN_RELEASE_BRANCH=main bash "$script" --check 2>&1)" || check_rc=$?
[ "$check_rc" = 0 ] || { echo "FAIL: --check on a clean live root at origin/main should PASS"; echo "$check_out"; exit 1; }

# Genuine uncommitted source-tree work must FAIL --check.
mkdir -p "$tmp/check-live/scripts"
echo "wip" > "$tmp/check-live/scripts/wip.sh"
dirty_rc=0
dirty_out="$(LIMEN_ROOT="$tmp/check-live" LIMEN_RELEASE_BRANCH=main bash "$script" --check 2>&1)" || dirty_rc=$?
[ "$dirty_rc" = 1 ] || { echo "FAIL: --check should FAIL on genuine untracked source dirt"; echo "$dirty_out"; exit 1; }
rm -f "$tmp/check-live/scripts/wip.sh"

# Regenerable bookkeeping churn (the default globs: branch-hygiene.md, overnight-watch.md) must
# still PASS --check — this is the exact class that stranded the live root for 3+ days when the
# tolerance list didn't cover it.
echo "v3-dirty" >> "$tmp/check-live/docs/branch-hygiene.md"
mkdir -p "$tmp/check-live/logs"
echo "beat line" >> "$tmp/check-live/logs/overnight-watch.md"
mkdir -p "$tmp/check-live/docs/receipts/some-lane"
echo '{"ok":true}' > "$tmp/check-live/docs/receipts/some-lane/closeout-latest.json"
bookkeeping_rc=0
bookkeeping_out="$(LIMEN_ROOT="$tmp/check-live" LIMEN_RELEASE_BRANCH=main bash "$script" --check 2>&1)" || bookkeeping_rc=$?
[ "$bookkeeping_rc" = 0 ] \
  || { echo "FAIL: --check should PASS with only regenerable bookkeeping dirty"; echo "$bookkeeping_out"; exit 1; }

# A contended session (limen.occupant set) should NOT block ff if dirt is entirely regenerable receipts.
git clone -q "$tmp/origin.git" "$tmp/contended-live" 2>/dev/null
( cd "$tmp/contended-live" && git checkout -q main )
git -C "$tmp/contended-live" config limen.occupant "test-contended-session"
# We need to advance origin so a fast-forward is actually needed
git clone -q "$tmp/origin.git" "$tmp/contended-peer" 2>/dev/null
( cd "$tmp/contended-peer" && git checkout -q main && echo r3 > rel3.md && git add -A && git commit -q -m "release advance three" && git push -q origin main )
mkdir -p "$tmp/contended-live/docs"
echo "v4-dirty" >> "$tmp/contended-live/docs/branch-hygiene.md"
contended_out="$(LIMEN_ROOT="$tmp/contended-live" LIMEN_RELEASE_BRANCH=main bash "$script" 2>&1)" || true
[ "$(git -C "$tmp/contended-live" rev-parse HEAD)" = "$(git --git-dir="$tmp/origin.git" rev-parse refs/heads/main)" ] \
  || { echo "FAIL: receipts-only tracked dirt blocked fast-forward under contention"; echo "$contended_out"; exit 1; }

# ── HELD BRANCH NAME: detach → advance → re-attach ──────────────────────────────────────────────
# The park this closes (observed 2026-08-09): .worktrees/main-checkout held `main`, so the unpark
# valve's `git switch` was refused every beat and the live checkout sat on a work branch three
# merges stale, accumulating 21 daemon `capture:` commits onto it. The organ captured the refusal
# reason and asked a human, forever — a sensor with no effector.
git init -q --bare "$tmp/held-origin.git"
git clone -q "$tmp/held-origin.git" "$tmp/held-live" 2>/dev/null
git -C "$tmp/held-live" checkout -q -b main
mkdir -p "$tmp/held-live/docs"
printf 'held-v1\n' > "$tmp/held-live/docs/base.md"
printf 'task\n' > "$tmp/held-live/tasks.yaml"
git -C "$tmp/held-live" add -A
git -C "$tmp/held-live" commit -q -m "held base"
git -C "$tmp/held-live" push -q -u origin main
git --git-dir="$tmp/held-origin.git" symbolic-ref HEAD refs/heads/main

# park the live root, THEN let a second worktree take the branch name (the real-world ordering)
git -C "$tmp/held-live" checkout -q -b codex/held-work
printf 'held-work\n' > "$tmp/held-live/docs/held-work.md"
git -C "$tmp/held-live" add docs/held-work.md
git -C "$tmp/held-live" commit -q -m "parked work"
git -C "$tmp/held-live" push -q -u origin codex/held-work
git -C "$tmp/held-live" worktree add -q "$tmp/held-peer" main

git clone -q "$tmp/held-origin.git" "$tmp/held-adv" 2>/dev/null
( cd "$tmp/held-adv" && git checkout -q main && echo h2 > h2.md && git add -A \
    && git commit -q -m "held release advance one" && git push -q origin main )

held_out="$(LIMEN_ROOT="$tmp/held-live" LIMEN_RELEASE_BRANCH=main bash "$script" 2>&1)" \
  || { echo "FAIL: held-branch sync exited nonzero"; echo "$held_out"; exit 1; }
[ -z "$(git -C "$tmp/held-live" symbolic-ref --quiet --short HEAD 2>/dev/null || echo)" ] \
  || { echo "FAIL: held branch name did not produce a detached HEAD"; echo "$held_out"; exit 1; }
grep -Fq "DETACHED at origin/main" <<<"$held_out" \
  || { echo "FAIL: detach fallback emitted no unpark receipt"; echo "$held_out"; exit 1; }
[ "$(git -C "$tmp/held-live" rev-parse HEAD)" = "$(git --git-dir="$tmp/held-origin.git" rev-parse refs/heads/main)" ] \
  || { echo "FAIL: detached HEAD is not at the release"; echo "$held_out"; exit 1; }
# the other worktree must be entirely untouched — that is the whole point of taking the SHA
[ "$(git -C "$tmp/held-peer" symbolic-ref --short HEAD)" = main ] \
  || { echo "FAIL: detach fallback disturbed the holding worktree"; echo "$held_out"; exit 1; }
# the parked branch's work is still preserved on origin
git -C "$tmp/held-live" cat-file -e origin/codex/held-work:docs/held-work.md 2>/dev/null \
  || { echo "FAIL: detach fallback skipped preserve-then-unpark"; echo "$held_out"; exit 1; }

# THE STEADY STATE — the arm that makes the detach a state rather than a one-shot. Without it the
# organ unparks once and then fails open on every beat afterwards, which reads in the log as an
# ordinary refusal rather than as a valve that fired once and died.
( cd "$tmp/held-adv" && echo h3 > h3.md && git add -A \
    && git commit -q -m "held release advance two" && git push -q origin main )
held2_out="$(LIMEN_ROOT="$tmp/held-live" LIMEN_RELEASE_BRANCH=main bash "$script" 2>&1)" \
  || { echo "FAIL: detached steady-state sync exited nonzero"; echo "$held2_out"; exit 1; }
[ "$(git -C "$tmp/held-live" rev-parse HEAD)" = "$(git --git-dir="$tmp/held-origin.git" rev-parse refs/heads/main)" ] \
  || { echo "FAIL: detached HEAD did not advance to the new release"; echo "$held2_out"; exit 1; }
grep -Fq "advancing detached HEAD" <<<"$held2_out" \
  || { echo "FAIL: detached advance emitted no receipt"; echo "$held2_out"; exit 1; }
[ -f "$tmp/held-live/h3.md" ] \
  || { echo "FAIL: detached advance did not deploy the release tree"; echo "$held2_out"; exit 1; }

# --check must call that converged-under-contention state a PASS: it asserts the live root RUNS the
# release, and no version of it that demands the branch NAME can ever go green while a second
# worktree holds it.
held_check_rc=0
held_check_out="$(LIMEN_ROOT="$tmp/held-live" LIMEN_RELEASE_BRANCH=main bash "$script" --check 2>&1)" || held_check_rc=$?
[ "$held_check_rc" = 0 ] \
  || { echo "FAIL: --check should PASS when detached at the release with the name held"; echo "$held_check_out"; exit 1; }
grep -Fq "DETACHED at exact origin/main" <<<"$held_check_out" \
  || { echo "FAIL: --check did not distinguish the detached PASS"; echo "$held_check_out"; exit 1; }

# …but a GRATUITOUS detach — nobody holding the name — is still a FAIL. The exemption is bounded by
# the contention that justifies it, not granted to detached HEADs generally.
git clone -q "$tmp/held-origin.git" "$tmp/loose-live" 2>/dev/null
git -C "$tmp/loose-live" checkout -q --detach origin/main
loose_rc=0
loose_out="$(LIMEN_ROOT="$tmp/loose-live" LIMEN_RELEASE_BRANCH=main bash "$script" --check 2>&1)" || loose_rc=$?
[ "$loose_rc" = 1 ] \
  || { echo "FAIL: --check should FAIL on a detached HEAD with the branch name free"; echo "$loose_out"; exit 1; }

# RE-ATTACH — the detach is a contingency the organ exits on its own. Release the name and HEAD
# comes home to the branch, then fast-forwards it normally in the same beat.
git -C "$tmp/held-live" worktree remove "$tmp/held-peer"
( cd "$tmp/held-adv" && echo h4 > h4.md && git add -A \
    && git commit -q -m "held release advance three" && git push -q origin main )
held3_out="$(LIMEN_ROOT="$tmp/held-live" LIMEN_RELEASE_BRANCH=main bash "$script" 2>&1)" \
  || { echo "FAIL: re-attach sync exited nonzero"; echo "$held3_out"; exit 1; }
[ "$(git -C "$tmp/held-live" symbolic-ref --quiet --short HEAD 2>/dev/null || echo)" = main ] \
  || { echo "FAIL: HEAD did not re-attach to main once the name was free"; echo "$held3_out"; exit 1; }
grep -Fq "RE-ATTACHED" <<<"$held3_out" \
  || { echo "FAIL: re-attach emitted no receipt"; echo "$held3_out"; exit 1; }
[ "$(git -C "$tmp/held-live" rev-parse HEAD)" = "$(git --git-dir="$tmp/held-origin.git" rev-parse refs/heads/main)" ] \
  || { echo "FAIL: re-attached branch did not fast-forward to the release"; echo "$held3_out"; exit 1; }
held_check2_rc=0
held_check2_out="$(LIMEN_ROOT="$tmp/held-live" LIMEN_RELEASE_BRANCH=main bash "$script" --check 2>&1)" || held_check2_rc=$?
[ "$held_check2_rc" = 0 ] \
  || { echo "FAIL: --check should PASS after re-attach"; echo "$held_check2_out"; exit 1; }

echo "PASS: preserve/unpark + override guard + tasks-only self-heal + mixed divergence fail-open + --check predicate + contended receipts-only unpark + held-name detach/advance/re-attach"
