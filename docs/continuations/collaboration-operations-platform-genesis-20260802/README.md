# Collaboration Operations Platform genesis

The reversible Limen genesis is prepared. The proposed repository has **not** been created, nobody
has been invited, and no collaborator project has been mutated.

## Durable boundary

[`institutio/collaboration-operations/platform.yaml`](../../../institutio/collaboration-operations/platform.yaml)
is the project-neutral owner map and seed contract. It keeps collaborator projects as external
sources rather than platform worktrees:

- David: `persona:david` / `project:victoroff-os` at `4444J99/victoroff-os`, mostly complete;
  issues #2, #3, #17, #27 and `RW-001` through `RW-010` are external references only.
- Maddie: the build lane remains closed and the existing grant remains push-only.
- Ari: HOSPES transcripts remain vault-class; custody movement waits for the transcript vault split.

Studio code may be reused. Client content, strategy, transcripts, credentials, and live fixtures may
not cross owner lanes. The platform itself is declared `operation_private`, audience `self`, with no
collaborator grant rows and synthetic fixtures only.

TABVLARIVS conducted root: `run-0aafe3f811510d8c3dcd50f7179b239b`. The compatibility owner-task
upsert returned `LIMEN-400` / receipt `busy-2633e1664daccf9fea307eaa`, then hit its existing hard-loop
limit; do not retry that compatibility task. The conducted root and this tracked contract own the
genesis lane.

## Executable successor

Launch a fresh successor session in the same identity-bound capsule with the compatibility wrapper
(this capsule predates the generator hydration fix):

```bash
cd "/Users/4jp/Workspace/limen/.worktrees/collaboration-operations-platform-genesis-20260802"
bash scripts/run-workstream-kickstart.sh .limen-workstream/kickstart.sh
```

Then re-probe reality and run the boundary plus the non-mutating genesis gate:

```bash
cd "/Users/4jp/Workspace/limen/.worktrees/collaboration-operations-platform-genesis-20260802"
python3 scripts/check-collaboration-operations.py
python3 scripts/repo-genesis.py \
  --name collaboration-operations-platform \
  --org organvm-iii-ergon \
  --class operation_private \
  --evidence docs/continuations/collaboration-operations-platform-genesis-20260802/workstream.json \
  --seed-extract institutio/collaboration-operations/platform.yaml \
  --why 'project-neutral collaboration operations platform; no collaborator grants; synthetic fixtures only' \
  --dry-run
```

Removing `--dry-run` is not authorized by this receipt. Repository creation requires the tracked
`L-COLLABORATION-OPERATIONS-PLATFORM-GENESIS` his-hand lever, its needs-human issue receipt, a fresh
remote absence probe, and a successor packet that also records the new ERGON shelf assignment. The
same boundary continues to prohibit invites, transfers, deployment, DNS, payments, email, and
credential movement without their own applicable receipts.
