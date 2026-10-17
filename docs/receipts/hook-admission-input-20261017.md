# Limen admission boundary repair

Date: 2026-10-17. Owner: Limen lifecycle. Source: user-supplied hook-estate
implementation design. Native session: 01a14ab2-92e3-7303-9d6f-aba7c66863ed.

## Scope and evidence

Malformed mutation input previously produced only a warning; an open stdin pipe
outlived the native hook timeout. Process fixtures reproduced both failures before
the repair. The repository runner also silently skipped a missing policy script.

The admission reader now limits input to 1 MiB and shares an eight-second evaluation
deadline across stdin, parsing, capability discovery, delegation and local policy.
Cancellation crosses lower-level error recovery; owned child groups are terminated
through the existing bounded subprocess owner. Delegate stdout is capped at 64 KiB,
stderr at 8 KiB. Invalid verdicts, crashes and unavailable mandatory entrypoints
produce one native denial; known informational lifecycle events remain nonblocking.
The existing startup, read-only action and exact Stop lease-release contracts remain
covered by the original admission suite.

The project registrations bind their event with `--event`, independently of JSON
payloads. Input cannot downgrade a registered PreToolUse event to a lifecycle event.
Error evidence contains class/reason metadata, never copied input or child stderr.

Focused predicate:
`cli/.venv/bin/python -m pytest cli/tests/test_hook_admission_boundary.py cli/tests/test_codex_host_admission_hook.py -q`
passed 61 tests in 22.44 seconds. The suite covers malformed, oversized and invalid
UTF-8 input, stalled stdin, shared input/delegate deadline, invalid and multiple
verdicts, crashing/flooding delegates, descendant cleanup, registered runner execution,
missing policy script, and original action-admission/lifecycle regressions.
The new scoped gate keeps those fixtures selected for future entrypoint changes.
`check-gates.py` and `check-test-hygiene.py` passed; the complete scoped batch is the
publication gate and its result must be recorded separately.

The first complete scoped batch passed all 31 cheap gates, including the 61-test
admission shard, then exited 75 before either heavy suite: pressure sensors were
unavailable with the deliberately narrowed verification PATH (which omitted
`/usr/sbin`). The corrective batch restores the original host PATH while selecting
the isolated test environment. It also covers a reproduced missing-interpreter
case: the shell runner now emits a native denial rather than exiting 127 silently.

The corrective batch on `c0c23c7d` exited 1: 30 cheap gates passed, including
62 admission tests in 22.68 seconds and whole-estate Python lint/format. The sole
failure was `verify-parallel-test` / `timeout-process-group`: the timeout fixture
never recorded its descendant. That exact failure and venv-launch sensitivity
already have an open owner, [Limen #2886](https://github.com/4444J99/limen/issues/2886).
The full CLI/API suites did not execute because the cheap wave failed. Neither
batch is reported as a green scoped result. No unchanged retry or merge is
authorized by these partial results; preserve the draft for that verification
owner and native hook acceptance. Documentation-only publication of this result
does not change the tested source paths; passing shard evidence remains scoped
to the recorded source commit.

## Integration and acceptance

This is an independent Limen packet. The concurrent Domus branch
`fix/hook-estate-evolution-20261017` owns shared inventory, dispatcher and adapters.
Its checkout and changes were preserved. The global wrapper's exact project-command
recognition must account for the added event argument before it can suppress itself;
until then it retains its conservative global fallback. This packet does not assert
that duplicate admission is resolved.

Changing a registered command may require native trust review. No trust state was
manufactured or enabled, no deployed configuration was edited, and no client was
restarted. Deployment, interception, consumed denial, permitted-action success, two
fresh sessions per surface and the 24-hour/20-event observation gates remain pending
with the hook-estate rollout owner. Fixtures establish source behavior only.

Retain the isolated topic checkout through publication and acceptance. The primary
Limen checkout's one-commit drift and unrelated files belong to the existing release
owner; this session did not fast-forward or otherwise alter that checkout.

## Estate completion audit, 2026-10-17 16:49 UTC

The concurrent Domus source packet is now committed through `d6ad7263`.
Its owning receipt is `docs/receipts/hook-estate-20261017.md`; its preserved
pre-deployment census is `docs/receipts/hook-estate-census-20261017-before.json`,
observed at 16:41:12 UTC. Inspection of that committed snapshot confirms 64 roots,
1102 surfaces, 364 handler declarations and 165 explicit coverage gaps. This is a
historical baseline, not a current installed/enforced census.

| Original requirement | Evidence and remaining acceptance | Owner |
|---|---|---|
| Effective roots, project/plugin/scoped discovery, registry/worktree reconciliation | Candidate inventory and reference generator exist; unresolved repositories and source renders keep coverage unknown. | Domus inventory |
| Separate configured, enabled, trusted, intercepted and enforced states | Snapshot records the fields separately; all 364 interception/enforcement fields are unknown. | Native runtime acceptance |
| Every discovered surface has an owner and disposition | All 364 handler rows have both fields, but all 1102 surface rows lack both. Add surface-level ownership/disposition and regression coverage before claiming this completion clause. | Domus inventory |
| Shared evaluator, command-aware matching, actual model inheritance/routing | Source packet exists; fixture results and native behavior require their own evidence. Cross-provider tier equivalence remains unresolved in its owner receipt. | Domus policy |
| Mandatory input/delegate failures block covered mutations | This Limen packet has 62 passing fixtures; global suppression stays conservative until native project execution is proven. | Limen admission and Domus adapter |
| Concurrency-safe cadence and bounded closeout failure accounting | Shared source changes exist; deployment and observed operation remain separate. Intentional paired SessionEnd producers remain represented. | Domus lifecycle |
| Claude failure contract; native Gemini/OpenCode/Copilot/Cursor adapters | Source definitions exist; new providers begin in observation. No source declaration establishes activation. Copilot timeout fail-open remains an explicit limitation. | Provider adapters |
| Codex discovery, trust/hash, matcher, payload and consumed verdict | Changed registration commands still require native review and fresh CLI/current-client receipts. No trust hashes were manufactured. | Native Codex loader |
| Independent fixture, interception and enforcement acceptance | Only fixture behavior is proven here. No native denial/allow marker pair is claimed. | Hook-estate acceptance |
| Two fresh sessions, 24 hours and 20 representative events | Pending; no synthetic timestamps, event counts or session evidence substitute for observed activity. | Hook-estate acceptance |
| Unsupported/bypassed execution paths remain explicit | Antigravity registration and cloud-orchestrated local hooks remain named gaps in the owning source receipt. | Runtime capability owners |
| Reviewed scoped deployment and rollback via chezmoi | Source rollout tooling exists; this session applied no managed target and changed no trust state. | Domus rollout |
| Complete scoped verification, publication and retention | Source is published in draft #2900; #2886 owns the failing broader fixture. Full CLI/API suites and merge remain unproven. Retain checkout. | Limen verification/lifecycle |

Independent-review admission was attempted through the keeper: native session
registration succeeded with Codex identity and human protection, but the bounded
read-only review reservation returned `conduct_rejected` (409). No run/lease was
returned and no reviewer child was launched. This is not independent review proof.
The existing draft PR remains the review/verification owner.

GitHub CLI and MCP reads subsequently returned 401. Removing ambient token
overrides did not restore CLI access. Existing SSH authentication successfully
read the exact topic head, providing a publication route without changing account
credentials or repository remotes. API authentication remains an access gap;
SSH publication must not be described as restored GitHub API access.

## Continuation checkpoint, 2026-10-17 16:53 UTC

GitHub API access recovered: a fresh PR read returned the published `2f110da5`
head and draft/open state. The earlier 401 observation is historical; it is no
longer a current blocker. Issue #2886 remains open and unchanged. The bounded
corrective verification attempt has already been consumed; do not repeatedly
rerun the same failing fixture to obtain a passing sample.

The other writer's post-rollout census, observed at 16:49:34 UTC, still reports
unknown coverage: all 1138 surface records lack owner/disposition fields. Its
current-client canary records `denied_marker_absent: false` and
`allowed_marker_present: true`, with native CLI interception unmeasured and
enforcement not established. This proves no native CLI denial; it also provides
no permission to promote mandatory coverage. Those evidence files remain in the
other active writer's checkout and were not altered here.

Host admission currently denies new heavy work for `swap-fraction`, with no
held lease to transfer. Independent review still lacks a keeper reservation.
The remaining source-owner repair belongs to the active Domus writer; full
verification belongs to #2886 and this draft; native trust review, two fresh
sessions and the observation threshold belong to the hook-estate acceptance
owner. Retain both checkouts. There is no passing full-scope or merge receipt,
and this checkpoint does not reset the attempt or cumulative allowance.

## Human-authorized finishline continuation

The human reopened this outcome at 16:54 UTC. The #2886 fixture race was reproduced
deterministically with a 250 ms cold-start delay: the existing 200 ms deadline
expired before its descendant existed. The cleanup case now starts a real owned
process group, waits at most five seconds for the child to install its signal
handler and write readiness, then exercises the actual monitor with the same
200 ms deadline. It asserts root and descendant termination before fallback
fixture cleanup. The separate cold-start gate still tests timeout from spawn.
Production timeout, output and process-group policies are unchanged.

The scheduling fixture suite passed every case with the cold-start delay in
place. One intermediate run reported an invalid-byte output-limit failure; a
bounded diagnostic was added and the final run passed that case too. This is
not a claim to have diagnosed or fixed an unrelated intermittent output case.

## Authorized session transfer and integration, 2026-10-17 17:37 UTC

The human explicitly authorized transfer of the prior task writer leases.
The exact two leases were released through the admission controller with exit 0;
other sessions' leases and processes were preserved. Native successor identity:
01a14ae3-b630-7ab0-b99d-ac2f0d3de089. Its direct registration returned 422,
so no keeper registration or new broker reservation is claimed.

The full earlier CI run on 874d899c recorded 8775 passed and one failing
owner-diagnostic assertion. Correction 16d69512 preserves only fixed typed owner
diagnostics. The focused admission-boundary and provider-owner-process suites
passed 32 tests in 17.76 seconds. Ruff lint and format checks also passed.
The original 62-case shard and 31 cheap gates remain scoped historical evidence;
no new complete CLI/API pass is claimed.

Domus #489 merged as f62299503d953a73812538bb8bd9a7421ca7f869 after its
exact-head fast-lane predicate cleared. This is source integration, not installed
adoption. The read-only rollout script invocation was denied by native review
with write-target-outside-worktree; no managed file was applied.

Limen #2900 was marked ready. Its single c803ab95 submission returned
DEFERRED / STALE-CORE. One bounded base merge incorporated cf32c32fe, whose
only incoming changes were two documentation files. An explicit diff against
16d69512 proved all implicated implementation/test/gate paths unchanged.
The new exact head may be submitted once; no repeated submission or moving-main
verification loop is authorized. Domus issue #487 retains native acceptance;
Limen #2900 retains source delivery, and #2901 retains its independent writer.
Native trust, permitted-action proof, fresh sessions and the 24-hour/20-event
window are still required. No successful closeout or deployment is asserted.
