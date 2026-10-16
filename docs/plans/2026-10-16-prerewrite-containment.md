# Pre-rewrite lineage: containment, classification, ordered reconciliation

Issue: #2878
PR: (pending)

Related: #2537 (GitHub-side purge of old SHAs — a separate human step).

## State at plan time (2026-10-16)

The 2026-10-10 rewrite (manifest commit `66b2ee71a`, boundary `31664a78`) replaced public history.
The shared checkout and many local refs still carry the pre-rewrite ("old") lineage. This plan is
**containment and classification only**; no old ref was moved, deleted, pushed, rebased, or reset.

Live evidence lives in `docs/receipts/privacy/prerewrite-containment-20261016.json` (public: ref
names, salted commit digests, classes, counts). Paths, subjects, full ids and the learned scrub map
stay in `$LIMEN_CUSTODY_STAGING_ROOT/prerewrite-containment-20261016/` (mode 0700).

| Measure | Value |
|---|---|
| Refs by lineage | 65 old · 279 new · 14 contained in `origin/main` |
| Old-only commits | 4,776 — 4,279 already-on-new-lineage · 99 purge-equivalent · 398 unique-work |
| Old refs by class | 45 unique-work · 19 purge-equivalent · 1 already-on-new-lineage |
| Purged paths / published blob versions | 77 / 132 — **all** hash-matched in `4444J99/limen--private` |
| Checkpoint-only purged versions | 1 (Cline snapshot refs only; never published, so never purged) |
| Old branches with push-capable upstream | 0 (48 quarantined to self-upstream this session) |

The shared checkout's `main` carries **zero** unique work: of its 179 patch-unmatched commits,
99 are purge-equivalent (93 differ only by the rewrite's name/e-mail scrub, 6 touched only purged
paths) and 80 are already on the new lineage (identical change, rewritten parents/ids).

### How a commit is classified (the predicate's evidence order)

1. `patch-id` equal to a new-lineage commit → already-on-new-lineage.
2. Rewritten counterpart = same author time + subject with hex ids masked (filter-repo rewrote
   abbreviated ids inside messages). Identical per-commit diff → already-on-new-lineage; equal
   after the learned whole-token scrub plus per-line in-token core scrubs, purged paths excluded
   → purge-equivalent.
3. No counterpart, change touched only purged paths → purge-equivalent (dropped by the rewrite).
4. Every non-purged path it changed already holds its bytes on the new tip → already-on-new-lineage.
5. Otherwise unique-work.

## Hazards found (ordered by blast radius)

1. **Old-lineage `scripts/capture.sh` on the shared checkout.** The checkout's on-disk copy predates
   #2846 and preserves a dirty/diverged default branch by pushing a commit parented on the old
   `main` head to `origin/capture/main-deferred`. One successful run republishes the entire purged
   lineage. Dormant since 2026-08-21 (last `logs/capture-log.jsonl` write); latent, not active.
2. **`scripts/sync-release.sh` unpark arm** pushes `origin "$CUR"` explicitly when the live checkout is
   parked on a non-default branch — explicit refspecs ignore the upstream quarantine. Today the
   checkout rests on `main`, which the arm refuses.
3. **Explicit pushers** (`scripts/lib/workstream-capsule.sh`, `capture.sh` `push -u`) are unaffected
   by branch config. The quarantine stops *implicit* `git push`/`git pull` only. No lineage-aware
   `pre-push` guard exists (global `core.hooksPath` hook is LFS-only).
4. **Old remote-tracking refs**: none after the fetch — every `refs/remotes/origin/*` is new lineage.

## Ordered reconciliation (each step gated on the predicate staying 0)

0. **Hold** — keep the heartbeat's capture rung off the shared checkout until step 4. Re-run
   `python3 scripts/check-prerewrite-containment.py` before any step; a moved/new old ref fails A
   and must be re-recorded with `--write-ledger` deliberately, never silently.
1. **Lineage pre-push guard** — add a repo-scoped `pre-push` refusal for any pushed commit whose
   ancestry contains an old-lineage commit (boundary descendant not reachable from `origin/main`).
   Owner: domus (the global hooks dir is chezmoi-rendered). Closes hazards 1–3 for every pusher.
2. **Preserve unique work without private custody first** — 7 refs hold unique commits that
   `limen--private` does not reach: `reap/amend-receipt-20261005`, `reap/closeout-audit-20261005`,
   `reap/closeout-correction-20261005`, `reap/closeout-invariant-20261005`,
   `fix/recovery-admission-20261010`, the `refs/limen/continuation-beat/…` receipt ref, and the three
   `refs/cline/checkpoints/*` (which also hold the one checkpoint-only purged-path version). Bundle
   each to custody staging (`git bundle`) and push to `limen--private` under `preserve/prerewrite/*`
   — owner decision (writes to the private sibling).
3. **Port unique work forward, per ref** — for each of the 45 unique-work refs, check its PR state
   (`gh pr list --head <branch> --state all`). Merged → the unique commits are squash residue;
   record and retire. Open/unmerged → cherry-pick the unique commits onto a fresh branch from
   `origin/main` with the scrub applied, open a superseding PR, close the old one. Largest first:
   `docs/heartbeat-natural-receipt-20260924` (107), `work/remote-first-custody-20261005` (73),
   `work/private-custody-completion-20261009` (70), `work/recovery-isolation-20260908` (35),
   `work/recovery-green-20260908` (29), `work/recovery-intent-completion-20260908` (27),
   `refs/tags/archive/pr-2543-detached-…` (26), `work/git-finishline-handoff-20260908` (26).
   Tag `preserve/reap-20261004/vigilia-pii-preserve-life` (18 unique, pre-boundary-adjacent) is a
   privacy-named preservation tag: confirm custody, never port to the public repo.
4. **Realign the shared checkout** — `main` is purge-equivalent with 0 unique commits: after the
   owner confirms, move it to `origin/main` (the beat's `sync-release.sh` divergence valve, or one
   human `git switch`), preserving the 4 dirty tracked files first. This retires hazard 1 at the root.
5. **Retire purge-equivalent refs** — 19 refs (incl. `main` before step 4, the detached
   `av-policy-readback` worktree, 6 retired-worktree refs, `refs/vigilia/main-snapshot`) hold nothing
   unique and are fully in `limen--private`. Retire through the receipt-backed reap rail only after
   #2537 lands, so local copies remain until GitHub stops serving old ids.
6. **Old-lineage worktrees** — `av-directory-receipt-20261010`, `av-policy-readback-20261010`,
   `reap-scope-20261004`, and `/Volumes/Scratch/…/review-checkout` follow their branch's step 3/5
   outcome. `recovery-admission-20261010` is new lineage and locked by a human session: untouched.
7. **Lift the quarantine** — restore each branch's original upstream from the private receipt only
   for refs that end on the new lineage; the predicate's C check keeps every old one quarantined.

## Owner decisions needed

- D1: push the 7 custody-less unique-work refs (and the checkpoint-only purged version) to
  `limen--private` (step 2).
- D2: per-ref port-or-retire for the 45 unique-work refs (step 3) — the predicate cannot decide intent.
- D3: realign the shared checkout's `main` to `origin/main` (step 4).
- D4: retire purge-equivalent refs after #2537 (step 5).

## Predicate

`python3 scripts/check-prerewrite-containment.py` — exit 0 ⟺ (A) every old-lineage ref is recorded
with its live tip and class, (B) every published purged-path blob and every purged path has a hash
match in the local `limen--private` clone and each checkpoint-only version is recorded, (C) no old
branch has a push-capable upstream. The classifier's logic is gated in CI by
`prerewrite-containment-test` on a synthetic two-lineage history; the live run is host-bound.
