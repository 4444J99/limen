# Dispatch Health

Generated: `2026-07-07T14:05:52+00:00`

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
- Plist LIMEN_DISPATCH_LANES: `jules,opencode`.
- Plist LIMEN_ASYNC_MAX: `4`.
- Plist LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Loaded launchd state: `running` pid `48894`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_DISPATCH_ASYNC: `1`.
- Loaded LIMEN_DISPATCH_LANES: `jules,opencode`.
- Loaded LIMEN_ASYNC_MAX: `4`.
- Loaded LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-07-07T14:05:53.096549+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run lanes: `jules,opencode`; max `4`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 3 ; 3 still running ; would launch 3 (cap 4) -> ['HEAL-cifix-organvm-limen-407', 'HEAL-cifix-organvm-limen-414', 'HEAL-cifix-organvm-limen-418']`.
- Async skipped down lanes: `gemini`.
  - `gemini`: usage health `exhausted`; signal `dispatch-count`; remaining `0` of `10`; headroom `0%`.

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
- Required open workstreams: `7`.
- Blocked workstreams: `0`.
- Done from receipt: `1`.
- Next item: `SUBSTRATE-DISK-TEMP` (`assigned_from_existing_work`).
- Public reconciliation: `~/Workspace/limen/docs/always-working.md`.
  - `SUBSTRATE-DISK-TEMP`: `substrate` / `assigned_from_existing_work`; disk/temp pressure needs owner work.
  - `PUBLIC-FACE-PROFILE`: `public-face` / `assigned_from_existing_work`; existing profile/frontdoor work is present but not projected.
  - `MAIL-ACTIVE-FLAGGED`: `mail-active` / `assigned_from_existing_work`; 128 active flagged non-deleted messages require classification.
  - `MAIL-HISTORICAL-BACKLOG`: `mail-historical` / `assigned_from_existing_work`; 81982 indexed non-deleted messages exist; process in batches, not one giant run.
  - `REPO-BOIL-UP`: `repo-boil-up` / `assigned_from_existing_work`; broad repo surface ledger exists, but it is stale for current boil-up work.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `d9a3c089951ab4ec435bce400cc08bcef6a9b509`.
- origin/main: `d9a3c089951ab4ec435bce400cc08bcef6a9b509`.
- Matches origin/main: `True`; ahead `0` behind `0`.
- Dirty entries: `1`.
- Ignored generated receipt dirty entries: `1`.
  - `docs/dispatch-health.md`
  - `tasks.yaml`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- `live-root-dirty`: live root has 1 dirty entries.
- `always-working-required-work-open`: 7 required promise workstream(s) remain open; next item SUBSTRATE-DISK-TEMP.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes jules,opencode --per-lane 3 --max 4 --dry-run`
