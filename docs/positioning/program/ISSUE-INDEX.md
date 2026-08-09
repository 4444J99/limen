# Production-Systems Program issue index

Generated from `institutio/positioning/program.yaml` and `institutio/positioning/github-map.json`. Do not edit by hand.

- Phases: **15**
- Atomic work packets: **111**
- Total projected GitHub objects: **127**

## Phases

| Phase | Issue | Leaves | Depends on | Exit gate |
|---|---:|---:|---|---|
| `PSP-P00` Program control plane | `PSP-P00` | 7 | — | All P00 leaves close and remote parity reports zero missing, duplicate, or orphan markers. |
| `PSP-P01` Foundation repair and upstream integration | `PSP-P01` | 5 | `PSP-P00` | PRs 2136 and 2141 have terminal owners; canonical sources are reconciled and baseline receipts are frozen. |
| `PSP-P02` Truth and evidence control plane | `PSP-P02` | 8 | `PSP-P01` | All selected flagships have evidence packets and every material or disputed claim has separate measurement, inference, implication, prominence, source, date, and staleness verdicts. |
| `PSP-P03` Position, narrative, and audience architecture | `PSP-P03` | 7 | `PSP-P02` | Target readers understand what is offered, why it is credible, and what to do next without an oral explanation. |
| `PSP-P04` Offer and commercial architecture | `PSP-P04` | 7 | `PSP-P03` | Audit, install, and retainer each have scope, exclusions, qualification, artifacts, economics, and contract boundaries. |
| `PSP-P05` Proof-production program | `PSP-P05` | 6 | `PSP-P02`, `PSP-P03`, `PSP-P04` | The six declared proof classes exist, are public-safe, and link back to current evidence rows. |
| `PSP-P06` Portfolio experience and progressive disclosure | `PSP-P06` | 7 | `PSP-P03`, `PSP-P05` | Tested designs satisfy progressive disclosure, audience routing, accessibility, performance, and visual quality. |
| `PSP-P07` Public surfaces and deployment | `PSP-P07` | 9 | `PSP-P02`, `PSP-P03`, `PSP-P05`, `PSP-P06` | All tracked public surfaces are coherent, live, linked, rollback-safe, and verified in rendered form. |
| `PSP-P08` Inbound capture and private lead operations | `PSP-P08` | 7 | `PSP-P04`, `PSP-P07` | Client and recruiter synthetic leads traverse capture, classification, routing, drafting, and reporting while no-send stays enforced. |
| `PSP-P09` Proof-led content and distribution | `PSP-P09` | 8 | `PSP-P05`, `PSP-P07`, `PSP-P08` | The flagship report and derived series are staged, owner-published where approved, measured, and linked to qualified capture. |
| `PSP-P10` Qualification, conversation, and conversion system | `PSP-P10` | 8 | `PSP-P04`, `PSP-P08`, `PSP-P09` | Client and recruiter playbooks, pipeline stages, proposal rules, objection capture, and the 90-day experiment work end to end. |
| `PSP-P11` Service-delivery operating system | `PSP-P11` | 8 | `PSP-P04` | A synthetic engagement traverses intake, evidence, analysis, verdict, implementation, QA, handoff, and closeout under the declared boundaries. |
| `PSP-P12` External validation and first commercial proof | `PSP-P12` | 6 | `PSP-P09`, `PSP-P10`, `PSP-P11` | The first audit outcome, external proof, and claims refresh are complete or the wedge has an evidence-backed invalidation receipt. |
| `PSP-P13` Governed foundry and domain-operator handoff | `PSP-P13` | 9 | `PSP-P02`, `PSP-P04`, `PSP-P11`, `PSP-P12` | The entire product estate is scored and one transfer reaches observed operation or an evidence-backed no-go decision. |
| `PSP-P14` Return loop, measurement, rollback, and Omega | `PSP-P14` | 9 | `PSP-P07`, `PSP-P08`, `PSP-P09`, `PSP-P10`, `PSP-P11`, `PSP-P12`, `PSP-P13` | Two unchanged remote checks prove complete issue coverage, current claims, healthy surfaces, closed loops, and terminal receipts. |

## PSP-P00 — Program control plane

One validated source graph projects a complete, non-duplicative, provider-neutral issue system.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P00-W01` Commit the canonical alpha-to-omega program manifest | `PSP-P00-W01` | `organvm/limen` | `deep` | `write` | — |
| `PSP-P00-W02` Build structural validation and dependency-cycle detection | `PSP-P00-W02` | `organvm/limen` | `routine` | `write` | `PSP-P00-W01` |
| `PSP-P00-W03` Build idempotent GitHub milestone, label, and issue projection | `PSP-P00-W03` | `organvm/limen` | `deep` | `external` | `PSP-P00-W02` |
| `PSP-P00-W04` Publish cross-agent work-packet and relay contracts | `PSP-P00-W04` | `organvm/limen` | `deep` | `write` | `PSP-P00-W01` |
| `PSP-P00-W05` Expose ready-work and provider-neutral packet seeds | `PSP-P00-W05` | `organvm/limen` | `deep` | `write` | `PSP-P00-W02` |
| `PSP-P00-W06` Prove issue-map parity and zero orphan program work | `PSP-P00-W06` | `organvm/limen` | `routine` | `read` | `PSP-P00-W03`, `PSP-P00-W05` |
| `PSP-P00-W07` Connect ready leaves to the authenticated conduct broker | `PSP-P00-W07` | `organvm/limen` | `deep` | `write` | `PSP-P00-W05`, `PSP-P00-W06` |

## PSP-P01 — Foundation repair and upstream integration

Existing truth and custody foundations merge on green CI and become the program's baseline.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P01-W01` Fix the wall-clock-dependent throughput-governor test | `PSP-P01-W01` | `organvm/limen` | `routine` | `write` | `PSP-P00-W06` |
| `PSP-P01-W02` Land the positioning truth-reconciliation foundation | `PSP-P01-W02` | `organvm/limen` | `deep` | `external` | `PSP-P01-W01` |
| `PSP-P01-W03` Land encrypted custody for private evidence artifacts | `PSP-P01-W03` | `organvm/limen` | `deep` | `external` | `PSP-P01-W01` |
| `PSP-P01-W04` Reconcile old positioning doctrine and generators against the new truth contract | `PSP-P01-W04` | `organvm/limen` | `deep` | `write` | `PSP-P01-W02` |
| `PSP-P01-W05` Freeze the post-merge public-surface baseline | `PSP-P01-W05` | `organvm/limen` | `routine` | `read` | `PSP-P01-W02`, `PSP-P01-W03`, `PSP-P01-W04` |

## PSP-P02 — Truth and evidence control plane

Every public statement is reproducible, classified, dated, bounded, and reversible.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P02-W01` Discover every organization and repository the owner controls | `PSP-P02-W01` | `organvm/limen` | `routine` | `read` | `PSP-P01-W05` |
| `PSP-P02-W02` Classify the full estate by role, maturity, visibility, and public relevance | `PSP-P02-W02` | `organvm/limen` | `deep` | `write` | `PSP-P02-W01` |
| `PSP-P02-W03` Score and ratify the flagship proof set | `PSP-P02-W03` | `organvm/limen` | `frontier_review` | `write` | `PSP-P02-W02` |
| `PSP-P02-W04` Build a complete evidence packet for every selected flagship | `PSP-P02-W04` | `organvm/limen` | `deep` | `write` | `PSP-P02-W03` |
| `PSP-P02-W05` Make every material metric and claim reproducible | `PSP-P02-W05` | `organvm/limen` | `deep` | `write` | `PSP-P02-W04` |
| `PSP-P02-W06` Enforce claim policy, staleness, and privacy in generation gates | `PSP-P02-W06` | `organvm/limen` | `deep` | `write` | `PSP-P02-W05` |
| `PSP-P02-W07` Establish public correction, withdrawal, and source-change protocol | `PSP-P02-W07` | `organvm/limen` | `deep` | `write` | `PSP-P02-W06` |
| `PSP-P02-W08` Adjudicate research criticisms against the live profile and primary sources | `PSP-P02-W08` | `organvm/limen` | `frontier_review` | `write` | `PSP-P02-W01`, `PSP-P02-W05` |

## PSP-P03 — Position, narrative, and audience architecture

One legible identity and two audience doors communicate authority without scale theater or takeover threat.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P03-W01` Ratify the production-systems architect identity contract | `PSP-P03-W01` | `organvm/limen` | `frontier_review` | `write` | `PSP-P02-W05`, `PSP-P02-W06`, `PSP-P02-W08` |
| `PSP-P03-W02` Define the client, recruiter, and deeper operator jobs-to-be-done | `PSP-P03-W02` | `organvm/limen` | `deep` | `write` | `PSP-P03-W01` |
| `PSP-P03-W03` Write the ten-second, five-minute, and diligence narrative ladder | `PSP-P03-W03` | `organvm/limen` | `deep` | `write` | `PSP-P03-W02` |
| `PSP-P03-W04` Create the client-facing narrative and expensive-problem map | `PSP-P03-W04` | `organvm/limen` | `deep` | `write` | `PSP-P03-W03` |
| `PSP-P03-W05` Create the recruiter-facing narrative and role map | `PSP-P03-W05` | `organvm/limen` | `deep` | `write` | `PSP-P03-W03` |
| `PSP-P03-W06` Design language that reduces the spy or takeover threat response | `PSP-P03-W06` | `organvm/limen` | `deep` | `write` | `PSP-P03-W04`, `PSP-P03-W05` |
| `PSP-P03-W07` Run blinded target-reader comprehension and trust tests | `PSP-P03-W07` | `organvm/limen` | `routine` | `read` | `PSP-P03-W06` |

## PSP-P04 — Offer and commercial architecture

The commercial wedge is sellable, bounded, economically coherent, and expandable without becoming unbounded consulting.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P04-W01` Productize the Agentic Delivery Audit | `PSP-P04-W01` | `organvm/limen` | `frontier_review` | `write` | `PSP-P03-W04`, `PSP-P02-W04` |
| `PSP-P04-W02` Productize the Governance Install | `PSP-P04-W02` | `organvm/limen` | `deep` | `write` | `PSP-P04-W01` |
| `PSP-P04-W03` Define the bounded delivery-governance retainer | `PSP-P04-W03` | `organvm/limen` | `deep` | `write` | `PSP-P04-W02` |
| `PSP-P04-W04` Define qualification, disqualification, and escalation criteria | `PSP-P04-W04` | `organvm/limen` | `deep` | `write` | `PSP-P04-W01`, `PSP-P04-W02`, `PSP-P04-W03` |
| `PSP-P04-W05` Model internal pricing, capacity, and discount guardrails | `PSP-P04-W05` | `organvm/limen` | `deep` | `write` | `PSP-P04-W01`, `PSP-P04-W02`, `PSP-P04-W03` |
| `PSP-P04-W06` Create proposal, SOW, and commercial-decision templates | `PSP-P04-W06` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P04-W04`, `PSP-P04-W05` |
| `PSP-P04-W07` Define the product-partnership offer without making it a front-door distraction | `PSP-P04-W07` | `organvm/limen` | `frontier_review` | `write` | `PSP-P04-W04` |

## PSP-P05 — Proof-production program

High-value claims are demonstrated through compact, reproducible proof objects rather than volume theater.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P05-W01` Publish the Limen engineering report source package | `PSP-P05-W01` | `organvm/limen` | `frontier_review` | `write` | `PSP-P02-W05`, `PSP-P03-W03`, `PSP-P04-W01` |
| `PSP-P05-W02` Reconcile every public surface against the claims contract | `PSP-P05-W02` | `organvm/limen` | `deep` | `write` | `PSP-P05-W01`, `PSP-P02-W06` |
| `PSP-P05-W03` Produce cost-per-task and failure-mode analysis | `PSP-P05-W03` | `organvm/limen` | `deep` | `write` | `PSP-P05-W01` |
| `PSP-P05-W04` Create fresh test-reproduction receipts for flagship claims | `PSP-P05-W04` | `organvm/limen` | `routine` | `read` | `PSP-P02-W04` |
| `PSP-P05-W05` Build a public-safe Limen architecture demonstration | `PSP-P05-W05` | `organvm/limen` | `deep` | `write` | `PSP-P05-W01`, `PSP-P02-W02` |
| `PSP-P05-W06` Produce external validation objects | `PSP-P05-W06` | `organvm/limen` | `deep` | `write` | `PSP-P05-W04`, `PSP-P05-W05` |

## PSP-P06 — Portfolio experience and progressive disclosure

The public experience feels precise and premium while the estate's density remains available on demand.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P06-W01` Establish the design context and taste brief | `PSP-P06-W01` | `organvm/portfolio` | `deep` | `write` | `PSP-P03-W03`, `PSP-P05-W01` |
| `PSP-P06-W02` Model the content and navigation architecture | `PSP-P06-W02` | `organvm/portfolio` | `deep` | `write` | `PSP-P06-W01`, `PSP-P03-W02` |
| `PSP-P06-W03` Design L1, L2, and L3 progressive-disclosure flows | `PSP-P06-W03` | `organvm/portfolio` | `frontier_review` | `write` | `PSP-P06-W02` |
| `PSP-P06-W04` Define reusable components and evidence-bound content interfaces | `PSP-P06-W04` | `organvm/portfolio` | `deep` | `write` | `PSP-P06-W03`, `PSP-P02-W06` |
| `PSP-P06-W05` Adopt the approved estate design tokens without flattening surface character | `PSP-P06-W05` | `organvm/portfolio` | `deep` | `write` | `PSP-P06-W04` |
| `PSP-P06-W06` Verify accessibility, responsiveness, performance, and reduced motion | `PSP-P06-W06` | `organvm/portfolio` | `routine` | `write` | `PSP-P06-W04`, `PSP-P06-W05` |
| `PSP-P06-W07` Run visual and comprehension QA with target-like users | `PSP-P06-W07` | `organvm/portfolio` | `frontier_review` | `read` | `PSP-P06-W06` |

## PSP-P07 — Public surfaces and deployment

Every identity and proof surface derives from the same truth while retaining a reversible release path.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P07-W01` Preserve, audit, and evolve the personal GitHub profile front door | `PSP-P07-W01` | `4444J99/4444J99` | `deep` | `write` | `PSP-P02-W08`, `PSP-P03-W03`, `PSP-P05-W02`, `PSP-P06-W04` |
| `PSP-P07-W02` Rebuild the organization profile as an estate map | `PSP-P07-W02` | `organvm/.github` | `deep` | `write` | `PSP-P02-W02`, `PSP-P03-W03` |
| `PSP-P07-W03` Implement and deploy the canonical portfolio site | `PSP-P07-W03` | `organvm/portfolio` | `deep` | `external` | `PSP-P06-W07`, `PSP-P05-W02` |
| `PSP-P07-W04` Rebuild the resume and interview evidence packet | `PSP-P07-W04` | `organvm/portfolio` | `deep` | `write` | `PSP-P03-W05`, `PSP-P05-W02` |
| `PSP-P07-W05` Upgrade selected flagship repositories as proof destinations | `PSP-P07-W05` | `multi-repository:selected-flagships` | `routine` | `write` | `PSP-P02-W04`, `PSP-P03-W03` |
| `PSP-P07-W06` Stage the LinkedIn, X, and email-signature identity package | `PSP-P07-W06` | `organvm/limen` | `deep` | `write` | `PSP-P03-W03`, `PSP-P03-W05` |
| `PSP-P07-W07` Attach the approved custom-domain hierarchy | `PSP-P07-W07` | `organvm/limen` | `routine` | `external` | `PSP-P07-W03` |
| `PSP-P07-W08` Install privacy-respecting funnel analytics and door tags | `PSP-P07-W08` | `organvm/portfolio` | `deep` | `write` | `PSP-P07-W03`, `PSP-P03-W02` |
| `PSP-P07-W09` Prove link health, release rollback, and surface parity | `PSP-P07-W09` | `organvm/limen` | `routine` | `write` | `PSP-P07-W01`, `PSP-P07-W02`, `PSP-P07-W03`, `PSP-P07-W04`, `PSP-P07-W05`, `PSP-P07-W06`, `PSP-P07-W07`, `PSP-P07-W08` |

## PSP-P08 — Inbound capture and private lead operations

Qualified interest enters a safe, tagged, private pipeline with no unauthorized outbound effect.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P08-W01` Activate a dedicated inbound alias and tagged CTAs | `PSP-P08-W01` | `organvm/limen` | `routine` | `external` | `PSP-P07-W09` |
| `PSP-P08-W02` Design minimal client and recruiter intake flows | `PSP-P08-W02` | `organvm/portfolio` | `deep` | `write` | `PSP-P04-W04`, `PSP-P08-W01` |
| `PSP-P08-W03` Normalize inbound mail and form submissions into private lead records | `PSP-P08-W03` | `organvm/universal-mail--automation` | `deep` | `write` | `PSP-P08-W02` |
| `PSP-P08-W04` Score and route client, recruiter, operator, spam, and ambiguous leads | `PSP-P08-W04` | `organvm/limen` | `deep` | `write` | `PSP-P08-W03`, `PSP-P04-W04` |
| `PSP-P08-W05` Create reply, scheduling, decline, and recruiter draft templates | `PSP-P08-W05` | `organvm/universal-mail--automation` | `routine` | `write` | `PSP-P08-W04`, `PSP-P04-W04` |
| `PSP-P08-W06` Build the private opportunity pipeline and decision ledger | `PSP-P08-W06` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P08-W03`, `PSP-P08-W04` |
| `PSP-P08-W07` Prove the capture funnel end to end with the send valve closed | `PSP-P08-W07` | `multi-repository:limen-portfolio-mail` | `deep` | `read` | `PSP-P08-W01`, `PSP-P08-W02`, `PSP-P08-W03`, `PSP-P08-W04`, `PSP-P08-W05`, `PSP-P08-W06` |

## PSP-P09 — Proof-led content and distribution

One flagship proof becomes a durable content engine whose derivatives attract qualified demand without claim drift.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P09-W01` Build the 90-day proof-led editorial calendar | `PSP-P09-W01` | `organvm/limen` | `deep` | `write` | `PSP-P05-W01`, `PSP-P04-W04` |
| `PSP-P09-W02` Stage and owner-publish the flagship Limen engineering report | `PSP-P09-W02` | `organvm/portfolio` | `frontier_review` | `external` | `PSP-P05-W01`, `PSP-P07-W09`, `PSP-P08-W07` |
| `PSP-P09-W03` Derive the agentic-delivery failure-modes essay | `PSP-P09-W03` | `organvm/portfolio` | `deep` | `write` | `PSP-P05-W03`, `PSP-P09-W02` |
| `PSP-P09-W04` Derive the cost-per-task and control-economics essay | `PSP-P09-W04` | `organvm/portfolio` | `deep` | `write` | `PSP-P05-W03`, `PSP-P09-W02` |
| `PSP-P09-W05` Derive the delivery-gates walkthrough | `PSP-P09-W05` | `organvm/portfolio` | `deep` | `write` | `PSP-P05-W05`, `PSP-P09-W02` |
| `PSP-P09-W06` Publish a candid incident and correction case study | `PSP-P09-W06` | `organvm/portfolio` | `deep` | `write` | `PSP-P02-W07`, `PSP-P09-W02` |
| `PSP-P09-W07` Generate channel-specific derivative assets without claim drift | `PSP-P09-W07` | `organvm/limen` | `routine` | `write` | `PSP-P09-W03`, `PSP-P09-W04`, `PSP-P09-W05`, `PSP-P09-W06` |
| `PSP-P09-W08` Execute owner-approved distribution and record channel outcomes | `PSP-P09-W08` | `organvm-iii-ergon/collaboration-operations-platform` | `routine` | `external` | `PSP-P09-W07`, `PSP-P08-W07` |

## PSP-P10 — Qualification, conversation, and conversion system

Qualified client and recruiter demand moves through repeatable decisions without over-selling or custom-scope sprawl.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P10-W01` Define the ideal client profile and live buying signals | `PSP-P10-W01` | `organvm/limen` | `deep` | `write` | `PSP-P04-W04`, `PSP-P09-W01` |
| `PSP-P10-W02` Build the client discovery-call guide | `PSP-P10-W02` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P10-W01`, `PSP-P04-W01` |
| `PSP-P10-W03` Build the pre-audit diagnostic questionnaire | `PSP-P10-W03` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P10-W02`, `PSP-P11-W01` |
| `PSP-P10-W04` Build the Agentic Delivery Audit sales page and intake path | `PSP-P10-W04` | `organvm/portfolio` | `deep` | `write` | `PSP-P04-W01`, `PSP-P08-W02`, `PSP-P10-W01` |
| `PSP-P10-W05` Implement proposal, follow-up, decision, and close-lost workflow | `PSP-P10-W05` | `organvm-iii-ergon/collaboration-operations-platform` | `routine` | `write` | `PSP-P04-W06`, `PSP-P08-W06`, `PSP-P10-W02` |
| `PSP-P10-W06` Build the recruiter conversation and interview packet | `PSP-P10-W06` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P03-W05`, `PSP-P03-W06`, `PSP-P07-W04` |
| `PSP-P10-W07` Operate a structured objection and no-outcome ledger | `PSP-P10-W07` | `organvm-iii-ergon/collaboration-operations-platform` | `routine` | `write` | `PSP-P10-W05`, `PSP-P10-W06` |
| `PSP-P10-W08` Run and adjudicate the 90-day demand experiment | `PSP-P10-W08` | `organvm/limen` | `frontier_review` | `write` | `PSP-P09-W08`, `PSP-P10-W07`, `PSP-P12-W02` |

## PSP-P11 — Service-delivery operating system

Audit, install, and retainer engagements can be delivered safely, consistently, and with reusable evidence.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P11-W01` Define read-only evidence intake and security boundaries | `PSP-P11-W01` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P04-W01` |
| `PSP-P11-W02` Build the Agentic Delivery Audit methodology and runbook | `PSP-P11-W02` | `organvm-iii-ergon/collaboration-operations-platform` | `frontier_review` | `write` | `PSP-P11-W01`, `PSP-P04-W01` |
| `PSP-P11-W03` Create the audit report and executive verdict template | `PSP-P11-W03` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P11-W02` |
| `PSP-P11-W04` Build the Governance Install delivery runbook | `PSP-P11-W04` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P11-W03`, `PSP-P04-W02` |
| `PSP-P11-W05` Build the bounded retainer operating contract | `PSP-P11-W05` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P11-W04`, `PSP-P04-W03` |
| `PSP-P11-W06` Build the private client workspace and decision log | `PSP-P11-W06` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P11-W01` |
| `PSP-P11-W07` Prove delivery QA, acceptance, handoff, and closeout | `PSP-P11-W07` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P11-W02`, `PSP-P11-W03`, `PSP-P11-W04`, `PSP-P11-W05`, `PSP-P11-W06` |
| `PSP-P11-W08` Define consent and sanitization for public client proof | `PSP-P11-W08` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P11-W07` |

## PSP-P12 — External validation and first commercial proof

Real users, buyers, recruiters, or partners create evidence beyond self-authored technical output.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P12-W01` Recruit a bounded design-partner cohort | `PSP-P12-W01` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `external` | `PSP-P09-W08`, `PSP-P10-W01`, `PSP-P11-W02` |
| `PSP-P12-W02` Close and deliver the first paid or explicitly bounded pilot audit | `PSP-P12-W02` | `organvm-iii-ergon/collaboration-operations-platform` | `frontier_review` | `external` | `PSP-P12-W01`, `PSP-P10-W05`, `PSP-P11-W07` |
| `PSP-P12-W03` Deliver the first Governance Install when the audit supports it | `PSP-P12-W03` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `external` | `PSP-P12-W02`, `PSP-P11-W04` |
| `PSP-P12-W04` Produce the first consented public case study | `PSP-P12-W04` | `organvm/portfolio` | `frontier_review` | `external` | `PSP-P12-W02`, `PSP-P11-W08` |
| `PSP-P12-W05` Capture testimonials, references, reproductions, and independent review | `PSP-P12-W05` | `organvm/limen` | `routine` | `write` | `PSP-P12-W02` |
| `PSP-P12-W06` Refresh positioning, proof, and offer claims from real outcomes | `PSP-P12-W06` | `organvm/limen` | `frontier_review` | `write` | `PSP-P12-W02`, `PSP-P12-W04`, `PSP-P12-W05`, `PSP-P02-W08` |

## PSP-P13 — Governed foundry and domain-operator handoff

The estate's product abundance becomes a scored portfolio whose validated products can transfer to accountable operators.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P13-W01` Inventory every product candidate across all owned organizations | `PSP-P13-W01` | `organvm/limen` | `routine` | `read` | `PSP-P02-W01`, `PSP-P02-W02` |
| `PSP-P13-W02` Score demand and market evidence for every product candidate | `PSP-P13-W02` | `organvm/limen` | `deep` | `write` | `PSP-P13-W01`, `PSP-P08-W06` |
| `PSP-P13-W03` Score technical readiness, custody, and maintenance risk | `PSP-P13-W03` | `organvm/limen` | `deep` | `write` | `PSP-P13-W01` |
| `PSP-P13-W04` Define the domain-operator profile and selection scorecard | `PSP-P13-W04` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P13-W02`, `PSP-P13-W03` |
| `PSP-P13-W05` Establish transfer floors, economics, and kill/park rules | `PSP-P13-W05` | `organvm/limen` | `deep` | `write` | `PSP-P13-W02`, `PSP-P13-W03` |
| `PSP-P13-W06` Design licensing, equity, revenue-share, custody, and return options | `PSP-P13-W06` | `organvm-iii-ergon/collaboration-operations-platform` | `frontier_review` | `write` | `PSP-P13-W04`, `PSP-P13-W05` |
| `PSP-P13-W07` Build the operator discovery, diligence, and trial pipeline | `PSP-P13-W07` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | `PSP-P13-W04`, `PSP-P13-W06` |
| `PSP-P13-W08` Execute one bounded operator-handoff pilot | `PSP-P13-W08` | `multi-repository:selected-product-and-private-platform` | `frontier_review` | `external` | `PSP-P13-W03`, `PSP-P13-W05`, `PSP-P13-W06`, `PSP-P13-W07` |
| `PSP-P13-W09` Institutionalize foundry governance and product return paths | `PSP-P13-W09` | `organvm/limen` | `deep` | `write` | `PSP-P13-W08` |

## PSP-P14 — Return loop, measurement, rollback, and Omega

Evidence, demand, delivery, and operator results continuously correct the system and converge without orphan work.

| Work ID | Issue | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|
| `PSP-P14-W01` Define the end-to-end event and KPI dictionary | `PSP-P14-W01` | `organvm/limen` | `deep` | `write` | `PSP-P07-W08`, `PSP-P08-W06`, `PSP-P11-W07`, `PSP-P13-W09` |
| `PSP-P14-W02` Operate the weekly execution and demand review | `PSP-P14-W02` | `organvm/limen` | `routine` | `write` | `PSP-P14-W01`, `PSP-P00-W07` |
| `PSP-P14-W03` Operate the monthly truth, surface, and privacy audit | `PSP-P14-W03` | `organvm/limen` | `deep` | `write` | `PSP-P02-W06`, `PSP-P02-W07`, `PSP-P07-W09` |
| `PSP-P14-W04` Operate the quarterly strategy and prominence review | `PSP-P14-W04` | `organvm/limen` | `frontier_review` | `write` | `PSP-P10-W08`, `PSP-P12-W06`, `PSP-P14-W01` |
| `PSP-P14-W05` Automate claim incident quarantine and correction propagation | `PSP-P14-W05` | `organvm/limen` | `deep` | `write` | `PSP-P02-W07`, `PSP-P07-W09` |
| `PSP-P14-W06` Automate release-level surface rollback and recovery verification | `PSP-P14-W06` | `multi-repository:public-surfaces` | `deep` | `external` | `PSP-P07-W09`, `PSP-P08-W07` |
| `PSP-P14-W07` Feed sales objections and demand outcomes back into offers | `PSP-P14-W07` | `organvm/limen` | `deep` | `write` | `PSP-P10-W07`, `PSP-P10-W08` |
| `PSP-P14-W08` Feed delivery and operator outcomes back into proof and portfolio classification | `PSP-P14-W08` | `organvm/limen` | `deep` | `write` | `PSP-P12-W06`, `PSP-P13-W08`, `PSP-P13-W09` |
| `PSP-P14-W09` Prove alpha-to-omega convergence in two unchanged passes | `PSP-P14-W09` | `organvm/limen` | `frontier_review` | `read` | `PSP-P14-W02`, `PSP-P14-W03`, `PSP-P14-W04`, `PSP-P14-W05`, `PSP-P14-W06`, `PSP-P14-W07`, `PSP-P14-W08` |
