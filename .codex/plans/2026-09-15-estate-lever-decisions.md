# Remaining estate lever implementation decisions

Owner: Codex, feat/gap-filling-estate-decisions-20260915. Full governing objective
remains 2026-09-15-gap-filling-implementation.md and its adoption continuation.

This draft owns completion of the remaining per-lever implementation review.
Eleven additional decisions now derive branch protection, App scope, collaborator
grants, account capability checks, exact-tip cleanup, dependency acceptance, draft
PR disposition and inventory-backed dispatch from their current component owners.
They preserve explicit external consent and account boundaries. All 107 permanent
records and their lifecycle fields are unchanged. 25 focused registry tests pass.

Current denominator: 97 nonterminal records; 29 have selected implementation
behavior and 68 still require component review. Ten terminal histories remain
retained and need their evidence audit; selection is not implementation completion.
Keep the draft open while finishing that review and its concrete acceptance
predicates. Do not treat the filled record shape as completed external work.

Default CI for d125bf3e2ed5da0166b9a959013d8515d0f00639 runs at
https://github.com/4444J99/limen/actions/runs/35037227552; web, Python and worker
jobs passed at observation time, while whole-repo verification was still running.
Observe its eventual result without holding a synchronous CI wait or rerunning
green work. Reader-mode schema #19 remains open at its unchanged published head;
its prior merge submission is not rearmed. Remaining relay, template/security,
product and custody obligations stay active under the full plan.

## Acceptance-definition and terminal audit continuation

The read-only report now distinguishes implementation-object coverage, selected
decisions and declared acceptance predicates. Current result: 29 selected,
68 requiring component review, two acceptance predicates present and 95 missing.
Malformed input is unmeasured, with unknown totals for unreadable registries; it
never becomes empty successful coverage. Five changed gates passed, including
22 registry/classifier tests.

All ten terminal records were audited against their current owner issue/PR and
registry context. Four owner issues are closed, five remain open, and one owner
is a merged PR with live stable repository identity corroboration. No lifecycle
was changed. Open engineering or authorization-receipt owners do not reactivate
terminal levers. The retired storage-grant issue still has stale request prose;
its existing owner retains that projection debt. Details are in
docs/receipts/terminal-lever-audit-20260915.json.

The stale terminal-owner projections were then reconciled on issues #912, #1046
and #1776: current registry dispositions now precede the preserved historical
requests. Exact body readback and unchanged OPEN states were verified. No issue
or lever was closed or reopened.

## Hook-component review

Three further decisions now bind trust-hook wiring, formatting/lint feedback and
dialog repair to their actual component contracts. Current count: 32 selected,
65 requiring component review; acceptance definitions remain 2 present and 95
missing. The existing hook-wiring hermetic matrix passes all 37 cases. Live
settings, permission policy and repair valves were not modified. The historical
daemon and vendor-bundle identity assumptions do not authorize current runtime
activation. Current fixed-host and bounded scheduling contracts own that work.

The registry batch passed eight scoped gates, including 7,681 CLI tests (two
skipped). A subsequent autotype scope correction refuses unreadable/empty estate
authority before any GitHub call and records unmeasured coverage. Its 21 focused
tests and Ruff pass; unchanged CLI shard results remain evidence. The dedicated
scoped gate covers future changes to the script as well as its tests.
