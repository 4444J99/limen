# Collaboration Operations Platform — Alpha-to-Omega plan

## Objective

Create `organvm-iii-ergon/collaboration-operations-platform` as the private, owner-controlled
system of record for every current and future collaboration, then implement the complete suite from
repository genesis through a repeatable Omega fixed point. The platform must centralize records
without centralizing access: every record belongs to an explicit owner partition, no collaborator
inherits access to another partition, and production-like development uses synthetic fixtures only.

## Durable plan set

- Product and technical architecture:
  `docs/continuations/collaboration-operations-platform-alpha-omega-20260803/architecture.md`
- Executable phase and packet graph:
  `docs/continuations/collaboration-operations-platform-alpha-omega-20260803/execution-dag.yaml`
- Acceptance and Omega contract:
  `docs/continuations/collaboration-operations-platform-alpha-omega-20260803/acceptance.md`
- Agy conductor prompt:
  `docs/continuations/collaboration-operations-platform-alpha-omega-20260803/agy-autonomous-intent.md`
- Plan predicate:
  `python3 scripts/check-collaboration-operations-plan.py`

## Current state

The Limen boundary contract and non-mutating genesis gate are green. The target repository is still
declared `prepared_not_created`. The direct human instruction on 2026-08-03 authorizes the private
repository genesis and the full non-destructive implementation program. Destructive data actions,
credential movement, paid spend, collaborator invitations, public release, production deployment,
DNS, and live client-data import retain their own gates.

## Execution order

1. Record the discharged genesis lever and its closeable graph receipt.
2. Launch a fresh 30-day, human-protected Agy workstream from an exact pushed Limen head.
3. Agy reads the plan set, runs its clock and broker-capability probes, and submits the root packet.
4. Agy mints the private target repository only after the fresh absence and four genesis gates pass.
5. Agy materializes the 24 Greek phases as bounded child packets, reserving every child before any
   native or remote fanout. Independent packets run concurrently only in separate worktrees.
6. Each packet lands through a topic branch and exact-head predicate receipt. The founding genesis
   push is the sole direct-main exception; all later target-repository changes use PRs.
7. At every boundary Agy derives `continue`, `switch`, `wait_relay`, `settled`, or `invalid` from
   live predicates. It never asks the operator to choose ordinary engineering mechanics.
8. The program settles only when `scripts/omega.sh` passes twice on an unchanged exact head and all
   discovered residuals have durable owner receipts.

## Completion predicate

Planning is complete when the Limen plan predicate passes. Product completion is deliberately a
different predicate, implemented during the target repository's Alpha/Gamma phases:

```bash
./scripts/omega.sh
```

That command must compose the immutable phase receipts rather than rerun already-green heavy gates.
