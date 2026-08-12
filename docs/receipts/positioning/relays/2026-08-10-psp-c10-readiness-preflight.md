---
type: prompt-relay-envelope
version: 2.0
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
- Exact tested implementation commit: `30b9ef12c94b19bcdca77b892ac67a00f96fc396`
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
- C08 remains PREPARED at Limen #2316
  `a7937bb1e122574edc5d9e9cb74e18538d2b86c5`.
- C09 remains PREPARED across existing drafts: Limen #2322
  `21f3132f129aa6e1eba515f03aa19619533cef4b`; private #136
  `1da9b00ce26e8d6b466750906f5cfc0a373a9086`; portfolio #222
  `a4c5165421344042efcc7a8b47660c1658b786d1`.
- C06 still has exactly three Product Design directions and all remain **UNSELECTED**.

## What the v2 contract proves

- Exact C10 leaf dependencies, model/effort assignments, and human gates are re-derived from the
  live program registry and fail closed on drift.
- The deterministic receipt binds a canonical C10 registry-projection digest rather than the whole
  program-manifest blob.
- `paid_audit`, `explicitly_bounded_pilot`, and `no_outcome` are distinct evidence types.
- Keep/narrow require terms, payment evidence, and client acceptance for a paid audit.
- A bounded pilot may support P12 delivery evidence but cannot alone satisfy P10-W08, conversion,
  revenue, or commercial proof.
- Pivot requires five unique qualified no outcomes with reasons and a recorded revision.
- Synthetic conversion, revenue, testimonial/reference, dependency closure, claim publication,
  and agent-authored external validation all remain false.
- Five synthetic scenarios exercise keep, narrow, pivot, insufficient evidence, and bounded-pilot
  insufficiency without creating a real outcome.

## Exact predicate receipts

| Predicate | Result |
|---|---|
| `python3 scripts/positioning-c10-readiness.py --check` | PASS; seven leaves; canonical registry projection `be2dc20217dfc53bf1f55ad49ce3e84705756b90a9471e7972ff53c59fb4ff14` |
| `python3 scripts/positioning-c10-readiness.py --verify-receipt docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` | PASS; receipt SHA-256 `ca5f359c257672071fbcf43f88b66abf99565f454d8d8db0e224caf34a5eb728` |
| focused pytest | 10 passed |
| Ruff check | PASS |
| diff hygiene | PASS |
| `scripts/verify-scoped.sh` | PASS; seven implicated cheap gates |

The receipt reports zero real conversions, paid audits, bounded pilots, revenue receipts,
testimonials/references, external outcomes, refreshed claims, satisfied leaf predicates, closed
issues, phase proof, or chunk exit.

## Activation boundary

Keep PR #2321 draft while predecessors remain open. When live `--ready --json` admits a C10 leaf,
the assigned native executor must use that leaf's exact model/effort and current authority, then
create real receipts only from real counterparties and source-linked evidence.

- A bounded pilot is not paid-demand proof.
- No synthetic or agent-authored testimonial may be attributed as real.
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
