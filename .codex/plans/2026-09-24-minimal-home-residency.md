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
