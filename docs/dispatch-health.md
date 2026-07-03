# Dispatch Health

Generated: `2026-07-03T07:07:44+00:00`

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
- Plist LIMEN_DISPATCH_LANES: `auto`.
- Plist LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Loaded launchd state: `running` pid `59103`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `1`.
- Loaded LIMEN_DISPATCH_LANES: `auto`.
- Loaded LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-07-03T07:07:44.941416+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 3 ; 0 still running ; would launch 5 (cap 12) -> ['GEN-organvm-session-meta-simplify-0703', 'GEN-meta-organvm-visual-substrate-inquiry-test-coverage-0620', 'GEN-organvm-i-theoria-organvm-vi-koinonia.github.io-test-coverage-0620', 'GEN-organvm-i-theoria-organvm-vii-kerygma.github.io-test-coverage-0620', 'GEN-organvm-i-theoria-meta-organvm.github.io-test-coverage-0620']`.
- Async skipped down lanes: `gemini, jules`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `e9fbace0cfd355d526e8c2fd25d75e67eab6a8b7`.
- origin/main: `e9fbace0cfd355d526e8c2fd25d75e67eab6a8b7`.
- Matches origin/main: `True`; ahead `0` behind `0`.
- Dirty entries: `0`.
- Ignored generated receipt dirty entries: `1`.
  - `docs/dispatch-health.md`

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
