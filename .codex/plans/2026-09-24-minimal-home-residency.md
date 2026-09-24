# Minimal home and Workspace: execution record

Owner: Limen recovery; direct user request 2026-09-24. Active checkout is the existing clean recovery lane, PR #2709. PRDS and all internal snapshots remain protected. No retirement without exact remote custody, and private originals additionally require encrypted restore proof. No new paid services.

## Intended outcome

PORTVS owns repository identity, canonical locations and residency; Domus owns home/runtime/hook configuration; Limen owns acquire/lease/preserve/release/retire; ARCA/HORREVM own encrypted custody and independent replicas; CCE owns authorized retrieval. Keep control repositories resident, protect PRDS; other authored repositories default to remote entries.

## Acceptance ledger

- [ ] One repo.ensure/repo.release interface, immutable GitHub identity, per-repository serialization, session idempotency, isolated worktrees, routed producers and lease-aware final retirement.
- [ ] One evidence classifier for reporting and deletion; fresh exact HEAD/ref/path/process/lease/private-payload evidence; stashes, metadata, ignored files, LFS and submodules preserved. No age or patch-equivalence deletion authority.
- [ ] Classify home and Workspace, hidden/nested/bare/application Git stores, copied source, symlinks, mounts, placeholders and unreadable areas. Assign owner, canonical location, residency reason and custody policy. Classify the reported 320 Codex bare stores.
- [ ] Preserve ARCA divergent history and ciphertext on an additive remote branch with readback; reconcile both histories.
- [ ] Incremental encrypted objects/catalog, private provenance, independent key recovery, consistent active database adapters, complete source coverage; retain legacy readers and ciphertext through restore acceptance.
- [ ] CCE registry-backed authorized retrieval, one derived index, configured paths, provenance and explicit unavailable states.
- [ ] Repair PR #2709, merge through rail, install immutable runtime; protect scheduled references from pruning and observe natural scheduled heartbeat execution and rollback.
- [ ] Bounded event hooks with one-second deadline and sub-250ms normal capture; scoped admission preserving reads; native Codex/Claude canaries; effective secret-scanning and LFS hooks.
- [ ] Extend Domus/PORTVS manifests; consolidate idle copies only with custody; drain active leases; explicit compatibility-link consumers and expiry; bounded drift reconciliation.
- [ ] Correct cache ownership, preserve required runtimes/environments; Claude VM reconstruction and cold-start proof before retirement; storage-domain reservations retain 50/200 GiB limits.
- [ ] Actual internal free space approximately 200 GiB, independently measured without APFS double counting; ordinary start/finish returns residency to baseline.

## Attempt 1

Bound: 30 minutes including at most 10 minutes verification under finite-workspace-recovery.md; one recovery writer, no agent fanout. Initial live PR #2709 head 652f6220fcfac1dbcab4a4242061f913a9cfbe04. Latest CI: 8090 tests passed, three failures (two reservation-order expectations and one missing-path fixture). Scope of this attempt: restore the recovery delivery rail and repair unsafe identity/proof boundaries. Wider acceptance remains open until exercised.

Observed: dispatcher selected basename candidates without verifying origin and finally returned the first mismatched candidate. Worktree planner emits provider refs but purge consumer still requires refs/remotes, a namespace mismatch. No deletion authorized by this document alone; use live predicates.


### Implemented boundaries and live observations

- Dispatcher discovery and clone reuse now require an exact GitHub origin coordinate. Basename and substring fallbacks are removed; non-GitHub lookalike hosts are rejected. Explicit local paths remain caller-authorized. Immutable-ID resolution across renames/transfers remains open.
- Remote clone purge accepts provider-advertised heads/tags/pull refs, rejects local tracking refs and malformed evidence, and requires the fresh content-probe callback before mutation. Existing planner/consumer path revalidation remains in force.
- PR #2709 reservation-order expectations reflect worktree admission before branch growth; missing sibling registration is retained, while genuine resolution errors still fail closed.
- Domus scheduled runtime guard is committed as 32602908 on fix/runtime-scheduled-retention-20260924; 49 installer tests and commit secret scanning passed. This lives in the existing recovery worktree; no new checkout was materialized.
- Live heartbeat: loaded but executable and working directory absent; 55 runs, last exit 78 EX_CONFIG. No successful scheduled receipt claimed.
- No external custody drive attached. Internal Data volume: 33,664,596 KiB available (32.1 GiB), about 167.9 GiB below target. No physical reclamation performed. PRDS, private originals and snapshots retained.
- Network routing briefly failed, then Git remote readback and Domus push succeeded. Earlier memory-derived capacity reports were not used as current evidence.

### Verification

Static scoped batch passed all 13 gates. Final dispatch shard: 353 passed. Final abandonment/Jules shards: 37 passed. Broader scoped Python verification outcome is recorded below when available. Full residency, encrypted custody, home classification, CCE authorization, hook canaries and storage recovery remain incomplete; none is inferred from these focused repairs.


### Attempt checkpoint

Limen code commit: `91aabc423` on PR https://github.com/4444J99/limen/pull/2709. Domus code commit: `32602908129de15a061c4dffe8c9a4b687b3e1d0`, pushed and published as https://github.com/4444J99/domus-genoma/pull/393. Its one allowed merge-drain submission returned `DEFERRED — LIFECYCLE-UNKNOWN`; no second submission or polling performed.

Broad scoped command: `bash scripts/verify-scoped.sh --base 652f6220fcfac1dbcab4a4242061f913a9cfbe04 --total-timeout-seconds 490 --gate-timeout-seconds 460 --jobs 2`. All 13 cheap gates passed. `pytest-cli` reached 99% with no printed failure before its 460.09-second hard timeout; overall command exited 1. This is incomplete verification, not a pass. Subsequent API verification wave did not run. A prior formatting failure was corrected once. Final narrow shards separately passed (353 dispatch, 37 abandonment/Jules); Domus 49 passed. No full-suite retry is authorized merely to reset the finite verification allowance.

Disposition: both working copies retained as control/recovery infrastructure with pushed source custody. No branch, clone, worktree, private original, application store, cache or snapshot was retired in this attempt. No immutable runtime installation, activation, rollback proof or natural scheduled-success receipt. The known loaded heartbeat still references missing files; source guard is published, not deployed.

Continuation is owned by this ledger and the two PRs. Observe the current exact-head PR #2709 result once on a subsequent authorized attempt; if passing, use the registry-declared exact-head merge rail, then `domus-limen-runtime plan-heartbeat --sha <merged-sha>` and its digest-bound activation command. Preserve Domus #393 deferred status until its owning lifecycle rail resolves it. Do not infer merge from this publication or start another CI waiter. After installation, require natural scheduled execution and rollback receipts. Then implement immutable repository-ID resolution and the lease-based ensure/release interface, route existing producers, and proceed through the remaining acceptance ledger. Private custody and CCE work must keep the user's encrypted-original/independent-key restoration gate; drive-dependent capture waits for attachment while independent engineering may continue within the original cumulative allowance.


### Codex temporary-store census, 19:37 UTC

Read-only inventory resolved the configured Codex runtime root and inspected only its two temporary surfaces without following directory symlinks. Deduplication by filesystem device/inode found **2,085 Git administration stores**, not the plan's historical 320 bare-repository count. Git reported none as bare; configuration inspection independently classified all 2,085 as non-bare administration with no explicit core.worktree declaration. Three have origin configured and are named `.git`; 2,082 have no origin configured and use other administration names. Both bounded probes completed without reported errors. These observations do not prove HEAD/refs/content custody, ownership leases, or disposability. All stores remain retained under the Codex application-owner boundary. This is a scoped temporary-store census, not complete home/Workspace classification.

Final capacity sample after verification: Data volume available **29,088,724 KiB (27.7 GiB)**. This supersedes the earlier 32.1 GiB observation. The cause of the concurrent decline is unmeasured; no net storage recovery is claimed. The approximately 200 GiB acceptance criterion remains unmet. Final code checkouts are clean and retained; remote publication is verified by exact branch SHA readback.


## Attempt 2: immutable identity and residency entry points

User explicitly continued autonomous execution at 19:42 UTC on 2026-09-24. Recovery remains within the original approved outcome and cumulative allowance. Domus PR #393 was reviewed live at its corrected exact head `57f502425d8dc8084939f40eb12c06d2c536afb5`; the prior run's only failure was Python lint E501. Wrapped the error path and pushed a new head. Focused installer suite (49) and the same Python lint predicate pass locally. Its new remote run was queued at the last observation; no CI waiter was started.

Limen identity tranche adds a 12-second bounded authenticated GitHub API lookup for repository IDs, caches only successful IDs for the process, and fails closed during offline/error results. Exact coordinate matches need no network. The existing identity registry supplies known old-coordinate search paths, and dispatch compares different owner/name coordinates by immutable ID. This supports registered aliases and repositories that retain a same-name path after transfer. The current registry covers only eight repositories; expanding it under PORTVS ownership and locating unregistered renamed checkouts remain open.

Verification: Ruff passed; `test_dispatch.py` plus `test_repository_identity.py` passed 360 tests. New tests cover old/new coordinates with matching IDs and offline failure. No new checkout or repo copy was created. Lease-based `repo.ensure/repo.release` and producer routing remain in progress.

### Session-scoped residency entry points

Added `limen repo ensure <repository-id> <revision> <session-id>` and `limen repo release <lease-id>`. Ensure resolves the live canonical coordinate through GitHub's immutable numeric-ID endpoint, serializes cross-process acquisition with `flock`, creates an ID-keyed canonical clone, and uses the crash-visible worktree initializer for an isolated checkout. Lease filenames contain only a session digest; repeated active acquisition for the same repository/session/revision returns the same worktree. Distinct sessions receive distinct linked worktrees. Release records dirty/unavailable work as retained and clean work as awaiting custody investigation; it never deletes a checkout or canonical store. Reacquisition under a released session ID is rejected.

Verification: lifecycle tests (2) pass, including repeated ensure, two-session isolation, single-lease release with another session retained, dirty payload retention, and immutable-ID input validation. The lifecycle, dispatcher and identity suites passed together at 362 tests in 81.74s before the final bounded exception/path-validation refinements; lifecycle tests (2), Ruff on new source/tests, CLI `repo --help`, import-order correction, and `git diff --check` pass after those refinements. The new API is not yet routed through dispatcher/editor/opener producers. Release intentionally stops at investigation until process, private payload, ignored/LFS/submodule and exact remote custody predicates are integrated. Canonical-store final retirement, lease expiry investigation, concurrent-process stress, and full user-root classification remain open.

## Attempt 3: merged control plane and heartbeat audit bound

PR #2709 exact head `50402d1109635a5c407acf3eac1709c8fd3c3c6c` merged through the declared Limen single-owner fast lane as `a77aa0375b10091bb5c74bbdc063a899e569b013`. The immutable runtime was installed and the digest-bound heartbeat plan was created. Two guarded activation attempts fired a one-shot that emitted a `passed` public receipt for the reviewed runtime, then failed post-fire verification and rolled back. The first error hid its failed fields; the updated Domus verifier in PR #393 identified `audit_limit_exceeded`. The live audit stream was 301,321 bytes against the 262,144-byte contract maximum. The transaction preserved its attempted plist in quarantine and restored the current pointer to the reviewed immutable runtime. The old activation receipt still names the prior runtime and is not evidence of current activation. No natural scheduled success is claimed.

Limen follow-up `fix/heartbeat-audit-bound-20260924` rotates the audit stream before an append would exceed 262,144 bytes. It preserves each displaced exact byte stream in a content-addressed history file with digest/readback collision checks; an oversized single event is likewise preserved and leaves an empty bounded active stream. It rejects symlink or non-regular audit/history paths. This addresses the measured verification failure without truncating or replacing evidence. Verification after this change: heartbeat supervisor suite 21 passed; scoped Ruff `--select E,F,W` and `git diff --check` passed. Not yet committed, merged, installed, or exercised through a natural scheduled execution. Domus PR #393 updated to `e31ee1cc062a8ef4b0e6677e07512b2b06f77281`; its one exact-head merge-rail submission returned `DEFERRED — LIFECYCLE-UNKNOWN`. No resubmission or CI wait.

PORTVS ownership inspection used the live `origin/main` manifest because the local main checkout is five commits behind. That owner already declares physical Workspace rows, remote refs, private-custody references, ephemeral roots, and expiring compatibility links. Its bootstrap treats repository rows as materialization destinations, so on-demand residency semantics need a designed schema extension and must be changed from a PORTVS-owned branch/worktree under its current instructions. No PORTVS file was changed. Home/Workspace full inventory, identity registry expansion, private encrypted custody, CCE, producer routing, cache/VM recovery, and the 200 GiB storage target remain incomplete.

### Follow-up receipts

The bounded audit fix merged as PR #2715 at `9be6f0d76d6623ec37ecb56510ec2ed77debae11`. Domus installed it, created plan `073ae699a0c52643ac82009adec807829877c36810dc311c29411283e9525d0d`, and activated the exact digest-bound heartbeat. Activation receipt status is `activated`; embedded verification status is `passed`, label `present`, watchdog `absent`, zero surviving processes, and active audit 955/262,144 bytes. Independent `verify-heartbeat` also passed. A content-addressed audit history object of 302,275 bytes passed SHA-256 filename/readback verification; no prior audit bytes were discarded. The five-minute natural scheduled execution receipt is still pending and must be observed before scheduler acceptance.

Read-only home census excluded the nested Workspace root and stopped at PORTVS's declared 250,000-entry scan ceiling: 250,014 entries observed, 48,804 directories, 198,720 files, 4 `.git` admin directories, 3 bare-repository-shaped candidates, 1,786 symlink entries not followed, no stat errors, and 701 queued directories left unmeasured. Separate Workspace census hit the same entry ceiling: 250,008 entries, 29,719 directories, 219,685 files, 42 `.git` admin directories, 29 linked-worktree `.git` files, 507 hidden directories, 434 symlinks not followed, no stat errors, and 129 queued directories. These bounded counts are not complete classification; no candidate names, contents, paths, or material were changed. The earlier targeted Codex temporary-store census remains 2,085 administration stores, all retained.

The lifecycle API's worktree destination was aligned with `effective_worktree_root()` so cache and isolated checkout placement obey the same live Domus/Limen storage-domain authority; release validates against that same root. Lifecycle tests remain green (2) and Ruff/diff checks pass. Repository producer routing remains unimplemented; this corrects destination ownership for explicit `repo ensure` calls only.

Limen PR #2716 merged at `01e27b138c955ecae6a3fdc900be4c5afb54382a`. A natural LaunchAgent interval has now been observed after activation: the public receipt at `2026-09-24T20:24:02Z` reports `passed` for runtime `9be6f0d76d6623ec37ecb56510ec2ed77debae11`, with the reviewed digest and zero consecutive system failures; `launchctl print` reports `runs = 3`, `last exit code = 0`, and the service remains loaded/not running between intervals. This is a natural scheduled receipt after activation's kickstart. The separate Domus runtime-retention/home-manifest PR #393 remains open at `51fd983c5d85565fd525e0d1a9dd39edbcbcc1a1`; its exact-head merge-drain submission again returned `DEFERRED — LIFECYCLE-UNKNOWN`. The home manifest source now explicitly assigns both `.codex/tmp` and `.codex/.tmp` to Codex, canonicalizes them under `.local/share/codex`, and requires investigation, no active owner/process refs, exact identity, complete commit/ref/stash/private-payload custody, and fresh LFS/submodule custody before retirement. `tests/test_home_guard.py` passes (35 tests); scoped Ruff and diff checks pass. Changes remain published on #393, not yet merged.

Latest independent Data-volume sample: 24,696,544 KiB available (23.55 GiB), approximately 176.45 GiB below the 200 GiB target. This supersedes earlier free-space readings; no reclamation was performed. The 250,000-entry ceiling left 701 home-only and 129 Workspace directories unmeasured. Full object classification, custody, private retrieval, producer routing, cache/VM proof, and capacity acceptance remain open.

A second read-only traversal across home including Workspace used a 1,000,000-entry/45-second ceiling to quantify drift beyond the manifest cap. It reached 1,000,001 entries in 14.73 seconds, with 170,820 directories, 800,689 files, 187 queued directories, 28,254 symlink entries not followed, zero stat/read errors, and no mount-device boundaries. It observed 700 hidden directories, 52 Git administration/store roots, two linked-worktree `.git` files, one bare-repository-shaped candidate, and three application-store markers; these are census-level signatures, not yet a fully identity-deduplicated object ledger. The traversal remains incomplete and none of the candidate objects was changed.
