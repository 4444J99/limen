# Dispatch Health

Generated: `2026-06-28T19:51:53+00:00`

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
- Loaded launchd state: `running` pid `24368`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `None`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-06-28T19:51:53.225450+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ? harvested 0 ? 0 still running ? would launch 0 (cap 12) -> []`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `feature/ORG-artist-organ-face-0628`; status `## feature/ORG-artist-organ-face-0628...origin/feature/ORG-artist-organ-face-0628`.
- HEAD: `84a3288eaaf91de93428aa8eae9dafbead39ba42`.
- origin/main: `1f4c1b72bf3bb610b9714f98cdf8f037be601c2f`.
- Matches origin/main: `False`; ahead `1` behind `7`.
- Dirty entries: `5`.
  - `container/launchd/com.user.netmeter.plist`
  - `scripts/netmode.sh`
  - `tasks.yaml`
  - `organs/health/`
  - `organs/media/`

## Verified Worktree

- Verified worktree: `~/Workspace/limen-conductor-owner-state-20260628`.
- Branch: `codex/conductor-owner-state-20260628`; status `## codex/conductor-owner-state-20260628...origin/codex/conductor-owner-state-20260628`.
- HEAD matches origin/main: `True`.

## Blockers

- `live-root-not-at-origin-main`: live root branch feature/ORG-artist-organ-face-0628 head 84a3288eaaf9 differs from origin/main 1f4c1b72bf3b.
- `live-root-dirty`: live root has 5 dirty entries.
- `heartbeat-loaded-env-drift`: plist LIMEN_DISPATCH_ASYNC='0', loaded=None.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes codex,opencode,agy,claude,gemini,jules --per-lane 3 --max 12 --dry-run`
