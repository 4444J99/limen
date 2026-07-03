# Prompt Lifecycle Ledger

Generated: `2026-07-03T22:35:52+00:00`
Horizon: `all local history`

## Canonical Decision

- A human prompt/session is a lifecycle seed. Work that starts from it must end in a named outcome: merged, pushed PR, preserved branch, owner-recorded blocker, named supersession, archived task, or documented non-source residue.
- Raw personal/session material belongs in `.limen-private/session-corpus/`; tracked ledgers must stay redacted and receipt-oriented.
- Screenshots are coverage hints. The canonical absorptive layer is the local app/session filesystem plus private cartridge materialization.
- Worktree cleanup is subordinate to prompt lifecycle: no unique work is removed just because a directory is inconvenient.

## Redacted Prompt Coverage

Indexed `13942` app/session files, `3.2 GiB`, with `125457` prompt-like user events hashed into the private index.
Normalized task-body payload covered `248.3 MiB` after stripping recognized scaffold-only prompt frames.

| Source | Files/Sessions | Prompt Events | Prompt Bytes | Task Body Bytes | Event Records | Size | Newest |
|---|---:|---:|---:|---:|---:|---:|---|
| `claude-projects` | 6270 | 115915 | 236.2 MiB | 232.4 MiB | 439516 | 1.8 GiB | `2026-07-03T22:28:41+00:00` |
| `codex-sessions` | 1294 | 7121 | 17.1 MiB | 12.4 MiB | 420095 | 1.3 GiB | `2026-07-03T22:35:35+00:00` |
| `opencode-db` | 1268 | 1275 | 2.8 MiB | 2.8 MiB | 72408 | 0 B | `2026-07-03T22:03:28+00:00` |
| `codex-history` | 1 | 978 | 689.8 KiB | 689.8 KiB | 978 | 787.6 KiB | `2026-07-03T22:11:39+00:00` |
| `claude-tasks` | 206 | 138 | 32.2 KiB | 32.2 KiB | 138 | 59.9 KiB | `2026-07-03T15:47:52+00:00` |
| `gemini-tmp-agy` | 15 | 30 | 267.0 KiB | 9.9 KiB | 60 | 280.8 KiB | `2026-06-30T14:29:59+00:00` |
| `claude-file-history` | 4841 | 0 | 0 B | 0 B | 0 | 59.8 MiB | `2026-07-03T21:46:56+00:00` |
| `claude-plans` | 43 | 0 | 0 B | 0 B | 0 | 369.8 KiB | `2026-07-03T15:08:54+00:00` |
| `codex-attachments` | 4 | 0 | 0 B | 0 B | 0 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |

## Prompt Body Mix

| Body Kind | Prompt Events |
|---|---:|
| `direct` | 121501 |
| `flame_scaffold` | 2262 |
| `flame_with_task_body` | 1679 |
| `session_context` | 15 |

## Prompt To Worktree Crosswalk

- Current `.limen-worktrees` roots scanned: `47`; debt roots: `6`.
- Current worktree roots with at least one local session/prompt receipt: `38`.
- Current worktree roots without a local session receipt in this index: `9`.

| Worktree Root | Session Files | Prompt Events | Debt Reason |
|---|---:|---:|---|
| `GEN-organvm-limen-ci-green-0702` | 0 | 0 | `unpushed-commits` |
| `agent-acbda3ba428e68d78` | 2 | 51 | `active(<24h)` |
| `agent-ad70c6c4b3b7b5aab` | 2 | 33 | `active(<24h)` |
| `agent-aefc63d95daa3131b` | 2 | 31 | `active(<24h)` |
| `bld-my--father-mother-harden-44b2` | 1 | 5 | `remote-pr-open` |
| `bld-promptscope-next-rev-3fde` | 1 | 4 | `remote-pr-open` |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | 3 | 79 | `remote-pr-open` |
| `discover-organvm-kerygma-profiles-6c74` | 1 | 24 | `remote-pr-open` |
| `domus-quarantine-retire-20260629` | 10 | 84 | `remote-pr-open` |
| `feat+workstream-channels` | 2 | 47 | `active(<24h)` |
| `feat-codex-skill-slim` | 20 | 403 | `active(<24h)` |
| `feat-gcp-sa-organ` | 13 | 727 | `owner-blocker` |
| `feat-tabularius-record-keeper` | 2 | 618 | `active(<24h)` |
| `feat-workstream-assign` | 1 | 1121 | `active(<24h)` |
| `gen-a-organvm-a-i-council--coliseum-ci-green-0620-29ec` | 1 | 5 | `owner-blocker` |
| `gen-organvm-limen-test-coverage-0703-3a17` | 1 | 3 | `not-a-git-dir` |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | 3 | 100 | `owner-blocker` |
| `gh-organvm-domus-genoma-170-bbbc` | 0 | 0 | `active(<6h)` |
| `heal+jules-revive-census-converge` | 20 | 952 | `active(<24h)` |
| `limen-main-trench-20260628` | 1 | 14 | `remote-pr-open` |
| `limen-network-substrate-20260628` | 2 | 21 | `remote-pr-open` |
| `linear-conjuring-bear` | 43 | 2041 | `active(<24h)` |
| `maddie-boundary-20260629` | 2 | 68 | `remote-pr-open` |
| `org-governance-organ-deepen-0703-9f8e` | 1 | 4 | `active(<6h)` |
| `org-health-organ-firstslice-0703-9ab8` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-charter-0703-dcc8` | 1 | 3 | `not-a-git-dir` |
| `org-legal-organ-firstslice-0703-621b` | 1 | 4 | `active(<6h)` |
| `org-legal-organ-firstslice-0703-8242` | 1 | 3 | `not-a-git-dir` |
| `org-social-organ-firstslice-0703-3636` | 1 | 3 | `not-a-git-dir` |
| `photos-universe-20260629-182431` | 4 | 20 | `remote-pr-open` |
| `pr-463` | 0 | 0 | `remote-merged` |
| `pr-466` | 0 | 0 | `remote-merged` |
| `pr-467` | 0 | 0 | `remote-merged` |
| `pr-468` | 0 | 0 | `remote-merged` |
| `pr-471` | 0 | 0 | `remote-merged` |
| `pr-475` | 0 | 0 | `remote-merged` |
| `resolve-organvm-i-theoria-.github-459-1ade` | 1 | 5 | `owner-blocker` |
| `student-email-d2l-support-20260629` | 2 | 67 | `remote-pr-open` |
| `the-invisible-ledger` | 106 | 3036 | `remote-pr-open` |
| `ticklish-bubbling-robin` | 69 | 2012 | `active(<24h)` |
| `triptych-story` | 3 | 212 | `remote-pr-open` |
| `universal-entry-20260629` | 0 | 0 | `remote-pr-open` |
| `warp-agent-routing-20260629` | 2 | 15 | `remote-pr-open` |
| `wf_29a15be5-9f8-1` | 1 | 14 | `active(<24h)` |
| `wf_29a15be5-9f8-2` | 1 | 33 | `active(<24h)` |
| `wf_29a15be5-9f8-3` | 1 | 38 | `active(<24h)` |
| `wf_29a15be5-9f8-4` | 1 | 15 | `active(<24h)` |

## Task Board Crosswalk

- Task records: `1649`.
- Status distribution: `archived` 439, `dispatched` 4, `done` 990, `in_progress` 1, `needs_human` 149, `open` 66.
- Invalid statuses outside canonical set: `0`.
- Current worktree root slugs mentioned exactly in `tasks.yaml`: `2` / `47`.
- Chronic reopen-loop candidates: `1`.
- Dispatched tasks with PR receipt: `1`.
- Dispatched Jules async tasks without PR yet: `0`.
- Dispatched local tasks still inside running grace/no-op guard: `2`.
- Dispatched local tasks stranded without PR receipt: `1`.
- Done tasks with PR receipt still visible in dispatch log/URLs: `780`.

## Remote Receipts

- Remote receipt collection disabled for this run.

## Cloud Receipts

- Cloud receipt collection disabled for this run.

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
