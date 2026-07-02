# Legal Organism — CHARTER (the virtual firm)

> **Boundary:** an AI-run legal *operations* firm that works under and for a licensed attorney. It does
> not practice law or give legal advice. The attorney of record directs it and owns every output. See
> [KERNEL.md](KERNEL.md) for the full guardrails and [FRAMEWORK-FOR-COUNSEL.md](FRAMEWORK-FOR-COUNSEL.md) for
> the client-facing deck.

## What it rivals — the Cochran standard

A top-tier litigation firm like Cochran's doesn't have better lawyers; it has **more bench**. For every
hour the named partner spends in court or on strategy, a coordinated team spends dozens of hours on
the work that makes that hour effective: evidence indexing, research, calendaring, drafting, chain-of-
custody discipline. The solo practitioner or lean firm has the same legal skill but **none of the bench**.

This organ supplies that bench as persistent AI roles that run continuously against the matter. It does
not replace the attorney — it replaces the headcount that multiplies the attorney's effective output.

The Cochran standard, distilled: **every fact is found before it is needed, every deadline is owned before
it arrives, and every argument is built on an evidence base that is complete and current.** This organ
makes that the default operating state for one attorney handling any matter.

## Institutional weight — how idle fleet capacity becomes a firm

VLTIMA's fleet produces 14K-16K idle AI workunits per month. This organ converts that spare capacity
into ongoing case operations. The mapping:

| Fleet idle capacity (supply) | → | Legal organ demand |
|---|---|---|
| Unlimited cheap reads + writes | → | Continuous evidence indexing, re-indexing as new docs arrive |
| Background processing beats | → | Daily standing updates, deadline proximity alerts, calendar maintenance |
| Research-oriented models | → | Statute/precedent pulls, elements-to-evidence gap analysis |
| Drafting runs | → | Skeleton document regeneration when facts change |
| Cross-model verification | → | Ethics/conflict sentinel checks on every output before human review |

The binding constraint is not capacity — it is **matters to feed**. One active matter consumes
approximately 20-40 workunits/month in steady-state operations. A fleet of 14K+ idle workunits can
sustain hundreds of matters simultaneously. The first matter (Anthony's ADA employment case) proves
the pipeline; scaling means adding matters, not capacity.

## The org-chart (AI roles, human-supervised)

| Role | Institution equivalent | Does | Human check |
|---|---|---|---|
| **Managing Partner (the attorney)** | Named partner | strategy, judgment, advice, all filings + appearances | — (this is the human) |
| **Case Manager** | Managing clerk / case coordinator | maintains the single source of truth: posture, deadlines, open obligations, risk register | attorney approves the calendar and posture assessment |
| **Paralegal (Evidence)** | Litigation paralegal | builds + maintains the evidence index and chain-of-custody record; cross-references every document against the element map | attorney verifies completeness and admissibility |
| **Researcher** | Junior associate / research fellow | pulls controlling statute/precedent, maps elements to evidence, flags gaps, surfaces adverse authority (real authority only — never fabricated) | attorney validates every cite and legal conclusion |
| **Drafter** | Brief writer / documents clerk | produces document *skeletons* (timelines, fact statements, correspondence drafts, discovery responses) from the evidence index and element map | attorney rewrites, adopts, and owns every word |
| **Calendar/Deadlines Clerk** | Docketing clerk | tracks every court date, statutory deadline, contractual obligation, and lead-time alert; produces a living deadline calendar | attorney approves the calendar weekly |
| **Ethics/Conflict Sentinel** | Ethics partner / conflicts committee | enforces privilege, UPL boundary, and conflict guardrails on every output; certifies each deliverable before it reaches the attorney | attorney is final arbiter |

The point of the chart: each role is a **workflow the conductor can run continuously**, so the matter
is always organized, always current, always ready — the leverage a big firm buys with headcount.

The attorney remains the center of gravity. These roles do not make decisions; they prepare the ground
so the attorney's decisions are better informed and faster.

## The firm-wide workflows it runs

Each workflow maps to the 5-primitive kernel (Member/Mandate/Standing/Standard/Governance) and
produces a specific artifact. Workflows run on a **cadence** — continuous for indexing, daily for
standing, weekly or on-event for drafting.

### 1. Intake → posture (Standing + Member)

- **Trigger:** new matter opened or facts change.
- **Process:** capture client/party identity (Member), the claim/matter scope (Mandate), current
  procedural stage, open obligations, risks, and leverage (Standing).
- **Runs:** on intake + on any material fact change.
- **Output:** a living case-posture brief — one page, always current. Sections: parties, matter,
  stage, deadlines, open items, risk register, leverage assessment.
- **Human gate:** attorney reviews and approves posture assessment.

### 2. Evidence → index (Member + Standard)

- **Trigger:** document ingested or fact asserted.
- **Process:** every document, message, record, and communication is indexed with: date, source,
  author, recipient, provenance, what element it supports, and chain-of-custody entry. Conflicting
  evidence flagged for attorney review.
- **Runs:** continuously as documents arrive; full reconciliation scan weekly.
- **Output:** evidence index — sortable, filterable, citable. Each entry is a row with: ID, date,
  source, type, element(s) supported, chain-of-custody, notes.
- **Human gate:** attorney verifies completeness, relevance, and admissibility.

### 3. Law → elements map (Standard + Mandate)

- **Trigger:** matter opened, new authority identified, or new claim theory emerges.
- **Process:** controlling statute, regulation, and precedent are pulled (real authority only). The
  claim is decomposed into legal elements. Each element is linked to the evidence that supports it
  and flagged where proof is thin or absent. Adverse authority is surfaced, never buried.
- **Runs:** on intake + on any new authority or theory change.
- **Output:** elements-to-evidence matrix — elements as rows, evidence citations as columns, with
  confidence ratings and gap flags.
- **Human gate:** attorney validates every cited authority and the legal element decomposition.

### 4. Deadlines → calendar (Standing + Governance)

- **Trigger:** matter opened, deadline set, date passes, or lead-time threshold hit.
- **Process:** every obligation (court deadline, statutory limitation, contractual date, discovery
  response, filing due date) is tracked with lead-time alerts at configurable thresholds (e.g., 30
  days, 14 days, 7 days, 24 hours). No deadline is owned by the system; all alerts are advisory.
- **Runs:** daily — calendar rebuilt every 24h with proximity alerts.
- **Output:** deadline calendar — all dates sorted by proximity, with alert status. Never misses
  a date because the calendar runs daily whether the attorney looks or not.
- **Human gate:** attorney approves the calendar weekly and confirms critical deadlines.

### 5. Draft → review (Governance + Mandate)

- **Trigger:** attorney requests a draft, or facts/elements change materially.
- **Process:** document skeletons (timelines, fact statements, correspondence drafts, discovery
  responses, demand letters, brief sections) are generated from the evidence index + elements map.
  Every skeleton is watermarked "DRAFT — NOT FILED, NOT FINAL" and routed through the Ethics
  Sentinel before human delivery.
- **Runs:** on demand or on material change to underlying data.
- **Output:** reviewable draft skeletons — never complete filings, never final. Always clearly
  marked as draft work product.
- **Human gate:** attorney rewrites, adopts, and owns every word. Nothing is filed or sent by
  the system.

### 6. Ethics / conflict check (Governance — cross-cuts all)

- **Trigger:** every output before delivery to the attorney.
- **Process:** each deliverable is checked against: privilege boundaries (no privileged material in
  unprivileged channels), UPL guardrails (no legal advice, no practice of law), conflict screens
  (against all matters in the organ), and confidentiality requirements. The sentinel is the
  last automated step before any artifact reaches the attorney.
- **Runs:** continuously, as a gate on every output workflow.
- **Output:** ethics certification — a stamp on every deliverable: "Ethics/Conflict check passed:
  privilege intact, UPL boundary held, no conflicts identified."
- **Human gate:** attorney is the final arbiter of all ethics and privilege decisions.

### Workflow orchestration diagram

```
                  ┌──────────────┐
                  │   Intake     │
                  │  (Member +   │
                  │   Mandate)   │
                  └──────┬───────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
   ┌──────────┐  ┌──────────────┐  ┌──────────┐
   │ Evidence │  │ Law → Map   │  │Deadlines │
   │ → Index  │  │ (Standard)  │  │→ Calendar│
   │(Member)  │  │              │  │(Standing)│
   └─────┬────┘  └──────┬───────┘  └────┬─────┘
          │              │              │
          └──────────────┼──────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │   Draft →   │
                  │   Review    │
                  │ (Governance)│
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  Ethics /    │
                  │  Conflict    │
                  │  Sentinel    │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  Attorney    │
                  │  (Managing   │
                  │   Partner)   │
                  └──────────────┘
```

Every workflow feeds the next. Evidence index supports the elements map. Elements map + evidence
index support drafting. Ethics sentinel gates everything. The attorney stands at the end of every
path — no artifact reaches an external destination without human judgment.

## Inputs / outputs

### Inputs (what the attorney or client supplies)

| Input | Format | Source | Maps to kernel |
|---|---|---|---|
| Matter facts | Structured intake form or narrative | Client / attorney | Member + Mandate |
| Documents, messages, records | PDF, text, email, image, spreadsheet | Client, attorney, discovery | Member + Standard |
| Controlling jurisdiction | Jurisdiction name + area of law | Attorney designates | Standard |
| Attorney instructions | Direction, feedback, correction | Attorney | Governance |
| Deadlines and obligations | Dates, rules, court orders | Court rules, attorney | Standing |

### Outputs (what the organ delivers to the attorney)

| Output | Format | Cadence | Maps to kernel |
|---|---|---|---|
| Case-posture brief | Markdown (one page) | Updated on fact change + weekly | Standing |
| Evidence index | Markdown or structured data (JSON/CSV) | Continuous as docs arrive | Member + Standard |
| Elements-to-evidence matrix | Markdown table or structured data | Updated on new authority/claim change | Standard + Mandate |
| Deadline calendar | Markdown list sorted by proximity | Updated daily | Standing + Governance |
| Draft skeletons | Markdown with DRAFT watermark | On demand or on material change | Mandate + Governance |
| Risk register | Markdown table | Updated with posture | Standing |
| Ethics certification | Inline stamp on each deliverable | Every output | Governance |

All outputs are **advisory-to-the-attorney**. None are self-acting, none are filed, none are
communicated externally without the attorney's review and execution.

## How the institutional weight works (the leverage math)

A top-tier firm's leverage comes from **ratio**: one partner with 3 associates, 2 paralegals, a
docketing clerk, and an evidence room. That's a 1:7 ratio. The partner's hour is worth 7x because
the bench finds, organizes, drafts, and tracks while the partner strategizes and advocates.

This organ delivers that bench as **continuous processing**. The key multipliers:

| Factor | Solo firm | This organ (steady state) | Source of leverage |
|---|---|---|---|
| Evidence indexing | On demand, attorney does it | Continuous, re-indexed on every document arrival | Idle fleet capacity does the scanning and cross-referencing |
| Deadline tracking | Manual calendar + human memory | Daily automated rebuild with proximity alerts | Runs every 24h regardless of attorney attention |
| Element mapping | Attorney builds and maintains | Rebuilt when facts or law change | Background processing beat |
| Drafting | From scratch each time | From current evidence index + element map | Structured data always ready |
| Ethics coverage | Attorney self-policing | Automated sentinel on every output | Cross-model verification run |
| Total effective bench | 1 person | 6 full-time-equivalent roles | Idle fleet capacity mapped to legal workflows |

The attorney still does what only the attorney can do: strategy, judgment, advocacy, filings,
client communication, and every outward-facing act. The organ does what headcount would do:
find, organize, track, draft, and verify.

## First proof: the micro instance

The micro instance — Anthony's ADA employment matter — is the first deployment, packaged as
[FRAMEWORK-FOR-COUNSEL.md](FRAMEWORK-FOR-COUNSEL.md): a deck attorney Counsel Longo can look at and
immediately see what an AI-augmented firm does for his client. Real case facts are placeholders
until the client/attorney supply them; the *structure* is the deliverable.

The SCRUM: run workflow 1 (intake → posture) and workflow 2 (evidence → index) against the real
matter facts once Counsel provides them. Workflow 4 (deadlines → calendar) runs as soon as dates
are known. Workflows 3 and 5 build on the index output.

## Future scaling (non-blocking, noted for later maturity bands)

When the organ reaches building stage (30%+):

- **Multi-matter support**: the same workflow stack runs against N matters simultaneously, each
  with its own evidence index, element map, deadline calendar, and sentinel scope.
- **Matter intake portal**: a structured intake form that non-attorney users can complete, producing
  a draft posture brief for attorney review.
- **Template library**: jurisdiction-specific skeleton libraries (demand letter, complaint, discovery
  requests, settlement agreement) that reduce drafting time further.
- **Authority database**: a curated, attorney-verified repository of controlling law by jurisdiction
  that accelerates the Law → elements map workflow.
- **PR / disclosure reviews**: the same indexing + sentinel workflow applied to public statements,
  press releases, or other communications that need legal review.

All future builds preserve the invariant: no legal advice, no practice of law, no self-acting
external communications, and the attorney of record owns every output.

## Constraint registry

| Constraint | Why | How it's enforced |
|---|---|---|
| No legal advice or UPL | Practicing law without a license is illegal and unethical | Ethics Sentinel blocks every output; KERNEL.md is prepended to every workflow prompt |
| No self-filing or self-sending | Only the attorney can file, serve, or communicate externally | No workflow output path leads to an external destination; all outputs stop at the attorney |
| No fabricated authority | Invented citations destroy credibility and violate ethics | Researcher workflow explicitly pulls real authority only; cross-verified before delivery |
| Privilege boundary | Attorney-client privilege must never be breached | Ethics Sentinel scans for privileged content crossing channels |
| Attorney owns every output | The attorney is responsible for everything bearing their name | Every deliverable is clearly marked as draft/skeleton/review-required |

All constraints are non-negotiable. They are the load-bearing walls of this organ.
