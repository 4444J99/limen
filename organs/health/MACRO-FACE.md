# Health / Body — MACRO FACE
## The concierge recovery platform: institutional care-administration weight, holdable by any patient

*The platform form of the health organ · Available to any person navigating a complex recovery*

> **What you are reading:** the macro face is what an outside patient holds — the portable,
> reusable body of this organ before any personal health data or case name touches it. The
> micro instance (the principal's unnamed post-injury recovery + ADA accommodation matter)
> proves it in practice. That proof is in [`MICRO-FACE.md`](MICRO-FACE.md).

---

## The problem this platform solves

A person navigating a complex recovery without institutional support has the same medical
team as a concierge patient — but **none of the administrative backbone**. For every hour
the attending physician spends on diagnosis and treatment, a concierge recovery team spends
dozens of hours on the work that makes that hour effective:

- Protocol tracking — who prescribed what, when is it due, was it done
- State recording — how does the body respond today vs. yesterday vs. last week
- Care-team coordination — what does the orthopedist know that the PT doesn't
- Appointment governance — when is the next specialist visit, what prep is needed
- Accommodation documentation — what functional limitations exist, what has been requested,
  what was the response

Without that backbone, the patient carries the full coordination load — under cognitive
strain, often while symptomatic, with no institutional memory between provider visits.

This platform supplies that backbone as **continuous AI-run workflows** that track, record,
and surface — so the patient can focus on recovery and the clinicians on clinical work.

---

## The thesis

> **The binding constraint on a solo recovery is not clinical access — it is process
> continuity.** A concierge team achieves better outcomes not by having better doctors but
> by having more administrative density per clinical hour. This platform delivers the same
> density from idle fleet capacity: 14K-16K workunits/month running coordination workflows
> that would otherwise require 5+ dedicated staff.

The mechanism is a **runnable posture model** — five primitives, six workflows, one living
recovery record per case — that turns every recovery into a trackable artifact chain from
intake to closeout.

---

## The five-primitive kernel

| Primitive | In health | Concretely |
|---|---|---|
| **Member** | the body / patient | the physical self as the operating subject — capabilities, limits, current functional status, recovery goals, and what the person needs to do or be |
| **Mandate** | the protocol | the treatment plan that governs action — prescribed routines, therapy cadence, constraint rules, medication schedule, specialist directives |
| **Standing** | health state | current condition baseline — symptoms, functional trend markers, pain/sleep/mood indicators, change velocity, risk flags |
| **Standard** | clinical guideline | verified care logic — published post-injury protocols, specialist directives, safety thresholds, rehab milestones, evidence base |
| **Governance** | care plan | specialist coordination, appointment orchestration, accommodation obligations, escalation paths, auditable record |

---

## The health posture sequence

```
INTAKE → ACTIVE → REVIEW → HOLD → COMPLETED
```

Each posture carries specific workflow authorizations:

| Posture | What is allowed | What is blocked |
|---|---|---|
| **INTAKE** | State recording, posture record creation, protocol registration | No accommodation documentation, no external outputs |
| **ACTIVE** | All 6 workflows: state, protocol, calendar, accommodation, safety | No clinical advice, no self-scheduling, no self-discharge |
| **REVIEW** | Posture brief generation, trend analysis, accommodation summary | No new protocol entries, no appointment modifications |
| **HOLD** | State recording only, monitoring beat | No accommodation actions, no protocol changes |
| **COMPLETED** | Archive preservation, closeout documentation | No active workflows |

The sequence advances; it does not regress silently. Progression changes require patient or
clinician confirmation.

---

## What the patient actually receives

When you hold the health platform, you have access to **six operational outputs** — one per
workflow — that collectively give you the institutional leverage of a concierge recovery team:

| # | Output | What it is | How to use it |
|---|---|---|---|
| 1 | **Recovery-posture brief** | `cases/<id>/posture.md` — one-page standing record with baseline, protocol, functional status, open items, risk flags, accommodation status | Always current. Share with any new provider — no "start from scratch" at every intake |
| 2 | **State log** | `cases/<id>/state-log.yaml` — dated entries with structured markers (pain, sleep, mood, function, medication effects) and trend indicators | Review each daily beat; correct entries; track improving/stable/declining per marker |
| 3 | **Protocol-adherence log** | `cases/<id>/protocol-log.md` — every prescribed action tracked with status (done/skipped/rescheduled) and timestamp. Adherence rate per period | Clinician reviews at each visit; the tracker never enforces compliance — only records |
| 4 | **Appointment calendar** | `cases/<id>/calendar.md` — all clinical events sorted by proximity with alert status, prep notes, post-visit action items | Patient books; scheduler tracks. Proximity alerts at configurable thresholds |
| 5 | **Accommodation record** | `cases/<id>/accommodation-log.md` — structured log of every functional limitation, request, response, and status change | Citable in ADA proceedings. Feeds directly into the legal organ's matter workflow |
| 6 | **Safety certification** | Inline stamp on every deliverable | "Safety check passed: clinical boundary held, no contradictions with licensed directives, privacy scoped." |

Every output is **advisory to the patient and their care team**. None are self-acting. None
replace clinical judgment. None are communicated externally without the patient's direction.

---

## What this is not

This platform does not diagnose, prescribe, give medical advice, or replace any licensed
professional. It is **health-operations infrastructure**, not a clinician.

Every clinical judgment — diagnosis, treatment plan, prescription, procedure — remains with
the licensed provider. The platform tracks protocol adherence; it does not recommend deviation.
It surfaces state changes; it does not interpret them clinically. It documents accommodation
needs; it does not give legal advice about ADA rights.

The constraints are features. They enforce the boundaries that keep the platform safe and
the care chain intact.

---

## Governance layer (the authority contract, plainly stated)

The organ runs the recovery-operations system. The patient and clinicians run the recovery.

| What the organ does | What the patient does |
|---|---|
| Tracks health state, protocol adherence, appointment calendar | Attends appointments, follows protocol, reports symptoms — the patient is the authority over their own body |
| Documents functional limitations and accommodation correspondence | Directs every accommodation request; the legal organ applies legal strategy |
| Produces structured records, trend markers, and proximity alerts | Clinician interprets clinical meaning; patient reviews and corrects all entries |
| Drafts the recovery-posture brief from state, protocol, and calendar inputs | Confirms posture is accurate before it is shared with any provider |
| Flags state changes and overdue items | Clinician is the only escalation path for clinical concerns |
| Enforces the safety boundary on every output | Reviews safety certification; clinician resolves any flagged concern |

No autonomous clinical decisions. No autonomous appointment booking. No autonomous external
communication. The patient and their clinicians are the final authority for every health act.

---

## Current stage and validation

The macro platform is **15% mature** (scaffold stage → building stage entry). The kernel,
charter, posture model, all six workflows, the first micro case artifacts, and the executable
infrastructure are all in place. The first micro proof — the principal's unnamed post-injury
recovery + ADA accommodation matter — is the live instance, currently standing at ACTIVE with
all 6 workflows producing artifacts.

**What exists now:**

- The 5-primitive kernel mapped to the health domain
- All 6 workflows specified with triggers, processes, outputs, cadences, and human gates
- 7 AI roles chartered with clear scope and human supervision
- Full constraint registry with enforcement mechanisms
- Cross-organ handoff to legal organ specified (accommodation record → ADA matter)
- Safety sentinel specified as a cross-cutting gate on every output
- **Workflow 1 (Intake → posture):** `cases/01-post-injury/posture.md` — one-page standing record with baseline, protocol, functional status, accommodation status, and open coordination items
- **Workflow 2 (State → record):** `cases/01-post-injury/state-log.yaml` — first daily beat with structured markers (pain, sleep, mood, energy, cognition, function, medication effects) and trend indicators
- **Workflow 3 (Protocol → adherence):** `cases/01-post-injury/protocol-log.md` — 96% adherence rate with per-action tracking across PT, specialist appointments, cognitive pacing, and medication
- **Workflow 4 (Appointments → calendar):** `cases/01-post-injury/calendar.md` — 6 upcoming appointments across PT, orthopedics, and neurology with proximity alerts, prep tracking, and conflict scan
- **Workflow 5 (Accommodation → documentation):** `cases/01-post-injury/accommodation-log.md` — 4 accommodation requests tracked with full limitation/request/response/correspondence structure, wired to legal organ intake
- **Workflow 6 (Safety sentinel):** `organs/health/safety-sentinel.sh` — executable gate checking 6 guardrails (clinical boundary, contradiction, self-scheduling, privacy, UPL, legal boundary)
- **Reception script:** `organs/health/RECEPTION.md` — conductor prompt routing patient input to the correct workflow, loaded with KERNEL boundaries
- **Workflow runner:** `organs/health/workflow-runner.sh` — orchestrates all 6 workflows with safety gates
- **Executive Health Office:** `scripts/health-organ.py` — integrated as the organ's daily execution engine, stamping liveness for proprioception

**What the remaining lift to 30% (building stage) requires:**

- 2+ weeks of daily state entries establishing trend baselines
- One full accommodation cycle completed through the entire lifecycle
- Accommodation record successfully consumed by legal organ (`organs/legal/` evidence index)
- Safety sentinel showing zero failures over a continuous 14-day period
- Posture brief shared with and confirmed by a new provider at intake
- Beat log receiving continuous daily entries for 14+ days

**Validation:**

```bash
# Check the health organ structure and workflow artifacts
ls organs/health/KERNEL.md organs/health/CHARTER.md organs/health/MACRO-FACE.md organs/health/MICRO-FACE.md
ls organs/health/RECEPTION.md organs/health/safety-sentinel.sh organs/health/workflow-runner.sh
ls organs/health/cases/01-post-injury/{posture.md,state-log.yaml,protocol-log.md,accommodation-log.md,calendar.md,beat-log.yaml}

# Run the safety sentinel against an existing artifact
./organs/health/safety-sentinel.sh organs/health/cases/01-post-injury/protocol-log.md --check-only

# Show current organ status
./organs/health/workflow-runner.sh status
```

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`CHARTER.md`](CHARTER.md) (org chart + 6-workflow orchestration + leverage math),
[`MICRO-FACE.md`](MICRO-FACE.md) (the principal's unnamed post-injury recovery instance).*
