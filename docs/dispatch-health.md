# Dispatch Health

Generated: `2026-07-10T01:49:52+00:00`

Status: `blocked`

## Incident Class

- Dispatch/heartbeat health is not proven by tests in a detached worktree alone.
- The live launchd daemon must run the same substrate that the conductor just verified, or the next lane can rediscover stale behavior.
- This receipt is read-only. It stops before launchd reloads, branch switches, resets, task-board writes, or live-root commits.

## Heartbeat

- Generated plist probe: `True` from `~/Workspace/limen/scripts/gen-launchd-plist.sh`.
- Generated LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Generated LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Generated LIMEN_DISPATCH_ASYNC: `1`.
- Generated LIMEN_ASYNC_MAX: `10`.
- LaunchAgent plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Plist KeepAlive: `True`; RunAtLoad: `True`.
- Plist LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Plist LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Plist LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Plist LIMEN_DISPATCH_ASYNC: `1`.
- Plist LIMEN_DISPATCH_LANES: `auto`.
- Plist LIMEN_ASYNC_MAX: `10`.
- Plist LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Loaded launchd state: `running` pid `75477`.
- Loaded LIMEN_ROOT: `/Users/4jp/Workspace/limen`.
- Loaded LIMEN_WORKTREES: `/Volumes/Scratch/limen-worktrees`.
- Loaded LIMEN_WORKTREE_ROOT: `/Volumes/Scratch/limen-worktrees`.
- Loaded LIMEN_DISPATCH_ASYNC: `1`.
- Loaded LIMEN_DISPATCH_LANES: `auto`.
- Loaded LIMEN_ASYNC_MAX: `10`.
- Loaded LIMEN_LANES: `codex,opencode,agy,claude,gemini`.
- Watchdog dry-run healthy: `True`; `[watchdog] 2026-07-10T01:49:52.425481+00:00 HEALTHY sig=healthy`.

## Async Dispatch

- Async dry-run requested: `True`.
- Async dry-run lanes: `auto`; max `10`.
- Async dry-run ok: `True`; timed out `False`.
- Async dry-run summary: `-- async: reaped 0 dead ; harvested 0 ; 0 still running ; would launch 13 (local cap 10, local per-lane 8) -> ['HEAL-cifix-organvm-peer-audited--behavioral-blockchain-771', 'GH-organvm-manumissio-5', 'HEAL-rebase-organvm-peer-audited--behavioral-blockchain-733', 'HEAL-cifix-organvm-limen-406', 'HEAL-cifix-organvm-limen-384', 'HEAL-rebase-organvm-domus-genoma-135', 'HEAL-rebase-stale-organvm-peer-audited--behavioral-blockchain-720', 'HEAL-rebase-organvm-session-meta-149', 'HEAL-cifix-organvm-limen-414', 'HEAL-cifix-organvm-limen-401', 'HEAL-rebase-organvm-domus-genoma-178', 'HEAL-rebase-stale-organvm-the-invisible-ledger-41', 'HEAL-cifix-organvm-limen-402']`.

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
- Required open workstreams: `2`.
- Blocked workstreams: `2`.
- Done from receipt: `7`.
- Next item: `PUBLIC-FACE-CONTRIBUTION-BALANCE` (`assigned_from_existing_work`).
- Public reconciliation: `~/Workspace/limen/docs/always-working.md`.
  - `PUBLIC-FACE-CONTRIBUTION-BALANCE`: `contribution-balance` / `assigned_from_existing_work`; GitHub activity mix needs owner action: commits 73.7%, PRs 13.7%, issues 11.7%, reviews 0.9%.
  - `MAIL-ACTIVE-FLAGGED`: `mail-active` / `assigned_from_existing_work`; 131 active flagged non-deleted messages require classification.

## Live Root

- Live root: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD: `636cee75368ea78e2e541e13c9bfdf2875f2784d`.
- origin/main: `636cee75368ea78e2e541e13c9bfdf2875f2784d`.
- Matches origin/main: `True`; ahead `0` behind `0`.
- Dirty entries: `0`.

## Verified Worktree

- Verified worktree: `~/Workspace/limen`.
- Branch: `main`; status `## main...origin/main`.
- HEAD matches origin/main: `True`.

## Blockers

- `always-working-required-work-open`: 2 required promise workstream(s) remain open; next item PUBLIC-FACE-CONTRIBUTION-BALANCE.

## Commands

- Refresh this receipt: `python3 scripts/dispatch-health.py --write --probe-async`
- Refresh the operator gate: `python3 scripts/live-root-gate.py --write`
- Refresh prompt packets: `python3 scripts/prompt-packet-ledger.py --write`
- Refresh always-working reconciliation: `python3 scripts/always-working.py --write`
- Verify async dispatch tests: `pytest -q cli/tests/test_async_dispatch.py`
- Probe heartbeat: `python3 scripts/watchdog.py --dry-run`
- Probe async dry-run: `PYTHONPATH=cli/src python3 scripts/dispatch-async.py --lanes auto --per-lane 3 --max 10 --dry-run`
