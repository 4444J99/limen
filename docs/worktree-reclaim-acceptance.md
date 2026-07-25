# Worktree Reclaim Acceptance

`scripts/reclaim-worktrees.py --apply` detaches registered worktrees and moves
standalone worktree-like clones or generated residue into recoverable
same-filesystem quarantine only after the loss-free reclaim gate passes.
Every physical action is mediated by `limen.worktree_abandonment.v1`.
Registered worktrees use non-forced Git detach; every other root uses one atomic
rename into an off-scan quarantine. The reaper does not reset, clean, or
recursively delete a root. A failed validation or move leaves the source in
place and writes a typed crash receipt under `logs/worktree-abandonment/`.

The same contract exposes the only sanctioned malformed-worktree lock repair:
an exact regular zero-byte lock may be removed only when two identity
observations match the operator-captured device, inode, size, and nanosecond
modification time, and an unprivileged open-file probe reports no owner.
Identity drift, a symlink, nonzero content, an open descriptor, or an
unavailable probe fails closed.

The merged loss-free classes (`clean+merged+idle` and
`receipt-remote-merged+clean+idle`) are pre-accepted under the operator standing grant
`standing-grant-2026-07-09`
(`docs/removal-acceptance-covenant.md` §Standing grant; disable with
`LIMEN_RECLAIM_STANDING_ACCEPTANCE=0`). Every other class additionally requires
a matching line in `docs/worktree-reclaim-acceptance.jsonl`. Do not create that
JSONL as a cleanup shortcut. It is the human acceptance ledger for physical
local worktree/root abandonment outside the standing-grant class.

Antigravity/Agy scratch roots are not covered by this worktree standing grant.
Even when a scratch clone is clean, merged, and idle, physical scratch-root
removal belongs to `scripts/antigravity-scratch-bridge.py` plus
`docs/antigravity-scratch-reap-acceptance.jsonl`.

Each JSONL event must be one object with:

```json
{
  "accepted_at": "2026-07-06T06:30:00Z",
  "root": "example-worktree",
  "accepted": true,
  "action": "remove-worktree",
  "reason": "clean+merged+idle",
  "archive_status": "not_required_clean_merged_remote",
  "archive_proof": "HEAD is reachable from the remote default branch or patch-equivalent to it",
  "redaction_review": "not_required_remote_only",
  "redaction_proof": "local removal deletes only a clean merged worktree; no untracked, dirty, private patch, or generated-only payload remains outside the documented receipt"
}
```

Required proof fields are `accepted_at`, `archive_proof`, and
`redaction_proof`. `accepted: true` without those fields is incomplete and will
not authorize removal.

Accepted archive statuses and redaction reviews are code-defined in
`scripts/reclaim-worktrees.py`. Use `not_required_clean_merged_remote` and
`not_required_remote_only` only when the worktree/root is clean, idle, and
already preserved by its merged remote/default lifecycle.

Pushed-but-unmerged branches and open PRs are not a removal class. They stay as
`not-merged-to-default` until the PR is merged or the local patch is proven
patch-equivalent to the remote default branch.
