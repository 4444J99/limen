# Encrypted knowledge publication: Limen operational boundary

The existing [archive loop](ai-exports-archive.md) continues to own local ingest, feeds, prompt
ledger, reading interfaces and the knowledge-alive predicate. CCE adds the opt-in `cce sealed`
publication/restoration layer; Limen does not implement another archive engine, duplicate the
cryptography, or change the corpus registry/store rules. Install the engine from an exact reviewed
revision containing that command and its `sealed` extra. Until its implementation PR is accepted,
this is a proposed operational interface, not evidence of an installed live capability.

The implementation owner and full command/format contract are
[`conversation-corpus-engine/docs/encrypted-publication.md`](https://github.com/4444J99/conversation-corpus-engine/blob/feat/encrypted-archive-publication-20261019/docs/encrypted-publication.md).
The link intentionally names the review branch; replace it with an accepted commit pin only after
integration and exact-revision verification. No deployed/installable engine revision is claimed here.

## Planes and authority

| Plane | Limen relationship |
|---|---|
| Raw exports and independent physical backups | Read-only sources and custody; unchanged |
| Existing `.limen-private` archive | Approved selection source; still Git-ignored plaintext |
| Atomic source/provenance/authorship | CCE message atoms and explicit `.atoms.jsonl` annotations; export roles confer no operator authority |
| Ciphertext Git tree | Separate dedicated worktree; selected bytes only; never a plaintext working store |
| Instance authorization | Owner-enrolled X25519 credential; app/instance ID labels alone grant nothing |
| Publication authorization | Pinned Ed25519 owner credential; transport credentials are separate |
| Recovery and freshness | Enrolled independent recovery key plus current owner-provided checkpoint, both outside Git |

The v1 adapter uses protected local credential files and checks POSIX file permissions. Hardware
attestation, Windows ACL enforcement, non-exportable keys and a remote key-release service are not
implemented. Do not claim access is restricted to a particular binary/runtime merely because its
credential carries that app ID. The local host and its credential custody are trusted.

## Reversible operator workflow

1. Verify the existing archive using its registered store and existing checks. Identify the exact
   selected normalized files, manifest and optional reading surfaces. Freeze them for the run.
2. Keep the selection, owner/device/recovery credentials, recipient records and freshness checkpoint
   outside every Git worktree. Verify intended device public keys independently before enrollment.
3. Use a fresh, dedicated empty ciphertext repository. Run CCE `sealed publish`, `verify`, `status`
   and `audit-history`. Stage only `HEAD.cce` and `objects`, using the fixed commit message
   `chore: update encrypted archive`; audit again after commit. Commit each snapshot before the next
   publication. Existing archive/feed/ledger receipts remain untouched.
4. Review measured tree and Git-history storage, update frequency, remote identity/visibility and
   provider policy before any real-data push. No automatic remote push, visibility change, paid
   storage, schedule, worker, lease authority or plaintext MCP endpoint is added.
5. Transfer a fresh checkpoint through a trusted channel to each enrolled device. Clone ciphertext,
   restore to a new private directory outside Git, byte-verify, register the reconstructed store and
   run the existing archive verification. The current reading interfaces remain local plaintext.
6. For a recipient change, use CCE `publish --rotate` with the complete intended recipient list.
   Old keys still decrypt old history. The command rotates the data epoch, not owner signing trust.
7. Repair a missing/corrupt unit only from matching authenticated ciphertext held in an independent
   copy; HEAD repair must match the exact private checkpoint. Missing data in all copies cannot be
   reconstructed from a digest. Do not prune Git history, retire sources or delete backups.

For command syntax and synthetic development validation, use the engine contract above; Limen
does not copy command implementations. Real-data acceptance requires local corpus access and
measured capacity, protected credential/recovery custody, actual device identities/enrollment,
freshness transfer, an independent restore, history audit and verified remote parity. Configuration
or synthetic tests are not a live publication receipt. Browser/Notes/Docs exports can be explicitly
selected as bytes and annotated as atoms; provider-specific capture/readers remain separate work.

## Preserve the independent backup

The unchanged [2026-10-18 receipt](../receipts/receipt-custody-ai-exports-second-copy-20261018.json)
records 3,547 files (3,467,404 kilobytes) for Claude, Gemini, Grok and Perplexity copied from disk7
Scratch to disk9 T7Recovery and compared by SHA-256 manifests. This change does not recopy, move,
delete or claim a fresh reread of either device. The existing archive map documents the receipt's
limits, including destination attachment/reverification and excluded ChatGPT scope. Ciphertext
portability complements this custody; it does not retire it.

## Capacity and privacy gate

GitHub is not an unlimited storage service. The engine default is a 512-MiB budget over retained
ciphertext plus a separate estimate of Git object storage/new ciphertext. Its small objects avoid
individual-object limits but do not eliminate retained-version growth, rotation overhead, the
2-GB push ceiling or GitHub's repository-size guidance. LFS is neither enabled nor assumed free.
The backup receipt's raw-source volume is already larger than one push; actual selected normalized
bytes have not been measured here. See the engine's dated primary-source capacity assessment.

Repository observers still see padded sizes, counts, equality/change patterns, recipient count,
generations and Git metadata. Source paths, plaintext hashes, app labels, timestamps and text
belong inside ciphertext. History audit covers reachable refs, not reflogs, unreachable blobs,
provider caches or previously leaked copies. Use fresh repository custody and content-free branch,
tag and commit naming. Never use a previously plaintext repository as a shortcut.
