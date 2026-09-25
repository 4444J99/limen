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
