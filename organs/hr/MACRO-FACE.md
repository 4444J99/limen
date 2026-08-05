# HR / People Office — MACRO FACE
## An HR-institution-in-a-box: the apparatus of a Fortune-500 people office, holdable by one practitioner

*The platform form of the HR organ · Available to any HR practitioner, small business, or solo operator*

> **What you are reading:** the macro face is what an outside operator holds — the portable,
> reusable body of this organ before any client name is in it. The micro instance (Jessica's
> HR practice) proves it in practice. That proof is in [`MICRO-FACE.md`](MICRO-FACE.md).

---

## The problem this platform solves

Large employers win the talent game not because their people leaders are better but because
a **standing apparatus** stands behind every manager:

- Structured hiring loops with calibrated interview rubrics
- Onboarding sequences that fire in the right order with compliance built in
- Policy handbooks written by specialists, jurisdiction-tagged, version-controlled
- Compliance calendars that surface deadlines before they arrive
- Performance frameworks with named rubrics and review-cycle scaffolding
- Offboarding checklists that protect both the company and the departing employee

A solo HR practitioner or a small-business owner has the **same judgment** as the Fortune-500
people office — but every process is reinvented per client, per hire, per incident. There is
no standing apparatus. There is no institutional memory between engagements.

This platform supplies that apparatus as **versioned, reusable, jurisdiction-aware artifacts**.

---

## The thesis

> **The binding constraint on a solo HR practitioner is not skill — it is process density.**
> A Fortune-500 people office runs on specialist headcount. A boutique consultancy substitutes
> structured playbooks and templates that eliminate re-invention. This platform delivers the
> same institutional leverage without the headcount premium.

The mechanism is a **runnable posture model** — five primitives, eight workflows, one
validated record per client — that turns every engagement into a trackable artifact chain
from intake to closeout.

---

## The five-primitive kernel

| Primitive | In HR | Concretely |
|---|---|---|
| **Member** | person in a role | employee, candidate, contractor, or client — capabilities, standing, consent, record |
| **Mandate** | role / policy / engagement | what the role exists to do, what the policy requires, what the engagement was hired for |
| **Standing** | employment or engagement state | candidate → hired → onboarding → active → transitioning → alumni; or DISCOVERY → PROPOSAL → ACTIVE → TRANSITIONING → CLOSED for clients |
| **Standard** | the compliance and quality bar | labor-law floor, compensation benchmark, policy handbook, performance rubric, jurisdiction rule set |
| **Governance** | people-ops process + ethics wall | who decides, what requires human sign-off, what the system may never do to a person |

---

## The HR engagement posture sequence

```
DISCOVERY → PROPOSAL → ACTIVE → TRANSITIONING → CLOSED
```

Each posture carries specific workflow authorizations:

| Posture | What is allowed | What is blocked |
|---|---|---|
| **DISCOVERY** | Intake, posture record creation, scope framing | No client-facing output |
| **PROPOSAL** | Handbook skeleton, compliance calendar sketch, benchmark research | No binding commitments, no employee-facing materials |
| **ACTIVE** | All 8 workflows: drafts, calendars, frameworks, plans | No outbound communication, no employment decisions |
| **TRANSITIONING** | Offboarding plans, knowledge-transfer docs, closeout archive | No new engagements under this scope |
| **CLOSED** | Archive preservation, ethics log terminal entry | No active workflows |

An engagement advances through the sequence; it does not regress. A scope change is logged
explicitly and attributed before it takes effect.

---

## What the operator actually receives

When you hold the HR platform, you have access to **seven operational outputs** — one per
workflow — that collectively give you the institutional leverage of a 50-person people office:

| # | Output | What it is | How to use it |
|---|---|---|---|
| 1 | **Client posture record** | `clients/<id>/posture.yaml` — all 5 primitives, scope boundary, change log, workflow state | One file per client. Opening it tells you exactly where the engagement stands. |
| 2 | **Handbook + policy drafts** | `clients/<id>/handbook.md`, `policies/*.md` — jurisdiction-tagged skeletons with version diffs | Populated from the template library, tagged by jurisdiction, ready for practitioner tailoring |
| 3 | **Compliance calendar** | `clients/<id>/compliance-calendar.md` — deadline table with configurable lead-time alerts | Rebuilt weekly; alert scan daily. Practitioner confirms all deadline posture. |
| 4 | **Compensation benchmark** | `clients/<id>/comp-benchmark.md` — market range table with source annotations | Practitioner validates before any offer or review discussion |
| 5 | **Performance framework** | `clients/<id>/performance-framework.md` — rubrics, goal cascades, review-cycle scaffold | Practitioner designs the philosophy; framework keeper translates it into structure |
| 6 | **Onboarding plan** | `clients/<id>/onboarding-plan.md` — day -14 through day 90 sequence with compliance built in | Practitioner reviews and sends to the hiring manager |
| 7 | **Offboarding plan** | `clients/<id>/offboarding-plan.md` — checklist for final pay, IT deprovision, knowledge transfer, exit | Practitioner executes every step; the organ drafts the plan |

Every output is a **draft staged for practitioner review**. None are self-acting. None
reach a client or employee without the practitioner's direction.

The ethics sentinel (W8) cross-cuts every output path. No artifact leaves the organ
without a boundary pass record.

---

## The template library

The macro platform includes a **jurisdiction-aware template library** at `organs/hr/templates/`:

```
templates/
  handbooks/              # Handbook skeletons by jurisdiction
    california.md
    federal.md
    new-york.md
    texas.md
    generic.md
  policies/               # Individual policy skeletons by jurisdiction
    at-will-employment/
      california.md
      texas.md
      generic.md
    anti-harassment/
      california.md
      federal.md
      generic.md
    leave-of-absence/
      california.md
      federal.md
      generic.md
  compliance/             # Jurisdiction rule annotations
    states/
      california.yaml
      new-york.yaml
      texas.yaml
    federal.yaml
  comp-benchmarks/        # Industry benchmarking skeletons
    technology.yaml
    healthcare.yaml
    professional-services.yaml
    nonprofit.yaml
  rubrics/                # Performance rubric templates
    communication.md
    collaboration.md
    execution.md
    leadership.md
```

Each template is tagged by jurisdiction, mandatory/elective status, and headcount
threshold. The policy drafter loads the appropriate skeleton from the library and
populates the client-specific fields — eliminating the "every handbook from scratch"
problem that costs solo practitioners days per engagement.

---

## How to adopt this platform

**You already hold it.** The platform is the directory structure, the template library,
and the validation rules.

```
organs/hr/
├── KERNEL.md              # Architecture and 5-primitive map
├── CHARTER.md             # Org-chart, 8 workflows, I/O, leverage math
├── MACRO-FACE.md          # This document
├── MICRO-FACE.md          # Jessica's HR practice as the micro proof
├── validate-hr.py         # Executable validation rules
├── templates/             # Macro platform template library
│   ├── handbooks/
│   ├── policies/
│   ├── compliance/
│   ├── comp-benchmarks/
│   └── rubrics/
└── clients/               # Per-client engagement artifacts
    └── <client-id>/
        ├── posture.yaml
        ├── handbook.md
        ├── policies/
        ├── compliance-calendar.md
        ├── comp-benchmark.md
        ├── performance-framework.md
        ├── onboarding-plan.md
        ├── offboarding-plan.md
        ├── ethics-log.md
        └── drafts/
```

**To adopt for your own practice:**

1. Copy the directory structure into your own repo
2. Create one client posture record: `clients/<client-id>/posture.yaml`
3. Name the five primitives — member, mandate, standing, standard, governance
4. Run the validator: `python3 validate-hr.py --fleet`
5. The validator tells you what is missing. Fix it. Run again.

That is the full adoption flow. The rule engine is the onboarding.

---

## What this is not

This platform does not replace the practitioner's judgment. It does not make employment
decisions, give benefits counsel, or communicate with employees, candidates, or regulators.
Every external act stays with the human practitioner — staged, surfaced, reviewed.

It also does not provide legal advice. Handbook and policy drafts are **templates, not legal
opinions**. The compliance calendar tracks known deadlines, not legal interpretations.

The constraints are features. They enforce the boundaries that keep the platform trustworthy.

---

## Governance layer (the authority contract, plainly stated)

The organ runs the people-operations system. The practitioner runs the client engagement.

| What the organ does | What the practitioner does |
|---|---|
| Captures intake, structures posture record | Confirms scope, accepts/rejects the mandate |
| Drafts handbook skeletons, policy drafts | Reviews every word, edits for client fit, owns delivery |
| Surfaces compliance deadlines with alerts | Executes all filings, confirms deadline posture |
| Produces comp benchmarks from structured data | Validates benchmarks against experience before any offer |
| Generates performance frameworks, onboarding/offboarding plans | Owns the review philosophy, executes all separation steps |
| Runs the ethics sentinel on every output | Is the final arbiter and responsible party for every artifact |
| Maintains the client posture record as source truth | Holds the client relationship, strategic judgment, and external communication |

No artifact leaves the organ without a practitioner gate. No employment decision is made
by the system. No communication reaches an employee or third party without human direction.

---

## Current stage and validation

The macro platform is **10% mature** (scaffold stage). The kernel, charter, template
skeletons, and posture record structure are defined. The first micro proof — Jessica's
HR practice — is at DISCOVERY standing.

**What exists now:**
- The 5-primitive kernel mapped to the HR domain
- All 8 workflows specified with triggers, processes, outputs, cadences, and human gates
- 10 AI roles chartered with clear scope and human supervision
- Full constraint registry with enforcement mechanisms
- Jessica engagement record at DISCOVERY (passes consulting fleet validator)
- Client template directory with all artifact skeletons
- Template library with jurisdiction-aware skeletons

**What the remaining lift to 30% (building stage) requires:**
- First client engagement moved from DISCOVERY to ACTIVE
- One complete handbook draft delivered through W2
- One compliance calendar built and reviewed (W3)
- Ethics sentinel producing its first pass records (W8)
- Validation rules proven against a real client engagement

**Validation:**

```bash
# Check the HR organ structure and posture rules
python organs/hr/validate-hr.py --fleet

# The Jessica micro instance validates through the consulting organ
python organs/consulting/validate-consulting.py --fleet --quiet
```

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`CHARTER.md`](CHARTER.md) (org chart + 8-workflow orchestration + leverage math),
[`MICRO-FACE.md`](MICRO-FACE.md) (Jessica's HR practice as the micro proof).*
