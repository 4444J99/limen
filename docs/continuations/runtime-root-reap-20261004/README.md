# Runtime-root reap — 2026-10-04

Operator-assigned reap of three disposable local runtime roots under the Limen checkout:

- `/Users/4jp/Workspace/limen/.agent-runtime/codex/worktrees`
- `/Users/4jp/Workspace/limen/.worktrees`
- `/Users/4jp/Workspace/limen/.claude/worktrees`

Authorization is the operator's direct-session instruction of 2026-10-04, bound verbatim in
[`reclaim-scope.json`](reclaim-scope.json) as a `limen.worktree_reclaim_scope.v1` packet.

Execution rail: `scripts/reclaim-worktrees.py --target … --scope-manifest …`, so every removal is
driven by a committed, remotely published, operator-scoped manifest rather than by ad hoc deletion.
Each removal additionally requires the tool's own gates — clean tree, live-remote reachability of
HEAD, all-local-ref remote proof for standalone clones, ignored-payload custody or regeneration
proof, no active process cwd, and no protected-exclusion match.

Per-directory receipts, live remote parity evidence, retention blockers and measured disk deltas are
in [`receipt.json`](receipt.json) and [`README.md`](README.md).

Children are processed before their shared store: `c06-portfolio` is a linked worktree whose Git
common directory lives inside `.agent-runtime/codex/worktrees/580e/portfolio/.git`, so it is reaped
before `580e`.
