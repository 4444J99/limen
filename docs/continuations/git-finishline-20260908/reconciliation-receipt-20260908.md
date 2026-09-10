# Recovery source reconciliation

The active owner remains #2573 with this correction stacked as #2576. The human's
September 8 correction is part of this acceptance: an intermediate implementation,
pushed branch, or passing shard is not a reason to stop the recovery campaign.
The campaign continues through source reconciliation, substantive review closure,
landing, integration verification, and archive restoration. This receipt records
evidence produced during that work; it does not declare the campaign complete.

## Source lineage

The frozen denominator remains **1,150 candidate records from 44 source objects**.
An authenticated read-only keeper snapshot contains 3,186 canonical tasks. The
reconciliation compares each of the 949 task candidates with every named stash
occurrence, rather than accepting a matching latest version while forgetting an
older request. Source task bodies and the canonical board remain private; the
published manifest contains opaque candidate IDs, field differences, and digests.

Native GitHub review IDs and `in_reply_to_id` links bind all 155 frozen review
records to **117 root findings and 38 replies**. Every native body matches the
frozen extraction. The 38 replies were individually assessed as correction
receipts or acknowledgements of their parent finding, with their body digests
retained in `review-reply-assessments.json`. They are folded into their finding's
candidate set, not discarded.

The follow-up source-delta predicate compares the stash base, staged index,
worktree, and a default-branch ancestor captured before the stash's recorded
creation time. It proves that **801 task candidates are carried projection
observations**, with no recovered request delta, and keeps **148 added or changed
task requests**. A staged-only request or changed execution authority prevents
observation classification. Stash 16 illustrates the original inflation: its old
branch base made 706 already-present default records appear newly requested.

Those 801 records now belong to the existing dated-observation preservation
intent with an explicit role stating that their underlying tasks are not being
declared complete. The manifest therefore has **311 provisional atoms**: 148 task
requests, 28 other source intents, 18 branch/PR lineage intents, and 117 root
review findings. It still covers all **1,150 candidates exactly once**. Remaining
source variants and actual delivery are unresolved.

All 16 historical stash labels are individually reassessed in
`source-reconciliation.json`. A dated observation or board projection remains in
custody and carries its underlying intent references; the word historical does
not discharge its requests. In particular, recurring generic human-gate rows can
change their unblock target between snapshots. Neither that change nor a current
task status supplies completion evidence or new authorization for a login, send,
or deletion.

Reproduce the redacted reconciliation using the existing private snapshots:

```sh
python3 docs/continuations/git-finishline-20260908/reconcile-sources.py --extraction-dir PRIVATE_EXTRACTION_DIRECTORY --canonical-board PRIVATE_CANONICAL_BOARD --native-review-dir PRIVATE_NATIVE_REVIEW_DIRECTORY --output docs/continuations/git-finishline-20260908/source-reconciliation.json --bind-manifest docs/continuations/git-finishline-20260908/completion.json
```

The source comparison never promotes a canonical task's `done` status to verified
delivery. The manifest still fails the delivery acceptance predicate. Six focused
counterexample tests cover missing/edited/cyclic native review evidence, retained
candidate coverage, idempotent reply grouping, source evolution, and false task
completion.

The scoped integration batch against starting head `47131d901` passed all five
implicated cheap gates, including the 17 existing completion counterexamples.
Five further counterexamples cover source-delta classification and lossless
observation grouping. The live completion predicate remains exit 1; the passing
source checks do not replace campaign acceptance.

Reproduce the source-delta classification, then bind it to the working manifest:

```sh
python3 docs/continuations/git-finishline-20260908/reconcile-delta-origin.py --extraction-dir PRIVATE_EXTRACTION_DIRECTORY --canonical-board PRIVATE_CANONICAL_BOARD --generation 6e2b554f76eb0ccdcd5a1b133fabb2c452de9220 --output docs/continuations/git-finishline-20260908/source-delta-origin.json --bind-manifest docs/continuations/git-finishline-20260908/completion.json
```

## Landing and custody

Fresh GitHub observations are bound to the captured default generation
`6e2b554f76eb0ccdcd5a1b133fabb2c452de9220`. Seven merged successors have positive
local ancestry proof at that generation. PR #2531's merge commit is not an
ancestor because its stacked source was squashed into #2528. Every one of its
three changed files is byte-identical at #2531's merge, #2528's merge, and the
captured default. `pr2531-equivalence.json` records all three blob identities.
This proves source preservation; its 43-rung heartbeat runtime predicates still
require their own deployment evidence.

One recovered request has a complete positive delivery binding: the original
Domus #147 failing-CI repair. All 13 completed checks succeeded at its exact head,
GitHub records the merged head, and its merge commit is ancestral to the captured
Domus default generation. The three typed receipts under `deliveries/` retain
those existing checks; no old successful suite was rerun. This is the original
repair's delivery, not a claim that current MCP authentication or fleet health is
complete. Five historical repair PRs have positive landing observations; the
other four lack a complete retained CI predicate here. Limen #400 is closed
unmerged and its historical checks failed, so it is not counted as delivered.

The fresh archive predicate passed using only the three immutable bundles. It
restored **26 stashes, nine deleted tips, and nine original PR heads** in new empty
bare repositories without source alternates. `custody-execution-20260908.json`
binds the predicate source and execution result. No archive was changed, no stash
was applied, and no peer branch or worktree was altered.

The final integration generation has not been selected by this source-only
reconciliation step. The campaign owner must refresh the final manifest once the
existing implementation and dependency owners have landed their verified heads.
