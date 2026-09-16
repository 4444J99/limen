# Workspace recovery: bounded implementation checkpoint

Status: partial; unfinished work remains unfinished. Owner: workspace-recovery-20260916.
The accompanying JSON contains the exact retirement and restoration receipts.

## Applied and observed

- Existing local autonomy policy is observe, dispatch disabled, without an expiring maintenance window. No unattended priorities are approved.
- Fresh discovery found 311 checkout paths and 165 linked working copies across 149 Git common-directory groups. Excluded private/application/cache locations remain unmeasured. This is broader than the original five-repository count.
- Chamber working copies: 87 before, 22 after. Retired 65 clean inactive copies through the existing non-forced detach lifecycle after current remote-ref ancestry checks. Zero branches or stashes deleted; no issues closed and no PR completion inferred.
- Removed file allocations total 9,956,261,888 bytes. Net volume free-space delta is unmeasured; APFS sharing means file allocation is not proof of unique physical bytes freed.
- Restored a sample directly from GitHub: 1,352 tracked files matched their original bytes, executable bits and symlink targets. The second retirement pass made zero changes.
- Retained four dirty, two ignored-payload and sixteen insufficient-custody chamber copies. Four stashes across three discovered repository groups remain in their original repositories. Personal/private material was not relocated or published.
- Authenticated broker readback after the supported environment bootstrap: 228 registered sessions, zero healthy sessions and zero active leases. No broker-owned autonomous process needed a cooperative stop.
- One Limen recovery worktree was already included in the census. One later Domus template worktree adds one retained linked copy: measured 100 after retirement, 101 including the companion checkout.

## Candidate implementation

The existing governor, inventory admission, conduct keepers, worktree creators, issue producers,
verifier and census are extended. No scheduler or task registry was added.

- Approved-priority checks precede local dispatch. Production issue, branch and worktree producers reserve their allowance in the authenticated keeper; reservations survive producer restarts and are shared across outcome descendants. Coverage includes the three issue producers, worktree initialization/session/cell/documentation helpers, audit fixers, marketplace/link API branches, Jules landing and fanout checkouts.
- Production Worker admission defaults closed without an administrator-installed policy. Broker run records reserve 30 minutes per attempt against one 120-minute outcome, cap concurrency, bound lease deadlines, and permit one changed-execution correction. Descendants retain the approved outcome. Legacy task claims reserve the same allowance; the in-progress transition retains the original reservation. Waiting children reserve cumulative time before registration, retain their deadline on promotion, and expire without automatic continuation.
- The verifier has one aggregate deadline capped at 600 seconds; registry timeouts cannot extend it. Automatic whole-matrix escalation is removed. Deterministic Python/shell syntax successes have content/dependency/environment-bound reusable receipts. Other checks remain live. Autonomous verifier invocations share a keeper-owned ten-minute deadline across restarts within the attempt. Dispatch clamps local process lifetime and holds timeout/rate-limit failures instead of automatically rerouting or retrying.
- Chamber copies enter the existing reclaimer census. A bounded chamber adapter delegates physical retirement to the existing journaled detach implementation.
- Task release invokes the existing detach journal for clean, idle, exact-remote-tip copies. Dirty, ignored, advanced and unbacked work is retained, as are all branch refs; repeated release is idempotent. Canonical doctrine and the Domus managed template express finite work and release dispositions.

## Verification

Focused results: recovery limit/cache tests 5 passed; governor/root/recovery tests 85 passed;
Python conduct protocol/restart tests 42 passed; worktree initialization tests 5 passed;
Worker keeper tests 66 passed; Worker inventory tests 19 passed; Worker recovery tests 3 passed.
Existing verifier parallel and CI-hardening fixtures passed. Python type checking passed
for 185 CLI source files. Instruction and parameter drift checks passed after corrections.

The resumed implementation passed 70 Worker keeper/recovery tests, 11 recovery/cache/retirement tests, 35 dispatch-identity/fanout tests, and the Python protocol/restart/initialization tests. The scoped batch passed 32 of 34 cheap gates; the two fixture failures were corrected, and their full gates then passed (144 and 61 tests). Heavy verification was denied by host admission with `swap-fraction`, exit 75. No admission override was used. This checkpoint is not eligible for merge or deployment.

## Explicit remaining work

1. Finish adversarial end-to-end producer coverage, including external chamber tooling and every remote provider launch/cancellation path; the repository scan is not proof of the entire estate. Add HTTP admission and legacy/deferred restart scenarios.
2. Broaden cache reuse only with declared deterministic dependency closures; current reusable results remain syntax-only. Retain relevant live integration/deployment predicates.
3. Complete the full implicated fixture/deployment verification when host admission permits; the last blocker is `swap-fraction`. Extend release retirement beyond local dispatch to all owning lifecycles and audit scratch-root configuration.
4. Complete home/configured-root/administered-organization inventory and per-item dispositions. The bounded GitHub census is in progress with resumable private cursor evidence. Preserve retained dirty/ignored/unique material through its existing custody owners before considering further retirement.
5. Deploy the reviewed keeper policy and source changes through existing release rails and verify live denial and concurrency receipts. Apply the reviewed managed template through chezmoi. Local observe mode remains in effect; merging either PR must not resume unrestricted dispatch.

Checkpoint is bounded by the requested attempt limit. Resume only this approved recovery outcome,
retaining its cumulative allowance and these receipts; do not spawn another implementation campaign.
