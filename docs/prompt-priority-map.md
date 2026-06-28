# Prompt Priority Map

Generated: `2026-06-28T04:02:30+00:00`

## Canonical Decision

- The long-running unit is a review batch, not a chat-length mega-prompt.
- Every prompt-like event is represented by a hash in the private map; tracked docs show only counts, session keys, lanes, and routes.
- A batch becomes dispatchable only after it has an owner repo or owner ledger, bounded next action, no raw-secret dependency, and a verification or blocker receipt.
- Credential/auth/secret lanes stay parked unless a scoped task directly requires non-secret preparation.

## Coverage

- Prompt lifecycle source files: `9489`.
- Prompt-like events from source ledger: `92795`.
- Prioritized session receipts: `3423`.
- Prioritized prompt events: `92795`.
- Unique prompt hashes: `55781`.
- Review batches: `152`.
- Codex classified sessions: `887`.
- Attack paths / blockers / capability items: `30` / `8` / `30`.
- Source mix: `claude-projects` 2400, `codex-sessions` 889, `claude-tasks` 133.
- Band mix: `low` 1336, `medium` 1300, `parked` 405, `high` 256, `critical` 126.
- Lane mix: `legacy-session-review` 1705, `historical-worktree-review` 819, `family` 419, `parked-secret` 405, `stalled-review` 58, `owner-blocker` 4.

## Priority Model

- Highest: stalled or active receipts tied to high-ranked attack paths, worktree preservation risk, repeated prompt hashes, and recent activity.
- Middle: legacy Claude/Codex sessions that need private sampling and owner-ledger promotion.
- Lowest: closed, already-parked, or credential/auth work unless directly blocking a selected path.
- The private JSON keeps the complete sorted hash/session map; this Markdown intentionally shows a bounded operator slice.

## Review Batches

| Rank | Batch | Band | Lane | Sessions | Prompt Events | Unique Prompts | Dominant Mix | Route |
|---:|---|---|---|---:|---:|---:|---|---|
| 1 | `prompt-batch-critical-owner-blocker-001` | `critical` | `owner-blocker` | 3 | 103 | 76 | sources claude-projects 2, codex-sessions 1; families uncategorized 2, worktree_lifecycle 1 | Classify whether this is an intentional migration, incomplete checkout, or generated deletion bug before cleanup, PR creation, or delegation. |
| 2 | `prompt-batch-critical-stalled-review-001` | `critical` | `stalled-review` | 25 | 108 | 69 | sources codex-sessions 25; families worktree_lifecycle 14, session_lifecycle 11 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 3 | `prompt-batch-critical-historical-worktree-review-001` | `critical` | `historical-worktree-review` | 25 | 3747 | 2450 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 4 | `prompt-batch-critical-remote-proof-001` | `critical` | `remote-proof` | 2 | 78 | 56 | sources claude-projects 1, codex-sessions 1; families uncategorized 1, session_lifecycle 1 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 5 | `prompt-batch-critical-stalled-review-002` | `critical` | `stalled-review` | 17 | 77 | 50 | sources codex-sessions 17; families github_review 12, session_lifecycle 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 6 | `prompt-batch-critical-legacy-session-review-001` | `critical` | `legacy-session-review` | 25 | 18681 | 9700 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 7 | `prompt-batch-critical-legacy-session-review-002` | `critical` | `legacy-session-review` | 16 | 4927 | 2872 | sources claude-projects 16; families uncategorized 16 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 8 | `prompt-batch-critical-historical-worktree-review-002` | `critical` | `historical-worktree-review` | 13 | 1248 | 849 | sources claude-projects 13; families uncategorized 13 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 9 | `prompt-batch-high-legacy-session-review-001` | `high` | `legacy-session-review` | 25 | 7410 | 4378 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 10 | `prompt-batch-high-historical-worktree-review-001` | `high` | `historical-worktree-review` | 25 | 2047 | 1271 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 11 | `prompt-batch-high-stalled-review-001` | `high` | `stalled-review` | 16 | 67 | 35 | sources codex-sessions 16; families agent_coordination 9, technical_debt_ci 3, session_lifecycle 2, uncategorized 2 | Packetize bounded work; do not dispatch broad sprawl prompts. |
| 12 | `prompt-batch-high-historical-worktree-review-002` | `high` | `historical-worktree-review` | 25 | 1851 | 1213 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 13 | `prompt-batch-high-legacy-session-review-002` | `high` | `legacy-session-review` | 25 | 2920 | 2310 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 14 | `prompt-batch-high-remote-close-001` | `high` | `remote-close` | 3 | 88 | 58 | sources claude-projects 2, codex-sessions 1; families uncategorized 2, github_review 1 | Review PR state/checks, then merge or name supersession before local reclaim. |
| 15 | `prompt-batch-high-historical-worktree-review-003` | `high` | `historical-worktree-review` | 25 | 1699 | 1106 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 16 | `prompt-batch-high-observe-001` | `high` | `observe` | 2 | 150 | 101 | sources claude-projects 2; families uncategorized 2 | Keep active work visible; do not interrupt unless it becomes stale. |
| 17 | `prompt-batch-high-documented-residue-001` | `high` | `documented-residue` | 1 | 94 | 64 | sources claude-projects 1; families uncategorized 1 | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| 18 | `prompt-batch-high-owner-blocker-001` | `high` | `owner-blocker` | 1 | 5 | 4 | sources codex-sessions 1; families session_lifecycle 1 | Classify against the current organvm/.github default branch before cleanup or delegation; direct PR is blocked because the touched workflow files are absent on the force-updated default history. |
| 19 | `prompt-batch-high-historical-worktree-review-004` | `high` | `historical-worktree-review` | 25 | 1529 | 931 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 20 | `prompt-batch-high-historical-worktree-review-005` | `high` | `historical-worktree-review` | 25 | 1369 | 873 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 21 | `prompt-batch-high-historical-worktree-review-006` | `high` | `historical-worktree-review` | 25 | 1361 | 891 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 22 | `prompt-batch-high-hash-review-001` | `high` | `hash-review` | 1 | 440 | 327 | sources codex-history 1; families uncategorized 1 | Review the redacted `codex-history` receipt privately and assign an owner route before delegation. |
| 23 | `prompt-batch-high-historical-worktree-review-007` | `high` | `historical-worktree-review` | 25 | 1258 | 806 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 24 | `prompt-batch-high-historical-worktree-review-008` | `high` | `historical-worktree-review` | 5 | 282 | 197 | sources claude-projects 5; families uncategorized 5 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 25 | `prompt-batch-high-legacy-session-review-003` | `high` | `legacy-session-review` | 2 | 157 | 145 | sources claude-projects 2; families uncategorized 2 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 26 | `prompt-batch-medium-legacy-session-review-001` | `medium` | `legacy-session-review` | 25 | 1532 | 1327 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 27 | `prompt-batch-medium-historical-worktree-review-001` | `medium` | `historical-worktree-review` | 25 | 1184 | 747 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 28 | `prompt-batch-medium-hash-review-001` | `medium` | `hash-review` | 2 | 46 | 15 | sources codex-sessions 2; families uncategorized 2 | Review the redacted `codex-sessions` receipt privately and assign an owner route before delegation. |
| 29 | `prompt-batch-medium-historical-worktree-review-002` | `medium` | `historical-worktree-review` | 25 | 1051 | 731 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 30 | `prompt-batch-medium-historical-worktree-review-003` | `medium` | `historical-worktree-review` | 25 | 972 | 668 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 31 | `prompt-batch-medium-family-001` | `medium` | `family` | 25 | 135 | 77 | sources codex-sessions 25; families worktree_lifecycle 23, session_lifecycle 2 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 32 | `prompt-batch-medium-historical-worktree-review-004` | `medium` | `historical-worktree-review` | 25 | 1017 | 705 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 33 | `prompt-batch-medium-historical-worktree-review-005` | `medium` | `historical-worktree-review` | 25 | 885 | 639 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 34 | `prompt-batch-medium-legacy-session-review-002` | `medium` | `legacy-session-review` | 25 | 1326 | 1164 | sources claude-projects 25; families uncategorized 25 | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| 35 | `prompt-batch-medium-historical-worktree-review-006` | `medium` | `historical-worktree-review` | 25 | 809 | 641 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 36 | `prompt-batch-medium-remote-close-001` | `medium` | `remote-close` | 1 | 20 | 11 | sources claude-projects 1; families uncategorized 1 | Review PR state/checks, then merge or name supersession before local reclaim. |
| 37 | `prompt-batch-medium-historical-worktree-review-007` | `medium` | `historical-worktree-review` | 25 | 906 | 567 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 38 | `prompt-batch-medium-historical-worktree-review-008` | `medium` | `historical-worktree-review` | 25 | 820 | 601 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 39 | `prompt-batch-medium-historical-worktree-review-009` | `medium` | `historical-worktree-review` | 25 | 696 | 487 | sources claude-projects 25; families uncategorized 25 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 40 | `prompt-batch-medium-family-002` | `medium` | `family` | 25 | 90 | 61 | sources codex-sessions 25; families session_lifecycle 16, github_review 9 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |

## Top Session Receipts

| Rank | Session Key | Band | Lane | Score | Source | Family / State | Worktree | Prompt Events | Next Action |
|---:|---|---|---|---:|---|---|---|---:|---|
| 1 | `9f6b8896a69bbb27c009` | `critical` | `owner-blocker` | 119 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | 73 | Classify whether this is an intentional migration, incomplete checkout, or generated deletion bug before cleanup, PR creation, or delegation. |
| 2 | `5bceb564a24c59faf63c` | `critical` | `stalled-review` | 106 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-a-organvm-a-i-chat--exporter-ci-green-0620-492b` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 3 | `975fcc5c2f1e78cb30c5` | `critical` | `stalled-review` | 106 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-organvm-mirror-mirror-ci-green-0622-98c1` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 4 | `cad7d3bad2068e8d3d75` | `critical` | `historical-worktree-review` | 105 | `claude-projects` | `uncategorized` / `unclassified` | `heal-192-regression` | 782 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 5 | `6319eb873eb2ed878896` | `critical` | `stalled-review` | 105 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-organvm-a-i-chat--exporter-ci-green-0622-4a4f` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 6 | `8ef2af43c35455b96d8e` | `critical` | `remote-proof` | 104 | `claude-projects` | `uncategorized` / `unclassified` | `gh-organvm-object-lessons-19-605a` | 73 | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| 7 | `5afdcea913650fa453d2` | `critical` | `historical-worktree-review` | 102 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-portfolio-test-coverage-0627-2931` | 113 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 8 | `8f2a4458a19128c966fe` | `critical` | `historical-worktree-review` | 101 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-domus-genoma-security-0627-b9ed` | 107 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 9 | `2d87d3d6120e585dcf99` | `critical` | `stalled-review` | 100 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-organvm-iii-ergon--github-6819` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 10 | `97936cf112edd566fab1` | `critical` | `stalled-review` | 100 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-organvm-v-logos--github-3b0e` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 11 | `efefc12afc137f75455b` | `critical` | `stalled-review` | 100 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `rev-mirror-deploy-3927` | 5 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 12 | `9491f01ba49706d8bca5` | `critical` | `historical-worktree-review` | 99 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-the-invisible-ledger-typing-0626-fb12` | 301 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 13 | `051401e0b765e77fbb04` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `bld-writelens-ci-9c3b` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 14 | `0f80a8b2fff6c2b0990d` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-a-organvm-public-record-data-scrapper-a5c1` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 15 | `25db5ecad5a24d2052ef` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `bld2-peer-audited--behavioral-blockchain-integration-tests-c82f` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 16 | `3e61b3a42462f291efa7` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-4444j99-domus-genoma-07e2` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 17 | `49c3236f515814e83ed0` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-conversation-corpus-engine-2e73` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 18 | `52a3197f95915d0262a9` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `bld-domus-genoma-ci-23a9` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 19 | `7bc21d2319c0becc8dc0` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `rev-styx-stripe-subscription-719b` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 20 | `86af038939f541f0cc00` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `gen-4444j99-media-ark-ci-green-0620-0bc1` | 3 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 21 | `88d1c646b67a6ef82218` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-a-organvm-mirror-mirror-4473` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 22 | `9e3302db88293f94a488` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-sovereign--ground-34de` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 23 | `9e95b555d72c21e03223` | `critical` | `stalled-review` | 99 | `codex-sessions` | `session_lifecycle` / `STALLED` | `bld-peer-audited--behavioral-blockchain-ci-706e` | 5 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 24 | `a7b42860bf42f8fb791f` | `critical` | `stalled-review` | 99 | `codex-sessions` | `worktree_lifecycle` / `STALLED` | `bld-domus-genoma-ci-ec4f` | 4 | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| 25 | `30430506c7f63f021904` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `rev-organvm-public-record-data-scrapper-revenue-readiness-0626-6d93` | 137 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 26 | `6f85af70c8b7c2aa59d4` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-a-i-chat--exporter-typing-0624-5bd9` | 125 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 27 | `82b6bf7f5cf6c4f5c517` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-domus-genoma-security-0626-5961` | 166 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 28 | `8cdf7b189043e65a730c` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-public-record-data-scrapper-ci-green-0625-ec9e` | 118 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 29 | `c54a97d270a56014657e` | `critical` | `historical-worktree-review` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-public-record-data-scrapper-security-0626-6c09` | 197 | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| 30 | `76b420912a423fa085a8` | `critical` | `owner-blocker` | 98 | `claude-projects` | `uncategorized` / `unclassified` | `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | 27 | Classify whether this is an intentional migration, incomplete checkout, or generated deletion bug before cleanup, PR creation, or delegation. |
| 31 | `0da770169830d2e25a55` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `resolve-a-organvm-peer-audited--behavioral-blockchain-714-6648` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 32 | `0f1862fbac5e43c4ebcf` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `resolve-a-organvm-the-invisible-ledger-4-68a9` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 33 | `1e91bfdf2d9519aa4343` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `resolve-a-organvm-the-invisible-ledger-6-b8dd` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 34 | `21b24f831030fdd82fb5` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-organvm-i-theoria-conversation-corpus-engine-ee1d` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 35 | `27c92b31ca08bc9bd700` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `resolve-organvm-i-theoria-.github-459-cd2f` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 36 | `49d1c148af42651fc860` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-099` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 37 | `58c20119ea3d81efc71e` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `cifix-a-organvm-peer-audited--behavioral-blockchain-3887` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 38 | `6cf13afbcf7cb2d144f4` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-084-8712` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 39 | `6e9ffdf3b05b2aea3284` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `limen-054` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
| 40 | `7385a82f1cbd54d7c08c` | `critical` | `stalled-review` | 98 | `codex-sessions` | `session_lifecycle` / `STALLED` | `gh-a-organvm-organvm-corpvs-testamentvm-494-0388` | 4 | Keep corpus/session ledgers current, collapse repeats into owner receipts. |

## Lane Task Map

| Lane | Top Band | Sessions | Prompt Events | Batches | Dominant Source | Dominant Family | Route |
|---|---|---:|---:|---:|---|---|---|
| `owner-blocker` | `critical` | 4 | 108 | 2 | `claude-projects` | `uncategorized` | Classify whether this is an intentional migration, incomplete checkout, or generated deletion bug before cleanup, PR creation, or delegation. |
| `stalled-review` | `critical` | 58 | 252 | 3 | `codex-sessions` | `session_lifecycle` | Preserve dirty or missing-remote roots, then reclaim duplicate local state. |
| `historical-worktree-review` | `critical` | 819 | 29499 | 35 | `claude-projects` | `uncategorized` | Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof. |
| `remote-proof` | `critical` | 2 | 78 | 1 | `claude-projects` | `uncategorized` | Verify remote/default preservation; reclaim local checkout only after exact proof. |
| `legacy-session-review` | `critical` | 1705 | 57942 | 70 | `claude-projects` | `uncategorized` | Sample the private source file, extract durable atoms, then route to an owner ledger. |
| `remote-close` | `high` | 4 | 108 | 2 | `claude-projects` | `uncategorized` | Review PR state/checks, then merge or name supersession before local reclaim. |
| `observe` | `high` | 3 | 155 | 2 | `claude-projects` | `uncategorized` | Keep active work visible; do not interrupt unless it becomes stale. |
| `documented-residue` | `high` | 1 | 94 | 1 | `claude-projects` | `uncategorized` | No unique source to preserve; directory contains only Vite dependency-cache metadata. Reclaim only after normal operator acceptance. |
| `hash-review` | `high` | 3 | 486 | 2 | `codex-sessions` | `uncategorized` | Review the redacted `codex-history` receipt privately and assign an owner route before delegation. |
| `family` | `medium` | 419 | 1573 | 17 | `codex-sessions` | `github_review` | Keep corpus/session ledgers current, collapse repeats into owner receipts. |
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
