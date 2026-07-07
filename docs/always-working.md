# Always-Working Reconciliation

Generated: `2026-07-07T19:54:34+00:00`
Status: `needs-work`
Required open: `5`
Blocked: `0`
Done from receipt: `3`

## Contract

- Start by harvesting existing receipts, not by doing a first run.
- A workstream is `done_from_receipt`, `assigned_from_existing_work`, `needs_assignment`, or `blocked`.
- Generic CI, rebase, and queue draining do not count while required user-promise work is open.
- Email send and destructive repo consolidation remain gated.
- Missing assignments are emitted through TABVLARIVS tickets, never by direct board edits.

## Next Packet

- ID: `MAIL-ACTIVE-FLAGGED`
- Workstream: `mail-active`
- Status: `assigned_from_existing_work`
- Verdict: 127 active flagged non-deleted messages require classification
- Lane fit: `local-codex-or-opencode`
- Predicate: `python3 scripts/mail-story-ledger.py --scope flagged --write`
- Receipt target: `~/Workspace/limen/docs/mail-story-ledger.md`

## Workstreams

| Priority | ID | Status | Verdict |
|---:|---|---|---|
| 0 | `SUBSTRATE-DISK-TEMP` | `done_from_receipt` | disk/temp above configured floor |
| 10 | `PUBLIC-FACE-PROFILE` | `done_from_receipt` | profile README reflects current proof surface |
| 20 | `MAIL-ACTIVE-FLAGGED` | `assigned_from_existing_work` | 127 active flagged non-deleted messages require classification |
| 30 | `MAIL-HISTORICAL-BACKLOG` | `assigned_from_existing_work` | 82042 indexed non-deleted messages exist; process in batches, not one giant run |
| 40 | `REPO-BOIL-UP` | `assigned_from_existing_work` | broad repo surface ledger exists, but it is stale for current boil-up work |
| 50 | `PROMPT-PACKETS` | `done_from_receipt` | packet ledger clear from receipts |
| 60 | `VALUE-REPOS` | `assigned_from_existing_work` | 14 value repos define the funded work lane |
| 70 | `TABVLARIVS-STATUS-WRITERS` | `assigned_from_existing_work` | Step 2.2 still open in the keeper doc |

## Assignment Packets

### MAIL-ACTIVE-FLAGGED

- Lane fit: `local-codex-or-opencode`
- Repo/root: `~/Workspace/limen`
- Task: Use existing mail-story atoms and UMA obligations to classify the active flagged set; draft/park, never send.
- Predicate: `python3 scripts/mail-story-ledger.py --scope flagged --write`
- Receipt target: `~/Workspace/limen/docs/mail-story-ledger.md`
- Stop condition: flagged set has classified atoms, obligations, and needs-human buckets
- Existing receipts:
  - `~/Workspace/limen/docs/mail-story-ledger.md`
  - `~/Workspace/limen/docs/his-hand-registry-mail-a290329e.md`
  - `~/Workspace/limen/obligations-ledger.json`
  - `~/Workspace/limen/scripts/mail-story-ledger.py`
  - `~/Workspace/limen/scripts/mail-beat.sh`

### MAIL-HISTORICAL-BACKLOG

- Lane fit: `local-codex-or-opencode`
- Repo/root: `~/Workspace/limen`
- Task: Continue the historical metadata sweep from existing receipts; emit batch cursor/count receipt before any thread enrichment.
- Predicate: `python3 scripts/mail-story-ledger.py --scope all --limit 500 --write`
- Receipt target: `~/Workspace/limen/docs/mail-story-ledger.md`
- Stop condition: next 500 historical messages are atomized or a precise cursor/blocker is recorded
- Existing receipts:
  - `~/Workspace/limen/docs/mail-story-ledger.md`
  - `~/Workspace/limen/docs/his-hand-registry-mail-a290329e.md`
  - `~/Workspace/limen/obligations-ledger.json`
  - `~/Workspace/limen/scripts/mail-story-ledger.py`
  - `~/Workspace/limen/scripts/mail-beat.sh`

### REPO-BOIL-UP

- Lane fit: `agy-or-opencode-readonly`
- Repo/root: `~/Workspace/limen`
- Task: Harvest existing repo-surface and consolidation receipts, then assign only missing classifications.
- Predicate: `python3 scripts/repo-surface-ledger.py --scan-root ~/Workspace --max-depth 6 --write`
- Receipt target: `~/Workspace/limen/docs/repo-surface-ledger.md`
- Stop condition: all discovered roots are classified or recorded with blocker/gate
- Existing receipts:
  - `~/Workspace/limen/docs/repo-surface-ledger.md`
  - `~/Workspace/limen/docs/consolidation/GATES.md`
  - `~/Workspace/limen/docs/consolidation/EXECUTION-MANIFEST.md`
  - `~/Workspace/limen/scripts/repo-surface-ledger.py`
  - `~/Workspace/limen/scripts/salvage-yard-map.py`

### VALUE-REPOS

- Lane fit: `jules-or-opencode-repo-specific`
- Repo/root: `organvm/a-i-chat--exporter,organvm/my-knowledge-base,organvm/public-record-data-scrapper,organvm/peer-audited--behavioral-blockchain,organvm/mirror-mirror`
- Task: Harvest existing PRs/tasks for top value repos, then assign only clean bounded ship predicates.
- Predicate: `python3 scripts/product-ledger.py --write`
- Receipt target: `~/Workspace/limen/docs/product-ledger.md`
- Stop condition: top value repo has shipped PR, open PR with predicate, owner task, or blocker
- Existing receipts:
  - `~/Workspace/limen/value-repos.json`
  - `~/Workspace/limen/docs/product-ledger.md`
  - `~/Workspace/limen/docs/positioning/_frontdoor.md`

### TABVLARIVS-STATUS-WRITERS

- Lane fit: `codex-integrator`
- Repo/root: `~/Workspace/limen`
- Task: Convert status/result writers to keeper tickets; preserve tasks.yaml drift as separate board state.
- Predicate: `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q`
- Receipt target: `~/Workspace/limen/docs/tabularius-record-keeper.md`
- Stop condition: non-keeper status/result direct writers are converted or explicitly owner-recorded
- Existing receipts:
  - `~/Workspace/limen/docs/tabularius-record-keeper.md`
  - `~/Workspace/limen/cli/src/limen/tabularius.py`

