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

## Continued implementation: verification repair and ARCA review remediation

Attempt started 2026-09-26 00:41:59 UTC. Existing owners remain E1/E5 for custody
and E4 for integration; umbrella #2739 and recovery PR #2718 are unchanged.
Source commit `d4c7ee7f6fc5cdd58dd3f6fec9901d8be44b8779` was committed with
the effective secret-scan hook, pushed with the effective LFS hook, and verified
as PR #2718's live head through the authenticated GitHub connector.

### Correction to the prior verification diagnosis

The preceding claim of inherited repository-wide lint findings was incorrect.
The host Python package metadata reports Ruff 0.15.8, but its module launcher
executes the Homebrew Ruff 0.16.9 binary. The pin checker inspected metadata only.
It now runs the exact interpreter's `-m ruff --version`, validates the output,
and fails closed on mismatch, launch failure, or its ten-second deadline.
Eleven regression cases are wired through the existing hermetic test runner.
The existing Limen virtual environment runs the declared Ruff 0.15.8: whole-estate
lint passes and all 723 files pass formatting. No package-manager binary, lint
rule, capability, or authentication configuration was changed.

Hosted PR-gate run 36197586536 at the preceding head failed because the real
extended-attribute test used a macOS attribute name on Linux. The fixture now
uses Linux's unprivileged `user.` namespace there and preserves the real native
capture/restore assertions on macOS. The 17 object tests plus 11 pin tests pass
locally; a local macOS pass is not a hosted Linux receipt.

Live GitHub metadata also confirms PR #2709 merged on 2026-09-24 at
`a77aa0375b10091bb5c74bbdc063a899e569b013`; its old prose is not current state.
That merge does not prove this recovery PR or its installed runtime.

### ARCA safety changes and review evidence

- The update cap counts the deduplicated union of pending history and changed
  index blobs, excluding remote-reachable objects. Missing tracking refs count
  all reachable HEAD blobs as pending rather than zero.
- Backup and explicit rotation share per-store staging and bounded commits.
  Rotation validates its cap before mutation, follows the manifest's current
  repository, verifies private destination visibility, and refuses unpublished
  old-generation state before changing its branch.
- Rejected store manifest entries are removed without losing generation
  metadata. Repeated refusal, including unborn HEAD, remains incomplete.
  Matching source hashes no longer suppress resealing dirty local payloads.
  Oversized source stores fail explicitly instead of returning success.
- Successful pushes require live exact-HEAD readback and establish the tracking
  reference even after an empty clone or rotation. Status uses live remote
  evidence; the freshness sensor consumes custody state rather than trusting
  recent push time alone. Pre-existing staged changes remain untouched.
- The existing outbound-writer registry now records two shared push sites and
  two read-only live-reference probes. No writer or predicate was disabled.

`bash scripts/tests/arca-generation.test.sh` passes **41 checks** using isolated
temporary repositories. Cases cover unchanged retries after rejected first
pushes, pending-plus-staged limits, inherited ciphertext isolation, deleted
remote branches, unborn-HEAD refusal, dirty payload repair, and rotation
retention. The twelve corresponding ARCA shell review threads were answered
with exact-commit evidence and resolved; other review findings remain open.

The final scoped batch selected **30 gates: 29 passed, 1 failed**. Its failure is
`positioning-foundry-technical-readiness-public-live`: the local GitHub CLI is
unauthenticated and the predicate reports `live GitHub observation failed closed`.
The authenticated connector and ordinary Git push both work. This is not a
green scoped receipt, and no merge or runtime deployment is claimed. The source
changes are retained in the existing draft PR, not installed into scheduled jobs.

### Remaining boundary and checkout disposition

PR #2718 remains draft. Still-open review work includes dispatch retry lease
identity, producer-bound encryption evidence for generic release payloads, and
dry-run outbound-effector matching. Catalog-last release publication was already
implemented: all 20 publisher tests passed again, and that separate review thread
was answered and resolved without new source changes. E1/E5 retain independent
key-restoration and replica acceptance; E4 retains installed lifecycle proof;
E6 retains authorized private retrieval. Whole-estate classification and the
200 GiB capacity outcome are not complete.

At 2026-09-26 01:01 UTC, Data-volume availability measured **40,575,540 KiB
(38.70 GiB)**. This observation is not reclaim attributable to this attempt.
No user checkout, private original, canonical store, PRDS material, or internal
snapshot was removed. The existing source worktree remains active and retained.
There are still **0/5 fully verified original end-state criteria**; source-level
progress is not a defensible overall completion percentage.

### Final same-attempt ARCA hook correction

The dry-run effector finding was subsequently repaired in this same custody
workstream: the three ARCA release/preservation command patterns require the
mutating `--apply` form within the same command segment. Default local plans
remain available without network receipts; publisher-internal preflight remains
unchanged and still runs before outbound mutation. The guard matrix passes,
including three local-plan cases, apply before other options, and a separate
command containing `--apply`. All **7 scoped gates** for this correction pass.
The prior 29/30 broader result remains failed; this narrower result does not
supersede it. Only dispatch retry identity and payload-encryption provenance
remain unresolved among the reviewed source findings. No installed hooks or
scheduled runtime were changed. The source checkout is retained for those owners.
