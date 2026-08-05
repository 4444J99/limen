# Antigravity Scratch Reap Acceptance

`scripts/antigravity-scratch-bridge.py --apply-safe-reap --write` deletes local
Antigravity scratch roots only after a matching line exists in
`docs/antigravity-scratch-reap-acceptance.jsonl`. Do not create that JSONL as a
cleanup shortcut. It is the human acceptance ledger for irreversible local
scratch-root removal.

Each JSONL event must be one object with:

```json
{
  "accepted_at": "2026-07-06T06:30:00Z",
  "root": "example-scratch-root",
  "accepted": true,
  "private_receipt_sha256": "0123456789abcdef...",
  "archive_proof": "matching preservation event is archive_verified:true at /Volumes/Archive4T/limen-private/agy-scratch-preserve/.../root",
  "redaction_review": "private_archive_only",
  "redaction_proof": "raw scratch contents and per-file listings remain in the private receipt/archive; public docs contain counts, hashes, repo/head, and root names only"
}
```

Required proof fields are `accepted_at`, `archive_proof`, and
`redaction_proof`. `accepted: true` without those fields is incomplete and will
not authorize deletion.

The active bridge also requires a matching verified preservation event in
`docs/antigravity-scratch-preservation.jsonl`, keyed by `root` and
`private_receipt_sha256`. Acceptance alone is never sufficient.

Accepted redaction reviews are code-defined in
`scripts/antigravity-scratch-bridge.py`. Use `private_archive_only` when raw
scratch content is stored only in the private/external archive and the public
receipt is limited to bounded proof fields.
