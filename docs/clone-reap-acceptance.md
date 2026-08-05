# Clone Reap Acceptance

`scripts/reap-clones.py --apply` deletes standalone local clone directories only
after the loss-free mirror gate passes and a matching line exists in
`docs/clone-reap-acceptance.jsonl`. Do not create that JSONL as a cleanup
shortcut. It is the human acceptance ledger for irreversible local clone
removal.

Each JSONL event must be one object with:

```json
{
  "accepted_at": "2026-07-06T06:30:00Z",
  "root": "example-clone",
  "slug": "owner/example-clone",
  "accepted": true,
  "reason": "pushed-mirror",
  "archive_status": "not_required_clean_remote_mirror",
  "archive_proof": "fresh fetch/remote reachability proved local refs are reachable from origin",
  "redaction_review": "not_required_remote_only",
  "redaction_proof": "local deletion removes only a clean clone cache; Git objects remain on the verified remote and no untracked, ignored-data, stash, reflog-only, LFS, submodule, or linked-worktree state is present"
}
```

Required proof fields are `accepted_at`, `archive_proof`, and
`redaction_proof`. `accepted: true` without those fields is incomplete and will
not authorize deletion.

Accepted archive statuses and redaction reviews are code-defined in
`scripts/reap-clones.py`. Use `not_required_clean_remote_mirror` and
`not_required_remote_only` only when the clone is a clean, re-cloneable remote
mirror and the local directory contains no unique unpublished data.
