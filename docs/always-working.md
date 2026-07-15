# Always-Working Reconciliation

Generated: `2026-07-15T16:04:18+00:00`
Status: `needs-work`
Required open: `5`
Blocked: `1`
Done from receipt: `5`

## Contract

- Start by harvesting existing receipts, not by doing a first run.
- A workstream is `done_from_receipt`, `assigned_from_existing_work`, `needs_assignment`, or `blocked`.
- Generic CI, rebase, and queue draining do not count while required user-promise work is open.
- Email send and destructive repo consolidation remain gated.
- Missing assignments are emitted through TABVLARIVS tickets, never by direct board edits.

## Next Packet

- ID: `SUBSTRATE-DISK-TEMP`
- Workstream: `substrate`
- Status: `assigned_from_existing_work`
- Verdict: substrate lifecycle predicate is failing
- Lane fit: `codex-local`
- Predicate: `python3 scripts/reclaim-generated-state.py --apply && python3 scripts/reclaim-tool-caches.py --apply && python3 scripts/reclaim-ollama-models.py --apply && python3 scripts/substrate-storage-pressure.py --write && python3 scripts/cvstos-organ.py --check && python3 scripts/worktree-debt.py --fail-on-debt --fail-reapable-over-cap`
- Receipt target: `git:organvm/limen:docs/estate-custody-implementation-receipts.json`

## Workstreams

| Priority | ID | Status | Verdict |
|---:|---|---|---|
| 0 | `SUBSTRATE-DISK-TEMP` | `assigned_from_existing_work` | substrate lifecycle predicate is failing |
| 5 | `ESTATE-CUSTODY` | `done_from_receipt` | run-and-gun laptop cache and external estate custody have implementation receipts |
| 10 | `PUBLIC-FACE-PROFILE` | `blocked` | visible profile README is current; GitHub sidebar bio/link needs profile-settings scope |
| 15 | `PUBLIC-FACE-CONTRIBUTION-BALANCE` | `assigned_from_existing_work` | GitHub activity mix needs owner action: commits 73.6%, PRs 14.3%, issues 11.3%, reviews 0.9% |
| 18 | `CREDENTIAL-WALL-TOKEN-HYGIENE` | `done_from_receipt` | credential wall and historical token tombstone receipt are present |
| 20 | `MAIL-ACTIVE-FLAGGED` | `assigned_from_existing_work` | 144 active flagged non-deleted messages require classification |
| 30 | `MAIL-HISTORICAL-BACKLOG` | `done_from_receipt` | 500 historical messages atomized in this bounded batch; 85058 indexed non-deleted messages remain for future batches |
| 40 | `REPO-BOIL-UP` | `assigned_from_existing_work` | broad repo surface ledger exists, but it is stale for current boil-up work |
| 50 | `PROMPT-PACKETS` | `done_from_receipt` | packet ledger clear from receipts |
| 60 | `VALUE-REPOS` | `assigned_from_existing_work` | value repo product ledger exists, but it is stale for current funded-lane steering |
| 70 | `TABVLARIVS-STATUS-WRITERS` | `done_from_receipt` | status-mutator tier is recorded closed |

## Assignment Packets

### SUBSTRATE-DISK-TEMP

- Lane fit: `codex-local`
- Repo/root: `organvm/limen`
- Task: Reclaim ignored generated state, preserve or owner-route local-only payloads, and keep Scratch as the active work substrate.
- Predicate: `python3 scripts/reclaim-generated-state.py --apply && python3 scripts/reclaim-tool-caches.py --apply && python3 scripts/reclaim-ollama-models.py --apply && python3 scripts/substrate-storage-pressure.py --write && python3 scripts/cvstos-organ.py --check && python3 scripts/worktree-debt.py --fail-on-debt --fail-reapable-over-cap`
- Receipt target: `git:organvm/limen:docs/estate-custody-implementation-receipts.json`
- Stop condition: free disk is at target, temp writes are usable, worktree debt is exactly zero, and reapable roots are zero
- Existing receipts:
  - `~/Workspace/limen/logs/heartbeat.out.log`
  - `~/Workspace/limen/logs/reclaim-generated-state.jsonl`
  - `~/Workspace/limen/logs/reclaim-tool-caches.jsonl`
  - `~/Workspace/limen/logs/reclaim-ollama-models.jsonl`
  - `~/Workspace/limen/docs/substrate-storage-pressure.md`
  - `~/Workspace/limen/docs/opencode-db-corpus-intake.md`
  - `~/Workspace/limen/scripts/cvstos-organ.py`
  - `~/Workspace/limen/scripts/dispatch-health.py`
  - `~/Workspace/limen/scripts/opencode-db-corpus-intake.py`
  - `~/Workspace/limen/scripts/reclaim-generated-state.py`
  - `~/Workspace/limen/scripts/reclaim-ollama-models.py`
  - `~/Workspace/limen/scripts/reclaim-tool-caches.py`
  - `~/Workspace/limen/scripts/reclaim-worktrees.py`
  - `~/Workspace/limen/scripts/reap-clones.py`
  - `~/Workspace/limen/scripts/substrate-storage-pressure.py`
  - `~/Workspace/limen/scripts/worktree-debt.py`

### PUBLIC-FACE-PROFILE

- Lane fit: `codex-integrator`
- Repo/root: `4444J99/4444J99`
- Task: Project the existing positioning/frontdoor and current metrics onto the profile README; fix stale counts and dead links.
- Predicate: `python3 scripts/test_sync_readme.py && python3 scripts/sync-readme.py --check`
- Receipt target: `git:4444J99/4444J99:README.md`
- Stop condition: profile README has current metrics, live links, and evidence-backed top-engineer positioning
- Existing receipts:
  - `~/Workspace/limen/docs/positioning/_frontdoor.md`
  - `~/Workspace/limen/his-hand-levers.json`
  - `~/Workspace/limen/face-ownership.json`
  - `~/Workspace/organvm/4444J99/README.md`
  - `https://github.com/4444J99/4444J99`

### PUBLIC-FACE-CONTRIBUTION-BALANCE

- Lane fit: `codex-conductor`
- Repo/root: `organvm/limen`
- Task: Use the live contribution balance as a value gate: route the next public work to substantive PR review first, then real issue criteria and PR packaging, before more commit-heavy implementation churn.
- Predicate: `python3 scripts/github-contribution-balance.py --login 4444J99 --json`
- Receipt target: `git:organvm/limen:docs/always-working.md`
- Stop condition: reviews/issues/PRs have owner receipts and commit-only churn is no longer the next public action
- Existing receipts:
  - `~/Workspace/limen/docs/github-contribution-balance.md`
  - `~/Workspace/limen/scripts/github-contribution-balance.py`
  - `~/Workspace/limen/cli/tests/test_github_contribution_balance.py`
  - `https://github.com/organvm/limen/issues/687`
  - `https://github.com/4444J99`

### MAIL-ACTIVE-FLAGGED

- Lane fit: `local-codex-or-opencode`
- Repo/root: `organvm/limen`
- Task: Use existing mail-story atoms and UMA obligations to classify the active flagged set; draft/park, never send.
- Predicate: `python3 scripts/mail-story-ledger.py --scope flagged --write`
- Receipt target: `git:organvm/limen:docs/mail-story-ledger.md`
- Stop condition: flagged set has classified atoms, obligations, and needs-human buckets
- Existing receipts:
  - `~/Workspace/limen/docs/mail-story-ledger.md`
  - `~/Workspace/limen/docs/his-hand-registry-mail-a290329e.md`
  - `~/Workspace/limen/obligations-ledger.json`
  - `~/Workspace/limen/scripts/mail-story-ledger.py`
  - `~/Workspace/limen/scripts/mail-beat.sh`

### REPO-BOIL-UP

- Lane fit: `agy-or-opencode-readonly`
- Repo/root: `organvm/limen`
- Task: Harvest existing repo-surface and consolidation receipts, then assign only missing classifications.
- Predicate: `python3 scripts/repo-surface-ledger.py --scan-root ~/Workspace --max-depth 6 --write`
- Receipt target: `git:organvm/limen:docs/repo-surface-ledger.md`
- Stop condition: all discovered roots are classified or recorded with blocker/gate
- Existing receipts:
  - `~/Workspace/limen/docs/repo-surface-ledger.md`
  - `~/Workspace/limen/docs/consolidation/GATES.md`
  - `~/Workspace/limen/docs/consolidation/EXECUTION-MANIFEST.md`
  - `~/Workspace/limen/scripts/repo-surface-ledger.py`
  - `~/Workspace/limen/scripts/salvage-yard-map.py`

### VALUE-REPOS

- Lane fit: `jules-or-opencode-repo-specific`
- Repo/root: `organvm/limen`
- Task: Harvest existing PRs/tasks for top value repos, then assign only clean bounded ship predicates.
- Predicate: `python3 scripts/product-ledger.py --write`
- Receipt target: `git:organvm/limen:docs/product-ledger.md`
- Stop condition: top value repo has shipped PR, open PR with predicate, owner task, or blocker
- Existing receipts:
  - `~/Workspace/limen/value-repos.json`
  - `~/Workspace/limen/docs/product-ledger.md`
  - `~/Workspace/limen/docs/positioning/_frontdoor.md`

