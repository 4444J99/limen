---
type: prompt-relay-envelope
version: 4.0
date: 2026-08-13
from: Codex direct-session preflight
to: next authorized PSP-C10 conductor
scope: organvm/limen PSP-C10 readiness topic branch
phase: PROVE
compression_level: high
---

# Relay — PSP-C10 reversible readiness, not commercial proof

## Routing and current state

- Work: `PSP-P12-W01` through `PSP-P12-W06`, plus `PSP-P10-W08`
- Branch: `codex/psp-c10-readiness-preflight`
- Integration PR: [organvm/limen#2321](https://github.com/organvm/limen/pull/2321)
- Foundational v3 implementation commit: `cc5f89bbc92239caa0422c1bcc3fa4460ff279fe`
- Superseding integrated source-lock head: pinned in PR #2321 because this tracked relay
  cannot self-name its containing commit
- Final relay-containing head and scoped predicate receipt: pinned in PR #2321 because this
  tracked relay cannot self-name its containing commit
- State: **PREPARED/PREFLIGHT**
- Formal predicates, leaf receipts, phase proof, and chunk closure: not run or claimed
- External effects: none

This was an explicitly authorized direct-session reversible preflight. It does not impersonate any
leaf executor, grant authority, or replace live registry admission.

## Dependency truth

- P02 is formally closed at accepted main `8faa5fb9899231ebf5f87e78bb171544c11b79d7`;
  marked receipt: [#2172](https://github.com/organvm/limen/issues/2172#issuecomment-5270095170).
- C03 is accepted through W06 at checkpoint
  `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; #2312 source
  `b6af8086c9050634313f519c29a6dfcb922c3721` is integrated at
  `8f89ad16ca1df84b00cb8227c88f368d0d64631a`. W07/#2188 remains open for five genuine
  independent target-like readers; model and synthetic records cannot satisfy it.
- C05 merged prepared packages: private #135 source
  `432c31ea6bcaf2c175b0fde08b6e1733fe4c2926`, integrated
  `9172619633bb9a09ea3a05eae9f48e987f2b3e7d`; Limen relay #2315 source
  `d31ce37a85adf5d2e448dab8273a61e388f1e589`, integrated
  `7a0682722185d17095a0b44de17d4bd5cf3284dd`.
- C04 merged prepared proof: Limen #2313 source
  `1bb0ceca162129f6c90ae47958712bb19cd99cbb`, integrated
  `3f2269dd38865244f826aaff4818912a636167be`; neither P05 nor P06 is promoted by this relay.
- C06 merged prepared relay: Limen #2317 source
  `854b6385de6b340485baaf59b1be55bd4d243a4d`, integrated
  `690617fc2aeea79acfe5604799e6413d70b6e4dd`; the three Product Design directions remain
  **UNSELECTED**, so no visual implementation or public-surface effect is admitted.
- C07 merged prepared package: Limen #2318 source
  `9d81552a65cab1a8785e74251853881ac1957925`, integrated
  `799c4bbe80634bb870e379061d03d08a74ea5405`; its private-inbound fixtures remain synthetic and
  its send valve remains closed.
- C08 merged prepared package: Limen #2316 source
  `4e55e76b672b296f246bb18f96eccb4de10a8fb4`, integrated
  `26dba96c74d18ead1244bee8dbbd18c630942b2f`.
- C09 merged prepared packages: Limen #2322 source
  `63f82f3cd9ee225cd4baeb84fef36305c7ee4593`, integrated
  `d1861e3c9b493ecd735f1360d3eacb4daf811ad3`; private #136 source
  `cd92697d596f674c9ddfc56edc919317ffb463e2`, integrated
  `53784482af1a5b213dd21df7ab5bc2bd38f90f18`; portfolio #222 source
  `c44bab44dca190ec115dd498ff252f57e2441a58`, integrated
  `77c27d16a777af5fc0da8d6a0da503ae17f0d29f`.
- Prepared heads are inputs, not dependency closure. C10 acceptance still follows the canonical
  registry predicates rather than branch existence or green preflight checks.

## What the v4 contract proves

- Every owned C10 leaf is audited against the canonical registry for dependency, target repository
  and paths, capabilities, effect class, acceptance, predicate, runtime assignment requirements,
  and human gates. No provider slug is frozen in the public contract.
- The deterministic receipt binds a canonical C10 registry-projection digest rather than the whole
  program-manifest blob.
- The contract and deterministic receipt exact-bind five current C05/C09 source packages, all with
  `counts_as_closure: false`, so commercial-readiness rehearsal cannot silently consume superseded
  delivery templates, offer routing, or qualification controls.
- Five complete recruitment packets bind qualification, all six hard-exclusion results, cohort
  disposition, invitation digest, `not_sent`, absent send receipt, and `not_agreed` terms.
- Typed fixture-only payment, acceptance, and delivery receipts are separately linked by candidate,
  engagement, authority, and content digest; none can claim the corresponding real event.
- `paid_audit`, `explicitly_bounded_pilot`, and `no_outcome` remain distinct evidence types.
- Keep/narrow require terms authority, a payment receipt, acceptance receipt, delivery receipt, and
  the required evidence classes for one paid-audit branch.
- A bounded pilot may support P12 delivery evidence but cannot alone satisfy P10-W08, conversion,
  revenue, or commercial proof.
- Pivot requires five unique qualified no outcomes with reasons and a recorded revision.
- Each scenario has one before/after strategy decision record; all external-outcome evidence lists
  are empty and every apply, publishable, and real-effect flag remains false.
- Case-study publication is `not_published`; each claim proposal has one matching
  `blocked_synthetic` promotion receipt with rollback, consent, authority, and claim-set digests.
- The deterministic writer regenerates the tracked receipt automatically from the contract,
  fixture, and canonical registry projection.
- Synthetic conversion, revenue, testimonial/reference, dependency closure, claim publication,
  and agent-authored external validation all remain false.
- Five synthetic scenarios exercise keep, narrow, pivot, insufficient evidence, and bounded-pilot
  insufficiency without creating a real outcome.

## Exact predicate receipts

| Predicate | Result |
|---|---|
| `python3 scripts/positioning-c10-readiness.py --check` | PASS; seven leaves; five exact C05/C09 source-plus-integrated bindings; canonical registry projection `6a4e1221a88f304726273339470e29d208e59282e236f39744c71ac4ecfb8a73` |
| `python3 scripts/positioning-c10-readiness.py --write-receipt` | PASS; generated receipt SHA-256 `d781c0ca6459d6a0ba620eff9f1a917948af81f16fb6a6a8918480a67781efaa`; zero external effects |
| `python3 scripts/positioning-c10-readiness.py --verify-receipt docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` | PASS; deterministic receipt match at the same SHA-256 |
| focused pytest | 15 passed |
| Ruff check | PASS |
| diff hygiene | PASS |
| `scripts/verify-scoped.sh` | Final relay-containing tree receipt is pinned to the exact head in draft PR #2321; the relay is part of that tree and intentionally does not self-assert the result |

The receipt reports zero real conversions, paid audits, bounded pilots, revenue receipts,
delivery acceptances, public case studies, testimonials/references, external outcomes, refreshed
claims, satisfied leaf predicates, closed issues, phase proof, or chunk exit.

## Activation boundary

Integrating PR #2321 preserves every formal dependency and human gate. When live `--ready --json`
admits a C10 leaf, the native executor must satisfy its runtime-derived capability/reasoning/effect/
effort requirements and current authority, then
create real receipts only from real counterparties and source-linked evidence.

- A bounded pilot is not paid-demand proof.
- No synthetic or agent-authored testimonial may be attributed as real.
- Fixture-only payment, acceptance, delivery, case-study, and promotion receipts are schema tests,
  never counterparty attestations.
- `HG-PUBLICATION-SEND`, `HG-CONTRACT`, and `HG-PUBLIC-IDENTITY` remain human gates.
- No outreach, agreement, signature, spend, payment, delivery, acceptance, publication, deployment,
  DNS change, account mutation, private-evidence exposure, claim promotion, merge, or issue closure
  occurred.

## References

- Contract: `docs/positioning/program/psp-c10-readiness/protocol.yaml`
- Fixture: `docs/positioning/program/psp-c10-readiness/synthetic-fixture.json`
- Synthetic receipt:
  `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json`
- Program registry: `institutio/positioning/program.yaml`
- Pull request: [organvm/limen#2321](https://github.com/organvm/limen/pull/2321)

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, lease, approval, consent, acceptance, or commercial proof.
