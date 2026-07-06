# Prompt Priority Map

Generated: `2026-07-06T15:42:57+00:00`

## Canonical Decision

- The long-running unit is a review batch, not a chat-length mega-prompt.
- Every prompt-like event is represented by a hash in the private map; tracked docs show only counts, session keys, lanes, and routes.
- A batch becomes dispatchable only after it has an owner repo or owner ledger, bounded next action, no raw-secret dependency, and a verification or blocker receipt.
- Credential/auth/secret lanes stay parked unless a scoped task directly requires non-secret preparation.

## Coverage

- Prompt lifecycle source files: `15291`.
- Prompt-like events from source ledger: `131758`.
- Prioritized session receipts: `6869`.
- Prioritized prompt events: `131758`.
- Unique prompt hashes: `78155`.
- Review batches: `294`.
- Codex classified sessions: `887`.
- Attack paths / blockers / capability items: `178` / `8` / `30`.
- Source mix: `claude-projects` 3422, `opencode-db` 1425, `codex-sessions` 1389.
- Band mix: `low` 4095, `medium` 1863, `parked` 416, `high` 396, `critical` 99.
- Lane mix: `legacy-session-review` 2236, `hash-review` 1965, `historical-worktree-review` 1500, `parked-secret` 405, `family` 401, `remote-pr-open` 130.

## Priority Model

- Highest: stalled or active receipts tied to high-ranked attack paths, worktree preservation risk, repeated prompt hashes, and recent activity.
- Middle: legacy Claude/Codex sessions that need private sampling and owner-ledger promotion.
- Lowest: closed, already-parked, or credential/auth work unless directly blocking a selected path.
- The private JSON keeps the complete sorted hash/session map; this Markdown intentionally shows a bounded operator slice.

## Review Batches

| Rank | Batch | Band | Lane | Sessions | Prompt Events | Unique Prompts | Dominant Mix | Route |
|---:|---|---|---|---:|---:|---:|---|---|
| 1 | `prompt-batch-critical-owner-blocker-001` | `critical` | `owner-blocker` | 8 | 812 | 385 | sources codex-sessions 5, claude-projects 3; families session_lifecycle 5, uncategorized 3 | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 2 | `prompt-batch-critical-human-gate-001` | `critical` | `human-gate` | 4 | 2225 | 1254 | sources claude-projects 4; families uncategorized 4 | No local-only source preservation remains. Local HEAD is an ancestor of current origin/main and `git diff origin/main...HEAD` is empty. Reclaim the local checkout only after operator acceptance. |
| 3 | `prompt-batch-critical-remote-pr-open-001` | `critical` | `remote-pr-open` | 5 | 2527 | 1419 | sources claude-projects 4, codex-sessions 1; families uncategorized 5 | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 4 | `prompt-batch-critical-observe-001` | `critical` | `observe` | 2 | 260 | 188 | sources claude-projects 2; families uncategorized 2 | Keep active work visible; do not interrupt unless it becomes stale. |
| 5 | `prompt-batch-critical-legacy-session-review-001` | `critical` | `legacy-session-review` | 23 | 12302 | 6676 | sources claude-projects 23; families uncategorized 23 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 6 | `prompt-batch-critical-historical-worktree-review-001` | `critical` | `historical-worktree-review` | 19 | 3085 | 2024 | sources claude-projects 19; families uncategorized 19 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 7 | `prompt-batch-critical-stalled-review-001` | `critical` | `stalled-review` | 25 | 105 | 67 | sources codex-sessions 25; families worktree_lifecycle 15, session_lifecycle 9, github_review 1 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 8 | `prompt-batch-critical-hash-review-001` | `critical` | `hash-review` | 2 | 236 | 133 | sources codex-sessions 2; families uncategorized 2 | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| 9 | `prompt-batch-critical-stalled-review-002` | `critical` | `stalled-review` | 11 | 53 | 33 | sources codex-sessions 11; families github_review 11 | Review PR/issue receipts only after owner repo, predicate, and blocker are explicit. |
| 10 | `prompt-batch-high-legacy-session-review-001` | `high` | `legacy-session-review` | 25 | 18423 | 9537 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 11 | `prompt-batch-high-legacy-session-review-002` | `high` | `legacy-session-review` | 25 | 10325 | 5938 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 12 | `prompt-batch-high-historical-worktree-review-001` | `high` | `historical-worktree-review` | 25 | 2401 | 1608 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 13 | `prompt-batch-high-remote-pr-open-001` | `high` | `remote-pr-open` | 25 | 1705 | 1093 | sources claude-projects 20, codex-sessions 5; families uncategorized 22, session_lifecycle 2, github_review 1 | Review draft PR #79, then merge, supersede, or archive the Invisible Ledger trial followups branch. Local checkout is no longer the only review surface. |
| 14 | `prompt-batch-high-human-gate-001` | `high` | `human-gate` | 5 | 131 | 103 | sources claude-projects 4, codex-sessions 1; families uncategorized 4, session_lifecycle 1 | Do not PR or delegate this deletion patch. The branch has no unique commits, no remote branch, no PR, no sparse-checkout configuration, and 167 tracked files deleted from disk while HEAD is an ancestor of origin/main. Treat as stale broken checkout/deletion artifact; reclaim only after operator acceptance, and recreate from origin/main if owner work is needed. |
| 15 | `prompt-batch-high-stalled-review-001` | `high` | `stalled-review` | 16 | 67 | 35 | sources codex-sessions 16; families agent_coordination 9, technical_debt_ci 3, session_lifecycle 2, uncategorized 2 | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 16 | `prompt-batch-high-owner-blocker-001` | `high` | `owner-blocker` | 25 | 346 | 295 | sources codex-sessions 14, claude-projects 11; families uncategorized 25 | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 17 | `prompt-batch-high-legacy-session-review-003` | `high` | `legacy-session-review` | 25 | 4549 | 2903 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 18 | `prompt-batch-high-remote-proof-001` | `high` | `remote-proof` | 5 | 15 | 6 | sources claude-projects 5; families uncategorized 5 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 19 | `prompt-batch-high-hash-review-001` | `high` | `hash-review` | 4 | 1370 | 843 | sources codex-sessions 3, codex-history 1; families uncategorized 4 | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| 20 | `prompt-batch-high-historical-worktree-review-002` | `high` | `historical-worktree-review` | 25 | 2043 | 1247 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 21 | `prompt-batch-high-historical-worktree-review-003` | `high` | `historical-worktree-review` | 25 | 1828 | 1138 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
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
| 1 | `488e26429b61892eb907` | `critical` | `owner-blocker` | 128 | `claude-projects` | `uncategorized` / `unclassified` | `feat-gcp-sa-organ` | 656 | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| 2 | `83050bf792c78f94c22a` | `critical` | `human-gate` | 124 | `claude-projects` | `uncategorized` / `unclassified` | `fluttering-twirling-abelson` | 327 | No local-only source preservation remains. Local HEAD is an ancestor of current origin/main and `git diff origin/main...HEAD` is empty. Reclaim the local checkout only after operator acceptance. |
| 3 | `e72bc9aee2e024ffa9bb` | `critical` | `human-gate` | 113 | `claude-projects` | `uncategorized` / `unclassified` | `linear-conjuring-bear` | 1636 | Do not merge PR #635 as-is. Current main preserves the consolidation execution packet under docs/consolidation/ and scripts/ with stricter LIMEN_CONSOLIDATION_GATE guards; PR #635 remains a draft review artifact and should be closed or superseded by a new narrow PR only after human review. Reclaim the local checkout only after operator acceptance. |
| 4 | `4e162f0ddb3cb2fb3a7c` | `critical` | `remote-pr-open` | 113 | `claude-projects` | `uncategorized` / `unclassified` | `ticklish-bubbling-robin` | 1571 | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 5 | `d2aee5cd2b95e2bf5de7` | `critical` | `observe` | 112 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-423-47a6f9ec` | 126 | Keep active work visible; do not interrupt unless it becomes stale. |
| 6 | `8b0fa94e76957bc765ea` | `critical` | `human-gate` | 108 | `claude-projects` | `uncategorized` / `unclassified` | `linear-conjuring-bear` | 239 | Do not merge PR #635 as-is. Current main preserves the consolidation execution packet under docs/consolidation/ and scripts/ with stricter LIMEN_CONSOLIDATION_GATE guards; PR #635 remains a draft review artifact and should be closed or superseded by a new narrow PR only after human review. Reclaim the local checkout only after operator acceptance. |
| 7 | `7b465b869b8433b3a2b9` | `critical` | `legacy-session-review` | 101 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 518 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 8 | `83af7669196a257c99c5` | `critical` | `remote-pr-open` | 101 | `claude-projects` | `uncategorized` / `unclassified` | `ticklish-bubbling-robin` | 146 | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 9 | `629e5838eecb0d4ce8e6` | `critical` | `owner-blocker` | 100 | `claude-projects` | `uncategorized` / `unclassified` | `peer-audited--behavioral-blockchain` | 77 | No PR or remote branch preserves this exact local commit. Do not reclaim from lifecycle cleanup; create a narrow owner packet to review, push, supersede, or retire the patch. |
| 10 | `cad7d3bad2068e8d3d75` | `critical` | `historical-worktree-review` | 99 | `claude-projects` | `uncategorized` / `unclassified` | `heal-192-regression` | 782 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 11 | `8b5ddd3315c01150acd3` | `critical` | `observe` | 99 | `claude-projects` | `uncategorized` / `unclassified` | `heal-cifix-organvm-limen-435-47b10f86` | 134 | Keep active work visible; do not interrupt unless it becomes stale. |
| 12 | `9185f2b3d942774cf587` | `critical` | `legacy-session-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 410 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 13 | `dc9efdf3fcc199d66167` | `critical` | `legacy-session-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `none` | 244 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 14 | `1ecb3a7f55ff1ee9ad8a` | `critical` | `remote-pr-open` | 98 | `codex-sessions` | `uncategorized` / `unclassified` | `triptych-story` | 192 | Review draft PR #1, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| 15 | `42efa5506eb8d63d286e` | `critical` | `stalled-review` | 97 | `codex-sessions` | `session_lifecycle` / `STALLED` | `rev-styx-stripe-subscription-719b` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 16 | `510d7ae2641801545169` | `critical` | `stalled-review` | 97 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-conversation-corpus-engine-2e73` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 17 | `7d7aaea5ca651cc57a45` | `critical` | `stalled-review` | 97 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-a-organvm-a-i-chat--exporter-ci-green-0620-492b` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 18 | `83d59699ccc4171636e4` | `critical` | `stalled-review` | 97 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-organvm-mirror-mirror-ci-green-0622-98c1` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 19 | `882fcf1609d319fa4426` | `critical` | `stalled-review` | 97 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `rev-mirror-deploy-3927` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 20 | `90d8cdfb8a9edfd2527f` | `critical` | `stalled-review` | 97 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-organvm-iii-ergon--github-6819` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 21 | `f7ced0e9fe6ddf19cea6` | `critical` | `stalled-review` | 97 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-organvm-v-logos--github-3b0e` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 22 | `04447e42f5e46fdd63ba` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-054` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 23 | `1ed08eb9b4f08134011b` | `critical` | `stalled-review` | 96 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-4444j99-media-ark-ci-green-0620-0bc1` | 3 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 24 | `1f935053382b9082e22e` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-084-8712` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 25 | `333c85c9905daeec00b7` | `critical` | `stalled-review` | 96 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `bld-domus-genoma-ci-23a9` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 26 | `5660b1decb73aeabeb70` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `gh-4444j99-domus-genoma-86-8188` | 3 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 27 | `608cb53fcc509dfb243a` | `critical` | `stalled-review` | 96 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | 3 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 28 | `74823d766af1b6f62da2` | `critical` | `stalled-review` | 96 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-a-organvm-mirror-mirror-4473` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 29 | `8898eba20ac1e48cea6c` | `critical` | `stalled-review` | 96 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-a-organvm-public-record-data-scrapper-a5c1` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 30 | `95805b44782887476f1b` | `critical` | `stalled-review` | 96 | `codex-sessions` | `session_lifecycle` / `STALLED` | `resolve-organvm-i-theoria-.github-459-cd2f` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |

## Lane Task Map

| Lane | Top Band | Sessions | Prompt Events | Batches | Dominant Source | Dominant Family | Route |
|---|---|---:|---:|---:|---|---|---|
| `owner-blocker` | `critical` | 92 | 1425 | 6 | `codex-sessions` | `uncategorized` | Do not delete, reclaim, or auto-port this Claude worktree without a narrower owner packet. PR #544 merged only through f20bb66, while local HEAD 0a4f21f remains unique and changes organs/media/NEXT.md to mark operator-cleared media-ark PR/issue atoms done. Preserve this as an owner blocker; if still wanted, port only that owner-record update onto current main with a named branch and predicate. |
| `human-gate` | `critical` | 37 | 2899 | 5 | `claude-projects` | `uncategorized` | No local-only source preservation remains. Local HEAD is an ancestor of current origin/main and `git diff origin/main...HEAD` is empty. Reclaim the local checkout only after operator acceptance. |
| `remote-pr-open` | `critical` | 130 | 5651 | 8 | `claude-projects` | `uncategorized` | Review draft PR #661, then merge, supersede, or archive this lane. Local checkout is no longer the only review surface. |
| `observe` | `critical` | 46 | 413 | 3 | `claude-projects` | `uncategorized` | Keep active work visible; do not interrupt unless it becomes stale. |
| `legacy-session-review` | `critical` | 2236 | 80108 | 91 | `claude-projects` | `uncategorized` | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| `historical-worktree-review` | `critical` | 1500 | 32590 | 62 | `claude-projects` | `uncategorized` | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| `stalled-review` | `critical` | 52 | 225 | 3 | `codex-sessions` | `worktree_lifecycle` | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| `hash-review` | `critical` | 1965 | 4431 | 81 | `opencode-db` | `uncategorized` | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| `remote-proof` | `high` | 5 | 15 | 1 | `claude-projects` | `uncategorized` | Verify remote/default preservation; reclaim local checkout only after exact proof. |
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
