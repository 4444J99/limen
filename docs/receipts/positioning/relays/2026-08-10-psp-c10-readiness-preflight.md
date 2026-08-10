---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: Codex direct-session preflight
to: next authorized PSP-C10 conductor
scope: organvm/limen PSP-C10 readiness topic branch
phase: PROVE
compression_level: medium
---

# Relay — PSP-C10 reversible readiness, not commercial proof

## Routing

- Program work IDs: `PSP-P12-W01` through `PSP-P12-W06`, plus `PSP-P10-W08`
- GitHub issues: [#2257](https://github.com/organvm/limen/issues/2257),
  [#2258](https://github.com/organvm/limen/issues/2258)–[#2263](https://github.com/organvm/limen/issues/2263),
  and [#2247](https://github.com/organvm/limen/issues/2247)
- Target repository for this preflight: `organvm/limen`
- Branch: `codex/psp-c10-readiness-preflight`
- Draft PR: [organvm/limen#2321](https://github.com/organvm/limen/pull/2321)
- Tested implementation commit: `0209b46b416c0922aabe26a82a093a956cba0bad`
- Relay carrier commit: `4240ca216573aa30486362c25abf1ddde1992fac`
- Conduct root/run/lease: none. The conduct client was unconfigured in this environment; the human
  explicitly authorized a direct-session reversible preflight. No formal leaf claim, mutation,
  transition, receipt, or closure was attempted.

## Verified current state

Observed from live GitHub and the local exact tree through `2026-08-10T20:24:16Z`.

| Item | Live state |
|---|---|
| Exact tested implementation head | `0209b46b416c0922aabe26a82a093a956cba0bad` |
| Exact remote branch head before relay commit | `0209b46b416c0922aabe26a82a093a956cba0bad` |
| Working tree before relay commit | clean |
| Acceptance condition | PREPARED/PREFLIGHT only; no PSP-C10 acceptance condition is met |
| Task-specific predicate | synthetic preflight predicates pass; formal `--verify-work` predicates were not run |
| Receipt verifier | deterministic synthetic receipt passes; SHA-256 `8c7da334018c5169b84859132189feea1056885bc0bca54fa957226fd22773c3` |
| Phase exit proof | not run; `PSP-P12` remains open and no phase receipt was minted |
| Omega observation | not applicable |
| External effects | none |

### Program and dependency receipts

- `python3 scripts/positioning-program.py --check` passed: 15 phases, 111 work packets, 127
  projected and mapped objects, and 13 execution chunks.
- `python3 scripts/positioning-program.py --verify-remote` passed with zero drift, missing objects,
  or orphans across all 127 objects.
- `python3 scripts/positioning-program.py --verify-model-assignments` passed against the live Codex
  catalog. `PSP-C10` remains `gpt-5.6-sol / max`; every leaf assignment is pinned in the readiness
  contract and re-derived by the validator.
- Live `--ready --json` emitted only `PSP-P01-W03`; it emitted no PSP-C10 leaf. The formal DAG and
  leaf readiness remain authoritative.
- C00/P00 is closed. Corrective PR [#2300](https://github.com/organvm/limen/pull/2300) merged as
  `fbab1543a863ba2a86546de1eb31bdb9f0f50388`; `PSP-P00-W07` and `PSP-P00` are closed with passing
  content-bound receipts. The earlier non-Codex/Agy requirement is preserved only as superseded
  history and is not a current gate.
- C03 remains an open draft at [#2312](https://github.com/organvm/limen/pull/2312), exact head
  `e440f5b96b7baa67ebc45868e327b5ce62579142`, with its exact-head Python, worker, web, `pr-gate`,
  and CodeRabbit checks successful. This is preflight evidence, not formal C03 closure.
- C05 remains PREPARED/PREFLIGHT. Private draft
  [collaboration-operations-platform#135](https://github.com/organvm-iii-ergon/collaboration-operations-platform/pull/135)
  is exact head `4ae8e81665e35e6a5d403a3e13935021ce6544ec` with required `verify` success. Public-safe relay
  [#2315](https://github.com/organvm/limen/pull/2315) is exact head
  `b62f83f192112f94e73735e06a765b3ad6d97d9b` with `pr-gate` and CodeRabbit success. C03 still
  prevents formal P11/C05 closure.
- C08 remains PREPARED/PREFLIGHT at draft [#2316](https://github.com/organvm/limen/pull/2316), exact
  head `36bf386c22e64785db8e7843899bf9aabf85bf89`, with Python, worker, web, `pr-gate`, CodeQL, and
  CodeRabbit success. `HG-PUBLIC-IDENTITY` and `HG-PUBLICATION-SEND` remain unapproved; nothing was
  published or sent and no distribution result counts toward the demand experiment.
- The sibling C09 lane owns `docs/positioning/sales/psp-c09/` and
  `scripts/positioning-qualification-preflight.py`. At the observation time it had isolated local
  work but no remote PR receipt; this lane did not inspect private fixture contents, edit its paths,
  or duplicate its P10-W01 through P10-W07 scope.

## Completed work

- [x] Added a chunk-owned, registry-bound readiness protocol with six qualification criteria, a
  three-partner cohort bound, exact leaf model routing, and exact leaf human-gate parity.
- [x] Added authority and consent receipt contracts with exact scope, digest, expiry/retention,
  revocation/withdrawal, provenance, and `usable_for_real_effect` boundaries.
- [x] Added an eleven-stage, one-team bounded pilot protocol covering qualification, invitation,
  terms, intake, audit, acceptance, conditional install, case study, independent validation,
  claim refresh, and demand adjudication.
- [x] Added typed evidence capture and a 90-day experiment contract with a five-qualified-door-mail
  denominator, keep/narrow/pivot/insufficient-evidence branches, and one bounded extension rule.
- [x] Added strengthen/narrow/invalidate claim proposals that are forced to `apply: false`,
  `publishable: false`, and `prominence: nowhere` in synthetic mode.
- [x] Added a synthetic-only validator, a deterministic committed dry-run receipt, and fail-closed
  tests for registry drift, gate drift, real-mode input, real-effect authority, proof promotion, and
  receipt drift.
- [x] Opened draft PR [#2321](https://github.com/organvm/limen/pull/2321) from the isolated branch.

## Predicate receipts

| Predicate | Result at tested implementation head |
|---|---|
| `python3 scripts/positioning-c10-readiness.py --check` | exit 0; contract `01dcffa580b4b2cd9abe8e79964da9d1100407428f3a8211da00d5b32eb925dc`, fixture `49600347a9fe8c7197115cc06260ea61ec503a289afb9376af916c3948db07ff` |
| `python3 scripts/positioning-c10-readiness.py --dry-run` | exit 0; four hypothetical branches exercised; every real count stayed zero and every PSP completion flag stayed false |
| `python3 scripts/positioning-c10-readiness.py --verify-receipt docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` | exit 0; receipt SHA-256 `8c7da334018c5169b84859132189feea1056885bc0bca54fa957226fd22773c3` |
| `bash scripts/run-pytest-hermetic.sh scripts/tests/test_positioning_c10_readiness.py -q` | exit 0; 6 passed |
| `python3 -m ruff check scripts/positioning-c10-readiness.py scripts/tests/test_positioning_c10_readiness.py` | exit 0 |
| `git diff --cached --check` | exit 0 |
| `scripts/verify-scoped.sh` | exit 0; seven implicated cheap gates passed |

## Decisions and rationale

| Decision | Evidence and rationale |
|---|---|
| Separate readiness from proof in the schema | Synthetic fixtures exercise mechanics but are barred from real counts, public claims, PSP predicates, and external effects. |
| Keep exact assignments as executable drift checks | The protocol snapshot is compared to the live manifest-derived conductor and leaf rows; a changed pair fails closed. |
| Treat C05 and C08 receipts as prepared inputs only | Both are clean draft preflights behind unresolved formal dependencies and human/external effects. |
| Do not wait for or mention Agy as a current gate | The human correction is implemented by merged #2300 and closed P00/W07 receipts. |
| Do not consume the active C09 worktree | C09 has its own owner and unique paths; C10 will consume its durable remote receipt after it exists. |

## Next actions

1. Keep PR #2321 draft and immutable while formal predecessors remain open; do not close a C10 leaf
   from this preflight.
2. When C05 and C09 have accepted formal receipts and live `--ready --json` emits a C10 leaf, use a
   fresh executor with that leaf's exact registry model/effort and current authority. Reuse this
   contract as an input; do not relabel the synthetic receipt.
3. For real recruitment or delivery, materialize the exact per-instance send, contract, consent,
   evidence, acceptance, and external-outcome receipts in their owning private/public-safe surfaces
   before the corresponding effect.
4. Only PSP-P12-W06 and PSP-P10-W08 may adjudicate claim and demand outcomes, and only from real,
   source-linked evidence after their dependencies are formally satisfied.

## Risks and prohibitions

- Human gates still unpulled: `HG-PUBLICATION-SEND`, `HG-CONTRACT`, and `HG-PUBLIC-IDENTITY`.
- External gates still unsatisfied: real outreach, agreement, payment or explicitly bounded pilot,
  delivery acceptance, testimonial/reference, and external outcome.
- Sensitive/private material boundary: no identity, contact, client evidence, terms, price,
  testimonial, private target content, or private path is present in this relay or the synthetic kit.
- Files or sibling work not to touch: `tasks.yaml`, C09's `docs/positioning/sales/psp-c09/` and
  `scripts/positioning-qualification-preflight.py`, shared generated PSP indexes, and every other
  active worktree/branch.
- No send, agreement, signature, spend, payment, delivery, acceptance, testimonial, publication,
  deployment, DNS, account mutation, private-evidence exposure, claim promotion, formal receipt,
  issue closure, merge, force-push, or direct-main write is authorized by this relay.
- Rollback route: close draft PR #2321 and delete its topic branch, or revert the tested
  implementation commit. No external state needs compensation because no external effect occurred.

## References

- Program manifest: `institutio/positioning/program.yaml`
- C10 contract: `docs/positioning/program/psp-c10-readiness/protocol.yaml`
- Synthetic receipt: `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json`
- Pull request: [organvm/limen#2321](https://github.com/organvm/limen/pull/2321)
- Immutable relay carrier: [commit `4240ca216573aa30486362c25abf1ddde1992fac`](https://github.com/organvm/limen/blob/4240ca216573aa30486362c25abf1ddde1992fac/docs/receipts/positioning/relays/2026-08-10-psp-c10-readiness-preflight.md)

The fresh-agent injection phrase is:

```text
Continue from docs/receipts/positioning/relays/2026-08-10-psp-c10-readiness-preflight.md on branch codex/psp-c10-readiness-preflight. mid-task — see Next Actions for current step.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, lease, approval, consent, acceptance, or commercial proof.
