# Always-Working Reconciliation

Generated: `2026-07-09T21:52:05+00:00`
Status: `needs-work`
Required open: `6`
Blocked: `1`
Done from receipt: `4`

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
- Verdict: disk/temp pressure needs owner work
- Lane fit: `codex-local`
- Predicate: `python3 scripts/cvstos-organ.py --check && python3 scripts/worktree-debt.py --fail-over-cap`
- Receipt target: `~/Workspace/limen/logs/cvstos-organ-state.json`

## Workstreams

| Priority | ID | Status | Verdict |
|---:|---|---|---|
| 0 | `SUBSTRATE-DISK-TEMP` | `assigned_from_existing_work` | disk/temp pressure needs owner work |
| 5 | `ESTATE-CUSTODY` | `assigned_from_existing_work` | estate doctrine exists; implementation receipt is not complete |
| 10 | `PUBLIC-FACE-PROFILE` | `blocked` | visible profile README is current; GitHub sidebar bio/link needs profile-settings scope |
| 15 | `PUBLIC-FACE-CONTRIBUTION-BALANCE` | `assigned_from_existing_work` | GitHub activity mix needs owner action: commits 73.7%, PRs 13.7%, issues 11.8%, reviews 0.8% |
| 18 | `CREDENTIAL-WALL-TOKEN-HYGIENE` | `done_from_receipt` | credential wall and historical token tombstone receipt are present |
| 20 | `MAIL-ACTIVE-FLAGGED` | `assigned_from_existing_work` | 131 active flagged non-deleted messages require classification |
| 30 | `MAIL-HISTORICAL-BACKLOG` | `done_from_receipt` | 500 historical messages atomized in this bounded batch; 83150 indexed non-deleted messages remain for future batches |
| 40 | `REPO-BOIL-UP` | `assigned_from_existing_work` | broad repo surface ledger exists, but it is stale for current boil-up work |
| 50 | `PROMPT-PACKETS` | `done_from_receipt` | packet ledger clear from receipts |
| 60 | `VALUE-REPOS` | `assigned_from_existing_work` | value repo product ledger exists, but it is stale for current funded-lane steering |
| 70 | `TABVLARIVS-STATUS-WRITERS` | `done_from_receipt` | status-mutator tier is recorded closed |

## Assignment Packets

### SUBSTRATE-DISK-TEMP

- Lane fit: `codex-local`
- Repo/root: `~/Workspace/limen`
- Task: Audit disk/temp pressure, worktree debt, and disposable local clone lifecycle before spawning more lanes.
- Predicate: `python3 scripts/cvstos-organ.py --check && python3 scripts/worktree-debt.py --fail-over-cap`
- Receipt target: `~/Workspace/limen/logs/cvstos-organ-state.json`
- Stop condition: free disk is at target, temp writes are usable, and reclaimable worktree debt is owner-routed
- Existing receipts:
  - `~/Workspace/limen/logs/heartbeat.out.log`
  - `~/Workspace/limen/scripts/cvstos-organ.py`
  - `~/Workspace/limen/scripts/dispatch-health.py`
  - `~/Workspace/limen/scripts/reclaim-worktrees.py`
  - `~/Workspace/limen/scripts/reap-clones.py`
  - `~/Workspace/limen/scripts/worktree-debt.py`

### ESTATE-CUSTODY

- Lane fit: `codex-conductor`
- Repo/root: `~/Workspace/limen`
- Task: Build the run-and-gun estate lifecycle: external SSDs hold durable private/raw data, processed/redacted corpora, repo/org mirrors, photos/media packages, and recovery copies; the laptop stays a thin hot cache. Route every pain point to an owner repo and a reusable public shell when private data can be redacted. Use the worktree reclaim candidate packet as the score-gated cleanup input; do not delete local roots without acceptance/redaction proof.
- Predicate: `test -f docs/estate-custody-primitives.md && python3 scripts/worktree-reclaim-candidates.py --write --limit 50 && python3 scripts/substrate-ledger.py --write && python3 scripts/vltima-prior-excavations.py --write`
- Receipt target: `~/Workspace/limen/docs/estate-custody-implementation-receipts.json`
- Stop condition: external estate cleanup, prompt chronology, repo/org custody, photos processing, and pain-point productization each have owner receipts without destructive local-only action
- Existing receipts:
  - `/Volumes/Archive4T/_OPERATIONS/STORAGE-OPERATING-MANUAL-2026-06-15.md`
  - `/Volumes/Archive4T/_OPERATIONS/LOCAL-DISK-EXPULSION-POLICY-2026-06-15.md`
  - `~/Workspace/limen/docs/vltima-absorb-cadence.md`
  - `~/Workspace/limen/docs/vltima-prior-excavations.md`
  - `~/Workspace/limen/docs/photos-universe-recovery-2026-06-29.md`
  - `~/Workspace/limen/docs/estate-custody-primitives.md`
  - `~/Workspace/limen/docs/worktree-reclaim-candidates.md`
  - `~/Workspace/limen/docs/worktree-reclaim-candidates.json`
  - `https://github.com/organvm/limen/issues/685`
  - `https://github.com/organvm/limen/issues/688`
  - `https://github.com/organvm/media-ark/issues/56`
  - `https://github.com/organvm/portvs/issues/2`

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

### PUBLIC-FACE-CONTRIBUTION-BALANCE

- Lane fit: `codex-conductor`
- Repo/root: `~/Workspace/limen`
- Task: Use the live contribution balance as a value gate: route the next public work to substantive PR review first, then real issue criteria and PR packaging, before more commit-heavy implementation churn.
- Predicate: `python3 scripts/github-contribution-balance.py --login 4444J99 --json`
- Receipt target: `~/Workspace/limen/docs/always-working.md`
- Stop condition: reviews/issues/PRs have owner receipts and commit-only churn is no longer the next public action
- Existing receipts:
  - `~/Workspace/limen/docs/github-contribution-balance.md`
  - `~/Workspace/limen/scripts/github-contribution-balance.py`
  - `~/Workspace/limen/cli/tests/test_github_contribution_balance.py`
  - `https://github.com/organvm/limen/issues/687`
  - `https://github.com/4444J99`

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

