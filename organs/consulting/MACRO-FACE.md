# Sovereign Systems — MACRO FACE
## ORGANVM-as-a-service: the institutional toolkit

*The platform form of the consulting organ · Available to any founder, operator, or institution*

> **What you are reading:** the macro face is what an outside operator holds — the portable,
> reusable body of this organ before any client name is in it. The micro instance (Maddie / Rob / Derek)
> proves it in practice. That proof is in [`MICRO-FACE.md`](MICRO-FACE.md).

---

## The problem this solves — in one scene

**Thursday morning. You have three clients — one is re-scoping mid-delivery, one needs a milestone
check-in before end of week, and one just sent a brief that changes the mandate.**

You keep it all in your head. Or in a chat thread. Or in a Notion doc you haven't updated since the
initial call. You know exactly what you promised each client — but you cannot point to the single
place where that promise is written down, gated, and tracked against a standard.

This is not a competence problem. It is an **institutional absence** problem.

A boutique agency solves this with staff: a PM who logs every scope change, a quality reviewer who
checks deliverables before handoff, a principal who owns the closeout. But the agency model costs
overhead and floor space that a solo operator, a two-person founding team, or an independent
contractor cannot sustain.

Sovereign Systems gives that operator **the same institutional floor** — without the overhead.

---

## The thesis

> **Most consulting engagements fail at the same four points:**
> 1. The intake is soft — nobody wrote down what the client actually needs before the work started.
> 2. The mandate drifts — scope expands, changes go unlogged, the original agreement is lost.
> 3. Handoffs are rushed — deliverables reach the client before anyone checked them against the agreed standard.
> 4. Nothing closes cleanly — the engagement ends with "the work stopped," not with a documented package.
>
> **This platform exists to make those four failures structurally impossible.**

The mechanism is not a methodology binder or a set of best-practice recommendations. It is a
**runnable posture model** — five primitives, one delivery sequence, six executable rules — that
turns every engagement into a trackable record from intake to closeout.

---

## What Sovereign Systems is

A **structured consulting-operations toolkit** that runs five functions — the same five that a
well-staffed agency performs through dedicated roles:

| Function | What it produces | The file you hold |
|---|---|---|
| **Intake** | A single client posture record: who the client is, what they actually need, what constraints apply | `engagements/<client>.yaml` — one file, all five primitives, validated |
| **Scope** | A proposal-grade engagement hypothesis with explicit inclusions, exclusions, and assumptions | Same file — `scope.boundary`, `scope.exclusions`, `scope.changes[]` |
| **Delivery** | A sequenced milestone map with named owners and human review gates at each checkpoint | Same file — `standing.current`, `standing.history[]`, `human_gates[]` |
| **Quality** | A per-deliverable audit against the agreed standard before any handoff | Same file — `standard.quality_bar`, `standard.evidence` |
| **Archive** | A closed-engagement package: what was promised, built, deferred, and left open | ARCHIVED standing + `standing.history[]` as the complete arc |

Every function lives in one file per client. The engagement file is the single source of truth.
It is validated programmatically — not by reading it, but by running it through a rule engine.

This is not a notion template. It is not a google doc. It is a structured YAML record with
enforceable rules. The difference is the difference between "I should update this" and
"the system will tell me if it's wrong."

---

## The five-primitive kernel

Every engagement is structured around five primitives. The same map works in any domain,
for any client type:

| Primitive | In consulting | What it looks like in the file |
|---|---|---|
| **Member** | the client | `member.name`, `member.context` — who they are, their constraints, their consent |
| **Mandate** | the engagement | `mandate.description`, `mandate.outcome` — what outcome was hired for, in language both sides can sign |
| **Standing** | delivery posture | `standing.current`, `standing.history[]`, `next_standing` — exactly where the engagement is in the sequence |
| **Standard** | the quality bar | `standard.quality_bar`, `standard.evidence` — what a good deliverable looks like, explicit and referenced |
| **Governance** | the authority map | `governance.authority`, `governance.ethics`, `governance.reversibility` — who decides what, what cannot be automated |

An engagement can only move forward when each primitive is named. No drifting mandates.
No silent scope changes. No unreviewed handoffs.

---

## The delivery posture sequence

```
DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION → REVIEW → ARCHIVED
                                                ↓
                                              HOLD
```

Rules of the road:
- An engagement's standing **advances**; it does not regress silently
- A scope change is **logged explicitly** and attributed before it takes effect
- A **HOLD** is a declared state, not an implied pause
- **ARCHIVED** is a complete closeout — what was promised, delivered, deferred, outstanding

These rules are not printed in a handbook. They are checked by the validator:
`python organs/consulting/validate-consulting.py --fleet` — and every violation
names the specific rule, field, and value.

---

## What the operator actually receives

When you hold Sovereign Systems, your workflow runs against five concrete outputs:

| # | Output | What it is | How to use it |
|---|---|---|---|
| 1 | **Client posture file** | `engagements/<client>.yaml` — member, mandate, standing, standards, human gates, scope boundary, change log | One file per engagement. The single source of truth. Open it when you need to know where a client stands. |
| 2 | **Scope draft** | The same file's `scope` section — what is included, excluded, and assumed | Ready for partner review before any external send. Changes are tracked in `scope.changes[]`. |
| 3 | **Milestone map** | The `standing.history[]` and `human_gates[]` fields — staged, owned, gated | No one-step commits to a full outcome. Every milestone has a named gate. |
| 4 | **Quality review** | The `standard` section — per-deliverable audit criteria against the agreed bar | Run the validator before handoff. It flags evidence gaps before they reach the client. |
| 5 | **Closeout archive** | The full file at ARCHIVED standing — what was promised, delivered, deferred, open | The record the next engagement or the next cycle of this engagement starts from. |

These are not templates to fill out. They are operational records that the rule engine
reads, validates, and reports against. The operator works in the file; the engine
enforces the discipline.

---

## How to adopt Sovereign Systems

**You already hold it.** There is no setup to install, no API key to request, no dashboard
to configure. The platform is the directory structure and the rule engine.

```
organs/consulting/
├── engagements/        # One YAML file per client deployment
│   ├── maddie.yaml
│   ├── rob.yaml
│   └── derek.yaml
├── CHARTER.md          # The role map and workflow definitions
├── KERNEL.md           # The architecture and 5-primitive map
├── MACRO-FACE.md       # This document
├── MICRO-FACE.md       # The live engagement record for Anthony's deployments
├── SOVEREIGN-SYSTEMS-DECK.md  # A ready-to-show pitch
├── seed.yaml           # The organ's self-assertion in the VLTIMA body
└── validate-consulting.py  # Six executable rules, one command
```

**To adopt for your own clients:**

1. Copy the directory structure: `organs/consulting/` into your own repo
2. Create one engagement file per client: `engagements/<client>.yaml`
3. Name the five primitives — member, mandate, standing, standard, governance
4. Run the validator: `python3 validate-consulting.py --fleet`
5. The validator tells you what is missing. Fix it. Run again.

That is the full adoption flow. No timezone-dependent kickoff call. No training.
The rule engine is the onboarding.

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

- No hardcoded client names — only `member.name` fields that change per engagement
- No private pricing assumptions — the platform records scope, not rate cards
- No personality-specific idiom — the five primitives and six rules apply to any domain

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
| Captures intake, structures scope | Strategic accept/reject — the human call on every engagement |
| Sequences milestones, tracks standing | Approves reprioritization and external commitments |
| Drafts deliverables, flags quality gaps | Signs off each handoff slice before it reaches the client |
| Stages outbound artifacts for review | Sends, signs, and commits externally — never the system |
| Runs the validator against posture rules | Fixes violations the validator flags; confirms resolution |
| Maintains the posture record as source truth | Owns the relationship, the mandate, and the outcome |

No autonomous external send. No autonomous billing. No autonomous contract execution.
The operator is the final authority for every outward-facing action.

---

## Current stage and validation

The macro platform is **60% mature** (maturing stage). The engagement posture rules are
executable and validated by `validate-consulting.py`. The first micro proof (three active
deployments) passes all six rules. The face is polished.

**What exists now:**
- The 5-primitive kernel mapped to the consulting domain
- The delivery posture sequence with explicit progression rules
- Six executable rules checked by `validate-consulting.py`
- Three active deployments (Maddie, Rob, Derek) at EXECUTION standing
- All three pass the validator: 3/3 green, 0 violations
- One scope change logged, attributed, and approved (Rob, 2026-06-15)
- Zero placeholder evidence fields — every `standard.evidence` is real

**The remaining lift to 70%+ requires:**
- Close one complete intake-to-closeout cycle for all three deployments
- Publish the closeout archive as the first repeatable handoff proof
- Operationalize the governance layer: make the authority contract executable, not just stated

**Validation:**

```bash
# Check all active engagements against Rules #1-6
python organs/consulting/validate-consulting.py --fleet

# Expected output:
# PASS  engagements/derek.yaml  posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
# PASS  engagements/maddie.yaml  posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
# PASS  engagements/rob.yaml     posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
```

---

*Companion documents: [KERNEL.md](KERNEL.md) (architecture + 5-primitive map),
[CHARTER.md](CHARTER.md) (org chart + workflows), [MICRO-FACE.md](MICRO-FACE.md)
(live engagement record for Maddie / Rob / Derek).*
