# Branch Reap Acceptance

`scripts/reap-branches.py --apply` deletes local branch refs only after a matching
line exists in `docs/branch-reap-acceptance.jsonl`. Do not create that JSONL as a
cleanup shortcut. It is the human acceptance ledger for irreversible branch-ref
reaping.

Each JSONL event must be one object with:

```json
{
  "accepted_at": "2026-07-06T06:30:00Z",
  "branch": "example/topic-branch",
  "accepted": true,
  "reason": "landed-ancestor",
  "tip": "0123456789abcdef0123456789abcdef01234567",
  "archive_status": "landed_on_default_verified",
  "archive_proof": "tip is reachable from origin/main at <default-sha>",
  "redaction_review": "not_required_landed_ref",
  "redaction_proof": "local ref deletion removes only a branch pointer; landed git objects remain on default"
}
```

Required proof fields are `accepted_at`, `archive_proof`, and
`redaction_proof`. `accepted: true` without those fields is incomplete and will
not authorize deletion.

Accepted archive statuses are defined in `scripts/reap-branches.py`; the common
branch case is `landed_on_default_verified` for an ancestor proof or
`merged_pr_verified` for a squash-merge proof. Accepted redaction reviews are
also code-defined. Use `not_required_landed_ref` only when the branch tip is
already stored on the default branch or by the merged PR receipt and the local
ref carries no additional unpublished content.

This file documents the acceptance shape only. The active acceptance ledger is
`docs/branch-reap-acceptance.jsonl`, which should be written only when a human
has reviewed the branch, archive/storage proof, and redaction proof.

## Standing grant (landed classes only)

A single ledger event with `"standing": true` and `"branch": "*"` covers every branch the
classifier itself proves landed — reason `landed-pr-merged` (PR MERGED per `gh` AND tip not
advanced past mergedAt) or `landed-ancestor` (tip reachable from the default ref). The machine
proof is the archive proof; the grant delegates the per-branch human key for exactly those two
classes and nothing else. Any other deletion class still requires a per-branch, tip-matched
acceptance event. Granted by Anthony in-session 2026-07-09 after repeated per-branch acceptance
rounds (178 reaps in one closeout) made the ask itself the friction; precedent: the merge
standing grant (#207).
