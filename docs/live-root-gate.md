# Live Root Gate

Generated: `2026-07-08T01:43:15+00:00`

Status: `blocked`

## Rule

- This is an operator gate for the live Limen checkout and heartbeat LaunchAgent.
- It does not switch branches, reset, stash, commit, edit tasks.yaml, or reload launchd.
- Treat tasks.yaml as daemon-owned live state; preserve it before release convergence.

## Gate State

- Operator gate required: `True`.
- Release reconcile allowed without human: `False`.
- Launchd reload allowed without human: `False`.
- Blocking gates: `live-root-not-at-release`, `live-root-unique-commits`, `live-root-dirty`, `live-root-task-board-dirty`.

## Live Root

- Path: `~/Workspace/limen`.
- Branch: `main`; release branch `main`.
- HEAD: `937814b19452dc5e93e0b6dc35524d6880b19a1d`.
- Release head: `e30bbf34b41b809ee6a2344d350be1c01d34e357`.
- Matches release: `False`; ahead `1` behind `0`.
- Unique local commits: `1`; patch-equivalent commits: `0`.
- Dirty entries: `6`.

### Local Commits

- `937814b1 limen: preserve async board state`

### Dirty Paths

- `cli/src/limen/worktree_debt.py`
- `cli/tests/test_worktree_debt.py`
- `docs/branch-reap-acceptance.jsonl`
- `docs/consolidation/GATES.md`
- `docs/worktree-preservation-receipts.json`
- `tasks.yaml`

## Heartbeat

- Plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Loaded launchd state: `running` pid `30310`.
- Loaded env matches plist for tracked LIMEN_* keys.

## Verified Worktree

- Path: `~/Workspace/limen`.
- Branch: `main`.
- Matches release: `False`.

## Stop Conditions

- Stop before `git reset`, branch switch, stash drop, task-board write, launchd bootout/bootstrap/kickstart, or async enablement.
- Stop if `git cherry origin/main HEAD` reports any `+` commits until the operator decides whether to preserve, cherry-pick, or abandon them.
- Stop if `tasks.yaml` is dirty until the daemon-owned queue has been explicitly preserved.
- Stop if heartbeat has live child work; reload only between beats.

## Human-Gated Command Packet

Run these only after operator approval, in order, stopping on any mismatch:

```bash
LIVE_ROOT='/Users/4jp/Workspace/limen'
HEARTBEAT_LABEL='com.limen.heartbeat'
git -C "$LIVE_ROOT" status --branch --short
git -C "$LIVE_ROOT" cherry origin/main HEAD
git -C "$LIVE_ROOT" diff --name-status
git -C "$LIVE_ROOT" ls-files --others --exclude-standard
python3 scripts/dispatch-health.py --write --probe-async
python3 scripts/live-root-gate.py --write
# After preserving or intentionally discarding live-root-only state:
# launchctl kickstart -k "gui/$(id -u)/$HEARTBEAT_LABEL"
# Then require dispatch-health status healthy before enabling async.
```

## Refresh Commands

- Refresh this gate: `python3 scripts/live-root-gate.py --write`
- Refresh with remote tracking update: `python3 scripts/live-root-gate.py --write --fetch`
- Refresh dispatch health: `python3 scripts/dispatch-health.py --write --probe-async`
- Verify watchdog: `python3 scripts/watchdog.py --dry-run`
