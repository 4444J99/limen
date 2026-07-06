# Prompt Lifecycle Ledger

Generated: `2026-07-06T15:41:45+00:00`
Horizon: `all local history`

## Canonical Decision

- A human prompt/session is a lifecycle seed. Work that starts from it must end in a named outcome: merged, pushed PR, preserved branch, owner-recorded blocker, named supersession, archived task, or documented non-source residue.
- Raw personal/session material belongs in `.limen-private/session-corpus/`; tracked ledgers must stay redacted and receipt-oriented.
- Screenshots are coverage hints. The canonical absorptive layer is the local app/session filesystem plus private cartridge materialization.
- Worktree cleanup is subordinate to prompt lifecycle: no unique work is removed just because a directory is inconvenient.

## Redacted Prompt Coverage

Indexed `15291` app/session files, `4.3 GiB`, with `131758` prompt-like user events hashed into the private index.
Normalized task-body payload covered `260.5 MiB` after stripping recognized scaffold-only prompt frames.

| Source | Files/Sessions | Prompt Events | Prompt Bytes | Task Body Bytes | Event Records | Size | Newest |
|---|---:|---:|---:|---:|---:|---:|---|
| `claude-projects` | 6646 | 120740 | 245.9 MiB | 239.9 MiB | 460371 | 1.9 GiB | `2026-07-06T15:30:51+00:00` |
| `codex-sessions` | 1389 | 7787 | 19.3 MiB | 13.6 MiB | 535774 | 1.5 GiB | `2026-07-06T15:38:37+00:00` |
| `opencode-db` | 1426 | 1433 | 3.9 MiB | 3.9 MiB | 81675 | 0 B | `2026-07-06T15:02:33+00:00` |
| `codex-history` | 1 | 1105 | 715.2 KiB | 715.2 KiB | 1105 | 823.1 KiB | `2026-07-06T15:28:28+00:00` |
| `agy-cli-conversations` | 501 | 481 | 2.3 MiB | 2.3 MiB | 30111 | 871.7 MiB | `2026-07-06T15:06:27+00:00` |
| `claude-tasks` | 206 | 138 | 32.2 KiB | 32.2 KiB | 138 | 59.9 KiB | `2026-07-03T15:47:52+00:00` |
| `agy-cli-history` | 1 | 44 | 10.7 KiB | 10.7 KiB | 44 | 16.4 KiB | `2026-07-03T11:53:18+00:00` |
| `gemini-tmp-agy` | 15 | 30 | 267.0 KiB | 9.9 KiB | 60 | 280.8 KiB | `2026-06-30T14:29:59+00:00` |
| `claude-file-history` | 5059 | 0 | 0 B | 0 B | 0 | 67.2 MiB | `2026-07-05T18:01:34+00:00` |
| `claude-plans` | 43 | 0 | 0 B | 0 B | 0 | 369.8 KiB | `2026-07-03T15:08:54+00:00` |
| `codex-attachments` | 4 | 0 | 0 B | 0 B | 0 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |

## Prompt Body Mix

| Body Kind | Prompt Events |
|---|---:|
| `direct` | 126994 |
| `flame_scaffold` | 2504 |
| `flame_with_task_body` | 2245 |
| `session_context` | 15 |

## Prompt To Worktree Crosswalk

- Current `.limen-worktrees` roots scanned: `152`; debt roots: `7`.
- Current worktree roots with at least one local session/prompt receipt: `77`.
- Current worktree roots without a local session receipt in this index: `75`.

| Worktree Root | Session Files | Prompt Events | Debt Reason |
|---|---:|---:|---|
| `agent-aefc63d95daa3131b` | 2 | 31 | `owner-blocker` |
| `bld-my--father-mother-harden-44b2` | 1 | 5 | `remote-pr-open` |
| `bld-promptscope-next-rev-3fde` | 1 | 4 | `remote-pr-open` |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | 3 | 79 | `remote-pr-open` |
| `discover-organvm-kerygma-profiles-6c74` | 1 | 24 | `remote-pr-open` |
| `domus-quarantine-retire-20260629` | 10 | 84 | `remote-pr-open` |
| `feat+workstream-channels` | 2 | 47 | `remote-pr-open` |
| `feat-gcp-sa-organ` | 13 | 727 | `owner-blocker` |
| `financial-codex-finish-0704` | 0 | 0 | `remote-pr-open` |
| `fluttering-twirling-abelson` | 8 | 403 | `remote-merged` |
| `gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec` | 1 | 5 | `owner-blocker` |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | 3 | 100 | `owner-blocker` |
| `gh-4444j99-hokage-chess-39-25daa3dd` | 0 | 0 | `active(<6h)` |
| `gh-4444j99-hokage-chess-39-c15d2ce9` | 0 | 0 | `active(<6h)` |
| `gh-organvm-domus-genoma-170-bbbc` | 0 | 0 | `remote-merged` |
| `heal-cifix-organvm-a-i--skills-26-90acdfa8` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-a-i--skills-27-7ed7339a` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-a-i--skills-27-d0df3765` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-a-i--skills-27-f0edd746` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-a-i--skills-27-f7577686` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-a-i--skills-28-aa405c3d` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-a-i--skills-28-d93d775c` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-a-i--skills-29-6209335e` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-a-i-chat--exporter-49-102d97d6` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-a-i-chat--exporter-49-1992eb0d` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-a-i-chat--exporter-54-3049e7fb` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-421-8f14068b` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-422-3a71d824` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-422-eda116ed` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-limen-423-354fa844` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-423-47a6f9ec` | 1 | 126 | `active(<6h)` |
| `heal-cifix-organvm-limen-424-8db5dab0` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-425-164d86db` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-limen-425-9c743c2c` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-427-42616f71` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-428-dbe8a466` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-429-4471ceb2` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-430-1738f072` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-limen-430-955f9dd1` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-431-6ee61f31` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-432-06bf02c7` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-434-b6e642da` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-limen-435-47b10f86` | 1 | 134 | `active(<6h)` |
| `heal-cifix-organvm-limen-438-da3b854e` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-limen-439-4583ba76` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-124-e0bb2d06` | 0 | 0 | `remote-merged` |
| `heal-cifix-organvm-organvm-engine-130-8a6060e4` | 0 | 0 | `remote-pr-open` |
| `heal-cifix-organvm-organvm-engine-130-ec1fdfaf` | 0 | 0 | `remote-pr-open` |
| `heal-cifix-organvm-organvm-engine-136-c3d543d8` | 0 | 0 | `owner-blocker` |
| `heal-cifix-organvm-organvm-engine-139-11d32b27` | 0 | 0 | `remote-pr-open` |
| `heal-cifix-organvm-organvm-engine-139-9dbf53bf` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-engine-139-b438a568` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-143-a164221c` | 0 | 0 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-engine-144-0ef4c596` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-engine-144-6ffd7057` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-144-e2096564` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-ontologia-10-0356e4b9` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-10-64603ca7` | 0 | 0 | `unpushed-commits` |
| `heal-cifix-organvm-organvm-ontologia-10-be8406e3` | 1 | 4 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-11-2978d499` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-11-55899198` | 0 | 0 | `dirty` |
| `heal-cifix-organvm-organvm-ontologia-11-a86cf99f` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-11-f753ad04` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-12-2c2c85ba` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-12-c16ea5ad` | 0 | 0 | `not-merged-to-default` |
| `heal-cifix-organvm-organvm-ontologia-13-517e2cb9` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-13-5364f697` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-13-953633bb` | 1 | 3 | `clean+merged+idle` |
| `heal-cifix-organvm-organvm-ontologia-13-c96051e5` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-13-ebb63927` | 1 | 3 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-103-e7e058ff` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-103-f5b1e4f4` | 1 | 3 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-107-a1b561eb` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-107-f3a0ded1` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-108-6253b273` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-108-9266466c` | 1 | 3 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-114-fb8e1c94` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-121-22d63bd9` | 1 | 4 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-121-89f977f6` | 1 | 3 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-136-1cbf3b75` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-139-0e6f6d4a` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-139-d6ff41fc` | 1 | 3 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-139-e3d6cd6e` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-85-aee53ecd` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-89-0448f70e` | 1 | 3 | `not-merged-to-default` |
| `heal-rebase-4444j99-hokage-chess-89-3e98bf07` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-89-77f50ed3` | 0 | 0 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-94-13cf83c7` | 1 | 4 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-94-b27fb091` | 1 | 3 | `active(<6h)` |
| `heal-rebase-organvm-4444j99.github.io-9-77ec7ab8` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-4444j99.github.io-9-8c34d9b5` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-4444j99.github.io-9-db69ae03` | 1 | 3 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-29-13582938` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-30-760b4a89` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-30-b99de3e7` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-31-78a6445b` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-61-6eab8b67` | 1 | 4 | `active(<6h)` |
| `heal-rebase-organvm-a-i-chat--exporter-66-71c4747e` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-payrail-4-91d2e253` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-peer-audited--behavioral-blockchain-721-4cf098da` | 1 | 3 | `active(<6h)` |
| `heal-rebase-organvm-peer-audited--behavioral-blockchain-721-68871455` | 1 | 3 | `active(<6h)` |
| `heal-rebase-organvm-peer-audited--behavioral-blockchain-721-d20ed684` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-your-fit-tailored-15-3def5941` | 1 | 3 | `active(<6h)` |
| `heal-rebase-organvm-your-fit-tailored-15-5f39fd5e` | 0 | 0 | `active(<6h)` |
| `heal-rebase-organvm-your-fit-tailored-15-fa5d798d` | 1 | 3 | `active(<6h)` |
| `heal-rebase-organvm-your-fit-tailored-15-fad950e3` | 1 | 3 | `active(<6h)` |
| `limen-main-trench-20260628` | 1 | 14 | `remote-pr-open` |
| `limen-network-substrate-20260628` | 2 | 21 | `remote-pr-open` |
| `limen_jules-gh-4444j99-hokage-chess-39-c953` | 0 | 0 | `active(<6h)` |
| `limen_jules-heal-cifix-organvm-limen-424-6357` | 0 | 0 | `active(<6h)` |
| `limen_jules-heal-cifix-organvm-organvm-engine-139-7f50` | 0 | 0 | `active(<6h)` |
| `limen_jules-heal-cifix-organvm-organvm-engine-144-db4a` | 0 | 0 | `active(<6h)` |
| `limen_jules-heal-cifix-organvm-organvm-ontologia-11-b2f0` | 0 | 0 | `active(<6h)` |
| `limen_jules-heal-cifix-organvm-public-record-data-scrapper-336-9d66` | 0 | 0 | `active(<6h)` |
| `limen_jules-heal-rebase-organvm-payrail-4-d50b` | 0 | 0 | `active(<6h)` |
| `limen_jules-heal-rebase-organvm-your-fit-tailored-15-0891` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-0289` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-02b9` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-02fb` | 0 | 0 | `clean+merged+idle` |
| `limen_jules-org-health-organ-kernel-0630-1481` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-274f` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-47a3` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-5341` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-6ef8` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-7bbc` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-8195` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-9d90` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-a46c` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-a901` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-f8cb` | 0 | 0 | `clean+merged+idle` |
| `linear-conjuring-bear` | 43 | 2230 | `remote-superseded` |
| `maddie-boundary-20260629` | 2 | 68 | `remote-pr-open` |
| `org-financial-organ-face-0704-5a117787` | 1 | 3 | `clean+merged+idle` |
| `org-financial-organ-face-0704-9855f329` | 0 | 0 | `active(<6h)` |
| `org-financial-organ-face-0704-bd436529` | 1 | 4 | `active(<6h)` |
| `org-governance-organ-selffeed-0703-00694775` | 1 | 4 | `active(<6h)` |
| `org-governance-organ-selffeed-0703-ae95b1bf` | 0 | 0 | `active(<6h)` |
| `org-health-organ-firstslice-0704-aac2b482` | 1 | 3 | `documented-residue` |
| `org-health-organ-firstslice-0704-caa4e142` | 1 | 3 | `documented-residue` |
| `peer-audited--behavioral-blockchain` | 95 | 650 | `owner-blocker` |
| `photos-universe-20260629-182431` | 4 | 20 | `remote-pr-open` |
| `pr-669-governance-deepen` | 0 | 0 | `remote-merged` |
| `resolve-organvm-i-theoria-.github-459-1ade` | 1 | 5 | `owner-blocker` |
| `review-avditor-billing-pr43` | 0 | 0 | `owner-blocker` |
| `student-email-d2l-support-20260629` | 2 | 67 | `remote-pr-open` |
| `the-invisible-ledger` | 106 | 3036 | `remote-pr-open` |
| `ticklish-bubbling-robin` | 69 | 2182 | `remote-pr-open` |
| `triptych-story` | 3 | 212 | `remote-pr-open` |
| `universal-entry-20260629` | 0 | 0 | `remote-pr-open` |
| `universal-kernel-recordkeeper-20260705` | 0 | 0 | `active(<24h)` |
| `warp-agent-routing-20260629` | 2 | 15 | `remote-pr-open` |
| `wf_29a15be5-9f8-2` | 1 | 33 | `owner-blocker` |

## Task Board Crosswalk

- Task records: `2153`.
- Status distribution: `archived` 439, `dispatched` 99, `done` 1056, `needs_human` 173, `open` 386.
- Invalid statuses outside canonical set: `0`.
- Current worktree root slugs mentioned exactly in `tasks.yaml`: `3` / `152`.
- Chronic reopen-loop candidates: `0`.
- Dispatched tasks with PR receipt: `93`.
- Dispatched Jules async tasks without PR yet: `6`.
- Dispatched local tasks still inside running grace/no-op guard: `0`.
- Dispatched local tasks stranded without PR receipt: `0`.
- Done tasks with PR receipt still visible in dispatch log/URLs: `843`.

## Remote Receipts

- GitHub worktree repos seen: `19`.
- Git worktree roots with remote branch present: `36`; missing: `108`.
- Branch-linked PR states: `OPEN` 30, `MERGED` 10, `CLOSED` 1.
- Task-board GitHub PR refs seen: `1211`; checked: `1000`; states: `CLOSED` 37, `MERGED` 455, `OPEN` 508.
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
