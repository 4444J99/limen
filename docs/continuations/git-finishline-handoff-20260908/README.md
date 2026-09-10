# Git recovery handoff — 2026-09-08

This prepared, human-protected capsule continues [PR2573](https://github.com/4444J99/limen/pull/2573)
from published correction `4b76be3ef799d3a486fdefc14470f4ae6bef1055`. Preparation and
identity verification succeeded; no agent has been launched. Retain this checkout as
the intentional handoff home. Its four-hour runway starts on launch, not preparation.

The production batch at `1fb83ecd33381e4bb135dbb9ef957a77389e8bc4` passed all **32 cheap
gates**. Host admission rejected its heavy wave for swap pressure (scoped exit 75).
The later capsule-only change passed four differential cheap gates; production and
heavy-shard inputs stayed unchanged. This is an admission hold, not a merge receipt.

Continue only the previously denied heavy shards when genuine machine-wide host
admission permits them. Preserve unchanged green shard receipts. Changed inputs
invalidate only their implicated shards; do not replay production, activate schedulers,
or poll CI to manufacture completion. Keep the finite runway and retained authority
boundaries in [workstream.json](workstream.json).

The denied gate IDs are `worker-check`, `pytest-cli`, `pytest-api`, and `web-build`.
Resolve their commands from `gates.yaml` and execute them through the existing bounded
runner, admission context, and serialization lock. The last three are registry-marked
serialized gates; retain those locks and their deadlines. Do not invoke the full
unchanged cheap wave again. The launch command below is the next action for the owner.

The [combined predicate receipt](combined-scoped.json) records its actual exit code
and private log digest. The [final state snapshot](final-state.json) binds custody,
PR dispositions, and landing receipts to the observed repository generation.
The [broker receipts](run-receipts.json) retain the complete reported deltas. The
governor and aggregate runs ended with explicit partial releases because their
initial packet path envelopes omitted some direct-session changes; they are not
successful broker receipts. All session leases were released. Derive the complete
path envelope before reserving any continuation children.

The inherited [custody and correction owner](../git-finishline-20260908/README.md),
[execution receipt](../git-finishline-20260908/receipt.json),
[stash ledger](../git-finishline-20260908/stash-custody.json),
[deleted-branch ledger](../git-finishline-20260908/branch-custody.json),
[original-PR ledger](../git-finishline-20260908/pr-custody.json), and
[review dispositions](../git-finishline-20260908/review-dispositions.json) remain authoritative.
They preserve 26 stashes, nine deleted tips, and nine original PR heads; the earlier
claim of ten original PRs was corrected against both original snapshots. Private
archives remain private. PR2553 keeps its independently recorded delivery gates.

PR2573 may merge only after its exact published head has all implicated local predicates
satisfied, including the denied heavy shards under host admission. Verify its head still
matches the expected candidate before the repository fast-lane squash merge with
`--match-head-commit`; a moved head requires assessment of its changed inputs. This
pushed plan branch is owned by PR2573 and needs no separate PR.

Launch once from this handoff worktree's repository root:

```sh
bash .limen-workstream/kickstart.sh
```
