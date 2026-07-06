# VLTIMA Prior Excavations

Generated: `2026-07-06T14:03:54+00:00`

## Canonical Decision

- Before a new estate-wide VLTIMA scan, excavate and reconcile the prior excavations.
- This register is metadata-only: it reads paths, mtimes, JSON keys, collection counts, and tracked generated timestamps.
- It does not read raw prompt bodies, private object-store text, skill bodies, plugin manifest contents, or credential values.
- Tracked output is redacted; exact path-level evidence and private JSON summaries live in the ignored private index.

## Coverage

- Prior surfaces: `23`.
- Scripts present: `21`.
- Outputs present: tracked `27`, private `20`, logs `3`.
- Discovered extra artifacts: `150`.
- Lanes: `archive-durability` 3, `capability-substrate` 1, `hooks-orientation` 1, `priority-routing` 5, `product-surface` 1, `prompt-lifecycle` 3, `repo-surfaces` 2, `session-corpus` 5, `worktree-preservation` 2.
- Statuses: `current` 18, `private-only` 1, `script-only` 1, `stale` 1, `tracked-only` 2.
- Refresh modes: `dry-run-first` 4, `manual-doc` 2, `manual-only` 2, `read-only` 2, `write-safe-ignored` 1, `write-safe-redacted` 12.

## Refresh Order

1. `session-corpus-ledger` - `write-safe-redacted` - python3 scripts/session-corpus-ledger.py --write
2. `prompt-lifecycle-ledger` - `write-safe-redacted` - python3 scripts/prompt-lifecycle-ledger.py --write --all
3. `session-lifecycle-blockers` - `write-safe-redacted` - python3 scripts/session-blockers-ledger.py --write
4. `worktree-preservation` - `read-only` - python3 scripts/worktree-debt.py --json
5. `session-lifecycle-pressure` - `write-safe-ignored` - python3 scripts/session-lifecycle-pressure.py --write
6. `session-attack-paths` - `write-safe-redacted` - python3 scripts/session-attack-paths.py --write
7. `prompt-priority-map` - `write-safe-redacted` - python3 scripts/prompt-priority-map.py --write
8. `corpus-command-center` - `write-safe-redacted` - python3 scripts/corpus-command-center.py --write
9. `capability-substrate-ledger` - `write-safe-redacted` - python3 scripts/capability-substrate-ledger.py --write
10. `repo-surface-ledger` - `dry-run-first` - python3 scripts/repo-surface-ledger.py --max-depth 8 --dry-run
11. `product-ledger` - `write-safe-redacted` - python3 scripts/product-ledger.py --write
12. `substrate-ledger` - `write-safe-redacted` - python3 scripts/substrate-ledger.py --write
13. `prompt-batch-review-ledger` - `write-safe-redacted` - python3 scripts/prompt-batch-review-ledger.py --write
14. `prompt-packet-ledger` - `write-safe-redacted` - python3 scripts/prompt-packet-ledger.py --write
15. `agent-session-full-stack-review` - `dry-run-first` - python3 scripts/agent-session-full-stack-review.py --write
16. `agent-reconstruction-review` - `dry-run-first` - python3 scripts/agent-reconstruction-review.py --write
17. `agent-code-review-queue` - `dry-run-first` - python3 scripts/agent-code-review-queue.py --write
18. `session-value-review` - `write-safe-redacted` - python3 scripts/session-value-review.py --write
19. `antigravity-scratch-bridge` - `manual-only` - python3 scripts/antigravity-scratch-bridge.py --help
20. `hooks-excavation` - `manual-doc` - read docs/hooks-excavation-and-plan.md
21. `offsite-durability-proposal` - `manual-doc` - read docs/OFFSITE-DURABILITY-PROPOSAL-2026-06-19.md
22. `library-preserve` - `manual-only` - python3 scripts/library-preserve.py
23. `pre-build-excavate` - `read-only` - scripts/pre-build-excavate.sh <owner/repo> [keyword ...]

## Prior Excavation Surfaces

| Surface | Lane | Status | Outputs | Refresh | Command |
|---|---|---|---:|---|---|
| `session-corpus-ledger` | `session-corpus` | `current` | 2 | `write-safe-redacted` | `python3 scripts/session-corpus-ledger.py --write` |
| `prompt-lifecycle-ledger` | `prompt-lifecycle` | `current` | 2 | `write-safe-redacted` | `python3 scripts/prompt-lifecycle-ledger.py --write --all` |
| `session-lifecycle-blockers` | `priority-routing` | `current` | 2 | `write-safe-redacted` | `python3 scripts/session-blockers-ledger.py --write` |
| `session-lifecycle-pressure` | `priority-routing` | `current` | 2 | `write-safe-ignored` | `python3 scripts/session-lifecycle-pressure.py --write` |
| `session-attack-paths` | `priority-routing` | `current` | 2 | `write-safe-redacted` | `python3 scripts/session-attack-paths.py --write` |
| `prompt-priority-map` | `priority-routing` | `current` | 2 | `write-safe-redacted` | `python3 scripts/prompt-priority-map.py --write` |
| `corpus-command-center` | `session-corpus` | `current` | 4 | `write-safe-redacted` | `python3 scripts/corpus-command-center.py --write` |
| `repo-surface-ledger` | `repo-surfaces` | `current` | 2 | `dry-run-first` | `python3 scripts/repo-surface-ledger.py --max-depth 8 --dry-run` |
| `capability-substrate-ledger` | `capability-substrate` | `current` | 2 | `write-safe-redacted` | `python3 scripts/capability-substrate-ledger.py --write` |
| `product-ledger` | `product-surface` | `current` | 2 | `write-safe-redacted` | `python3 scripts/product-ledger.py --write` |
| `substrate-ledger` | `archive-durability` | `private-only` | 1 | `write-safe-redacted` | `python3 scripts/substrate-ledger.py --write` |
| `worktree-preservation` | `worktree-preservation` | `current` | 5 | `read-only` | `python3 scripts/worktree-debt.py --json` |
| `prompt-batch-review-ledger` | `prompt-lifecycle` | `current` | 3 | `write-safe-redacted` | `python3 scripts/prompt-batch-review-ledger.py --write` |
| `prompt-packet-ledger` | `prompt-lifecycle` | `current` | 3 | `write-safe-redacted` | `python3 scripts/prompt-packet-ledger.py --write` |
| `agent-session-full-stack-review` | `session-corpus` | `current` | 2 | `dry-run-first` | `python3 scripts/agent-session-full-stack-review.py --write` |
| `agent-reconstruction-review` | `session-corpus` | `stale` | 2 | `dry-run-first` | `python3 scripts/agent-reconstruction-review.py --write` |
| `agent-code-review-queue` | `session-corpus` | `current` | 3 | `dry-run-first` | `python3 scripts/agent-code-review-queue.py --write` |
| `session-value-review` | `priority-routing` | `current` | 2 | `write-safe-redacted` | `python3 scripts/session-value-review.py --write` |
| `antigravity-scratch-bridge` | `worktree-preservation` | `current` | 4 | `manual-only` | `python3 scripts/antigravity-scratch-bridge.py --help` |
| `hooks-excavation` | `hooks-orientation` | `tracked-only` | 1 | `manual-doc` | `read docs/hooks-excavation-and-plan.md` |
| `offsite-durability-proposal` | `archive-durability` | `tracked-only` | 1 | `manual-doc` | `read docs/OFFSITE-DURABILITY-PROPOSAL-2026-06-19.md` |
| `library-preserve` | `archive-durability` | `current` | 1 | `manual-only` | `python3 scripts/library-preserve.py` |
| `pre-build-excavate` | `repo-surfaces` | `script-only` | 0 | `read-only` | `scripts/pre-build-excavate.sh <owner/repo> [keyword ...]` |

## Mismatches To Reconcile

| Surface | Lane | Status | Reason |
|---|---|---|---|
| `substrate-ledger` | `archive-durability` | `private-only` | missing or asymmetric outputs |
| `agent-reconstruction-review` | `session-corpus` | `stale` | missing or asymmetric outputs |
| `pre-build-excavate` | `repo-surfaces` | `script-only` | missing or asymmetric outputs |

## Extra Artifacts

These matched excavation naming patterns but are not part of the canonical surface list yet.

| Artifact | Lane | Kind |
|---|---|---|
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T022811Z-organvm-session-meta` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T022931Z-organvm-session-meta` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T023603Z-session-meta-no-prompt` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T024219Z-session-meta-2` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T024423Z-peer-audited--behavioral-blockchain` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T024627Z-sovereign-systems--elevate-align` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T024745Z-public-record-data-scrapper` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T024925Z-dot-github--theoria` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T025108Z-limen` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T025302Z-mirror-mirror` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T025421Z-organvm-i-theoria-github` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T025535Z-a-i-chat--exporter` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T025734Z-universal-mail--automation` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T030234Z-bountyscope-test-coverage` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T030747Z-edgarflash` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T030905Z-bountyscope` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T030959Z-vulnpulse` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T031111Z-domus-genoma` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T031541Z-organvm-i-theoria-mesh` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T032235Z-rules-system-bound` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T033729Z-organvm-engine` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T033837Z-conversation-corpus-engine` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T033946Z-4444J99` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T034048Z-anon-hookup-now` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T034150Z-hokage-chess` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T034251Z-studium-generale` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T034537Z-session-meta-4` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035207Z-atomic-substrata` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035244Z-adaptive-personal-syllabus` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035327Z-brainstorm-20260423` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035405Z-system-system--system--monad` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035441Z-vigiles-aeternae--corpus-mythicum` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035515Z-media-ark-33` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035547Z-organvm-ontologia` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035631Z-sovereign--ground` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035706Z-github` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035739Z-writelens` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035840Z-organvm` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T035938Z-organvm-i-theoria` | `session-corpus` | `private` |
| `.limen-private/session-corpus/lifecycle/agy-scratch-preserve/20260706T040023Z-organvm-vi-koinonia` | `session-corpus` | `private` |
| `...` | `truncated` | `110 more in private index` |

## Contract

- This register does not authorize deletion, dedupe, branch cleanup, repo movement, archive rewrite, or task-board mutation.
- `Archive4T` and other mounted volumes are read-only inputs unless a separate preservation command explicitly owns a copy operation.
- A stale or partial prior excavation is a routing signal, not a global blocker.
- The next VLTIMA estate census must reuse these surfaces before adding a new scanner.
