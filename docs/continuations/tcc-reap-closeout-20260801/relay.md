# TCC automatic worktree reap — terminal relay

## Summary

The heartbeat now performs the canonical bounded exact-plan reclaim cycle, and the two TCC worktrees that motivated the repair have been safely detached. No operator action remains. This capsule exists only to re-verify or owner-route a future regression.

## What changed

- PR [#1749](https://github.com/organvm/limen/pull/1749) merged the shared reclaim-cycle controller and the heartbeat/drain integrations as commit `3ff446a1144d6f73109c49af28ad50d45f92a898`.
- The heartbeat explicitly discovers repo-local and registered worktrees and applies only the SHA returned by its bounded dry plan.
- The two TCC targets were detached through the accepted typed-abandonment path and recorded in the aggregate reclaim log.
- Issue [#1522 terminal receipt](https://github.com/organvm/limen/issues/1522#issuecomment-5154127442) is the remote owner for the closeout evidence.

## Attempts and decisions

- A broad reclaim dry run exposed unrelated eligible candidates, so it was not applied.
- The exact two requested TCC targets were reclaimed individually through the canonical acceptance and receipt machinery.
- The 24-hour idle guard and active-process guard remain unchanged.
- No force removal, LaunchAgent addition, plist edit, or plan-SHA bypass was used.

## Proofs

- `bash scripts/verify-tcc-reap-closeout.sh` checks the idempotent local fixed point: both paths absent, both Git registrations absent, both typed receipts terminal, and one exact aggregate apply receipt with no failures.
- Independent local and GitHub owner checks both returned high confidence with no missing evidence.
- Live `main` and `origin/main` were both `3ff446a1144d6f73109c49af28ad50d45f92a898` at closeout.

## Continuation command

Use the canonical kickstart command emitted by this capsule only if issue #1522 is reopened or the predicate fails:

```sh
bash /Users/4jp/Workspace/limen/.worktrees/tcc-reap-closeout-20260801/.limen-workstream/kickstart.sh
```

On a clean predicate, record the verification on issue #1522 and stop. On failure, diagnose read-only, file the exact failing predicate on that issue, and do not delete anything outside the accepted reclaim path.
