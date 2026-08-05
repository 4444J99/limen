# Authorities and constraints

- Follow the nearest `AGENTS.md`, typed task contracts, and owner receipts on GitHub.
- Treat GitHub as remote truth and local checkouts as disposable caches or preservation surfaces.
- Routine isolated code PRs, focused verification, and policy-cleared serial merges are authorized.
- Mass merges, force pushes, public messaging unrelated to an owner PR, paid overages, remote branch
  deletion, credential/account actions, and personal-data deletion remain gated.
- Keep code, board projection, lifecycle receipts, and analysis in separate commits/PRs.
- Never edit `tasks.yaml` directly; submit changes through TABVLARIVS.

## Inherited safety boundaries

- The user-led Claude session is a separate owner. Re-probe it by counts/process/remote receipts only.
  Do not inspect raw transcript bodies or active worktree diffs, and do not kill, answer, approve,
  rebase, push, merge, comment on, or rerun its work.
- External volumes were cleanly ejected. Treat `/Volumes/*` work as unavailable unless the expected
  mount is observed live; never infer that a drive has been reconnected.
- `com.limen.overnight-watch` was unloaded after ignoring the pause marker and consuming 87-95% CPU.
  Keep `logs/AUTONOMY_PAUSED` in force until the watcher pause guard is remotely landed and the
  installed LaunchAgent proves a fast, side-effect-free exit while paused.
- Preserve dirty, divergent, open-PR, locked, active, and non-Git roots. Only the accepted reaper may
  remove a root after exact remote custody and its configured lifecycle predicate pass.
