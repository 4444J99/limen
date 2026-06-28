# Prompt Lifecycle Ledger

Generated: `2026-06-28T02:52:30+00:00`
Horizon: `all local history`

## Canonical Decision

- A human prompt/session is a lifecycle seed. Work that starts from it must end in a named outcome: merged, pushed PR, preserved branch, owner-recorded blocker, named supersession, archived task, or documented non-source residue.
- Raw personal/session material belongs in `.limen-private/session-corpus/`; tracked ledgers must stay redacted and receipt-oriented.
- Screenshots are coverage hints. The canonical absorptive layer is the local app/session filesystem plus private cartridge materialization.
- Worktree cleanup is subordinate to prompt lifecycle: no unique work is removed just because a directory is inconvenient.

## Redacted Prompt Coverage

Indexed `9489` app/session files, `2.1 GiB`, with `92795` prompt-like user events hashed into the private index.

| Source | Files | Prompt Events | Event Records | Size | Newest |
|---|---:|---:|---:|---:|---|
| `claude-projects` | 4854 | 87828 | 313210 | 1.4 GiB | `2026-06-28T01:17:54+00:00` |
| `codex-sessions` | 889 | 4394 | 234164 | 731.8 MiB | `2026-06-28T02:51:14+00:00` |
| `codex-history` | 1 | 440 | 440 | 192.7 KiB | `2026-06-28T02:24:32+00:00` |
| `claude-tasks` | 188 | 133 | 133 | 57.7 KiB | `2026-06-26T00:08:52+00:00` |
| `claude-file-history` | 3519 | 0 | 0 | 42.2 MiB | `2026-06-27T00:26:28+00:00` |
| `claude-plans` | 34 | 0 | 0 | 289.3 KiB | `2026-06-25T03:22:45+00:00` |
| `codex-attachments` | 4 | 0 | 0 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |

## Prompt To Worktree Crosswalk

- Current `.limen-worktrees` roots scanned: `14`; debt roots: `8`.
- Current worktree roots with at least one local session/prompt receipt: `14`.
- Current worktree roots without a local session receipt in this index: `0`.

| Worktree Root | Session Files | Prompt Events | Debt Reason |
|---|---:|---:|---|
| `bld-mirror-mirror-harden-350f` | 1 | 5 | `unpushed-commits` |
| `bld-my--father-mother-harden-44b2` | 1 | 5 | `active(<6h)` |
| `bld-promptscope-next-rev-3fde` | 1 | 4 | `active(<6h)` |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | 3 | 79 | `unpushed-commits` |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | 1 | 71 | `active(<6h)` |
| `discover-organvm-kerygma-profiles-6c74` | 1 | 24 | `not-merged-to-default` |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | 1 | 3 | `dirty` |
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | 1 | 4 | `not-a-git-dir` |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | 3 | 100 | `dirty` |
| `gh-organvm-object-lessons-19-605a` | 1 | 73 | `clean+merged+idle` |
| `resolve-a-organvm-the-invisible-ledger-4-f657` | 1 | 5 | `clean+merged+idle` |
| `resolve-organvm-i-theoria-.github-459-1ade` | 1 | 5 | `unpushed-commits` |
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | 1 | 79 | `active(<6h)` |
| `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | 1 | 94 | `not-a-git-dir` |

## Task Board Crosswalk

- Task records: `1427`.
- Status distribution: `archived` 438, `dispatched` 41, `done` 807, `in_progress` 1, `needs_human` 61, `open` 79.
- Invalid statuses outside canonical set: `0`.
- Current worktree root slugs mentioned exactly in `tasks.yaml`: `0` / `14`.
- Chronic reopen-loop candidates: `0`.
- Dispatched tasks with PR receipt: `0`.
- Dispatched Jules async tasks without PR yet: `41`.
- Dispatched local tasks still inside running grace/no-op guard: `0`.
- Dispatched local tasks stranded without PR receipt: `0`.
- Done tasks with PR receipt still visible in dispatch log/URLs: `636`.

## Remote Receipts

- GitHub worktree repos seen: `11`.
- Git worktree roots with remote branch present: `7`; missing: `4`.
- Branch-linked PR states: `OPEN` 6, `MERGED` 1, `CLOSED` 1.
- Task-board GitHub PR refs seen: `657`; checked: `657`; states: `CLOSED` 31, `MERGED` 447, `OPEN` 179.

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
