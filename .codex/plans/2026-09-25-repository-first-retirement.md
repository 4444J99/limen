# Repository-first retirement

Authorized by the user's explicit implementation instruction on 2026-09-25.
This changes the ordering of the minimal-home-residency execution record, not
its preservation requirements or final five outcome criteria.

## Immediate outcome

Retire every individually eligible inactive authored checkout and clone from
home and Workspace, preserving its existing remote repository and exact work.
Keep Limen, Domus, PORTVS, PRDS, active owners and installed-service dependencies.
Application-owned Git stores and private originals retain their owner policies.
Blocked candidates do not stop independent eligible candidates.

## Execution

1. Reuse the existing inventory, deduplicate actual filesystem/Git identities,
   and record per-candidate ownership and eligibility.
2. Reconcile stale clone-reaper exemptions with the PORTVS control pins and
   active-work/runtime protections. Preserve current unrelated working edits.
3. Verify fresh repository identity, exact remote Git custody, dirty/ignored
   payloads, local metadata, refs/stashes, nested stores and active references.
4. Retire proven copies through the existing journaled removal paths. Publish
   straightforward unique source additively after leak checks and readback;
   retain anything whose required custody cannot yet be established.
5. Record actual removed paths privately, neutral public aggregates, retained
   reasons, and physical free-space deltas. Preserve remote branches and snapshots.

## Acceptance

No proven eligible inactive candidate remains in the measured set. Every retained
candidate has a concrete reason. Source publication is distinct from project
completion; directory removal is distinct from APFS space recovery. The larger
200 GiB target, private recovery and CCE remain open independently.

## Attempt record

- Starting available space: 17,401,548 KiB (16.596 GiB), Data volume.
- Existing recovery checkout retained; unrelated edits in the ARCA file-object
  helper and its tests are outside this attempt.
- Retired 30 linked worktrees across six repositories. All 30 completed
  abandonment receipts were checked against absent paths. No standalone clone,
  remote repository, branch, private original or snapshot was deleted.
- Created 19 additive `preserve/workspace-retirement-20260925/*` branches.
  Secret scans passed for unpublished source before normal Git/LFS pushes;
  every retirement re-read the exact live branch tip. Existing refs remain.
- Removed checkout allocation totaled 3,269,244 KiB (3.118 GiB). The latest
  Data-volume sample was 29,523,112 KiB (28.155 GiB), versus 17,401,548 KiB
  initially: +11.560 GiB observed during the interval. This exceeds the removed
  allocation and cannot all be attributed to this pass; concurrent activity,
  APFS sharing and snapshot accounting remain relevant. No snapshot was removed.
- Worktree administration was archived and byte-checked before detach. Copies
  are also retained in pinned Limen's Git administration custody, with a private
  digest index. These are retained metadata, not reclaimed storage or verified
  remote private custody. Parent-clone reapers now retain this metadata class.
- Fixed the blanket Gitlink veto for linked checkout retirement: empty,
  uninitialized directories hold only the parent commit's preserved pointer;
  populated paths and symlink components still fail closed. The common object
  store remains. Recheck precedes native non-forced `git worktree remove`.
- Reconciled clone default pins with Limen/Domus/PORTVS and all observed PRDS
  components; additional configured pins are additive. The whole `prds-work`
  subtree is protected, including newly named components.
- Validation: 111 focused lifecycle/abandonment/reaper tests passed with the
  explicit recovery source path; after expanded PRDS protection, 72 reaper
  tests passed; the additional retained-metadata test passed separately.
  Changed-file Ruff lint/format and diff hygiene passed. The scoped verifier
  passed 11 of 12 cheap gates but stopped at existing formatting drift in
  `cli/src/limen/repo_lifecycle.py` and `cli/tests/test_dispatch.py`. No full
  scoped pass, deployment or installed-runtime claim is made.

## Remaining candidate dispositions

- The standalone scout inspected 34 authored candidates: 11 dirty, 25 with
  ignored content, eight with multiple worktrees, two submodules and one stash
  (categories overlap). Three clean/ignored-free standalone prospects still
  require complete ref/reflog and local-metadata custody; none was deleted.
- The linked scout inspected 81 saved candidates: 24 had ignored content,
  eight were dirty, three had process references and 17 were stale/unavailable
  at inspection (not disjoint completion accounting). PRDS/UCC support lanes,
  frozen human lanes and application-owned checkouts remain protected.
- The reclaimer's remaining source-only clone candidates still lack full
  administrative/reflog custody. Two clean UCC support lanes are deliberately
  retained for protected PRDS work. The original broad inventory remains
  incomplete; no estate-wide zero-eligible or remote-only claim is made.
- Machine-readable removal receipts and metadata-custody index live in the
  private `repository-first-retirement-20260925` receipt cohort. The existing
  home/Workspace inventory remains the source for the next bounded candidate
  pass; do not restart a full home census.

The repository-first milestone remains partial: real checkout retirement is
complete for this cohort, while most standalone repositories require their
specific preservation step. Full private recovery, automatic residency and
the approximately 200 GiB outcome remain open.
