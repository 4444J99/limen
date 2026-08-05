# Owner and output receipts

## Existing owners to re-probe

- Original serial PR queue: #1029 through #1036.
- #1030, #1033, and #1034 were semantically stale/conflicting at the relay; preserve current-main
  doctrine when reconciling them and never use a mechanical conflict resolution.
- #1049 owns the telemetry `--help` side-effect fix.
- #1050 is preservation-only custody for checkout-guard commit `95b47a63`; do not merge it directly.
- The epoch report/continuation-standard PR owns Study/Insight/Heal/Evolve and the capsule protocol;
  discover its exact number and CI state from the current branch/remote.
- `docs/plans/ci-bounded-shards.md` owns removal of the duplicated long API/CLI/verify path; implement
  it in a focused PR rather than mixing a workflow rewrite into the closeout branch.

These are candidates, not a fixed queue. A newer merge, superseding PR, exact-head failure, owner
change, resource gate, or more valuable underwritten leaf may change the correct order.

## Required outputs

For every completed leaf, record changed paths, exact predicate and result, commit/PR/head SHA, exact
CI state, and remaining scoped risk. For every unfinished leaf, create its owner PR/task/preservation
receipt or named external blocker before switching. Refresh prompt/work lineage and progress from
those receipts; never combine “evidence exists” with “done.”

At a context, value, resource, provider, or logical epoch boundary, run closeout again. Emit a
successor capsule README plus one launch command. Use an isolated worktree when repository-backed and
an owner-native workspace or remote receipt when a Git worktree would be artificial.
