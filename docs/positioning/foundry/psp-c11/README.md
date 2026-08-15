# PSP-C11 governed-foundry handoff preflight

Status: **PREPARED / NO TRANSFER**. This package is reversible and public-safe. PSP-P13-W01 has an
accepted candidate denominator, and the W03 technical-readiness audit records conservative
acceptance evidence without making any candidate transferable. It does not select or contact an
operator, choose binding terms, grant access, move custody, sign anything, spend, or claim an
observed pilot.

Reconciled 2026-08-13 against the runtime provider catalog contract. The registry pins capability,
reasoning, effect, and effort requirements while provider/model selection remains live and fails
closed when no eligible lane exists. Reconciliation updates dependencies and evidence; it does not
convert preparation into formal closure.

The machine-readable owners are:

- [`foundry-preflight-contract.json`](foundry-preflight-contract.json) — rubrics, floors, structure
  options, pipeline, pilot design, governance, runtime assignment requirements, and human gates;
- [`product-candidate-snapshot.json`](product-candidate-snapshot.json) — the live two-pass candidate
  denominator and conservative per-candidate demand/readiness screen;
- [`synthetic-drill-receipt.json`](synthetic-drill-receipt.json) — operator routing, access denial,
  return, and governance replay using invented records only;
- [`scripts/positioning-foundry-preflight.py`](../../../../scripts/positioning-foundry-preflight.py)
  — the validator and public-safe live census.
- [`foundry-handoff-contract.json`](foundry-handoff-contract.json) — accepted C02 taxonomy
  comparison, non-binding decision records, authority/privacy boundaries, and rollback contract;
- [`scripts/positioning-foundry-handoff.py`](../../../../scripts/positioning-foundry-handoff.py)
  — deterministic classification, decision-record, and five-case rollback validation.

## Dependency and authority boundary

The formal graph still owns closure. [P02](https://github.com/organvm/limen/issues/2172) is closed;
P04, P11, and P12 remain unsatisfied. PSP-C10's prepared package was integrated through
[#2321](https://github.com/organvm/limen/pull/2321): source
`71a6046c2186b4d4ead5136920b82b412ff5d540`, integrated main
`f45fa5f5952a9ae4a5806a5ac4b3f562ace262e2`. It is still not formal closure. Its deterministic
synthetic readiness receipt has digest
`d781c0ca6459d6a0ba620eff9f1a917948af81f16fb6a6a8918480a67781efaa` with all five current
C05/C09 source and integrated-main pairs explicitly marked `counts_as_closure: false`. C03's offer
package was integrated from source `b6af8086c9050634313f519c29a6dfcb922c3721` to main
`8f89ad16ca1df84b00cb8227c88f368d0d64631a`, while formal acceptance remains through W06 at
`c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; its genuine-reader W07 gate remains open in
[#2188](https://github.com/organvm/limen/issues/2188). No C11/P13 leaf is ready. The authorized
preflight therefore prepares downstream machinery but posts no leaf receipt and changes no issue
state.

The candidate denominator reuses, without copying private facts, the two accepted C02 inputs:

- merged [#2305](https://github.com/organvm/limen/pull/2305) at
  `10cf8476d5e88309c71d5fac25167ec7b7af59c4` — two-pass exhaustive ownership census and
  private-facts custody;
- merged [#2307](https://github.com/organvm/limen/pull/2307) at
  `35134b95650a26185a58eb3b3a82632e5b80b5b2` — role, maturity, visibility, public relevance,
  and uncertainty classification.

Only those two inventory inputs appear in the candidate snapshot's source list. The P02 closure
receipt is a dependency binding, not a candidate-data source.

## W01 — Complete candidate denominator

Two consecutive authenticated owner-wide passes returned the same repository identity digest:

- 10 controlled organizations;
- 319 accessible repositories;
- 62 product-ledger candidates, all resolving to exactly one currently owned repository;
- 54 public candidates and 8 private candidates;
- zero new organization, repository, or candidate keys between passes.

Public candidates retain their public repository identity in the snapshot. The eight private rows
are `private-candidate-NNN` only. Their names, URLs, descriptions, topics, timestamps, and
owner-specific row identities never enter this package. The validator scans the complete C11 public
package against the current private-name set and fails on an exact private repository token.

The executable classification comparison reapplies the accepted C02 rule order to every public
candidate using the current governance and access registries. It records whether each candidate is
primarily a product, proof surface, archive, infrastructure component, or partner lane. Private
rows remain classified only in restricted custody; the public package records eight withheld
classifications and no private role, maturity, or repository detail.

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

[`technical-readiness-audit.json`](technical-readiness-audit.json) is locked to the accepted W01
receipt URL, its canonical issue-comment receipt digest, accepted head, acceptance digest, and
private-inclusive candidate identity digest. The
validator recomputes that identity digest from the live accepted W01 candidate identities and also
derives the complete accepted candidate projection from the immutable snapshot at the recorded W01
accepted revision. It compares that revision-bound projection with the working snapshot across
identity, visibility, repository, lifecycle, fork, demand, economics, blocker, and source
transfer-eligibility fields; no working-tree projection digest is trusted. Its denominator is exactly 62
candidates: 54 public rows and eight opaque private
rows. Every public row records the currently observed 40-hex repository head and an exact-schema
result for build, test, deploy, documentation, security, data custody, IP custody,
observability/return, and maintenance. Every private row exposes only its accepted opaque
identifier, a restricted state, a generic accountable owner role, score zero, and
`transfer_eligible: false`.

[`verify_technical_readiness.py`](verify_technical_readiness.py) derives its weights from
`foundry-preflight-contract.json` and its candidate set from
`product-candidate-snapshot.json`. It rejects duplicate JSON members, candidate or source-lock
drift, unpinned evidence, metadata promoted to build/test/deploy proof, score or summary tampering,
unowned blockers, private detail, private-name leakage, and transfer eligibility with any hard
blocker. Live mode re-queries all public repository heads and scans the tracked public C11 package
against private full names and unique private bare tokens held only in memory. That scan is
case-insensitive: full `owner/repository` identities are checked in tracked file content and paths,
while ambiguous bare names are checked only in tracked path names and components so ordinary prose
cannot become a false identity disclosure.

Missing exact-head evidence scores zero and carries a named owner plus bounded next action. A
verified dimension requires a dimension-specific immutable receipt in the candidate repository or
the trusted Limen receipt surface. The receipt may live at a later commit, avoiding a Git fixed
point, but its `tested_commit` must equal the candidate's observed head. Its relative output and
artifact paths resolve at the receipt commit, must be distinct, and must match independently fetched
SHA-256 digests. Trusted live validation also resolves the receipt's exact GitHub Actions
`run_attempt` through the attempt-specific endpoint; its head, attempt, conclusion, predicate path,
and completion time bind the tested commit, pass/fail semantics, and non-future receipt chronology.
The separate maintenance-funding provenance uses the same attempt-specific rule. Self-authored commands or hashes, reused blobs,
invented paths, and generic commit URLs do not prove a dimension. A pass requires integer exit code
zero, while a verified failure requires a non-boolean nonzero integer plus an executed `failure` or
`timed_out` workflow conclusion; skipped, cancelled, neutral, and other non-executed runs are not
failure evidence. The top-level audit time and receipt chronology cannot be future-dated. A `high`
or `critical` security class cannot be promoted to `verified_pass` or satisfy the security hard
floor, and every recorded class must equal the classification in the independently fetched,
exact-head assessment artifact. A homepage, default branch,
recent push, or repository metadata never becomes build, test, runtime, security, custody, or
maintenance proof. Blockers may be empty only after every hard
floor named by the readiness contract is a verified pass, and every tracked blocker carries its
candidate-bound trusted-live clearance predicate. Blocker codes exactly cover every unresolved
dimension, including a `not_applicable` disposition, use a shell-safe identifier grammar, and reject
unclassified additions as hard transfer blockers. `--require-cleared` accepts only the governed
dimension blocker codes or the private-clearance code and rejects unknown codes before testing
absence. An unresolved nested maintenance blocker must equal
its canonical top-level blocker. Maintenance points require a named owner, a positive estimate no
higher than the contract's 40-hour monthly maximum, and a response window no longer than the
contract's 168-hour maximum; the response window must equal the value in the independently resolved
technical receipt. The unique readiness dimensions must total exactly 100 points, and
the transfer threshold is derived from the contract's governed technical-readiness minimum. The
contract's joint 20-point build/test dimension scores only when both receipts pass, and an accepted
archived or parked candidate remains technically non-transferable regardless of evidence. A
maintenance pass must independently resolve a distinct immutable funding receipt, funding artifact,
and successful execution provenance. The parsed artifact must bind the receipt's funded capacity and
the candidate's bounded maintenance estimate; the technical receipt, an owner, and an estimate cannot
self-attest funding. Technical readiness alone never grants transfer eligibility: accepted E3+ demand,
a canonical receipt-backed operator score meeting the contract minimum, approved terms, downside-tested
economics, funded maintenance, and tested return must all clear their governed floors. A live
collection shares one 270-second deadline,
a 96-call ceiling, and an immutable-response cache across W01 verification, receipt blobs, output and
artifact blobs, and Actions provenance, so repeated lookups cannot restart the 300-second gate clock.
Contents API evidence above 1 MiB resolves through its exact Git blob SHA with a 100 MiB fail-closed
ceiling; size and Git-object digest must match before receipt SHA-256 validation.
A live refresh preserves an accepted row only while its repository and exact head are unchanged; a moved
head resets that row to unresolved instead of erasing unrelated candidate evidence. A proposed
private clearance is tracked only as `clearance_pending_live`, with an opaque digest, its blocker,
score zero, and `transfer_eligible: false`. Deterministic scoped CI can validate that explicit
deferral but cannot self-attest `cleared`; trusted private-inclusive live validation must confirm the
matching owner-controlled custody receipt. The current accepted evidence is therefore conservative:
all 62 candidates remain non-transferable.

| Screen result | Candidates |
| --- | ---: |
| Public blocked pending exact-head diligence | 54 |
| Private evidence withheld | 8 |
| Fully transferable | 0 |

The full 100-point readiness rubric covers exact-head build/test, runtime, documentation, security,
data/privacy, IP/custody, observability/return, and maintenance. Missing evidence scores zero. Any
unresolved IP, contributor, data, credential, ownership, or rollback boundary is a hard transfer
blocker. The public snapshot withholds every private candidate's state, fork, demand, readiness,
economics, and custody detail behind an opaque per-snapshot identifier.

The `positioning-foundry-technical-readiness-test` gate in
`institutio/governance/gates.yaml` binds the audit, validator, focused adversarial tests, and
accepted W01 inputs as a deterministic scoped acceptance surface, including the foundry-handoff
regression suite. The scoped `positioning-foundry-technical-readiness-public-live` predicate resolves
immutable public evidence blobs and run provenance plus the canonical W01 marked receipt without
comparing mutable repository heads or enumerating private repositories. Its owning PR workflow
grants only `actions: read`, `contents: read`, and `issues: read`; no write permission is introduced.
The whole-only
`positioning-foundry-technical-readiness-live` predicate retains private-inclusive
identity, private-clearance custody, and private-leak checks under explicitly armed
`LIMEN_VERIFY_LIVE=1` verification. A repository-scoped Actions token is not accepted as operator
evidence for the private estate. The tracked privacy scan includes case-insensitive HTTPS and SSH
clone identities with or without the optional `.git` suffix, but still enumerates only Git-tracked
public C11 paths.

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

A deterministic non-binding decision record is generated for every candidate. Each record carries
classification, demand, readiness, economics state, next action, no-go codes, required human gates,
and unchanged-custody state. Generated records can route only to park, bounded experiment, or
no-go; none can select terms, appoint an operator, or mark transfer eligibility.

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

The operating-authority matrix permits reversible analysis only. Contact, private disclosure,
credentials, production access, term selection, signature, spend, publication, deployment,
custody transfer, and an observed-pilot claim all fail closed to their owning gate or receipt.

## W08 — Bounded pilot design, not an observed pilot

The 28-day pilot design has day-zero baselines, weekly reviews, a midpoint access/economics audit,
and a dated continue/revise/return/terminate decision. Entry requires the transfer floor, completed
operator diligence, signed approved terms, least privilege, baseline telemetry, tested revocation
and restore, and a named decision date.

Every real-world flag is explicitly false: no product selected, no operator selected or recruited,
no terms selected or signed, no rights transferred, no credentials or production access granted,
and no observed pilot. The only rehearsal uses invented product/operator/data records and ends with
owner custody unchanged.

Five synthetic rollback cases cover evidence failure, access or security breach, custody
ambiguity, operator failure, and downside-economics failure. Every case executes the same
nine-step freeze, capture, revoke, return, verify, reconcile, decide, and receipt workflow with
zero external effects and owner custody unchanged.

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
python3 -B scripts/positioning-program.py --check
python3 -B scripts/positioning-program.py --verify-model-assignments
python3 -B scripts/positioning-foundry-preflight.py --json
python3 -B scripts/positioning-foundry-preflight.py --drills --json
python3 -B scripts/positioning-foundry-preflight.py --verify-live-snapshot --json
python3 -B scripts/positioning-foundry-handoff.py --json
python3 -B scripts/positioning-foundry-handoff.py --records --json
python3 -B scripts/positioning-foundry-handoff.py --drills --json
python3 -B -m unittest scripts.tests.test_positioning_foundry_preflight scripts.tests.test_positioning_foundry_handoff
python3 -B docs/positioning/foundry/psp-c11/test_technical_readiness.py
python3 -B docs/positioning/foundry/psp-c11/verify_technical_readiness.py --audit docs/positioning/foundry/psp-c11/technical-readiness-audit.json --live --json
```

The bare W03 live command above is the non-circular PSP-P13-W03 acceptance predicate. It remains
read-only and reports `external_effects: []`. Only after sanctioned merge and a marked #2267
receipt may the conductor run `python3 scripts/positioning-program.py --verify-work PSP-P13-W03`;
no other leaf or phase closes from this package.
