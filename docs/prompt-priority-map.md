# Prompt Priority Map

Generated: `2026-07-06T09:27:48+00:00`

## Canonical Decision

- The long-running unit is a review batch, not a chat-length mega-prompt.
- Every prompt-like event is represented by a hash in the private map; tracked docs show only counts, session keys, lanes, and routes.
- A batch becomes dispatchable only after it has an owner repo or owner ledger, bounded next action, no raw-secret dependency, and a verification or blocker receipt.
- Credential/auth/secret lanes stay parked unless a scoped task directly requires non-secret preparation.

## Coverage

- Prompt lifecycle source files: `15221`.
- Prompt-like events from source ledger: `131016`.
- Prioritized session receipts: `6799`.
- Prioritized prompt events: `131016`.
- Unique prompt hashes: `77790`.
- Review batches: `291`.
- Codex classified sessions: `887`.
- Attack paths / blockers / capability items: `63` / `7` / `30`.
- Source mix: `claude-projects` 3396, `opencode-db` 1407, `codex-sessions` 1363.
- Band mix: `low` 4068, `medium` 1825, `parked` 416, `high` 389, `critical` 101.
- Lane mix: `legacy-session-review` 2236, `hash-review` 1942, `historical-worktree-review` 1500, `parked-secret` 405, `family` 401, `remote-pr-open` 130.

## Priority Model

- Highest: stalled or active receipts tied to high-ranked attack paths, worktree preservation risk, repeated prompt hashes, and recent activity.
- Middle: legacy Claude/Codex sessions that need private sampling and owner-ledger promotion.
- Lowest: closed, already-parked, or credential/auth work unless directly blocking a selected path.
- The private JSON keeps the complete sorted hash/session map; this Markdown intentionally shows a bounded operator slice.

## Review Batches

| Rank | Batch | Band | Lane | Sessions | Prompt Events | Unique Prompts | Dominant Mix | Route |
|---:|---|---|---|---:|---:|---:|---|---|
| 1 | `prompt-batch-critical-remote-proof-001` | `critical` | `remote-proof` | 5 | 315 | 225 | sources claude-projects 5; families uncategorized 5 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 2 | `prompt-batch-critical-owner-blocker-001` | `critical` | `owner-blocker` | 8 | 812 | 385 | sources codex-sessions 5, claude-projects 3; families session_lifecycle 5, uncategorized 3 | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 3 | `prompt-batch-critical-remote-pr-open-001` | `critical` | `remote-pr-open` | 5 | 2517 | 1417 | sources claude-projects 4, codex-sessions 1; families uncategorized 5 | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 4 | `prompt-batch-critical-human-gate-001` | `critical` | `human-gate` | 2 | 1860 | 1024 | sources claude-projects 2; families uncategorized 2 | Do not merge PR #635 as-is. Current main preserves the consolidation execution packet under docs/consolidation/ and scripts/ with stricter LIMEN_CONSOLIDATION_GATE guards; PR #635 remains a draft review artifact and should be closed or superseded by a new narrow PR only after human review. Reclaim the local checkout only after operator acceptance. |
| 5 | `prompt-batch-critical-legacy-session-review-001` | `critical` | `legacy-session-review` | 23 | 12302 | 6676 | sources claude-projects 23; families uncategorized 23 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 6 | `prompt-batch-critical-historical-worktree-review-001` | `critical` | `historical-worktree-review` | 19 | 3085 | 2024 | sources claude-projects 19; families uncategorized 19 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 7 | `prompt-batch-critical-stalled-review-001` | `critical` | `stalled-review` | 25 | 116 | 74 | sources codex-sessions 25; families github_review 11, session_lifecycle 9, worktree_lifecycle 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 8 | `prompt-batch-critical-hash-review-001` | `critical` | `hash-review` | 3 | 383 | 184 | sources codex-sessions 3; families uncategorized 3 | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| 9 | `prompt-batch-critical-stalled-review-002` | `critical` | `stalled-review` | 11 | 42 | 26 | sources codex-sessions 11; families worktree_lifecycle 10, github_review 1 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 10 | `prompt-batch-high-legacy-session-review-001` | `high` | `legacy-session-review` | 25 | 18423 | 9537 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 11 | `prompt-batch-high-legacy-session-review-002` | `high` | `legacy-session-review` | 25 | 10325 | 5938 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 12 | `prompt-batch-high-historical-worktree-review-001` | `high` | `historical-worktree-review` | 25 | 2401 | 1608 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 13 | `prompt-batch-high-remote-pr-open-001` | `high` | `remote-pr-open` | 25 | 1705 | 1093 | sources claude-projects 20, codex-sessions 5; families uncategorized 22, session_lifecycle 2, github_review 1 | Review draft PR #79, then merge, supersede, or archive the Invisible Ledger trial followups branch. Local checkout is no longer the only review surface. |
| 14 | `prompt-batch-high-human-gate-001` | `high` | `human-gate` | 2 | 78 | 54 | sources claude-projects 1, codex-sessions 1; families uncategorized 1, session_lifecycle 1 | Do not PR or delegate this deletion patch. The branch has no unique commits, no remote branch, no PR, no sparse-checkout configuration, and 167 tracked files deleted from disk while HEAD is an ancestor of origin/main. Treat as stale broken checkout/deletion artifact; reclaim only after operator acceptance, and recreate from origin/main if owner work is needed. |
| 15 | `prompt-batch-high-stalled-review-001` | `high` | `stalled-review` | 16 | 67 | 35 | sources codex-sessions 16; families agent_coordination 9, technical_debt_ci 3, session_lifecycle 2, uncategorized 2 | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 16 | `prompt-batch-high-owner-blocker-001` | `high` | `owner-blocker` | 25 | 346 | 295 | sources codex-sessions 14, claude-projects 11; families uncategorized 25 | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 17 | `prompt-batch-high-legacy-session-review-003` | `high` | `legacy-session-review` | 25 | 4549 | 2903 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 18 | `prompt-batch-high-historical-worktree-review-002` | `high` | `historical-worktree-review` | 25 | 2043 | 1247 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 19 | `prompt-batch-high-residue-001` | `high` | `residue` | 2 | 6 | 2 | sources claude-projects 2; families uncategorized 2 | Inspect for unique files; if only cache/generated residue, record owner receipt before reclaiming. |
| 20 | `prompt-batch-high-historical-worktree-review-003` | `high` | `historical-worktree-review` | 25 | 1828 | 1138 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 21 | `prompt-batch-high-hash-review-001` | `high` | `hash-review` | 3 | 1183 | 788 | sources codex-sessions 2, codex-history 1; families uncategorized 3 | Review the redacted `codex-history` receipt privately and assign an owner route before delegation. |
| 22 | `prompt-batch-high-legacy-session-review-004` | `high` | `legacy-session-review` | 25 | 2633 | 2085 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 23 | `prompt-batch-high-historical-worktree-review-004` | `high` | `historical-worktree-review` | 25 | 1704 | 1055 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 24 | `prompt-batch-high-owner-blocker-002` | `high` | `owner-blocker` | 25 | 135 | 90 | sources codex-sessions 23, claude-projects 2; families uncategorized 25 | No PR or remote branch preserves this exact local commit. Do not reclaim from lifecycle cleanup; create a narrow owner packet to review, push, supersede, or retire the patch. |
| 25 | `prompt-batch-high-historical-worktree-review-005` | `high` | `historical-worktree-review` | 25 | 1546 | 962 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 26 | `prompt-batch-high-legacy-session-review-005` | `high` | `legacy-session-review` | 4 | 338 | 266 | sources claude-projects 4; families uncategorized 4 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 27 | `prompt-batch-high-owner-blocker-003` | `high` | `owner-blocker` | 25 | 96 | 33 | sources claude-projects 25; families uncategorized 25 | No PR or remote branch preserves this exact local commit. Do not reclaim from lifecycle cleanup; create a narrow owner packet to review, push, supersede, or retire the patch. |
| 28 | `prompt-batch-high-historical-worktree-review-006` | `high` | `historical-worktree-review` | 25 | 1443 | 960 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 29 | `prompt-batch-high-historical-worktree-review-007` | `high` | `historical-worktree-review` | 10 | 563 | 393 | sources claude-projects 10; families uncategorized 10 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 30 | `prompt-batch-high-remote-pr-open-002` | `high` | `remote-pr-open` | 2 | 60 | 37 | sources claude-projects 1, codex-sessions 1; families uncategorized 1, session_lifecycle 1 | Review draft PR #79, then merge, supersede, or archive the Invisible Ledger trial followups branch. Local checkout is no longer the only review surface. |

## Top Session Receipts

| Rank | Session Key | Band | Lane | Score | Source | Family / State | Worktree | Prompt Events | Next Action |
|---:|---|---|---|---:|---|---|---|---:|---|
| 1 | `83050bf792c78f94c22a` | `critical` | `remote-proof` | 139 | `claude-projects` | `uncategorized` / `unclassified` | `fluttering-twirling-abelson` | 239 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 2 | `488e26429b61892eb907` | `critical` | `owner-blocker` | 128 | `claude-projects` | `uncategorized` / `unclassified` | `feat-gcp-sa-organ` | 656 | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 3 | `e72bc9aee2e024ffa9bb` | `critical` | `human-gate` | 113 | `claude-projects` | `uncategorized` / `unclassified` | `linear-conjuring-bear` | 1630 | Do not merge PR #635 as-is. Current main preserves the consolidation execution packet under docs/consolidation/ and scripts/ with stricter LIMEN_CONSOLIDATION_GATE guards; PR #635 remains a draft review artifact and should be closed or superseded by a new narrow PR only after human review. Reclaim the local checkout only after operator acceptance. |
| 4 | `4e162f0ddb3cb2fb3a7c` | `critical` | `remote-pr-open` | 113 | `claude-projects` | `uncategorized` / `unclassified` | `ticklish-bubbling-robin` | 1561 | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 5 | `8b0fa94e76957bc765ea` | `critical` | `human-gate` | 108 | `claude-projects` | `uncategorized` / `unclassified` | `linear-conjuring-bear` | 230 | Do not merge PR #635 as-is. Current main preserves the consolidation execution packet under docs/consolidation/ and scripts/ with stricter LIMEN_CONSOLIDATION_GATE guards; PR #635 remains a draft review artifact and should be closed or superseded by a new narrow PR only after human review. Reclaim the local checkout only after operator acceptance. |
| 6 | `1ecb3a7f55ff1ee9ad8a` | `critical` | `remote-pr-open` | 107 | `codex-sessions` | `uncategorized` / `unclassified` | `triptych-story` | 192 | Review draft PR #1, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 7 | `faa050cc1fec01d8248b` | `critical` | `remote-proof` | 106 | `claude-projects` | `uncategorized` / `unclassified` | `fluttering-twirling-abelson` | 23 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 8 | `7b465b869b8433b3a2b9` | `critical` | `legacy-session-review` | 101 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 518 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 9 | `83af7669196a257c99c5` | `critical` | `remote-pr-open` | 101 | `claude-projects` | `uncategorized` / `unclassified` | `ticklish-bubbling-robin` | 146 | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 10 | `629e5838eecb0d4ce8e6` | `critical` | `owner-blocker` | 100 | `claude-projects` | `uncategorized` / `unclassified` | `peer-audited--behavioral-blockchain` | 77 | No PR or remote branch preserves this exact local commit. Do not reclaim from lifecycle cleanup; create a narrow owner packet to review, push, supersede, or retire the patch. |
| 11 | `cad7d3bad2068e8d3d75` | `critical` | `historical-worktree-review` | 99 | `claude-projects` | `uncategorized` / `unclassified` | `heal-192-regression` | 782 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 12 | `9185f2b3d942774cf587` | `critical` | `legacy-session-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 410 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 13 | `dc9efdf3fcc199d66167` | `critical` | `legacy-session-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 244 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 14 | `42efa5506eb8d63d286e` | `critical` | `stalled-review` | 97 | `codex-sessions` | `session_lifecycle` / `STALLED` | `rev-styx-stripe-subscription-719b` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 15 | `510d7ae2641801545169` | `critical` | `stalled-review` | 97 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-conversation-corpus-engine-2e73` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 16 | `22ad4c797b9266275679` | `critical` | `remote-proof` | 96 | `claude-projects` | `uncategorized` / `unclassified` | `fluttering-twirling-abelson` | 20 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 17 | `04447e42f5e46fdd63ba` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-054` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 18 | `1f935053382b9082e22e` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-084-8712` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 19 | `5660b1decb73aeabeb70` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `gh-4444j99-domus-genoma-86-8188` | 3 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 20 | `95805b44782887476f1b` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `resolve-organvm-i-theoria-.github-459-cd2f` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 21 | `9d3d51c6a1fc16d8b4bf` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-conversation-corpus-engine-ee1d` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 22 | `a506303dc7dd69fb2c61` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `gh-a-organvm-organvm-corpvs-testamentvm-494-0388` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 23 | `ca0427da1bc37b6ffdf8` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-099` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 24 | `15734e947177c6527dad` | `critical` | `legacy-session-review` | 95 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 515 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 25 | `3dd1d71b025bf0dcb107` | `critical` | `legacy-session-review` | 95 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 618 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 26 | `4371a54262e8290e787c` | `critical` | `legacy-session-review` | 95 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 658 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 27 | `43f31c2c9bbd1da6cb6e` | `critical` | `legacy-session-review` | 95 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 1169 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 28 | `4edabe77b0f5d6c13c96` | `critical` | `legacy-session-review` | 95 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 597 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 29 | `57665d5149716630d8f5` | `critical` | `legacy-session-review` | 95 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 1035 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 30 | `5c4ddaf945029e2e76f6` | `critical` | `legacy-session-review` | 95 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 708 | Sample the private source file, extract durable atoms, then route to an owner ledger. |

## Lane Task Map

| Lane | Top Band | Sessions | Prompt Events | Batches | Dominant Source | Dominant Family | Route |
|---|---|---:|---:|---:|---|---|---|
| `remote-proof` | `critical` | 5 | 315 | 1 | `claude-projects` | `uncategorized` | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| `owner-blocker` | `critical` | 92 | 1425 | 6 | `codex-sessions` | `uncategorized` | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| `human-gate` | `critical` | 30 | 2475 | 4 | `claude-projects` | `uncategorized` | Do not merge PR #635 as-is. Current main preserves the consolidation execution packet under docs/consolidation/ and scripts/ with stricter LIMEN_CONSOLIDATION_GATE guards; PR #635 remains a draft review artifact and should be closed or superseded by a new narrow PR only after human review. Reclaim the local checkout only after operator acceptance. |
| `remote-pr-open` | `critical` | 130 | 5641 | 8 | `claude-projects` | `uncategorized` | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| `legacy-session-review` | `critical` | 2236 | 80108 | 91 | `claude-projects` | `uncategorized` | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| `historical-worktree-review` | `critical` | 1500 | 32590 | 62 | `claude-projects` | `uncategorized` | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| `stalled-review` | `critical` | 52 | 225 | 3 | `codex-sessions` | `worktree_lifecycle` | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| `hash-review` | `critical` | 1942 | 4218 | 80 | `opencode-db` | `uncategorized` | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| `residue` | `high` | 2 | 6 | 1 | `claude-projects` | `uncategorized` | Inspect for unique files; if only cache/generated residue, record owner receipt before reclaiming. |
| `family` | `medium` | 401 | 1501 | 17 | `codex-sessions` | `github_review` | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| `observe` | `medium` | 4 | 12 | 1 | `claude-projects` | `uncategorized` | Keep active work visible; do not interrupt unless it becomes stale. |
| `parked-secret` | `parked` | 405 | 2500 | 17 | `codex-sessions` | `auth_credentials` | Keep parked unless a scoped account/setup task directly requires non-secret prep. |

## Private Output

- Prompt priority private map: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-priority-map.json`.
- The private map contains prompt hashes, session keys, source paths, lanes, scores, and batch membership; it contains no prompt text.

## Commands

- Refresh prerequisites: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/session-attack-paths.py --write`
- Refresh this priority map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Show a wider tracked slice: `python3 scripts/prompt-priority-map.py --write --limit 60`
