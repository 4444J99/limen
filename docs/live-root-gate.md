# Live Root Gate

Generated: `2026-09-30T20:48:29+00:00`

Status: `blocked`

## Rule

- This is an operator gate for the live Limen checkout and heartbeat LaunchAgent.
- It does not switch branches, reset, stash, commit, edit tasks.yaml, or reload launchd.
- Treat tasks.yaml as daemon-owned live state; preserve it before release convergence.

## Gate State

- Operator gate required: `True`.
- Release reconcile allowed without human: `False`.
- Launchd reload allowed without human: `False`.
- Blocking gates: `live-root-not-release-branch`, `live-root-not-at-release`, `live-root-dirty`.

## Live Root

- Path: `~/Workspace/limen`.
- Branch: `HEAD`; release branch `main`.
- HEAD: `d4ec45cb456fa63a5c594eb429537fac572ce320`.
- Release head: `04417f540cfa460450430661591ff1cf44d67fcf`.
- Matches release: `False`; ahead `0` behind `69`.
- Unique local commits: `0`; patch-equivalent commits: `0`.
- Dirty entries: `3`.
- Ignored generated receipt dirty entries: `1`.
  - `docs/live-root-gate.md`

### Dirty Paths

- `docs/branch-hygiene.md`
- `docs/jules-orphan-adoptions.jsonl`
- `docs/continuations/git-parity-20260930/`

## Heartbeat

- Plist: `~/Library/LaunchAgents/com.limen.heartbeat.plist` present `True`.
- Loaded launchd state: `not running` pid `None`.
- Loaded env matches plist for tracked LIMEN_* keys.

## Verified Worktree

- Path: `~/Workspace/limen`.
- Branch: `HEAD`.
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
