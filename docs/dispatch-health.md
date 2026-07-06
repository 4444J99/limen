# Dispatch Health

Generated: `2026-07-06T10:30:21+00:00`

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
- Loaded launchd state: `running` pid `51335`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `1`.
- Loaded LIMEN_DISPATCH_LANES: `auto`.
- Loaded LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-07-06T10:30:21.560956+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 4 ; 0 still running ; would launch 12 (cap 12) -> ['HEAL-cifix-organvm-organvm-ontologia-13', 'HEAL-rebase-4444j99-hokage-chess-94', 'HEAL-rebase-4444j99-hokage-chess-108', 'GH-4444j99-hokage-chess-39', 'HEAL-cifix-organvm-organvm-engine-139', 'HEAL-cifix-organvm-organvm-engine-144', 'HEAL-cifix-organvm-organvm-ontologia-11', 'HEAL-rebase-4444j99-hokage-chess-89', 'HEAL-rebase-4444j99-hokage-chess-107', 'HEAL-rebase-organvm-peer-audited--behavioral-blockchain-721', 'ORG-financial-organ-face-0704', 'HEAL-rebase-4444j99-hokage-chess-114']`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `bacbcaaa24ff6846e506106e822c395a14c42cbd`.
- origin/main: `bacbcaaa24ff6846e506106e822c395a14c42cbd`.
- Matches origin/main: `True`; ahead `0` behind `0`.
- Dirty entries: `0`.
- Ignored generated receipt dirty entries: `1`.
  - `docs/live-root-gate.md`

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
