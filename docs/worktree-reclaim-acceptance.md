# Worktree Reclaim Acceptance

`scripts/reclaim-worktrees.py --apply` removes registered worktrees, standalone
worktree-like clones, or generated residue only after the loss-free reclaim gate
passes and a matching line exists in `docs/worktree-reclaim-acceptance.jsonl`.
Do not create that JSONL as a cleanup shortcut. It is the human acceptance
ledger for irreversible local worktree/root removal.

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
