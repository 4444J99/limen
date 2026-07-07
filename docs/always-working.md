# Always-Working Reconciliation

Generated: `2026-07-07T20:10:06+00:00`
Status: `needs-work`
Required open: `2`
Blocked: `1`
Done from receipt: `5`

## Contract

- Start by harvesting existing receipts, not by doing a first run.
- A workstream is `done_from_receipt`, `assigned_from_existing_work`, `needs_assignment`, or `blocked`.
- Generic CI, rebase, and queue draining do not count while required user-promise work is open.
- Email send and destructive repo consolidation remain gated.
- Missing assignments are emitted through TABVLARIVS tickets, never by direct board edits.

## Next Packet

- ID: `VALUE-REPOS`
- Workstream: `revenue-value-repos`
- Status: `assigned_from_existing_work`
- Verdict: 14 value repos define the funded work lane
- Lane fit: `jules-or-opencode-repo-specific`
- Predicate: `python3 scripts/product-ledger.py --write`
- Receipt target: `~/Workspace/limen/docs/product-ledger.md`

## Workstreams

| Priority | ID | Status | Verdict |
|---:|---|---|---|
| 0 | `SUBSTRATE-DISK-TEMP` | `done_from_receipt` | disk/temp above configured floor |
| 10 | `PUBLIC-FACE-PROFILE` | `blocked` | visible profile README is current; GitHub sidebar bio/link needs profile-settings scope |
| 20 | `MAIL-ACTIVE-FLAGGED` | `done_from_receipt` | 127 active flagged messages classified into 11 clusters; no body reads or mailbox mutations |
| 30 | `MAIL-HISTORICAL-BACKLOG` | `done_from_receipt` | 500 historical messages atomized in this bounded batch; 82042 indexed non-deleted messages remain for future batches |
| 40 | `REPO-BOIL-UP` | `done_from_receipt` | fresh repo surface ledger covers broad repo estate; 48 duplicate remote group(s) recorded |
| 50 | `PROMPT-PACKETS` | `done_from_receipt` | packet ledger clear from receipts |
| 60 | `VALUE-REPOS` | `assigned_from_existing_work` | 14 value repos define the funded work lane |
| 70 | `TABVLARIVS-STATUS-WRITERS` | `assigned_from_existing_work` | Step 2.2 still open in the keeper doc |

## Assignment Packets

### PUBLIC-FACE-PROFILE

- Lane fit: `codex-integrator`
- Repo/root: `~/Workspace/organvm/4444J99`
- Task: Project the existing positioning/frontdoor and current metrics onto the profile README; fix stale counts and dead links.
- Predicate: `python3 scripts/test_sync_readme.py && python3 scripts/sync-readme.py --check`
- Receipt target: `~/Workspace/organvm/4444J99/README.md`
- Stop condition: profile README has current metrics, live links, and evidence-backed top-engineer positioning
- Existing receipts:
  - `~/Workspace/limen/docs/positioning/_frontdoor.md`
  - `~/Workspace/limen/his-hand-levers.json`
  - `~/Workspace/limen/face-ownership.json`
  - `~/Workspace/organvm/4444J99/README.md`
  - `https://github.com/4444J99/4444J99`

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

