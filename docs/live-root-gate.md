# Live Root Gate

Generated: `2026-06-28T20:07:01+00:00`

Status: `blocked`

## Rule

- This is an operator gate for the live Limen checkout and heartbeat LaunchAgent.
- It does not switch branches, reset, stash, commit, edit tasks.yaml, or reload launchd.
- Treat tasks.yaml as daemon-owned live state; preserve it before release convergence.

## Gate State

- Operator gate required: `True`.
- Release reconcile allowed without human: `False`.
- Launchd reload allowed without human: `False`.
- Blocking gates: `live-root-not-release-branch`, `live-root-not-at-release`, `live-root-unique-commits`, `live-root-dirty`, `live-root-task-board-dirty`, `heartbeat-loaded-env-drift`.

## Live Root

- Path: `~/Workspace/limen`.
- Branch: `feature/ORG-artist-organ-face-0628`; release branch `main`.
- HEAD: `84a3288eaaf91de93428aa8eae9dafbead39ba42`.
- Release head: `219f210ffed2878130e8f95d63c840ed0cc74e0b`.
- Matches release: `False`; ahead `1` behind `9`.
- Unique local commits: `1`; patch-equivalent commits: `0`.
- Dirty entries: `5`.

### Local Commits

- `84a3288 feat(artist): author KERNEL and CHARTER for A-MAVS-OLEVM`

### Dirty Paths

- `container/launchd/com.user.netmeter.plist`
- `scripts/netmode.sh`
- `tasks.yaml`
- `organs/health/`
- `organs/media/`

## Heartbeat

- Plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Loaded launchd state: `running` pid `24368`.

### Loaded Env Drift

- `LIMEN_DISPATCH_ASYNC`: plist `0`; loaded `None`.

## Verified Worktree

- Path: `~/Workspace/limen-conductor-owner-state-20260628`.
- Branch: `codex/conductor-owner-state-20260628`.
- Matches release: `True`.

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
