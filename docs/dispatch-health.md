# Dispatch Health

Generated: `2026-07-08T06:33:21+00:00`

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
- Plist LIMEN_ASYNC_MAX: `1`.
- Plist LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Loaded launchd state: `running` pid `30310`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `1`.
- Loaded LIMEN_DISPATCH_LANES: `auto`.
- Loaded LIMEN_ASYNC_MAX: `1`.
- Loaded LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-07-08T06:33:21.399386+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run lanes: `auto`; max `1`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 0 ; 0 still running ; would launch 1 (cap 1) -> ['HEAL-cifix-organvm-domus-genoma-172']`.

## Prompt Packet Gate

- Prompt packet index present: `True`.
- Prompt packet status: `clear`.
- Open prompt packets: `0`.
- Conductor-required packets: `0`.
- Ready-after-predicate packets: `0`.
- Recorded packets: `8`.
- Public packet ledger: `~/Workspace/limen/docs/prompt-packet-ledger.md`.

## Always-Working Gate

- Reconciliation index present: `True`.
- Reconciliation status: `needs-work`.
- Required open workstreams: `3`.
- Blocked workstreams: `1`.
- Done from receipt: `7`.
- Next item: `SUBSTRATE-DISK-TEMP` (`assigned_from_existing_work`).
- Public reconciliation: `~/Workspace/limen/docs/always-working.md`.
  - `SUBSTRATE-DISK-TEMP`: `substrate` / `assigned_from_existing_work`; disk/temp pressure needs owner work.
  - `ESTATE-CUSTODY`: `estate-custody` / `assigned_from_existing_work`; estate doctrine exists; implementation receipt is not complete.
  - `PUBLIC-FACE-CONTRIBUTION-BALANCE`: `contribution-balance` / `assigned_from_existing_work`; GitHub activity mix needs owner action: commits 74.0%, PRs 13.2%, issues 12.0%, reviews 0.8%.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `4de2ec9681dbc96f840f51ccfd6227e21623a2b4`.
- origin/main: `4de2ec9681dbc96f840f51ccfd6227e21623a2b4`.
- Matches origin/main: `True`; ahead `0` behind `0`.
- Dirty entries: `0`.
- Ignored generated receipt dirty entries: `1`.
  - `docs/dispatch-health.md`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- `always-working-required-work-open`: 3 required promise workstream(s) remain open; next item SUBSTRATE-DISK-TEMP.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 1 --dry-run`
