# Prompt Batch Review Ledger

Generated: `2026-06-28T02:52:39+00:00`

## Canonical Decision

- Review batches are promoted by owner receipt, not by exposing raw prompt/session text.
- `owner-recorded`, `non-source-recorded`, and `superseded-recorded` batches have durable evidence but can still require an owner decision before cleanup or delegation.
- `needs-*` batches are the next work queue; they require private review, packetization, remote proof, or owner routing before dispatch.
- `parked-secret` remains parked unless a scoped account/setup task explicitly activates it.

## Coverage

- Priority batches read: `153`.
- Review batches recorded: `153`.
- Batches with durable owner/non-source/supersession evidence: `3`.
- Open review batches: `133`.
- Parked secret batches: `17`.
- Prompt events represented: `92795`.
- Preservation receipts available: `6`.
- Status mix: `needs-private-review` 125, `parked-secret` 17, `needs-packetization` 3, `needs-remote-proof` 3, `owner-recorded` 2, `needs-owner-route` 2, `non-source-recorded` 1.
- Lane mix: `legacy-session-review` 71, `historical-worktree-review` 35, `family` 17, `parked-secret` 17, `stalled-review` 3, `owner-blocker` 2, `hash-review` 2, `remote-close` 2, `observe` 2, `documented-residue` 1, `remote-proof` 1.

## Recorded Batches

| Rank | Batch | Status | Band | Lane | Events | Owner Repos | Evidence | Gate |
|---:|---|---|---|---|---:|---|---|---|
| 1 | `prompt-batch-critical-owner-blocker-001` | `owner-recorded` | `critical` | `owner-blocker` | 103 | `organvm/sovereign--ground`, `organvm/universal-mail--automation` | `generated_results_patch_preserved` 1, `private_patch_preserved` 1 | not dispatchable: owner classification remains before cleanup, PR creation, or delegation |
| 2 | `prompt-batch-high-owner-blocker-001` | `owner-recorded` | `high` | `owner-blocker` | 5 | `organvm/.github` | `history_mismatch_patch_preserved` 1 | not dispatchable: owner classification remains before cleanup, PR creation, or delegation |
| 3 | `prompt-batch-high-documented-residue-001` | `non-source-recorded` | `high` | `documented-residue` | 94 | `organvm/the-invisible-ledger` | `cache_only_residue` 1 | not dispatchable: recorded as non-source residue; reclaim only after operator acceptance |

## Next Review Queue

| Rank | Batch | Status | Band | Lane | Sessions | Events | Dominant Mix | Next Action |
|---:|---|---|---|---|---:|---:|---|---|
| 1 | `prompt-batch-critical-stalled-review-001` | `needs-packetization` | `critical` | `stalled-review` | 25 | 108 | sources codex-sessions 25; families session_lifecycle 11, worktree_lifecycle 14 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 2 | `prompt-batch-critical-stalled-review-002` | `needs-packetization` | `critical` | `stalled-review` | 17 | 77 | sources codex-sessions 17; families github_review 12, session_lifecycle 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 3 | `prompt-batch-high-stalled-review-001` | `needs-packetization` | `high` | `stalled-review` | 16 | 67 | sources codex-sessions 16; families agent_coordination 9, session_lifecycle 2, technical_debt_ci 3, uncategorized 2 | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 4 | `prompt-batch-critical-historical-worktree-review-001` | `needs-private-review` | `critical` | `historical-worktree-review` | 25 | 3747 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 5 | `prompt-batch-critical-legacy-session-review-001` | `needs-private-review` | `critical` | `legacy-session-review` | 25 | 18681 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 6 | `prompt-batch-critical-legacy-session-review-002` | `needs-private-review` | `critical` | `legacy-session-review` | 16 | 4927 | sources claude-projects 16; families uncategorized 16 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 7 | `prompt-batch-critical-historical-worktree-review-002` | `needs-private-review` | `critical` | `historical-worktree-review` | 13 | 1248 | sources claude-projects 13; families uncategorized 13 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 8 | `prompt-batch-high-historical-worktree-review-001` | `needs-private-review` | `high` | `historical-worktree-review` | 25 | 2040 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 9 | `prompt-batch-high-legacy-session-review-001` | `needs-private-review` | `high` | `legacy-session-review` | 25 | 7410 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 10 | `prompt-batch-high-historical-worktree-review-002` | `needs-private-review` | `high` | `historical-worktree-review` | 25 | 1858 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 11 | `prompt-batch-high-legacy-session-review-002` | `needs-private-review` | `high` | `legacy-session-review` | 25 | 2920 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 12 | `prompt-batch-high-historical-worktree-review-003` | `needs-private-review` | `high` | `historical-worktree-review` | 25 | 1699 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 13 | `prompt-batch-high-historical-worktree-review-004` | `needs-private-review` | `high` | `historical-worktree-review` | 25 | 1518 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 14 | `prompt-batch-high-historical-worktree-review-005` | `needs-private-review` | `high` | `historical-worktree-review` | 25 | 1359 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 15 | `prompt-batch-high-historical-worktree-review-006` | `needs-private-review` | `high` | `historical-worktree-review` | 25 | 1348 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 16 | `prompt-batch-high-hash-review-001` | `needs-private-review` | `high` | `hash-review` | 1 | 440 | sources codex-history 1; families uncategorized 1 | Review the redacted `codex-history` receipt privately and assign an owner route before delegation. |
| 17 | `prompt-batch-high-historical-worktree-review-007` | `needs-private-review` | `high` | `historical-worktree-review` | 25 | 1255 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 18 | `prompt-batch-high-historical-worktree-review-008` | `needs-private-review` | `high` | `historical-worktree-review` | 7 | 385 | sources claude-projects 7; families uncategorized 7 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 19 | `prompt-batch-high-legacy-session-review-003` | `needs-private-review` | `high` | `legacy-session-review` | 2 | 157 | sources claude-projects 2; families uncategorized 2 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 20 | `prompt-batch-medium-hash-review-001` | `needs-private-review` | `medium` | `hash-review` | 2 | 46 | sources codex-sessions 2; families uncategorized 2 | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| 21 | `prompt-batch-medium-historical-worktree-review-001` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 1184 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 22 | `prompt-batch-medium-legacy-session-review-001` | `needs-private-review` | `medium` | `legacy-session-review` | 25 | 1532 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 23 | `prompt-batch-medium-historical-worktree-review-002` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 1051 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 24 | `prompt-batch-medium-family-001` | `needs-private-review` | `medium` | `family` | 25 | 135 | sources codex-sessions 25; families session_lifecycle 2, worktree_lifecycle 23 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 25 | `prompt-batch-medium-historical-worktree-review-003` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 987 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 26 | `prompt-batch-medium-historical-worktree-review-004` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 1012 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 27 | `prompt-batch-medium-historical-worktree-review-005` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 883 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 28 | `prompt-batch-medium-historical-worktree-review-006` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 796 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 29 | `prompt-batch-medium-legacy-session-review-002` | `needs-private-review` | `medium` | `legacy-session-review` | 25 | 1326 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 30 | `prompt-batch-medium-historical-worktree-review-007` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 908 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 31 | `prompt-batch-medium-historical-worktree-review-008` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 801 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 32 | `prompt-batch-medium-family-002` | `needs-private-review` | `medium` | `family` | 25 | 90 | sources codex-sessions 25; families github_review 9, session_lifecycle 16 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 33 | `prompt-batch-medium-historical-worktree-review-009` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 696 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 34 | `prompt-batch-medium-historical-worktree-review-010` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 717 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 35 | `prompt-batch-medium-legacy-session-review-003` | `needs-private-review` | `medium` | `legacy-session-review` | 25 | 1159 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 36 | `prompt-batch-medium-historical-worktree-review-011` | `needs-private-review` | `medium` | `historical-worktree-review` | 25 | 582 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 37 | `prompt-batch-medium-legacy-session-review-004` | `needs-private-review` | `medium` | `legacy-session-review` | 25 | 1018 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 38 | `prompt-batch-medium-legacy-session-review-005` | `needs-private-review` | `medium` | `legacy-session-review` | 25 | 1017 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 39 | `prompt-batch-medium-family-003` | `needs-private-review` | `medium` | `family` | 25 | 94 | sources codex-sessions 25; families github_review 25 | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 40 | `prompt-batch-medium-family-004` | `needs-private-review` | `medium` | `family` | 25 | 91 | sources codex-sessions 25; families github_review 25 | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |

## Private Output

- Prompt batch review private index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-batch-review-ledger.json`.
- The private index keeps batch membership, session keys, prompt hashes, private receipt paths, and owner routing evidence; it contains no prompt text.

## Commands

- Refresh prerequisites: `python3 scripts/prompt-priority-map.py --write && python3 scripts/session-attack-paths.py --write`
- Refresh this review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Show a wider tracked slice: `python3 scripts/prompt-batch-review-ledger.py --write --limit 60`
