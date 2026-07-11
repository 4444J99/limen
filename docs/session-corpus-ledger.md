# Session Corpus Ledger

Generated: `2026-07-07T00:04:42+00:00`
Horizon: `all local history`

## Canonical Decision

- Limen is the control plane and visible ledger for session/corpus lifecycle.
- `session-meta` remains the producer for redacted, deduped, multi-provider atoms.
- `knowledge-corpus` remains the distillation target consumed by `corpus-converge.py`.
- `prompt-lifecycle-ledger.py` is the redacted crosswalk from local prompts/sessions to worktrees, tasks, GitHub receipts, and cloud probes.
- Raw personal/session data is private local material. It belongs under `./.limen-private/session-corpus/` when materialized, never in public Git history.
- The app screenshots are coverage hints, not canonical input. Canonical input is the local Claude/Codex/session-meta filesystem state.
- External/archive roots are opt-in through `LIMEN_EXTERNAL_SESSION_ROOTS`; they are bounded inventory inputs, not deletion targets.

## Local Session Sources

Total seen: `14350` files, `3.7 GiB`.

| Source | Root | Files | Size | Newest |
|---|---:|---:|---:|---|
| `claude-projects` | `~/.claude/projects` | 6755 | 1.9 GiB | `2026-07-07T00:00:53+00:00` |
| `codex-sessions` | `~/.local/share/codex/sessions` | 1518 | 1.6 GiB | `2026-07-07T00:04:34+00:00` |
| `claude-file-history` | `~/.claude/file-history` | 5059 | 67.2 MiB | `2026-07-05T18:01:34+00:00` |
| `codex-goals-state` | `~/.local/share/codex` | 6 | 23.3 MiB | `2026-07-07T00:04:35+00:00` |
| `chatgpt-desktop-app-support` | `~/Library/Application Support/com.openai.chat` | 258 | 15.7 MiB | `2026-07-06T15:46:42+00:00` |
| `codex-shell-snapshots` | `~/.local/share/codex/shell_snapshots` | 25 | 8.1 MiB | `2026-07-07T00:00:44+00:00` |
| `codex-history` | `~/.local/share/codex` | 1 | 844.6 KiB | `2026-07-06T23:54:52+00:00` |
| `gemini-desktop-stores` | `~/Library/Application Support/com.google.GeminiMacOS` | 12 | 569.0 KiB | `2026-06-23T21:43:47+00:00` |
| `claude-usage-session-meta` | `~/.claude/usage-data/session-meta` | 397 | 426.9 KiB | `2026-07-03T13:33:18+00:00` |
| `claude-plans` | `~/.claude/plans` | 43 | 369.8 KiB | `2026-07-03T15:08:54+00:00` |
| `claude-desktop-indexeddb` | `~/Library/Application Support/Claude/IndexedDB` | 2 | 359.2 KiB | `2026-06-30T11:06:52+00:00` |
| `codex-app-sqlite` | `~/.local/share/codex/sqlite` | 1 | 68.0 KiB | `2026-06-30T11:03:30+00:00` |
| `claude-tasks` | `~/.claude/tasks` | 206 | 59.9 KiB | `2026-07-03T15:47:52+00:00` |
| `claude-usage-facets` | `~/.claude/usage-data/facets` | 62 | 55.3 KiB | `2026-07-03T13:33:30+00:00` |
| `codex-attachments` | `~/.local/share/codex/attachments` | 4 | 6.2 KiB | `2026-06-27T18:15:45+00:00` |
| `perplexity-desktop-stores` | `~/Library/Application Support/ai.perplexity.macv3` | 1 | 400 B | `2026-06-02T13:20:10+00:00` |

## Missing Local App Sources

These are known local app/store adapters with no matched files in this scan. This is a coverage signal only; roots are not deletion targets.

| Source | Root | Reason |
|---|---|---|
| `chatgpt-atlas-app-support` | `~/Library/Application Support/OpenAI/ChatGPT Atlas` | `no-matching-files` |

## Existing Organs

| Organ | Role | Path | Git state |
|---|---|---|---|
| `session-meta` | producer: redacted, deduped multi-provider atoms | `~/Workspace/session-meta` | `## fix/security-hardening-0629; 1 dirty entries` |
| `knowledge-corpus` | distillation target: collection, reduced faces, THE ONE | `~/Workspace/knowledge-corpus` | `not a git repo` |
| `conversation-corpus-engine` | product/research engine: provider import and corpus promotion | `~/Workspace/conversation-corpus-engine` | `not a git repo` |

## Substrate Counts

- `session-meta/ingest/manifest.jsonl`: 25,309 records, mtime `2026-07-06T23:32:51+00:00`.
- `session-meta/ingest/atoms.jsonl`: 238,119 atoms, mtime `2026-07-06T23:39:25+00:00`.
- `knowledge-corpus`: `0` reduced faces; `00-THE-ONE.md` present: `False`.
- Top manifest sources: `gemini` 4,592, `claude` 3,961, `claude-projects` 3,599, `chatgpt` 2,709, `codex` 2,082, `cowork-sessions` 2,047, `antigravity` 1,893, `downloads` 1,717.

## Session Lifecycle

- Last `quicken.py` journal: `2026-07-06T23:32:02+00:00`.
- Claude FleetView sessions classified: `21` total; `7` stalled, `12` closed, `2` alive, `0` done.
- Reaped worktrees in that pass: `0`.
- Last `codex-quicken.py` journal: `2026-06-27T21:42:32+00:00`.
- Codex sessions classified: `887` total; `ALIVE` 1, `CLOSED` 783, `PARKED` 40, `STALLED` 63.
- Top Codex lifecycle families: `auth_credentials` 405, `session_lifecycle` 159, `github_review` 158, `worktree_lifecycle` 77, `agent_coordination` 40, `technical_debt_ci` 36.

## Private Cartridge

- Private root: `~/Workspace/limen/.limen-private/session-corpus`.
- Private inventory: `~/Workspace/limen/.limen-private/session-corpus/inventory/session-corpus-ledger.json`.
- `.limen-private/` is ignored by Git; it is the local raw/private landing zone.
- Materialized objects this run: copied `323`, already present `14027`, bytes copied `274.6 MiB`.
- Private object store now holds `14168` unique objects, `6.5 GiB`.
- Private screenshot evidence: `14` PNG artifacts, `22.9 MiB`, newest `2026-06-27T13:41:25+00:00`.
- Screenshot batches: `2026-06-27` 14.

## Tracked Intake Receipts

- Screenshot intake: `docs/session-screenshot-intake-2026-06-27.md`.
- Session lifecycle drain queue: `docs/session-lifecycle-drain-queue-2026-06-27.md`.
- Session lifecycle blockers: `docs/session-lifecycle-blockers.md`.
- Session attack paths: `docs/session-attack-paths.md`.
- Prompt priority map: `docs/prompt-priority-map.md`.
- Canonical ask-atom control ledger: `docs/prompt-atom-ledger.md`.
- Prompt batch review ledger: `docs/prompt-batch-review-ledger.md`.
- Prompt packet ledger: `docs/prompt-packet-ledger.md`.
- Prompt packet resolution receipts: `docs/prompt-packet-resolution-receipts.json`.
- Capability substrate ledger: `docs/capability-substrate-ledger.md`.

## Roadblocks And Potholes

- session-meta is not clean/in-sync; do not mutate it from Limen until its existing dirty and divergent work is preserved or merged.
- Local Claude/Codex app stores are live private data; screenshots are only UI evidence. Canonical ingestion must come from the filesystem stores, not from the screenshots.

## Commands

- Refresh the visible all-history ledger: `python3 scripts/session-corpus-ledger.py --write --all`
- Refresh a bounded ledger: `python3 scripts/session-corpus-ledger.py --write --days 7`
- Absorb raw local objects into the ignored cartridge: `python3 scripts/session-corpus-ledger.py --write --all --materialize`
- Refresh local/remote/cloud prompt lifecycle: `python3 scripts/prompt-lifecycle-ledger.py --write --all`
- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`
- Refresh parked blockers: `python3 scripts/session-blockers-ledger.py --write`
- Refresh ranked attack paths: `python3 scripts/session-attack-paths.py --write`
- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`
- Refresh prompt ask atoms: `python3 scripts/prompt-atom-ledger.py --scan --write`
- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`
- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`
- Rebuild session-meta atoms after preserving its dirty work: `cd ~/Workspace/session-meta && ./ingest/refresh-atoms.sh`
- Refresh Limen coverage view: `python3 scripts/ingest-coverage.py`
- Classify Codex app/session lifecycle: `python3 scripts/codex-quicken.py --all --apply`
