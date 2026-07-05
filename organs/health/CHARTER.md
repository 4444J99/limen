# Health Organism — CHARTER (the concierge recovery team)

> **Boundary:** this is health-operations infrastructure that augments licensed medical
> professionals, the patient, and their care team. It does **not** replace clinical judgment,
> diagnosis, treatment, medical advice, or the patient-provider relationship. Patient safety,
> privacy, and the primacy of the licensed care chain remain non-negotiable. See
> [KERNEL.md](KERNEL.md) for the full guardrails.

## What it rivals — the concierge medical / recovery team standard

A concierge medical practice or premium recovery team doesn't have better doctors — it has
**more continuity**. For every hour the attending physician spends on diagnosis and treatment,
a coordinated team spends dozens of hours on the work that makes that hour effective: protocol
tracking, state monitoring, care-team coordination, accommodation documentation, schedule
management, and discharge-readiness verification. The patient navigating a complex recovery
without support has the same medical team but **none of the administrative backbone**.

This organ supplies that backbone as persistent AI roles that run continuously against the
recovery. It does not replace any clinician — it replaces the care-coordination headcount that
multiplies every clinical hour's effectiveness.

The concierge standard, distilled: **every protocol is tracked before the next session,
every state delta is recorded before the next beat, every appointment is scheduled before
the window closes, and every accommodation is documented before it is needed.** This organ
makes that the default operating state for one person recovering from a complex injury.

## Institutional weight — how idle fleet capacity becomes a recovery team

VLTIMA's fleet produces 14K-16K idle AI workunits per month. This organ converts that spare
capacity into ongoing health operations. The mapping:

| Fleet idle capacity (supply) | → | Health organ demand |
|---|---|---|
| Unlimited cheap reads + writes | → | Continuous protocol tracking, symptom logging, state updates |
| Background processing beats | → | Daily standing updates, trend detection, appointment proximity alerts |
| Structured-data workflows | → | Health state records, capability-trend charts, protocol-adherence logs |
| Cross-model verification | → | Safety sentinel checks on every output — never contradicts a clinician |
| Document processing | → | Accommodation documentation, care-team communications, visit summaries |

The binding constraint is not capacity — it is **a recovery to manage**. One active recovery
consumes approximately 15-30 workunits/month in steady-state operations. A fleet of 14K+ idle
workunits can sustain hundreds of concurrent recoveries. The first instance (the principal's
unnamed post-injury recovery + ADA accommodation matter) proves the pipeline; scaling means adding
cases, not capacity.

## The org-chart (AI roles, human-supervised)

| Role | Institution equivalent | Does | Human check |
|---|---|---|---|
| **The Patient** *(the human)* | The person recovering | decides what the body needs, reports state, attends all clinical appointments, makes all health decisions | — (this is the human) |
| **The Care Team** *(licensed clinicians)* | Specialists, therapists, PCP | diagnose, treat, prescribe, perform procedures, direct the protocol | — (these are the licensed humans) |
| **Recovery Coordinator** | Care coordinator / case manager | maintains the single source of truth: current protocol, adherence log, next-session prep, open coordination items, and risk flags | patient or clinician confirms posture assessment |
| **State Recorder** | Intake nurse / monitoring tech | captures health state at each beat: symptoms, functional status, pain/sleep/mood markers, capability deltas since last recorded | patient reviews and corrects state entries |
| **Protocol Tracker** | Rehab tech / therapy aide | tracks every prescribed action against the protocol: exercises done, medications taken, appointments kept, specialists seen; flags skipped or overdue items | clinician reviews adherence summary at interval |
| **Accommodation Clerk** | Disability access coordinator | documents functional limitations, accommodation needs, reasonable-accommodation requests, and correspondence trail for the ADA/legal track | patient reviews and directs legal action |
| **Appointment Scheduler** | Medical scheduling clerk | maintains the appointment calendar across all specialists, therapy types, and follow-ups; produces proximity alerts and identifies scheduling conflicts | patient books and confirms; scheduler tracks |
| **Safety Sentinel** | Quality & safety officer | enforces the boundary (no clinical advice, no diagnosis), verifies no output contradicts a licensed directive, and flags any documented state that warrants clinician attention | clinician is the only escalation path for clinical concerns |

The point of the chart: each role is a **workflow the conductor can run continuously**, so the
recovery is always organized, always tracked, always documented — the leverage a concierge team
buys with headcount.

The patient and their licensed clinicians remain the center of gravity. These roles do not make
health decisions; they prepare the ground so the patient's and clinicians' decisions are better
informed and the recovery produces an auditable record.

## The workflows it runs

Each workflow maps to the 5-primitive kernel (Member/Mandate/Standing/Standard/Governance) and
produces a specific artifact. Workflows run on a **cadence** — continuous for state, daily for
protocol, weekly for posture, on-demand for accommodation.

### 1. Intake → posture (Standing + Member)

- **Trigger:** new recovery case opened or event occurs (new diagnosis, change in status,
  hospitalization, discharge).
- **Process:** capture the patient's current functional state (Member), the active protocol(s)
  and diagnosis scope (Mandate), current functional baseline, open care items, risks, and
  accommodation posture (Standing).
- **Runs:** on intake + on any material health event.
- **Output:** a living recovery-posture brief — one page, always current. Sections: patient
  baseline, active protocols, current functional status, open coordination items, risk flags,
  accommodation status.
- **Human gate:** patient reviews and approves posture assessment; clinician validates
  clinical content.

### 2. State → record (Member)

- **Trigger:** daily beat or patient-reported change.
- **Process:** capture health state markers: pain level, sleep quality, mood/energy, functional
  capacity (what the body can do today vs. yesterday), medication effects, new symptoms. Track
  trend: improving, stable, or declining per marker. No interpretation — recorded observation
  only.
- **Runs:** daily minimum; optionally on each patient-reported beat.
- **Output:** a dated state log entry with structured markers and a trend indicator. Each
  entry is timestamped and append-only.
- **Human gate:** patient reviews and corrects entries. Trend flags are advisory — the
  clinician interprets clinical meaning.

### 3. Protocol → adherence (Mandate + Standard)

- **Trigger:** protocol prescribed, modified, or session completed.
- **Process:** every prescribed action (exercise, therapy session, medication dose, specialist
  visit, test) is tracked against the protocol schedule. Completed items are logged with
  timestamp and notes. Missed or overdue items are flagged with proximity. Protocol deviations
  (patient-modified or clinician-modified) are recorded with rationale.
- **Runs:** on each prescribed action — daily scan for adherence completeness.
- **Output:** protocol-adherence log — a chronological list of every prescribed action with
  status (done/skipped/rescheduled/deferred), timestamp, and notes. Adherence rate calculated
  per period.
- **Human gate:** clinician reviews adherence at each visit or by agreed cadence. The tracker
  never enforces compliance — it only records and surfaces.

### 4. Appointments → calendar (Standing + Governance)

- **Trigger:** appointment scheduled, rescheduled, completed, or missed.
- **Process:** every clinical appointment (specialist, therapy, primary care, test, procedure)
  is tracked with date, time, provider, location, prep instructions, and follow-up window. Lead-
  time alerts at configurable thresholds (14 days, 7 days, 3 days, 24 hours). Conflicts between
  appointments flagged. Post-appointment follow-up items created.
- **Runs:** daily — calendar rebuilt every 24h with proximity alerts and conflict scan.
- **Output:** appointment calendar — all clinical events sorted by proximity, with alert status,
  prep notes, and post-visit action items.
- **Human gate:** patient books all appointments; scheduler tracks what is booked. Patient
  confirms scheduling changes.

### 5. Accommodation → documentation (Governance + Member)

- **Trigger:** accommodation need identified, requested, granted, denied, or modified.
- **Process:** capture functional limitations (what the body cannot do or cannot sustain), map
  to accommodation requests (schedule flexibility, remote/rest breaks, equipment, task
  reassignment), track the request status (submitted, under review, granted, denied, appealed),
  and maintain the correspondence trail. Designed explicitly to produce the record for the ADA
  legal matter.
- **Runs:** on each accommodation event; posture review weekly during active accommodation
  processes.
- **Output:** accommodation record — a structured log of every limitation, request, response,
  and status change. Citable in the ADA proceeding.
- **Human gate:** patient directs every accommodation request and response. Legal organ
  (organs/legal/) consumes these records for the ADA matter.

### 6. Safety sentinel (Governance — cross-cuts all)

- **Trigger:** every output before delivery to the patient or clinician.
- **Process:** each deliverable is checked against: clinical boundary (no diagnosis, no treatment
  advice, no prescription), contradiction guard (nothing that contradicts a licensed directive),
  privacy scope (no protected health information outside authorized channels), and UPL-adjacent
  boundary (no legal advice about accommodation rights — that belongs to the legal organ).
- **Runs:** continuously, as a gate on every output workflow.
- **Output:** safety certification — a stamp on every deliverable: "Safety check passed:
  clinical boundary held, no contradictions with licensed directives, privacy scoped."
- **Human gate:** clinician is the final arbiter of all clinical questions. The sentinel
  never self-resolves a clinical concern.

### Workflow orchestration diagram

```
                  ┌──────────────┐
                  │   Intake →   │
                  │   Posture    │
                  │ (Standing +  │
                  │   Member)    │
                  └──────┬───────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
   ┌──────────┐  ┌──────────────┐  ┌──────────┐
   │  State   │  │  Protocol   │  │Appt.    │
   │ → Record │  │ → Adherence │  │→ Calendar│
   │ (Member) │  │(Mandate +   │  │(Standing)│
   │          │  │  Standard)  │  │          │
   └─────┬────┘  └──────┬───────┘  └────┬─────┘
          │              │              │
          └──────────────┼──────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │Accommodation │
                  │→ Document    │
                  │(Governance + │
                  │  Member)     │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │   Safety     │
                  │  Sentinel    │
                  └──────┬───────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
       ┌──────────────┐    ┌──────────────┐
       │  Patient     │    │  Care Team   │
       │ (decides)    │    │ (directs)    │
       └──────────────┘    └──────────────┘
```

Every workflow feeds into the next or the legal organ. State record informs the protocol
adherence log. Protocol log + appointment calendar support the accommodation record. Safety
sentinel gates everything. The patient and their clinicians stand at the end of every path.

## Inputs / outputs

### Inputs (what the patient or clinicians supply)

| Input | Format | Source | Maps to kernel |
|---|---|---|---|
| Protocol and directives | Clinician instructions, discharge plan, prescription | Licensed clinician | Mandate + Standard |
| Health state reports | Patient-reported markers: pain, sleep, mood, function | Patient | Member |
| Symptom / side-effect reports | Free-form narrative or structured check-in | Patient | Member |
| Appointment confirmations | Date, time, provider, location | Patient books; scheduler records | Governance |
| Accommodation needs / responses | Correspondence, decision letters, functional limitation notes | Patient, employer, ADA process | Governance + Member |
| Patient corrections | Feedback on any recorded entry | Patient | Governance |
| Clinician changes to protocol | Modified instructions, new directives | Licensed clinician | Mandate |

### Outputs (what the organ delivers)

| Output | Format | Cadence | Maps to kernel |
|---|---|---|---|
| Recovery-posture brief | Markdown (one page) | Updated on event + weekly | Standing |
| State log | Structured entry (JSON/MD) per beat | Daily minimum, append-only | Member |
| Trend chart | Visual or tabular — per-marker trajectory | Updated with each state entry | Member |
| Protocol-adherence log | Chronological list with status per action | Updated per action + daily scan | Mandate |
| Adherence rate | Percentage per period (weekly/monthly) | Updated with adherence log | Mandate + Standard |
| Appointment calendar | Sorted list by proximity with alerts | Rebuilt daily | Standing + Governance |
| Accommodation record | Structured log: limitation → request → status → correspondence | Updated per accommodation event | Governance + Member |
| Safety certification | Inline stamp on each deliverable | Every output | Governance |

All outputs are **advisory to the patient and their care team**. None are self-acting, none
replace clinical judgment, and none are communicated externally without the patient's direction.

## How the institutional weight works (the leverage math)

A concierge recovery team's leverage comes from **ratio**: one patient with 1-2 clinicians, a
care coordinator, a scheduler, a rehab tech, and a disability access coordinator. That is
effectively a 1:5+ ratio. The clinicians' hour is worth 5x because the coordination team
tracks, records, schedules, and documents while the clinicians diagnose and treat.

This organ delivers that coordination bench as **continuous processing**. The key multipliers:

| Factor | Solo recovery | This organ (steady state) | Source of leverage |
|---|---|---|---|
| State recording | Patient must self-track, often inconsistently | Daily structured capture with trend markers | Background processing beat every 24h |
| Protocol adherence | Manual log + memory | Automated per-action tracking with overdue flags | Continuous processing on every beat |
| Appointment tracking | Patient maintains calendar across multiple providers | Daily automated calendar with proximity alerts and conflict detection | Runs every 24h regardless of patient attention |
| Accommodation documentation | Patient builds record under stress | Structured capture per event — always ready for the ADA matter | Document processing workflows |
| Care-team coordination | Patient relays between specialists | Single-source posture brief any provider can review | State + protocol + calendar feeds one standing record |
| Safety boundaries | Patient self-polices what is clinical vs. operational | Automated sentinel on every output | Cross-model verification run |
| Total effective coordination bench | 1 person (the patient, already under cognitive load) | 6 coordination roles running continuously | Idle fleet capacity mapped to health operations |

The patient still does what only the patient can do: attend appointments, follow protocols,
report symptoms, and direct their own recovery. The clinicians still do what only clinicians
can do: diagnose, treat, prescribe, and operate. The organ does what coordination headcount
would do: track, record, schedule, document, and verify.

## First proof: the micro instance

The micro instance — the principal's unnamed post-injury recovery and ADA accommodation matter — is
the first deployment. The anchor event is a 4th-story fall (~2024). No personal name is used in the
case record; documentation stays capability-focused.

The rollout order, matching the workflows above:

1. **Workflow 2 (State → record)** runs first — establishes the daily baseline log and trend
   tracking. Minimum viable: patient reports markers, recorder timestamps and structures them.
   Requires zero clinician setup.

2. **Workflow 1 (Intake → posture)** runs next — captures the current recovery state, active
   protocols, and open coordination items into the one-page posture brief.

3. **Workflow 4 (Appointments → calendar)** runs as soon as the appointment schedule is
   known — produces the living calendar with proximity alerts.

4. **Workflow 3 (Protocol → adherence)** runs once the protocol is prescribed and recorded —
   tracks actions against the regimen.

5. **Workflow 5 (Accommodation → documentation)** runs whenever an accommodation need is
   identified. Produces the record that feeds into the legal organ's ADA matter workflow.

6. **Workflow 6 (Safety sentinel)** gates all outputs from step 1 onward.

The SCRUM: run workflow 2 (state → record) daily and workflow 1 (posture) weekly from the start.
Workflows 3-5 activate as the required inputs (protocol, appointments, accommodation needs)
become available.

## Future scaling (non-blocking, noted for later maturity bands)

When the organ reaches building stage (30%+):

- **Multi-case support**: the same workflow stack runs against N recovery cases simultaneously,
  each with its own state log, protocol tracker, appointment calendar, and accommodation record.
- **Clinician-accessible posture brief**: a shareable one-page summary any new provider can
  review at intake — reduces repeat-history burden on the patient.
- **Standard protocol library**: evidence-based post-injury protocol templates (orthopedic,
  neurological, post-surgical, etc.) that can be loaded and customized, reducing setup time
  for each new case.
- **Accommodation letter generator**: structured accommodation request drafts based on the
  documented functional limitations and the relevant legal framework — always reviewed and
  directed by the patient and their legal counsel.
- **Medication/dose tracking**: structured log of medications, dosages, schedules, and effects,
  always advisory and clinician-verified.
- **Discharge-readiness checklist**: a structured evaluation of protocol completion, functional
  recovery milestones, and accommodation closure criteria.

All future builds preserve the invariant: no clinical advice, no diagnosis, no replacement of
licensed professionals, and the patient remains the decision-maker for their own body.

## Constraint registry

| Constraint | Why | How it's enforced |
|---|---|---|
| No clinical advice or diagnosis | Practicing medicine without a license is illegal and dangerous | Safety Sentinel blocks every output; KERNEL.md is prepended to every workflow prompt |
| No contradiction of licensed directives | Clinician instructions are the authority; the organ must never undermine them | Protocol tracker records adherence but never recommends deviation; sentinel flags potential contradictions |
| No self-scheduling or self-booking | Only the patient can confirm appointments with providers | Appointment calendar is advisory-only; no output path books anything autonomously |
| Privacy of health information | Protected health information must never leak | All outputs scoped to the patient and their designated care team; accommodation record is role-scoped |
| Patient owns every health decision | The person recovering is the authority over their own body | Every output is advisory; nothing self-executes; the patient is the terminal reviewer for non-clinical content |
| Safety concerns escalated, never resolved | If the organ detects concerning patterns, only a clinician can interpret them | Safety sentinel flags and surfaces; never self-diagnoses or recommends action |
| Accommodation records feed legal, not replace it | The ADA matter is a legal proceeding directed by counsel | Accommodation outputs are structured records — the legal organ consumes them; the health organ does not give legal advice |

All constraints are non-negotiable. They are the load-bearing walls of this organ.

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map + hard guardrails),
[`MACRO-FACE.md`](MACRO-FACE.md) (the health institution platform pitch),
[`MICRO-FACE.md`](MICRO-FACE.md) (the unnamed post-injury recovery instance).*
