# Campaign Heartbeat Health

Generated: `2026-08-10T21:04:04+00:00`

Status: `blocked`

## Incident Class

- Campaign-heartbeat health is not proven by tests in a detached worktree alone.
- The live launchd daemon must run the same substrate that the conductor just verified, or the next lane can rediscover stale behavior.
- This receipt is read-only. It stops before launchd reloads, branch switches, resets, task-board writes, or live-root commits.

## Heartbeat

- Generated plist probe: `True` from `~/Workspace/limen/scripts/gen-launchd-plist.sh`.
- Generated LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Generated LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Generated LIMEN_CAMPAIGN_WAKE_TIMEOUT: `300`.
- LaunchAgent plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Plist KeepAlive: `True`; RunAtLoad: `True`.
- Plist LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Plist LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Plist LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Plist LIMEN_CAMPAIGN_WAKE_TIMEOUT: `300`.
- Loaded launchd state: `running` pid `84914`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Loaded LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Loaded LIMEN_CAMPAIGN_WAKE_TIMEOUT: `300`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-08-10T21:04:04.983709+00:00 HEALTHY sig=healthy`.

## Legacy Manual Async Diagnostic

- This optional diagnostic is retained for manual-engine compatibility and does not define campaign-heartbeat health.
- Async dry-run requested: `False`.
- Async dry-run lanes: ``; max ``.
- Async dry-run ok: `None`; timed out `False`.
- Async dry-run summary: ``.

## Prompt Packet Gate

- Prompt packet index present: `True`.
- Prompt packet status: `clear`.
- Open prompt packets: `0`.
- Conductor-required packets: `0`.
- Ready-after-predicate packets: `0`.
- Recorded packets: `0`.
- Public packet ledger: `~/Workspace/limen/docs/prompt-packet-ledger.md`.

## Always-Working Gate

- Reconciliation index present: `True`.
- Reconciliation status: `needs-work`.
- Required open workstreams: `5`.
- Blocked workstreams: `2`.
- Done from receipt: `4`.
- Next item: `SUBSTRATE-DISK-TEMP` (`assigned_from_existing_work`).
- Public reconciliation: `~/Workspace/limen/docs/always-working.md`.
  - `SUBSTRATE-DISK-TEMP`: `substrate` / `assigned_from_existing_work`; substrate lifecycle predicate is failing.
  - `PUBLIC-FACE-CONTRIBUTION-BALANCE`: `contribution-balance` / `assigned_from_existing_work`; GitHub activity mix needs owner action: commits 69.9%, PRs 17.9%, issues 11.2%, reviews 1.0%.
  - `MAIL-ACTIVE-FLAGGED`: `mail-active` / `assigned_from_existing_work`; 242 active flagged non-deleted messages require classification.
  - `REPO-BOIL-UP`: `repo-boil-up` / `needs_assignment`; repo surface ledger missing; assignment must refresh existing roots before new work.
  - `VALUE-REPOS`: `revenue-value-repos` / `assigned_from_existing_work`; 19 value repos define the funded work lane.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main [behind 9]`.
- HEAD: `c32f846006d517dd01738ea02107f7233ed849bd`.
- origin/main: `7c269d54e51024c37099ce2f4bcd248fdcfa58bf`.
- Matches origin/main: `False`; ahead `0` behind `9`.
- Dirty entries: `19`.
- Ignored generated receipt dirty entries: `1`.
  - `docs/dispatch-health.md`
  - `docs/RECLASSIFY-PROPOSAL.md`
  - `docs/always-working.md`
  - `docs/branch-hygiene.md`
  - `docs/capacity-fill.md`
  - `docs/diurnal/INDEX.md`
  - `docs/github-actions-usage.json`
  - `docs/receipts/session-contention-ledger.json`
  - `docs/receipts/tcc-track-c-1703/closeout-latest.json`
  - `logs/overnight-watch.md`
  - `organs/contributions/MIRROR.md`
  - `organs/contributions/opportunities.json`
  - `organs/financial/cashflow.md`
  - `docs/diurnal/2026-08-10.md`
  - `docs/receipts/tcc-track-c-1703/closeout-20260810T133238Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260810T155418Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260810T172244Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260810T190416Z.json`
  - `docs/receipts/tcc-track-c-1703/closeout-20260810T205244Z.json`
  - `studium/ledger/studium-2026-08-10.md`

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main [behind 9]`.
- HEAD matches origin/main: `False`.

## Blockers

- `live-root-not-at-origin-main`: live root branch main head c32f846006d5 differs from origin/main 7c269d54e510.
- `live-root-dirty`: live root has 19 dirty entries.
- `always-working-required-work-open`: 5 required promise workstream(s) remain open; next item SUBSTRATE-DISK-TEMP.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 10 --dry-run`
