# Dispatch Health

Generated: `2026-07-07T19:33:34+00:00`

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
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-07-07T19:33:34.387728+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run lanes: `auto`; max `1`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 0 ; 1 still running ; would launch 0 (cap 1) -> []`.
- Async skipped down lanes: `claude, gemini, jules`.
  - `claude`: usage health `rate-limited`; signal `tokens`; remaining `100000000` of `100000000`; headroom `100%`.
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
- Required open workstreams: `6`.
- Blocked workstreams: `0`.
- Done from receipt: `2`.
- Next item: `PUBLIC-FACE-PROFILE` (`assigned_from_existing_work`).
- Public reconciliation: `~/Workspace/limen/docs/always-working.md`.
  - `PUBLIC-FACE-PROFILE`: `public-face` / `assigned_from_existing_work`; existing profile/frontdoor work is present but not projected.
  - `MAIL-ACTIVE-FLAGGED`: `mail-active` / `assigned_from_existing_work`; 127 active flagged non-deleted messages require classification.
  - `MAIL-HISTORICAL-BACKLOG`: `mail-historical` / `assigned_from_existing_work`; 82041 indexed non-deleted messages exist; process in batches, not one giant run.
  - `REPO-BOIL-UP`: `repo-boil-up` / `assigned_from_existing_work`; broad repo surface ledger exists, but it is stale for current boil-up work.
  - `VALUE-REPOS`: `revenue-value-repos` / `assigned_from_existing_work`; 14 value repos define the funded work lane.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `60f0b730213e346f7943d2a08bf2d312c1615a3c`.
- origin/main: `60f0b730213e346f7943d2a08bf2d312c1615a3c`.
- Matches origin/main: `True`; ahead `0` behind `0`.
- Dirty entries: `2`.
  - `docs/always-working.md`
  - `docs/prompt-packet-ledger.md`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- `live-root-dirty`: live root has 2 dirty entries.
- `always-working-required-work-open`: 6 required promise workstream(s) remain open; next item PUBLIC-FACE-PROFILE.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 1 --dry-run`
