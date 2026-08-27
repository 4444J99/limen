# Closeout reconciliation: discovered ref and worktree debt

Observed 2026-08-23 from the read-only closeout census. These rows are part of
the recovery denominator; none authorizes a reset, stash, deletion, or remote
effect.

| Item | Durable owner | Terminal predicate | Next command |
| --- | --- | --- | --- |
| `organvm/limen:recovery/agy-project-md-20260823@c84d1ad0033d6a28befe7976ee47d2cf9ab3a69c` | `organvm/limen:universe-recovery-20260823` | Exact landing, equivalent landing, recovery PR, or an explicit source-exhaustion blocker is recorded. | `git -C /Users/4jp/Workspace/limen branch -r --contains c84d1ad0033d6a28befe7976ee47d2cf9ab3a69c` |
| `/Users/4jp/Workspace/.limen-worktrees/m1_repos` | `organvm/limen:universe-recovery-20260823` | The path is identified as a valid registered checkout with its own receipt, or a safe filesystem-owner blocker is recorded; do not remove a non-Git path by inference. | `python3 scripts/worktree-debt.py --json --strict` |
| `/Users/4jp/Workspace/4444J99/application-pipeline/.worktrees/career-pass-20260728` | `organvm/limen:universe-recovery-20260823` | Its owning repository records preservation/landing or a human-protected worktree receipt before any cleanup. | `git -C /Users/4jp/Workspace/4444J99/application-pipeline/.worktrees/career-pass-20260728 status --short --branch` |

The two already-owned dirty rows remain with their native owners: Vltima's
`docs/plans/2026-08-06-prima-materia-reconciliation.md` and collaboration
platform's `docs/continuations/collaboration-operations-platform-alpha-20260802/workstream.json`.
Charles's clean editorial worktrees remain protected; they are not granted to
this recovery lane for reaping.
