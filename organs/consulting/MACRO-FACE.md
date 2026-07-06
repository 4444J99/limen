# Sovereign Systems — MACRO FACE
## ORGANVM-as-a-service: the institutional toolkit

*The platform form of the consulting organ · Available to any founder, operator, or institution that runs client work*

> **What you are reading:** the macro face is what an outside operator holds — the portable,
> reusable body of this organ before any client name is in it. The micro instance (five active
> deployments across four domains) proves it in practice. That proof is in [`MICRO-FACE.md`](MICRO-FACE.md).

---

## The one-sentence position

> **Sovereign Systems gives a solo or small-team operator the same institutional delivery floor
> that a boutique agency provides — without the overhead of a firm, the rent of an office,
> or the dependency on staff whose availability you cannot control.**

---

## The failure this solves

Every solo consulting practice hits the same four walls. They are not competence failures.
They are **institutional absence** failures:

| Wall | What it costs | Why it happens |
|------|---------------|----------------|
| **Soft intake** | The work starts before the mandate is written. The real need never gets captured — and the engagement is misbuilt from the first conversation. | No structured intake ritual. The operator trusts memory instead of a record. |
| **Mandate drift** | Scope expands between calls. Nobody logs the delta. The engagement that ends is not the one that started — and the operator absorbs the un-billed overhang. | No scope boundary, no change log. The agreement is implicit, so it can move without notice. |
| **Rushed handoff** | Deliverables go out before anyone checks them against the agreed standard. Quality is uneven — one client gets the operator's best, another gets a draft. | No per-deliverable audit gate. Handoff is whatever the operator has time to send. |
| **No closeout** | The engagement just *stops*. No archive. No lessons. The next engagement starts from zero, repeating the same mistakes. | No closeout ritual. The engagement record evaporates when the chat thread ends. |

An agency solves these with staff — PMs who capture scope, reviewers who check quality,
principals who own closeout. A solo operator cannot hire a team for every engagement.

**Sovereign Systems is the operator's institutional floor.** The same functions, automated.

---

## The mechanism — five primitives, one sequence, six executable rules

The platform is not a methodology binder. It is a **runnable posture model** — five primitives
that structure every engagement, one delivery sequence that governs its movement, and six
executable rules that the operator runs instead of remembering.

### The five-primitive kernel

Every engagement is one YAML file structured around five primitives. The same map works
for any domain, any client type, any engagement size:

| Primitive | What it captures | Engagement file field |
|-----------|------------------|----------------------|
| **Member** | The client — who they are, their constraints, their context, their consent | `member.name`, `member.context` |
| **Mandate** | The engagement — what outcome was hired for, in language both sides can sign | `mandate.description`, `mandate.outcome` |
| **Standing** | Delivery posture — exactly where the engagement is in the sequence | `standing.current`, `standing.history[]`, `next_standing` |
| **Standard** | The quality bar — what a good deliverable looks like, explicit and referenced | `standard.quality_bar`, `standard.evidence` |
| **Governance** | The authority map — who decides what, what cannot be automated, what requires a human hand | `governance.authority`, `governance.ethics`, `governance.reversibility` |

An engagement can only move forward when all five primitives are named. No drifting mandates.
No silent scope changes. No unreviewed handoffs.

### The delivery posture sequence

```
DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION → REVIEW → ARCHIVED
                                                ↓
                                              HOLD
```

The rules of movement:
- Standing **advances**; it never regresses silently
- A scope change is **logged explicitly and attributed** before it takes effect
- **HOLD** is a declared state, never an implied pause
- **ARCHIVED** is a complete closeout — what was promised, delivered, deferred, outstanding

### The six executable rules

These are not printed in a handbook. They are run:

```bash
python3 organs/consulting/validate-consulting.py --fleet
```

| # | Rule | What it enforces | What happens if broken |
|---|------|------------------|------------------------|
| 1 | **Valid Posture** | Standing must be in the canonical sequence; no skips, no regression | The validator names the exact field and value |
| 2 | **Manual Mode** | Every milestone declares explicit human gates. No autonomic delivery claims | Violation is flagged — the organ never sends or commits without a hand |
| 3 | **5-Primitive Completeness** | All five primitives must be named in every engagement record | Missing fields are reported by name |
| 4 | **Scope Integrity** | Scope boundary is explicit; changes are tracked and attributed | Silent scope creep is structurally impossible |
| 5 | **No Overreach** | No engagement may claim legal, tax, or medical advice | Scope boundary is scanned for prohibited language |
| 6 | **Evidence Integrity** | Every `standard.evidence` field must reference real artifacts — no TODO, TBD, or placeholder | Placeholder text is caught and surfaced |

---

## What the operator actually receives

When you hold Sovereign Systems, your workflow runs on these five outputs:

| # | Output | What it is | How to use it |
|---|--------|------------|---------------|
| 1 | **Client posture file** | `engagements/<client>.yaml` — all five primitives, scope boundary, change log, human gates | One file per engagement. The single source of truth. Read it when you need to know exactly where a client stands. |
| 2 | **Scope draft** | The file's `scope` section — inclusions, exclusions, assumptions | Ready for partner review before any external send. Changes are tracked in `scope.changes[]`. |
| 3 | **Milestone map** | The `standing.history[]` and `human_gates[]` — staged, owned, gated | No one-step commits to full outcomes. Every milestone has a named authority. |
| 4 | **Quality review** | The `standard` section — per-deliverable audit criteria against the agreed bar | Run the validator before handoff. It flags evidence gaps before they reach the client. |
| 5 | **Closeout archive** | The full file at ARCHIVED standing — what was promised, delivered, deferred, open | The record the next engagement — or the next cycle — starts from. |

These are not templates. They are operational records that the rule engine reads, validates,
and reports against. The operator works in the file; the engine enforces the discipline.

---

## How to adopt

**You already hold it.** There is no setup to install, no API key to request, no dashboard to
configure. The platform is the directory structure and the rule engine.

```
organs/consulting/
├── engagements/              # One YAML file per client deployment
│   ├── maddie.yaml           # wellness | EXECUTION
│   ├── rob.yaml              # fitness + chess | EXECUTION
│   ├── derek.yaml            # education + narrative | EXECUTION
│   ├── jessica.yaml          # HR | DISCOVERY
│   └── john-f.yaml           # finance | DISCOVERY
├── CHARTER.md                # The role map and workflow definitions
├── KERNEL.md                 # The architecture and 5-primitive map
├── MACRO-FACE.md             # This document
├── MICRO-FACE.md             # Live engagement record for all deployments
├── SOVEREIGN-SYSTEMS-DECK.md # A ready-to-show pitch
├── FUNNEL-ENGINE.md          # The client-growth playbook (engine + N niche instances)
├── seed.yaml                 # The organ's self-assertion in the VLTIMA body
├── validate-consulting.py    # Six executable rules, one command
└── funnel/                   # Niche-funnel engine instances
    ├── validate-funnel.py    # Engine Rules #1-7
    ├── ROB-BODI-OPERATING-FLOOR.md
    ├── templates/
    └── instances/
```

**To adopt for your own clients:**

1. Copy the directory structure into your own repo
2. Create one engagement file per client: `engagements/<client>.yaml`
3. Name the five primitives — member, mandate, standing, standard, governance
4. Run `python3 validate-consulting.py --fleet`
5. The validator tells you what is missing. Fix it. Run again.

No timezone-dependent kickoff call. No training. **The rule engine is the onboarding.**

---

## Governance layer — the authority contract

The organ runs the engagement system. The operator runs the engagement. This is the
boundary, stated plainly and enforced by the validator:

| What the organ does | What the operator does |
|---------------------|------------------------|
| Captures intake, structures posture record | Strategic accept/reject — the human call on every engagement |
| Assembles scope draft, logs changes | Approves scope boundaries before any external send |
| Sequences milestones, tracks standing | Approves reprioritization and external commitments |
| Drafts deliverables, flags quality gaps | Signs off each handoff slice before it reaches the client |
| Stages outbound artifacts for review | Sends, signs, and commits externally — never the system |
| Runs the validator against posture rules | Fixes violations the validator flags; confirms resolution |
| Maintains the posture record as source truth | Owns the relationship, the mandate, and the outcome |

**No autonomous external send. No autonomous billing. No autonomous contract execution.**
The operator is the final authority for every outward-facing action. The validator enforces
this at every beat.

---

## Proof — the micro instance

The macro platform makes testable claims about engagement discipline. Five active
deployments across four domains prove them:

| Claim | Evidence | Status |
|-------|----------|--------|
| Scope does not drift silently | 2 scope changes logged across 5 engagements, all attributed and approved | **CONFIRMED** |
| Posture is always named | All 5 have a named `standing.current`; all 3 at EXECUTION have complete `standing.history[]` | **CONFIRMED** |
| Human gates are structural, not advisory | All 5 declare named human gates; 0 autonomic claims | **CONFIRMED** |
| The validator enforces the rules | 30/30 checks pass across 5 engagements (6 rules × 5 engagements) | **CONFIRMED** |
| Portability holds across domains | One process works for scope-stability, cadence-stability, cross-domain, HR-discovery, and finance-discovery | **CONFIRMED** |
| Placeholder evidence is zero | Every `standard.evidence` field references real artifacts | **CONFIRMED** |

Three deployments at EXECUTION (Maddie, Rob, Derek) — deliveries in progress, all six
rules passing. Two at DISCOVERY (Jessica, John F.) — organic growth from the same pipeline,
proving the platform scales to new niches without ceremony.

The full engagement record is in [`MICRO-FACE.md`](MICRO-FACE.md).

---

## Current stage and forward path

**Stage:** maturing (60%). The engagement posture model is executable and validated.
All active deployments pass the six-rule validator. The first scope changes have been
logged, attributed, and approved — proving the scope-integrity mechanism works in
practice.

**What exists now:**
- The 5-primitive kernel mapped to the consulting domain
- The delivery posture sequence with explicit progression rules
- Six executable rules checked by `validate-consulting.py`
- Five active deployments across four domains (wellness, fitness+chess, education+narrative, HR, finance)
- 30/30 validations pass: zero violations
- Two scope changes logged, attributed, and approved
- The niche-funnel engine (FUNNEL-ENGINE.md) operationalized for the fitness+chess lane
- Zero placeholder evidence fields

**The remaining lift to 70%+:**
- Close one complete intake-to-closeout cycle for any deployment — the first full end-to-end proof
- Publish the closeout archive as the first repeatable handoff artifact
- Operationalize the governance layer: make the authority contract executable, not just stated

**Validation command:**

```bash
python3 organs/consulting/validate-consulting.py --fleet

# Expected output (5 engagements, 30/30 pass):
# PASS  engagements/derek.yaml     posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
# PASS  engagements/jessica.yaml   posture: DISCOVERY  |  next: PROPOSAL
# PASS  engagements/john-f.yaml    posture: DISCOVERY  |  next: PROPOSAL
# PASS  engagements/maddie.yaml    posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
# PASS  engagements/rob.yaml       posture: DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION  |  next: REVIEW
```

---

## What this is not

This toolkit does not replace the operator's judgment. It does not send proposals, execute
contracts, bill clients, or make commitments. Every external act stays with the human
partner — staged, surfaced, reviewed.

It also does not provide legal, tax, or medical advice. It is **delivery infrastructure**,
not professional services.

The constraint is a feature. It enforces the boundary that protects the operator's license
to practice and their client's trust. The validator scans for overreach language at every
beat.

---

*Companion documents: [KERNEL.md](KERNEL.md) (architecture + 5-primitive map),
[CHARTER.md](CHARTER.md) (org chart + workflows), [MICRO-FACE.md](MICRO-FACE.md)
(live engagement record for all deployments).*
