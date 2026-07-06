# Prompt Lifecycle Ledger

Generated: `2026-07-06T09:27:40+00:00`
Horizon: `all local history`

## Canonical Decision

- A human prompt/session is a lifecycle seed. Work that starts from it must end in a named outcome: merged, pushed PR, preserved branch, owner-recorded blocker, named supersession, archived task, or documented non-source residue.
- Raw personal/session material belongs in `.limen-private/session-corpus/`; tracked ledgers must stay redacted and receipt-oriented.
- Screenshots are coverage hints. The canonical absorptive layer is the local app/session filesystem plus private cartridge materialization.
- Worktree cleanup is subordinate to prompt lifecycle: no unique work is removed just because a directory is inconvenient.

## Redacted Prompt Coverage

Indexed `15221` app/session files, `4.3 GiB`, with `131016` prompt-like user events hashed into the private index.
Normalized task-body payload covered `259.7 MiB` after stripping recognized scaffold-only prompt frames.

| Source | Files/Sessions | Prompt Events | Prompt Bytes | Task Body Bytes | Event Records | Size | Newest |
|---|---:|---:|---:|---:|---:|---:|---|
| `claude-projects` | 6620 | 120295 | 245.3 MiB | 239.6 MiB | 458666 | 1.9 GiB | `2026-07-06T09:24:19+00:00` |
| `codex-sessions` | 1363 | 7566 | 18.8 MiB | 13.4 MiB | 516615 | 1.5 GiB | `2026-07-06T09:26:01+00:00` |
| `opencode-db` | 1408 | 1415 | 3.7 MiB | 3.7 MiB | 81621 | 0 B | `2026-07-06T08:52:27+00:00` |
| `codex-history` | 1 | 1047 | 709.6 KiB | 709.6 KiB | 1047 | 813.0 KiB | `2026-07-06T02:17:32+00:00` |
| `agy-cli-conversations` | 501 | 481 | 2.3 MiB | 2.3 MiB | 29662 | 870.0 MiB | `2026-07-06T08:44:10+00:00` |
| `claude-tasks` | 206 | 138 | 32.2 KiB | 32.2 KiB | 138 | 59.9 KiB | `2026-07-03T15:47:52+00:00` |
| `agy-cli-history` | 1 | 44 | 10.7 KiB | 10.7 KiB | 44 | 16.4 KiB | `2026-07-03T11:53:18+00:00` |
| `gemini-tmp-agy` | 15 | 30 | 267.0 KiB | 9.9 KiB | 60 | 280.8 KiB | `2026-06-30T14:29:59+00:00` |
| `claude-file-history` | 5059 | 0 | 0 B | 0 B | 0 | 67.2 MiB | `2026-07-05T18:01:34+00:00` |
| `claude-plans` | 43 | 0 | 0 B | 0 B | 0 | 369.8 KiB | `2026-07-03T15:08:54+00:00` |
| `codex-attachments` | 4 | 0 | 0 B | 0 B | 0 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |

## Prompt Body Mix

| Body Kind | Prompt Events |
|---|---:|
| `direct` | 126417 |
| `flame_scaffold` | 2433 |
| `flame_with_task_body` | 2151 |
| `session_context` | 15 |

## Prompt To Worktree Crosswalk

- Current `.limen-worktrees` roots scanned: `48`; debt roots: `0`.
- Current worktree roots with at least one local session/prompt receipt: `30`.
- Current worktree roots without a local session receipt in this index: `18`.

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
| `fluttering-twirling-abelson` | 8 | 315 | `active(<24h)` |
| `gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec` | 1 | 5 | `owner-blocker` |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | 3 | 100 | `owner-blocker` |
| `gh-organvm-domus-genoma-170-bbbc` | 0 | 0 | `remote-merged` |
| `heal-cifix-organvm-organvm-engine-124-e0bb2d06` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-130-8a6060e4` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-130-ec1fdfaf` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-136-c3d543d8` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-139-11d32b27` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-139-9dbf53bf` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-143-a164221c` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-engine-144-0ef4c596` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-10-64603ca7` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-11-55899198` | 0 | 0 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-11-a86cf99f` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-12-2c2c85ba` | 1 | 3 | `active(<6h)` |
| `heal-cifix-organvm-organvm-ontologia-13-953633bb` | 1 | 3 | `active(<6h)` |
| `heal-rebase-4444j99-hokage-chess-89-0448f70e` | 1 | 3 | `active(<6h)` |
| `limen-main-trench-20260628` | 1 | 14 | `remote-pr-open` |
| `limen-network-substrate-20260628` | 2 | 21 | `remote-pr-open` |
| `limen_jules-org-health-organ-kernel-0630-0289` | 0 | 0 | `active(<6h)` |
| `limen_jules-org-health-organ-kernel-0630-02fb` | 0 | 0 | `active(<6h)` |
| `linear-conjuring-bear` | 43 | 2215 | `remote-superseded` |
| `maddie-boundary-20260629` | 2 | 68 | `remote-pr-open` |
| `org-health-organ-firstslice-0704-aac2b482` | 1 | 3 | `generated-log-shell` |
| `org-health-organ-firstslice-0704-caa4e142` | 1 | 3 | `generated-log-shell` |
| `peer-audited--behavioral-blockchain` | 95 | 650 | `owner-blocker` |
| `photos-universe-20260629-182431` | 4 | 20 | `remote-pr-open` |
| `pr-669-governance-deepen` | 0 | 0 | `active(<6h)` |
| `resolve-organvm-i-theoria-.github-459-1ade` | 1 | 5 | `owner-blocker` |
| `review-avditor-billing-pr43` | 0 | 0 | `owner-blocker` |
| `student-email-d2l-support-20260629` | 2 | 67 | `remote-pr-open` |
| `the-invisible-ledger` | 106 | 3036 | `remote-pr-open` |
| `ticklish-bubbling-robin` | 69 | 2172 | `remote-pr-open` |
| `triptych-story` | 3 | 212 | `remote-pr-open` |
| `universal-entry-20260629` | 0 | 0 | `remote-pr-open` |
| `universal-kernel-recordkeeper-20260705` | 0 | 0 | `active(<24h)` |
| `warp-agent-routing-20260629` | 2 | 15 | `remote-pr-open` |
| `wf_29a15be5-9f8-2` | 1 | 33 | `owner-blocker` |

## Task Board Crosswalk

- Task records: `2117`.
- Status distribution: `archived` 439, `dispatched` 4, `done` 1043, `in_progress` 1, `needs_human` 172, `open` 458.
- Invalid statuses outside canonical set: `0`.
- Current worktree root slugs mentioned exactly in `tasks.yaml`: `3` / `48`.
- Chronic reopen-loop candidates: `0`.
- Dispatched tasks with PR receipt: `4`.
- Dispatched Jules async tasks without PR yet: `0`.
- Dispatched local tasks still inside running grace/no-op guard: `0`.
- Dispatched local tasks stranded without PR receipt: `0`.
- Done tasks with PR receipt still visible in dispatch log/URLs: `830`.

## Remote Receipts

- GitHub worktree repos seen: `14`.
- Git worktree roots with remote branch present: `21`; missing: `22`.
- Branch-linked PR states: `OPEN` 20, `MERGED` 5, `CLOSED` 1.
- Task-board GitHub PR refs seen: `1194`; checked: `1000`; states: `CLOSED` 36, `MERGED` 452, `OPEN` 512.
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
