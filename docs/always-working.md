# Always-Working Reconciliation

Generated: `2026-09-10T23:39:34+00:00`
Status: `needs-work`
Required open: `4`
Blocked: `2`
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
- Predicate: `python3 -m pytest cli/tests/test_reclaim_worktrees.py -q`
- Receipt target: `git:4444J99/limen:docs/worktree-preservation-receipts.json`

## Workstreams

| Priority | ID | Status | Verdict |
|---:|---|---|---|
| 0 | `SUBSTRATE-DISK-TEMP` | `assigned_from_existing_work` | substrate lifecycle predicate is failing |
| 5 | `ESTATE-CUSTODY` | `blocked` | external estate custody is missing required mounted evidence |
| 10 | `PUBLIC-FACE-PROFILE` | `blocked` | profile repo README missing |
| 15 | `PUBLIC-FACE-CONTRIBUTION-BALANCE` | `assigned_from_existing_work` | GitHub activity mix needs owner action: commits 69.6%, PRs 17.2%, issues 12.4%, reviews 0.7% |
| 18 | `CREDENTIAL-WALL-TOKEN-HYGIENE` | `done_from_receipt` | credential wall and historical token tombstone receipt are present |
| 20 | `MAIL-ACTIVE-FLAGGED` | `done_from_receipt` | no active flagged messages remain |
| 30 | `MAIL-HISTORICAL-BACKLOG` | `done_from_receipt` | no indexed mail backlog visible |
| 40 | `REPO-BOIL-UP` | `needs_assignment` | repo surface ledger missing; assignment must refresh existing roots before new work |
| 50 | `PROMPT-PACKETS` | `done_from_receipt` | packet ledger clear from receipts |
| 60 | `VALUE-REPOS` | `assigned_from_existing_work` | 19 value repos define the funded work lane |
| 70 | `TABVLARIVS-STATUS-WRITERS` | `done_from_receipt` | status-mutator tier is recorded closed |

## Assignment Packets

### SUBSTRATE-DISK-TEMP

- Lane fit: `codex-local`
- Repo/root: `4444J99/limen`
- Task: Run exactly one accepted worktree-reclaim tranche from an isolated Limen owner worktree: LIMEN_RECLAIM_GENERATED=0 LIMEN_RECLAIM_MAX=3 python3 scripts/reclaim-worktrees.py --apply --force --json. The generated-cleanup disable is mandatory: do not run generated-state, tool-cache, Ollama, or clone reclaimers in this packet. Record each removed root and the exact apply receipt in docs/worktree-preservation-receipts.json, then push one narrow owner PR.
- Predicate: `python3 -m pytest cli/tests/test_reclaim_worktrees.py -q`
- Receipt target: `git:4444J99/limen:docs/worktree-preservation-receipts.json`
- Stop condition: one tranche removes at most three accepted roots or records that no accepted root remains; every residual root stays preserved for a later packet
- Existing receipts:
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/logs/heartbeat.out.log`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/logs/reclaim-generated-state.jsonl`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/logs/reclaim-tool-caches.jsonl`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/logs/reclaim-ollama-models.jsonl`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/substrate-storage-pressure.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/opencode-db-corpus-intake.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/cvstos-organ.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/dispatch-health.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/opencode-db-corpus-intake.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/reclaim-generated-state.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/reclaim-ollama-models.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/reclaim-tool-caches.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/reclaim-worktrees.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/reap-clones.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/substrate-storage-pressure.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/worktree-debt.py`

### ESTATE-CUSTODY

- Lane fit: `codex-conductor`
- Repo/root: `4444J99/limen`
- Task: Build the run-and-gun estate lifecycle: external SSDs hold durable private/raw data, processed/redacted corpora, repo/org mirrors, photos/media packages, and recovery copies; the laptop stays a thin hot cache. Route every pain point to an owner repo and a reusable public shell when private data can be redacted. Use the worktree reclaim candidate packet as the score-gated cleanup input; do not delete local roots without acceptance/redaction proof.
- Predicate: `test -f docs/estate-custody-primitives.md && python3 scripts/worktree-reclaim-candidates.py --write --limit 50 && python3 scripts/substrate-ledger.py --write && python3 scripts/vltima-prior-excavations.py --write`
- Receipt target: `git:4444J99/limen:docs/estate-custody-implementation-receipts.json`
- Stop condition: external estate cleanup, prompt chronology, repo/org custody, photos processing, and pain-point productization each have owner receipts without destructive local-only action
- Existing receipts:
  - `/Volumes/Archive4T/_OPERATIONS/STORAGE-OPERATING-MANUAL-2026-06-15.md`
  - `/Volumes/Archive4T/_OPERATIONS/LOCAL-DISK-EXPULSION-POLICY-2026-06-15.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/vltima-absorb-cadence.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/vltima-prior-excavations.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/photos-universe-recovery-2026-06-29.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/estate-custody-primitives.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/worktree-reclaim-candidates.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/worktree-reclaim-candidates.json`
  - `https://github.com/4444J99/limen/issues/685`
  - `https://github.com/4444J99/limen/issues/688`
  - `https://github.com/organvm/media-ark/issues/56`
  - `https://github.com/organvm/portvs/issues/2`

### PUBLIC-FACE-PROFILE

- Lane fit: `codex-integrator`
- Repo/root: `4444J99/4444J99`
- Task: Project the existing positioning/frontdoor and current metrics onto the profile README; fix stale counts and dead links.
- Predicate: `python3 scripts/test_sync_readme.py && python3 scripts/sync-readme.py --check`
- Receipt target: `git:4444J99/4444J99:README.md`
- Stop condition: profile README has current metrics, live links, approved positioning, and no forbidden ranking claims
- Existing receipts:
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/positioning/_frontdoor.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/his-hand-levers.json`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/face-ownership.json`
  - `~/Workspace/organvm/4444J99/README.md`
  - `https://github.com/4444J99/4444J99`

### PUBLIC-FACE-CONTRIBUTION-BALANCE

- Lane fit: `codex-conductor`
- Repo/root: `4444J99/limen`
- Task: Run python3 scripts/github-contribution-balance.py --login 4444J99 --json and use the live contribution balance as a value gate: route the next public work to substantive PR review first, then real issue criteria and PR packaging, before more commit-heavy implementation churn.
- Predicate: `python3 -m pytest cli/tests/test_github_contribution_balance.py -q`
- Receipt target: `git:4444J99/limen:docs/always-working.md`
- Stop condition: reviews/issues/PRs have owner receipts and commit-only churn is no longer the next public action
- Existing receipts:
  - `~/Workspace/limen/docs/github-contribution-balance.md`
  - `~/Workspace/limen/scripts/github-contribution-balance.py`
  - `~/Workspace/limen/cli/tests/test_github_contribution_balance.py`
  - `https://github.com/4444J99/limen/issues/687`
  - `https://github.com/4444J99`

### REPO-BOIL-UP

- Lane fit: `agy-or-opencode-readonly`
- Repo/root: `4444J99/limen`
- Task: Run python3 scripts/repo-surface-ledger.py --scan-root ~/Workspace --max-depth 6 --write. Harvest existing repo-surface and consolidation receipts, then assign only missing classifications.
- Predicate: `scripts/verify-scoped.sh`
- Receipt target: `git:4444J99/limen:docs/repo-surface-ledger.md`
- Stop condition: all discovered roots are classified or recorded with blocker/gate
- Existing receipts:
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/repo-surface-ledger.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/consolidation/GATES.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/consolidation/EXECUTION-MANIFEST.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/repo-surface-ledger.py`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/salvage-yard-map.py`

### VALUE-REPOS

- Lane fit: `jules-or-opencode-repo-specific`
- Repo/root: `4444J99/limen`
- Task: Harvest existing PRs/tasks for top value repos, then assign only clean bounded ship predicates.
- Predicate: `python3 scripts/product-ledger.py --write`
- Receipt target: `git:4444J99/limen:docs/product-ledger.md`
- Stop condition: top value repo has shipped PR, open PR with predicate, owner task, or blocker
- Existing receipts:
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/value-repos.json`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/product-ledger.md`
  - `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/docs/positioning/_frontdoor.md`

