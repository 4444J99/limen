# Always-Working Reconciliation

Generated: `2026-07-07T20:19:32+00:00`
Status: `blocked`
Required open: `0`
Blocked: `1`
Done from receipt: `7`

## Contract

- Start by harvesting existing receipts, not by doing a first run.
- A workstream is `done_from_receipt`, `assigned_from_existing_work`, `needs_assignment`, or `blocked`.
- Generic CI, rebase, and queue draining do not count while required user-promise work is open.
- Email send and destructive repo consolidation remain gated.
- Missing assignments are emitted through TABVLARIVS tickets, never by direct board edits.

## Next Packet

- ID: `PUBLIC-FACE-PROFILE`
- Workstream: `public-face`
- Status: `blocked`
- Verdict: visible profile README is current; GitHub sidebar bio/link needs profile-settings scope
- Lane fit: `codex-integrator`
- Predicate: `python3 scripts/test_sync_readme.py && python3 scripts/sync-readme.py --check`
- Receipt target: `~/Workspace/organvm/4444J99/README.md`

## Workstreams

| Priority | ID | Status | Verdict |
|---:|---|---|---|
| 0 | `SUBSTRATE-DISK-TEMP` | `done_from_receipt` | disk/temp above configured floor |
| 10 | `PUBLIC-FACE-PROFILE` | `blocked` | visible profile README is current; GitHub sidebar bio/link needs profile-settings scope |
| 20 | `MAIL-ACTIVE-FLAGGED` | `done_from_receipt` | 127 active flagged messages classified into 11 clusters; no body reads or mailbox mutations |
| 30 | `MAIL-HISTORICAL-BACKLOG` | `done_from_receipt` | 500 historical messages atomized in this bounded batch; 82042 indexed non-deleted messages remain for future batches |
| 40 | `REPO-BOIL-UP` | `done_from_receipt` | fresh repo surface ledger covers broad repo estate; 48 duplicate remote group(s) recorded |
| 50 | `PROMPT-PACKETS` | `done_from_receipt` | packet ledger clear from receipts |
| 60 | `VALUE-REPOS` | `done_from_receipt` | top 5 value repos have owner receipts; 14 value repos are sell-ready in the product ledger |
| 70 | `TABVLARIVS-STATUS-WRITERS` | `done_from_receipt` | status-mutator tier is recorded closed |

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

