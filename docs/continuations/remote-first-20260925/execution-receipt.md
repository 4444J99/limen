# First remote-first execution receipt

Date: 2026-09-25. Owner: https://github.com/4444J99/limen/issues/2739.

## Published and verified

- Created the program and seven new epics; reused capacity issue #685. Fresh
  GitHub sub-issue readback returned all eight intended owner issues, including
  PORTVS #14 and Domus #397. The issue index is in `issues.json`.
- Created #2745 under E1. Its source-access evidence is recorded in
  `hosted-source-receipt.md` and remotely at
  https://github.com/4444J99/limen/issues/2745#issuecomment-5839890917.
  The hosted execution predates this attempt; it was inspected and reused,
  not launched or rerun here. It covers candidate `cd287e5893b70e59f52894f58e7ce978030ac8b4`
  in the identified PR merge tree, not later revisions.
- TABVLARIVS accepted the open task `REMOTE-FIRST-20260925` at
  `2026-09-25T21:32:16.976Z` through its authenticated compatibility relay.
  Its scope is publication of program ownership, not completion of the estate
  or authorization to dispatch all epics. The returned owner and receipt target
  are #2739. No local `tasks.yaml` edit, task claim, or autonomous child was made.
- A concurrent session committed and published `a95553b63552e273dc14bd347533abea1726cc56`
  while this documentation was being prepared. Its ARCA changes were not edited
  or staged by this session. The older hosted test receipt does not certify it.

## Storage and retention

Fresh Data-volume `df -k` reported 33,058,380 KiB available (31.53 GiB).
This is a current observation, not reclaim attributable to this attempt. The
approximately 200 GiB target and 50 GiB new-worktree admission floor remain unmet.

No checkout, private original, snapshot, branch, application state, or cache was
removed by this attempt. The existing recovery checkout is retained because it
has active users and is part of a still-running source/custody lane. Native agent
state also still depends on the control source root. No new worktree was created.

Earlier source receipts describe 30 linked worktrees and six hydration clones
retired; those are historical cohort results, not new work or complete coverage.
The latest recorded candidate pass had zero eligible clones. Do not rerun the
same full-root census without changed eligibility evidence.

## Next owned actions

1. E1: preserve the retained candidate's unique/unreachable Git objects and
   administrative state through the appropriate custody owner, then verify
   reconstruction. Its existing local source receipt is in the repository-first
   retirement record; publish no sensitive object paths or payloads.
2. E2: reclassify only that changed candidate with fresh owner/process/ref checks;
   retire only if every custody and active-owner condition passes.
3. E3: detach native state through Domus-owned generators and client canaries;
   do not move an active client's state or stop protected sessions.
4. Cloud implementation dispatch remains distinct from hosted CI source access.
   Existing provider deadline restrictions still apply. No provider activation,
   paid capacity, or unrestricted backlog dispatch is authorized by this receipt.

All original end-state criteria remain open. Issue publication, task intake and
the source-access canary are completed deliverables within this first attempt;
none is a substitute for full custody, retirement or autonomous implementation.

## Continued execution: encrypted Git-store custody

The user explicitly resumed this program. This continuation reused the existing
recovery checkout and targeted the retained candidate from the earlier object
audit, without another whole-root scan or new worktree. Fresh checks observed a
clean checkout, no ignored files, one worktree and no open-file references. Git
reported 187 unreachable objects (59 commits, 117 trees, 11 blobs); none was
pruned, deleted or exposed as plaintext in a public repository.

Captured 326 Git-store files with the existing per-file encrypted-object tool.
The capture includes objects and administrative state, not just current branch
tips. Its encrypted catalog and 326 payload assets total 1,574,759 bytes. A
GitHub HTTP 500 interrupted the first publish after 304 verified assets. Fresh
remote inventory found 320 uploaded assets and no catalog. One bounded resume
verified their server SHA-256/size metadata, uploaded/read back the remaining
six objects, then published and read back the catalog last. A final remote
listing confirmed exactly 327 assets, one catalog and the stated byte count.

A separately encrypted source-binding record carries immutable repository ID,
filesystem identities, source location, exact HEAD/ref observations, custody
references and retention reasons. Its two assets total 1,801 bytes and passed
full remote readback. Public receipts contain only neutral IDs and aggregates;
the machine-readable checkpoint is `git-store-custody-receipt.json`.

### Capture safety repair

Inspection found that the file-object inventory relied on `os.walk`'s default
silent handling of traversal errors. Added a fail-closed error callback, so an
unreadable/disappearing source cannot become a successful empty or partial
catalog. Six regression cases cover permission, missing-directory and other
I/O errors during both initial inventory and the final source recheck. Prior
catalog and source remain unchanged; unpublished partial ciphertext is removed.
The two touched Python files were also normalized with Ruff's formatter.

Verification: all 17 file-object tests passed, all eight implicated scoped gates
passed, and targeted Ruff lint/format checks passed. The live Git-store capture
preceded this repair; the provenance capture used the repaired implementation.
No installed-runtime or merged-source claim follows from these local checks.

### Precisely scoped recovery gate

The initial restore used the legacy default GPG home and failed with
`No secret key`. Domus's actual environment template declares the XDG data
keyring instead. A metadata-only check there found the matching secret subkey;
the single corrected restore attempt then failed with
`Inappropriate ioctl for device`. Thus key absence is not the current diagnosis:
native unlock is unavailable to this noninteractive session. No key was exported,
rotated, copied, logged or requested in chat. The native unlock request was sent
separately to the operator; E5 owns the subsequent real restore and independent
recovery proof. Domus #397 owns correct native-consumer environment propagation.

No independent custody drive was mounted. The source clone, encrypted local
capture and original private material remain retained. Even a successful native
unlock alone will not authorize retirement: exact reconstruction, independent
key/replica proof and unverified ACL/ownership/timestamp coverage remain separate
gates. The reaper's existing unreachable-object guard was not weakened.

Data-volume free space sampled 30,808,580 KiB (29.38 GiB). No storage was reclaimed
by this continuation, and concurrent free-space movement is not attributed to
the small encrypted capture. Next action: after native unlock, restore this exact
catalog into the existing private custody owner, verify all source bytes and Git
objects, and retain the clone until the complete applicable retirement gate passes.

### Source parity completed independently of native unlock

The subsequent exact Git graph check found that most previously unreachable
commits already had live GitHub ancestry. Two commits needed durable branch
anchors, and a third was retained only by a pull-request ref. Inspected the
changes (CI and dependency lockfile only) and passed redacted secret scans,
including merge-parent diffs. Pushed three additive `preserve/recovery-*`
branches. A detached tree outside every commit graph was preserved unchanged
under a `preserve/tree-*` tag. Its child objects already belonged to the examined
commit graphs. No synthetic commit, default-branch update, force push, pruning
or branch deletion was performed.

Fresh remote readback matched all four exact object IDs. Enumerated all locally
present objects with `git cat-file --batch-all-objects`, intersected current live
branch/tag tips with locally available objects, and traversed their closure with
`git rev-list --objects --no-object-names`. Repeated the remote advertisement and
local object enumeration to reject drift. Result: **640 local objects, 244 live
anchors, zero objects outside the verified remote graph**, with both observations
stable. The first all-object pass exposed the PR-only commit; the final pass
succeeded after its additive preservation branch was published. Git identifies
this as a promisor repository: the result covers all *locally present* objects,
not missing promisor content or a newly reconstructed full clone.

The exact object-set digest and counts are in `git-store-custody-receipt.json`.
The encrypted provenance resolves the candidate's repository and source path.
The encrypted Git-store snapshot remains a pre-publication point-in-time copy;
the new remote preservation refs do not turn it into a later metadata snapshot.
This is one verified source-parity cohort, not whole-estate parity, a cloud coding
run, or authority to remove the clone's administrative/private state. Retention
and independent restoration requirements remain unchanged.

## Continued implementation: isolated release and metadata-safe detach

Owner: E4, https://github.com/4444J99/limen/issues/2741. Source commit:
`d86d57237433ebe3151b0ec2cc8ec9a8113f7f4f` on the existing recovery PR #2718.
This is implementation in the existing lifecycle, not a new cleanup framework.

- Released eligible worktrees can now retire while sibling session leases stay
  active. Active lease records and checkouts are not modified, and their shared
  canonical store remains retained. Invalid lease shapes and states fail closed.
- Native detach previously removed the worktree's administrative directory.
  The lifecycle now inventories that directory, verifies a replica, and moves
  the original into the retained common store before Git removes the replica.
  Original file/directory identities, including native attributes held by those
  identities, remain local; this is containment, not encrypted remote custody.
  Reflog old/new object IDs and worktree-local refs receive additive local
  preservation refs, so ordinary Git garbage collection cannot silently strand
  their unique history after the worktree registration disappears.
- Inventory is bounded and rejects locks, symlinks, special entries and
  in-progress Git operations. Hidden tracked edits, ignored payloads, HEAD,
  owner state and metadata are rechecked before the non-forced detach.
- A write-ahead receipt permits recovery from the original/replica rename gap
  only with matching path, store, inode and inventory evidence and an idle
  owner. A completed detach followed by an interrupted lease checkpoint is
  recovered from that lease's exact completed receipt. Missing directories,
  stale receipts or changed retained metadata alone cannot establish completion.
  Recovered checkpoint counts are separate from newly retired checkout counts.

### Verification and deployment boundary

Final focused command:
`python3 -m pytest cli/tests/test_repo_lifecycle.py cli/tests/test_worktree_abandonment.py cli/tests/test_reap_clones.py -q`
passed **137 tests**. It exercises real Git operations in isolated test fixtures,
including active siblings, unique reflog/ref history, failed/corrupt copies,
source drift, interrupted rename and lease writes, late ignored payloads,
hidden tracked edits, malformed leases and parent-store retention.

Scoped verification against `abdb7d71a79dd80e46d6d7e8576e892cc43d859e`
passed **10 of 11** gates, including syntax, type checking, formatting, test
hygiene and effector ownership. The full result remains **failed** because
repository-wide Ruff lint reports inherited findings and exceeds its bounded
output allowance. Comparing the four changed files against the exact base with
Ruff JSON found **zero new findings**; the abandonment module has the same four
pre-existing broad-exception findings at both revisions. No lint rule, capability
or hook was disabled. E4 owns integration acceptance, including this red gate;
the next predicate is the same scoped command after its actual findings change.

A live, read-only probe of the configured managed cache found no residency
registry and zero repository records. This is not coverage of all resident
repositories and does not prove the installed producers use the new lifecycle.
No installed runtime was changed and no user checkout was retired in this
attempt. The source checkout remains active and retained. Secret scanning and
the effective Git LFS pre-push hook remain enabled.

### Program acceptance checkpoint

The denominator is the five original end-state criteria, not commits or tests:

| Required end state | Verified complete | Current evidence boundary |
| --- | --- | --- |
| Both roots fully classified | No | Prior census still has unmeasured coverage |
| Every resident authored repo leased or pinned | No | Complete producer/resident reconciliation unverified |
| Ordinary cycles return residency to baseline | No | Source tests pass; installed end-to-end cycle unverified |
| Registered private material has custody and authorized retrieval | No | Partial ciphertext custody is not restoration or retrieval proof |
| Approximately 200 GiB actual internal free space | No | Latest sample: 25,781,552 KiB, approximately 24.59 GiB |

Thus **0/5 end-state criteria are verified complete**; implementation effort
has no measured percentage. The latest free-space sample is an observation,
not reclaim attributable to this attempt. Local metadata containment earns no
reclaimed-storage credit. No private original, protected PRDS checkout, internal
snapshot, canonical store or user branch was deleted. E4's remaining installed
cycle and final-store custody gates remain open in the existing program.
