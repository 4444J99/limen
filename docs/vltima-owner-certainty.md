# VLTIMA Owner Certainty

Generated: `2026-07-06T16:54:15+00:00`

## Canonical Decision

- Every result claim must have an owner before it can become action.
- Missing ownership produces `unowned_ore`, not dispatchable work.
- Superseded and quarantined claims are parked until fresh evidence or a human-safe packet owns them.
- This surface reads sanitized result claims only; it does not read raw private bodies or mutate `tasks.yaml`.

## Coverage

- Source digest generated: `2026-07-06T15:46:22+00:00`.
- Claims classified: `434`.
- Owner status mix: `owned_current` 421, `owned_lineage` 7, `parked` 6.
- Action level mix: `packet_candidate` 421, `parked` 6, `review_only` 7.
- Unowned dispatchable claims: `0`.

## Packet Candidates

| Owner | Surface | Subject | Trust | Next |
|---|---|---|---|---|
| `limen:priority-routing` | `session-attack-paths` | `local_pressure_bytes` | `high` | local_pressure_bytes = 35775126919 |
| `limen:session-corpus` | `session-corpus-ledger` | `object_bytes` | `high` | object_bytes = 6686897790 |
| `limen:capability-substrate` | `capability-substrate-ledger` | `bytes` | `high` | bytes = 2726650513 |
| `limen:session-corpus` | `corpus-command-center` | `units` | `high` | units = 665397 |
| `limen:session-corpus` | `corpus-command-center` | `units` | `high` | units = 665397 |
| `limen:session-corpus` | `corpus-command-center` | `private_object_count` | `high` | private_object_count = 399789 |
| `limen:session-corpus` | `corpus-command-center` | `unique_hashes` | `high` | unique_hashes = 399789 |
| `limen:session-corpus` | `corpus-command-center` | `clusters` | `high` | clusters = 360059 |
| `limen:session-corpus` | `corpus-command-center` | `clusters` | `high` | clusters = 360059 |
| `limen:priority-routing` | `session-attack-paths` | `prompt_events` | `high` | prompt_events = 131758 |
| `limen:prompt-lifecycle` | `prompt-lifecycle-ledger` | `direct` | `high` | direct = 126994 |
| `limen:prompt-lifecycle` | `prompt-lifecycle-ledger` | `claude-projects` | `high` | claude-projects: 120740 prompt events; newest 2026-07-06T15:30:51+00:00 |
| `limen:priority-routing` | `prompt-priority-map` | `prompt_units` | `high` | prompt_units = 78155 |
| `limen:capability-substrate` | `capability-substrate-ledger` | `scanned_files` | `high` | scanned_files = 67532 |
| `limen:priority-routing` | `session-value-review` | `insertions` | `high` | insertions = 38724 |
| `limen:priority-routing` | `session-value-review` | `prompt_events_recorded` | `high` | prompt_events_recorded = 22600 |
| `limen:priority-routing` | `session-value-review` | `unique_prompt_hash_refs_recorded` | `high` | unique_prompt_hash_refs_recorded = 17794 |
| `limen:session-corpus` | `agent-reconstruction-review` | `.` | `high` | 1126 sessions; 2320 prompt events; risk 16065 |
| `limen:prompt-lifecycle` | `prompt-lifecycle-ledger` | `sessions` | `high` | sessions = 15291 |
| `limen:priority-routing` | `session-attack-paths` | `prompt_files` | `high` | prompt_files = 15291 |
| `limen:session-corpus` | `session-corpus-ledger` | `local_files` | `high` | local_files = 14099 |
| `limen:session-corpus` | `session-corpus-ledger` | `object_count` | `high` | object_count = 13845 |
| `limen:product-surface` | `product-ledger` | `products` | `high` | products = 11570 |
| `limen:prompt-lifecycle` | `prompt-lifecycle-ledger` | `codex-sessions` | `high` | codex-sessions: 7787 prompt events; newest 2026-07-06T15:38:37+00:00 |
| `limen:priority-routing` | `prompt-priority-map` | `session_items` | `high` | session_items = 6869 |
| `limen:session-corpus` | `session-corpus-ledger` | `claude-projects` | `high` | claude-projects: 6646 files; newest 2026-07-06T15:30:51+00:00 |
| `limen:session-corpus` | `session-corpus-ledger` | `claude-file-history` | `high` | claude-file-history: 5059 files; newest 2026-07-05T18:01:34+00:00 |
| `limen:session-corpus` | `corpus-command-center` | `sessions_indexed` | `high` | sessions_indexed = 4800 |
| `limen:priority-routing` | `session-value-review` | `deletions` | `high` | deletions = 4776 |
| `limen:session-corpus` | `agent-code-review-queue` | `sessions` | `high` | sessions = 4375 |
| `limen:session-corpus` | `agent-code-review-queue` | `/Volumes/Archive4T` | `high` | claude / {'done_words': 1799, 'failures': 1283, 'receipts': 1655, 'verification': 807}; risk 4282 |
| `limen:session-corpus` | `agent-reconstruction-review` | `unknown` | `high` | 266 sessions; 264 prompt events; risk 4136 |
| `limen:session-corpus` | `agent-code-review-queue` | `~/Workspace/limen/.claude/worktrees/rippling-launching-trinket` | `high` | claude / {'done_words': 551, 'failures': 325, 'receipts': 1003, 'verification': 302}; risk 3622 |
| `limen:session-corpus` | `agent-code-review-queue` | `code` | `high` | code = 3545 |
| `limen:session-corpus` | `agent-code-review-queue` | `docs` | `high` | docs = 3255 |
| `limen:prompt-lifecycle` | `prompt-lifecycle-ledger` | `flame_scaffold` | `high` | flame_scaffold = 2504 |
| `limen:session-corpus` | `agent-reconstruction-review` | `sessions_without_changed_refs` | `high` | sessions_without_changed_refs = 2398 |
| `limen:prompt-lifecycle` | `prompt-lifecycle-ledger` | `flame_with_task_body` | `high` | flame_with_task_body = 2245 |
| `limen:session-corpus` | `agent-code-review-queue` | `/Volumes/Archive4T` | `high` | claude / {'done_words': 489, 'failures': 251, 'receipts': 1562, 'verification': 201}; risk 2233 |
| `limen:session-corpus` | `agent-code-review-queue` | `~/Workspace/limen/.claude/worktrees/fluttering-wandering-wilkes` | `high` | claude / {'done_words': 530, 'failures': 151, 'receipts': 943, 'verification': 209}; risk 2137 |

## Parked Or Review-Only

| Status | Owner | Surface | Subject | Reason |
|---|---|---|---|---|
| `owned_lineage` | `limen:worktree-preservation` | `worktree-preservation` | `.limen-private/session-corpus/lifecycle/worktree-preserve` | dormant_ore / lane:worktree-preservation |
| `owned_lineage` | `limen:worktree-preservation` | `worktree-preservation` | `worktree-preservation` | dormant_ore / lane:worktree-preservation |
| `owned_lineage` | `limen:priority-routing` | `session-lifecycle-pressure` | `session-lifecycle-pressure` | dormant_ore / lane:priority-routing |
| `owned_lineage` | `limen:hooks-orientation` | `hooks-excavation` | `hooks-excavation` | dormant_ore / lane:hooks-orientation |
| `owned_lineage` | `limen:archive-durability` | `library-preserve` | `library-preserve` | dormant_ore / lane:archive-durability |
| `owned_lineage` | `limen:archive-durability` | `offsite-durability-proposal` | `offsite-durability-proposal` | dormant_ore / lane:archive-durability |
| `owned_lineage` | `limen:repo-surfaces` | `pre-build-excavate` | `pre-build-excavate` | dormant_ore / lane:repo-surfaces |
| `parked` | `limen:priority-routing` | `session-value-review` | `merged_roots` | superseded_material / lane:priority-routing |
| `parked` | `limen:session-corpus` | `agent-reconstruction-review` | `.claude/worktrees/temporal-percolating-token` | quarantined_ghost / lane:session-corpus |
| `parked` | `limen:product-surface` | `product-ledger` | `bountyscope: billing` | quarantined_ghost / lane:product-surface |
| `parked` | `limen:priority-routing` | `session-lifecycle-blockers` | `auth_credentials` | quarantined_ghost / lane:priority-routing |
| `parked` | `limen:priority-routing` | `session-lifecycle-blockers` | `cloud-credential-handles-unconfigured` | quarantined_ghost / lane:priority-routing |
| `parked` | `limen:priority-routing` | `session-lifecycle-blockers` | `credential-codex-auth-sessions` | quarantined_ghost / lane:priority-routing |

## Contract

- `packet_candidate` means candidate packetization only; it does not enqueue or dispatch.
- Any future enqueue step must preserve owner, verification command, receipt target, and privacy class.
