# Sovereign Systems
## The institutional consulting toolkit — ready to show

*ORGANVM-as-a-service · Micro instance: Maddie · Rob · Derek*

---

## One-line position

> **Sovereign Systems gives one operator the institutional delivery floor that a
> boutique agency provides — without the overhead of a firm.**

---

## The structural failure

Every solo consulting practice hits the same four walls:

| Wall | What it costs |
|---|---|
| Soft intake | The work starts before the mandate is written. The client's real need never gets captured. |
| Mandate drift | Scope expands between calls. Nobody logs the delta. The engagement that ends is not the one that started. |
| Rushed handoff | Deliverables go out before anyone checks them against the agreed standard. Quality is uneven. |
| No closeout | The engagement just *stops*. No archive. No lessons. The next engagement starts from zero. |

An agency solves these with staff — PMs, reviewers, principals. A solo operator solves them
with **process infrastructure**. Sovereign Systems is that infrastructure.

---

## The system

| Function | Output | How it's enforced |
|---|---|---|
| **Intake** | One posture file per client | Five primitives must be named — Member, Mandate, Standing, Standard, Governance |
| **Scope** | Explicit boundary + change log | Scope changes are logged, attributed, and require partner approval |
| **Delivery** | Staged, gated milestone map | Every milestone names a human gate — no autonomic advancement |
| **Quality** | Per-deliverable audit against standard | Evidence must reference real artifacts — no TODOs, no TBDs |
| **Archive** | Complete closeout package | Standing advances through ARCHIVED with full delivery record |

Each function is executable. The same rule engine that validates one engagement validates
all of them. The platform does not ask the operator to *remember* the discipline — it
checks it.

---

## The delivery posture sequence

```
DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION → REVIEW → ARCHIVED
                                                ↓
                                              HOLD
```

Standing advances. It never regresses. A scope change is explicit. A hold is declared.
An archive is written. Nothing is implied.

---

## The authority contract

| Sovereign Systems does | The operator does |
|---|---|
| Captures intake, builds posture record | Strategic accept/reject — the human call on every engagement |
| Assembles scope draft, logs changes | Approves scope before any external send |
| Sequences milestones, tracks standing | Approves reprioritization |
| Drafts deliverables, flags quality gaps | Signs off each handoff |
| Stages outbound artifacts for review | Sends, signs, commits externally |

The system drafts and stages. The operator decides and acts. Nothing external happens
without explicit human authorization.

---

## The validator (the evidence)

Six executable rules, one command:

```bash
$ python3 organs/consulting/validate-consulting.py --fleet

PASS  engagements/derek.yaml  posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
PASS  engagements/maddie.yaml  posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
PASS  engagements/rob.yaml     posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
────────────────────────────────────────────────────────────
  3/3 passed  |  0 violation(s)
  Sovereign Systems Rules #1-6: all checks passed.
```

When it passes, the engagement is structurally sound. When it fails, the output names
the exact rule, field, and value — no guessing about what broke.

---

## The live proof — three active deployments

### Maddie — scope stability under shifting priorities

- **File:** `engagements/maddie.yaml`
- **Standing:** EXECUTION — delivery artifacts in progress
- **Scope changes:** 0 (unchanged since acceptance — the mandate has held)
- **Next gate:** Anthony signs off deliverable package → REVIEW
- **What it proves:** the posture model holds when requirements move

### Rob — cadence stability across recurring work

- **File:** `engagements/rob.yaml`
- **Standing:** EXECUTION — milestone checkpoint in progress
- **Scope changes:** 1 logged, attributed, approved change (2026-06-15)
- **Next gate:** Anthony confirms milestone checkpoint → REVIEW
- **What it proves:** the platform records and gates scope changes — it does not absorb them silently

### Derek — portability across different work idioms

- **File:** `engagements/derek.yaml`
- **Standing:** EXECUTION — brief format + milestone ledger active
- **Scope changes:** 0 (original brief structure held across education and narrative domains)
- **Next gate:** Anthony reviews brief + ledger → REVIEW
- **What it proves:** one operating model works for scope-stability, cadence-stability, and cross-domain work

---

## What the deployments prove — in numbers

| Metric | Value |
|---|---|
| Active engagements | 3 |
| Rule checks passed | 18/18 (6 rules × 3 engagements) |
| Scope changes logged | 1 (attributed and approved) |
| Human gates declared | 9 total (3 per engagement) |
| Placeholder evidence fields | 0 |
| Autonomic claims | 0 |
| Overreach violations | 0 |

---

## How to adopt

1. Copy `organs/consulting/` into your repo
2. Create `engagements/<client>.yaml` with the five primitives
3. Run `python3 validate-consulting.py --fleet`
4. Fix what the validator flags
5. Your engagements are now institutional records

No install. No API. No training. The rule engine is the onboarding.

---

## Operating constraints (non-negotiable)

- No autonomous client-facing messages — the organ drafts; the partner sends
- No autonomous contract sends or modifications — staged and surfaced only
- No autonomous billing — invoice drafts reviewed before any send
- No external commitments without explicit partner gate
- No legal, tax, or medical advice — delivery infrastructure only
- No invented proof — all status reflects what actually exists

---

*Sovereign Systems · stage: maturing (60%) · validator: green · constraint: manual prototype mode*
*Full architecture: [KERNEL.md](KERNEL.md) · Platform face: [MACRO-FACE.md](MACRO-FACE.md) · Live deployments: [MICRO-FACE.md](MICRO-FACE.md)*
