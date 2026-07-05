# HR Organism — CHARTER (the people office)

> **Boundary:** see `KERNEL.md`. Infrastructure augmenting human HR
> judgment; no employment decisions, no counsel on hiring/firing/discipline/
> leave/benefits, ever. Every act with legal effect on a person's livelihood
> stays in human hands, permanently.

## What it rivals

A Fortune-500 people office fused with a boutique HR consultancy. The large
employer wins the talent game not because its people are better but because a
standing apparatus — structured hiring loops, onboarding sequences, policy
handbooks, compliance calendars, performance frameworks, offboarding
checklists — stands behind every manager. A solo practitioner or small
business has the same judgment but reinvents every process per client, per
hire, per incident.

This organ supplies that apparatus as versioned, reusable artifacts. The
fractal: one practitioner (micro: Jessica) wields the institutional weight
of a 50-person people office for each client, without burning out
re-inventing the machinery.

## Institutional model — how idle fleet capacity becomes a people office

VLTIMA's fleet produces 14K-16K idle AI workunits per month. This organ
converts that spare capacity into ongoing HR operations:

| Fleet idle capacity | → | HR organ demand |
|---|---|---|
| Unlimited cheap reads + writes | → | Continuous intake processing, handbook iteration, compliance calendar maintenance |
| Background processing beats | → | Daily compliance deadline scan, offboarding checklist readiness, performance-cycle proximity alerts |
| Structured-data workflows | → | Posture records, comp-benchmark tables, policy-version diffs, engagement-state tracking |
| Cross-model verification | → | Ethics sentinel on every output — never oversteps the UPL/boundary |
| Document processing | → | Policy draft skeletons, handbook versions, offboarding transition docs |

The binding constraint is not capacity — it is **clients to serve**. One
active client engagement consumes approximately 20-40 workunits/month in
steady-state operations. The first instance (Jessica's HR practice, discovery
stage at `organs/consulting/engagements/jessica.yaml`) proves the pipeline;
scaling means enrolling clients, not adding capacity.

## The org-chart (AI roles, human-supervised)

| AI Role | Institution equivalent | Scope | Output | Human gate |
|---|---|---|---|---|
| **The Practitioner** *(the human)* | HR consultant / people-office head | client relationships, strategic judgment, all external communication, employment decisions | — (this is the human) | — |
| **Intake Clerk** | HR coordinator / practice manager | client intake into structured posture records: mandate, standing, standard, scope, jurisdiction, exclusions | `clients/<id>/posture.yaml` | practitioner reviews and confirms scope before any downstream workflow |
| **Policy Drafter** | HR policy analyst / handbook compiler | handbook skeleton + policy drafts from the template library, jurisdiction-tagged, with version diffs | `clients/<id>/handbook.md`, `clients/<id>/policies/*.md` | practitioner reviews and owns every word before delivery |
| **Compliance Calendarist** | Employment compliance coordinator | jurisdiction-aware compliance calendar: filing/renewal/review deadlines with lead-time alerts, jurisdiction rule annotations | `clients/<id>/compliance-calendar.md` | practitioner approves all deadline posture and executes filings |
| **Compensation Analyst** | Comp & benefits analyst | comp-benchmark table from public/survey data, role-mapped, with cost-of-living adjustments | `clients/<id>/comp-benchmark.md` | practitioner validates benchmarks before any offer or review |
| **Performance Framework Keeper** | Performance management lead | rubric + review-cycle scaffolds (Styx-compatible: peer-audited behavioral accountability), goal cascades, competencies | `clients/<id>/performance-framework.md` | practitioner designs the review process; framework keeper drafts and stages |
| **Onboarding Steward** | Onboarding specialist / HR generalist | onboarding sequence: day-0 prep → day-1 setup → week-1 checklist → 30-60-90 day plans, compliant with jurisdiction | `clients/<id>/onboarding-plan.md` | practitioner confirms before giving to the hiring manager |
| **Offboarding Steward** | Offboarding coordinator | checklist + transition-doc drafts: knowledge transfer, final pay, benefits transition, COBRA, return of property, exit interview | `clients/<id>/offboarding-plan.md` | practitioner executes the separation; steward drafts the plan |
| **Ethics & Boundary Sentinel** | HR ethics officer / compliance counsel | enforces the boundary: no employment decisions, no counsel, no UPL; flags any output that could be construed as legal advice or a personnel action | `clients/<id>/ethics-log.md` | practitioner is the final arbiter and responsible party |

No AI role has authority to communicate with employees, clients, candidates,
regulators, or outside parties. Every output is a draft staged for the
practitioner's review, correction, and delivery.

## The workflows it runs

Each workflow maps to the 5-primitive kernel (Member/Mandate/Standing/
Standard/Governance) and produces a specific artifact in `clients/<id>/`.

### W1) Practice intake → client posture

- **Trigger:** new client engagement opened, mandate changed, or scope
  materially shifted.
- **Input:** practitioner-approved intake packet: client entity, jurisdiction,
  employee headcount, current practices, known gaps, engagement exclusions,
  desired services.
- **Process:** create and maintain a client posture record: Member (the
  client entity + key contacts), Mandate (engagement scope and services),
  Standing (DISCOVERY → PROPOSAL → ACTIVE → TRANSITIONING → CLOSED),
  Standard (jurisdiction's labor-law floor + agreed quality bar), Governance
  (scope boundary, human gates, ethics rules).
- **Output:** `clients/<id>/posture.yaml`.
- **Cadence:** on engagement event + weekly standing review.
- **Gate:** practitioner correction before any downstream workflow consumes
  it.

### W2) Handbook → policy skeleton → tailored draft

- **Trigger:** new client intake approved; annual review cycle; jurisdiction
  change.
- **Input:** posture record, jurisdiction set, employee headcount, company
  policies list (from intake), template library in the macro platform.
- **Process:** load the jurisdiction-appropriate handbook skeleton, populate
  with policy drafts from the template library, tag each policy with
  its jurisdiction and mandatory/elective status, produce a complete
  handbook draft with version history.
- **Output:** `clients/<id>/handbook.md` + `clients/<id>/policies/*.md`.
- **Cadence:** on intake + annual + on material regulatory change.
- **Gate:** practitioner reviews each policy and edits before delivery to
  client. Nothing in the handbook is binding until the client signs off.

### W3) Compliance calendar → deadline surface

- **Trigger:** client jurisdiction(s) established; new regulatory obligation
  discovered; calendar review cadence.
- **Input:** jurisdiction set from posture, relevant labor/employment law
  obligations (federal, state, local), filing and renewal cycles, posting
  requirements, reporting deadlines.
- **Process:** map each jurisdiction's deadline set: what, when, by whom,
  format. Lead-time alerts at configurable thresholds (90/60/30/14/7 days).
  Flag conflicts and recurrences.
- **Output:** `clients/<id>/compliance-calendar.md` — a living deadline
  table with alert status and action owner.
- **Cadence:** rebuilt weekly; alert scan daily.
- **Gate:** practitioner confirms deadline posture and executes every
  filing. The calendarist never files anything.

### W4) Compensation → benchmark table

- **Trigger:** new role created, comp review cycle, client requests
  market data, jurisdiction-mandated pay transparency deadline.
- **Input:** role title, seniority level, industry, location (for cost-of-
  living), required skills, relevant public/survey data sources.
- **Process:** produce a comp-benchmark table: market p10/p25/p50/p75/p90
  for the role, adjusted for location and industry. Annotate sources and
  confidence levels.
- **Output:** `clients/<id>/comp-benchmark.md` with range table, source
  annotations, and year-over-year trend where available.
- **Cadence:** on demand + annual review cycle.
- **Gate:** practitioner validates the benchmark against practitioner
  experience before any offer or review discussion. The comp analyst never
  makes a compensation recommendation — it provides data for human judgment.

### W5) Performance framework → review-cycle scaffold

- **Trigger:** performance review cycle approaching, new role created with
  performance expectations, client requests performance process design.
- **Input:** posture record, org structure, role descriptions, client's
  stated values and competencies, preferred review cadence.
- **Process:** produce a performance framework: competency rubrics, goal-
  cascade templates (company → team → individual), self-review prompt
  structures, manager-review guide, and the calibration-process design.
  Styx-compatible: the framework integrates the peer-audited behavioral-
  accountability product for habit-based goals and loss-aversion staking
  when teams opt in.
- **Output:** `clients/<id>/performance-framework.md`.
- **Cadence:** on setup + annual refresh + mid-cycle calibration.
- **Gate:** practitioner designs the review philosophy; the framework keeper
  translates it into scaffold. Practitioner approves every rubric and cycle
  before deployment. No employee is evaluated by the organ.

### W6) Onboarding → sequence plan

- **Trigger:** new hire committed; new role type created.
- **Input:** role description, start date, department, manager, required
  access/system provisioning list, jurisdiction-specific onboarding
  requirements (I-9, tax forms, right-to-work verification).
- **Process:** produce a day-0/day-1/week-1/30-60-90 day plan with
  compliance tasks, IT/access provisioning checklist, benefits enrollment
  windows, policy acknowledgment queue, and role-specific training plan.
- **Output:** `clients/<id>/onboarding-plan.md`.
- **Cadence:** per new hire.
- **Gate:** practitioner reviews and sends to the hiring manager. The
  steward never communicates with the new hire directly.

### W7) Offboarding → transition checklist

- **Trigger:** resignation, termination, end of contract, role elimination.
- **Input:** employee name, role, last working date, applicable notice
  period, jurisdiction termination requirements, COBRA/final-pay rules,
  return-of-property inventory, knowledge-transfer scope.
- **Process:** produce a checklist: final pay and benefits transition
  (COBRA/continuation), accrued PTO payout, final expense report, IT
  deprovisioning, account lockout schedule, equipment return, knowledge-
  transfer plan, exit interview questions.
- **Output:** `clients/<id>/offboarding-plan.md`.
- **Cadence:** per offboarding event.
- **Gate:** practitioner reviews and owns the execution. The steward never
  communicates with the departing employee. The offboarding plan is a draft;
  the practitioner executes every step with legal/care.

### W8) Ethics & boundary sentinel (cross-cuts all workflows)

- **Trigger:** every draft or output before delivery to the practitioner.
- **Input:** artifact content + source lineage + originating workflow.
- **Process:** check against: UPL boundary (no employment counsel, no
  benefits advice, no personnel-action recommendation), scope boundary
  (no intake scope creep without practitioner approval), privacy boundary
  (no PII in artifacts without explicit consent), Styx-consent boundary
  (behavioral tooling is opt-in only, never used for covert monitoring).
- **Output:** ethics pass entry in `clients/<id>/ethics-log.md`; blocking
  reason with the specific boundary violated when gate fails.
- **Cadence:** continuous, as a gate on every output workflow.
- **Gate:** no artifact leaves the HR organ without a pass record and
  practitioner direction. The sentinel flags but never overrides.

### Workflow orchestration diagram

```
                     ┌──────────────┐
                     │   W1: Intake │
                     │   → Posture  │
                     │  (all 5 prim)│
                     └──────┬───────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                  │
          ▼                 ▼                  ▼
   ┌──────────────┐ ┌──────────────┐ ┌────────────────┐
   │ W3: Compliance│ │ W2: Handbook │ │ W4: Compensation│
   │   Calendar    │ │   + Policies │ │   Benchmark     │
   │  (Standard)   │ │   (Mandate)  │ │   (Standard)    │
   └──────┬───────┘ └──────┬───────┘ └───────┬────────┘
          │                │                  │
          └────────────────┼──────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ W5: Perf.   │
                    │  Framework  │
                    │  (Standard) │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ W6: Onbrd│ │ W7: Offbr│ │(recurring│
       │  Plan    │ │  Plan    │ │  cycles) │
       │(Govern)  │ │(Govern)  │ │          │
       └────┬─────┘ └────┬─────┘ └──────────┘
            │            │
            └──────┬─────┘
                   │
                   ▼
            ┌──────────────┐
            │   W8: Ethics │
            │   Sentinel   │
            │ (Governance) │
            └──────┬───────┘
                   │
          ┌────────┴────────┐
          │                 │
          ▼                 ▼
   ┌──────────────┐ ┌──────────────┐
   │ Practitioner │ │   Client     │
   │ (reviews &   │ │ (receives &  │
   │  delivers)   │ │  acts on)    │
   └──────────────┘ └──────────────┘
```

Every workflow feeds into the sentinel before reaching the practitioner.
W2-W7 may run in parallel per client posture. W1 establishes the posture
that constrains all downstream workflows. The practitioner stands at the
end of every path — nothing reaches a client without a human hand.

## Inputs / outputs

### Inputs (what the practitioner or client supplies)

| Input | Format | Source | Maps to kernel |
|---|---|---|---|
| Client intake packet | Structured facts: entity, jurisdiction, headcount, scope | Practitioner | Member + Mandate |
| Current policies (if any) | Existing documents or notes | Client intake | Mandate |
| Job descriptions / role specs | Structured role data | Client | Mandate + Standard |
| Org structure | Org chart or notes | Client | Member + Governance |
| Compensation data | Current comp ranges, if sharing | Client | Standard |
| Performance review philosophy | Practitioner's design intent | Practitioner | Governance |
| Offboarding notice | Separation details, date, rules | Client or practitioner | Governance + Standing |
| Regulatory updates | New laws or deadlines in jurisdiction | Practitioner (via external research) | Standard |

### Outputs (what the organ delivers)

| Output | Format | Cadence | Maps to kernel |
|---|---|---|---|
| Client posture record | YAML/Markdown — living state | Updated on event + weekly | Member + Mandate + Standing |
| Handbook draft | Markdown — skeleton + tailored policies | On intake + annual + material change | Mandate + Standard |
| Policy drafts | Markdown — individual policy documents | On intake + per policy need | Mandate |
| Compliance calendar | Markdown — deadline table with alerts | Rebuilt weekly; alert scan daily | Standard + Governance |
| Comp-benchmark table | Markdown — range table with sources | On demand + annual | Standard |
| Performance framework | Markdown — rubrics, cycle scaffolds, Styx tie | On setup + annual refresh | Standard + Governance |
| Onboarding plan | Markdown — day-0→90 day sequence | Per new hire | Governance + Member |
| Offboarding plan | Markdown — checklist + transition docs | Per offboarding event | Governance + Member |
| Ethics log | Markdown — append-only boundary-pass/fail record | Continuous per- output | Governance |
| Job description draft | Markdown — role skeleton with comp note | On demand | Mandate + Standard |

All outputs are **drafts staged for practitioner review**. None are
self-acting, none replace practitioner judgment, and none are communicated
externally without the practitioner's direction.

## How one-person institutional weight works (the leverage math)

A Fortune-500 people office's leverage comes from **scope**: specialists
owning each domain — recruiting, compensation, compliance, performance,
employee relations, offboarding — so no single person carries the full
load. A boutique consultancy substitutes **process density**: the same
practitioner does every domain, but against structured playbooks and
templates that eliminate re-invention.

This organ delivers both at once:

| Factor | Solo practitioner | This organ (steady state) | Source of leverage |
|---|---|---|---|
| Intake discipline | Reinvented per client | Structured posture record with versioned templates on first contact | Template library + automated record creation |
| Policy drafting | Every handbook from scratch | Jurisdiction-tagged skeleton → tailored draft → version diff in one workflow | Template library + W2 automation |
| Compliance tracking | Spreadsheet or memory | Living calendar with automated alerts at configurable lead times | W3 daily scan + jurisdiction rule annotations |
| Compensation benchmarking | Manual research each time | On-demand benchmark from structured data with source annotations | W4 research pipeline |
| Performance framework design | Designed from scratch per client | Rubric library + Styx integration for habit/accountability limb | W5 scaffold generator + Styx product tie |
| Onboarding/offboarding | Checklist rediscovered per event | Structured sequence plan per hire/separator with compliance tasks built in | W6/W7 sequence generators |
| Ethics boundary | Self-policed under pressure | Automated sentinel on every output — catches scope creep, UPL drift, privacy leaks | W8 cross-workflow gate |
| **Effective bench** | **1 person (the practitioner)** | **8 role-equivalents running continuously** | **Idle fleet capacity mapped to HR operations** |

The practitioner still does what only a human can do: build client
relationships, exercise strategic judgment, make scope decisions, review
and own every deliverable, and execute all external communication. The
organ does what coordination headcount would do: intake, draft, track,
benchmark, calendar, scaffold, sequence, and verify.

## The Styx product tie — performance/habits limb

The performance framework (W5) has a native integration with Styx
(`organvm/peer-audited--behavioral-blockchain`), the peer-audited
behavioral accountability product. The integration is **consent-first**:

- Teams that opt in receive Styx-backed habit competitions, loss-aversion
  staking, and peer-audited accountability as a performance/habits limb
  within the broader performance framework.
- The Styx product constellation includes the main blockchain repo, the
  behavioral-economics theory repo (`organvm/styx-behavioral-economics-theory`),
  and the art/communication repo (`organvm/styx-behavioral-art`).
- **Naming note (reconciliation):** the limen tasks.yaml and organ-ladder.json
  reference `organvm/styx`, but the canonical public GitHub org key is
  `organvm/peer-audited--behavioral-blockchain`. The shorter name "Styx" is
  the project name; the canonical repo key is the load-bearing identifier.
  This CHARTER uses the canonical key; the shorter alias is used for
  readability in product descriptions. A future INDEX-NOMINVM pass should
  reconcile all references across the estate to a single canonical form.

## Target build surface (scaffold-complete set)

```
organs/hr/
  KERNEL.md              -- 5-primitive kernel, boundary, architecture
  CHARTER.md             -- this file: org-chart, workflows, I/O, leverage
  clients/               -- per-client engagement artifacts
    <client-id>/
      posture.yaml       -- W1: living client posture record
      handbook.md        -- W2: tailored handbook
      policies/          -- W2: individual policy drafts
      compliance-calendar.md  -- W3: deadline surface
      comp-benchmark.md       -- W4: compensation benchmarks
      performance-framework.md -- W5: rubric + review-cycle scaffold
      onboarding-plan.md      -- W6: per-hire sequence
      offboarding-plan.md     -- W7: per-separator checklist
      ethics-log.md           -- W8: boundary pass/fail record
      drafts/                 -- staging area for review
```

The macro platform (the template library, jurisdiction rules, rubric
library, comp data) lives at the organ root alongside these two documents.
Client-specific artifacts live under `clients/`.

## First proof

1. The Jessica engagement record (`organs/consulting/engagements/jessica.yaml`)
   passes the consulting fleet validator, proving the micro instance is on
   record at DISCOVERY.
2. This kernel/charter pair is registered in `organ-ladder.json` — the organ
   exists in the census (rank 11, maturity 10%).
3. Next: the first client posture record (W1) for Jessica's first client,
   produced as a runnable template that proves the intake→posture workflow.

```bash
python organs/consulting/validate-consulting.py --fleet --quiet
```

Exit 0 ⟺ the Jessica engagement record is valid and the consulting organ
recognizes the HR micro instance.

## Constraint registry

| Constraint | Why | How it's enforced |
|---|---|---|
| No employment decisions | Practicing HR without authority is unethical and exposes the client to liability | Ethics sentinel blocks every output; no workflow produces a binding decision |
| No counsel on hiring/firing/discipline/leave/benefits | Only licensed practitioners and attorneys give employment counsel | All outputs are drafts marked for review; KERNEL.md boundary prepended to every prompt |
| No outbound communication by the organ | Communication with employees, regulators, and third parties is a human act | No output path leaves the `clients/<id>/` artifact tree |
| No UPL (unauthorized practice of law) | Handbook/policy drafts are templates, not legal advice; compliance calendar tracks known deadlines, not legal interpretations | Every handbook and policy draft carries a disclaimer; ethics sentinel flags legal-adjacent language |
| Styx behavioral tooling is consent-first | Covert monitoring or mandatory accountability damages trust and may violate privacy law | Ethics sentinel checks Styx integration for opt-in consent records |
| Practitioner owns every deliverable | Only the human practitioner has the client relationship and liability | Every output is a draft; the practitioner reviews, corrects, signs off, and delivers |
| No scope creep without practitioner approval | Intake scope is the engagement contract | W8 checks every downstream workflow against the posture record's scope block |
| Privacy of person data | Employee/candidate/client PII must never leak | All artifacts scoped to `clients/<id>/` with role-based access; no output path exposes PII externally |

All constraints are non-negotiable. They are the load-bearing walls of this
organ.

## Naming

Working name: **HR / People Office**. A proper name — consistent with the
flagship convention used by the legal organ (Cochran), the artist organ
(A-MAVS-OLEVM), and the governance organ (Aerarium / Cvrsvs Honorvm) — is
pending an INDEX-NOMINVM pass. See `organ-ladder.json` rank 11 note.
