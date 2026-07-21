# Phase 0 authority-and-ownership workshop

Status: **FACILITATOR READY / NOT CONDUCTED**

## Outcome

In one decision session, BBNC either declines the program or produces the inputs for an executed
website-modernization charter and a narrow Phase 1 discovery authorization. Silence, incomplete
attendance, or unresolved authority yields no commission.

## Required BBNC seats

- Executive sponsor
- Product owner
- Legal/compliance owner
- IT/security owner
- Records owner
- Communications owner
- Cultural-content steward
- Release authority

One person may hold multiple seats only when BBNC explicitly allows it and separation-of-duty rules
remain satisfied. Padavano attends as facilitator and proposed delivery party, not as a BBNC
decision-maker.

## Pre-read requested from BBNC

BBNC decides what may be shared. The workshop can proceed with summaries or owner attestations
instead of source documents.

- current authority hierarchy and delegation process;
- applicable security, privacy, retention, accessibility, and third-party requirements;
- identity and group ownership;
- current BBNC.net, WordPress, analytics, DNS/CDN, forms, media, and vendor ownership;
- myBBNC and external-system handoff owners;
- acceptance, release, incident, backup, and recovery processes;
- known distribution, enrollment, annual-meeting, and proxy blackout windows.

No Confidential or Restricted material enters the public prospect packet.

## 150-minute agenda

| Time | Decision block | Required output |
|---|---|---|
| 0-15 | Authority to meet | Attendance, decision rights, recusals, recording/retention rule |
| 15-35 | Product boundary | Stewardship, BBNC.net, preserved systems, v1 exclusions |
| 35-60 | Root authority | Authority hierarchy, policy owners, delegation and separation-of-duty rules |
| 60-80 | Data boundary | Allowed classifications, opaque-link rule, retention and export owners |
| 80-100 | Ownership | RACI, BBNC-owned accounts, Padavano access constraints, IP schedule |
| 100-120 | Acceptance | Work packages, predicates, change control, findings severity, dispute path |
| 120-135 | Security and continuity | Identity, environments, logging, backup, restore, incident, access review |
| 135-145 | Phase 1 authorization | Exact discovery scope, inputs, participant recruitment, receipt target |
| 145-150 | Read-back | Unresolved decisions, owners, dates, and explicit proceed/decline verdict |

## Decision rules

1. BBNC speaks for BBNC authority; Padavano records and reads back.
2. A title alone grants nothing. Every authority is tied to scope, effective dates, and delegation.
3. Unresolved classification defaults to Restricted and stays in its owner system.
4. Unresolved Phase 0 gates prevent Phase 1.
5. The workshop cannot authorize production access, public launch, or later work packages.
6. Changes to the charter require a new exact revision and renewed execution.

## Capture sequence

1. Record decisions in a BBNC-owned working copy of `preparation.json`.
2. Replace role-state entries with opaque BBNC principal references.
3. Attach gate evidence in BBNC's private owner systems.
4. Complete the charter; legal/compliance and release authority confirm the final exact revision.
5. Execute and store the charter in BBNC's private records owner.
6. Generate the redacted authority receipt defined in `acceptance.md`.
7. Run `validate-phase0.py authorize` before any Phase 1 repository, account, access, or discovery work.

## Terminal outcomes

- **Declined:** BBNC records the decision; Padavano archives or withdraws the prospect packet.
- **Deferred:** BBNC records owner, missing gate, and review date; no implementation begins.
- **Authorized:** the external authority predicate passes for Phase 1 discovery only.
