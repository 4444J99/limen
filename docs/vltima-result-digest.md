# VLTIMA Result Digest

Generated: `2026-07-06T15:37:45+00:00`

## Canonical Decision

- Read the results of prior excavations before adding another broad scanner.
- Old material is lineage, not authority. New material is authority, not total memory.
- This digest classifies result claims as `current_doctrine`, `living_lineage`, `dormant_ore`, `superseded_material`, or `quarantined_ghost`.
- It does not read raw prompt bodies, private object-store text, repo source trees, credentials, remotes, or `tasks.yaml`.

## Coverage

- Prior index generated: `2026-07-06T15:37:45+00:00`.
- Prior surfaces: `23`.
- Result claims: `435`.
- Authority mix: `current_doctrine` 422, `dormant_ore` 7, `quarantined_ghost` 5, `superseded_material` 1.
- Freshness mix: `fresh` 428, `unknown` 7.

## Continual Absorption Cadence

- Local AI app chats, projects, plans, tasks, histories, and app-store movement are ongoing corpus input.
- Claude has extra lifecycle phases in this workspace: projects, tasks, plans, file history, usage facets, usage session-meta, and quicken states.
- The cadence absorbs movement as private/redacted evidence first; it does not let every brainstorm become current authority.

| Phase | Cadence | Command | Why |
|---|---|---|---|
| `capture` | session-boundary and daily | `python3 scripts/session-corpus-ledger.py --write --all` | any local AI app movement is signal, even when it is only a brainstorm through a narrow lens |
| `materialize-private` | deliberate daily or before row-level review | `python3 scripts/session-corpus-ledger.py --write --all --materialize` | raw local material is absorbable, but it stays private and out of tracked Git |
| `crosswalk` | after capture, before routing | `python3 scripts/prompt-lifecycle-ledger.py --write --all` | brainstorms become useful when they can be related to current work without becoming authority |
| `classify-pressure` | session end and before delegation | `python3 scripts/session-blockers-ledger.py --write && python3 scripts/session-lifecycle-pressure.py --write` | system clogs must be visible before assigning new work |
| `rank-and-packetize` | after classification | `python3 scripts/session-attack-paths.py --write && python3 scripts/prompt-priority-map.py --write` | old ideas seed lineage; current evidence chooses action order |
| `distill` | after current receipts are fresh | `python3 scripts/corpus-command-center.py --write` | many local brainstorms can be boiled into fewer reusable principles without concatenating everything |

## Current Doctrine

| Surface | Subject | Trust | Evidence | Next |
|---|---|---|---|---|
| `session-attack-paths` | `local_pressure_bytes` | `high` | local_pressure_bytes = 35205579610 | current_doctrine |
| `session-corpus-ledger` | `object_bytes` | `high` | object_bytes = 6686897790 | current_doctrine |
| `capability-substrate-ledger` | `bytes` | `high` | bytes = 2726650513 | current_doctrine |
| `corpus-command-center` | `units` | `high` | units = 664430 | current_doctrine |
| `corpus-command-center` | `units` | `high` | units = 664430 | current_doctrine |
| `corpus-command-center` | `private_object_count` | `high` | private_object_count = 399265 | current_doctrine |
| `corpus-command-center` | `unique_hashes` | `high` | unique_hashes = 399265 | current_doctrine |
| `corpus-command-center` | `clusters` | `high` | clusters = 359628 | current_doctrine |
| `corpus-command-center` | `clusters` | `high` | clusters = 359628 | current_doctrine |
| `session-attack-paths` | `prompt_events` | `high` | prompt_events = 131758 | current_doctrine |
| `prompt-lifecycle-ledger` | `direct` | `high` | direct = 126994 | current_doctrine |
| `prompt-lifecycle-ledger` | `claude-projects` | `high` | claude-projects: 120740 prompt events; newest 2026-07-06T15:28:32+00:00 | current_doctrine |
| `prompt-priority-map` | `prompt_units` | `high` | prompt_units = 78155 | current_doctrine |
| `capability-substrate-ledger` | `scanned_files` | `high` | scanned_files = 67532 | current_doctrine |
| `session-value-review` | `insertions` | `high` | insertions = 38724 | current_doctrine |
| `session-value-review` | `prompt_events_recorded` | `high` | prompt_events_recorded = 22600 | current_doctrine |
| `session-value-review` | `unique_prompt_hash_refs_recorded` | `high` | unique_prompt_hash_refs_recorded = 17794 | current_doctrine |
| `agent-reconstruction-review` | `local-path:limen` | `high` | 1126 sessions; 2320 prompt events; risk 16065 | current_doctrine |
| `prompt-lifecycle-ledger` | `sessions` | `high` | sessions = 15291 | current_doctrine |
| `session-attack-paths` | `prompt_files` | `high` | prompt_files = 15291 | current_doctrine |
| `session-corpus-ledger` | `local_files` | `high` | local_files = 14101 | current_doctrine |
| `session-corpus-ledger` | `object_count` | `high` | object_count = 13845 | current_doctrine |
| `product-ledger` | `products` | `high` | products = 11570 | current_doctrine |
| `prompt-lifecycle-ledger` | `codex-sessions` | `high` | codex-sessions: 7787 prompt events; newest 2026-07-06T15:29:31+00:00 | current_doctrine |
| `prompt-priority-map` | `session_items` | `high` | session_items = 6869 | current_doctrine |
| `session-corpus-ledger` | `claude-projects` | `high` | claude-projects: 6646 files; newest 2026-07-06T15:28:32+00:00 | current_doctrine |
| `session-corpus-ledger` | `claude-file-history` | `high` | claude-file-history: 5059 files; newest 2026-07-05T18:01:34+00:00 | current_doctrine |
| `corpus-command-center` | `sessions_indexed` | `high` | sessions_indexed = 4800 | current_doctrine |
| `session-value-review` | `deletions` | `high` | deletions = 4776 | current_doctrine |
| `agent-code-review-queue` | `sessions` | `high` | sessions = 4375 | current_doctrine |
| `agent-code-review-queue` | `local-path:Archive4T` | `high` | claude / {'done_words': 1799, 'failures': 1283, 'receipts': 1655, 'verification': 807}; risk 4282 | current_doctrine |
| `agent-reconstruction-review` | `unknown` | `high` | 266 sessions; 264 prompt events; risk 4136 | current_doctrine |
| `agent-code-review-queue` | `local-path:rippling-launching-trinket` | `high` | claude / {'done_words': 551, 'failures': 325, 'receipts': 1003, 'verification': 302}; risk 3622 | current_doctrine |
| `agent-code-review-queue` | `code` | `high` | code = 3545 | current_doctrine |
| `agent-code-review-queue` | `docs` | `high` | docs = 3255 | current_doctrine |
| `prompt-lifecycle-ledger` | `flame_scaffold` | `high` | flame_scaffold = 2504 | current_doctrine |
| `agent-reconstruction-review` | `sessions_without_changed_refs` | `high` | sessions_without_changed_refs = 2398 | current_doctrine |
| `prompt-lifecycle-ledger` | `flame_with_task_body` | `high` | flame_with_task_body = 2245 | current_doctrine |
| `agent-code-review-queue` | `local-path:Archive4T` | `high` | claude / {'done_words': 489, 'failures': 251, 'receipts': 1562, 'verification': 201}; risk 2233 | current_doctrine |
| `agent-code-review-queue` | `local-path:fluttering-wandering-wilkes` | `high` | claude / {'done_words': 530, 'failures': 151, 'receipts': 943, 'verification': 209}; risk 2137 | current_doctrine |

## Lineage And Dormant Ore

| Surface | Subject | Trust | Evidence | Next |
|---|---|---|---|---|
| `worktree-preservation` | `.limen-private/session-corpus/lifecycle/worktree-preserve` | `unknown` | directory entries 19; json files 0 | dormant_ore |
| `worktree-preservation` | `worktree-preservation` | `unknown` | worktree-preservation status is current; refresh mode read-only | dormant_ore |
| `session-lifecycle-pressure` | `session-lifecycle-pressure` | `unknown` | session-lifecycle-pressure status is current; refresh mode write-safe-ignored | dormant_ore |
| `hooks-excavation` | `hooks-excavation` | `unknown` | hooks-excavation status is tracked-only; refresh mode manual-doc | dormant_ore |
| `library-preserve` | `library-preserve` | `unknown` | library-preserve status is current; refresh mode manual-only | dormant_ore |
| `offsite-durability-proposal` | `offsite-durability-proposal` | `unknown` | offsite-durability-proposal status is tracked-only; refresh mode manual-doc | dormant_ore |
| `pre-build-excavate` | `pre-build-excavate` | `unknown` | pre-build-excavate status is tracked-only; refresh mode read-only | dormant_ore |

## Superseded Or Quarantined

| Surface | Subject | Trust | Evidence | Next |
|---|---|---|---|---|
| `session-value-review` | `merged_roots` | `low` | merged_roots = 283 | superseded_material |
| `agent-reconstruction-review` | `local-path:temporal-percolating-token` | `low` | 1 sessions; 155 prompt events; risk 158 | quarantined_ghost |
| `product-ledger` | `bountyscope: billing` | `low` | verify / verify / revenue-path | quarantined_ghost |
| `session-lifecycle-blockers` | `auth_credentials` | `low` | auth_credentials = 2 | quarantined_ghost |
| `session-lifecycle-blockers` | `cloud-credential-handles-unconfigured` | `low` | auth_credentials / parked: 6 credential/deploy handles absent; 0 present. No values inspected. | Do not repair inline; open a bounded credential/setup workstream only when a cloud action requires it. |
| `session-lifecycle-blockers` | `credential-codex-auth-sessions` | `low` | auth_credentials / parked: 405 Codex sessions classified as auth/credential work; states: ALIVE 1, CLOSED 364, PARKED 40 | Keep parked unless a future scoped task explicitly requires the account action. |

## Result Mismatches

- No stale/private-only/script-only surface mismatches recorded.

## Next Safe Sequence

1. Refresh prior excavations before any broad VLTIMA estate crawl.
2. Treat current_doctrine claims as action guidance only when the owner repo/path is explicit.
3. Use living_lineage and dormant_ore to recover forgotten ideas, not to override newer architecture.
4. Resolve stale/private-only/script-only result mismatches before trusting those surfaces.
5. Keep quarantined_ghost claims parked unless a bounded human-auth or secret-safe packet owns them.

## Privacy Contract

- Tracked output is redacted and claim-level.
- Private JSON stores the same sanitized claims plus path-level evidence labels.
- A quarantined claim is not rejected; it is parked until a bounded human-safe packet owns it.
- This digest does not authorize deletion, dedupe, branch cleanup, repo movement, archive rewrite, task-board mutation, or credential handling.
