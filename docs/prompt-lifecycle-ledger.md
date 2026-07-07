# Prompt Lifecycle Ledger

Generated: `2026-07-07T00:13:03+00:00`
Horizon: `all local history`

## Canonical Decision

- A human prompt/session is a lifecycle seed. Work that starts from it must end in a named outcome: merged, pushed PR, preserved branch, owner-recorded blocker, named supersession, archived task, or documented non-source residue.
- Raw personal/session material belongs in `.limen-private/session-corpus/`; tracked ledgers must stay redacted and receipt-oriented.
- Screenshots are coverage hints. The canonical absorptive layer is the local app/session filesystem plus private cartridge materialization.
- Worktree cleanup is subordinate to prompt lifecycle: no unique work is removed just because a directory is inconvenient.

## Redacted Prompt Coverage

Indexed `15590` app/session files, `4.5 GiB`, with `136694` prompt-like user events hashed into the private index.
Normalized task-body payload covered `266.5 MiB` after stripping recognized scaffold-only prompt frames.

| Source | Files/Sessions | Prompt Events | Prompt Bytes | Task Body Bytes | Event Records | Size | Newest |
|---|---:|---:|---:|---:|---:|---:|---|
| `claude-projects` | 6755 | 124922 | 250.9 MiB | 243.8 MiB | 475433 | 1.9 GiB | `2026-07-07T00:00:53+00:00` |
| `codex-sessions` | 1518 | 8415 | 21.8 MiB | 14.8 MiB | 589192 | 1.6 GiB | `2026-07-07T00:04:46+00:00` |
| `opencode-db` | 1486 | 1493 | 4.3 MiB | 4.3 MiB | 82239 | 0 B | `2026-07-07T00:04:58+00:00` |
| `codex-history` | 1 | 1171 | 731.3 KiB | 731.2 KiB | 1171 | 844.6 KiB | `2026-07-06T23:54:52+00:00` |
| `agy-cli-conversations` | 501 | 481 | 2.8 MiB | 2.8 MiB | 32046 | 865.0 MiB | `2026-07-07T00:00:51+00:00` |
| `claude-tasks` | 206 | 138 | 32.2 KiB | 32.2 KiB | 138 | 59.9 KiB | `2026-07-03T15:47:52+00:00` |
| `agy-cli-history` | 2 | 44 | 10.7 KiB | 10.7 KiB | 5755 | 1.5 MiB | `2026-07-06T20:05:27+00:00` |
| `gemini-tmp-agy` | 15 | 30 | 267.0 KiB | 9.9 KiB | 60 | 280.8 KiB | `2026-06-30T14:29:59+00:00` |
| `claude-file-history` | 5059 | 0 | 0 B | 0 B | 0 | 67.2 MiB | `2026-07-05T18:01:34+00:00` |
| `claude-plans` | 43 | 0 | 0 B | 0 B | 0 | 369.8 KiB | `2026-07-03T15:08:54+00:00` |
| `codex-attachments` | 4 | 0 | 0 B | 0 B | 0 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |

## Prompt Body Mix

| Body Kind | Prompt Events |
|---|---:|
| `direct` | 130675 |
| `flame_scaffold` | 3345 |
| `flame_with_task_body` | 2659 |
| `session_context` | 15 |

## Prompt To Worktree Crosswalk

- Current `.limen-worktrees` roots scanned: `524`; debt roots: `63`.
- Current worktree roots with at least one local session/prompt receipt: `335`.
- Current worktree roots without a local session receipt in this index: `189`.

| Worktree Root | Session Files | Prompt Events | Debt Reason |
|---|---:|---:|---|
| `agent-aefc63d95daa3131b` | 2 | 31 | `owner-blocker` |
| `bld-my--father-mother-harden-44b2` | 1 | 5 | `remote-pr-open` |
| `bld-promptscope-next-rev-3fde` | 1 | 4 | `remote-pr-open` |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | 3 | 79 | `remote-pr-open` |
| `discover-organvm-browser-state-a15688df` | 0 | 0 | `active(<6h)` |
| `discover-organvm-cind-and-sol-foundation-1f04e5fe` | 0 | 0 | `active(<6h)` |
| `discover-organvm-gens-ce1d73b7` | 0 | 0 | `active(<6h)` |
| `discover-organvm-kerygma-profiles-6c74` | 1 | 24 | `remote-pr-open` |
| `discover-organvm-pages--theoria-copy--ergon-3ff3933b` | 0 | 0 | `active(<6h)` |
| `discover-organvm-pages--theoria-copy--kerygma-61b952b3` | 0 | 0 | `active(<6h)` |
| `discover-organvm-pages--theoria-copy--logos-340cb28c` | 0 | 0 | `active(<6h)` |
| `discover-organvm-palimpsest-718249e2` | 0 | 0 | `active(<6h)` |
| `discover-organvm-sovereign--ground--4444j99-0f507a63` | 0 | 0 | `active(<6h)` |
| `domus-quarantine-retire-20260629` | 10 | 84 | `remote-pr-open` |
| `feat+workstream-channels` | 2 | 47 | `remote-pr-open` |
| `feat-gcp-sa-organ` | 13 | 727 | `owner-blocker` |
| `financial-codex-finish-0704` | 0 | 0 | `remote-pr-open` |
| `fluttering-twirling-abelson` | 8 | 430 | `remote-merged` |
| `gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec` | 1 | 5 | `owner-blocker` |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | 3 | 100 | `owner-blocker` |
| `gh-4444j99-hokage-chess-39-25daa3dd` | 0 | 0 | `dirty` |
| `gh-4444j99-hokage-chess-39-c15d2ce9` | 0 | 0 | `dirty` |
| `gh-organvm-domus-genoma-170-bbbc` | 0 | 0 | `remote-merged` |
| `heal-cifix-organvm-a-i--skills-26-90acdfa8` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i--skills-27-07bf31e9` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-a-i--skills-27-7d6c0216` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-a-i--skills-27-7ed7339a` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-a-i--skills-27-8f4677cb` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-a-i--skills-27-a88b2381` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i--skills-27-b9ecf630` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i--skills-27-d0df3765` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i--skills-27-f0edd746` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i--skills-27-f7577686` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i--skills-27-fff625ac` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-a-i--skills-28-aa405c3d` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i--skills-28-d93d775c` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i--skills-29-6209335e` | 1 | 4 | `not-merged-to-default` |
| `heal-cifix-organvm-a-i-chat--exporter-49-102d97d6` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i-chat--exporter-49-1992eb0d` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i-chat--exporter-54-220ff315` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i-chat--exporter-54-3049e7fb` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-a-i-chat--exporter-54-cac20ffd` | 1 | 4 | `not-merged-to-default` |
| `heal-cifix-organvm-a-i-council--coliseum-175-e675406b` | 1 | 131 | `active(<6h)` |
| `heal-cifix-organvm-a-i-council--coliseum-177-f2be6be4` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-atomic-substrata-4-41b9ec96` | 1 | 68 | `active(<6h)` |
| `heal-cifix-organvm-bountyscope-13-3199dbf4` | 1 | 36 | `active(<6h)` |
| `heal-cifix-organvm-bountyscope-14-f7b2ff23` | 1 | 37 | `active(<6h)` |
| `heal-cifix-organvm-bountyscope-8-2120cf4d` | 1 | 47 | `active(<6h)` |
| `heal-cifix-organvm-call-function--ontological-10-ad14b431` | 2 | 41 | `active(<6h)` |
| `heal-cifix-organvm-community-hub-9-48838101` | 1 | 43 | `active(<6h)` |
| `heal-cifix-organvm-community-hub-9-b78c10e5` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-134-79bb0602` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-135-c093cc45` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-136-12ee50f4` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-136-2c2c192c` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-136-32638a2c` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-136-5448713c` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-136-6a8c088f` | 1 | 112 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-137-1fcfca82` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-138-422787bb` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-138-6cb82894` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-138-d81d092f` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-139-3c02468a` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-140-e28cc056` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-141-0f57388a` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-141-70e4ccde` | 1 | 101 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-141-d5c1d0f6` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-141-e43baa15` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-142-194f0277` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-142-2548098e` | 1 | 61 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-142-47b084ef` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-142-9acd5d5c` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-143-d5587a4e` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-145-b06f5919` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-146-0bb5970c` | 3 | 99 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-146-22877d48` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-146-49a1e04b` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-146-89c46870` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-146-9dc2db2e` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-148-3f088c21` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-149-63beaf51` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-149-8df127df` | 1 | 118 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-149-9f9060b8` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-149-b73c4ce9` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-149-d5e7f4d5` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-149-e0f24a23` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-150-1c22d9db` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-150-7af8143e` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-150-c9c434aa` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-152-10b45a9f` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-152-aaa842d9` | 1 | 92 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-152-d3af5bd7` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-153-0c7ac0c8` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-153-451788bb` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-153-469ca57e` | 1 | 45 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-153-52799968` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-153-eb2b9ba6` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-154-0d7fe61f` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-154-0d80d55c` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-154-35479caf` | 1 | 78 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-155-2721d52d` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-155-83292900` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-155-ac07fcb1` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-155-f2f394b3` | 1 | 103 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-157-088ea9fb` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-157-baceffbf` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-157-e92cc6f4` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-159-2cfdfff6` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-159-615266b7` | 1 | 82 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-159-97fee589` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-domus-genoma-159-da75ada8` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-growth-auditor-11-0e5131c4` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-growth-auditor-11-ddbe8b4c` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-growth-auditor-12-610fe0a5` | 2 | 74 | `active(<6h)` |
| `heal-cifix-organvm-growth-auditor-13-1d41d80b` | 2 | 53 | `active(<6h)` |
| `heal-cifix-organvm-growth-auditor-13-bc0b11cc` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-growth-auditor-14-87e185fb` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-growth-auditor-16-aa9e65aa` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-growth-auditor-17-05e37ea2` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-limen-421-8f14068b` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-422-0a0aae09` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-422-3a71d824` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-422-3c1a44a2` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-limen-422-5764e9ef` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-422-6b0c8ca2` | 1 | 4 | `dirty` |
| `heal-cifix-organvm-limen-422-94534247` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-422-be9eb353` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-422-eda116ed` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-423-354fa844` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-limen-423-40984048` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-limen-423-47a6f9ec` | 1 | 126 | `unpushed-commits` |
| `heal-cifix-organvm-limen-423-e48b35df` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-limen-424-8db5dab0` | 1 | 4 | `dirty` |
| `heal-cifix-organvm-limen-425-0597e483` | 1 | 4 | `not-merged-to-default` |
| `heal-cifix-organvm-limen-425-164d86db` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-425-713511d7` | 1 | 5 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-425-9c743c2c` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-425-db11388b` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-426-0ff7babe` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-426-4aab452b` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-426-6e741804` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-426-71ba33ff` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-426-71c5627d` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-426-756e0f5d` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-426-92e122fb` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-426-a93cb119` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-426-b1a41cda` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-426-d270c2a2` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-426-d7a0e516` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-427-42616f71` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-427-568b73c9` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-427-5f8bb97d` | 0 | 0 | `not-merged-to-default` |
| `heal-cifix-organvm-limen-427-a7bd2bb9` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-428-0079823c` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-428-01f73e57` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-428-2ae62246` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-428-4b320e87` | 1 | 4 | `dirty` |
| `heal-cifix-organvm-limen-428-544b47af` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-428-ad4f755d` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-428-dbe8a466` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-428-e3e2925e` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-428-e536788e` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-429-4471ceb2` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-limen-429-89a0a2b4` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-429-bf5b90ab` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-430-0a5c6bc2` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-430-1738f072` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-430-29605f83` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-430-61bd3388` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-430-7c7129d9` | 1 | 4 | `dirty` |
| `heal-cifix-organvm-limen-430-955f9dd1` | 1 | 4 | `unpushed-commits` |
| `heal-cifix-organvm-limen-430-a14ed351` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-430-af02d89e` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-430-b979134a` | 1 | 4 | `not-merged-to-default` |
| `heal-cifix-organvm-limen-431-11bda3f4` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-431-58a1e655` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-431-6eac4607` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-431-6ee61f31` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-431-749c4e36` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-431-d068660e` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-432-00cf570a` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-432-06bf02c7` | 1 | 4 | `not-merged-to-default` |
| `heal-cifix-organvm-limen-432-19e5f605` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-432-a9af57ee` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-433-32e25f35` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-433-aba31b6f` | 1 | 4 | `unpushed-commits` |
| `heal-cifix-organvm-limen-434-2f84fe31` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-434-3d7b65ff` | 0 | 0 | `not-merged-to-default` |
| `heal-cifix-organvm-limen-434-529e2e6d` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-434-a0692202` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-434-b6e642da` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-limen-435-401dee02` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-435-47b10f86` | 1 | 134 | `unpushed-commits` |
| `heal-cifix-organvm-limen-435-8d8df7c4` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-435-b69ba98c` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-435-c14f845c` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-435-fa00a596` | 1 | 9 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-436-3b707e9b` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-436-4702c4dc` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-436-609efb0e` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-436-6c1766c9` | 1 | 55 | `active(<6h)` |
| `heal-cifix-organvm-limen-436-b9f684dd` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-436-ffaf1582` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-437-59c98bd8` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-437-91307a5b` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-437-a869092b` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-437-ae361281` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-438-260ee687` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-438-7e4c81d1` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-438-899cbaa9` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-438-980dae49` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-438-d70e6c75` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-438-da3b854e` | 1 | 4 | `dirty` |
| `heal-cifix-organvm-limen-438-f0f9ba29` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-438-fcc35eed` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-limen-439-0851d4aa` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-439-4583ba76` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-439-9e5ed9f8` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-439-b17fd83a` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-440-735e22cd` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-440-c16aa072` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-440-f537a8e3` | 0 | 0 | `not-merged-to-default` |
| `heal-cifix-organvm-limen-440-f9739c3e` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-441-7c31138a` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-limen-441-c60154a0` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-442-1b11af92` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-442-3902a00d` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-442-41ea2f93` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-442-4ddd8c37` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-442-c9d99871` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-442-cb861a12` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-443-4e67ed4e` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-443-5476c544` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-443-9cd88b5e` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-443-c22de24a` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-443-ee755868` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-444-32af06e6` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-444-a00aa985` | 1 | 4 | `dirty` |
| `heal-cifix-organvm-limen-444-d3ea6fe8` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-limen-444-d6220f0e` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-445-08a8f4b2` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-445-4f8beb6f` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-445-7282d149` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-446-0862daaa` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-446-4dfb7f88` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-446-76408b03` | 1 | 85 | `active(<6h)` |
| `heal-cifix-organvm-limen-446-acc60adb` | 1 | 1 | `clean+merged+idle` |
| `heal-cifix-organvm-limen-446-c3c48d16` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-100-34862f7f` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-100-88b1e47c` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-104-28912ebe` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-104-5198c1b2` | 2 | 86 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-70-916a1157` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-71-5bd74193` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-71-6877a3e2` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-71-955f0971` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-71-d83257ef` | 2 | 102 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-77-6e70554b` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-77-c105b09b` | 1 | 86 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-77-d31a3fdd` | 1 | 90 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-79-7fbbb01a` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-79-ae77e382` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-79-c0509fb7` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-83-29f6eefc` | 2 | 49 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-83-6c728f6b` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-83-8dd8a3bf` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-86-0470da42` | 1 | 71 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-86-05676968` | 1 | 28 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-86-45ff622e` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-86-68597dae` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-90-028f12b1` | 2 | 159 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-90-b2321100` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-93-3e3f59d1` | 2 | 84 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-93-692692a9` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-93-7dfcb32a` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-94-543799cf` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-94-7890f8b6` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-94-802b94e1` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-95-10d60bab` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-95-20f0cd1b` | 1 | 101 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-95-47edfa17` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-mirror-mirror-95-49e2a3f0` | 1 | 80 | `active(<6h)` |
| `heal-cifix-organvm-my--father-mother-19-6a175061` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-my--father-mother-19-7988886d` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-my--father-mother-21-17cd7d29` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-my--father-mother-21-5fcb223d` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-my--father-mother-21-fd6a0ac5` | 3 | 116 | `active(<6h)` |
| `heal-cifix-organvm-narratological-algorithmic-lenses-36-b62cbab8` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-narratological-algorithmic-lenses-36-faf77525` | 1 | 63 | `active(<6h)` |
| `heal-cifix-organvm-nexus--babel-alexandria-125-306fcd79` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-nexus--babel-alexandria-125-e175f665` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-organvm-corpvs-testamentvm-511-cc58b96d` | 2 | 67 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-105-0b8f68ed` | 1 | 26 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-105-a7fcb622` | 1 | 58 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-110-cf645ef4` | 1 | 52 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-124-e0bb2d06` | 0 | 0 | `remote-merged` |
| `heal-cifix-organvm-organvm-engine-130-8a6060e4` | 0 | 0 | `remote-pr-open` |
| `heal-cifix-organvm-organvm-engine-130-ec1fdfaf` | 0 | 0 | `remote-pr-open` |
| `heal-cifix-organvm-organvm-engine-136-c3d543d8` | 0 | 0 | `owner-blocker` |
| `heal-cifix-organvm-organvm-engine-139-11d32b27` | 0 | 0 | `remote-pr-open` |
| `heal-cifix-organvm-organvm-engine-139-9dbf53bf` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-engine-139-b438a568` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-engine-143-a164221c` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-engine-144-0ef4c596` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-engine-144-6ffd7057` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-engine-144-e2096564` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-ontologia-10-0356e4b9` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-10-64603ca7` | 0 | 0 | `unpushed-commits` |
| `heal-cifix-organvm-organvm-ontologia-10-be8406e3` | 1 | 4 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-11-2978d499` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-11-55899198` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-ontologia-11-a86cf99f` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-11-f753ad04` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-12-2c2c85ba` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-12-c16ea5ad` | 0 | 0 | `not-merged-to-default` |
| `heal-cifix-organvm-organvm-ontologia-13-517e2cb9` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-13-5364f697` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-ontologia-13-953633bb` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-13-c96051e5` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-13-ebb63927` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-public-process-27-b0270e71` | 1 | 4 | `not-merged-to-default` |
| `heal-cifix-organvm-public-process-28-623757d1` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-process-28-6f74f785` | 1 | 4 | `unpushed-commits` |
| `heal-cifix-organvm-public-process-28-8f2fcfb3` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-public-process-29-14210afa` | 1 | 4 | `not-merged-to-default` |
| `heal-cifix-organvm-public-process-30-2b47c833` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-public-process-30-40a0fb19` | 1 | 76 | `active(<6h)` |
| `heal-cifix-organvm-public-process-30-59ffa133` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-process-30-81b7e012` | 2 | 47 | `active(<6h)` |
| `heal-cifix-organvm-public-process-30-a53c362c` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-public-process-31-20476025` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-public-process-31-2cb162ea` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-public-process-31-42c38b3d` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-public-process-31-5a5632ef` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-public-process-31-ccd6cf45` | 1 | 58 | `active(<6h)` |
| `heal-cifix-organvm-public-process-31-cfc2a87e` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-process-33-319b4349` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-public-process-33-47cc8080` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-process-33-6d0bb144` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-public-process-33-ac0cc087` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-process-33-cb1d50b3` | 1 | 52 | `active(<6h)` |
| `heal-cifix-organvm-public-process-33-e4144c00` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-public-process-33-f04f03c5` | 1 | 37 | `active(<6h)` |
| `heal-cifix-organvm-public-process-34-61614a22` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-public-process-34-752f6f37` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-process-34-90c17525` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-public-process-34-b0f362dc` | 2 | 65 | `active(<6h)` |
| `heal-cifix-organvm-public-process-34-db165650` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-public-record-data-scrapper-315-92684314` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-record-data-scrapper-315-ac6c61f8` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-record-data-scrapper-315-d69452a0` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-record-data-scrapper-337-9a71dedd` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-public-record-data-scrapper-337-cf34b72a` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-public-record-data-scrapper-338-2d4c55b7` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-public-record-data-scrapper-338-39c66ec8` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-recursive-engine--generative-entity-15-18929ff6` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-recursive-engine--generative-entity-15-6f03ec2d` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-recursive-engine--generative-entity-15-a915d1fb` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-schema-definitions-7-4535f14e` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-schema-definitions-7-535c5b92` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-schema-definitions-7-9edff626` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-schema-definitions-7-f11dac25` | 1 | 9 | `active(<6h)` |
| `heal-cifix-organvm-system-governance-framework-41-90094af7` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-system-governance-framework-43-92be8b62` | 1 | 46 | `active(<6h)` |
| `heal-cifix-organvm-system-governance-framework-43-e369b224` | 1 | 61 | `active(<6h)` |
| `heal-cifix-organvm-tab-bookmark-manager-28-7db92014` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-tab-bookmark-manager-28-c39923bb` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-31-46d7cceb` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-31-b0ae2dce` | 2 | 48 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-31-ff889566` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-39-15c4bcf0` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-39-50be9f89` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-41-682764a8` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-41-92bdce89` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-42-07e936e9` | 2 | 68 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-46-1eecc65a` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-46-93aec92b` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-46-c9301f3f` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-47-c07b6c24` | 5 | 52 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-47-eb3de1fa` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-57-99c7f8a5` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-57-fdd43ffc` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-58-b9160ce8` | 1 | 1 | `active(<6h)` |
| `heal-cifix-organvm-the-invisible-ledger-59-cd5f956f` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-trendpulse-8-90939f40` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-universal-mail--automation-118-26b3e882` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-universal-mail--automation-118-9f686157` | 2 | 101 | `active(<6h)` |
| `heal-cifix-organvm-universal-node-network-7-58e7652e` | 1 | 69 | `active(<6h)` |
| `heal-cifix-organvm-universal-node-network-9-570847b2` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-vigiles-aeternae--agon-cosmogonicum-7-997907fd` | 1 | 27 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-103-e7e058ff` | 0 | 0 | `dirty` |
| `heal-rebase-4444j99-hokage-chess-103-f5b1e4f4` | 1 | 3 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-107-a1b561eb` | 0 | 0 | `unpushed-commits` |
| `heal-rebase-4444j99-hokage-chess-107-f3a0ded1` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-108-6253b273` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-108-9266466c` | 1 | 3 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-114-fb8e1c94` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-121-22d63bd9` | 1 | 4 | `unpushed-commits` |
| `heal-rebase-4444j99-hokage-chess-121-89f977f6` | 1 | 3 | `not-merged-to-default` |
| `heal-rebase-4444j99-hokage-chess-136-1cbf3b75` | 0 | 0 | `dirty` |
| `heal-rebase-4444j99-hokage-chess-139-07d2980f` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-139-0e6f6d4a` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-139-54cda4e9` | 1 | 4 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-139-aa978656` | 1 | 5 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-139-c0e277d3` | 0 | 0 | `dirty` |
| `heal-rebase-4444j99-hokage-chess-139-d6ff41fc` | 1 | 3 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-139-e3d6cd6e` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-85-aee53ecd` | 0 | 0 | `dirty` |
| `heal-rebase-4444j99-hokage-chess-89-0448f70e` | 1 | 3 | `not-merged-to-default` |
| `heal-rebase-4444j99-hokage-chess-89-3e98bf07` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-89-77f50ed3` | 0 | 0 | `dirty` |
| `heal-rebase-4444j99-hokage-chess-94-13cf83c7` | 1 | 4 | `clean+merged+idle` |
| `heal-rebase-4444j99-hokage-chess-94-b27fb091` | 1 | 3 | `clean+merged+idle` |
| `heal-rebase-organvm-4444j99.github.io-9-77ec7ab8` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-organvm-4444j99.github.io-9-8c34d9b5` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-organvm-4444j99.github.io-9-db69ae03` | 1 | 3 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-29-13582938` | 1 | 4 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-30-74c22c45` | 1 | 1 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-30-760b4a89` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-30-83dc3d03` | 1 | 5 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-30-88d45188` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-30-ace9199f` | 1 | 4 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-30-b99de3e7` | 1 | 4 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-30-c96e4a23` | 0 | 0 | `dirty` |
| `heal-rebase-organvm-a-i-chat--exporter-30-ec506add` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-31-78a6445b` | 1 | 4 | `dirty` |
| `heal-rebase-organvm-a-i-chat--exporter-61-6eab8b67` | 1 | 4 | `dirty` |
| `heal-rebase-organvm-a-i-chat--exporter-66-71c4747e` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-66-80a17af2` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-66-97a71482` | 1 | 1 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-66-d443d50d` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-66-ea484c96` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-66-f4469c47` | 1 | 9 | `clean+merged+idle` |
| `heal-rebase-organvm-a-i-chat--exporter-66-fbdc462f` | 1 | 1 | `clean+merged+idle` |
| `heal-rebase-organvm-dot-github--logos-37-d981b37b` | 1 | 23 | `active(<6h)` |
| `heal-rebase-organvm-kerygma-profiles-6-1eaad9e8` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-kerygma-profiles-6-af889f90` | 1 | 22 | `active(<6h)` |
| `heal-rebase-organvm-kerygma-profiles-7-2b25ce2c` | 1 | 54 | `active(<6h)` |
| `heal-rebase-organvm-kerygma-profiles-7-46a39587` | 1 | 3 | `active(<6h)` |
| `heal-rebase-organvm-kerygma-profiles-7-af89aa48` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-organvm-corpvs-testamentvm-495-ee057f86` | 1 | 38 | `active(<6h)` |
| `heal-rebase-organvm-organvm-corpvs-testamentvm-496-b9da6fb3` | 1 | 18 | `active(<6h)` |
| `heal-rebase-organvm-payrail-4-91d2e253` | 0 | 0 | `dirty` |
| `heal-rebase-organvm-peer-audited--behavioral-blockchain-711-893d6d0d` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-peer-audited--behavioral-blockchain-713-dd7791ce` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-peer-audited--behavioral-blockchain-721-4cf098da` | 1 | 3 | `clean+merged+idle` |
| `heal-rebase-organvm-peer-audited--behavioral-blockchain-721-68871455` | 1 | 3 | `clean+merged+idle` |
| `heal-rebase-organvm-peer-audited--behavioral-blockchain-721-d20ed684` | 0 | 0 | `dirty` |
| `heal-rebase-organvm-rules-system-bound-10-1ebaf735` | 1 | 3 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-10-ae4ac16b` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-10-c2d23459` | 1 | 1 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-10-eb00b73c` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-10-eba6fc9e` | 1 | 52 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-5-32379ac2` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-6-1edc9fe6` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-6-8d4ebb37` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-6-9f7690fb` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-6-e5c003c7` | 1 | 21 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-9-28a32b4f` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-9-2fa2012d` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-rules-system-bound-9-c3f5163e` | 1 | 1 | `active(<6h)` |
| `heal-rebase-organvm-the-invisible-ledger-52-f4c5a0cd` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-the-invisible-ledger-64-081af90f` | 1 | 3 | `active(<6h)` |
| `heal-rebase-organvm-the-invisible-ledger-64-3ef1b1e0` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-universal-mail--automation-119-ba27962d` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-universal-mail--automation-130-17d2410f` | 1 | 42 | `active(<6h)` |
| `heal-rebase-organvm-universal-mail--automation-134-e544ecb8` | 2 | 68 | `active(<6h)` |
| `heal-rebase-organvm-your-fit-tailored-15-3def5941` | 1 | 3 | `clean+merged+idle` |
| `heal-rebase-organvm-your-fit-tailored-15-5f39fd5e` | 0 | 0 | `clean+merged+idle` |
| `heal-rebase-organvm-your-fit-tailored-15-fa5d798d` | 1 | 3 | `clean+merged+idle` |
| `heal-rebase-organvm-your-fit-tailored-15-fad950e3` | 1 | 3 | `clean+merged+idle` |
| `limen-main-trench-20260628` | 1 | 14 | `remote-pr-open` |
| `limen-network-substrate-20260628` | 2 | 21 | `remote-pr-open` |
| `limen_jules-gh-4444j99-hokage-chess-39-c953` | 0 | 0 | `unpushed-commits` |
| `limen_jules-heal-cifix-organvm-bountyscope-12-7d22` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-heal-cifix-organvm-limen-424-6357` | 0 | 0 | `not-merged-to-default` |
| `limen_jules-heal-cifix-organvm-organvm-engine-139-7f50` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-heal-cifix-organvm-organvm-engine-144-db4a` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-heal-cifix-organvm-organvm-ontologia-11-b2f0` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-heal-cifix-organvm-public-record-data-scrapper-336-9d66` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-heal-cifix-organvm-trendpulse-6-fd32` | 0 | 0 | `active(<6h)` |
| `limen_jules-heal-rebase-organvm-payrail-4-d50b` | 0 | 0 | `not-merged-to-default` |
| `limen_jules-heal-rebase-organvm-your-fit-tailored-15-0891` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-0289` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-02b9` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-02fb` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-1481` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-274f` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-47a3` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-5341` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-6ef8` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-7bbc` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-8195` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-9d90` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-a46c` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-a901` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-f8cb` | 0 | 0 | `clean+merged+idle` |
| `linear-conjuring-bear` | 43 | 2248 | `remote-superseded` |
| `maddie-boundary-20260629` | 2 | 68 | `remote-pr-open` |
| `mail-story-mining-20260706` | 0 | 0 | `active(<24h)` |
| `org-financial-organ-face-0704-5a117787` | 1 | 3 | `clean+merged+idle` |
| `org-financial-organ-face-0704-9855f329` | 0 | 0 | `not-merged-to-default` |
| `org-financial-organ-face-0704-bd436529` | 1 | 4 | `dirty` |
| `org-governance-organ-selffeed-0703-00694775` | 1 | 4 | `dirty` |
| `org-governance-organ-selffeed-0703-ae95b1bf` | 0 | 0 | `clean+merged+idle` |
| `org-health-organ-firstslice-0704-aac2b482` | 1 | 3 | `documented-residue` |
| `org-health-organ-firstslice-0704-caa4e142` | 1 | 3 | `documented-residue` |
| `peer-audited--behavioral-blockchain` | 95 | 650 | `owner-blocker` |
| `photos-universe-20260629-182431` | 4 | 20 | `remote-pr-open` |
| `pr-669-governance-deepen` | 0 | 0 | `remote-merged` |
| `resolve-organvm-i-theoria-.github-459-1ade` | 1 | 5 | `owner-blocker` |
| `rev-organvm-mirror-mirror-revenue-ship-0704-134a11b8` | 0 | 0 | `active(<6h)` |
| `rev-organvm-mirror-mirror-revenue-ship-0704-94c4704f` | 0 | 0 | `active(<6h)` |
| `review-avditor-billing-pr43` | 0 | 0 | `owner-blocker` |
| `student-email-d2l-support-20260629` | 2 | 67 | `remote-pr-open` |
| `the-invisible-ledger` | 106 | 3036 | `remote-pr-open` |
| `ticklish-bubbling-robin` | 69 | 2202 | `remote-pr-open` |
| `triptych-account-excavation-20260706` | 0 | 0 | `active(<24h)` |
| `triptych-story` | 3 | 212 | `remote-pr-open` |
| `universal-entry-20260629` | 0 | 0 | `remote-pr-open` |
| `universal-kernel-recordkeeper-20260705` | 0 | 0 | `active(<24h)` |
| `vltima-organ-impl-codex-20260706` | 0 | 0 | `dirty` |
| `warp-agent-routing-20260629` | 2 | 15 | `remote-pr-open` |
| `wf_29a15be5-9f8-2` | 1 | 33 | `owner-blocker` |

## Task Board Crosswalk

- Task records: `2159`.
- Status distribution: `archived` 439, `dispatched` 96, `done` 1099, `failed` 4, `needs_human` 199, `open` 322.
- Invalid statuses outside canonical set: `0`.
- Current worktree root slugs mentioned exactly in `tasks.yaml`: `17` / `524`.
- Chronic reopen-loop candidates: `0`.
- Dispatched tasks with PR receipt: `90`.
- Dispatched Jules async tasks without PR yet: `6`.
- Dispatched local tasks still inside running grace/no-op guard: `0`.
- Dispatched local tasks stranded without PR receipt: `0`.
- Done tasks with PR receipt still visible in dispatch log/URLs: `886`.

## Remote Receipts

- GitHub worktree repos seen: `48`.
- Git worktree roots with remote branch present: `111`; missing: `398`.
- Branch-linked PR states: `OPEN` 82, `MERGED` 41, `CLOSED` 2.
- Task-board GitHub PR refs seen: `1253`; checked: `1000`; states: `CLOSED` 38, `MERGED` 484, `OPEN` 478.
- Task PR receipt scan truncated at `1000` refs.

## Cloud Receipts

- Public site probed: `https://device-streaming-067d747a.web.app`; `4` / `4` probes passed.
- Runtime URL configured: `False`; runtime health probe ok: `False`.
- Cloudflare deploy auth present: `False`.
- Cloud env flags: `CLOUDFLARE_API_TOKEN`=absent, `GOOGLE_APPLICATION_CREDENTIALS`=absent, `LIMEN_API_TOKEN`=absent, `LIMEN_CLIENT_TOKEN`=absent, `LIMEN_WORKER_URL`=absent, `NETLIFY_AUTH_TOKEN`=absent, `NEXT_PUBLIC_API_URL`=absent, `VERCEL_TOKEN`=absent.

## Roadblocks And Potholes

- The app screenshots are partially covered by local Codex history and Claude project/task stores, but screenshots alone are not durable enough to be the corpus. The durable object is now filesystem source + private object copy + redacted hash ledger.
- Remote/cloud receipts are part of the lifecycle proof, but they are not substitutes for preserving local raw prompt/session material.
- Worktree roots still do not have first-class task-board receipt fields; exact slug references are the bridge to add before automatic drain can be trusted.
- Dispatch receipt classification must distinguish async Jules work from stranded local no-PR work; otherwise the conductor burns attention on healthy async reservations.
- Prompt/session coverage is now hashed, but lifecycle judgment still needs owner actions: dirty roots need PRs or blocker records, and open PR receipts need merge or named supersession.
- Codex now has prompt-event coverage plus `codex-quicken.py` lifecycle classification: `887` sessions; `ALIVE` 1, `CLOSED` 783, `PARKED` 40, `STALLED` 63.

## Drain Queue

- Session lifecycle drain queue: `docs/session-lifecycle-drain-queue-2026-06-27.md`.

## Private Outputs

- Prompt lifecycle private index: `~/Workspace/limen/.limen-private/session-corpus/lifecycle/prompt-lifecycle-index.json`.
- Raw object cartridge: `~/Workspace/limen/.limen-private/session-corpus/objects`.
- The private index contains source paths, session hashes, prompt hashes, CWD hashes, and worktree links; it contains no prompt text.

## Commands

- Refresh this ledger with remote/cloud receipts: `python3 scripts/prompt-lifecycle-ledger.py --write --all`
- Refresh local-only when offline: `python3 scripts/prompt-lifecycle-ledger.py --write --all --no-remote --no-cloud`
- Refresh and absorb raw session/app files: `python3 scripts/session-corpus-ledger.py --write --all --materialize`
- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Inspect lifecycle debt: `python3 scripts/worktree-debt.py --json`
