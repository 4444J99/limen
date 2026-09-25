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
0600 state file. Bounded live passes observed 634,030 distinct directories and
exhausted the traversal frontier. One vanished temporary path is recorded as a
resolved source change; one cloud-storage area timed out and remains unmeasured.
The scan is **incomplete** and grants no deletion authority. Checkout `.git`
stores are now distinguished from independent bare repositories. Its resumable
private checkpoint is at
`/Users/4jp/Workspace/limen/.limen-private/home-workspace-inventory-v1.json`.
Focused restart/classification tests pass. Reconcile the remaining cloud timeout and
candidate identities with PORTVS/Domus owners and fresh custody evidence before any
retirement. Internal free space sampled at approximately 15 GiB; the 200 GiB outcome
remains unmet.

The repository acquisition path now checks every existing or newly cloned store's
origin against the requested live immutable GitHub repository ID. Coordinate/alias
similarity cannot issue a lease. Focused lifecycle and inventory checks pass (6 tests).
Final-release preservation, retirement, and reconstruction remain unimplemented.

### PORTVS catalog checkpoint, 2026-09-24

PORTVS PR #12 (`feat/remote-default-residency-20260924`, head
`5e79f13d218bdf23dc708801f7481d71a2cae7b5`) declares five authored
repositories `remote-default` and the three control repositories `control-pin`.
All eight rows have live immutable GitHub IDs and current `4444J99` coordinates;
Domus's default-branch metadata is corrected to `main`. PORTVS bootstrap accepts
an absent remote-default checkout without cloning, and reports an absent control
pin for Limen-managed acquisition. Legacy `laptop` clone behavior is still present
for older manifests and must migrate before all producers satisfy the one-interface
rule. All 69 bootstrap tests plus the new immutable-ID case passed. The live
read-only plan had zero actions and six blockers for the three control roots and
their compatibility links. No roots were moved. One exact-head merge-drain
submission returned `DEFERRED — LIFECYCLE-UNKNOWN`; do not retry without changed
relevant input. The PR is open, not merged or deployed.

The existing worktree abandonment detach path now retains Gitlink/submodule and
LFS-tracked checkouts until separate custody is demonstrated. Missing Git/LFS
inventory also retains the checkout. All 29 abandonment tests passed, including
new submodule and LFS retention cases. This is a safety gate, not final-release
retirement or canonical-store reconstruction.

The clone reaper now removes directory mtime from retirement authority, rejects
basename-only acceptance matches, cannot disable live origin verification via
`LIMEN_REAP_VERIFY_REMOTE=0`, and subtracts only `origin` refs when checking unique
objects. Ignored content of any name retains the clone pending owner-specific
custody/reconstruction proof. Apply rechecks live origin, payloads and filesystem
identity immediately before removal. All 64 focused real-Git tests passed. The
reaper still needs shared evidence classification, full local Git metadata custody,
and integration with the lease-release worker before it can establish the complete
repository loop or justify broad source retirement.

The removal edge now rejects symlinked `.git` stores, rechecks status with an
explicit Git exit code, and records partial/failed `rmtree` as incomplete rather
than reclaimed. Apply reports measured free-space change separately from
apparent file sizes; APFS sharing and concurrent writes can make these differ.
All 65 focused reaper tests passed, including a failed-removal receipt case.

ARCA's live private Releases were rechecked: each contains only one small encrypted
catalog asset and no encrypted payload object, so registered private custody is
still incomplete. The release publisher now uploads and verifies object assets
before publishing the encrypted catalog as a batch commit marker; eight focused
publisher tests pass. No bulk upload, source retirement, or restoration claim
follows from this ordering fix. HORREVM cold storage is not attached.
The normal GPG listing advertises the pinned key, but the real
`private-vault.py recovery-check --apply` still failed to decrypt with
`No secret key`. Listing metadata is not a recovery receipt. Independent-key
restoration remains unproven, and no private original may be retired.

Limen now exposes `repo reconcile REPO_ID` as a bounded background custody pass.
Release records the checkout's exact HEAD; reconcile serializes on the repository
lock, retains all checkouts while any owner lease is active, checks the store's live
immutable GitHub ID, and detaches only clean released worktrees whose HEAD matches
a freshly advertised origin branch through the existing abandonment receipt rail.
Dirty work and the canonical object store remain resident. Unknown lease states,
offline identity, missing checkouts and failed detach retain explicit states.
A controlled local test exercised two sessions, final release, exact-tip checkout
retirement, dirty retention and idempotent replay. `repo reconcile-pending` now
walks the managed lease registry with a durable round-robin cursor, one repository
per existing heartbeat hygiene tick, and a 90-second child deadline. Symlinked
registry entries are ignored; an unavailable repository is reported retained and
the cursor advances. Thirty-five focused lifecycle and abandonment tests, focused
Ruff, CLI help, and heartbeat shell syntax passed. Whole-file Ruff on `cli.py`
still reports five pre-existing `subprocess.run` check-argument findings outside
this change. This is source-level scheduling and checkout retirement only:
installed-runtime execution, canonical-store custody/retirement and a real GitHub
reacquisition canary remain.

After PR #2709 merged, PR #2718 conflicted with main only in the earlier plan
record. The plan text was preserved and main merged at `0713f370f`; 35 focused
lifecycle/abandonment tests and heartbeat syntax passed again, and GitHub now
reports the draft PR mergeable. The new reconciliation call subsequently moved
to the existing `beat_run` wrapper so timeouts and other child failures enter the
heartbeat rung ledger with their actual exit codes, rather than being masked by
a `tail` pipeline. This wrapper change still needs its own published receipt.

### Physical-capacity checkpoint, 2026-09-25

The owner-aware cache reclaimer checked 27 paths and produced nine unreferenced,
regenerable candidates totaling 7,619,404 KiB apparent allocation under plan
`e4c274c005a025ad74c014e3e77735ab45a05c03b2eb5c54894757b90497216b`.
Its exact-plan apply removed all nine after fresh identity and process-reference
checks; the apply receipt reports zero residual candidates. Six other paths were
blocked by active processes or owner policy. No private, worktree, application
recovery Git, installed-runtime, or plugin source was included.

Fresh `df -k /Users/4jp/Workspace` reports 12,751,568 KiB available (12.16 GiB),
so the apparent cache deletion did not achieve physical headroom. APFS currently
reports 16 local Time Machine snapshots on the Data volume; these remain protected.
The approximately 200 GiB capacity criterion is still unmet, and future candidate
receipts must distinguish apparent bytes from measured free-space change.

Domus PR #393 now owns a narrow Claude VM lifecycle adapter and manifest policy
at `6ead1eb3`. The live compressed base decoded successfully to 10,737,418,240
bytes, but its SHA-256 differs from the expanded `rootfs.img` of the same logical
size. The expanded image occupies 10,619,207,680 allocated bytes and is
`retained-divergent-expanded-image`; the separate `sessiondata.img` remains
protected. Thirty-seven targeted Domus tests, focused Ruff, JSON validation,
pre-commit hooks and live read-only digest verification passed. No VM image was
removed: distinct expanded state lacks custody and a native cold-start
reconstruction receipt, and snapshots may retain physical blocks regardless. The
adapter compares digests locally and emits only equality and aggregate byte counts.
Domus PR #393 later failed CI at `6ead1eb3`: its new script had four E501 lines,
and four notification BATS cases depended on wall-clock quiet hours. Head
`3ad8eef8` fixes the lines and pins the fixture clock. The targeted notification
suite passed 19/19, the local full BATS suite passed 349/349, 37 targeted Python
tests passed, and CI's E/F/W Ruff selection passed locally. The new remote CI run
was queued at last observation. One exact-head merge-drain submission returned
`DEFERRED — LIFECYCLE-UNKNOWN`; no merge or installed-runtime claim follows.
The exact Domus PR head later reported all GitHub checks successful, including
Build/Test/Lint, BATS, Python, secret scanning and Semgrep. It remains open; the
unchanged head is not resubmitted after the one-shot deferred rail receipt.
Subsequent independent `df -k` measured 30,117,868 KiB (28.72 GiB) available,
while APFS listed 10 local Time Machine snapshots rather than 16. Snapshot aging
is observed, not an agent retirement action or an attributable cache result. The
host remains below the 50 GiB new-worktree admission floor and the 200 GiB target.

### ARCA bounded-object checkpoint, 2026-09-25

`arca-file-objects.py` now builds catalog v3 by encrypting each plaintext part
independently, with a default and maximum 32 MiB part size. It no longer creates
a whole-file ciphertext temporary or reads 1 GiB chunks. Restore validates each
ciphertext part and plaintext part before appending into the atomic restore tree;
legacy v1/v2 split-ciphertext catalogs remain readable. Seven focused tests and
Ruff pass, including a v2 reconstruction case. This is source engineering only:
the live ARCA private Releases still lack payload objects, independent-key
restoration and HORREVM replication remain unproven, and no private original may
be retired. The builder now serializes captures per output root and refuses
stale hidden partial objects or a partial catalog left by a process crash.
On an ordinary exception it removes only partial files created by that
invocation, leaving the prior catalog untouched; committed orphan ciphertext
remains for custody investigation. A symlinked object directory is rejected.
Nine focused tests and Ruff pass, including interrupted-encryption cleanup
and stale-partial refusal. This is fail-closed interruption handling, not yet
durable same-snapshot resume. Bounded capture scheduling and the 1,000-asset
release ceiling still need operational proof.

### Legacy ARCA Git reconstruction checkpoint, 2026-09-25

The legacy ciphertext helper now stores exact raw commit/tree/tag objects from
the unpublished `origin/main..HEAD` range inside its encrypted catalog, verifying
each Git object ID before encryption. It records the embedded legacy manifest's
blob ID. An isolated reconstruction command fetches the catalog's exact base,
writes verified ciphertext blobs and raw Git metadata into a new bare repository,
requires `git fsck --strict` and exact recovered HEAD, then publishes the new
destination atomically. Four focused tests and Ruff pass, including a real-Git
divergence whose reconstructed commit ID matches the source and a malformed
asset-digest rejection. This reconstruction still depends on the exact base
remaining available from the supplied repository and covers this HEAD range,
not all local refs, stashes or historical metadata; full independent closure is
not yet proven.

The live ARCA source was clean, and its `origin/main` matched the freshly
advertised remote tip; GitHub immutable repository ID `1332536900` resolved to
the expected private owner. A local-only dry run produced an 8,505-byte,
mode-0600 encrypted catalog covering 59 ciphertext files and 5,389,255,296
bytes, with 60 planned Release assets including the catalog. The source vault
remained clean. No payload asset was uploaded and no remote readback, independent
key restoration, branch reconciliation or source retirement is claimed.

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

### ARCA fixed-catalog Release attempt, 2026-09-25

The Release publisher now has a 25-minute apply deadline and neutral per-asset
readback progress. A fixed-catalog resume command requires the exact source
HEAD, encrypted catalog SHA-256, ciphertext file count and byte total; it
refuses dirty or changed source files. Twelve focused ARCA tests, Ruff and diff
hygiene passed. Limen source commit `c4ecab47b` is pushed on draft PR #2718.

One bounded live apply used the pre-existing 8,505-byte encrypted catalog at
SHA-256 `b41047e0aa7d17ccc1f818c0d0698416b8c3ef106323658c9d59e192a4485549`
and source HEAD `22142cd82297cc90c0f15737134043db668e337b`.
The source preflight checked 59 committed ciphertext files totaling
5,389,255,296 bytes. GitHub private repository identity `1332536900` and the
release write preflight passed. Twenty-four assets uploaded and passed full
SHA-256 remote download/readback. The 25-minute deadline expired during
readback of the next object; a fresh GitHub listing showed 25 object assets
and zero catalog assets on the fixed release tag. The 25th object remains
unverified. The batch is incomplete, with no source retirement or custody
completion claim. A dry run of the committed resume command passed and returned
the same tag, 60 planned assets and 5,389,263,801 planned bytes. The local
encrypted catalog and source remain retained. Actual internal free space was
26,477,548 KiB (about 25.25 GiB), well below the 200 GiB target.

Next custody attempt resumes the same fixed tag and rechecks every present
asset by download, including the unverified 25th; upload remaining objects
and publish the encrypted catalog last. Independent-key restoration, second
replica, full Git ref/stash closure and CCE authorization remain open.

### ARCA digest-assisted continuation, 2026-09-25

The publisher now supports an explicit resume mode that checks GitHub's live
`uploaded` asset state, SHA-256 digest and size against the local ciphertext
for assets already on the fixed Release. New uploads still receive full
download/readback and SHA-256 verification. Missing or mismatched remote
metadata fails closed. Thirteen focused ARCA tests and Ruff passed. Source
commit `69df8451e` is pushed on draft Limen PR #2718.

A 10-minute continuation validated the existing 25 assets against server
digests and fully read back new assets through 38/60. Its deadline expired;
a fresh GitHub listing showed 38 objects and no catalog. A subsequent
six-minute continuation validated the existing 38 and fully read back new
assets through 46/60. Its deadline expired during the next object; a fresh
listing showed 47 objects and no catalog. Asset 47 is present but unverified
by the completed publisher flow. Neither batch published the encrypted
catalog. The fixed local source and catalog remain authoritative; no private
original was retired. The latest actual internal free space was 26,155,680
KiB (about 24.94 GiB), below the 200 GiB target.

The next bounded custody run must verify asset 47 and the remaining objects,
then publish the encrypted catalog last. This work is approaching the existing
120-agent-minute cumulative Limen execution allowance; the full original
outcome remains incomplete and requires an execution-budget decision before
additional heavy runs. Independent-key recovery, a second replica, complete
source closure, authorized private retrieval, full root classification and
physical capacity recovery are still unproved.

### Complete fixed ARCA Release batch, 2026-09-25

A further fixed-catalog, ten-minute continuation checked the 47 existing
objects against GitHub's live uploaded-state SHA-256 and size, then uploaded
and fully downloaded/read back the remaining 12 ciphertext objects. The
encrypted catalog uploaded last and passed full readback. The publisher
returned `state=verified`, 60 assets and 5,389,263,801 bytes for immutable
private repository ID `1332536900` and tag
`arca-objects-b41047e0aa7d17ccc1f818c0d0698416`.

An independent live GitHub API listing then confirmed 60 uploaded assets,
one encrypted catalog, SHA-256 digests on all assets, and the exact planned
byte total. The local ARCA checkout remained clean at original HEAD
`22142cd82297cc90c0f15737134043db668e337b`. This proves one complete
encrypted remote Release batch for this fixed legacy snapshot; it does not
prove independent-key decryption/restoration, second-replica custody, all
local refs/stashes, additive branch reconciliation, or coverage of other
private domains. No local private original was retired. Actual internal free
space was 25,524,248 KiB (about 24.34 GiB), still far below 200 GiB.

The cumulative agent execution has passed the global finite-work recovery
allowance of 120 minutes. Stop automatic heavy recovery work at this
checkpoint under `/Users/4jp/AGENTS.md`; retain the full goal as incomplete.

### Resumed deployment and key-recovery checkpoint, 2026-09-25

The user explicitly resumed autonomous tranches. The fixed ARCA Release still
lists 60 uploaded digest-bearing assets, including one encrypted catalog and
the exact planned byte total. The vault checkout is clean; internal free space
at restart was 25,125,420 KiB. The synthetic real-key `private-vault.py
recovery-check --apply` failed again: GPG lists a recipient-matching secret
subkey, but its agent cannot supply the decryption key in this noninteractive
session. A secret-subkey export diagnostic returned `Inappropriate ioctl for
device`, consistent with an unavailable interactive unlock. This is not an
independent restoration receipt; no source retirement follows.

Limen PR #2718 was conflicting and its Python CI failed on formatter drift.
Fetched main at `b0ca0d678`, merged it into the existing recovery branch,
preserved the process-group clone/fetch timeout, incorporated main's lease
record typing fix, and corrected the remaining typed reconcile result list.
Ruff lint/format, mypy across 190 modules, and 383 focused lifecycle,
dispatch and heartbeat tests passed locally. Merge commit `53d234adc` was
pushed; the PR is now mergeable and its new hosted checks were queued at the
first observation. It remains draft and unmerged pending hosted evidence and
the wider unfinished lifecycle acceptance. Domus #393 and PORTVS #12 remain
open at their prior exact heads; no unchanged-head merge retry was attempted.

### CI and installed-cache correction, 2026-09-25

The new hosted PR head exposed two further exact gates. Python CI rejected an
undeclared `LIMEN_REPO_RECONCILE_TIMEOUT` and the now-orphaned
`LIMEN_REAP_VERIFY_REMOTE` declaration. The parameter registry now declares
the bounded heartbeat timeout and removes the obsolete bypass knob; fresh
remote verification remains mandatory. PR Gate rejected the read-only
`refs/heads/main` fetch literal in the ARCA reconstruction helper as an
unclassified direct-main seam. The writer registry now classifies its exact
single read-only refspec. Local `check-params.py` and
`direct-main-writer-audit.py` both pass.

A current tool-cache census initially listed `~/.cache/codex-runtimes` as a
generic 1.6 GiB deletion candidate. That path contains the installed Codex
primary runtime, so the cache policy now assigns Domus installed-runtime
ownership and retains it. The first exact-plan apply failed closed on drift
before deletion. A subsequent fresh plan, with the runtime excluded, removed
only two regenerable caches totaling 355,496 KiB apparent; it retained all
active and owner-specific stores. Actual APFS free space rose from 25,125,420
to 25,180,896 KiB, a measured 55,476 KiB gain, so apparent bytes are not
credited as physical recovery. Twelve focused cache tests and Ruff passed.

The final-lease store path was audited against the existing clone reaper before
adding deletion. Its remote-object, ignored-payload, process and nested-store
checks do not yet preserve every local Git metadata byte (for example custom
repository configuration). A proposed managed-store deletion path was tested
in isolation, then withdrawn before publication because it did not satisfy
the plan's exact metadata-custody condition. Reconciliation now reports
`retained-store-metadata-custody-unproven` when every checkout is retired,
instead of presenting the canonical store as an unexplained permanent cache.
The store is not deleted. A focused test proves this retained state; seven
repository-lifecycle tests, mypy and Ruff pass. The required next step is a
shared metadata-preservation classifier with remote encrypted readback and
restoration evidence, followed by a locked final-store deletion edge.

### Owner-manifest merge receipts, 2026-09-25

Domus #393 was submitted once through the exact-head merge rail at
`3ad8eef85220f644a5e6728ba04b748a6000e1b3`; GitHub confirms `MERGED`
at `633a298f1b49676be03ff1a30bad60f4a7898e1b`. PORTVS #12 was
submitted once at `5e79f13d218bdf23dc708801f7481d71a2cae7b5`;
GitHub confirms `MERGED` at `a749437e62802f6ab553e93c8f68e475476bd5e2`.
These receipts deliver the owner manifests and Domus source adapters, not
installed host configuration or completed migration. Domus's current source
checkout has unrelated `.serena/project.yml` drift, so installation must use
the merged source without overwriting that local state. PORTVS's checked-out
source remains on its feature branch; synchronize the manifest consumer from
the verified merged main without moving an active runtime.

Limen #2718 remains draft and open at `a76733824a32d78252cdad8997b8ecfb44cba9b8`.
Its latest hosted Python, contract, worker and web checks passed; PR Gate and
Semgrep were still running at observation. No installed Limen runtime or
natural scheduled receipt is inferred from source CI.

The merged Domus source was applied through chezmoi only to three named host
targets: `~/.config/domus/home-surface.yaml`,
`~/.local/bin/domus-limen-runtime`, and
`~/.local/bin/domus-claude-vm-lifecycle`. A post-apply scoped chezmoi diff is
empty and both installed commands answer `--help`. The default Domus chezmoi
source checkout is on an older `master` with unrelated `.serena/project.yml`
drift; it was not reset or broadly applied. The scoped source was the clean
merged PR head. The new read-only VM classifier measured 10,619,207,680
allocated bytes for Claude's expanded image and 1,227,485,184 bytes for its
compressed base. Full base comparison reported equal logical size but unequal
content (`retained-divergent-expanded-image`); retirement authorization is
false and session data remains protected. This image contributes no verified
recoverable bytes yet.

### Managed acquisition admission, 2026-09-25

The `repo.ensure` entry point previously checked identity and serialized
acquisition but could create a new canonical clone below the existing worktree
free-space floor. It now consults Limen's live worktree admission snapshot
under the per-repository acquisition lock before a new store or checkout is
created. The snapshot resolves Limen's runtime root independently of caller
cwd. An unavailable snapshot fails closed. An existing active lease is still
opened idempotently under pressure after its canonical-store origin and
worktree identity are verified. Focused lifecycle tests (8), Ruff lint/format,
and mypy pass. This is admission protection, not a complete capacity
reservation: direct callers still need a measured byte claim and shared
machine reservation for the clone plus checkout. The existing cache-root
resolver already requires the canonical store and worktree to share one
filesystem; an unsafe different-volume cache fails closed.

The live admission snapshot after this change returned `block_new_local=true`,
22.82 GiB free, and an unavailable resource graph, so no new checkout was
attempted. The actual APFS free-space reading was 23,898,764 KiB at tranche
start; the 200 GiB completion criterion remains unmet.

The private home/Workspace inventory has 2,431 `bare_git_candidate` paths
under the two Codex-owned `.tmp` roots, far more than the earlier 320 observed
in one root. A bounded first-100 Git inspection found no refs, remotes,
resolvable HEADs, or pack files. A read-only full-cohort filesystem shape pass
found exactly one regular `HEAD` file per directory, no config or index, and
51,051 total file bytes across all 2,431 shells. These are Git-shaped empty
initialization shells, not demonstrated repository custody or meaningful
storage recovery. The count and shape are inventory evidence only; process
reference and current-state checks would still precede any retirement.

The inventory classifier now records this exact three-entry shell shape as
`codex_empty_git_shell_candidate` only under a Codex `.tmp` owner root. It
checks regular `HEAD`, empty `objects` and `refs`, and rejects populated stores;
the class itself grants no deletion authority. Resuming the private inventory
reclassified all 2,431 current shells, leaving 23 other bare Git candidates.
The root traversal has no frontier, but one cloud `TimeoutError` remains
unmeasured, so `complete=false`. Four inventory tests and Ruff pass. The
private 30 MB path-bearing state still needs encrypted remote custody; its
aggregate counts alone are safe for this public execution record.

The remaining 23 Git-store candidates now have a read-only owner grouping:
16 OpenCode recovery snapshots (49,612 KiB apparent), three nested submodule
stores (3,076 KiB), three pre-commit fixtures/cache stores (468 KiB), and one
local test remote (264 KiB). The OpenCode stores expose no remote, refs, or
valid HEAD through Git; the submodule and pre-commit stores contain live refs
and remotes. These findings explain the candidate count but do not prove
process ownership, reconstruction, or retirement eligibility. No member was
removed.

### Encrypted inventory snapshot custody, 2026-09-25

The current private inventory state (30,590,791 plaintext bytes) was captured
with ARCA's per-file encrypted-object pipeline. A hard link in an owner-private
capture directory fixes the source inode without duplicating plaintext blocks;
source digest validation passed during encryption. The private ARCA repository
`1332536900` received one opaque ciphertext object and one encrypted catalog
on tag `arca-objects-9bac65aa7962314a2d81b27e84dc398e`. The publisher
returned `state=verified`, two assets, and 2,611,964 ciphertext bytes after
full remote readback. An independent GitHub API listing confirms both uploaded
assets with SHA-256 digests and the exact byte total. No large object entered
Git. Sensitive paths, names, and indexes remain inside the encrypted catalog.
The plaintext state and linked fixed snapshot remain retained because the
independent-key restoration gate is still unavailable; this receipt proves one
encrypted remote copy, not complete private-data coverage or recoverability.

### Fish host parity and remaining migration gates, 2026-09-25

The running fish configuration still exported `WORKSPACE_ROOT` as Domus's
`projects` directory despite the merged Domus source declaring `~/Workspace`.
A scoped chezmoi render from merged Domus #393 used an explicit override for
chezmoi's active source directory, keeping `DOMUS_ROOT` on the existing
checkout rather than the temporary PR worktree. The only applied target was
`~/.config/fish/conf.d/15-env.fish`. Post-apply scoped diff is empty; native
fish now resolves `WORKSPACE_ROOT=~/Workspace` and the three control roots to
their declared current paths. Five repository-root shell tests pass. The
default Domus chezmoi source checkout remains on divergent `master` with
unrelated local drift, so a broad future apply could regress this installed
fish surface. Source-root reconciliation needs unique-commit/dirty-state
custody and an active-consumer drain before changing chezmoi's sourceDir.

PORTVS's merged bootstrap, run in read-only plan mode against the literal
Workspace root, reports no safe additive actions. The Domus and PORTVS
canonical paths are absent while legacy sources remain active; the Limen
canonical path is an existing non-repository directory containing logs. Its
compatibility links remain blocked by those canonical states. No control
repository was moved or cloned below the live admission floor. GPG's current
agent lists the recipient-matching secret subkey, but noninteractive loopback
decryption of the encrypted inventory catalog fails with `No passphrase given`.
This confirms that independent restoration still requires a sanctioned key
unlock path; no private original is retired.

The divergent Domus `master` source has exactly one commit absent from merged
`main`, adding six OpenCode theme JSON files; `master` matches its remote. The
existing merged Domus worktree was reused (no new checkout) to cherry-pick
that exact commit onto current main as `aba45318eb2951e04e1284b8fcc1cfa94c2fbf35`.
All six JSON files parse and diff hygiene passes. PR #394 is open, mergeable,
and labeled `lifecycle:delivery`; its one exact-head merge-rail submission
returned `DEFERRED — CI-PENDING`. No unchanged-head retry or merge claim
follows. The default Domus checkout's `.serena/project.yml` drift remains
untouched, and sourceDir migration waits for this PR's merge receipt plus a
fresh active-consumer/custody check.

Read-only host verification finds immutable Limen runtime
`9be6f0d76d6623ec37ecb56510ec2ed77debae11` installed and selected.
The installed Domus verifier returns `verified=true`, `status=passed`, matching
runtime/launcher/interpreter digests, no surviving child process, heartbeat
label present and watchdog absent. Launchd reports 84 invocations and last
exit code zero for the selected runtime. This supports current installed-job
health; it does not demonstrate the still-draft #2718 source has been
installed, nor by itself prove the required natural execution receipt for
that future runtime. The Data volume currently lists 12 purgeable local Time
Machine snapshots. They remain protected under the plan, and their apparent
retention is not credited as recoverable free space. Current actual free
space is 23,728,532 KiB, well below the 200 GiB target.

### Allocated-space owner census, 2026-09-25

A bounded same-filesystem `du` pass, excluding CloudStorage traversal, measured
220,415,164 KiB under home and 65,544,716 KiB under Workspace. Major home
areas are Library 88,968,768 KiB, `.cache` 18,878,024 KiB, Pictures
14,194,564 KiB, `.arca-vault` 11,968,156 KiB, and `.local` 9,008,872 KiB.
Within Library, Application Support uses 18,975,368 KiB, Caches 14,445,792
KiB, Containers 13,108,232 KiB, Group Containers 11,795,964 KiB, Messages
10,637,572 KiB, and Mobile Documents 9,291,336 KiB. Within Workspace,
Limen uses 32,138,232 KiB. These are allocated directory measurements,
not independent reclaim estimates; APFS sharing and protected snapshots can
prevent apparent deletion from raising `df` free space.

The current cache reclaimer found only 436,048 KiB of policy-eligible caches.
The large 11,398,160 KiB `uv` cache is actively referenced by eight observed
processes and remains retained. The 1,638,064 KiB Codex runtime cache is
Domus-owned installed infrastructure, not generic cache. No large cache
cleanup was attempted. The verified cold-storage drive is not attached;
`/Volumes` shows only internal and local-snapshot mounts. Drive-dependent
replication and retirement wait for attachment while source engineering
continues.

CCE's configured corpus doorway still reaches the original private corpus,
but the installed `/opt/homebrew/bin/cce` entry point fails before search
because its Python package is absent. Domus's `cce-refresh` wrapper still
points to a vanished `~/Code/organvm/conversation-corpus-engine` checkout and
silently skips refresh. The remote repository resolves by immutable GitHub ID
`1188128304`, but new local acquisition is denied by current host admission.
This is an explicit unavailable retrieval state, not an authorized CCE search
receipt.

Further bounded Limen ownership measurement locates 15,137,856 KiB in its
agent runtime: Codex 9,631,992 KiB, OpenCode 3,505,432 KiB, and Claude
2,000,352 KiB. Codex includes 6,194,512 KiB of sessions plus live root-level
SQLite application state, including approximately 1.64 GB allocated to thread
history and 654 MB to logs. These databases require consistent backup/export
adapters and verified encrypted custody before any local retirement; their
presence is not generic cache. `~/Library/Caches` totals 14,445,792 KiB;
CloudKit alone uses 5,147,864 KiB and remains application-owned. The
separately measured `~/.cache/uv` remains active and retained. These figures
locate the deficit but do not add to an APFS-free-space recovery claim.

### Active SQLite capture canary, 2026-09-25

Limen now has a bounded, no-overwrite SQLite online-backup adapter for active
application databases. It requires a private real output directory, captures
through SQLite's backup API, seals the output into DELETE journal mode, checks
integrity and source-path identity, fsyncs, and publishes the snapshot by an
atomic no-replace hard link. A timeout or interruption retains the private
partial and never emits a completed snapshot. Three focused tests cover WAL
content, private mode/no overwrite, invalid source/partial, and deadline
retention; Ruff lint/format pass.

The first live small Codex `goals_1.sqlite` canary exposed a real sidecar bug:
the read-only integrity connection left zero-byte WAL and SHM companion files
beside the snapshot. That local-only capture was not published. The adapter
now seals the journal and uses an immutable integrity reader, refusing to
publish if sidecars remain. A second live canary yielded one 49,152-byte
integrity-checked snapshot and no sidecars. ARCA encrypted it as one object
plus an encrypted catalog; the private Release publisher fully read back both
assets (`state=verified`, 8,524 ciphertext bytes) on tag
`arca-objects-b05cc60b39c5b885817dcea36109b0a2`. An independent GitHub
listing confirms both uploaded digest-bearing assets. The original Codex
database, both private local canary directories, and all larger databases
remain retained. This proves consistent encrypted remote capture for one
small active SQLite source, not independent-key restoration or estate-wide
database coverage.

Tranche close measurement: Data-volume free space is 22,260,588 KiB
(approximately 21.2 GiB), lower than the prior sample. The cause of the
concurrent change is unmeasured; neither the small canary nor apparent cache
sizes are claimed as net recovery. Limen #2718 remains draft/open at
`9fc22675029c73e60737cdb03992f5b214bca7cc`, with no observed failed
hosted checks and Python/PR Gate/Semgrep still pending. Domus #394 remains
open and clean at its already-submitted head; all observed checks are green,
but its exact-head merge rail previously returned `DEFERRED — CI-PENDING` and
has not returned a merge receipt. Do not promote either source PR to installed
or merged status without the respective receipt.

### CCE catalog and refresh wiring, 2026-09-25

PORTVS registered `organvm-i-theoria/conversation-corpus-engine` as a
remote-default repository under immutable GitHub ID `1188128304`, retaining
the old path only as a discovery alias. Seventy PORTVS bootstrap tests passed;
its read-only plan took no clone action because the host's control-root
migration remains gated. PR #13 merged through Limen's exact-head rail at
`c4e8023c95fd3409f94f10d6a8a600c116203e79`.

Domus PR #395 now replaces the vanished-path silent-success CCE refresh
wrapper with Limen `repo ensure`/`repo release` around the scheduled script.
Two local lease/admission tests pass, as do syntax and commit hooks. Hosted
Shell Formatting failed on a here-string spacing difference; `shfmt -i 2 -ci`
corrected it, the two tests reran green, and the fix was pushed. The PR is
open at `37bf9cbdfc8533efc646f5a9b83275a487f9d634`; its one exact-head
merge-rail submission returned `DEFERRED — CI-PENDING`, with no retry. The source is not
installed, and Limen #2718 remains draft/uninstalled. The repair therefore
does not yet establish working CCE search or a natural scheduled refresh
receipt. The separate source-root theme PR #394 remains open; its earlier
exact-head submission was deferred and has not been retried. Current actual
Data-volume free space is 22,038,536 KiB (~21.0 GiB); no physical recovery
is claimed from these source changes.

Subsequent GitHub observation shows every named #395 hosted check successful,
including Python tests, shell formatting, CI, secret scanning and Semgrep.
It remains open at the same head; the single deferred merge submission is
not a merge receipt. #394 likewise remains open with named checks green.

### Shared acquisition capacity reservation, 2026-09-25

The draft Limen `repo.ensure` source now reserves measured checkout room under
the same machine admission lock and durable lease registry used by dispatch.
Dispatch hands its already-selected lease to `ensure`; the latter verifies its
current process, state, shape and a fresh host admission snapshot without
double-counting it. Direct callers reserve their own disk promise until the
bare canonical store, requested revision and isolated worktree are materialized
or the attempt fails. A confirmed dead process is handled by the existing
admission-lease reaper. The live GitHub tree estimate now uses the requested
revision, and gitlinks fail closed because their nested bytes are not measured.
New canonical stores use a bare clone, avoiding a redundant default checkout.

The full repository lifecycle and dispatcher tests passed (366 cases); focused
tests for concurrent room promises, inherited-lease validation, requested-ref
measurement and submodule denial passed after the final edit. No live checkout
was created because current host free space remains below admission. The draft
runtime is not installed; LFS acquisition sizing and final canonical-store
metadata custody still require engineering and acceptance proof.

The hosted Python check on the first reservation head failed mypy because
the direct path passed a lightweight coordinate holder to a Task-typed
estimator. The estimator now accepts the repository coordinate explicitly,
and dispatch retains a Task wrapper. The exact hosted type-check command
`python3 -m mypy src/limen/` passes locally for all 190 source files; 15
focused lifecycle/dispatcher tests pass after the correction. Hosted CI on
the corrected head remains a separate receipt.

### Application Git-store owner policies, 2026-09-25

Domus PR #396 adds retain-and-investigate lifecycle rows for the observed
OpenCode recovery snapshot roots, pre-commit fixture cache, two parent-owned
submodule stores, and local test remote. A private inventory-to-policy prefix
check matched all 23 remaining non-Codex bare Git candidates (23/23), and the
home-guard suite passed 37 tests. The policy does not classify every home or
Workspace object and grants no retirement authority; each candidate still
needs fresh native owner, process, exact-ref and payload custody evidence.
The PR is source-only and has not been deployed.
Its exact head is `f88a195b954e17d71842f8f41a4f5e63587c3d4f`; one
merge-rail submission returned `DEFERRED — CI-PENDING`. No unchanged-head
retry or merge claim follows.

### Source-context inventory refinement, 2026-09-25

The read-only home/Workspace inventory now distinguishes marker-bearing
source directories nested in Git checkouts, dependency caches, application
state and caches from independent copied-source candidates. Resuming the
private state with no new traversal changed the 16,257 ambiguous source
markers into 13,278 dependency, 1,646 repository-internal, 1,258 application,
61 cache and 14 copied-source candidates. Five focused tests and Ruff pass.
This is contextual classification, not exact owner/custody proof or retirement
authority. The scan still has no frontier and one cloud-trash TimeoutError;
`complete=false` remains correct.

One roughly 32 MiB copied public-repository tree has no Git metadata. A
bounded live remote-tree comparison found 66 exact path/blob pairs, 513 local
paths absent remotely and 72 content mismatches after excluding generated
dependency/build directories. It is retained as unique local work pending
candidate-specific preservation; remote repository existence is not custody
for those unmatched files. The path-bearing current inventory snapshot is
encrypted in one object plus catalog and was verified by private Release
readback at neutral tag `arca-objects-7c001c63a86cf4b490c3962e3da4f217`
(two assets, 2,617,319 ciphertext bytes). The local inventory and source copy
remain. An earlier intermediate classification snapshot is separately retained
at tag `arca-objects-637ca60b28571111d8eb2a7269b9fc57`.

### Bounded cache retirement, 2026-09-25

The current cache classifier produced exact plan
`2b8b6e1af5af10d15dcbdf7b6415c6be9071231f02159b6cb3c17645c47ccf91`
with four inactive policy-eligible tool caches. Applying that unchanged plan
removed `~/.cache/npm`, `~/.npm/_cacache`, Homebrew cache, and node-gyp
cache (436,048 KiB apparent allocation); the recheck found zero residual
candidates. Agent state, installed runtimes, live caches, private records,
worktrees, and recovery stores stayed excluded. Data-volume `df` free space
was 22,013,264 KiB immediately before and 22,009,092 KiB afterward, so
this is **not** counted as physical recovery. The concurrent difference is
unattributed; APFS snapshots/sharing and other writers remain possible.

### Active AI database encrypted cohorts, 2026-09-25

Two additional live Codex SQLite databases were captured with the consistent
online-backup adapter. Cohort A is 648,474,624 snapshot bytes; its encrypted
catalog and 20 ciphertext objects (121,697,407 bytes in total) passed complete
private GitHub Release readback at neutral tag
`arca-objects-91dcf395651ab93e28542af05eb0d406`. Cohort B is
1,641,095,168 snapshot bytes; its encrypted catalog and 49 ciphertext objects
(503,227,751 bytes in total) passed complete readback at neutral tag
`arca-objects-789f8f978a33394d9c9c7e246dbde720`. Independent `gh api`
listings confirmed exactly 21 and 50 remote assets and the corresponding
ciphertext byte totals. The repository is private; its releases are published
inside that private repository. Names and source paths remain in encrypted
catalogs, not public asset names.

These are point-in-time encrypted remote captures, not independent-key restore
or continuing coverage of mutable databases. Both native databases and the
owner-private local captures remain. The capture/upload work consumed local
space: current Data-volume free space is 19,073,576 KiB (~18.2 GiB), further
from the 200 GiB target. No private original or capture has been retired.

### Bounded small-object publication, 2026-09-25

The ARCA Release publisher now groups up to 16 new encrypted objects and
128 MiB per authorized `gh release upload` call. It checks source digests
before upload, downloads each bounded batch in one call, checks each object
digest independently, and publishes
the encrypted catalog only after object verification. Existing digest-addressed
assets remain reusable; interrupted uploads retain the local ciphertext and
resume from the remote asset list. Cohorts above GitHub's 1,000-asset
per-release limit now use deterministic object-shard releases of at most
1,000 assets each. The final release contains only the encrypted catalog and
is created after every object shard passes readback. The observed 2,062-file
copied source tree is therefore structurally publishable. It was captured
locally as 2,062 independently encrypted objects plus one encrypted catalog;
remote publication, independent restoration, and retirement remain pending.
The publisher accepts an object directory to avoid oversized command lines,
and its cross-release reuse index includes shard tags. The first live publish
verified shard one (1,000 objects) and 512 objects in shard two, then a GitHub
upload command failed. A digest-assisted resume confirmed all 1,512 existing
assets but failed at the same next upload. GitHub's reported core rate budget
was 5,000 and the release was not immutable; the precise upload rejection was
not exposed by the former generic error. The publisher now reports only a
bounded, neutral error category. A corrective retry with one object per upload,
after digest-checking all 1,512 existing objects, returned **HTTP 403** on the
same next object. That is a remote mutation denial, not evidence that the
16-object batch is too large. Do not retry unchanged inputs; investigate the
GitHub response and account/repository upload policy before resuming.
Shard three and
the final catalog release do not exist, so this copied source tree does **not**
have complete remote custody. The source and all local ciphertext remain.
Seventeen focused publisher
test cases, Ruff, and the
outbound preflight guard passed. This reduces per-object authorization and
upload overhead for small-file cohorts; it does not establish whole-estate
custody, independent-key restoration, or the 200 GiB free-space target.

### PR gate merge-tree repair, 2026-09-25

Draft PR #2718's hosted `pr-gate` failed one of 8,173 CLI tests: the live
effector scanner found 23 entries while the branch baseline retained 25. The
two stale entries named in-process POST and PUT in `consolidate-github.py`.
That file had changed on `main` after this branch diverged and had no
branch-local edits. The branch now carries the exact `origin/main` version of
that file and a baseline with only the two no-longer-live entries removed.
The focused effector suite passed 44 tests and `check-effectors.py` reports
23 baselined findings with no new finding. A fresh hosted merge-tree result
is still required; no merge or installation is claimed.

### Copied-source encrypted remote custody, 2026-09-25

The prior HTTP 403 did not recur after external time advanced; its cause is
unproven, so no rate-limit diagnosis is claimed. The publisher now classifies
provider failures without exposing response bodies or source paths. The
2,062-file local capture resumed from 1,512 existing objects and completed
remote readback of every encrypted object plus the final catalog. Independent
private GitHub API listings show shard counts of 1,000, 1,000, and 62 objects,
then one catalog asset, totaling 7,711,545 ciphertext bytes. The catalog's
remote uploaded-state SHA-256 matches the local ciphertext exactly. Neutral
final tag: `arca-objects-989085af4e956a7c8fb08095669b720f`.

This is complete encrypted remote custody for the captured point-in-time tree.
The source and local encrypted capture remain because independent-key restore,
an independent cold replica, and source-currentness/ownership review remain
unverified. Internal Data-volume free space after publication is 21,846,640
KiB (~20.8 GiB), not the 200 GiB target.

### Physical storage attribution and cache-owner check, 2026-09-25

The latest read-only Data-volume measurement showed 21,271,404 KiB
(~20.3 GiB) available. APFS reported 21 local Time Machine snapshots;
they remain protected. Snapshot listings do not provide attributable physical
sizes, so no apparent directory total is treated as reclaimable capacity.
Read-only allocated-size measurements were ~212.8 GiB under home, including
~65.3 GiB under Workspace and ~84.7 GiB under Library. The home cache tree
was ~17.9 GiB and Library/Caches ~13.6 GiB, but these include active tools,
application state, and protected private material.

The owner-aware cache classifier checked 27 allowlisted paths using current
process/file references. It found two tiny eligible npm caches totaling only
284 KiB. Seven entries were blocked; notably the ~11.1 GiB uv cache and
~1.64 GiB Playwright browser cache had active process references. The
~1.56 GiB Codex runtime cache is excluded under Domus's installed-runtime
policy. No cache, snapshot, private store, or repository was retired in this
tranche. The 200 GiB target remains unmet; the measured deficit is roughly
180 GiB, with physical attribution limited by APFS sharing and snapshot
accounting. Next eligible recovery requires owner-specific reconstruction and
custody evidence, not size-based deletion.

### Released-dirty lease reconciliation finding, 2026-09-25

Source audit of `repo_lifecycle.release` and `reconcile` found a lifecycle
stall: release records a dirty or unavailable checkout as
`retained-dirty-or-unavailable`, but the bounded background reconciler only
processes `released-awaiting-custody-investigation`. A later owner-preserved,
clean checkout therefore cannot automatically re-enter retirement review.
The next correction must revalidate actual worktree identity, exact HEAD,
status including ignored payloads, process ownership and live remote custody
before transitioning that lease to review; an expired lease or a clean status
alone cannot authorize deletion. The final canonical store still has no
metadata/object-custody proof and remains retained after checkout retirement.

### Selective ciphertext hydration foundation, 2026-09-25

Limen's ARCA Release adapter now has an internal `hydrate_ciphertext`
primitive. It accepts a verified private repository ID, a completed encrypted
catalog digest, selected object ciphertext digests, and an existing private
destination. It resolves the current repository identity, checks the final
catalog marker, requires uploaded-state remote SHA-256 and size for each
asset, fetches only the requested ciphertext, verifies downloaded bytes, and
never overwrites differing local bytes. It neither decrypts nor emits private
names or paths. Nineteen focused Release-adapter tests and Ruff check passed.
The files had pre-existing Ruff-format differences; broad formatting was not
applied to this scoped change.

This is byte transport, not authorized CCE retrieval. The current installed
`cce` package remains unavailable, its registered source is remote-only, and
host admission remains below 50 GiB. The CCE caller/destination authorization,
encrypted registry mapping, derived index, provenance, and positive/negative
native search canaries are still required before any private result is emitted.

### LFS admission safety, 2026-09-25

The remote checkout estimator previously treated an LFS pointer's small Git
blob size as the materialized checkout size. It now reads tracked
`.gitattributes` blobs from the requested GitHub tree, validates their
encoding and size, and returns unknown capacity if an LFS filter is present
or the attributes cannot be verified. Ordinary non-LFS attributes remain
admissible. This is a fail-closed interim guard; measuring LFS object sizes
and proving their custody before checkout retirement remain open. Six focused
admission tests and mypy on `dispatch.py` pass. Broad Ruff on the existing
large dispatch/test files reports pre-existing findings and is not a green
gate for this head.

A live read-only hydration canary resolved private repository ID
`1332536900` and catalog digest
`989085af4e956a7c8fb08095669b720fab1b638c5cbba694acdb78e191b00b36`.
It fetched the completed encrypted catalog and one selected encrypted object
into a new owner-private directory, verified remote metadata and downloaded
bytes, and returned `state=verified`, `asset_count=2`. No decryption, source
retirement, or native CCE search occurred.
