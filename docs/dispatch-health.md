# Campaign Heartbeat Health

Generated: `2026-08-08T18:31:33+00:00`

Status: `blocked`

## Incident Class

- Campaign-heartbeat health is not proven by tests in a detached worktree alone.
- The live launchd daemon must run the same substrate that the conductor just verified, or the next lane can rediscover stale behavior.
- This receipt is read-only. It stops before launchd reloads, branch switches, resets, task-board writes, or live-root commits.

## Heartbeat

- Generated plist probe: `True` from `~/Workspace/limen/scripts/gen-launchd-plist.sh`.
- Generated LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Generated LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Generated LIMEN_CAMPAIGN_WAKE_TIMEOUT: `300`.
- LaunchAgent plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Plist KeepAlive: `True`; RunAtLoad: `True`.
- Plist LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Plist LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Plist LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Plist LIMEN_CAMPAIGN_WAKE_TIMEOUT: `300`.
- Loaded launchd state: `running` pid `84914`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Loaded LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Loaded LIMEN_CAMPAIGN_WAKE_TIMEOUT: `300`.
- Watchdog dry-run healthy: `False`; `[watchdog] 2026-08-08T18:31:33.895818+00:00 UNHEALTHY sig=beating`.

## Legacy Manual Async Diagnostic

- This optional diagnostic is retained for manual-engine compatibility and does not define campaign-heartbeat health.
- Async dry-run requested: `False`.
- Async dry-run lanes: ``; max ``.
- Async dry-run ok: `None`; timed out `False`.
- Async dry-run summary: ``.

## Prompt Packet Gate

- Prompt packet index present: `True`.
- Prompt packet status: `clear`.
- Open prompt packets: `0`.
- Conductor-required packets: `0`.
- Ready-after-predicate packets: `0`.
- Recorded packets: `0`.
- Public packet ledger: `~/Workspace/limen/docs/prompt-packet-ledger.md`.

## Always-Working Gate

- Reconciliation index present: `True`.
- Reconciliation status: `needs-work`.
- Required open workstreams: `5`.
- Blocked workstreams: `2`.
- Done from receipt: `4`.
- Next item: `SUBSTRATE-DISK-TEMP` (`assigned_from_existing_work`).
- Public reconciliation: `~/Workspace/limen/docs/always-working.md`.
  - `SUBSTRATE-DISK-TEMP`: `substrate` / `assigned_from_existing_work`; substrate lifecycle predicate is failing.
  - `PUBLIC-FACE-CONTRIBUTION-BALANCE`: `contribution-balance` / `assigned_from_existing_work`; GitHub activity mix needs owner action: commits 70.5%, PRs 17.8%, issues 10.7%, reviews 0.9%.
  - `MAIL-ACTIVE-FLAGGED`: `mail-active` / `assigned_from_existing_work`; 236 active flagged non-deleted messages require classification.
  - `REPO-BOIL-UP`: `repo-boil-up` / `needs_assignment`; repo surface ledger missing; assignment must refresh existing roots before new work.
  - `VALUE-REPOS`: `revenue-value-repos` / `assigned_from_existing_work`; 19 value repos define the funded work lane.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main [behind 16]`.
- HEAD: `bf68718fdc05a22a561e558850f2cfc301ec3277`.
- origin/main: `8f1d5d8119b5f8d1a465cc34145d805ff1c2c258`.
- Matches origin/main: `False`; ahead `0` behind `16`.
- Dirty entries: `50`.
- Ignored generated receipt dirty entries: `1`.
  - `docs/dispatch-health.md`
  - `docs/RECLASSIFY-PROPOSAL.md`
  - `docs/always-working.md`
  - `docs/branch-hygiene.md`
  - `docs/capacity-fill.md`
  - `docs/diurnal/INDEX.md`
  - `docs/github-actions-usage.json`
  - `docs/github-pr-debt-ledger.json`
  - `docs/receipts/session-contention-ledger.json`
  - `docs/receipts/tcc-track-c-1703/closeout-latest.json`
  - `logs/overnight-watch.md`
  - `organs/contributions/MIRROR.md`
  - `organs/contributions/opportunities.json`
  - `organs/financial/STATUS.md`
  - `organs/financial/cashflow.md`
  - `docs/diurnal/2026-08-06.md`
  - `docs/diurnal/2026-08-07.md`
  - `docs/diurnal/2026-08-08.md`
  - `docs/receipts/tcc-track-c-1703/closeout-20260805T222100Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T022247Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T025632Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T065717Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T073041Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T113740Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T122116Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T162356Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T165721Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T210343Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260806T215728Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260807T000415Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260807T015152Z.json`
  - `<truncated>`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main [behind 16]`.
- HEAD matches origin/main: `False`.

## Blockers

- `heartbeat-watchdog-unhealthy`:   ok  not-wedged: {"reason": "no PARALLEL beats in window", "recent_pr_counts": [], "max_fails_threshold": 3}
- `live-root-not-at-origin-main`: live root branch main head bf68718fdc05 differs from origin/main 8f1d5d8119b5.
- `live-root-dirty`: live root has 50 dirty entries.
- `always-working-required-work-open`: 5 required promise workstream(s) remain open; next item SUBSTRATE-DISK-TEMP.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 10 --dry-run`
