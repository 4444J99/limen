# Portable context and migration receipt

Use a small Markdown packet for human-facing import, or a structured equivalent
when the destination explicitly supports it. This is an interchange convention,
not a provider-native schema. Do not upload this entire ledger if the destination
only needs the approved facts.

## Packet fields

- Migration ID and captured-at timestamp.
- Source provider and account/workspace alias; destination alias and context type.
- Coverage: inspected, empty, unavailable, omitted, with reasons.
- Facts grouped by preferences, working conventions, active projects, and durable
  background only where present. Keep transient session observations separate.
- For each fact: stable ID, concise text, scope, source pointer, source timestamp
  if known, and basis (explicit user statement or clearly labeled inference).
- Conflicts and exclusions, with decisions or unresolved status.

Example fact (synthetic):

| ID | Context | Scope | Basis | Source |
|---|---|---|---|---|
| PREF-001 | Prefer concise progress updates. | General working style | Explicit user statement | Sanitized source item 12 |
| PROJ-001 | Draft milestones before estimating delivery. | Project Cedar only | Explicit project instruction | Sanitized source item 27 |

Do not invent absent values. Keep detailed private source mappings in the private
receipt, with only safe aliases in shareable output.

## Comparison

| Item ID | Source | Destination | Disposition | Reason |
|---|---|---|---|---|
| PREF-001 | Same preference | Already present | Keep existing | Duplicate |
| PROJ-001 | Scoped instruction | Absent | Add if in scope | New context |

Other useful dispositions: revise, conflicting, excluded, unavailable. Distinguish
semantic agreement from byte equality; provider normalization may change wording.
Show conflicting values and provenance without silently choosing one. Preserve
the user's current explicit correction when it resolves the conflict.

## Sanitization ledger

Record item ID, category removed/generalized, reason, and effect on usefulness.
Never copy a secret into the ledger. Scan the final payload and any attachments,
including filenames and metadata that may expose private identifiers.

## Receipt

Record:

- Original artifact location and integrity hash in private storage.
- Sanitized packet location/hash, included item IDs, redaction count, and coverage.
- Destination, supported import route, and payload/chunk IDs.
- Submission result and time, including an unknown result.
- Persistence readback evidence, item-level differences, and recall-check result
  if performed.
- Unresolved conflicts, unavailable surfaces, and the precise next verification.

A submitted import without readback stays "submitted; persistence unverified."
A requested account export without a received file stays "requested; not received."
