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
| Committed synthetic receipt verifies | The receipt exactly matches the tracked protocol, fixture, and program manifest | Leaf, phase, chunk, issue, or external-outcome completion |

Real-world evidence belongs in the owning private or public-safe receipt surface under the relevant
terms. This public kit contains no client identity, contact detail, private evidence, price, signed
term, testimonial, or external outcome.

## Scope and exact routing

The validator derives scope and routing from `institutio/positioning/program.yaml` and fails when
this snapshot drifts. A future leaf executor must use the exact registry pair; no substitution is
permitted.

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
five unique qualified door-mails. Qualification does not authorize outreach.

The pilot is capped at one active engagement and one team, with a 21-day default delivery window.
Every scope change requires a new receipt. The lifecycle stops separately at invitation, terms,
delivery, acceptance, conditional install, public case study, independent validation, claim
refresh, and demand adjudication. A dry run exercises the record shape at each stop while leaving
the real effect blocked.

## Consent and authority

The protocol defines two distinct receipt families:

- Authority receipts bind one exact artifact and scope to `HG-PUBLICATION-SEND`, `HG-CONTRACT`, or
  `HG-PUBLIC-IDENTITY`, with a decision, expiry, evidence locator, and revocation route.
- Consent receipts bind evidence intake, outcome interview, public case study, or validation-object
  use to permitted and prohibited uses, retention, and withdrawal.

Fixture receipts use `decision: fixture_only` and `usable_for_real_effect: false`. They prove the
fields and stops exist; they grant nothing.

## Evidence and adjudication

Every evidence record carries source time and method, a content digest, visibility, consent and
authority references, machine-assistance treatment, and limitations. Synthetic records are forced
to `internal_synthetic` visibility and `fixture://` sources.

The adjudicator exercises four branches:

- `keep`: an accepted paid or explicitly bounded audit meets its declared outcome;
- `narrow`: an accepted audit does not meet its declared outcome;
- `pivot`: five unique qualified no outcomes carry documented reasons; and
- `insufficient_evidence`: neither real threshold is met.

In this kit those verdicts are always labelled hypothetical. The real 90-day decision requires
source-linked outcomes and may use at most one 14-day extension with a named missing-evidence
condition, fixed end date, and unchanged thresholds.

Claim refresh remains proposal-only. Synthetic strengthen, narrow, and invalidate branches are
forced to `apply: false`, `publishable: false`, and `prominence: nowhere`.

## Commands

Run each command bare and use its own exit status:

```bash
python3 scripts/positioning-c10-readiness.py --check
python3 scripts/positioning-c10-readiness.py --dry-run
python3 scripts/positioning-c10-readiness.py --verify-receipt docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json
```

Formal leaf execution still begins from live registry readiness, the exact leaf assignment, and
current authority. This kit is an integration input, not a lease, approval, receipt for real work,
or substitute for any `--verify-work` or phase predicate.
