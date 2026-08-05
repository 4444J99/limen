# Legal Organism — CHARTER (COCHRAN FLAGSHIP)

> **Boundary (load-bearing):** This is legal-operations infrastructure that augments licensed
> counsel. It does **not** practice law, give legal advice, file pleadings, send demand letters,
> negotiate settlements, or make attorney-level legal judgments. Every legal judgment and external
> act remains with the attorney of record.

## 1) Purpose and standard

`organs/legal/` exists to give one attorney the operational benchmark of a top-tier litigation firm.
Its flagship instance is called **COCHRAN**.

COCHRAN is not an alternative to counsel. It is a virtual bench:

- evidence operations
- deadline control
- factual posture tracking
- authority-to-proof mapping
- draft preparation
- ethics/conflict enforcement

So the attorney can spend decision bandwidth on strategy and advocacy rather than reconstructing
process infrastructure.

## 2) Institutional model (what makes this “top-tier”)

One attorney gets institution-level output when work is converted from ad hoc manual effort into
continuous, auditable workflows. COCHRAN adds the equivalent of multiple bench functions without
claiming any legal function ownership:

1. **Memory at tempo:** the matter is represented as structured artifacts that are updated by role-
   specific workflows.
2. **Parallelized support:** research, evidence handling, drafting prep, and docketing move in
   separate streams with explicit handoffs.
3. **Cadence:** continuous/periodic automation of repeatable tasks prevents stale posture.
4. **Attorney choke point:** every deliverable stops at counsel for correction and adoption.

The standard is realized by replacing missing firm headcount with explicit, reviewable workflows.

## 3) Virtual firm org-chart

| AI role | Institution equivalent | Scope | Output | Human gate |
|---|---|---|---|---|
| Managing Partner | Lead attorney | Strategy, legal judgment, filings, settlement decisions, client signoff | — | The human attorney is the only legal decider |
| Case Manager | Litigations case coordinator | Matter registration, posture state, task sequencing, risk register | `matters/<id>/posture.md` | Attorney reviews and approves posture |
| Paralegal | Evidence paralegal | Evidence discovery, indexing, chain-of-custody map, retrieval metadata | `matters/<id>/evidence-index.csv` | Attorney verifies completeness/admissibility |
| Research Associate | Research fellow | Authority retrieval (real authority only), element decomposition, adverse authority scan | `matters/<id>/elements-map.md` | Attorney validates legal interpretation and citations |
| Drafting Clerk | Briefing clerk | Draft skeletons: timelines, fact statements, correspondence, response outlines | `matters/<id>/drafts/*` | Attorney rewrites, adopts, and owns every word |
| Docket Clerk | Court clerk / docket assistant | Deadline and obligation tracking with lead-time alerts | `matters/<id>/deadlines.md` | Attorney approves all deadline posture |
| Ethics and Conflict Sentinel | Governance partner / conflicts committee | UPL boundary, privilege checks, conflict checks, artifact safety gate | `matters/<id>/ethics-log.md` | Attorney is final arbiter |

No AI role has authority to contact courts, clients, witnesses, employers, or outside parties.

## 4) Workflows (buildable now)

Each workflow runs from explicit inputs and produces local artifacts in `organs/legal/matters/<matter-id>/`.

### W1) Intake → Matter Posture

- **Trigger:** new matter opened; major fact change.
- **Input:** attorney-approved intake packet (facts, parties, counsel scope, exclusions, jurisdiction).
- **Process:** create and maintain posture structure: stage, obligations, leverage, risk, and next actions.
- **Output:** `intake.md`, `posture.md`.
- **Cadence:** on intake and material change.
- **Gate:** attorney correction before any downstream workflow consumes it.

### W2) Evidence Intake → Evidence Index

- **Trigger:** a new source doc/message/record arrives or is corrected.
- **Input:** source identifiers, receipt date, provenance, content summary.
- **Process:** append-only index row with element mapping, custody/chain notes, and open contradictions.
- **Output:** `evidence-index.csv`.
- **Cadence:** continuous.
- **Gate:** attorney review before output is treated as complete for strategy packets.

### W3) Law → Elements Matrix

- **Trigger:** active matter, change in theory, new authority discovered.
- **Input:** attorney-approved statutes, regulations, rules, and precedent list.
- **Process:** map each claim element to evidence proof points and gap flags; list adverse authority.
- **Output:** `elements-map.md`.
- **Cadence:** on theory change or evidence change.
- **Gate:** attorney validates all legal maps and authority references.

### W4) Deadlines → Calendar

- **Trigger:** filing deadline, response requirement, hearing date, statutory date, court-ordered date.
- **Input:** source date, rule basis, jurisdiction, lead time.
- **Process:** maintain a living deadline table with alert thresholds and ownership note.
- **Output:** `deadlines.md`.
- **Cadence:** rebuilt daily.
- **Gate:** attorney signs off before calendar is treated as final.

### W5) Drafting Loop

- **Trigger:** attorney request or upstream material change (posture, evidence, element map).
- **Input:** posture, evidence index, element map, deadline posture.
- **Process:** generate draft skeletons only (clearly watermarked as draft/review only).
- **Output:** `drafts/*` (Markdown/structured outputs).
- **Cadence:** on demand + material change.
- **Gate:** attorney reviews and rewrites before any send/filing.

### W6) Ethics and Conflict Gate

- **Trigger:** each draft or exported artifact before delivery to attorney.
- **Input:** artifact content + source lineage.
- **Process:** check UPL boundary, privilege boundary, confidentiality intent, conflict check signals.
- **Output:** ethics pass entry in `ethics-log.md`; blocking reason when gate fails.
- **Cadence:** continuous as artifact output point.
- **Gate:** no artifact leaves the legal organ without a pass record and counsel direction.

## 5) Inputs and outputs

### Inputs required by COCHRAN

- Intake packet from attorney/client.
- Matter scope, jurisdiction, and counsel directives.
- Source materials (documents, notices, emails, exhibits, transcripts).
- Dates and obligations from source rules/court events.
- Counsel corrections and approval marks.
- Privilege/confidentiality metadata.

### Outputs delivered to counsel

- `intake.md` and `posture.md` (living matter posture).
- `evidence-index.csv` (provenance-linked evidence register).
- `elements-map.md` (claim element / proof mapping).
- `deadlines.md` (obligation and due-date surface).
- `drafts/*` (draft skeletons only).
- `ethics-log.md` (audit trail of safety and boundary checks).

## 6) Exact mechanism: one-person institutional weight

COCHRAN creates one-person institutional weight via these concrete mechanisms:

- **One source-of-truth stack:** case posture, evidence, law map, and deadlines are stored as separate,
  linked artifacts that persist between attorney touches.
- **Nonlinear staffing via workflow fanout:** a single human can receive bench-scale support in the same
  cycle through parallel role workflows.
- **Fail-safe cadence:** routine scans and updates continue even when counsel is unavailable.
- **Mandatory counsel choke point:** all outputs are routed for human control, keeping legal authority and
  liability with counsel.

## 7) Target build surface (scaffold-complete set)

```text
organs/legal/
  KERNEL.md
  CHARTER.md
  FRAMEWORK-FOR-MICAH.md
  matters/
    <matter-id>/
      intake.md
      posture.md
      evidence-index.csv
      elements-map.md
      deadlines.md
      drafts/
      ethics-log.md
```

No matter enters external communication by this organ. The workflow stack and artifacts are the
execution backbone that counsel can run against the flagship matter and additional matters as this
organ matures.

## 8) Constraint registry

| Constraint | Enforcement |
|---|---|
| No legal advice / UPL | All outputs are draft/review and all prompts inherit `KERNEL.md` boundaries |
| No self-filing / no autonomous messaging | No output path leaves local matter artifacts |
| No invented law | All authority references are attorney-provided or explicitly verified before use |
| Privilege and confidentiality | Privilege metadata is required for sensitive material; ethics gate records decisions |
| Counsel ownership | No filing, signature, service, or advisory external action without attorney execution |
