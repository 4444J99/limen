# Collaboration Operations Platform genesis

The reversible Limen genesis is prepared for a universal private collaboration space: one place for
you to capture, store, and retrieve important information across every current and future
collaboration and client. The proposed repository has **not** been created, nobody has been invited,
and no collaborator project has been mutated.

## Durable boundary

[`institutio/collaboration-operations/platform.yaml`](../../../institutio/collaboration-operations/platform.yaml)
is the universal private collaboration-records owner map and seed contract. It keeps collaborator
projects as external sources rather than platform worktrees. David, Maddie, and Ari are current
boundary examples, not the limit of the platform's scope:

- David: `persona:david` / `project:victoroff-os` at `4444J99/victoroff-os`, mostly complete;
  issues #2, #3, #17, #27 and `RW-001` through `RW-010` are external references only.
- Maddie: the build lane remains closed and the existing grant remains push-only.
- Ari: HOSPES transcripts remain vault-class; custody movement waits for the transcript vault split.

Studio code may be reused. Important collaboration and client records may be stored centrally in
private owner partitions, but one client's content, strategy, transcripts, credentials, and live
fixtures may never be exposed to another client. The platform itself is declared
`operation_private`, audience `self`, with no collaborator grant rows and synthetic fixtures only.

TABVLARIVS conducted root: `run-0aafe3f811510d8c3dcd50f7179b239b`. The compatibility owner-task
upsert returned `LIMEN-400` / receipt `busy-2633e1664daccf9fea307eaa`, then hit its existing hard-loop
limit; do not retry that compatibility task. The conducted root and this tracked contract own the
genesis lane.

## Executable successor

The human authorized private repository genesis and bounded autonomous execution on 2026-08-03.
`L-COLLABORATION-OPERATIONS-PLATFORM-GENESIS` is discharged by closed issue #1790. The complete
successor contract is indexed by
[`collaboration-operations-platform-alpha-omega-20260803`](../collaboration-operations-platform-alpha-omega-20260803/agy-autonomous-intent.md):
24 ordered phases, 72 bounded packets, packet predicates and receipts, a root `omega` predicate, and
an Agy conductor that derives native teammate lanes from live broker capabilities.

After the successor capsule has been rendered, launch it with one command:

```bash
cd "/Users/4jp/Workspace/limen/.worktrees/collaboration-operations-platform-alpha-omega-20260803" && bash scripts/run-workstream-kickstart.sh .limen-workstream/kickstart.sh
```

The command is idempotent: when the workstream is already live, it returns success without starting
a duplicate provider. Agy must re-probe live remote, host, broker, usage, and custody state before
each packet boundary; the plan never pins a model or fabricates a future green state.

Repository creation is authorized only inside that plan's private, synthetic-fixture boundary.
Invites, transfers, destructive personal-data operations, credentials, paid spend, public sends,
DNS, production deployment, and live client or transcript import retain their explicit human gates.
