# Concurrent Integration

Multiple sessions are a supported operating condition. The integration rail serializes mutations
to `main`; it does not serialize thought, editing, review, or exact-head verification.

## Contract

1. Every mutation session works in one isolated worktree and topic branch. Action-level host
   admission allows concurrent writers in distinct worktrees and exactly one writer per canonical
   worktree scope. The live `main` checkout remains the read/control plane and may be dirty with
   daemon-owned board state; source writes there fail `shared-checkout-write`.
2. PR-head verification is immutable. A successful check receipt belongs to one exact
   `headRefOid`; moving `main` does not authorize changing that head or repeating successful
   children.
3. Current-base verification belongs to GitHub's merge queue. The queue constructs a
   `merge_group` from latest `main`, the exact PR head, and any predecessors. The always-on
   `pr-gate` runs every scoped gate implicated by that synthetic composition.
4. `BEHIND` means queueable only when the live repository reports an active queue. An absent,
   unreadable, or partially configured queue fails closed. `DIRTY` always remains a real conflict.
5. Agent and provider sessions never wait on PR state. They may submit one exact head once with
   `scripts/merge-drain.py --repo OWNER/NAME --pr NUMBER --expected-head SHA`, then return control.
   `QUEUED` proves durable GitHub ownership only; it is never promoted into a `MERGED` receipt.
   `scripts/await-pr.sh` is a fail-closed compatibility circuit breaker for stale instructions.
6. `scripts/merge-drain.py` applies the same predicate immediately before each effect. Its one-shot
   mode never polls or retries; its recurring beat mode owns later observation and applies bounded
   work without keeping an agent/provider session alive.
7. Tabularius never pushes `main`. It keeps the sealed board dirty locally, publishes only
   `tasks.yaml` to the stable `tabularius/board-projection` branch with normal fast-forward commits,
   and opens one exact-head PR. Newer local state coalesces while that PR is in flight. A stale
   competing publisher loses at the remote ref without a force push.
8. The default-branch ruleset combines `merge_queue` with a zero-approval `pull_request` rule and
   no bypass actors. That remote predicate rejects every direct `main` write; automation workflows
   use the same board PR publisher and cannot create a hidden side door.

## Verification split

| Receipt | Identity | Work |
|---|---|---|
| PR head | exact `headRefOid` | ordinary PR CI and review |
| Integration | exact `merge_group` SHA and base SHA | every scoped gate implicated by the combined diff |
| Main | resulting merge SHA | normal push/deploy receipts |

This split removes the starvation loop without weakening the silent-revert guard: current `main` is
still present in the tested tree, but it is composed by the queue instead of copied into every
author branch.

## Operator commands

```bash
scripts/merge-policy.sh <PR> --expected-head <SHA>
scripts/merge-drain.py --repo OWNER/NAME --pr <PR> --expected-head <SHA>
```

Queue settings are declared and applied idempotently by `scripts/setup-rulesets.py`. The rollout
order is strict: land the `merge_group` workflow first, apply the queue settings second, then prove
the live queue before treating any stale PR as queueable.
