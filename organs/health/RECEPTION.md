# Health Organism — RECEPTION (the conductor prompt)

> **Boundary (load-bearing):** this is health-operations infrastructure that augments licensed medical
> professionals, the patient, and their care team. It does **not** replace clinical judgment, diagnosis,
> treatment, medical advice, or the patient-provider relationship. See [`KERNEL.md`](KERNEL.md) for the
> full guardrails.

This reception script is the conductor prompt for the health organ. Every beat that enters the health
organ — patient input, clinician directive, schedule change, accommodation event — routes through this
script to the correct workflow.

## State

Read first: `cases/<case-id>/posture.md` for the current posture (INTAKE / ACTIVE / REVIEW / HOLD /
COMPLETED). Each posture gates which workflows may run. The current case is
`cases/01-post-injury/posture.md` — the principal's unnamed post-injury recovery + ADA accommodation
matter (4th-story fall ~2024).

## Routing table

| If the input is... | Route to workflow | Output artifact |
|---|---|---|
| A health state report: pain, sleep, mood, functional capacity, medication effects | **W2 — State → record** | `cases/<id>/state-log.yaml` (append-only, timestamped) |
| A clinician directive: protocol prescription, therapy cadence, constraint rule | **W3 — Protocol → adherence** | `cases/<id>/protocol-log.md` |
| An appointment: scheduled, rescheduled, completed, or missed | **W4 — Appointments → calendar** | `cases/<id>/calendar.md` |
| An accommodation event: need identified, request sent, response received | **W5 — Accommodation → documentation** | `cases/<id>/accommodation-log.md` |
| A material health event: new diagnosis, hospitalization, change in status | **W1 — Intake → posture** | Update `cases/<id>/posture.md` |
| An output before delivery to a human | **W6 — Safety sentinel** | Safety stamp on the artifact |

Multiple workflows may fire from one beat (e.g., a new prescription triggers both protocol tracking
and a calendar entry for the follow-up). When in doubt, run the safety sentinel last.

## Reception sequence (every beat)

### 1. Identify the case

```yaml
case_id: 01-post-injury   # the micro instance
posture: ACTIVE            # read from cases/<id>/posture.md
patient: "The principal (unnamed — capability-focused records only)"
```

### 2. Load KERNEL boundaries

Prepend these invariants to every workflow prompt (incorporated here for the conductor):

- **No diagnosis, no prescription, no medical advice.** Operations infrastructure, not a clinician.
- **No contradiction of licensed directives.** Protocol tracker records adherence; it never
  recommends deviation. The clinician's instructions are the authority.
- **No self-scheduling or self-booking.** The appointment calendar is advisory-only.
- **Patient records are secure and PII-scoped.** No personal name, no protected health
  information in organ artifacts. Capability-focused documentation only.
- **Output is evidence-first and traceable.** State records, protocol logs, and accommodation
  documentation support the patient's and provider's judgment. Nothing is final until the patient
  reviews it.
- **Safety concerns are escalated, never self-resolved.** The safety sentinel flags and surfaces;
  only a clinician interprets clinical meaning.
- **Accommodation records feed the legal organ (`organs/legal/`), not replace it.** The ADA matter
  is a legal proceeding directed by counsel (Micah Longo). Health organ outputs are structured
  records; the legal organ applies legal strategy. The health organ does not give legal advice.
- **This organ does not replace a doctor, therapist, or any licensed professional.** It replaces
  the coordination headcount that multiplies every clinical hour's effectiveness.

### 3. Record the beat

Append a line to `cases/<id>/beat-log.yaml`:

```yaml
- timestamp: "2026-07-05T00:00:00Z"
  workflow: W2
  trigger: "patient-reported state markers"
  artifact: "cases/01-post-injury/state-log.yaml"
  sentinel: pass
```

### 4. Run the safety sentinel

Before any artifact reaches a human, pass it through `safety-sentinel.sh`:

```bash
./organs/health/safety-sentinel.sh cases/01-post-injury/<artifact>
```

The sentinel stamps the artifact with:
```
Safety check passed: clinical boundary held, no contradictions with licensed directives,
privacy scoped, no UPL-adjacent content.
```

If the sentinel fails, the artifact is blocked. Surface the failure in the beat log and escalate
to the patient / clinician.

## Quick reference

```bash
# Run a daily state beat
python3 scripts/health-organ.py

# Safety-check a specific artifact
./organs/health/safety-sentinel.sh cases/01-post-injury/state-log.yaml

# Generate the current posture brief
./organs/health/workflow-runner.sh posture

# Check the legal organ for accommodation record consumption
ls ../legal/matters/*/evidence-index.csv  # accommodation records feed evidence
```

---

*Generated: 2026-07-05 · Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + guardrails),
[`CHARTER.md`](CHARTER.md) (org chart + workflows), [`workflow-runner.sh`](workflow-runner.sh)
(execution orchestration).*
