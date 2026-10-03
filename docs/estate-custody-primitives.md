# Estate Custody Primitives

Generated for the run-and-gun substrate correction on 2026-07-07.

## Contract

The laptop is a thin control plane. It must be able to run at a coffee shop from
remote owner receipts, active checkouts, and small cached indexes.

The external SSD estate is the durable library and processing substrate. When the
drives are plugged in, they should hold the complete private/raw estate, processed
and redacted corpora, repo/org custody mirrors, photos/media packages, and recovery
copies. They are not just leftovers from the prior recovery incident.

Remote services remain canonical for remote objects. GitHub repos, profile state,
issues, PRs, releases, and deployed proof surfaces must be read from the remote
owner first. Local clones are staging caches.

## Existing Doctrine

These prior receipts are the current authority until a newer owner receipt
supersedes them:

- `/Volumes/Archive4T/_OPERATIONS/STORAGE-OPERATING-MANUAL-2026-06-15.md`
- `/Volumes/Archive4T/_OPERATIONS/LOCAL-DISK-EXPULSION-POLICY-2026-06-15.md`
- `/Volumes/Archive4T/_MANIFESTS/ARCHIVE4T-CURRENT-STATE-2026-06-15.md`
- `docs/vltima-absorb-cadence.md`
- `docs/vltima-prior-excavations.md`
- `docs/photos-universe-recovery-2026-06-29.md`

Key rules recovered from those surfaces:

- `Archive4T` is the curated archive for retained documents, exports, organized
  media/text, and code/project source not actively edited on the Mac.
- `Ingress` is temporary intake. Nothing in it is archived until promoted or
  deleted after backup gates.
- `Scratch` is disposable workspace. Nothing important lives only there.
- `T7Recovery` is the second local recovery copy. It is not scratch and should
  not be erased until offsite/versioned backup is proven and restore-tested.
- Important data is safe only when it exists in at least two independent places
  and at least one place has retention or version history.
- Internal free space must cover the telemetry-backed resource envelope for the
  selected task graph. Historical fixed-space targets remain evidence only.
- No mass deletion, dedupe, repo movement, or archive rewrite is authorized by
  this doc.

## Primitive Layers

### Portable recovery amendment (2026-10-03)

External drives are optional library/processing attachments, not a prerequisite
for session measurement or recovery. An intentionally detached drive remains an
observed offline replica; it is not replaced by a fabricated mount or device ID.
The two-independent-copy/full-restore gate remains binding.

`limen.custody_receipt.v2` adds a backend-neutral contract alongside unchanged
v1 physical-device receipts. Each replica binds its provider, opaque account
namespace, exact encrypted object generation, capture profile, manifest,
authenticated ciphertext readback and full content/native-metadata restoration.
GitHub and Google Drive are separate provider failure domains. Two repositories,
folders or accounts at one provider are not two independent vendors. Only a real
physical replica carries `device_id`. At least one restored replica must bind a
retention horizon to provider evidence. Dropbox remains a sealed continuity
kernel/recovery-card rail, not an estate archive fallback.

A valid schema is not a provider observation, restore execution, session release
or deletion permission. The producers and acceptance consumers must authenticate
these facts before v2 evidence can authorize any retirement. Legacy receipts must
not be rewritten to call cloud accounts physical devices. Portable recovery keeps
the original native session/caller and records old/new scope lineage explicitly;
it never drops a missing historical root from the denominator.

The scoped session consumer accepts v2 only through a
`limen.portable_custody_evidence.v1` bundle: set the custody packet's `contract`
to `limen.custody_receipt.v2`. The bundle binds the exact session and all original
scope path digests, embeds the v2 contract, and resolves every supporting digest
through committed, unchanged owner evidence. Capture manifests enumerate the
same logical/native atoms in every original root; ciphertext manifests bind the
exact captured object denominator. Authenticated readback records bind provider,
account namespace, object ID, revision, bytes and checksum. Retention covers all
generations and must still be in force. Each full restore has a committed predicate
and an observation that covers every logical and native atom. Contract validity,
an expired retention receipt, or a partial restore renamed "full" cannot satisfy
this consumer. Legacy custody evidence is unchanged and cannot substitute for a
new portable contract's supporting graph.

`limen.native_capture.capture_manifests` supplies bounded, no-ignore native
capture. It reads file contents, symlink targets without traversal, cross-root
hardlinks, ownership, modes, timestamps, flags, xattrs and ACLs. macOS creation
timestamps use `getattrlist` nanoseconds, not rounded Python floats. Native value
bytes and file contents are represented by digests in these inventories; raw
recovery bytes still belong in the encrypted archive. Unsupported metadata,
changed sources and exhausted resource bounds reject the whole capture, never a
silently reduced denominator. The caller must admit the heavy workload and keep
the generated inventories in private encrypted custody.

These functions do not upload ciphertext, execute an independent restore, relax
historical path binding or authorize deletion. Missing/relocated roots still
require separately implemented and verified lineage acceptance; all six original
scopes and current deltas remain work until their owning predicates pass.

`limen.native_equivalence.compare_native_manifests` supplies the inventory
comparison primitive for that pending lineage/restore consumer. It requires
complete original and observed records, identical root/atom membership, and exact
content, ownership, modes, mtime, birthtime, flags, xattrs, ACLs and hardlink
membership. Original atime and filesystem-maintained ctime remain mandatory
historical records; a restored filesystem's distinct clocks are reported, never
asserted recreated. The report binds both complete input digests but does not
establish live freshness, encrypted custody, relocation permission, retirement,
or session release. The complete historical inventory must stay in encrypted
custody; a comparison report cannot replace it. Lineage wiring and live proof
over all original scopes remain unfinished.

The existing T7 lifeboat already points at the correct symbolic form:

| Layer | Existing Root | Role |
|---|---|---|
| `00_SUBSTRATE` | `/Volumes/T7Recovery/CleanUnique-Lifeboat-2026-06-13/00_SUBSTRATE` | device, shell, PATH, local tools, session/runtime control-plane evidence |
| `10_PROFILE` | `/Volumes/T7Recovery/CleanUnique-Lifeboat-2026-06-13/10_PROFILE` | public/private identity, profile proof, user-facing persona, account evidence |
| `20_TEXT` | `/Volumes/T7Recovery/CleanUnique-Lifeboat-2026-06-13/20_TEXT` | prompts, transcripts, markdown, plans, notes, docs, redacted corpora |
| `30_CODE` | `/Volumes/T7Recovery/CleanUnique-Lifeboat-2026-06-13/30_CODE` | repos, worktrees, prior migrations, hidden git roots, source custody |
| `_MANIFESTS` | `/Volumes/T7Recovery/CleanUnique-Lifeboat-2026-06-13/_MANIFESTS` | verification, classification, domain maps, restore evidence |

The next implementation pass should preserve this shape while adding explicit
processed/redacted outputs for media, prompts, plans, and private data.

## Run-And-Gun Laptop Rule

The laptop keeps:

- active worktrees only while being worked;
- small durable receipts and redacted indexes;
- local tools required to hydrate from remotes;
- enough cached state to continue when the drives are unplugged.

The laptop should not keep:

- completed repo clones after remote custody is proven;
- bulk prompt/session corpora that already have private external custody;
- raw media exports or Photos-derived working sets after package custody;
- dependency caches, build outputs, and abandoned scratch roots.

## Private Data Pipeline

Private data is not ignored. It is processed with custody:

1. Raw private data lives in the external estate with backup/restore evidence.
2. Private processors read it and write private receipts into ignored owner paths.
3. Public repos receive only redacted aggregate counts, generated methods, demos,
   tests, or fixtures that cannot expose private records.
4. A pain point that becomes a reusable method should get a public shell and a
   private adapter boundary.

This is the product form: solve the pain locally, split private data from method,
then ship the method outward when safe.

## Owner Packets

Current owner packets already opened or required:

- Disk/worktree lifecycle: `https://github.com/organvm/limen/issues/685`
- External estate implementation receipt: `https://github.com/organvm/limen/issues/688`
- Photos/media processing pipeline: `https://github.com/organvm/media-ark/issues/56`
- Portvs triptych publication: `https://github.com/organvm/portvs/issues/2`
- Historical token tombstone and credential wall: `https://github.com/organvm/limen/issues/686`
- Contribution-balance value gate: `https://github.com/organvm/limen/issues/687`
- GitHub sidebar metadata scope gate: `https://github.com/4444J99/4444J99/issues/1`
- LAVREA profile-card overflow: `https://github.com/organvm/laurea/issues/4`

Owner packets still open after this doctrine lands:

- External estate implementation receipt: keep `docs/estate-custody-implementation-receipts.json`
  open until the safe, non-destructive implementation pass proves what moved,
  what was indexed, what was redacted, and what remains blocked.
- Prompt chronology: VLTIMA/Limen must refresh session corpus, prompt lifecycle,
  command-center, prior-excavation, and result-digest ledgers before inventing
  another prompt store.

## Verification

Non-destructive current-state refresh:

```bash
python3 scripts/always-working.py --write
python3 scripts/substrate-ledger.py --write
python3 scripts/vltima-prior-excavations.py --write
python3 scripts/photos-duplicate-proof.py --help
```

Cleanup or movement is a separate owner action. It must cite the two-copy/restore
gate and write an implementation receipt before any local cache is deleted.
