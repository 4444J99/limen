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

## Continuation checkpoint, 2026-09-25

- A fresh Limen worktree-reclaimer check examined 52 targets and proposed only
  the two clean UCC support worktrees already retained for protected PRDS work.
  They remain retained under that protection decision; no formal lease/pin
  evidence is asserted, and no reclaimer mutation was applied.
- The clone-specific reaper found zero eligible clones in the 75-copy Workspace
  scope. A bounded home-root dry run (`/Users/4jp`, depth 3) found zero eligible
  clones among 26 examined. These are scoped checks, not proof that hidden or
  deeper application stores have a completed owner policy.
- Cross-checking exposed a classifier mismatch: the linked-worktree reclaimer
  could propose removing standalone clones with only local-ref proof, while the
  clone owner must also account for reflogs, nested stores and fresh remote
  reconciliation. The general reclaimer now leaves ordinary standalone clones
  to that owner-specific classifier; only exact restored-custody receipts may
  authorize a clone through the recovery path. The three Limen candidates were
  not deleted.
- The debt reporter initially overstated this set as 19 reapable. It did not
  reject 16 ignored-payload worktrees and trusted one stale remote-tracking tip.
  Reporting now uses the live `ls-remote` advertisement for reachability and
  rejects ignored payloads; strict debt inventory and the reclaimer now agree
  on exactly the same two UCC/PRDS candidates.
- Focused lifecycle/debt/candidate tests pass: 126. Both reaper passes were
  dry-run only. No branch, private original, snapshot, or UCC lane was removed.
- Available Data-volume space at the latest measurement was approximately
  27.5 GiB; the ~200 GiB outcome remains unmet. Full home/Workspace coverage is
  still incomplete, including the recorded cloud-trash timeout and application
  stores requiring explicit owners.

### Cache-owner follow-through, 2026-09-25

- Re-ran the allowlisted owner-aware cache classifier at 16:05Z. It found
  three candidates totaling 572,928 KiB, but retained UV (11.1 GiB), Playwright
  (1.6 GiB), and capabilities cache (208.2 MiB) due to live process references;
  pre-commit remained blocked on repository custody. Owner-managed runtime and
  Codex recovery stores were not considered eligible.
- Used Homebrew's own `cleanup --dry-run --prune=all` before mutation. It
  proposed 524.2 MB of obsolete downloads/API metadata and stale logs; the
  operation completed and Homebrew reported that amount freed. Installed
  `codex`, VS Code, Kimi, UV, and Node remained available (Homebrew versions
  and the `codex`, `code`, and `kimi` executables verified).
- Immediate Data-volume free-space measurement moved from 28,458,220 KiB to
  28,478,412 KiB (+19.7 MiB). This is a measured net change, not an attribution
  of the full apparent reclaim; APFS sharing and other concurrent activity
  remain. The post-Homebrew cleanup check initially reported 59.8 MiB across
  three eligible candidates.
- Candidate-level repository checks did not authorize pruning the four
  standalone clones inspected: their consumers, local-only history, or dirty
  and ignored generated state remain unresolved. This reinforces that the
  repository-first retirement milestone remains partial, not remote-only.

### Deeper hydration-cache retirement, 2026-09-25

- Expanded the clone-reaper dry-run from its default depth-three boundary to
  depth six. It found seven additional candidates under a collaboration
  hydration cache (0.57 GiB apparent), all classified as clean pushed mirrors.
- Confirmed the hydration owner reconstructs these repository sources on
  demand with a shallow `gh repo clone` when no normal local checkout exists;
  the adjacent vault, receipts, and encrypted-object state were not targeted.
- The immediate apply rechecked all candidates. Six remained eligible and
  were reaped (about 0.56 GiB apparent); the seventh changed classification
  and was retained. A subsequent depth-six dry-run found zero eligible clones.
- The clone reaper observed approximately zero net GiB free-space change; the
  separate Data-volume sample moved from 28,449,892 KiB to 28,424,112 KiB
  (-25,780 KiB). Concurrent writes/APFS mean this is not a reclaim estimate.
  Disk remains below the 50 GiB admission threshold. No private vault data,
  branches, or remote repositories were removed.

### Remaining npm cache, 2026-09-25

- The owner-aware check had correctly identified a separate idle cache at
  `~/.cache/npm`; the standard npm cache command did not target it. Verified
  that exact cache through `npm --cache <path> cache verify` (154 entries,
  17,581,523 bytes), then cleared it using the same explicit cache argument
  and verified zero entries remained.
- A fresh allowlist check now reports 42.0 MiB total across three candidates;
  UV, Playwright, and capabilities remain active-process blocked, and
  pre-commit remains blocked on Git custody. Homebrew's current dry-run had no
  further cleanup output.
- Data-volume free space sampled 28,424,112 KiB before this npm-cache removal
  and 28,413,368 KiB after (-10,744 KiB). Concurrent writes/APFS effects mean
  no physical recovery is attributed to the 17.7 MB cache deletion.

### Final idle tool-cache pass, 2026-09-25

- The later exact-plan check found 43,040 KiB across only the npm and
  Homebrew cache allowlist entries. Applied that unchanged plan through the
  tool's expected-plan-hash gate; the subsequent fresh check found zero
  eligible tool-cache candidates. Active UV, Playwright, and capabilities
  caches, repository-custody-blocked pre-commit stores, and Domus/Codex-owned
  paths remained excluded.
- The generated-cache checker found one 88,018,944-byte `node_modules` tree
  under protected `prds-work/prds-engine`; retained it. No protected project
  environment was removed.
- Data-volume free space changed from 27,640,772 KiB at the tool-cache check
  to 27,625,604 KiB afterward (-15,168 KiB). This is a net observation, not
  attributed reclaim; the 43,040 KiB apparent cache retirement is directory
  accounting only. The 50 GiB admission threshold remains unmet.

### Deep root reconciliation, 2026-09-25

- A fresh depth-six Workspace dry run proposed one 0.01 GiB collaboration
  hydration clone. Its owner reconstructs repository sources from GitHub on
  demand. The apply-time recheck saw a live SSH process with its current
  directory inside that clone and reaped nothing. The candidate remains
  protected until that process exits and a new live check confirms eligibility.
- The matching depth-six home-root dry run exposed seven installed-plugin and
  marketplace source clones totaling 0.23 GiB apparent. Native Copilot
  marketplace and installed-plugin state confirms that the largest is an
  application-owned source, not an idle generic cache. No owner-specific
  eviction/reconstruction transaction is yet proven, so all seven remain.
  Other home clones remain individually blocked by active tasks/processes,
  dirty or ignored state, linked worktrees, submodules, local-only objects,
  or metadata-custody requirements; this is not a claim that every retained
  clone has completed per-path adjudication.
- Data-volume free space measured 27,593,692 KiB after these read-only checks.
  Concurrent use continues to dominate small apparent candidate totals; no
  additional storage reclaim is attributed.

### Ciphertext-only second-device replica, 2026-09-25

- HORREVM's cloud rail remains parked on its explicit egress-consent gate. The
  existing private-vault verifier passed for four encrypted objects and its
  neutral, public-safe manifest. A fresh GitHub API read of live `main` showed
  the exact same five Git blob IDs and sizes as the current local tree.
- Made an additive copy of only those four ciphertext objects and the neutral
  manifest onto a separately attached physical storage device. The volume is
  APFS and unencrypted; the replica directory is mode 700 and each copied file
  mode 600. No plaintext, source filenames, or sensitive path index was copied.
- Flushed before publishing the staged directory, then compared the completed
  destination tree byte-for-byte with the verified local vault (`diff -qr`,
  exit 0). The complete replica is 35,382 bytes across five files. This proves
  an independent physical ciphertext copy for this vault cohort only; it does
  not prove key recovery, decryption/restoration, coverage of other private
  domains, or authorization to retire any source. The unencrypted volume must
  never receive plaintext or sensitive names/indexes.

### Concurrent residency acceptance, 2026-09-25

- Added a race test for two different session IDs entering `repo.ensure` at
  once against one temporary remote. It verifies one canonical bare store,
  two distinct isolated worktrees and lease records, then repeats one session
  to verify idempotency. This exercises the real filesystem lock and Git
  worktree plumbing; only the GitHub clone transport is replaced by a local
  test fixture.
- `python3 -m pytest -q cli/tests/test_repo_lifecycle.py`: 11 passed.
  Pinned Ruff 0.15.8 lint and format checks passed for the changed test.
  This is local contract evidence, not a live-GitHub concurrent canary or
  proof that final-release canonical stores are retired.

### Orphan-object guard and candidate preservation, 2026-09-25

- A clean public-repository hydration clone contained one local dependency
  commit. Gitleaks scanned that exact commit (one commit, 371 changed bytes)
  with no findings. Pushed it additively to a new `preserve/local-only-*`
  branch, without moving `main`; a fresh GitHub ref readback returned the exact
  commit `849ca7ad1d83ccc9698e54a212dba5bf050f67d3`.
- Before considering clone retirement, a deeper read-only object audit found
  three stale remote-tracking refs, two commits reachable only through those
  stale refs, and 187 objects unreachable from current refs (including 59
  commits and 11 blobs). The clone remains retained. No fetch-prune or delete
  was run on it, and no storage reclaim is claimed.
- Fixed the clone reaper's evidence classifier to reject unreachable/dangling
  objects during reporting, after live fetch/prune, and at the final mutation
  edge. Added regressions for a ref-less blob and a deleted remote branch whose
  only local reference is stale tracking state. This prevents fetch-prune from
  converting recoverable history into unexamined garbage.
- `python3 -m pytest -q cli/tests/test_reap_clones.py`: 75 passed. Pinned Ruff
  0.15.8 lint and format checks passed. The full 75-test suite passed again
  after formatting.
- A fresh depth-six Workspace dry run with the new classifier examined 144
  candidates and found zero eligible copies; two were retained specifically
  for unreachable-object evidence. A subsequent liveness probe found a live
  SSH process with its cwd inside one of those repositories, adding an active
  owner gate. No copy was removed and no storage reclaim is attributed.

### Bounded continuation, 2026-09-25

- Re-ran the Workspace clone reaper after the liveness changes. The depth-six
  apply pass performed fresh checks and reaped zero of 144 candidates. A
  depth-seven dry run discovered eight more paths (152 total); none was
  eligible. Current blockers include live process references, active tasks,
  protected roots, dirty/ignored data, linked worktrees, missing administrative
  metadata custody, and unique/unreachable Git objects. No uncertain copy was
  modified.
- The home-root depth-three dry run remained at zero eligible among 26
  candidates. The broader depth-six home-root attempt exceeded the interactive
  execution bound without a result and was not treated as a completed scan.
  The existing resumable whole-home inventory remains the bounded source of
  deeper candidate identities; it has no traversal frontier but remains
  incomplete because one cloud-backed area was unmeasured.
- A read-only summary of that private inventory distinguishes 254 Git
  checkouts and 241 Git stores from application/dependency source, plus 23
  non-checkout bare-store candidates. It also records 2,431 Codex temporary
  empty Git initialization shells (one `HEAD` file each; 51,051 aggregate
  bytes in the earlier owner-scoped shape check). These are not repositories
  with remote content and offer negligible storage recovery; no shell or
  application-owned store was removed in this pass.
- Available Data-volume space was approximately 21 GiB at the fresh reaper
  checks. This remains below the 50 GiB admission threshold; the 200 GiB
  completion target is unmet. Directory cleanup is not being represented as
  physical recovery.

### Owner-scoped home and runtime pass, 2026-09-25

- Reused the existing 54,580-object private home/Workspace inventory rather
  than starting another root census. Its traversal frontier is empty, but one
  cloud-backed area is still unmeasured, so coverage is not complete.
- The deeper Workspace Git checkouts not covered by the depth-seven reaper
  pass are confined to Domus/Limen-owned locations. Of 37 under OpenCode's
  runtime data owner, all current filesystem identities still match inventory;
  all have valid HEADs, refs, and remotes, 36 are clean, and one has dirty or
  untracked state. A fresh open-file probe found one live OpenCode process with
  six references under that owner root. All are retained as application
  recovery state. Two Domus UV archive checkouts also match inventory identity;
  no direct open-file references were observed, but no per-object reconstruction
  receipt authorizes their retirement.
- The 37 Neovim plugin directories exactly match Domus's 37 active lockfile
  entries. All four installed tmux plugin directories are explicitly named in
  the active Domus configuration. These owner-managed sources have no stale
  checkout identified by those owner manifests, so none was removed.
- The fresh tool-cache plan identified four allowlisted, inactive, regenerable
  cache roots. Applied only that exact plan hash after its full identity check
  and immediately repeated process-reference checks: four roots removed,
  675,196 KiB apparent (659.4 MiB), and zero eligible residual candidates.
  The cache tool's receipt contains exact paths; it remains local/ignored,
  owner-readable only (mode 0600), with FileVault enabled. No sensitive paths
  were copied into this public plan.
- A fresh Data-volume `df` sample after the apply reported 26,717,136 KiB
  available (about 25.48 GiB). The prior sample was about 21 GiB, but concurrent
  writes and APFS mean the difference is not attributed to cache removal.
  Free space is still below the 50 GiB admission threshold and far below the
  approximately 200 GiB completion criterion.
