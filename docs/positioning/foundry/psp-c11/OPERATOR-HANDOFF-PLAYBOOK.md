# Operator-handoff playbook

This is a draft-only operating template for PSP-P13. It is not an offer, legal advice, a selected
deal structure, operator approval, signed term, access grant, transfer, or observed pilot.

## 1. Candidate decision record

Create one record per product-ledger key. A public record may name a public repository. A private
record stays in sanctioned private custody and exports only an opaque candidate ID plus aggregate
counts.

| Field | Required content |
| --- | --- |
| Candidate identity | Public repository or opaque private candidate ID |
| Lineage | Product-ledger source, predecessor/successor, current owner, and custody receipt |
| Visibility | Public or private; classification never changes visibility |
| Current state | Active repository, archived, superseded, experiment, proof, or operating product |
| Demand | Tier, score, dated sources, limitations, next experiment, and stop condition |
| Readiness | Dimension scores, exact-head receipts, missing evidence, and blocker owners |
| Economics | Unit of value, cost/runway scenario, transfer trigger, and park/kill rule |
| Operator state | None, sourced, diligence, synthetic trial, terms, pilot, returned, or terminated |
| Access/custody | Current access class, owner, changes, revocation route, and return owner |
| Decision | Experiment, park, kill, diligence, transfer candidate, return, or continue |
| Receipt | Reviewer, date, exact heads, predicate, evidence URLs, and rollback state |

Decision rules:

- Missing evidence is recorded as missing and scores zero.
- A repository is not a product outcome, a homepage is not liveness, activity is not demand, and
  internal use is not market validation.
- A high aggregate score cannot override a security, data, IP, contributor, credential, conflict,
  legal-capacity, or return-path blocker.
- A private detail cannot be copied into a public decision record to make the record easier to read.

## 2. Demand evidence review

For each candidate, complete this ordered review:

1. Record public attention and fork signals without implying adoption.
2. Locate any consented problem, activation, retention, buying-intent, payment, or operating receipt.
3. Bind every receipt to its date, method, denominator, exact source, and limitations.
4. Assign E0-E5 from the canonical contract.
5. Write the cheapest bounded experiment that could move exactly one missing evidence class.
6. State the stop condition before running the experiment.

Experiment brief:

```text
Candidate ID:
Current tier / score:
Evidence gap:
Hypothesis:
Audience and consent boundary:
Method:
Maximum time/cost:
Success threshold:
Failure threshold:
Stop/park action:
External send gate, if any:
Receipt target:
```

No experiment begins from this preflight. Interviews, outreach, publication, paid traffic, and
operator recruiting require their own authority and gate.

## 3. Technical, custody, and maintenance diligence

The full review uses the eight weighted dimensions in the machine contract. Every dimension gets
one of `pass`, `fail`, `blocked`, or `unverified`; only a dated reproducible receipt can produce
`pass`.

### Build and test

- exact default-branch head and environment;
- dependency lock and reproducible install;
- unit, integration, end-to-end, migration, and recovery predicates as applicable;
- failing, skipped, flaky, or environment-blocked tests separated from passes;
- artifact digest and rollback point.

### Deploy and runtime

- actual deployment path, owner, environment, and release address;
- health, smoke, observability, backup, restore, and rollback receipts;
- external services, costs, quotas, billing owner, and credential boundary;
- liveness distinguished from a configured homepage or historical deployment.

### Security, data, and privacy

- data inventory, classification, source, lawful basis/consent, retention, deletion, and export;
- secret and credential inventory by name/class only, never value;
- dependency and vulnerability posture, incident route, least privilege, and revocation;
- production/customer/private data excluded from synthetic trials.

### IP and custody

- repository, domain, package, account, trademark, content, model, dataset, and key ownership;
- license compatibility, contributor rights, forks, generated material, and third-party restrictions;
- current custodian, successor custodian, return owner, redirect/restore behavior, and archive custody;
- no transfer while any owner, license, contributor, or return fact is disputed.

### Maintenance

- named maintainer and backup owner;
- response/repair window and realistic monthly owner time;
- recurring infrastructure, support, security, compliance, and dependency cost;
- abandonment, park, archive, and emergency-return triggers.

## 4. Operator profile and scorecard

Evidence for each score must cite a reference, work sample, dated interview, legal/capacity record,
or synthetic trial result. Enthusiasm is not a score source.

| Dimension | Weight | Evidence examples |
| --- | ---: | --- |
| Demand access | 20 | Real domain channel, problem ownership, qualified audience, or buying process |
| Domain credibility | 15 | Relevant operating history, references, regulation, and counterpart trust |
| Execution discipline | 15 | Plans, cadence, decisions, incident handling, and completed outcomes |
| Security/data stewardship | 15 | Least privilege, privacy practice, incidents, audits, and return behavior |
| Financial discipline | 10 | Forecasting, collections, controls, downside planning, and reporting |
| Product stewardship | 10 | User empathy, quality, maintenance, prioritization, and deprecation |
| Governance/communication | 10 | Transparent reporting, escalation, records, and disagreement handling |
| Conflict transparency | 5 | Disclosures, independence, related parties, and remedies |

Scoring sheet:

```text
Opaque operator ID:
Candidate product ID:
Evidence date:
Dimension scores (0-5) and sources:
Weighted total:
Hard-decline review:
Human-review review:
References checked:
Conflicts and remedies:
Capacity / beneficial ownership / sanctions status:
Proposed route: proceed | diligence | trial | decline | human_review
Reviewer and independent challenge:
Access class after decision:
Rollback / next review date:
```

## 5. Diligence checklist

The operator pipeline may advance only when the current stage is complete. Unknowns never inherit
an optimistic value.

### Identity and capacity

- verified legal/person identity and authority to act;
- beneficial ownership, conflicts, sanctions, litigation, insolvency, and regulatory constraints;
- insurance and professional/corporate capacity where material;
- no undisclosed intermediary or side agreement.

### Domain and demand

- domain thesis and problem evidence;
- access to the claimed audience/channel;
- referenceable operating outcomes and failure history;
- acquisition, activation, service, and support plan.

### Execution and governance

- 30/60/90-day operating plan, decision cadence, and named people;
- metrics, books/records, issue escalation, security incident, and change-control practice;
- willingness to accept audit, least privilege, revocation, termination, and return;
- continuity if the primary operator becomes unavailable.

### Economics

- downside/base/upside assumptions and sources;
- direct, support, maintenance, security, compliance, payment, and tax costs;
- cash and owner-time runway;
- attribution, reporting, audit, reserve, clawback, and tail treatment;
- no undisclosed compensation or conflicting incentive.

### Access and custody

- access-stage request and purpose;
- data/credential/repository/domain/IP boundary;
- logging, expiry, revocation, deletion, restore, and return test;
- responsible owner for every asset and system.

## 6. Structure comparison and issue spotting

No structure is preferred by this template. The correct structure derives from the candidate,
operator, jurisdiction, tax, liability, data, financing, and custody evidence, then receives owner
and qualified-counsel approval.

| Option | Owner retains | Operator may receive after approval | Principal risks | Return mechanism |
| --- | --- | --- | --- | --- |
| Revocable operating license | IP and underlying custody | Narrow field/territory/term license | Scope creep, sublicensing, data, implied exclusivity | Termination, revocation, deletion/return receipt |
| Performance revenue share | IP and custody | Defined share of collected value | Attribution, expenses, audit, chargebacks, tail | Reconciliation, authority stop, access/asset return |
| Performance-vesting venture | Reserved rights until vesting | Milestone-based equity or rights | Dilution, tax, deadlock, control, repurchase | Unvested lapse, repurchase, license/data return |
| Custody-preserving mandate | Repository, account, domain, IP, data custody | Bounded operating decisions | Agency, credential abuse, service/incident risk | Mandate termination, access revoke, runbook handover |
| Time-boxed option trial | Every right and asset | Synthetic/isolated evaluation only | Implied license, data leakage, option ambiguity | Automatic expiry, sandbox teardown, deletion receipt |

Every draft must address:

```text
Parties, capacity, and purpose
Defined product/assets and excluded assets
IP ownership and license grant (if any)
Data roles, privacy, retention, deletion, and cross-border processing
Access class, credentials, repositories, domains, accounts, and change control
Decision rights, reserved matters, governance, records, and audit
Economics, waterfall, costs, reserves, taxes, attribution, payment, and clawback
Performance milestones, service levels, acceptance, and remedies
Security, incident response, business continuity, backup, restore, and insurance
Confidentiality, publicity, claims, references, and brand use
Subcontracting, assignment, sublicensing, change of control, and conflicts
Term, suspension, termination, transition, return, deletion, and surviving duties
Liability, indemnity, warranty, dispute, governing law, and counsel review
Signature authority and complete human-gate receipt
```

No clause, amount, entity, jurisdiction, percentage, valuation, or operator-specific fact is filled
in here.

## 7. Pipeline and access ledger

Access is monotonic only after a satisfied gate and is always revocable. A stage change creates a
receipt; it does not inherit authority from chat or a prior synthetic drill.

| Stage | Maximum access | Mandatory exit evidence |
| --- | --- | --- |
| Source | Public metadata | Criteria match; no contact yet |
| Consented intro | Public material | Consent, identity class, conflicts, and purpose |
| Desk diligence | Public + redacted | Identity, capacity, references, sanctions/conflicts |
| Structured diligence | Approved redacted private material | Scorecard, security/data/economics review |
| Synthetic trial | Invented data + isolated sandbox | Safe/denied paths, teardown, and custody receipt |
| Terms review | No new access | Approved structure and signed gates outside automation |
| Bounded pilot | Signed least-privilege scope only | Baseline, telemetry, cadence, incident, and return readiness |
| Decision | Decision-specific | Continue/revise/return/terminate plus custody accounting |

Access ledger row:

```text
Opaque operator ID / candidate ID:
Stage:
Requested capability:
Purpose and minimum scope:
Approver / human-gate receipt:
Granted scope and expiry:
Systems/data explicitly excluded:
Logging and review cadence:
Revocation command/owner:
Return/deletion test:
Current state:
```

## 8. Bounded pilot charter template

This template remains blank until all entry predicates and human gates pass.

```text
Pilot ID:
Product candidate ID:
Operator ID:
Structure and signed receipt:
Exact product/repository heads:
Start / decision date (maximum 28 days):
Problem and demand evidence:
Transfer-floor receipt:
In-scope operating decisions:
Out-of-scope decisions and assets:
Access matrix and expiries:
Data classes and prohibited inputs:
Baseline metrics:
Outcome / quality / reliability metrics:
Security and privacy telemetry:
Operator and owner time:
Direct and maintenance cost:
Weekly review owners:
Midpoint access/economics audit:
Incident, pause, and termination triggers:
Revocation / restore / return procedure and tested receipt:
Day-28 decision: continue | revise | return | terminate
Complete custody accounting:
```

The synthetic rehearsal fills none of these fields with real values. It proves only that invented
records can traverse the safe stages, that forbidden access is denied, and that owner custody is
unchanged at the end.

## 9. Return, termination, and custody restoration

1. Freeze new authority and record the trigger.
2. Capture exact product, data, access, account, domain, and telemetry state.
3. Suspend/revoke temporary access and rotate affected credentials through the credential owner.
4. Stop operator-controlled deploy, payment, message, or data-processing routes as the signed terms
   permit.
5. Return repositories, branches, packages, domains, accounts, data, documentation, and in-flight
   work to the named custodian.
6. Verify deletion/return, backup/restore, redirects, and ongoing data/legal obligations.
7. Reconcile economics, expenses, reserves, chargebacks, tail, IP, and surviving duties.
8. Decide continue, revise, re-source, park, kill, or archive with an independent review.
9. Write the immutable decision and custody receipt; preserve evidence without exposing private
   identities.

Emergency action may reduce access to contain harm, but it cannot silently decide ownership,
economics, or long-term disposition.

## 10. Institutional review record

```text
Review date / cadence / trigger:
Candidate and operator IDs:
Current demand, readiness, operator, and economics scores:
Score/evidence changes since prior review:
Access and custody inventory:
Security, data, service, financial, and conflict events:
Threshold / covenant / gate breaches:
Return readiness result:
Independent challenge and response:
Decision and rationale:
Next experiment / action / owner / date:
Park, kill, return, or rollback action:
Evidence and exact-head receipts:
```

The monthly review owns the experiment/park/kill queue. The quarterly review owns operator,
economics, access, custody, and return readiness. Event review handles harm or boundary breaches.
The annual review updates rubrics and structure templates with qualified counsel; it never rewrites
historical receipts.

## Completion boundary

This playbook becomes formal leaf evidence only after the exact assigned leaf executor obtains a
broker lease, the relevant predecessor and target-repository state is current, the non-circular
predicate passes, and a structured receipt is durable. Until then it remains useful preflight and
cannot be cited as operator acceptance, legal approval, asset transfer, pilot observation, or phase
completion.
