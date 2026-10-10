# Health / Body — MICRO FACE
## The principal's unnamed post-injury recovery + ADA accommodation matter

*Anthony's live health deployment · Internal review only · No personal identifiers in the record*

> **What you are reading:** the micro face is the proof that the macro health platform holds
> for a real recovery case. The platform description is in [`MACRO-FACE.md`](MACRO-FACE.md).
> No personal name, no protected health information, and no clinical detail beyond functional
> capability posture is recorded in this document.

---

## Why this instance exists

The anchor event is a **4th-story fall (~2024)**. The principal — unnamed in all records —
sustained injuries from a fall that produced persistent functional limitations requiring
coordinated care across multiple specialists, ongoing therapy, and workplace accommodations
under the Americans with Disabilities Act.

This instance exists for two interconnected reasons:

1. **Recovery management** — the coordination load of a multi-specialty post-injury recovery
   (orthopedic, neurological, rehabilitative) without a dedicated care-administration team
   falls entirely on the patient. This instance supplies that coordination backbone.

2. **ADA accommodation matter** — the functional limitations from the injury intersect with
   an active ADA employment proceeding directed by counsel. The accommodation record produced
   by this instance feeds directly into `organs/legal/` for the legal organ's ADA matter
   workflow. The two organs share the same evidentiary thread.

The constraint — unnamed, no personal identifiers, capability-focused documentation — is
structural. The record proves what the institution can do without naming who it does it for.

| Stress test | Why it matters |
|---|---|
| **First state entry logged** | Proves the State → record workflow (W2) produces a structured, timestamped, append-only entry from patient-reported markers |
| **Accommodation record produced** | Proves the Accommodation → documentation workflow (W5) captures functional limitations, request status, and correspondence trail in a format the legal organ can consume |
| **Posture brief shared with a provider** | Proves the Intake → posture workflow (W1) produces a one-page standing record accurate enough to share with a new specialist at intake |
| **Protocol adherence tracked weekly** | Proves the Protocol → adherence workflow (W3) tracks prescribed actions and flags overdue items without clinical overreach |
| **Safety sentinel stamps every output** | Proves the Safety sentinel (W6) enforces the clinical boundary on every deliverable |

---

## Health posture standing

| Field | Value |
|---|---|
| Case record | `organs/health/cases/principal/*` (internal, PII-scoped) |
| Current standing | ACTIVE (all 6 workflows operational) |
| Next standing | REVIEW (after first accommodation cycle closes) |
| Patient | The principal (human — all health decisions are theirs) |
| Clinicians | Licensed specialists — orthopedist, neurologist, physical therapist, primary care |
| Legal counsel | Micah Longo (ADA matter — all legal strategy stays with counsel) |
| Legal organ link | `organs/legal/` — accommodation record feeds the ADA matter workflow |
| Last updated | 2026-07-05 |

---

## What exists now

1. **Organ chartered** — `organs/health/KERNEL.md` + `CHARTER.md` authored with the full
   5-primitive map, institutional prosthesis framing, rival institution, legal organ link,
   hard guardrails, 6-workflow orchestration, 7 AI role org-chart, and leverage math.

2. **Legal organ link specified** — the Accommodation → documentation workflow (W5) produces
   a structured record that the legal organ consumes for the ADA matter. The handoff is
   explicit: health records functional limitations and correspondence; legal applies strategy.
   Neither organ crosses domains.

3. **Posture sequence defined** — INTAKE → ACTIVE → REVIEW → HOLD → COMPLETED with clear
   authorization rules per posture.

4. **Safety boundary established** — every output carries a safety certification check:
   clinical boundary held, no contradictions with licensed directives, privacy scoped,
   no UPL-adjacent content.

5. **Cross-organ constraint** — the safety sentinel prevents health-organ outputs from
   crossing into legal advice; the legal organ's ethics wall prevents legal outputs from
   crossing into clinical advice.

6. **First state log entry created** — `cases/01-post-injury/state-log.yaml` with structured
   markers (pain, sleep, mood, energy, cognition, functional capacity, medication effects)
   and trend indicators. Workflow 2 (State → record) is operational: daily beat produces a
   timestamped, append-only entry.

7. **Protocol adherence log produced** — `cases/01-post-injury/protocol-log.md` with 96%
   adherence rate across physical therapy (100%), cognitive pacing (88%), appointments (100%),
   and medication adherence (100%). Workflow 3 (Protocol → adherence) tracks every prescribed
   action with status and timestamps.

8. **Accommodation record linked to legal organ** — `cases/01-post-injury/accommodation-log.md`
   with 4 tracked accommodation requests (3 granted, 1 under review), functional limitation
   documentation, correspondence trail, and explicit handoff to `organs/legal/` for the ADA
   matter. Workflow 5 (Accommodation → documentation) is operational.

9. **Accommodation record wired into legal organ intake** — the structured limitation/request/
   response log is consumable by `organs/legal/` as evidence. Risk flags and escalation triggers
   are documented. Neither organ crosses domains.

10. **Safety sentinel operationalized** — `organs/health/safety-sentinel.sh` is an executable
    gate that checks every deliverable against 6 guardrails (clinical boundary, contradiction
    guard, self-scheduling restriction, privacy scope, UPL boundary, legal boundary) and stamps
    the artifact on pass.

11. **Reception script written** — `organs/health/RECEPTION.md` is the conductor prompt that
    loads KERNEL boundaries and routes patient input to the correct workflow. Includes routing
    table, reception sequence, and quick reference.

12. **Workflow runner operational** — `organs/health/workflow-runner.sh` orchestrates all 6
    workflows, calls the Executive Health Office (`scripts/health-organ.py`) for the daily
    beat, and routes every output through the safety sentinel.

13. **Executive Health Office integrated** — `scripts/health-organ.py` (the broader daily health
     operations engine) runs as the organ's primary execution engine, producing the health
     briefing, digest, regimen, and surveillance reports, and stamping liveness for proprioception.

14. **Appointment calendar created** — `cases/01-post-injury/calendar.md` with 6 upcoming
     appointments across PT, orthopedics, and neurology, sorted by proximity with alert status,
     prep notes, post-visit action items, prep-to-do tracking, conflict scan, and risk flags.
     Workflow 4 (Appointments → calendar) is operational.

15. **Beat log established** — `cases/01-post-injury/beat-log.yaml` — an append-only orchestration
     record capturing every reception event: which workflow fired, trigger, artifact produced,
     and sentinel status. Provides the audit trail for proprioception.

---

## The non-negotiable constraints (this instance specifically)

These are in addition to the organ-wide guardrails in KERNEL.md. They apply to this micro
instance because it touches both a clinical recovery and a legal proceeding:

- **No personal name in the record.** The case is tracked by functional limitations, recovery
  milestones, and accommodation status — not by identity. Nobody reading the record should
  be able to identify the person it describes.
- **No protected health information in organ artifacts.** Medical details that would identify
  the patient or constitute a HIPAA-protected disclosure stay within the patient's own private
  channels. Organ outputs are capability-focused and role-scoped.
- **No clinical detail beyond what the patient authorizes.** The patient controls what is
  recorded, what is shared, and with whom. Every entry is patient-corrected before it becomes
  part of the standing record.
- **Accommodation records are raw material for legal strategy, not legal advice.** The
  functional limitation log and correspondence trail are structured records. The legal organ
  applies legal strategy. This organ never suggests what accommodation should be requested
  or what legal argument to make.
- **The recovery track and the legal track are parallel, not merged.** The organ maintains
  two distinct streams: clinical recovery operations (state, protocol, appointments) and
  accommodation documentation (limitations, requests, responses). They inform each other but
  never blur. The safety sentinel prevents clinical outputs from being interpreted as legal
  positions and vice versa.

---

## Next proof step — from ACTIVE to REVIEW

The organ reached ACTIVE standing on 2026-07-05. The next milestone — REVIEW — requires:

1. **2+ weeks of daily state entries** — a trend baseline across pain, sleep, mood, energy,
   cognition, and functional capacity that shows direction (improving/stable/declining) per
   marker.
2. **One full accommodation cycle completed** — an accommodation request that goes through the
   entire lifecycle: need identified → request submitted → employer response → accommodation
   enforced or escalated to legal organ.
3. **An accommodation record successfully consumed by the legal organ** — counsel (Micah Longo)
   or the legal organ's evidence index (`organs/legal/matters/*/evidence-index.csv`) contains
   a row referencing the health organ's accommodation correspondence trail.
4. **Safety sentinel passes on every artifact produced** — zero sentinel failures across all
   workflows for a continuous 14-day period.
5. **Posture brief shared with a provider** — the one-page posture brief is confirmed accurate
   by the patient and shared with at least one new specialist at intake, proving the burden-
   reduction thesis.

---

*Companion documents: [`MACRO-FACE.md`](MACRO-FACE.md) (platform description),
[`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`CHARTER.md`](CHARTER.md) (org chart + 6 workflows + leverage math).*
