# Legal Organism — CHARTER (the virtual firm)

> **Boundary:** an AI-run legal *operations* firm that works under and for a licensed attorney. It does
> not practice law or give legal advice. The attorney of record directs it and owns every output. See
> [KERNEL.md](KERNEL.md) for the full guardrails.

## What it rivals

A top-tier litigation firm — the **Cochran standard**: not one lawyer with a shoebox, but a coordinated
bench where nothing is missed, every fact is indexed, every deadline is owned, and the attorney walks in
prepared the way only a well-staffed firm allows. This organ supplies that bench as AI roles.

## The org-chart (AI roles, human-supervised)

| Role | Does | Human check |
|---|---|---|
| **Managing Partner (the attorney)** | strategy, judgment, advice, all filings + appearances | — (this is the human) |
| **Case Manager** | maintains the single source of truth: posture, deadlines, open obligations | attorney approves the calendar |
| **Paralegal** | builds + maintains the evidence index and chain-of-custody record | attorney verifies completeness |
| **Researcher** | pulls controlling statute/precedent, maps elements-to-evidence (real authority only) | attorney validates every cite |
| **Drafter** | produces document *skeletons* (timelines, fact statements, correspondence drafts) | attorney rewrites + owns |
| **Ethics/Conflict Sentinel** | enforces privilege, UPL, and conflict guardrails on every output | attorney is final arbiter |

The point of the chart: each role is a workflow the conductor can run continuously, so the matter is
always organized, always current, always ready — the leverage a big firm buys with headcount.

## The workflows it runs

1. **Intake → posture.** Capture the matter against the kernel (Member/Mandate/Standing/Standard/
   Governance). Output: a living case-posture brief.
2. **Evidence → index.** Every document, message, and record indexed with date, source, and what it
   proves; a chain-of-custody log. Output: an evidence index a paralegal would be proud of.
3. **Law → elements map.** The controlling standard broken into elements; each element linked to the
   evidence that supports it and the gaps that don't yet. Output: an elements-to-evidence matrix.
4. **Deadlines → calendar.** Every obligation and date tracked with lead-time alerts. Output: a deadline
   calendar (attorney-approved).
5. **Draft → review.** Document skeletons generated for the attorney to correct and adopt. Output:
   reviewable drafts — never anything filed or sent by the system.

## Inputs / outputs

- **Inputs:** the matter facts (client-provided), the documents/evidence, the controlling jurisdiction.
- **Outputs:** the case-posture brief, the evidence index, the elements map, the deadline calendar, and
  attorney-reviewed draft work product. All advisory-to-the-attorney; none self-acting.

## First proof

The micro instance — Anthony's ADA employment matter — is the first deployment, packaged as
[FRAMEWORK-FOR-COUNSEL.md](FRAMEWORK-FOR-COUNSEL.md): a deck Counsel can look at and immediately see what an
AI-augmented firm does for his client. Real case facts are placeholders until the client/attorney supply
them; the *structure* is the deliverable.
