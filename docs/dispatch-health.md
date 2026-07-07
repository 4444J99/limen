# Dispatch Health

Generated: `2026-07-07T19:54:34+00:00`

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
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-07-07T19:54:34.872501+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run lanes: `auto`; max `1`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 0 ; 1 still running ; would launch 0 (cap 1) -> []`.
- Async skipped down lanes: `codex, gemini, jules`.
  - `codex`: usage health `throttle`; signal `tokens`; remaining `0` of `100000000`; headroom `0%`.
  - `gemini`: usage health `exhausted`; signal `dispatch-count`; remaining `0` of `10`; headroom `0%`.
  - `jules`: usage health `low`; signal `dispatch-count`; remaining `8` of `100`; headroom `8%`.

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
- Required open workstreams: `5`.
- Blocked workstreams: `0`.
- Done from receipt: `3`.
- Next item: `MAIL-ACTIVE-FLAGGED` (`assigned_from_existing_work`).
- Public reconciliation: `~/Workspace/limen/docs/always-working.md`.
  - `MAIL-ACTIVE-FLAGGED`: `mail-active` / `assigned_from_existing_work`; 127 active flagged non-deleted messages require classification.
  - `MAIL-HISTORICAL-BACKLOG`: `mail-historical` / `assigned_from_existing_work`; 82042 indexed non-deleted messages exist; process in batches, not one giant run.
  - `REPO-BOIL-UP`: `repo-boil-up` / `assigned_from_existing_work`; broad repo surface ledger exists, but it is stale for current boil-up work.
  - `VALUE-REPOS`: `revenue-value-repos` / `assigned_from_existing_work`; 14 value repos define the funded work lane.
  - `TABVLARIVS-STATUS-WRITERS`: `tabularius` / `assigned_from_existing_work`; Step 2.2 still open in the keeper doc.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `b894c8ab2ee3920247c433e33f9ec9468f9ce90c`.
- origin/main: `b894c8ab2ee3920247c433e33f9ec9468f9ce90c`.
- Matches origin/main: `True`; ahead `0` behind `0`.
- Dirty entries: `4`.
- Ignored generated receipt dirty entries: `1`.
  - `docs/dispatch-health.md`
  - `cli/tests/test_always_working.py`
  - `cli/tests/test_session_lifecycle_pressure.py`
  - `docs/always-working.md`
  - `scripts/always-working.py`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- `live-root-dirty`: live root has 4 dirty entries.
- `always-working-required-work-open`: 5 required promise workstream(s) remain open; next item MAIL-ACTIVE-FLAGGED.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 1 --dry-run`
