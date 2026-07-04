# Session Corpus Ledger

Generated: `2026-07-04T19:01:32+00:00`
Horizon: `all local history`

## Canonical Decision

- Limen is the control plane and visible ledger for session/corpus lifecycle.
- `session-meta` remains the producer for redacted, deduped, multi-provider atoms.
- `knowledge-corpus` remains the distillation target consumed by `corpus-converge.py`.
- `prompt-lifecycle-ledger.py` is the redacted crosswalk from local prompts/sessions to worktrees, tasks, GitHub receipts, and cloud probes.
- Raw personal/session data is private local material. It belongs under `./.limen-private/session-corpus/` when materialized, never in public Git history.
- The app screenshots are coverage hints, not canonical input. Canonical input is the local Claude/Codex/session-meta filesystem state.

## Local Session Sources

Total seen: `13581` files, `3.4 GiB`.

| Source | Root | Files | Size | Newest |
|---|---:|---:|---:|---|
| `claude-projects` | `~/.claude/projects` | 6512 | 1.9 GiB | `2026-07-04T19:01:04+00:00` |
| `codex-sessions` | `~/.local/share/codex/sessions` | 1361 | 1.4 GiB | `2026-07-04T19:01:26+00:00` |
| `claude-file-history` | `~/.claude/file-history` | 4980 | 63.7 MiB | `2026-07-04T18:49:08+00:00` |
| `codex-goals-state` | `~/.local/share/codex` | 6 | 20.4 MiB | `2026-07-04T19:01:26+00:00` |
| `codex-shell-snapshots` | `~/.local/share/codex/shell_snapshots` | 8 | 2.6 MiB | `2026-07-04T18:11:30+00:00` |
| `codex-history` | `~/.local/share/codex` | 1 | 801.2 KiB | `2026-07-04T18:11:56+00:00` |
| `claude-usage-session-meta` | `~/.claude/usage-data/session-meta` | 397 | 426.9 KiB | `2026-07-03T13:33:18+00:00` |
| `claude-plans` | `~/.claude/plans` | 43 | 369.8 KiB | `2026-07-03T15:08:54+00:00` |
| `codex-app-sqlite` | `~/.local/share/codex/sqlite` | 1 | 68.0 KiB | `2026-06-30T11:03:30+00:00` |
| `claude-tasks` | `~/.claude/tasks` | 206 | 59.9 KiB | `2026-07-03T15:47:52+00:00` |
| `claude-usage-facets` | `~/.claude/usage-data/facets` | 62 | 55.3 KiB | `2026-07-03T13:33:30+00:00` |
| `codex-attachments` | `~/.local/share/codex/attachments` | 4 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |

## Existing Organs

| Organ | Role | Path | Git state |
|---|---|---|---|
| `session-meta` | producer: redacted, deduped multi-provider atoms | `~/session-meta` | `not a git repo` |
| `knowledge-corpus` | distillation target: collection, reduced faces, THE ONE | `~/knowledge-corpus` | `not a git repo` |
| `conversation-corpus-engine` | product/research engine: provider import and corpus promotion | `~/conversation-corpus-engine` | `not a git repo` |

## Substrate Counts

- `session-meta/ingest/manifest.jsonl`: 0 records, mtime `missing`.
- `session-meta/ingest/atoms.jsonl`: 0 atoms, mtime `missing`.
- `knowledge-corpus`: `0` reduced faces; `00-THE-ONE.md` present: `False`.

## Session Lifecycle

- Last `quicken.py` journal: `2026-07-04T18:30:23+00:00`.
- Claude FleetView sessions classified: `0` total; `0` stalled, `0` closed, `0` alive, `0` done.
- Reaped worktrees in that pass: `0`.
- Last `codex-quicken.py` journal: `2026-06-27T21:42:32+00:00`.
- Codex sessions classified: `887` total; `ALIVE` 1, `CLOSED` 783, `PARKED` 40, `STALLED` 63.
- Top Codex lifecycle families: `auth_credentials` 405, `session_lifecycle` 159, `github_review` 158, `worktree_lifecycle` 77, `agent_coordination` 40, `technical_debt_ci` 36.

## Private Cartridge

- Private root: `~/Workspace/limen/.limen-private/session-corpus`.
- Private inventory: `~/Workspace/limen/.limen-private/session-corpus/inventory/session-corpus-ledger.json`.
- `.limen-private/` is ignored by Git; it is the local raw/private landing zone.
- Materialized objects this run: copied `420`, already present `13161`, bytes copied `286.1 MiB`.
- Private object store now holds `10577` unique objects, `4.5 GiB`.
- Private screenshot evidence: `14` PNG artifacts, `22.9 MiB`, newest `2026-06-27T13:41:25+00:00`.
- Screenshot batches: `2026-06-27` 14.

## Tracked Intake Receipts

- Screenshot intake: `docs/session-screenshot-intake-2026-06-27.md`.
- Session lifecycle drain queue: `docs/session-lifecycle-drain-queue-2026-06-27.md`.
- Session lifecycle blockers: `docs/session-lifecycle-blockers.md`.
- Session attack paths: `docs/session-attack-paths.md`.
- Prompt priority map: `docs/prompt-priority-map.md`.
- Prompt batch review ledger: `docs/prompt-batch-review-ledger.md`.
- Prompt packet ledger: `docs/prompt-packet-ledger.md`.
- Prompt packet resolution receipts: `docs/prompt-packet-resolution-receipts.json`.
- Capability substrate ledger: `docs/capability-substrate-ledger.md`.

## Roadblocks And Potholes

- Local Claude/Codex app stores are live private data; screenshots are only UI evidence. Canonical ingestion must come from the filesystem stores, not from the screenshots.
- session-meta atoms.jsonl is missing, so corpus-converge has no atom substrate.

## Commands

- Refresh the visible all-history ledger: `python3 scripts/session-corpus-ledger.py --write --all`
- Refresh a bounded ledger: `python3 scripts/session-corpus-ledger.py --write --days 7`
- Absorb raw local objects into the ignored cartridge: `python3 scripts/session-corpus-ledger.py --write --all --materialize`
- Refresh local/remote/cloud prompt lifecycle: `python3 scripts/prompt-lifecycle-ledger.py --write --all`
- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`
- Refresh parked blockers: `python3 scripts/session-blockers-ledger.py --write`
- Refresh ranked attack paths: `python3 scripts/session-attack-paths.py --write`
- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Rebuild session-meta atoms after preserving its dirty work: `cd ~/Workspace/session-meta && ./ingest/refresh-atoms.sh`
- Refresh Limen coverage view: `python3 scripts/ingest-coverage.py`
- Classify Codex app/session lifecycle: `python3 scripts/codex-quicken.py --all --apply`
