# Sovereign Systems — MACRO FACE
## ORGANVM-as-a-service: the institutional toolkit

*The platform form of the consulting organ · Available to any founder, operator, or institution*

> **What you are reading:** the macro face is what an outside operator holds — the portable,
> reusable body of this organ before any client name is in it. The micro instance (Maddie / Rob / Derek)
> proves it in practice. That proof is in [`MICRO-FACE.md`](MICRO-FACE.md).

---

## The problem this solves

Most well-intentioned teams are beaten by well-resourced ones not because of raw ability but
because of **institutional weight** — the fixed routines, structured memory, and disciplined
operating floors that turn good intent into reliable outcomes.

A top-tier agency doesn't wing its intakes. It doesn't lose scope between calls. It doesn't
hand off deliverables without a quality gate. Its junior doesn't forget what was promised in
the last meeting because there's a system that remembers.

Sovereign Systems gives a solo operator, a two-person founding team, or an independent
contractor **the same institutional floor** — without the overhead of hiring a firm.

---

## What Sovereign Systems is

A **structured consulting-operations toolkit** that runs the five functions that agencies
do better than individuals:

| Function | What it produces |
|---|---|
| **Intake** | A single client posture record: who the client is, what they actually need, what constraints apply |
| **Scope** | A proposal-grade engagement hypothesis with explicit inclusions, exclusions, and assumptions |
| **Delivery** | A sequenced milestone map with named owners and human review gates at each checkpoint |
| **Quality** | A per-deliverable audit against the agreed standard before any handoff |
| **Archive** | A closed-engagement package: what was promised, built, deferred, and left open |

Each function is repeatable. Each feeds the next. The whole system can be held by one person.

---

## The five-primitive kernel

Every engagement is structured around five primitives. The same map works in any domain,
for any client type:

| Primitive | In consulting | Concretely |
|---|---|---|
| **Member** | the client | who they are, their constraints, their consent, their context |
| **Mandate** | the engagement | what outcome was hired for, in language both sides can sign |
| **Standing** | delivery posture | exactly where the engagement sits right now: discovery, proposal, acceptance, execution, review, hold, or archived |
| **Standard** | the quality bar | what a good deliverable looks like, per phase, per client — explicit, not assumed |
| **Governance** | the authority map | who decides what, what requires explicit approval, what cannot be sent or promised by the system |

The engagement can only move forward when each primitive is named. No drifting mandates. No
silent scope changes. No unreviewed handoffs.

---

## The delivery posture sequence

```
DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION → REVIEW → ARCHIVED
                                                      ↓
                                                    HOLD
```

An engagement's standing can advance; it cannot regress silently. A scope change is logged
explicitly and approved before it takes effect. A hold is declared, not assumed.

This is the standard a boutique agency enforces through staff and process. Here it is enforced
through the posture record itself.

---

## What the operator actually receives

1. **A client posture file** — one record per engagement: member, mandate, standing, standards,
   human gates, scope boundary, and scope change log.
2. **A proposal-grade scope draft** — ready for partner review before any external send.
3. **A milestone execution map** — staged, owned, and gated. No one-step commits to a full outcome.
4. **A deliverable review log** — quality notes, missing evidence markers, and next-step list
   before each handoff.
5. **A closeout archive** — what was promised, delivered, deferred, and unresolved. The record
   the next cycle starts from.

---

## What this is not

This toolkit does not replace the operator's judgment. It does not send proposals, execute
contracts, bill clients, or make commitments. Every external act stays with the human
partner — staged, surfaced, reviewed.

It also does not provide legal, tax, or medical advice. It is **delivery infrastructure**,
not professional services.

The constraint is a feature. It enforces the boundary that protects the operator's license
to practice and their client's trust.

---

## Who holds this platform

The macro form of Sovereign Systems is intentionally generic:

- No hardcoded client names
- No private pricing assumptions
- No personality-specific idiom

A founder running three simultaneous client threads, a freelance operator managing recurring
work with two partners, or an agency principal trying to turn a chaotic delivery history into
a repeatable model — all three hold the same toolkit and fill in their own Member, Mandate,
and Standard.

The proof that it holds across different clients, different idioms, and different delivery
rhythms is the micro instance.

---

## Governance layer (the authority contract, plainly stated)

The organ runs the engagement system. The operator runs the engagement.

| What the organ does | What the operator does |
|---|---|
| Captures intake, structures scope | Strategic accept/reject, final scope call |
| Sequences milestones, tracks standing | Approves reprioritization and external commitments |
| Drafts deliverables, flags quality gaps | Signs off each handoff slice |
| Stages outbound artifacts for review | Sends, signs, and commits externally |

No autonomous external send. No autonomous billing. No autonomous contract execution.
The operator is the final authority for every outward-facing action.

---

## Current stage and validation

The macro platform is **60% mature** (maturing stage). The engagement posture rules are
executable and validated by `validate-consulting.py`. The first micro proof (three active
deployments) passes all six rules. The face is polished. The remaining lift is to close
the intake-to-closeout cycle completely for all three micro deployments and operationalize
the handoff archive.

Validation:

```bash
python organs/consulting/validate-consulting.py --fleet
```

---

*Companion documents: [KERNEL.md](KERNEL.md) (architecture + 5-primitive map),
[CHARTER.md](CHARTER.md) (org chart + workflows), [MICRO-FACE.md](MICRO-FACE.md)
(live engagement record for Maddie / Rob / Derek).*
