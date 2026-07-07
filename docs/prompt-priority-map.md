# Prompt Priority Map

Generated: `2026-07-07T00:20:58+00:00`

## Canonical Decision

- The long-running unit is a review batch, not a chat-length mega-prompt.
- Every prompt-like event is represented by a hash in the private map; tracked docs show only counts, session keys, lanes, and routes.
- A batch becomes dispatchable only after it has an owner repo or owner ledger, bounded next action, no raw-secret dependency, and a verification or blocker receipt.
- Credential/auth/secret lanes stay parked unless a scoped task directly requires non-secret preparation.

## Coverage

- Prompt lifecycle source files: `15590`.
- Prompt-like events from source ledger: `136694`.
- Prioritized session receipts: `7144`.
- Prioritized prompt events: `136694`.
- Unique prompt hashes: `81036`.
- Review batches: `309`.
- Codex classified sessions: `887`.
- Attack paths / blockers / capability items: `550` / `8` / `30`.
- Source mix: `claude-projects` 3508, `codex-sessions` 1518, `opencode-db` 1485.
- Band mix: `low` 4128, `medium` 1942, `high` 525, `parked` 416, `critical` 133.
- Lane mix: `legacy-session-review` 2236, `hash-review` 1982, `historical-worktree-review` 1500, `parked-secret` 405, `family` 401, `observe` 209.

## Priority Model

- Highest: stalled or active receipts tied to high-ranked attack paths, worktree preservation risk, repeated prompt hashes, and recent activity.
- Middle: legacy Claude/Codex sessions that need private sampling and owner-ledger promotion.
- Lowest: closed, already-parked, or credential/auth work unless directly blocking a selected path.
- The private JSON keeps the complete sorted hash/session map; this Markdown intentionally shows a bounded operator slice.

## Review Batches

| Rank | Batch | Band | Lane | Sessions | Prompt Events | Unique Prompts | Dominant Mix | Route |
|---:|---|---|---|---:|---:|---:|---|---|
| 1 | `prompt-batch-critical-remote-proof-001` | `critical` | `remote-proof` | 3 | 264 | 191 | sources claude-projects 2, codex-sessions 1; families uncategorized 3 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 2 | `prompt-batch-critical-owner-blocker-001` | `critical` | `owner-blocker` | 8 | 812 | 385 | sources codex-sessions 5, claude-projects 3; families session_lifecycle 5, uncategorized 3 | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 3 | `prompt-batch-critical-remote-pr-open-001` | `critical` | `remote-pr-open` | 5 | 2547 | 1428 | sources claude-projects 4, codex-sessions 1; families uncategorized 5 | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 4 | `prompt-batch-critical-human-gate-001` | `critical` | `human-gate` | 3 | 2247 | 1243 | sources claude-projects 3; families uncategorized 3 | No local-only source preservation remains. Local HEAD is an ancestor of current origin/main and `git diff origin/main...HEAD` is empty. Reclaim the local checkout only after operator acceptance. |
| 5 | `prompt-batch-critical-observe-001` | `critical` | `observe` | 25 | 2337 | 1534 | sources claude-projects 25; families uncategorized 25 | Keep active work visible; do not interrupt unless it becomes stale. |
| 6 | `prompt-batch-critical-preserve-001` | `critical` | `preserve` | 11 | 44 | 33 | sources codex-sessions 11; families uncategorized 11 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 7 | `prompt-batch-critical-historical-worktree-review-001` | `critical` | `historical-worktree-review` | 19 | 3085 | 2024 | sources claude-projects 19; families uncategorized 19 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 8 | `prompt-batch-critical-stalled-review-001` | `critical` | `stalled-review` | 25 | 105 | 67 | sources codex-sessions 25; families worktree_lifecycle 15, session_lifecycle 9, github_review 1 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 9 | `prompt-batch-critical-legacy-session-review-001` | `critical` | `legacy-session-review` | 21 | 11922 | 6405 | sources claude-projects 21; families uncategorized 21 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 10 | `prompt-batch-critical-hash-review-001` | `critical` | `hash-review` | 2 | 236 | 133 | sources codex-sessions 2; families uncategorized 2 | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| 11 | `prompt-batch-critical-stalled-review-002` | `critical` | `stalled-review` | 11 | 53 | 33 | sources codex-sessions 11; families github_review 11 | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 12 | `prompt-batch-high-legacy-session-review-001` | `high` | `legacy-session-review` | 25 | 18423 | 9537 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 13 | `prompt-batch-high-legacy-session-review-002` | `high` | `legacy-session-review` | 25 | 10105 | 5876 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 14 | `prompt-batch-high-historical-worktree-review-001` | `high` | `historical-worktree-review` | 25 | 2401 | 1608 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 15 | `prompt-batch-high-remote-pr-open-001` | `high` | `remote-pr-open` | 25 | 1609 | 1146 | sources claude-projects 25; families uncategorized 25 | Review draft PR #79, then merge, supersede, or archive the Invisible Ledger trial followups branch. Local checkout is no longer the only review surface. |
| 16 | `prompt-batch-high-observe-001` | `high` | `observe` | 25 | 1327 | 881 | sources claude-projects 25; families uncategorized 25 | Keep active work visible; do not interrupt unless it becomes stale. |
| 17 | `prompt-batch-high-human-gate-001` | `high` | `human-gate` | 6 | 154 | 126 | sources claude-projects 5, codex-sessions 1; families uncategorized 5, session_lifecycle 1 | Do not PR or delegate this deletion patch. The branch has no unique commits, no remote branch, no PR, no sparse-checkout configuration, and 167 tracked files deleted from disk while HEAD is an ancestor of origin/main. Treat as stale broken checkout/deletion artifact; reclaim only after operator acceptance, and recreate from origin/main if owner work is needed. |
| 18 | `prompt-batch-high-remote-proof-001` | `high` | `remote-proof` | 25 | 108 | 75 | sources codex-sessions 24, claude-projects 1; families uncategorized 25 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 19 | `prompt-batch-high-remote-proof-002` | `high` | `remote-proof` | 25 | 90 | 44 | sources claude-projects 16, codex-sessions 9; families uncategorized 25 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 20 | `prompt-batch-high-stalled-review-001` | `high` | `stalled-review` | 16 | 67 | 35 | sources codex-sessions 16; families agent_coordination 9, technical_debt_ci 3, session_lifecycle 2, uncategorized 2 | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 21 | `prompt-batch-high-legacy-session-review-003` | `high` | `legacy-session-review` | 25 | 4886 | 3062 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 22 | `prompt-batch-high-owner-blocker-001` | `high` | `owner-blocker` | 25 | 346 | 295 | sources codex-sessions 14, claude-projects 11; families uncategorized 25 | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 23 | `prompt-batch-high-hash-review-001` | `high` | `hash-review` | 4 | 1446 | 883 | sources codex-sessions 3, codex-history 1; families uncategorized 4 | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| 24 | `prompt-batch-high-remote-proof-003` | `high` | `remote-proof` | 25 | 51 | 22 | sources claude-projects 13, opencode-db 12; families uncategorized 25 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 25 | `prompt-batch-high-historical-worktree-review-002` | `high` | `historical-worktree-review` | 25 | 2043 | 1247 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 26 | `prompt-batch-high-legacy-session-review-004` | `high` | `legacy-session-review` | 25 | 2720 | 2137 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 27 | `prompt-batch-high-historical-worktree-review-003` | `high` | `historical-worktree-review` | 25 | 1828 | 1138 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 28 | `prompt-batch-high-remote-close-001` | `high` | `remote-close` | 5 | 20 | 15 | sources codex-sessions 5; families uncategorized 5 | Review PR state/checks, then merge or name supersession before local reclaim. |
| 29 | `prompt-batch-high-remote-proof-004` | `high` | `remote-proof` | 6 | 23 | 17 | sources codex-sessions 5, claude-projects 1; families uncategorized 6 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 30 | `prompt-batch-high-remote-pr-open-002` | `high` | `remote-pr-open` | 18 | 424 | 328 | sources claude-projects 14, codex-sessions 4; families uncategorized 14, session_lifecycle 3, github_review 1 | Review draft PR #79, then merge, supersede, or archive the Invisible Ledger trial followups branch. Local checkout is no longer the only review surface. |

## Top Session Receipts

| Rank | Session Key | Band | Lane | Score | Source | Family / State | Worktree | Prompt Events | Next Action |
|---:|---|---|---|---:|---|---|---|---:|---|
| 1 | `8b5ddd3315c01150acd3` | `critical` | `remote-proof` | 134 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-435-47b10f86` | 134 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 2 | `d2aee5cd2b95e2bf5de7` | `critical` | `remote-proof` | 134 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-423-47a6f9ec` | 126 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 3 | `488e26429b61892eb907` | `critical` | `owner-blocker` | 128 | `claude-projects` | `uncategorized` / `unclassified` | `feat-gcp-sa-organ` | 656 | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 4 | `4e162f0ddb3cb2fb3a7c` | `critical` | `remote-pr-open` | 126 | `claude-projects` | `uncategorized` / `unclassified` | `ticklish-bubbling-robin` | 1591 | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 5 | `83050bf792c78f94c22a` | `critical` | `human-gate` | 124 | `claude-projects` | `uncategorized` / `unclassified` | `fluttering-twirling-abelson` | 354 | No local-only source preservation remains. Local HEAD is an ancestor of current origin/main and `git diff origin/main...HEAD` is empty. Reclaim the local checkout only after operator acceptance. |
| 6 | `83af7669196a257c99c5` | `critical` | `remote-pr-open` | 114 | `claude-projects` | `uncategorized` / `unclassified` | `ticklish-bubbling-robin` | 146 | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 7 | `e72bc9aee2e024ffa9bb` | `critical` | `human-gate` | 113 | `claude-projects` | `uncategorized` / `unclassified` | `linear-conjuring-bear` | 1645 | Do not merge PR #635 as-is. Current main preserves the consolidation execution packet under docs/consolidation/ and scripts/ with stricter LIMEN_CONSOLIDATION_GATE guards; PR #635 remains a draft review artifact and should be closed or superseded by a new narrow PR only after human review. Reclaim the local checkout only after operator acceptance. |
| 8 | `12fc528ed36543429760` | `critical` | `observe` | 111 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-universal-mail--automation-118-9f686157` | 101 | Keep active work visible; do not interrupt unless it becomes stale. |
| 9 | `299646b71d625c1a2665` | `critical` | `observe` | 110 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-my--father-mother-21-fd6a0ac5` | 116 | Keep active work visible; do not interrupt unless it becomes stale. |
| 10 | `8b0fa94e76957bc765ea` | `critical` | `human-gate` | 108 | `claude-projects` | `uncategorized` / `unclassified` | `linear-conjuring-bear` | 248 | Do not merge PR #635 as-is. Current main preserves the consolidation execution packet under docs/consolidation/ and scripts/ with stricter LIMEN_CONSOLIDATION_GATE guards; PR #635 remains a draft review artifact and should be closed or superseded by a new narrow PR only after human review. Reclaim the local checkout only after operator acceptance. |
| 11 | `04cce8a6d84a16cdd71d` | `critical` | `observe` | 107 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-mirror-mirror-90-028f12b1` | 159 | Keep active work visible; do not interrupt unless it becomes stale. |
| 12 | `978e08ff84b3748e6a6b` | `critical` | `observe` | 107 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-mirror-mirror-71-d83257ef` | 102 | Keep active work visible; do not interrupt unless it becomes stale. |
| 13 | `6cdcc4f33f4c641e414a` | `critical` | `observe` | 106 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-domus-genoma-152-aaa842d9` | 92 | Keep active work visible; do not interrupt unless it becomes stale. |
| 14 | `6b59b9992484dea50d40` | `critical` | `observe` | 105 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-domus-genoma-141-70e4ccde` | 101 | Keep active work visible; do not interrupt unless it becomes stale. |
| 15 | `7ee2ffe6ad4ac8e79cf6` | `critical` | `observe` | 104 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-mirror-mirror-95-20f0cd1b` | 101 | Keep active work visible; do not interrupt unless it becomes stale. |
| 16 | `01d472b14313eb110ed0` | `critical` | `observe` | 103 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-mirror-mirror-104-5198c1b2` | 86 | Keep active work visible; do not interrupt unless it becomes stale. |
| 17 | `5d42ea04d16c616c3d1b` | `critical` | `observe` | 103 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-446-76408b03` | 85 | Keep active work visible; do not interrupt unless it becomes stale. |
| 18 | `ad02976c896f5994edde` | `critical` | `observe` | 102 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-mirror-mirror-77-c105b09b` | 86 | Keep active work visible; do not interrupt unless it becomes stale. |
| 19 | `12ba10d9c92b0bf6bbe4` | `critical` | `observe` | 101 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-domus-genoma-159-615266b7` | 82 | Keep active work visible; do not interrupt unless it becomes stale. |
| 20 | `629e5838eecb0d4ce8e6` | `critical` | `owner-blocker` | 100 | `claude-projects` | `uncategorized` / `unclassified` | `peer-audited--behavioral-blockchain` | 77 | No PR or remote branch preserves this exact local commit. Do not reclaim from lifecycle cleanup; create a narrow owner packet to review, push, supersede, or retire the patch. |
| 21 | `1037af727e38c09b892e` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `heal-rebase-organvm-a-i-chat--exporter-61-6eab8b67` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 22 | `1cad38b2d547e766f190` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-444-a00aa985` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 23 | `45e1f765b44222b1c4b7` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-438-da3b854e` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 24 | `4a3e861a6a6e8fd05ec6` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `heal-cifix-organvm-public-process-30-59ffa133` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 25 | `4f646327595a2d388082` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-428-4b320e87` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 26 | `5b51fda85a1e2c2ca21d` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `heal-rebase-organvm-a-i-chat--exporter-31-78a6445b` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 27 | `a6349046871aa9a33252` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `org-financial-organ-face-0704-bd436529` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 28 | `a7a74599648e4c40c2f8` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-424-8db5dab0` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 29 | `d49eb2ea0f2cb125021a` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-430-7c7129d9` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| 30 | `dbf503a7cea5be8cbe49` | `critical` | `preserve` | 100 | `codex-sessions` | `uncategorized` / `unclassified` | `org-governance-organ-selffeed-0703-00694775` | 4 | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |

## Lane Task Map

| Lane | Top Band | Sessions | Prompt Events | Batches | Dominant Source | Dominant Family | Route |
|---|---|---:|---:|---:|---|---|---|
| `remote-proof` | `critical` | 84 | 536 | 5 | `codex-sessions` | `uncategorized` | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| `owner-blocker` | `critical` | 92 | 1425 | 6 | `codex-sessions` | `uncategorized` | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| `remote-pr-open` | `critical` | 130 | 5671 | 8 | `claude-projects` | `uncategorized` | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| `human-gate` | `critical` | 37 | 2944 | 5 | `claude-projects` | `uncategorized` | No local-only source preservation remains. Local HEAD is an ancestor of current origin/main and `git diff origin/main...HEAD` is empty. Reclaim the local checkout only after operator acceptance. |
| `observe` | `critical` | 209 | 4458 | 11 | `codex-sessions` | `uncategorized` | Keep active work visible; do not interrupt unless it becomes stale. |
| `preserve` | `critical` | 11 | 44 | 1 | `codex-sessions` | `uncategorized` | Inspect diff, run owner predicate, push branch/open draft PR or record blocker. |
| `historical-worktree-review` | `critical` | 1500 | 32590 | 62 | `claude-projects` | `uncategorized` | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| `stalled-review` | `critical` | 52 | 225 | 3 | `codex-sessions` | `worktree_lifecycle` | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| `legacy-session-review` | `critical` | 2236 | 80108 | 91 | `claude-projects` | `uncategorized` | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| `hash-review` | `critical` | 1982 | 4672 | 82 | `opencode-db` | `uncategorized` | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| `remote-close` | `high` | 5 | 20 | 1 | `codex-sessions` | `uncategorized` | Review PR state/checks, then merge or name supersession before local reclaim. |
| `family` | `medium` | 401 | 1501 | 17 | `codex-sessions` | `github_review` | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
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
