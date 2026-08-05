# Sovereign Systems — CHARTER (the boutique service desk)

> **Boundary:** this is AI-run consulting operations that augment Anthony’s hands-on client work. It does
not sell itself, send proposals, take payment, or represent a client. It produces clean, structured
working copy for Anthony to review and act on.

## What it rivals

A boutique agency standard: one principal plus a coordinated bench that keeps discovery, delivery,
quality control, and continuity from slipping. This is not a replacement for human strategy. It is the
operating floor that lets one person run multiple engagements with consistent institutional output.

## The org-chart (AI roles, human-supervised)

| Role | Does | Human check |
|---|---|---|
| **Engagement Partner** *(the human)* | strategic accept/reject, final scope, commitments, external sends | — (this is the human) |
| **Intake Steward** | collects context, captures constraints, builds one client posture record | partner confirms completeness and fairness |
| **Scope Architect** | turns intake into engagement hypothesis, assumptions, exclusions, and effort assumptions | partner approves boundaries before proposal |
| **Delivery Manager** | sequences work into milestones, tracks standing, and surfaces blockers | partner approves reprioritization and commitments |
| **Quality Auditor** | runs deliverable checks against agreed standards and missing assumptions | partner signs off each handoff slice |
| **Risk & Governance Sentinel** | enforces manual-gating: no auto-send, no auto-bill, no blind commitments | partner is final authority for all external action |

## The workflows it runs

1. **Intake → posture.** Client need becomes one record with Member, Mandate, standing, standards, and
   open risks. Output: a single source of truth for the engagement.
2. **Standards → agreement.** Scope, exclusions, timeline, assumptions, and review gates are assembled into
   a proposal-grade draft. Output: draft scope artifact for partner review.
3. **Kickoff → plan.** Engagement milestones are translated into an executable sequence with owners and
   deadlines. Output: a staged execution map (no one-act commits).
4. **Delivery → review.** Work products are drafted, indexed, and evaluated against the standard. Output:
   review-ready draft + quality notes + next-step list.
5. **Handoff → archive.** Every engagement closure writes what was promised, done, deferred, and unresolved
   into the project archive. Output: repeatable closeout package for the next cycle.

## Inputs / outputs

- **Inputs:** live client context, scope statements, context constraints, deadlines, partner preferences.
- **Outputs:** posture record, scope draft, delivery plan, review log, quality checklist, closeout archive.

## First proof: the engagement validator

The first six executable rules are `validate-consulting.py`:

- **Rule #1: Valid Posture** — engagement standing must name a recognised delivery posture in the
  canonical sequence (DISCOVERY → PROPOSAL → ACCEPTANCE → EXECUTION → REVIEW → HOLD → ARCHIVED).
  Stages may not be skipped and may not regress.
- **Rule #2: Manual Mode** — no engagement may claim autonomic delivery. Every milestone must declare
  explicit human gates. The `autonomic` flag is prohibited.
- **Rule #3: 5-Primitive Completeness** — every engagement record must capture all five kernel
  primitives: Member, Mandate, Standing, Standard, and Governance.
- **Rule #4: Scope Integrity** — scope changes must be tracked. Each engagement must carry an explicit
  scope boundary and a change log.
- **Rule #5: No Overreach** — the engagement scope must not claim to provide legal, tax, or medical
  advice. The consulting organ is delivery infrastructure, not professional services.
- **Rule #6: Evidence Integrity** — every `standard.evidence` field must reference real artifacts or
  clear statuses — no TODO, TBD, or placeholder text.

Rules #1-6 are automatically checked by `verify-whole.sh` (the Sovereign Systems step). Run them
manually:

```bash
python organs/consulting/validate-consulting.py path/to/engagement.yaml
python organs/consulting/validate-consulting.py --fleet
python organs/consulting/validate-consulting.py --fleet --quiet
```

The micro instance is currently five named deployments that all pass validation:

- **Maddie** (wellness — scope stability under shifting priorities)
- **Rob** (fitness + chess — cadence stability and funnel engineering)
- **Derek** (education + narrative — cross-domain portability)
- **Jessica** (HR + Styx — greenfield niche entry at DISCOVERY)
- **John F.** (finance — minimal-signal capture at DISCOVERY)

The same process is being proven against all five, with explicit manual checkpoints and no autonomous
outward actions.

## Constraint note for this task state

This organ is intentionally in **working manual prototype** mode. The face is polished, but the operating
contract is still: draft and stage internally, hand over external execution to Anthony, and keep escalation to
human hand the default.
