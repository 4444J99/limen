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
candidate set, not discarded. The working manifest therefore has 1,112 atoms and
still covers all 1,150 candidates exactly once. This is still a provisional
useful-intent count: source variants and actual delivery remain unresolved.

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
The live completion predicate returned exit 1 with 44 sources, 1,112 provisional
atoms, all 1,150 candidates retained, and zero verified delivered atoms. Its
failure remains the campaign's acceptance result; the passing source checks do
not replace it.

## Landing and custody

Fresh GitHub observations are bound to the captured default generation
`6e2b554f76eb0ccdcd5a1b133fabb2c452de9220`. Seven merged successors have positive
local ancestry proof at that generation. PR #2531's merge commit is not an
ancestor because its stacked source was squashed into #2528. Every one of its
three changed files is byte-identical at #2531's merge, #2528's merge, and the
captured default. `pr2531-equivalence.json` records all three blob identities.
This proves source preservation; its 43-rung heartbeat runtime predicates still
require their own deployment evidence.

The fresh archive predicate passed using only the three immutable bundles. It
restored **26 stashes, nine deleted tips, and nine original PR heads** in new empty
bare repositories without source alternates. `custody-execution-20260908.json`
binds the predicate source and execution result. No archive was changed, no stash
was applied, and no peer branch or worktree was altered.

The final integration generation has not been selected by this source-only
reconciliation step. The campaign owner must refresh the final manifest once the
existing implementation and dependency owners have landed their verified heads.
