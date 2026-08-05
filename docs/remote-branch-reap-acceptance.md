# Remote Branch Reap Acceptance

`scripts/reap-remote-branches.py --apply` deletes a remote branch (`git push origin
--delete`) only after a matching line exists in `docs/remote-branch-reap-acceptance.jsonl`
AND `LIMEN_REMOTE_REAP_APPLY=1` arms the run (double-dark). Do not create that JSONL as a
cleanup shortcut. It is the human acceptance ledger for irreversible remote-ref reaping.

A remote delete is **not reflog-recoverable** on the origin — unlike a local branch ref,
whose pre-squash commits linger in the local reflog ~90d. That is why this surface is armed
separately (`LIMEN_REMOTE_REAP_APPLY` defaults `0`, not `1`) and carries a wider default
grace window (24h vs the local reaper's 60m): other clones and CI may still hold the ref.

Each JSONL event must be one object with:

```json
{
  "accepted_at": "2026-07-10T18:30:00Z",
  "branch": "example/topic-branch",
  "accepted": true,
  "reason": "landed-ancestor",
  "tip": "0123456789abcdef0123456789abcdef01234567",
  "archive_status": "landed_on_default_verified",
  "archive_proof": "origin/example/topic-branch is reachable from origin/main at <default-sha>",
  "redaction_review": "not_required_landed_ref",
  "redaction_proof": "remote ref deletion removes only a branch pointer; landed git objects remain on origin/main"
}
```

Required proof fields are `accepted_at`, `archive_proof`, and `redaction_proof`.
`accepted: true` without those fields is incomplete and will not authorize deletion.

Accepted archive statuses and redaction reviews are defined in
`scripts/reap-remote-branches.py`; the common cases are `landed_on_default_verified` for an
ancestor proof or `merged_pr_verified` for a squash-merge proof, and
`not_required_landed_ref` for redaction when the branch tip is already on the default branch
or captured by the merged-PR receipt and the remote ref carries no additional unpublished
content.

This file documents the acceptance shape only. The active acceptance ledger is
`docs/remote-branch-reap-acceptance.jsonl`, which should be written only when a human has
reviewed the branch, archive/storage proof, and redaction proof.

## Standing grant (landed classes only)

A single ledger event with `"standing": true` and `"branch": "*"` covers every remote branch
the classifier itself proves landed — reason `landed-pr-merged` (PR MERGED per `gh` AND the
tip not advanced past mergedAt) or `landed-ancestor` (the remote tip reachable from the
default ref). The machine proof is the archive proof; the grant delegates the per-branch human
key for exactly those two classes and nothing else. Any other class still requires a
per-branch, tip-matched acceptance event. This mirrors the local branch reaper's standing
grant and the merge standing grant (#207); it is intentionally NOT granted by default here,
because a remote delete is irreversible — arm it deliberately.
