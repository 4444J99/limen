# Dispatch Health

Generated: `2026-06-30T14:46:35+00:00`

Status: `blocked`

## Incident Class

- Dispatch/heartbeat health is not proven by tests in a detached worktree alone.
- The live launchd daemon must run the same substrate that the conductor just verified, or the next lane can rediscover stale behavior.
- This receipt is read-only. It stops before launchd reloads, branch switches, resets, task-board writes, or live-root commits.

## Heartbeat

- LaunchAgent plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Plist KeepAlive: `True`; RunAtLoad: `True`.
- Plist LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Plist LIMEN_DISPATCH_ASYNC: `0`.
- Loaded launchd state: `running` pid `92588`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `0`.
- Watchdog dry-run healthy: `False`; `[watchdog] 2026-06-30T14:46:35.452106+00:00 UNHEALTHY sig=daemon-up`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `False`; timed out `False`.
- Async dry-run summary: `PermissionError: [Errno 1] Operation not permitted: '/Users/4jp/Workspace/limen/logs/.queue.lock.d'`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `work/workstream-agent-launcher-20260629`; status `## work/workstream-agent-launcher-20260629...origin/work/workstream-agent-launcher-20260629 [ahead 1]`.
- HEAD: `a66424e0edd80e3df3235188570328fa98af6698`.
- origin/main: `db526e33a3715bf04e5f1e3dbb71ed9d49ef20fb`.
- Matches origin/main: `False`; ahead `28` behind `18`.
- Dirty entries: `29`.
  - `cli/src/limen/capacity.py`
  - `cli/src/limen/dispatch.py`
  - `cli/src/limen/io.py`
  - `cli/tests/test_async_dispatch.py`
  - `cli/tests/test_dispatch.py`
  - `cli/tests/test_dispatch_engine.py`
  - `cli/tests/test_substrate_repo_product_fanout.py`
  - `docs/capacity-fill.md`
  - `docs/current-session-fanout.md`
  - `docs/dispatch-health.md`
  - `institutio/governance/parameters.yaml`
  - `scripts/current-session-fanout.py`
  - `scripts/dispatch-async.py`
  - `scripts/heal-dispatch.py`
  - `scripts/heartbeat-loop.sh`
  - `scripts/product-ledger.py`
  - `scripts/repo-surface-ledger.py`
  - `scripts/verify-dispatch.py`
  - `tasks.yaml`
  - `agy_log.txt`
  - `agy_log_big.txt`
  - `docs/lane-checkups/agy/20260630-02.md`
  - `docs/lane-checkups/claude/20260630-01.md`
  - `docs/lane-checkups/claude/20260630-06.md`
  - `docs/lane-checkups/gemini/20260630-02.md`
  - `docs/lane-checkups/gemini/20260630-03.md`
  - `docs/lane-checkups/oz/`
  - `docs/lane-checkups/warp/`
  - `scripts/salvage-yard-map.py`

## Verified Worktree

- Verified worktree: `~/Workspace/.limen-worktrees/capfill-codex-20260630-07-c131`.
- Branch: `limen/capfill-codex-20260630-07-c131`; status `## limen/capfill-codex-20260630-07-c131...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- `heartbeat-watchdog-unhealthy`:   ok  not-wedged: {"recent_pr_counts": [3, 0, 1], "max_fails_threshold": 3, "consecutive_zero": false}
- `live-root-not-at-origin-main`: live root branch work/workstream-agent-launcher-20260629 head a66424e0edd8 differs from origin/main db526e33a371.
- `live-root-dirty`: live root has 29 dirty entries.
- `async-dry-run-unhealthy`: PermissionError: [Errno 1] Operation not permitted: '/Users/4jp/Workspace/limen/logs/.queue.lock.d'

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
