# Dispatch Health

Generated: `2026-07-03T11:33:39+00:00`

Status: `healthy`

## Incident Class

- Dispatch/heartbeat health is not proven by tests in a detached worktree alone.
- The live launchd daemon must run the same substrate that the conductor just verified, or the next lane can rediscover stale behavior.
- This receipt is read-only. It stops before launchd reloads, branch switches, resets, task-board writes, or live-root commits.

## Heartbeat

- LaunchAgent plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Plist KeepAlive: `True`; RunAtLoad: `True`.
- Plist LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Plist LIMEN_DISPATCH_ASYNC: `1`.
- Plist LIMEN_DISPATCH_LANES: `opencode,agy`.
- Plist LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Loaded launchd state: `running` pid `4306`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `1`.
- Loaded LIMEN_DISPATCH_LANES: `opencode,agy`.
- Loaded LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-07-03T11:33:40.072797+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 0 ; 1 still running ; would launch 10 (cap 12) -> ['REV-organvm-mirror-mirror-revenue-ship-0703', 'ORG-health-organ-firstslice-0703', 'ORG-social-organ-firstslice-0703', 'GEN-organvm-mirror-mirror-simplify-0630', 'ORG-financial-organ-deepen-0703', 'ORG-governance-organ-selffeed-0703', 'ORG-financial-organ-face-0703', 'DISCOVER-organvm-the-actual-news', 'DISCOVER-organvm-sovereign-systems--layer-above-hokage', 'GEN-organvm-domus-genoma-test-coverage-0702']`.
- Async skipped down lanes: `gemini, jules`.
  - `gemini`: usage health `exhausted`; signal `dispatch-count`; remaining `0` of `10`; headroom `0%`.
  - `jules`: usage health `exhausted`; signal `count`; remaining `0` of `100`; headroom `0%`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `1e8b6c4be3b4bbcbf711cefc512ef5aea4efaf97`.
- origin/main: `1e8b6c4be3b4bbcbf711cefc512ef5aea4efaf97`.
- Matches origin/main: `True`; ahead `0` behind `0`.
- Dirty entries: `0`.

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- none

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 12 --dry-run`
