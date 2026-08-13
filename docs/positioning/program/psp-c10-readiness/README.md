# PSP-C10 reversible readiness kit

This kit prepares the reversible part of `PSP-C10` without pretending that a synthetic exercise is
commercial proof. It covers `PSP-P12` plus `PSP-P10-W08`: cohort qualification, consent and
authority receipts, a bounded pilot lifecycle, evidence capture, outcome adjudication,
claim-refresh proposals, and the 90-day decision mechanism.

The validator accepts synthetic fixtures only. A passing run means the contract is internally
coherent and its decision branches are executable. It does **not** mean anyone was contacted, any
terms were agreed, an audit was paid for or delivered, a client accepted an outcome, a testimonial
or reference exists, a claim was refreshed, or a PSP predicate passed.

## Truth boundary

| Result | What it establishes | What it cannot establish |
|---|---|---|
| Contract check passes | Registry scope, exact model routing, gates, record fields, thresholds, and bounds agree | Readiness of formal predecessors or authority for a real effect |
| Synthetic dry run passes | Keep, narrow, pivot, and insufficient-evidence branches work over fixture-only records | Qualified demand, payment, delivery acceptance, commercial proof, or wedge invalidation |
| Committed synthetic receipt verifies | The receipt exactly matches the tracked protocol, fixture, and canonical C10 registry projection | Leaf, phase, chunk, issue, or external-outcome completion |

Real-world evidence belongs in the owning private or public-safe receipt surface under the relevant
terms. This public kit contains no client identity, contact detail, private evidence, price, signed
term, testimonial, or external outcome.

## Scope and exact routing

The validator derives scope, dependencies, routing, and gates from
`institutio/positioning/program.yaml` and fails when the C10 projection drifts. Its receipt binds a
canonical digest of only the C10 chunk and leaf projection, so an unrelated manifest edit does not
invalidate unchanged readiness evidence. A future leaf executor must use the exact registry pair;
no substitution is permitted.

The contract also exact-binds the current C05 delivery relay/private templates and the C09
qualification relay/private/portfolio packages. Those five prepared inputs remain
`counts_as_closure: false`; the bindings prevent this readiness kit from silently validating
against superseded offers, delivery templates, or conversion controls.

| Work | Assigned model | Effort | Prepared contract |
|---|---|---|---|
| `PSP-P12-W01` | `gpt-5.6-sol` | `xhigh` | cohort criteria, invitation and terms stops |
| `PSP-P12-W02` | `gpt-5.6-sol` | `max` | bounded audit, acceptance, and closeout evidence |
| `PSP-P12-W03` | `gpt-5.6-sol` | `xhigh` | conditional one-team install and before/after evidence |
| `PSP-P12-W04` | `gpt-5.6-sol` | `max` | exact-copy consent, publication, and withdrawal stops |
| `PSP-P12-W05` | `gpt-5.6-luna` | `medium` | provenance, permitted wording, and withdrawal inventory |
| `PSP-P12-W06` | `gpt-5.6-sol` | `max` | strengthen, narrow, or invalidate proposals only |
| `PSP-P10-W08` | `gpt-5.6-sol` | `max` | qualified denominator and keep/narrow/pivot adjudication |

The `PSP-C10` conductor assignment remains `gpt-5.6-sol` at `max` effort.

## Recruitment and pilot bounds

A qualified door-mail must satisfy all six tracked criteria: problem fit, decision authority,
least-privilege evidence access, bounded scope, an observable outcome, and capacity to decide
consent and retention. The design-partner cohort is capped at three; the 90-day denominator remains
five unique qualified door-mails. Each fixture recruitment packet binds the criteria and exclusion
results, qualification receipt, cohort slot, invitation digest, and explicit `not_sent` /
`not_agreed` states. Qualification does not authorize outreach.

The pilot is capped at one active engagement and one team, with a 21-day default delivery window.
Every scope change requires a new receipt. The lifecycle stops separately at invitation, terms,
delivery, acceptance, conditional install, public case study, independent validation, claim
refresh, and demand adjudication. A dry run exercises the record shape at each stop while leaving
the real effect blocked.

## Receipt and authority boundaries

The protocol separates each evidence and authority boundary:

- Authority receipts bind one exact artifact and scope to `HG-PUBLICATION-SEND`, `HG-CONTRACT`, or
  `HG-PUBLIC-IDENTITY`, with a decision, expiry, evidence locator, and revocation route.
- Consent receipts bind evidence intake, outcome interview, public case study, or validation-object
  use to permitted and prohibited uses, retention, and withdrawal.
- Payment, acceptance, and delivery receipts bind one candidate or engagement to source locators,
  digests, custody, limitations, and the relevant authority references.
- Case-study receipts require exact-copy, client, owner, consent, identity, contract, publication,
  withdrawal, and rollback fields.
- Claim-promotion receipts bind each proposed disposition to external-outcome, consent, authority,
  target-claim, prior/proposed digest, and rollback fields.

Fixture receipts use `fixture_only`, `not_published`, or `blocked_synthetic` states and
`usable_for_real_effect: false`. They prove the fields and stops exist; they grant nothing and do
not attest that payment, delivery, acceptance, approval, publication, or promotion occurred.

## Evidence and adjudication

Every evidence record carries source time and method, a content digest, visibility, consent and
authority references, machine-assistance treatment, and limitations. Synthetic records are forced
to `internal_synthetic` visibility and `fixture://` sources.

The adjudicator exercises four decisions across five scenarios:

- `keep`: a paid audit has terms, payment, and client-acceptance evidence and meets its declared outcome;
- `narrow`: a paid audit has terms, payment, and client-acceptance evidence but misses its declared outcome;
- `pivot`: five unique qualified no outcomes carry documented reasons and a recorded revision; and
- `insufficient_evidence`: neither real threshold is met.

An explicitly bounded pilot may support P12 delivery evidence, but it cannot by itself satisfy
P10-W08, conversion, revenue, or commercial proof. Synthetic or agent-authored testimonial and
reference objects are likewise never attributed as real evidence.

In this kit those verdicts are always labelled hypothetical. The real 90-day decision requires
source-linked outcomes and may use at most one 14-day extension with a named missing-evidence
condition, fixed end date, and unchanged thresholds.

Each synthetic scenario also has a before/after strategy decision record with its basis, changed
assumptions, source outcomes, and an empty external-evidence list. These records are forced to
`apply: false`, `publishable: false`, and `usable_for_real_effect: false`.

Claim refresh remains proposal-only. Synthetic strengthen, narrow, and invalidate branches are
forced to `apply: false`, `publishable: false`, and `prominence: nowhere`; every proposal has one
matching `blocked_synthetic` promotion receipt.

## Commands

Run each command bare and use its own exit status:

```bash
python3 scripts/positioning-c10-readiness.py --check
python3 scripts/positioning-c10-readiness.py --dry-run
python3 scripts/positioning-c10-readiness.py --write-receipt
python3 scripts/positioning-c10-readiness.py --verify-receipt docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json
```

`--write-receipt` deterministically regenerates the tracked synthetic receipt from the canonical
C10 registry projection, contract, and fixture. It performs no network or external action.

Formal leaf execution still begins from live registry readiness, the exact leaf assignment, and
current authority. This kit is an integration input, not a lease, approval, receipt for real work,
or substitute for any `--verify-work` or phase predicate.
