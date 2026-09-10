# Campaign Heartbeat Health

Generated: `2026-09-10T23:39:29+00:00`

Status: `blocked`

## Incident Class

- Campaign-heartbeat health is not proven by tests in a detached worktree alone.
- The live launchd daemon must run the same substrate that the conductor just verified, or the next lane can rediscover stale behavior.
- This receipt is read-only. It stops before launchd reloads, branch switches, resets, task-board writes, or live-root commits.

## Heartbeat

- Generated plist probe: `False` from `~/Workspace/organvm/copilot-worktrees/limen/4444j99-probable-invention/scripts/gen-launchd-plist.sh`.
- Generated LIMEN_WORKTREES: `None`.
- Generated LIMEN_WORKTREE_ROOT: `None`.
- Generated LIMEN_CAMPAIGN_WAKE_TIMEOUT: `None`.
- LaunchAgent plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `False`.
- Plist KeepAlive: `None`; RunAtLoad: `None`.
- Plist LIMEN_ROOT: `None`.
- Plist LIMEN_WORKTREES: `None`.
- Plist LIMEN_WORKTREE_ROOT: `None`.
- Plist LIMEN_CAMPAIGN_WAKE_TIMEOUT: `None`.
- Loaded launchd state: `missing` pid `None`.
- Loaded LIMEN_ROOT: `None`.
- Loaded LIMEN_WORKTREES: `None`.
- Loaded LIMEN_WORKTREE_ROOT: `None`.
- Loaded LIMEN_CAMPAIGN_WAKE_TIMEOUT: `None`.
- Watchdog plist present: `False`.
- Watchdog launchd state: `missing` pid `None`.
- Watchdog dry-run healthy: `False`; `[watchdog] 2026-09-10T23:39:30.868490+00:00 UNHEALTHY sig=beating+daemon-up`.

## Legacy Manual Async Diagnostic

- This optional diagnostic is retained for manual-engine compatibility and does not define campaign-heartbeat health.
- Async dry-run requested: `False`.
- Async dry-run lanes: ``; max ``.
- Async dry-run ok: `None`; timed out `False`.
- Async dry-run summary: ``.

## Prompt Packet Gate

- Prompt packet index present: `True`.
- Prompt packet status: `unavailable`.
- Open prompt packets: `0`.
- Conductor-required packets: `0`.
- Ready-after-predicate packets: `0`.
- Recorded packets: `0`.
- Public packet ledger: `docs/prompt-packet-ledger.md`.

## Always-Working Gate

- Reconciliation index present: `False`.
- Reconciliation status: `missing`.
- Required open workstreams: `0`.
- Blocked workstreams: `0`.
- Done from receipt: `0`.
- Next item: `` (``).
- Public reconciliation: `docs/always-working.md`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `74505dddaad6892fd101dee0928bda44166b3d21`.
- origin/main: `74505dddaad6892fd101dee0928bda44166b3d21` (cached at receipt generation).
- Matches origin/main: `True`; ahead `0` behind `0` in the cached observation only.
- Dirty entries: `0`.

## Verified Worktree

- Verified worktree: current producer worktree (ephemeral; not a durable receipt path).
- Branch: `4444j99-verify-heal-mcp-wave0`; status `## 4444j99-verify-heal-mcp-wave0`.
- HEAD matches origin/main: `False`.

## Blockers

- `heartbeat-plist-missing`: LaunchAgent plist was not found.
- `heartbeat-launchd-not-running`: launchd state is missing.
- `heartbeat-watchdog-unhealthy`:   ok  not-wedged: {"reason": "no PARALLEL beats in window", "recent_pr_counts": [], "max_fails_threshold": 3}
- `always-working-reconciliation-missing`: No current always-working reconciliation receipt is available.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 10 --dry-run`
