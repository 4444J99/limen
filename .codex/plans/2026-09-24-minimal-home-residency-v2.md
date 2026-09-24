# Minimal home and Workspace — aligned implementation plan

Owner: Limen recovery, with PORTVS, Domus, ARCA/HORREVM and CCE owning their existing domains.
Authorized: direct user instruction to implement the aligned plan, 2026-09-24.
Supersedes the implementation ordering and ARCA publication mechanism in
`2026-09-24-minimal-home-residency.md`; historical receipts there remain evidence.
The original goal and all five completion criteria remain unchanged.

## Intended form

The laptop holds declared operating-system/application/personal working surfaces,
pinned control infrastructure, and active work. Other repositories default to a remote
catalog and materialize on demand. Both home and Workspace, including hidden and
application-owned stores, are in scope. Exact recoverability is mandatory; large
payloads in Git history are not.

| Owner | Authority |
| --- | --- |
| PORTVS | Immutable repository identity, canonical Workspace locations, residency and reconstruction references |
| Domus | Home surfaces, runtime/configured paths, tools, native adapters and hooks |
| Limen | Acquisition, session-bound leases, capacity, preservation coordination and retirement |
| ARCA/HORREVM | Encrypted originals/catalogs, recovery and independent replicas |
| CCE | Authorized selective retrieval and provenance |

Limen, Domus and PORTVS are pinned; PRDS and internal snapshots stay protected.
Other pins need an owner and reason. Extend the existing authorities; do not create
competing lease registries, catalogs or schedulers. Uncertain evidence means retained.

## Contracts

### Repository lifecycle

Keep `repo.ensure(repo_id, revision, session_id)` and `repo.release(lease_id)`.
Ensure returns the lease, managed directory, store and resolved commit. Bind local
residency records to conductor/native-session ownership. Serialize by immutable ID,
atomically publish ready stores, and retain interrupted initialization journals.
Repeated acquisition in an active session is idempotent; conflicting revisions require
a new session; separate sessions share a store through isolated worktrees.
Idempotent release queues the existing background consumer. Retire eligible worktrees
and then the store only after the final lease, absent pins/process references and
complete fresh custody. Expiry triggers investigation, never deletion.

Reporting and all reclaimers must share one classifier: actual filesystem identity,
repository identity, exact commits/refs, live remote custody, leases/process references,
private metadata/payloads, LFS and submodules. Revalidate under lock immediately before
mutation. Remove age, basename, patch-equivalence, ignored-name and stale-tracking-ref
deletion authority. Checkout, branch and task completion are separate.

### ARCA, HORREVM and CCE

Preserve ordinary files individually encrypted; large files use ciphertext parts.
Paths, names, native metadata, plaintext hashes and provenance belong inside encrypted
catalogs. Reuse unchanged ciphertext. Use streaming I/O, 32 MiB default parts, 4 MiB
buffers, bounded scratch reservations and process-group deadlines. A durable journal
resumes the same snapshot/catalog. Upload and read back payloads first; commit the
catalog/complete-snapshot receipt last. Incomplete releases are not custody.

Use the existing private GitHub Release adapter with pagination, under-2-GiB assets
and at most 1,000 assets per release. Bulk ciphertext is never staged in Git. Git
contains code, schemas, neutral receipts and small encrypted-catalog references.

The legacy ARCA commit must be reconstructible exactly: capture the complete necessary
Git object closure, raw commits/trees/tags/blobs, refs and relevant local metadata in
encrypted custody. A small additive branch references the reconstruction receipt;
do not claim the original SHA is a live GitHub branch. Isolated reconstruction must
reproduce original object IDs. Retain the original checkout until recovery passes.

Capture, primary readback, independent replication, independent-key recovery and real
restoration are distinct predicates. Existing ciphertext may be copied additively;
private-original retirement requires verified two-copy custody and restoration.
Independent-key recovery uses an isolated environment and the existing escrow owner,
not the normal keyring. Preserve legacy readers/ciphertext through replacement proof.
Use consistent database adapters and native metadata preservation; skipped, changed,
unsupported or failed sources are incomplete. Switch scheduled backup/status/restore
only after a bounded real canary succeeds. HORREVM replicates the same immutable
objects to declared independent storage rather than mirroring the legacy Git vault.

CCE retains `cce_search`: registered corpus/object IDs only; trusted caller and
destination authorization before decryption/emission; one derived private index;
bounded selective hydration; original object/version provenance. Explicitly distinguish
uncaptured, cold, unavailable and unauthorized. Resolve runtime/source provenance and
the configured corpus root through existing owners before deploying changes.

### Estate and hooks

Every managed object gets owner, canonical location, residency reason, custody state,
storage domain and retirement policy. Inventory both roots through a resumable bounded
frontier, including nested/hidden Git and copied source. Deduplicate filesystem identity;
do not follow symlink cycles, hydrate cloud placeholders or hide unreadable areas.

Codex recovery stores, plugins/package sources and installed runtimes leave generic
cache-disposal policy and use owner-specific custody/reconstruction rules. Inspect
actual executables, open files and loaded scheduled references. Claude VM handling
separates reconstructible images from protected sessions and proves cold start first.

Hooks perform scoped admission, deduplicated capture and lease release only. One-second
hard deadline; normal local capture below 250 ms. Background consumers do slow work.
Preserve reads during admission failures and scope mutation denial to its owner.
Native Codex/Claude canaries must prove effective configuration, secret scanning and LFS.

## Ordered tranches

1. **A — Control surfaces:** reconcile prior receipts/unpublished work; resolve root
   contracts in owning sources; diagnose the scoped verification timeout. Exit: consistent
   location contract, dispositions for existing PRs/changes, implicated verification.
2. **B — Classification/headroom:** resumable full inventory and measured growth;
   owner-specific safe cache and already-preserved idle-copy retirement. Exit: coverage
   ledger and candidate-level receipts with actual physical-space deltas.
3. **C — Complete repository loop:** shared evidence/release worker; one controlled
   concurrent acquire/work/preserve/release/retire/reacquire demonstration. Exit: one
   store, isolated work, exact custody and baseline residency restored.
4. **D — Custody/retrieval:** reliable objects, exact legacy reconstruction, independent
   recovery/replica, domain adapters and CCE. Exit: real remote-only restore and positive
   and negative authorized-retrieval proofs, before bulk migration.
5. **E — Producer rollout/migration:** all launchers, dispatchers, provider landings,
   editors and human opener; native hooks/runtime protections; idle-copy consolidation,
   then drain active leases. Exit: every resident authored repo has lease/pin, links have
   consumers and retirement conditions, ordinary cycles return to baseline.
6. **F — Steady state:** complete eligible cache/VM/private retirement and cold-storage
   verification; event maintenance plus bounded drift reconciliation. Exit: all five
   original outcome predicates, including approximately 200 GiB free.

Missing keys/drives block dependent private migrations only. Continue independent
engineering. Use existing admitted workspaces and bounded scratch; preserve 50/200 GiB
admission hysteresis. No alternate roots to evade admission.

### Tranche B checkpoint, 2026-09-24

`scripts/home-workspace-inventory.py` now provides a read-only, resumable home-root
frontier, including the Workspace subtree, hidden directories, nested Git stores,
linked worktrees, bare Git candidates, copied-source candidates and symlink aliases.
It records filesystem identities, mount boundaries and unmeasured paths in a private
0600 state file. A bounded live pass observed 41,262 directories, left 110,816 queued,
and recorded 1 unmeasured area; it is **incomplete** and grants no deletion authority.
Two focused restart/classification tests pass. Continue the frontier and reconcile
candidate identities with PORTVS/Domus owners and fresh custody evidence before any
retirement. Internal free space sampled at approximately 15 GiB; the 200 GiB outcome
remains unmet.

## Acceptance and reporting

Do not repeat subjective implementation percentages. Report original outcomes passed
out of five; evidence stages of the eleven original acceptance bundles; classified,
unresolved/unmeasured objects and custody coverage; actual free GiB and measured delta.
Code/tests/PRs/scans/catalog-only uploads never substitute for end-to-end acceptance.

- [ ] Both roots completely classified; no unexplained managed repository copies.
- [ ] Every resident authored repository has an active lease or explicit pin.
- [ ] Ordinary start/finish cycles return residency to baseline.
- [ ] Registered private material has verified encrypted remote custody and authorized retrieval.
- [ ] Approximately 200 GiB actual internal free space, APFS-aware and without size double-counting.

Verification covers simultaneous/idempotent acquisition; single and final release;
renames/transfers/conflicts/missing HEAD/interrupted clones/stale receipts/offline/crash;
dirty/ignored/stashed/native metadata/LFS/submodule preservation; interrupted capture,
source changes/corrupt parts/hostile catalogs/exact Git reconstruction; independent-key
and second-copy real restoration; caller/destination/path rejection; duplicate hooks,
network failure/timeouts/client restart; installed runtime/loaded references/natural
scheduled execution/rollback/reconstruction; and a second reconciliation with no needless
changes. A measured capacity deficit explains incompletion, never satisfies the target.

## Execution discipline and current receipt

One recovery writer; at most two implementation tasks and one heavy workload. Attempts
are 30 minutes with at most 10 minutes verification, bounded by the existing cumulative
120 agent-minute allowance. Do not reset counters through retries/restarts or rename
the same outcome. Reuse unchanged valid verification receipts; diagnose failures and
follow the exact-head merge rail without synchronous polling. No new paid service.

2026-09-24 planning evidence: 12.95 GiB free; Limen #2718 and Domus #393 open; 20
modified/untracked files in the existing recovery worktree. Two ARCA releases contain
only encrypted catalogs (5,846 and 5,848 bytes), zero verified ciphertext payload uploads.
Heartbeat has a prior natural execution receipt; wider rollout remains incomplete.
The current preservation helper lacks raw Git commit/tree closure and cannot yet prove
exact reconstruction. CCE's resolver ignores its deployed corpus-store variable.
Domus source already declares the correct Workspace root, but its deployed zsh surface
still exports the obsolete projects root. No retirement follows from this receipt.

### Aligned implementation receipt, 2026-09-24 23:30 UTC

Tranches A/B progressed; none of the five whole-estate acceptance criteria is closed.

- Applied Domus's existing authoritative zsh template to its exact installed surface.
  A fresh shell reports Workspace as `~/Workspace`, with the existing control-repository
  compatibility paths. `chezmoi status` reports no drift on that installed shell surface.
- Limen's resolver now consumes the shared `CCE_CORPUS_STORE_ROOT` contract, with an
  explicit Limen override and legacy source-drop compatibility. A configured empty or
  unavailable store cannot silently select an older populated store; invalid relative or
  repository-root configuration fails explicitly. Ten isolated resolver tests passed.
- This exposed an empty configured CCE store. Domus now declares and deploys a non-copying
  compatibility doorway to the registry-owned original corpus, with owner, two consumers
  and four custody/migration/reader retirement conditions. The original remains untouched;
  the configured location resolves to exactly the same original directory and reaches two
  corpora. This is path reachability, not a native CCE search or authorization receipt.
- Domus home-surface tests: 36 passed. Scoped Ruff E/F/W, diff hygiene and commit hooks,
  including secret scanning, passed. Source commit `113599c29190108c54524da56278d29554be4f2c`
  is pushed and exact branch readback matched. PR #393 remains open; the one exact-head
  merge submission returned `DEFERRED — LIFECYCLE-UNKNOWN`. No merge is claimed.
- The generic cache reclaimer now keeps application recovery stores, installed runtimes,
  plugins and installed tools visible as `owner-policy-required`. Nested Git stores require
  repository custody. Ownership uses actual cwd/executable/open-file references, not command
  substrings. Recheck references and path identity immediately before each retirement;
  unknown sensors retain candidates. Cache identity traversal has a 30-second bound.
  Twelve focused cache tests passed. No live cache apply or original retirement occurred.
- Registered the previously unregistered legacy ARCA helper tests; their predicate explicitly
  does not claim exact Git-history reconstruction or independent recovery. The source object
  implementation remains experimental and the legacy scheduled path remains unchanged.
- Scoped cheap wave: 41/42 passed initially; the citation gate correctly failed on the empty
  configured store. After deploying the declared doorway, that exact failed predicate passed.
  The API shard passed 52 tests. A bounded two-worker full CLI diagnostic still timed out at
  330 seconds, having progressed to 68%; it is not a pass. A sampled worker held an overnight
  trial fixture's observation lock; this localizes further profiling but does not prove a
  deadlock. No repeated whole-suite attempt or merge is justified by this checkpoint.
  The subsequent admission-gated dispatcher, repo-lifecycle and cache shard passed
  370 tests in 5.81 seconds. This focused receipt does not replace the incomplete full
  CLI gate. Current implementation is suitable for publication as unfinished work,
  not merge/deployment acceptance for the complete lifecycle.
- Latest capacity observation during verification: 11.84 GiB free. There is no net recovery
  claim and the cause of concurrent growth remains unmeasured. ARCA's existing pack directory
  contains 6,789,859,243 bytes, which is inventory evidence, not deletion authority.

Continuation retains the same original outcome and cumulative budget. Resolve the full CLI
verification tail through bounded profiling and durable shard evidence, then continue the
resumable full classification/shared evidence lifecycle work. Do not restart bulk ARCA uploads
or retire private originals in lieu of the missing independent-key and replica restore proofs.

Publication/readback: Limen implementation commit
`2df974022bd3fd6f6009dcd01c52e3912accd93f` is preserved on the existing PR #2718;
exact remote branch and PR head matched. The PR is explicitly draft because full CLI
verification remains incomplete. Both implementation worktrees were clean after publication.
The read-only application-owner canary inspected six declared surfaces: two existing
surfaces were retained as owner-policy-required, four were absent, no candidate was
eligible, and the actual process sensor reported no error. No deletion was attempted.
The final sampled free capacity was 11.51 GiB; this does not satisfy capacity acceptance.
