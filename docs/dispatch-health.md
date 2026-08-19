# Campaign Heartbeat Health

Generated: `2026-08-18T20:06:13+00:00`

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
- Loaded launchd state: `running` pid `1278`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Loaded LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Loaded LIMEN_CAMPAIGN_WAKE_TIMEOUT: `300`.
- Watchdog dry-run healthy: `False`; `[watchdog] 2026-08-18T20:06:13.945475+00:00 UNHEALTHY sig=beating`.

## Legacy Manual Async Diagnostic

- This optional diagnostic is retained for manual-engine compatibility and does not define campaign-heartbeat health.
- Async dry-run requested: `False`.
- Async dry-run lanes: ``; max ``.
- Async dry-run ok: `None`; timed out `False`.
- Async dry-run summary: ``.

## Prompt Packet Gate

- Prompt packet index present: `False`.
- Prompt packet status: `missing`.
- Open prompt packets: `0`.
- Conductor-required packets: `0`.
- Ready-after-predicate packets: `0`.
- Recorded packets: `0`.
- Public packet ledger: `~/Workspace/limen/docs/prompt-packet-ledger.md`.

## Always-Working Gate

- Reconciliation index present: `False`.
- Reconciliation status: `missing`.
- Required open workstreams: `0`.
- Blocked workstreams: `0`.
- Done from receipt: `0`.
- Next item: `` (``).
- Public reconciliation: `~/Workspace/limen/docs/always-working.md`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `docs/custody-preservation-receipts-20260817`; status `## docs/custody-preservation-receipts-20260817...origin/docs/custody-preservation-receipts-20260817`.
- HEAD: `f2aba88470eba938d5a6a572afcb6a2d7ae17bb1`.
- origin/main: `751f44ab7f39cc62dba16733cfa21c3f0feaae37`.
- Matches origin/main: `False`; ahead `7` behind `14`.
- Dirty entries: `11`.
- Ignored generated receipt dirty entries: `2`.
  - `docs/receipts/tcc-track-c-1703/closeout-latest.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260818T152738Z.json`
  - `docs/RECLASSIFY-PROPOSAL.md`
  - `docs/branch-hygiene.md`
  - `docs/diurnal/INDEX.md`
  - `docs/github-pr-debt-ledger.json`
  - `docs/prompt-atom-ledger.md`
  - `docs/prompt-authority-seal.json`
  - `docs/receipts/session-contention-ledger.json`
  - `dump.rdb`
  - `logs/overnight-watch.md`
  - `organs/financial/cashflow.md`
  - `docs/diurnal/2026-08-18.md`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `docs/custody-preservation-receipts-20260817`; status `## docs/custody-preservation-receipts-20260817...origin/docs/custody-preservation-receipts-20260817`.
- HEAD matches origin/main: `False`.

## Blockers

- `heartbeat-watchdog-unhealthy`:   ok  not-wedged: {"reason": "no PARALLEL beats in window", "recent_pr_counts": [], "max_fails_threshold": 3}
- `live-root-not-at-origin-main`: live root branch docs/custody-preservation-receipts-20260817 head f2aba88470eb differs from origin/main 751f44ab7f39.
- `live-root-dirty`: live root has 11 dirty entries.
- `always-working-reconciliation-missing`: No current always-working reconciliation receipt is available.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 10 --dry-run`
