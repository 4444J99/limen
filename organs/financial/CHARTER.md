# Financial Office — CHARTER (the virtual family office)

> **Boundary:** an AI-run financial *operations* office that works under and for the human
> principal. It does not execute trades, move money, file taxes, or give fiduciary advice.
> The principal directs it and owns every output. See [KERNEL.md](KERNEL.md) for the full
> guardrails and the 5-primitive kernel map.

## What it rivals — the billionaire's family office

A billionaire's family office doesn't have a smarter principal; it has **more bench**. For
every strategic financial decision the principal makes, a coordinated team spends dozens of
hours on the work that makes that decision possible: reconciliation, projection, tax
modeling, compliance monitoring, disbursement scheduling, insurance review, and estate
planning maintenance. The solo high-net-worth individual or lean entrepreneur has the same
financial acumen but **none of the bench**.

This organ supplies that bench as persistent AI roles that run continuously across the
financial domain. It does not replace the principal — it replaces the headcount that
multiplies the principal's financial effectiveness.

The family-office standard, distilled: **every position is known before a decision is needed,
every obligation is owned before it comes due, every tax position is modeled before the
filing window, and every disbursement is planned before the money is spent.** This organ
makes that the default operating state for one principal managing any financial complexity.

## Institutional weight — how idle fleet capacity becomes a family office

VLTIMA's fleet produces 14K-16K idle AI workunits per month. This organ converts that spare
capacity into ongoing financial operations. The mapping:

| Fleet idle capacity (supply) | → | Financial office demand |
|---|---|---|
| Unlimited cheap reads + writes | → | Continuous reconciliation of statements, accounts, and obligations |
| Background processing beats | → | Daily position updates, cash-flow projections, alert generation |
| Projection-oriented models | → | Rolling 12-week cash-flow forecasts, tax-position estimation, runway analysis |
| Drafting runs | → | Disbursement schedules, wire instructions (drafts only), tax-prep workpapers |
| Cross-model verification | → | Compliance/audit sentinel on every output — separation-of-duties for a one-person office |

The binding constraint is not capacity — it is **data feeds**. One financial instance with
full entity coverage consumes approximately 10-20 workunits/month in steady-state operations.
A fleet of 14K+ idle workunits can sustain hundreds of financial-office instances
simultaneously. Anthony's own instance (the micro deployment) proves the pipeline; scaling
means adding entity/account registrations, not capacity.

## The org-chart (AI roles, human-supervised)

| Role | Institution equivalent | Does | Human check |
|---|---|---|---|
| **Principal (the human)** | The wealth owner / CPO | all strategic decisions: what to spend, invest, donate, file, insure, and how | — (this is the human) |
| **Chief Financial Officer** | CPO / Family Office COO | maintains the single source of truth: net position, cash-flow projection, runway, open decisions, and the consolidated dashboard | principal approves position assessment and major decisions |
| **Reconciliation Clerk** | Staff accountant | reconciles accounts: imports statements, matches transactions, flags discrepancies, maintains the obligation ledger | principal reviews exceptions monthly |
| **Tax Strategist** | Tax partner / CPA | estimates current and projected tax position across entities, identifies optimization windows, tracks filing deadlines, drafts tax-prep workpapers | CPA or principal validates every filing position |
| **Treasury Analyst** | Treasury / FP&A analyst | builds and maintains cash-flow models, disbursement schedules, runway projections, and liquidity alerts | principal reviews projections and approves disbursement schedule |
| **Compliance Sentinel** | Compliance officer / auditor | enforces the governance rules: disbursement thresholds, segregation-of-duties, audit trail, policy adherence; certifies each output | principal is final arbiter of policy exceptions |

The point of the chart: each role is a **workflow the conductor can run continuously**, so
the financial position is always current, always modeled, always governed — the leverage a
family office buys with headcount.

The principal remains the center of gravity. These roles do not make decisions; they prepare
the ground so the principal's decisions are better informed, faster, and never miss a
deadline or obligation.

## The office-wide workflows it runs

Each workflow maps to the 5-primitive kernel (Member/Mandate/Standing/Standard/Governance)
and produces a specific artifact. Workflows run on a **cadence** — continuous for
reconciliation, daily for position, weekly for projection, on-event for major decisions.

The polished faces are now first-class artifacts:

- [MACRO.md](MACRO.md) — the deployable family-office-in-a-box face for anyone.
- [MICRO.md](MICRO.md) — Anthony's own MONETA/payrail/wealth/tax office instance.

### 1. Entity registry → position (Member + Standing)

- **Trigger:** entity added, account opened, or position change detected.
- **Process:** capture entity identity (Member), its accounts and instruments, current
  balances, access boundaries, and the allocation mandate (Mandate). Aggregate into net
  position (Standing) across all entities.
- **Runs:** on entity change + daily reconciliation sweep.
- **Output:** consolidated balance sheet — net worth across all entities, always current.
  Sections: entity summary, account detail, net position by entity, consolidated total.
- **Human gate:** principal reviews position monthly and approves material changes.

### 2. Cash-flow projection (Standing + Mandate)

- **Trigger:** any known inbound or outbound event — invoice, subscription, payroll,
  tax payment, disbursement, investment.
- **Process:** build a rolling 12-week cash-flow model: known inflows (revenue, grants,
  transfers) and outflows (bills, disbursements, payroll, taxes). Flag gaps, surpluses,
  and runway limits.
- **Runs:** daily — projection rebuilt every 24h with new data and time roll-forward.
- **Output:** cash-flow projection — rolling 12-week table with weekly balances,
  surplus/deficit flags, and minimum runway alert threshold.
- **Human gate:** principal reviews weekly; the organ alerts automatically if runway
  drops below configured threshold.

### 3. Tax-position estimation (Standard + Member)

- **Trigger:** new entity, new revenue stream, tax law change, or approaching filing
  deadline.
- **Process:** estimate current-year tax position across all entities: estimated tax
  due, installment schedule, available credits/deductions, and optimization windows.
  Flag estimated-vs-prepaid gaps.
- **Runs:** monthly full estimate + weekly delta scan.
- **Output:** tax-position dashboard — estimated liability by entity, paid-to-date,
  remaining installments, filing deadline calendar, optimization opportunities.
- **Human gate:** CPA or principal validates every filing position. No position is
  filed by the organ.

### 4. Disbursement scheduling (Governance + Mandate)

- **Trigger:** recurring obligation, one-time bill, investment commitment, or
  principal instruction.
- **Process:** maintain the disbursement calendar: what, to whom, from which account,
  by when. Draft wire/ACH instructions (readable, not executable). Flag funding gaps
  or policy violations.
- **Runs:** daily — calendar rebuilt every 24h with proximity alerts at configurable
  thresholds.
- **Output:** disbursement calendar — all scheduled payments sorted by due date, with
  funding source, policy compliance, and alert status. Draft instructions attached.
- **Human gate:** principal reviews and executes each disbursement in their banking
  portal. The organ never sends money.

### 5. Obligations ledger (Standing + Governance)

- **Trigger:** new obligation identified (subscription, insurance premium, tax
  installment, loan payment, grant commitment).
- **Process:** each recurring or future obligation is recorded with: amount, frequency,
  next due date, funding source, legal basis, and cancellation policy. The ledger is
  the source of truth for the cash-flow projection and disbursement calendar.
- **Runs:** continuous — obligation added when discovered; full audit weekly.
- **Output:** obligations ledger — sorted by urgency, with auto-renew flag,
  cancellation window, and total committed vs. available.
- **Human gate:** principal reviews monthly and confirms/renews/cancels obligations.

### 6. Compliance / audit sentinel (Governance — cross-cuts all)

- **Trigger:** every output before delivery to the principal.
- **Process:** each deliverable is checked against governance rules: disbursement
  thresholds (no single disbursement > policy limit without approval), segregation of
  duties (org-prep vs. human-execute), audit trail (every position has a timestamped
  source), and policy adherence (no spending outside mandate). The sentinel is the
  last automated step before any artifact reaches the principal.
- **Runs:** continuously, as a gate on every output workflow.
- **Output:** compliance certification — a stamp on every deliverable: "Compliance check
  passed: policy limits held, segregation maintained, audit trail current."
- **Human gate:** principal is the final arbiter of all policy exceptions.

### Workflow orchestration diagram

```
                   ┌──────────────────┐
                   │  Entity Registry │
                   │  → Position     │
                   │  (Member +       │
                   │   Standing)      │
                   └──────┬───────────┘
                          │
           ┌──────────────┼──────────────────┐
           │              │                  │
           ▼              ▼                  ▼
    ┌────────────┐ ┌──────────────┐ ┌──────────────┐
    │ Cash-Flow  │ │ Tax-Position │ │ Disbursement │
    │ Projection │ │ Estimation   │ │ Scheduling   │
    │ (Standing) │ │ (Standard)   │ │ (Governance) │
    └─────┬──────┘ └──────┬───────┘ └──────┬───────┘
           │              │                │
           └──────────────┼────────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │ Obligations  │
                   │ Ledger       │
                   │ (Standing)   │
                   └──────┬───────┘
                          │
                          ▼
                   ┌──────────────┐
                   │ Compliance / │
                   │ Audit        │
                   │ Sentinel     │
                   └──────┬───────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  Principal   │
                   │  (CPO)       │
                   └──────────────┘
```

Every workflow feeds the next. Entity registry feeds cash-flow, tax, and disbursement.
All three feed the obligations ledger. Compliance sentinel gates everything. The principal
stands at the end of every path — no money moves, no filing is submitted, no commitment
is made without human judgment.

## Inputs / outputs

### Inputs (what the principal or connected sources supply)

| Input | Format | Source | Maps to kernel |
|---|---|---|---|
| Entity/account info | Structured form or narrative | Principal | Member |
| Bank/broker/CC statements | CSV, PDF, or manual summary | Principal uploads or OCR | Member + Standing |
| Revenue records | Platform reports, invoices | Product platforms, principal | Standing |
| Obligations and bills | Recurring commitment detail | Principal, bills | Standing |
| Tax documents | Tax forms, prior returns | Principal, CPA | Standard |
| Principal instructions | Goals, policies, decisions | Principal | Mandate + Governance |

### Outputs (what the organ delivers to the principal)

| Output | Format | Cadence | Maps to kernel |
|---|---|---|---|
| Consolidated balance sheet | Markdown (one page) | Updated daily + on entity change | Standing |
| Cash-flow projection | Markdown table (12-week rolling) | Updated daily | Standing + Mandate |
| Tax-position dashboard | Markdown summary + deadline calendar | Updated monthly + delta weekly | Standard |
| Disbursement calendar | Markdown list sorted by proximity | Updated daily | Mandate + Governance |
| Obligations ledger | Markdown list sorted by urgency | Updated continuously + weekly audit | Standing + Governance |
| Compliance certification | Inline stamp on each deliverable | Every output | Governance |

All outputs are **advisory to the principal**. None are self-acting, none move money,
none file taxes, and none are communicated to third parties without the principal's
review and execution.

## Scaling the-invisible-ledger: from B2B CPA tool to personal family office

The task constraint names the migration path. The-invisible-ledger starts as a working
accounting tool (the B2B CPA product it already is) and must scale into a personal family
office that an individual can operate with institutional weight. The phases:

### Phase 1 — Foundation (current: this KERNEL + CHARTER) [maturity 30-50%]

- Seed `organs/financial/` with the kernel map, charter, and workflow designs (done here).
- Map the-invisible-ledger's existing product schema to the financial organ's primitive
  model: identify gaps in entity/account representation, multi-entity aggregation,
  cash-flow projection, and governance rules.
- Author the first personal balance-sheet and obligation ledger (micro instance) running
  on Anthony's real entity data — even if manually populated at first.
- Organ-ladder maturity moves from 30% → 40%.

### Phase 2 — Self-feeding loop [building 50-70%]

- Wire the financial organ into the C_FEED generator beat alongside revenue and organs.
  The existing `organ-selffeed` lever in generate-organ-backlog.py already emits self-feed
  tasks for building-stage organs. When the first balance-sheet lands, maturity bumps and
  the generator emits the next deepen/selffeed task automatically — the lockless,
  idempotent, floor-gated pattern proven by revenue/studium.
- Add a dedicated beat or generator hook for financial-data ingestion if the generic
  organ generator's cadence (every 3 beats, building levers) is insufficient. Otherwise
  the existing organ generator IS the self-feeding hook — it runs every feed beat, reads
  organ-ladder.json, and emits building-stage tasks (including `organ-selffeed`) when the
  floor drops.

### Phase 3 — Dashboard + integration [maturing 70-90%]

- Wire the-invisible-ledger's live accounting UI as the financial organ's macro face.
- Add real data feeds (where available, respecting the no-credential boundary) for
  reconciliation automation.
- Surface the family office dashboard in the fleet's visible surfaces (money-view.py,
  the conducting report, the phone page).
- Tax-position estimation graduates from manual workpapers to model-driven projections.

### Phase 4 — Mature [>=90%]

- Self-running: the organ reconciles, projects, alerts, and drafts without principal
  attention. The principal reviews and decides. The-invisible-ledger serves both as the
  B2B CPA tool AND the personal family office — one instance, two faces.

## First proof: the micro instance

The micro instance — Anthony's own financial position — is the first deployment. The steps:

1. Create the entity registry: personal accounts, the LLC, the non-profit, and any
   other financial entities.
2. Populate the balance sheet with known positions (bank balances, investments, debts,
   assets) — even as approximate starting values.
3. Build the obligations ledger: recurring bills, subscriptions, insurance, tax
   installments, and other commitments.
4. Run the cash-flow projection: known revenue (product income, consulting, grants)
   against known obligations on a 12-week rolling horizon.
5. Produce the payrail disbursement map: how product revenue flows from the earning
   entity through institutional accounts to personal accounts and obligations — the
   legal/tax scaffolding for each hop.

The SCRUM: workflow 1 (entity → position) first, then workflow 4 (obligations ledger),
then workflow 2 (cash-flow projection), then workflow 5 (disbursement scheduling).
Workflow 3 (tax-position estimation) runs on the results of 1+2+4.

## Constraint registry

| Constraint | Why | How it's enforced |
|---|---|---|
| No money movement | Only the principal can authorize disbursements | No workflow output path leads to an external financial system; all outputs stop at the principal |
| No stored credentials | Banking/broker credentials create unacceptable risk | The organ reads from manual reports, statements, and principal-provided summaries |
| No tax or legal advice | Unlicensed tax/legal advice creates liability | Compliance Sentinel blocks every output that could be construed as advice; KERNEL.md is prepended to every workflow prompt |
| Privacy by structure | Financial data is the most sensitive personal data | Access scoped by entity governance rules; no cross-entity data sharing without explicit policy |
| All projections have caveats | Stale or overconfident numbers cause bad decisions | Every projection output includes confidence level, as-of date, and assumption list |
| Principal owns every decision | The principal is responsible for every financial outcome | Every deliverable is clearly marked as advisory/review-required; no self-acting financial acts |

All constraints are non-negotiable. They are the load-bearing walls of this organ.
