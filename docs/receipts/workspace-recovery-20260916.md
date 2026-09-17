# Workspace recovery: bounded implementation checkpoint

Status: partial; unfinished work remains unfinished. Owner: workspace-recovery-20260916.
The accompanying JSON contains the exact retirement and restoration receipts.

## Applied and observed

- Existing local autonomy policy is observe, dispatch disabled, without an expiring maintenance window. No unattended priorities are approved.
- Fresh discovery found 311 checkout paths and 165 linked working copies across 149 Git common-directory groups. Excluded private/application/cache locations remain unmeasured. This is broader than the original five-repository count.
- Chamber working copies: 87 before, 22 after. Retired 65 clean inactive copies through the existing non-forced detach lifecycle after current remote-ref ancestry checks. Zero branches or stashes deleted; no issues closed and no PR completion inferred.
- Total confirmed retirements are 66 after one additional non-chamber checkout passed the existing exact-plan reclaimer. Six further candidates retained ignored payloads. The next check found zero eligible copies. Removed file allocations total 9,961,877,504 bytes. Net volume free-space delta is unmeasured; APFS sharing means file allocation is not proof of unique physical bytes freed.
- Restored a sample directly from GitHub: 1,352 tracked files matched their original bytes, executable bits and symlink targets. The second retirement pass made zero changes.
- Retained four dirty, two ignored-payload and sixteen insufficient-custody chamber copies. Four stashes across three discovered repository groups remain in their original repositories. Personal/private material was not relocated or published.
- Authenticated broker readback after the supported environment bootstrap: 228 registered sessions, zero healthy sessions and zero active leases. No broker-owned autonomous process needed a cooperative stop.
- One Limen recovery worktree was already included in the census. One later Domus template worktree adds one retained linked copy: measured 100 after retirement, 101 including the companion checkout.

## Candidate implementation

The existing governor, inventory admission, conduct keepers, worktree creators, issue producers,
verifier and census are extended. No scheduler or task registry was added.

- Approved-priority checks precede local dispatch. Production issue, branch and worktree producers reserve their allowance in the authenticated keeper; reservations survive producer restarts and are shared across outcome descendants. Coverage includes the three issue producers, worktree initialization/session/cell/documentation helpers, audit fixers, marketplace/link API branches, Jules landing and fanout checkouts.
- Production Worker admission defaults closed without an administrator-installed policy. Broker run records reserve 30 minutes per attempt against one 120-minute outcome, cap concurrency, bound lease deadlines, and permit one changed-execution correction. Descendants retain the approved outcome. Legacy task claims reserve the same allowance; the in-progress transition retains the original reservation. Waiting children reserve cumulative time before registration, retain their deadline on promotion, and expire without automatic continuation.
- The verifier has one aggregate deadline capped at 600 seconds; registry timeouts cannot extend it. Automatic whole-matrix escalation is removed. All successful gates retain bounded receipts. Deterministic Python/shell syntax checks and three registry-declared lint/type gates reuse content/dependency/environment-bound results; other checks remain live. Autonomous verifier invocations share a keeper-owned ten-minute deadline across restarts within the attempt. Dispatch clamps local process lifetime and holds timeout/rate-limit failures instead of automatically rerouting or retrying.
- Chamber copies enter the existing reclaimer census. A bounded chamber adapter delegates physical retirement to the existing journaled detach implementation.
- Task release invokes the existing detach journal for clean, idle, exact-remote-tip copies. Dirty, ignored, advanced and unbacked work is retained, as are all branch refs; repeated release is idempotent. Canonical doctrine and the Domus managed template express finite work and release dispositions.

## Verification

Focused results: recovery limit/cache tests 5 passed; governor/root/recovery tests 85 passed;
Python conduct protocol/restart tests 42 passed; worktree initialization tests 5 passed;
Worker keeper tests 66 passed; Worker inventory tests 19 passed; Worker recovery tests 3 passed.
Existing verifier parallel and CI-hardening fixtures passed. Python type checking passed
for 185 CLI source files. Instruction and parameter drift checks passed after corrections.

The resumed implementation passed 70 Worker keeper/recovery tests and a combined 93-test Python recovery/cache/retirement, protocol/restart, initialization, dispatch-identity and fanout batch. The scoped batch passed 32 of 34 cheap gates; the two fixture failures were corrected, and their full gates then passed (144 and 61 tests). Heavy verification was denied by host admission with `swap-fraction`, exit 75. No admission override was used. This checkpoint is not eligible for merge or deployment.

## Explicit remaining work

1. Finish adversarial end-to-end producer coverage, including external chamber tooling and every remote provider launch/cancellation path; the repository scan is not proof of the entire estate. HTTP resource/revocation/restart, legacy/deferred restart and deadline-incapable provider scenarios now pass; broader estate producer coverage remains open.
2. Retain cache reuse only with declared deterministic dependency closures; syntax checks and three declared command gates now reuse results. Retain relevant live integration/deployment predicates.
3. Complete the full implicated fixture/deployment verification when host admission permits; the last blocker is `swap-fraction`. Release retirement now includes Jules landing, fanout landing and ship-docs; audit the remaining owning lifecycles and scratch-root configuration.
4. Complete home/configured-root/administered-organization inventory and per-item dispositions. The resumed GitHub census completed 326 repositories (86 private), 10,459 branches, 1,968 check records, 2,136 issue records and 966 PR records with zero missing leaves. Local strict census still records 44 identity/custody exceptions, 98 failure records, and 81 linked copies before the final one-copy retirement; this uses a different denominator than broad discovery and is not a like-for-like reduction count. The JSON preserves separate census receipts. Preserve retained dirty/ignored/unique material through its existing custody owners before considering further retirement.
5. Deploy the reviewed keeper policy and source changes through existing release rails and verify live denial and concurrency receipts. Apply the reviewed managed template through chezmoi. Local observe mode remains in effect; merging either PR must not resume unrestricted dispatch.

The latest scoped batch passed 47 of 49 cheap gates; both type/format failures were corrected and their full predicates passed (185 + 14 Python source files; 709 format-checked files). The next heavy admission was denied again for `swap-fraction`; no heavy check was run. A local probe wrapper then misnamed its exception handler and exited 1, so this is an observed admission denial, not a successful verifier exit. Worker keeper tests passed 70 scenarios. Jules custody/transaction and task projection tests passed 89 scenarios, with the final custody retry change passing its 22-test subset.

The latest focused batch additionally exercises private-error redaction, ignored-payload protection,
content-closure cache reuse and changed dependencies. Provider adapters without a demonstrated hard
deadline remain unavailable for new autonomous implementation, with observation/recovery preserved.
The native tool-cache owner produced a read-only plan for 27 paths; no cache removal was applied.

Checkpoint is bounded by the requested attempt limit. Resume only this approved recovery outcome,
retaining its cumulative allowance and these receipts; do not spawn another implementation campaign.


Further custody audit: fanout landing no longer automatically deletes the provider-result
clone when an exception unwinds. Its admitted private root preserves failed application
contents; successful landings journal their exact receipt before cleanup and revalidate
remote evidence when cleanup resumes. Supporting clones remain recovery anchors.
Focused validation: 31 fanout scenarios passed; the changed module passed type checking.
No additional physical removal or deployment occurred in this follow-up.


Producer-boundary verification now invokes the three registered issue writers and both
GitHub API branch writers with an unapproved outcome: no outbound create/write runs.
The issue writers share one persisted allowance across entry points. The real Git
initializer also proves rejection leaves branch refs and checkout registrations unchanged.
The recovery suite passes 18 tests and initializer suite passes 6. CI on 859a9463f found
a Python 3.12/mypy inference issue in census error redaction; an explicit dictionary type
fixes it without changing runtime behavior. The corrected module passes local type checking.


A fresh bounded pass over the original home-discovery seeds plus the companion checkout
observed 149 Git groups, 241 registered paths, 93 registered linked worktrees and 229
existing paths, with 17 failed probes. This is a separate nonexhaustive snapshot; only the
66 journaled removals are attributed to this recovery. No stale registration was pruned.

The deadline audit also corrected fanout predicates: the authenticated keeper owns their
shared ten-minute window, checked before creating the verification checkout and before
execution; timeout kills the process group through the existing helper. Verifier input
fingerprinting now checks the same deadline while enumerating dependencies and hashing
file content. Validation: 32 fanout tests, 19 recovery tests, type checking, and both
verifier scheduling/CI-hardening fixture suites passed.
