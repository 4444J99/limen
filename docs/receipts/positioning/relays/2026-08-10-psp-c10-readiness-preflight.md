---
type: prompt-relay-envelope
version: 3.0
date: 2026-08-12
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
- Draft PR: [organvm/limen#2321](https://github.com/organvm/limen/pull/2321)
- Exact tested v3 implementation commit: `cc5f89bbc92239caa0422c1bcc3fa4460ff279fe`
- Final relay-containing head and scoped predicate receipt: pinned in draft PR #2321 because this
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
  `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`. W07/#2188 remains open for five genuine
  independent target-like readers; model and synthetic records cannot satisfy it.
- C05 remains PREPARED: private #135
  `6ff7d4e6bd9003213e2675f4e8d59c41a3726b3b`; Limen relay #2315
  `a72a05d917bf14d53221c7d02ec52d3786b4f88e`.
- C04 remains PREPARED at Limen draft #2313 / fetched branch checkpoint
  `23712398c6586e005c303eff632604985cd0a25c`; neither P05 nor P06 is promoted by this relay.
- C06 remains PREPARED at Limen fetched branch checkpoint
  `4eb50463b7f4136b47a103c9792c1ded5caf7873`; the three Product Design directions remain
  **UNSELECTED**, so no visual implementation or public-surface effect is admitted.
- C07 remains PREPARED at Limen fetched branch checkpoint
  `c3b92707a0f6d0ea3076680d100d60d0217f8fe9`; its private-inbound fixtures remain synthetic and
  its send valve remains closed.
- C08 remains PREPARED at Limen #2316
  `a7937bb1e122574edc5d9e9cb74e18538d2b86c5`.
- C09 remains PREPARED across existing drafts: Limen #2322
  `21f3132f129aa6e1eba515f03aa19619533cef4b`; private #136
  `1da9b00ce26e8d6b466750906f5cfc0a373a9086`; portfolio #222
  `a4c5165421344042efcc7a8b47660c1658b786d1`.
- Prepared heads are inputs, not dependency closure. C10 acceptance still follows the canonical
  registry predicates rather than branch existence or green preflight checks.

## What the v3 contract proves

- Every owned C10 leaf is audited against the canonical registry for dependency, target repository
  and paths, capabilities, effect class, acceptance, predicate, exact model/effort, and human gates.
- The deterministic receipt binds a canonical C10 registry-projection digest rather than the whole
  program-manifest blob.
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
| `python3 scripts/positioning-c10-readiness.py --check` | PASS; seven leaves; canonical registry projection `b0db1fc88d686665c08041d1263c0b95cd808b4d744c1ef8382835ba87753d33` |
| `python3 scripts/positioning-c10-readiness.py --write-receipt` | PASS; generated receipt SHA-256 `1f2ee06d21e6604ecd732edee81405d42f26d31c894c35a3762658ae8a1b8671`; zero external effects |
| `python3 scripts/positioning-c10-readiness.py --verify-receipt docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` | PASS; deterministic receipt match at the same SHA-256 |
| focused pytest | 14 passed |
| Ruff check | PASS |
| diff hygiene | PASS |
| `scripts/verify-scoped.sh` | Final relay-containing tree receipt is pinned to the exact head in draft PR #2321; the relay is part of that tree and intentionally does not self-assert the result |

The receipt reports zero real conversions, paid audits, bounded pilots, revenue receipts,
delivery acceptances, public case studies, testimonials/references, external outcomes, refreshed
claims, satisfied leaf predicates, closed issues, phase proof, or chunk exit.

## Activation boundary

Keep PR #2321 draft while predecessors remain open. When live `--ready --json` admits a C10 leaf,
the assigned native executor must use that leaf's exact model/effort and current authority, then
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
