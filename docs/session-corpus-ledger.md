# Session Corpus Ledger

Generated: `2026-06-27T20:58:33+00:00`
Horizon: `all local history`

## Canonical Decision

- Limen is the control plane and visible ledger for session/corpus lifecycle.
- `session-meta` remains the producer for redacted, deduped, multi-provider atoms.
- `knowledge-corpus` remains the distillation target consumed by `corpus-converge.py`.
- `prompt-lifecycle-ledger.py` is the redacted crosswalk from local prompts/sessions to worktrees, tasks, GitHub receipts, and cloud probes.
- Raw personal/session data is private local material. It belongs under `./.limen-private/session-corpus/` when materialized, never in public Git history.
- The app screenshots are coverage hints, not canonical input. Canonical input is the local Claude/Codex/session-meta filesystem state.

## Local Session Sources

Total seen: `9722` files, `2.1 GiB`.

| Source | Root | Files | Size | Newest |
|---|---:|---:|---:|---|
| `claude-projects` | `~/.claude/projects` | 4851 | 1.4 GiB | `2026-06-27T20:23:23+00:00` |
| `codex-sessions` | `~/.codex/sessions` | 887 | 710.1 MiB | `2026-06-27T20:58:32+00:00` |
| `claude-file-history` | `~/.claude/file-history` | 3519 | 42.2 MiB | `2026-06-27T00:26:28+00:00` |
| `codex-goals-state` | `~/.codex` | 6 | 12.3 MiB | `2026-06-27T20:58:32+00:00` |
| `claude-plans` | `~/.claude/plans` | 34 | 289.3 KiB | `2026-06-25T03:22:45+00:00` |
| `claude-usage-session-meta` | `~/.claude/usage-data/session-meta` | 197 | 221.4 KiB | `2026-06-23T19:06:40+00:00` |
| `codex-history` | `~/.codex` | 1 | 180.5 KiB | `2026-06-27T20:49:57+00:00` |
| `codex-app-sqlite` | `~/.codex/sqlite` | 1 | 68.0 KiB | `2026-06-27T13:58:29+00:00` |
| `claude-tasks` | `~/.claude/tasks` | 188 | 57.7 KiB | `2026-06-26T00:08:52+00:00` |
| `claude-usage-facets` | `~/.claude/usage-data/facets` | 32 | 29.1 KiB | `2026-06-23T19:06:55+00:00` |
| `codex-attachments` | `~/.codex/attachments` | 4 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |
| `codex-shell-snapshots` | `~/.codex/shell_snapshots` | 2 | 2.6 KiB | `2026-06-27T11:43:56+00:00` |

## Existing Organs

| Organ | Role | Path | Git state |
|---|---|---|---|
| `session-meta` | producer: redacted, deduped multi-provider atoms | `~/Workspace/session-meta` | `## codex/preserve-session-meta-owner-state-20260627; 1 dirty entries` |
| `knowledge-corpus` | distillation target: collection, reduced faces, THE ONE | `~/Workspace/knowledge-corpus` | `## codex/preserve-knowledge-corpus-owner-state-20260627...origin/codex/preserve-knowledge-corpus-owner-state-20260627` |
| `conversation-corpus-engine` | product/research engine: provider import and corpus promotion | `~/Workspace/conversation-corpus-engine` | `## discover-latent-value-corpus-engine...origin/discover-latent-value-corpus-engine` |

## Substrate Counts

- `session-meta/ingest/manifest.jsonl`: 23,541 records, mtime `2026-06-27T20:15:50+00:00`.
- `session-meta/ingest/atoms.jsonl`: 104,756 atoms, mtime `2026-06-27T20:18:39+00:00`.
- `knowledge-corpus`: `13` reduced faces; `00-THE-ONE.md` present: `True`.
- Top manifest sources: `gemini` 4,592, `claude` 3,961, `chatgpt` 2,709, `claude-projects` 2,455, `cowork-sessions` 2,047, `antigravity` 1,893, `downloads` 1,717, `intake` 1,569.

## Session Lifecycle

- Last `quicken.py` journal: `2026-06-27T20:43:02+00:00`.
- Claude FleetView sessions classified: `29` total; `0` stalled, `29` closed, `0` alive, `0` done.
- Reaped worktrees in that pass: `0`.
- Last `codex-quicken.py` journal: `2026-06-27T20:24:22+00:00`.
- Codex sessions classified: `887` total; `ALIVE` 1, `CLOSED` 783, `PARKED` 40, `STALLED` 63.
- Top Codex lifecycle families: `auth_credentials` 405, `session_lifecycle` 159, `github_review` 158, `worktree_lifecycle` 77, `agent_coordination` 40, `technical_debt_ci` 36.

## Private Cartridge

- Private root: `~/Workspace/limen/.limen-private/session-corpus`.
- Private inventory: `~/Workspace/limen/.limen-private/session-corpus/inventory/session-corpus-ledger.json`.
- `.limen-private/` is ignored by Git; it is the local raw/private landing zone.
- Raw object materialization was not requested on this run.
- Private screenshot evidence: `14` PNG artifacts, `22.9 MiB`, newest `2026-06-27T13:41:25+00:00`.
- Screenshot batches: `2026-06-27` 14.

## Tracked Intake Receipts

- Screenshot intake: `docs/session-screenshot-intake-2026-06-27.md`.
- Session lifecycle drain queue: `docs/session-lifecycle-drain-queue-2026-06-27.md`.

## Roadblocks And Potholes

- session-meta is not clean/in-sync; do not mutate it from Limen until its existing dirty and divergent work is preserved or merged.
- Local Claude/Codex app stores are live private data; screenshots are only UI evidence. Canonical ingestion must come from the filesystem stores, not from the screenshots.

## Commands

- Refresh the visible all-history ledger: `python3 scripts/session-corpus-ledger.py --write --all`
- Refresh a bounded ledger: `python3 scripts/session-corpus-ledger.py --write --days 7`
- Absorb raw local objects into the ignored cartridge: `python3 scripts/session-corpus-ledger.py --write --all --materialize`
- Refresh local/remote/cloud prompt lifecycle: `python3 scripts/prompt-lifecycle-ledger.py --write --all`
- Rebuild session-meta atoms after preserving its dirty work: `cd ~/Workspace/session-meta && ./ingest/refresh-atoms.sh`
- Refresh Limen coverage view: `python3 scripts/ingest-coverage.py`
- Classify Codex app/session lifecycle: `python3 scripts/codex-quicken.py --all --apply`
