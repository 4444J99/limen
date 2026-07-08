# Always-Working Reconciliation

Generated: `2026-07-08T05:12:35+00:00`
Status: `needs-work`
Required open: `4`
Blocked: `1`
Done from receipt: `6`

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
| 15 | `PUBLIC-FACE-CONTRIBUTION-BALANCE` | `assigned_from_existing_work` | GitHub activity mix needs owner action: commits 74.1%, PRs 13.3%, issues 12.0%, reviews 0.6% |
| 18 | `CREDENTIAL-WALL-TOKEN-HYGIENE` | `assigned_from_existing_work` | credential wall passes current-home check; historical token tombstone audit still needs owner receipt |
| 20 | `MAIL-ACTIVE-FLAGGED` | `done_from_receipt` | 127 active flagged messages classified into 11 clusters; no body reads or mailbox mutations |
| 30 | `MAIL-HISTORICAL-BACKLOG` | `done_from_receipt` | 500 historical messages atomized in this bounded batch; 82109 indexed non-deleted messages remain for future batches |
| 40 | `REPO-BOIL-UP` | `done_from_receipt` | fresh repo surface ledger covers broad repo estate; 48 duplicate remote group(s) recorded |
| 50 | `PROMPT-PACKETS` | `done_from_receipt` | packet ledger clear from receipts |
| 60 | `VALUE-REPOS` | `done_from_receipt` | top 5 value repos have owner receipts; 14 value repos are sell-ready in the product ledger |
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
- Current beat receipt (`2026-07-08T05:01:28Z`):
  - Value gate: worth doing now as coordination/owner-routing work. The repo is not a value-tier repo, but the packet is critical, budget cost is 1, and the public proof mix is outside the steering rails: commits 74.1% (target <=60%), PRs 13.3% (target >=15%), issues 12.1% (target >=15%), reviews 0.6% (target >=10%). More direct implementation commits would worsen the visible signal.
  - Harvest before predicate: read this receipt, `tasks.yaml` entries `AW-PUBLIC-FACE-CONTRIBUTION-BALANCE` and `GH-organvm-limen-687`, `docs/github-contribution-balance.md`, `scripts/github-contribution-balance.py`, and `cli/tests/test_github_contribution_balance.py`; public profile surface `https://github.com/4444J99` is reachable unauthenticated.
  - Live predicate result: `python3 scripts/github-contribution-balance.py --login 4444J99 --json` exited 2 because `gh api graphql` could not reach `api.github.com`; `gh auth status` also reports the local default token invalid. No secret values were read or recorded.
  - Issue owner receipt: `https://github.com/organvm/limen/issues/687` owns the contribution-balance criteria before more commit-heavy public work.
  - Review route: the next public GitHub action must be a substantive review on an existing open PR, selected after `gh pr list --repo organvm/limen --state open --json number,title,reviewDecision,mergeStateStatus,url` succeeds. Record the review URL here or on issue #687 before starting new implementation.
  - PR packaging route: the next implementation unit must be packaged as a branch + PR linked to issue #687. Direct `main` commits are limited to narrow owner receipts like this one, daemon snapshots, or urgent protocol repair.
  - Stop rule: commit-only implementation churn is not the next public action; review first, then issue criteria refresh, then PR packaging.

### CREDENTIAL-WALL-TOKEN-HYGIENE

- Lane fit: `codex-integrator`
- Repo/root: `~/Workspace/limen`
- Task: Keep token/scope failures out of chat by registering every current credential atom and adding a historical tombstone receipt for formerly exposed or rotated tokens. Never record secret values.
- Predicate: `python3 scripts/credential-wall.py --check && test -f docs/credential-token-tombstone-audit.md`
- Receipt target: `~/Workspace/limen/docs/credential-token-tombstone-audit.md`
- Stop condition: current credential wall passes and historic token existence/revocation custody is recorded without values
- Existing receipts:
  - `~/Workspace/limen/scripts/credential-wall.py`
  - `~/Workspace/limen/scripts/creds-hydrate.py`
  - `https://github.com/organvm/limen/issues/320`
  - `https://github.com/organvm/limen/labels/credential`

