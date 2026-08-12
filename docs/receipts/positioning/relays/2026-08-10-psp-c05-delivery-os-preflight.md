---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: codex-direct-psp-c05-preflight
to: next admitted Codex session for PSP-C05
scope: organvm-iii-ergon/collaboration-operations-platform@codex/psp-c05-delivery-os-preflight
phase: PROVE
compression_level: high
---

# Relay — PSP-C05 / PSP-P11 service-delivery OS preflight

## Routing

- Program work ID: `PSP-C05` / `PSP-P11` (`PSP-P11-W01` through `PSP-P11-W08`)
- GitHub issue: [#2248](https://github.com/organvm/limen/issues/2248)
- Target repository: `organvm-iii-ergon/collaboration-operations-platform`
- Branch: `codex/psp-c05-delivery-os-preflight`
- Conduct receipt: none; this is an authorized direct-session preflight, not a formal leaf claim or
  lifecycle transition

## Verified current state

| Item | Live state |
| --- | --- |
| Exact implementation head | `2c4efce84082f344fd5e0d90cc110662a379435f` |
| Exact remote branch head | `2c4efce84082f344fd5e0d90cc110662a379435f` |
| C03 dependency head consumed | PR #2312 at `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; core contract `2a1a01149adc2c036b7d3da624740a78d140a672` |
| Accepted C03 progress | PSP-P02 and PSP-P03-W01 through W06 closed; W06 receipt [#2187 comment 5271254820](https://github.com/organvm/limen/issues/2187#issuecomment-5271254820), SHA-256 `260081dfbffc75d55824c0e6ed7d7718a7e397763afb689c94d2230963d79617` |
| Working tree | Clean at checkpoint |
| Acceptance condition | PREPARED/PREFLIGHT only; W07 is C03's sole unsatisfied leaf, and formal P11 acceptance remains unmet until C03 closes and registry admission opens |
| Underlying predicate | Aggregate W01-W08 validator PASS with eight work IDs, six executable contracts, zero external effects, and formal predicates explicitly false; exact target tree also passed focused Prettier, TypeScript, 19 tests, no-plaintext scan, ESLint with zero errors, and production build |
| Receipt verifier | Formal `--verify-work` predicates intentionally not run |
| Phase exit proof | `python3 scripts/positioning-program.py --phase-proof PSP-P11` intentionally not run |
| External effects | None; no client data, send, terms, account action, publication, spend, DNS, or production effect |

## Completed work

- [x] Drafted W01-W08 schemas, runbooks, rubrics, templates, synthetic fixtures, focused tests, and
  synthetic receipts under the registered target paths.
- [x] Bound Audit, Install, and Retainer authority/timing/acceptance to the exact C03 contract while
  retaining symbolic price anchors only.
- [x] Bound the accepted W06 posture: additive leverage, sponsor-granted written scope,
  collaboration, current-owner visibility, reversible work, least access, and clean handoff.
- [x] Proved synthetic intake rejection, audit calibration, finite capacity, partition isolation,
  export-before-delete, rollback, two-pass closeout, and non-publishable consent withdrawal.
- [x] Added one aggregate executable W01-W08 contract that validates sponsor/current-owner
  authority, discovery and architecture procedures, evidence-to-recommendation traceability,
  Governance Install and retainer handoffs, exact zero-effect boundaries, and recursive
  credential/private-identity/numeric-pricing rejection.
- [x] Added malformed-structure and fail-closed regressions; the aggregate validator exits green
  only for the tracked synthetic bundle and cannot satisfy formal predicates.
- [x] Opened target draft PR [#135](https://github.com/organvm-iii-ergon/collaboration-operations-platform/pull/135).

## Decisions and rationale

| Decision | Evidence and rationale |
| --- | --- |
| Keep status `prepared_preflight` | W07 has not supplied its genuine five-reader evidence, C03/P04 has not formally closed, and the live registry has not admitted P11 execution. |
| Pin C03 PR #2312 exact head | Prevents a competing pricing, authority, timing, acceptance, or handoff contract. |
| Keep W07 explicitly unsatisfied | W06 model review is authority-language evidence, not five independent target-reader responses. |
| Keep private economics out | C03 permits only symbolic `PRICE-*` / `RANGE-*` anchors outside their sanctioned private owner. |
| Model W08 as non-publishable | Synthetic consent never satisfies HG-CONTRACT or grants publication authority. |

## Next actions

1. After PSP-P03-W07 closes with genuine external-reader evidence and PSP-C03 formally closes,
   confirm the admitted head descends from `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; when live
   ready-work admits PSP-C05, obtain fresh authority for each leaf and preserve the registered
   path/effect/model boundaries.
2. Run each leaf underlying predicate and durable receipt flow separately, then the P11 phase proof;
   do not treat this preflight PR, local tests, or synthetic receipts as formal completion evidence.

## Risks and prohibitions

- Human gates still unpulled: `HG-PRICE-ANCHORS`, `HG-CONTRACT`, `HG-OPERATOR-TERMS` for their
  respective external/commercial effects.
- Sensitive boundary: no client data, credentials, private pricing values, private paths, or private
  implementation bodies may enter Limen.
- Do not touch `tasks.yaml`, close P11 issues, merge either draft, publish proof, send terms, or grant
  access before the formal dependency and authority predicates pass.
- Rollback: revert target commit `2c4efce84082f344fd5e0d90cc110662a379435f` or close target draft
  PR #135; all checked-in delivery fixtures are synthetic.

## References

- Program manifest: `institutio/positioning/program.yaml`
- GitHub map: `institutio/positioning/github-map.json`
- C03 draft: [organvm/limen#2312](https://github.com/organvm/limen/pull/2312)
- C05 target draft: [organvm-iii-ergon/collaboration-operations-platform#135](https://github.com/organvm-iii-ergon/collaboration-operations-platform/pull/135)

The fresh-agent injection phrase is:

```text
Continue from relay at <admitted-limen-checkout>/docs/receipts/positioning/relays/2026-08-10-psp-c05-delivery-os-preflight.md. mid-task — see Next Actions for current step.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, lease, approval, or permission.
