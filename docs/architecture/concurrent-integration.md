# Concurrent Integration

Multiple sessions are a supported operating condition. Integration serializes mutations to
`main`; it does not serialize thought, editing, review, or exact-head verification. A registry
chooses the smallest sound rail for each repository.

## Contract

1. Every mutation session works in one isolated worktree and topic branch. The live `main`
   checkout remains the read/control plane; source writes there fail `shared-checkout-write`.
2. Verification is immutable. A successful local `scripts/verify-scoped.sh` receipt belongs to one
   clean `headRefOid`; moving `main` does not authorize changing that head or repeating successful
   children.
3. A registry-declared **single-owner fast lane** has no inter-party admission problem. After one
   exact-tree local verification batch and one push, merge immediately through the PR rail with
   `gh pr merge NUMBER --repo OWNER/NAME --squash --match-head-commit SHA`. Remote CI and automated
   review remain advisory fix-forward evidence. A deploy-triggering diff includes its implicated
   local build/deploy predicate in the same batch.
4. A shared-writer repository may instead use GitHub's merge queue. GitHub composes a synthetic
   `merge_group` from latest `main`, the immutable PR head, and queued predecessors; its declared
   integration gate verifies that composition. Submit it once with `scripts/merge-drain.py`.
5. Agent and provider sessions never wait on PR state. `scripts/await-pr.sh` is a fail-closed
   compatibility circuit breaker. There is no sleep/recheck, polling loop, auto-merge babysitting,
   or automatic retry in either rail.
6. `BEHIND` never causes a repeated merge/rebase/full-suite cycle. The single-owner rail relies on
   GitHub's atomic exact-head mergeability check; the shared-writer rail uses a positively proven
   queue. A real `DIRTY` conflict is repaired once as a changed head.
7. Tabularius never pushes `main`. It publishes `tasks.yaml` through its stable
   `tabularius/board-projection` branch with normal fast-forward commits and one exact-head PR.
8. The default-branch rule remains PR-only, squash-only, no-bypass, no force push, and no deletion.
   A single-owner declaration removes remote status and bot-thread admission; it does not create a
   direct-`main` or admin side door.

## Verification split

| Rail | Admission receipt | Remote evidence | Merge binding |
|---|---|---|---|
| Single owner | exact local tree + scoped implicated predicates | advisory CI/review, fix-forward | PR number + `--match-head-commit SHA` |
| Shared writer | exact PR head plus declared integration gate | required queue/check receipt | one `merge-drain.py` submission |
| Main | repository-qualified merge SHA | push/deploy receipts | default-branch presence |

## Operator commands

```bash
# Registry-declared single-owner fast lane
scripts/verify-scoped.sh
gh pr merge <PR> --repo OWNER/NAME --squash --match-head-commit <SHA>

# Shared-writer rail
scripts/merge-policy.sh <PR> --expected-head <SHA>
scripts/merge-drain.py --repo OWNER/NAME --pr <PR> --expected-head <SHA>
```

`scripts/setup-rulesets.py` derives the rail from `institutio/github/estate.yaml` and verifies the
live GitHub state after applying it.
