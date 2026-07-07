# Dispatch Health

Generated: `2026-07-07T00:43:50+00:00`

Status: `blocked`

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
- Loaded launchd state: `running` pid `79488`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `1`.
- Loaded LIMEN_DISPATCH_LANES: `auto`.
- Loaded LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-07-07T00:43:50.287985+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 2 ; 10 still running ; would launch 2 (cap 12) -> ['HEAL-rebase-organvm-universal-mail--automation-119', 'HEAL-cifix-organvm-the-invisible-ledger-47']`.

## Prompt Packet Gate

- Prompt packet index present: `True`.
- Prompt packet status: `clear`.
- Open prompt packets: `0`.
- Conductor-required packets: `0`.
- Ready-after-predicate packets: `0`.
- Recorded packets: `8`.
- Public packet ledger: `~/Workspace/limen/docs/prompt-packet-ledger.md`.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `72f4e4eab294cefc6ce249ba440f3673a7c1c500`.
- origin/main: `72f4e4eab294cefc6ce249ba440f3673a7c1c500`.
- Matches origin/main: `True`; ahead `0` behind `0`.
- Dirty entries: `7`.
- Ignored generated receipt dirty entries: `2`.
  - `docs/session-attack-paths.md`
  - `docs/session-lifecycle-blockers.md`
  - `docs/current-session-fanout.md`
  - `docs/prompt-batch-review-ledger.md`
  - `docs/prompt-lifecycle-ledger.md`
  - `docs/prompt-packet-ledger.md`
  - `docs/prompt-packet-resolution-receipts.json`
  - `docs/prompt-priority-map.md`
  - `tasks.yaml`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- `live-root-dirty`: live root has 7 dirty entries.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 12 --dry-run`
