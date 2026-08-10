# PSP-C11 governed-foundry handoff preflight

Status: **PREPARED/PREFLIGHT**. This package is reversible, public-safe, and deliberately unable to
close PSP-P13 or any W01-W09 leaf. It does not select or contact an operator, choose binding terms,
grant access, move custody, sign anything, spend, or claim an observed pilot.

The machine-readable owners are:

- [`foundry-preflight-contract.json`](foundry-preflight-contract.json) — rubrics, floors, structure
  options, pipeline, pilot design, governance, exact model assignments, and human gates;
- [`product-candidate-snapshot.json`](product-candidate-snapshot.json) — the live two-pass candidate
  denominator and conservative per-candidate demand/readiness screen;
- [`synthetic-drill-receipt.json`](synthetic-drill-receipt.json) — operator routing, access denial,
  return, and governance replay using invented records only;
- [`scripts/positioning-foundry-preflight.py`](../../../../scripts/positioning-foundry-preflight.py)
  — the validator and public-safe live census.

## Dependency and authority boundary

The formal graph still owns closure: PSP-C11 depends on PSP-C10, P13 depends on P02, P04, P11, and
P12, and the live ready-work query returned no leaves. The authorized preflight therefore prepares
the downstream machinery but posts no leaf receipt and changes no issue state.

Merged PR [#2300](https://github.com/organvm/limen/pull/2300) is the live C00/P00 completion
receipt. It supersedes the old native-identity/Agy note; Agy is not a dependency of this lane. The
candidate denominator reuses, without copying private facts, the two active C02 preflights:

- [#2305](https://github.com/organvm/limen/pull/2305) — two-pass exhaustive ownership census and
  private-facts custody;
- [#2307](https://github.com/organvm/limen/pull/2307) — role, maturity, visibility, public relevance,
  and uncertainty classification.

Those PRs remain draft and are evidence inputs, not completed program leaves.

## W01 — Complete candidate denominator

Two consecutive authenticated owner-wide passes returned the same repository identity digest:

- 10 controlled organizations plus the personal owner;
- 314 accessible repositories;
- 62 product-ledger candidates, all resolving to exactly one currently owned repository;
- 54 public candidates and 8 private candidates;
- zero new organization, repository, or candidate keys between passes.

Public candidates retain their public repository identity in the snapshot. The eight private rows
are `private-candidate-NNN` only. Their names, URLs, descriptions, topics, timestamps, and
owner-specific row identities never enter this package. The validator scans the complete C11 public
package against the current private-name set and fails on an exact private repository token.

## W02 — Demand and market evidence

Every candidate has a demand tier, source row or explicit zero-evidence row, next experiment, and
stop condition. The public-safe snapshot currently contains:

| Tier | Meaning in this preflight | Candidates |
| --- | --- | ---: |
| E0 | No approved demand evidence | 48 |
| E1 | Public attention signal only | 9 |
| E2 | Public reuse signal only | 5 |
| E3-E5 | Consented problem/use, buying intent, or observed paid/operated outcome | 0 |

Stars, forks, and watchers are weak discovery signals and are capped at 35/100. Repository count,
activity, homepage presence, deployment, and internal use are not market demand. No candidate may
cross the transfer floor without an E3-or-stronger primary receipt. Every lower-tier candidate has
a finite experiment and is parked after two bounded failures rather than kept alive by enthusiasm.

## W03 — Technical readiness, custody, and maintenance risk

The current screen proves only repository ownership and metadata facts. It never upgrades metadata
into a build, test, deploy, security, data, IP, observability, return, or maintenance receipt.

| Screen result | Candidates |
| --- | ---: |
| Diligence required | 60 |
| Parked because archived | 2 |
| Fully transferable | 0 |

The full 100-point readiness rubric covers exact-head build/test, runtime, documentation, security,
data/privacy, IP/custody, observability/return, and maintenance. Missing evidence scores zero. Any
unresolved IP, contributor, data, credential, ownership, or rollback boundary is a hard transfer
blocker. The public snapshot treats private-candidate custody as restricted review and reveals no
private detail.

## W04 — Domain-operator profile

The scorecard weights demand access, domain credibility, execution discipline, security/data
stewardship, financial discipline, product stewardship, governance/communication, and conflict
transparency. Synthetic cases deterministically route to all five outcomes:

| Case | Score | Route |
| --- | ---: | --- |
| High fit, no exception | 90 | Proceed |
| Material diligence needed | 73 | Diligence |
| Bounded-learning candidate | 60 | Trial |
| Requests credentials before terms | 0 | Decline |
| Strong score with unresolved conflict | 96 | Human review |

A numerical score cannot override a hard decline, material conflict, legal-capacity question,
reference contradiction, or policy exception.

## W05 — Floors, economics, park, and kill rules

The contract separates three floors:

1. **Experiment:** demand 20, metadata screen 15, one bounded hypothesis, finite cost/time, and a
   stop condition.
2. **Transfer:** demand 60 with E3+ evidence, technical readiness 75, operator 75, downside-tested
   economics, funded maintenance, clean custody, approved terms, and tested return.
3. **Institutional:** demand 75, readiness 85, operator 80, an observed bounded lifecycle, complete
   telemetry, an executed decision, and a repeatable review.

The current conservative portfolio disposition is two experiment candidates and 60 parked
candidates. Transfer-eligible is zero. Every row has an unpriced public hypothesis, unapproved
runway, transfer trigger, and stop condition; private amounts remain outside the public package.
Park/kill rules stop narrative and maintenance drag when evidence, safety, legality, custody, or
economics cannot clear the declared thresholds.

## W06 — Structure and return options

Five draft-only structures are fully enumerated without selecting one:

- revocable operating license;
- performance revenue share;
- performance-vesting venture/equity;
- custody-preserving management mandate;
- time-boxed option trial.

Each carries required IP, data, access, reporting, audit, termination, revocation, deletion, and
return boundaries. Amounts, valuation, equity, revenue-share percentages, liability, tax, and final
terms stay private and require owner plus qualified-counsel review. These are issue-spotting
templates, not legal advice or an offer.

## W07 — Discovery, diligence, and trial pipeline

The stage model is source → consented intro → desk diligence → structured diligence → synthetic
trial → terms review → bounded pilot → continue/revise/return/terminate. It is a template only; no
one was sourced or contacted.

Access begins with public metadata, can advance only to redacted material under owner approval,
and permits invented data in an isolated synthetic trial. Credentials, customer or production
data, private source, repository administration, domain control, IP licenses, and transfer rights
are denied before approved terms. The synthetic drill proves those denials and grants no real
access.

## W08 — Bounded pilot design, not an observed pilot

The 28-day pilot design has day-zero baselines, weekly reviews, a midpoint access/economics audit,
and a dated continue/revise/return/terminate decision. Entry requires the transfer floor, completed
operator diligence, signed approved terms, least privilege, baseline telemetry, tested revocation
and restore, and a named decision date.

Every real-world flag is explicitly false: no product selected, no operator selected or recruited,
no terms selected or signed, no rights transferred, no credentials or production access granted,
and no observed pilot. The only rehearsal uses invented product/operator/data records and ends with
owner custody unchanged.

## W09 — Institutional governance and return paths

The reusable governance model names portfolio owner, product custodian, operator, security/data
steward, qualified counsel, and independent reviewer accountabilities. Reviews run monthly,
quarterly, annually, and on security/data/ownership/conflict/threshold events.

The return workflow freezes new authority, captures state, revokes temporary access, rotates any
applicable credentials, returns repositories/domains/data/artifacts, verifies deletion and custody,
settles surviving obligations, adjudicates park/kill/resume/re-source, and writes the immutable
decision receipt. The synthetic lifecycle replays that sequence with invented artifacts and no
external effect.

## Human gates, recorded once

The contract references the canonical definitions in `institutio/positioning/program.yaml` and
does not create a competing gate list:

- `HG-PUBLICATION-SEND` — no recruiting, outreach, or direct-message send;
- `HG-OPERATOR-TERMS` — no license, equity, revenue-share, custody, access, or transfer terms;
- `HG-CONTRACT` — no signature, spend, liability, data-processing, or service commitment.

All three remain unpulled. Reversible preparation continues; the gates become relevant only at
their exact external act.

## Verification

```bash
python3 scripts/positioning-foundry-preflight.py --json
python3 scripts/positioning-foundry-preflight.py --drills --json
python3 scripts/positioning-foundry-preflight.py --verify-live-snapshot --json
python3 -m unittest discover -s scripts/tests -p 'test_positioning_foundry_preflight.py'
```

Formal leaf predicates remain intentionally deferred. After predecessors close, a fresh correctly
assigned Codex leaf must obtain broker authority, refresh exact heads, prove its non-circular
underlying predicate, attach a structured receipt, and only then run `--verify-work` for that leaf.
