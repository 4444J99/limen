# Health Organism — KERNEL (the concierge recovery architecture)

> **Boundary (load-bearing, repeated everywhere in this organ):** this is health-operations
> infrastructure that augments licensed medical professionals, the patient, and their care team.
> It does **not** replace clinical judgment, diagnosis, treatment, medical advice, or the
> patient-provider relationship. Patient safety, privacy, and the primacy of the licensed care
> chain remain non-negotiable.

---

## Why this organ exists

This organ is an **institutional prosthesis** for recovery management and disability access. It
replaces the missing administrative weight for people who otherwise face complex health events,
coordinated care, accommodation processes, and recovery tracking without a dedicated care
administration team.

A concierge medical practice or premium recovery team does not have better doctors — it has more
continuity. For every hour the attending physician spends on diagnosis and treatment, a coordinated
team spends dozens of hours on the work that makes that hour effective: protocol tracking, state
monitoring, care-team coordination, accommodation documentation, and schedule management. The
person navigating a complex recovery without support has the same medical team but **none of the
administrative backbone**.

This organ supplies that backbone as persistent AI roles running continuously against the recovery.
It makes health operations repeatable: protocol tracking, symptom and state recording, care-team
coordination, standard adherence, appointment governance, and capability-focused accommodation
records — the institutional weight normally purchased at concierge-tier prices.

Generic at the base and instance-first atop that base: **generic + nameless underneath, his
instance on top**.

---

## The 5-primitive kernel, mapped to health

| Primitive | Health meaning | Concretely |
|---|---|---|
| **Member** | **body / patient** | the physical self as the operating subject: capabilities, limits, current functional status, recovery goals, and what the person needs to do or be — the unit of care the whole system serves |
| **Mandate** | **protocol** | the treatment plan that governs action: prescribed routines, therapy cadence, constraint rules, medication schedule, specialist directives, and the coordination signals that flow between providers |
| **Standing** | **health state** | the current condition baseline: symptoms, functional trend markers, pain/sleep/mood indicators, change velocity since the last beat, and any risk flags warranting clinical attention |
| **Standard** | **clinical guideline** | verified care logic: published post-injury protocols, specialist directives, safety thresholds, rehab milestones, and the evidence base that frames consistent, defensible action |
| **Governance** | **care plan** | the control structure: specialist coordination, appointment orchestration, accommodation obligations, scheduling authority, escalation paths, and the auditable record that connects the health track to the legal ADA matter |

This is the same kernel shape as the legal, education, governance, and artist organs — only the
domain layer changes. The structure is fixed; the skin is health. That is the fractal: one kernel,
every pillar.

---

## Fractal deployment

### MACRO — the health/recovery + disability-access institution anyone can hold

A reusable platform anyone can hold: protocol ingestion, symptom and state tracking, care-team
coordination, a standing health record with trend markers, clinical-standard alignment checks, and a
governance layer for accommodations, scheduling, and care-plan integrity. The macro form is
intentionally generic — no individual identity, no personal health data at the template layer. It is
the platform that scales to N recovery cases with zero marginal design cost.

### MICRO — Anthony's post-injury recovery + disability access (tied to the legal ADA matter)

A post-injury recovery and disability-access case run with the weight of a dedicated care-
administration team, explicitly tied to the legal ADA accommodation matter. The anchor event is a
4th-story fall (~2024). This instance proves the macro platform by producing an auditable,
capability-focused record of recovery state, protocol adherence, and accommodation needs for the
ADA proceeding. The accommodation record produced by this instance feeds directly into
`organs/legal/` for the active ADA employment matter — the two organs share the same evidentiary
thread. No personal name is used in the record; the instance relationship alone is described.

---

## The rival institution

A concierge medical practice or premium recovery team: a coordinated bench of care coordinator,
rehab tech, disability access coordinator, and appointment scheduler working continuously behind a
single patient's licensed clinical team. That is institutional weight only purchasable at
significant cost. This organ delivers the same coordination function from idle fleet capacity —
14K-16K work-units/month, with a steady-state recovery consuming roughly 15-30 of them. The organ
converts idle capacity into institutional continuity.

---

## The legal organ link

This organ does not operate independently of `organs/legal/`. The accommodation track (workflow:
accommodation → documentation) produces the structured limitation/request/status record that the
legal organ consumes for the ADA employment matter. The handoff is explicit: the health organ
records functional limitations and accommodation correspondence; the legal organ applies legal
strategy. Neither organ gives advice in the other's domain. The safety sentinel blocks health-organ
outputs from crossing into legal advice; the legal organ's ethics wall blocks legal outputs from
crossing into clinical advice.

---

## The authority contract

| What the organ does | What the human does |
|---|---|
| Tracks health state, protocol adherence, appointment calendar | Attends appointments, follows protocol, reports symptoms — the patient is the authority over their own body |
| Documents functional limitations and accommodation correspondence | Directs every accommodation request; the legal organ applies legal strategy to the ADA matter |
| Produces structured records, trend markers, and proximity alerts | Clinician interprets clinical meaning; patient reviews and corrects all entries |
| Drafts the recovery-posture brief from state, protocol, and calendar inputs | Confirms posture is accurate before it is shared with any provider |
| Flags state changes and overdue items | Clinician is the only escalation path for clinical concerns |
| Enforces the safety boundary on every output | Reviews safety certification; clinician resolves any flagged concern |

The pattern is: **record, track, surface — the human decides, the clinician directs, the organ
enables.**

---

## The health state posture sequence

```
INTAKE → ACTIVE → REVIEW → HOLD → COMPLETED
```

Posture rules:
- The sequence advances; it does not regress silently
- Progression changes require patient or clinician confirmation
- HOLD is a declared state (e.g., awaiting specialist, between protocols), not an implied pause
- COMPLETED is a full closeout — what was treated, achieved, deferred, and outstanding

---

## Hard guardrails (non-negotiable, every beat)

- **No diagnosis, no prescription, no medical advice output.** This organ is operations
  infrastructure, not a clinician. Every clinical judgment remains with the licensed provider.
- **No independent clinical decisions.** Every treatment shift, diagnosis, and prescription
  stays with the licensed provider. The organ tracks adherence; it does not recommend deviation.
- **No self-scheduling or self-booking.** The appointment calendar is advisory-only. Only the
  patient confirms appointments with providers. The organ tracks; the patient acts.
- **Patient records are secure and scoped.** Medical data stays with the patient and their
  licensed care chain. Protected health information does not leak through any output path.
- **Output is evidence-first and traceable.** State records, protocol logs, and accommodation
  documentation support the patient's and provider's judgment. Nothing is final until the
  patient reviews it.
- **Safety concerns are escalated, never self-resolved.** If the organ surfaces concerning
  patterns, only a clinician interprets them. The safety sentinel flags and surfaces; it does
  not diagnose or recommend clinical action.
- **Accommodation records feed the legal organ, not replace it.** The ADA matter is a legal
  proceeding directed by counsel. Health organ outputs are structured records; the legal organ
  applies legal strategy. The health organ does not give legal advice.
- **This organ does not replace a doctor, therapist, hospital, or any licensed professional.**
  It replaces the coordination headcount that multiplies every clinical hour's effectiveness.

---

## What gets built next

From the scaffold stage (10% → building 30%):

1. Run workflow 2 (State → record) daily — establish the baseline log with structured markers
2. Run workflow 1 (Intake → posture) on the first real health event — capture the current
   recovery state into the one-page posture brief
3. Wire the accommodation record into the legal organ's intake — prove the cross-organ handoff
4. Operationalize the safety sentinel as an executable gate on every output workflow
5. Write the first reception script — a conductor prompt that loads the KERNEL boundary and
   routes the patient's input to the correct workflow

---

*Companion documents: [`CHARTER.md`](CHARTER.md) (org-chart + 6-workflow orchestration + role
assignments + leverage math), `MACRO-FACE.md` (the health institution platform pitch),
`MICRO-FACE.md` (Anthony's post-injury recovery instance).*
