# MCP estate keeper prerequisite receipt

## Resumed implementation evidence

Protected session `mcp-estate-resume-20260908` restored credentials using the documented bootstrap.
The full claim response `busy-99d7002144349fe1339b88ed` showed the implicit
`repo/4444j99/limen/write` claim conflicting with four active leases:
`lease-1030-40d6b65160c4dc39`, `lease-1031-44b23122942200c9`,
`lease-1032-bd2a984ebb54ac4f`, and `lease-1033-c6b155f901806b78`.
Their live graph identifies unrelated git-finishline branch/path scopes, including a separate
serial-governor branch. Those peers were preserved. An explicit two-branch execution packet was
accepted as `run-3890a837deca93e3ca65ac4ef1bce340`, lease `lease-1034-3890a837deca93e3`,
generation 1034, and claimed by this protected session. The canonical estate task claim remains
unaccepted; this separate execution record is not a board transition.

Python and Worker claim normalization now recognize the existing strict non-capacity projection
contract before adding the code-write fallback. Only exact zero-cost keeper-owned board packets
avoid repository-wide exclusion. Task exclusion remains; malformed or paid packets retain the
conservative fallback. Focused regression: one Python test passed and 20 Worker projection and
work-loan tests passed. No scope from a peer was changed.

Remote Worker job `102150509863` in run `34252627214` failed before tests on four fast-uri
advisories: GHSA-5jgf-p345-68v8, GHSA-f65p-4m7j-42xc, GHSA-fph4-wmhf-6fwf,
GHSA-jqff-g426-hqxp. The Worker override now requires fast-uri >=3.1.6 within 3.x;
the regenerated lockfile audit reports zero vulnerabilities.

The resumed scoped batch passed all 12 cheap gates, including type checking, lint and formatting.
Its heavy wave returned exit 75 (`swap-fraction,vitals-shed`). Live host evidence showed no
conflicting host lease, 6.56 GB swap on 17.18 GB physical memory (38.2%), and VITALS shed.
No host threshold, process or admission rule was changed. Deployment and the two live publication
mutations remain unverified. The gate remains owned by this prerequisite PR; the next command is
the scoped verification command below when admitted, followed by the exact merged deployment rail.

Owner: Codex; parent intent and residual acceptance owner: `MCP-ESTATE-20260908`.
Source branch: `fix/keeper-publication-recovery-20260908`.
Protected broker session: `mcp-estate-20260908-implementation`.

## Implemented

The publisher recovers a missing publication ref after a merge returns 404. Recovery confirms
the repository identity and authoritative default branch, reads that branch's current commit,
creates only the missing publication ref, then independently rereads it. Concurrent creation is
accepted only with a valid observed ref; existing publication history is never reset. A configured
default that disagrees with the repository, a default-branch publication target, permission errors,
invalid commits, and failed creation all fail closed. The subsequent merge has one recovery attempt;
the existing bounded publication CAS remains unchanged. No local task projection was modified.

## Verification and admission

- `node --test web/worker/test/projection-recovery.test.js web/worker/test/public-projection-cas.test.js`:
  **14 passed**, including two consecutive private keeper mutations after automatic branch recovery,
  private history preservation, counts-only publication, and concurrent recreation.
- `git diff --check`: passed after the final source changes.
- `bash scripts/verify-scoped.sh --base 569f164a3 --integration --gate-timeout-seconds 300 --gate-output-bytes 262144`:
  cheap wave passed on prerequisite commit `c75eba03e`; required Worker wave was **not run** because
  machine-wide host admission returned `swap-fraction,vitals-shed` (exit 75). A later small refinement
  validates an already-existing ref and adds the consecutive-mutation fixture; it has the focused
  results above, not a new scoped-pass claim.
- The documented `workstream_hydrate_conduct_environment` bootstrap restored authenticated shell
  broker access. Registration was acknowledged with `human_protected: true` and no native fanout.
- Canonical board observation showed `MCP-ESTATE-20260908` **open**. The claim request returned
  **busy**, so no execution lease or task-state transition is claimed. The last task run remains the
  successful original intake `run-b889f63094064498fde826185f2fd864`.

The native MCP capabilities call lacked broker configuration, and its task lookup did not find the
task that was present in authenticated private keeper custody. This is additional client-route
evidence for the existing estate task, not evidence that the canonical task disappeared.

## Explicit outcomes

Implementation verification: **partial**; focused prerequisite regression passed, Worker/scoped
acceptance remains unavailable. Deployment: **not performed**. Estate ideal: **not satisfied**.
Neither companion draft was altered, merged, or deployed by this prerequisite lane.

## Continuation and owning predicates

The prerequisite PR owns the host-admission blocker and missing deployment receipt. Once the host
admits the Worker wave, run one bounded scoped batch on its current exact head, retain unchanged
green shard receipts, and land through the registry-declared PR rail. Use the documented
`deploy-worker.yml` exact-main deployment procedure; no synchronous CI waiter or admission bypass.
Then require two consecutive live broker mutations without manual ref restoration. The fixture
above is not that production receipt.

Launch verification from an isolated checkout of this branch:

```sh
bash scripts/verify-scoped.sh --base 569f164a3 --integration --gate-timeout-seconds 300 --gate-output-bytes 262144
```

The existing companion drafts remain the durable owners of the larger implementation:
[Limen #2567](https://github.com/4444J99/limen/pull/2567) and
[Domus #379](https://github.com/organvm/domus-genoma/pull/379). Their recorded 28 MCP tests,
50 Domus tests, API tests and Serena protocol canary remain historical receipts. After broker
admission, resume those exact branches in isolated worktrees and implement the supplied plan:

1. Expected service and registration inventories with effective client/plugin/project precedence,
   relocated runtime roots, declared routes, source owners, and missing integrations retained.
2. Conditional atomic Domus repairs and version-bound private rollback custody; one Serena policy
   for quiet startup, explicit dashboard access, standalone default and isolated projects.
3. ianva upstream/capability reconciliation across every adapter; direct LaunchDarkly OAuth retained
   until an independently verified migration contract passes. No login from health checks.
4. Supported MCP initialization/stateless exchanges, pagination, independent measurement dimensions,
   probe-owned cleanup, observed dependency-bound canaries, and native read-only status exposure.
5. Effective skill inventory and native runtime context accounting in `codex-skill-slim.py`, preserving
   all skill identities/bodies. Require a fresh-session witness; absent telemetry remains unavailable.
6. Registered one-apply/one-verify repair episodes with no repeated unchanged mutation; existing
   monitor/update hooks only. Recover full CLI failure identities under host admission.
7. Fresh distinct-client startup, routing, UI, capability, isolation and cleanup canaries; targeted
   deployment receipts; seven defect counts plus both denominators. Authentication/coverage gaps
   remain owned and prevent whole-estate success independently of source or deployment progress.

No new credential consent, client restart, scheduler, fanout, or manual publication-ref restoration
was performed. The larger task remains unfulfilled and must not be marked done from this receipt.
