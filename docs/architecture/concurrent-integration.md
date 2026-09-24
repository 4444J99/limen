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


## Cross-repository operations boundary

An operations repository is an adapter, not a second authority. More repositories add
participants to the existing protocol; they do not add independent quota allocators, work
queues, or completion vocabularies.

| Surface | Owns | Must not become |
|---|---|---|
| Limen conduct / TABVLARIVS | Admission, resource leases, fencing generations, authority attenuation, and lifecycle transitions | A product implementation or a second copy of a product backlog |
| `4444J99/ops` | The existing GitHub schedule carrier and its own reports/bookends | A second Jules dispatcher or an estate-wide lease database |
| `4444J99/ops-witness` | Read-only reconciliation and evidence validation | A launcher, merger, quota allocator, or completion-state writer |
| `4444J99/organvm-ci-relay` | Authenticated transport and the existing verification/integration trust boundary | A task selector or independent repair scheduler |
| Participating repository | Its authored implementation, tests, acceptance predicate, and isolated PR | The owner of another repository's product state |

For the Chat-native Jules service, the existing Steward owns new starts; Intake supplies
bounded work and Landing owns delivery verification/integration. These are operation roles,
not extra repositories. Foreground and specialist work must reconcile the same active attempt
before correcting, replacing, or integrating it. A role name, issue comment, or library receipt
is not an atomic lock and does not establish that every caller uses the keeper.

### Minimum contract for another participant

1. Resolve the authoritative numeric repository ID and its current canonical coordinate before
   admission. Preserve the ID as provenance and the canonical coordinate in the existing
   `AuthorityEnvelopeV1` and resource keys. The path parser does not discover transfers or resolve
   historical aliases; an unresolved identity is not a new, independent resource.
2. Reuse `WorkPacketV1`: one stable work key for the acceptance intention, the observed base/head,
   explicit allowed paths and effects, the real executor identity, and the existing bounded
   deadline/spend/retry envelopes. A changed SHA or a retry is not a new intention.
3. Acquire only the resources the operation consumes. Shared reads may coexist. A write conflicts
   with an overlapping read or write on the same repository and base; sibling prefixes do not.
   A whole-root claim is a typed path claim, including its normalized slashless form. A broad
   authority envelope is permission, not by itself an exclusive repository lease.
4. Treat the base segment as part of the isolation domain, not proof of semantic independence.
   Separate branch claims do not prove that two changes to a shared API, migration, generated
   registry, lockfile, or release contract can safely land independently. Declare the shared
   integration resource and use the existing exact-head integration rail.
5. Keep execution occupancy, branch ownership, and landing work in progress separate. A provider's
   positive terminal receipt frees its execution slot, not an unmerged branch or its acceptance
   obligation. Unknown creation results retain their reservation; a timeout is not cancellation.
   Exact-head output acceptance must reject stale generations through the existing keeper.

A GitHub Actions concurrency group coordinates runs within its repository, not the provider
account across repositories. It cannot enforce the account-wide Jules ceiling. Local workflow
persistence serialization, keeper resource leases, and provider capacity accounting solve
separate conflicts and must remain separate.

### Executable boundary regression

`spec/contracts/conduct/resource-overlap-vectors.json` is test data, not another admission
implementation. Both `cli/tests/test_conduct_resource_boundaries.py` and
`web/worker/test/conduct-resource-boundaries.test.js` consume it. The Python tests additionally
exercise real keeper refusal of root claims outside path authority and root-read versus
child-write contention. The thousand-repository fixture proves namespace isolation only;
it is not a thousand-task execution or a production load/concurrency claim.

This contract and its regression do not certify current account coverage, deployed keeper
adoption, credentials, 100 accepted starts per day, or an account-wide maximum of 15 executions.
Those remain the existing `4444J99/limen#2680` acceptance predicates, with credential custody in
`#320`. No new service, timer, queue, production deployment, or permission is created here.
