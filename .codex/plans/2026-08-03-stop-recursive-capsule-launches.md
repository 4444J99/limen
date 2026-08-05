# Stop recursive capsule launches

## Objective

Make a workstream capsule's generated `kickstart.sh` a host-shell bootstrap that executes once.
The provider it launches must inherit a capsule-, worktree-, and session-bound admission marker,
continue from the generated modules, and no-op successfully if it invokes the bootstrap command.

## Implementation

- Validate the linked worktree Git directory, common Git directory, and configured remote before
  conduct or runway admission. Run bounded fetch and status preflights before the first admission
  mutation, leave the existing unstarted contract and receipt bytes exact on failure, and diagnose
  permission or network failures as launch-environment errors.
- Add a validated successor interface. `--predecessor-receipt` establishes committed path-free
  lineage; default `--runway-mode inherit` preserves admitted timing exactly, while explicit
  `--runway-mode renew --runway <duration>` creates a distinct unstarted contract without changing
  predecessor bytes.
- Derive workstream launch adapters and model-flag support from the canonical provider registry so
  arbitrary provider renames and catalog additions, removals, or reordering cannot change behavior.
- Mark every admitted provider process with `LIMEN_WORKSTREAM_PROVIDER_ACTIVE=1` plus exact capsule,
  worktree, and session bindings.
- Put the generated recursion guard before lock acquisition and every Git, receipt, conduct, or
  provider action.
- Give providers an explicit admitted-session continuation preamble and label the generated README
  launch command as host-shell-only.
- Preserve `workspace-write`, the no-`--add-dir` boundary, capsule identity validation, and
  receipt-only publication.

## Predicate

Focused workstream tests must prove one host fetch, one receipt-only publication, and one provider;
a provider self-invocation must produce no Git, receipt, lock, or child-process effect. Separate
fixtures must fail before provider launch for unwritable linked Git metadata and an unavailable
remote. Fetch and status failure fixtures must also prove contract and receipt bytes remain exact.
Registry fixtures must cover provider rename plus catalog addition, removal, and reorder. Successor
fixtures must prove exact inherited timing, explicit fresh renewal, and path-free immutable lineage.
The repository's scoped verifier must pass for the exact implementation head.

## Rollout

Publish the Limen change through a topic-branch PR. Leave the existing Danse capsule byte-identical,
generate a successor with the original absolute deadline and durable receipt lineage, and launch it
once from the host shell so its admitted provider continues issue #7 directly.
