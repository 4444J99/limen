# Aerarium MACRO Face — Family Office in a Box

> **Promise:** deploy the operating system a billionaire's family office runs on —
> every entity known, every account classified, every obligation visible, every cash
> path modeled, every tax exposure staged for review, and every disbursement governed
> before anyone touches a bank portal. One person, institutional weight, zero staff.
>
> **Boundary:** Aerarium does not move money, execute trades, open accounts, file taxes,
> or sign anything. MONETA owns sovereign intake at `moneta/`. Aerarium owns the census,
> ledger, forecast, payrail map, tax workpapers, and review gates around that intake.

## What It Is

Aerarium is a **deployable family office** — the institutional prosthesis a billionaire
buys with a $500K+/year staff, delivered as a directory of structured files and a
generator that keeps them current. It is built from the-invisible-ledger's accounting
core, scaled from B2B CPA tool into a personal financial operating system.

The old shape was organizing books for a business and its accountant. The scaled shape:
one deployable financial office for a person, family, or small institution that needs
institutional weight without hiring a staff.

The platform turns scattered financial facts into one operating surface:

- **Entity registry:** people, LLCs, nonprofits, trusts, products, wallets, accounts,
  and obligations registered as first-class financial members.
- **Consolidated balance sheet:** assets and liabilities roll up across every entity,
  with unknown balances explicitly marked instead of hidden (no fake zeros).
- **Rolling cash-flow projection:** known inflows, obligations, runway, and reserve
  needs rebuilt on every beat.
- **Payrail disbursement map:** money paths modeled from revenue source to collection
  account to entity account to obligation, with the gate and tax treatment for each hop.
- **Tax-position desk:** estimated liabilities, installments, filing windows, deductions,
  and CPA handoff packets staged from the same ledger.
- **Compliance sentinel:** every output checked for source timestamp, approval gate,
  segregation of duties, assumption labels, and policy limits.

This is not another budgeting app. A budgeting app asks you to remember. Aerarium makes
the institution remember — continuously, across every entity, every account, every
obligation, every tax implication, without you hiring a CFO.

## What You Get When You Deploy

Aerarium is a directory of files you own, edit in any text editor, and commit to your
own repo or keep on your own drive. No login, no subscription, no vendor lock-in.

```
organs/financial/
├── CHARTER.md            # The institutional charter — what this organ is, who it rivals
├── KERNEL.md             # The 5-primitive kernel mapped to the financial domain
├── MACRO.md              # This face — the deployable family office
├── MICRO.md              # The reference instance (how it's used in production)
├── seed.yaml             # The organ's own assertion — what it produces and consumes
├── entities.yaml         # YOUR entity registry — edit this to add accounts
├── balance-sheet.md      # GENERATED — consolidated net position
├── cashflow.md           # GENERATED — 12-week rolling projection
├── payrail.md            # Authored — your disbursement map
├── STATUS.md             # GENERATED — one-page dashboard
├── balances-history.json # GENERATED — time-series of snapshots
└── consolidate.py        # The generator that produces all artifacts
```

Three file types:
- **YOU EDIT:** `entities.yaml` (your entities, accounts, balances), `payrail.md` (your
  money paths), and any of the `*.md` faces if you want a customized pitch.
- **GENERATED:** `balance-sheet.md`, `cashflow.md`, `STATUS.md`, `balances-history.json`,
  and the web JSON face — produced by `consolidate.py`.
- **YOUR WEB FACE:** `web/app/public/financial-standing.json` — the machine-readable
  dashboard for your web surface.

There is no database. No cloud. No API key. Your financial office is a directory you
control.

## Deploy in 5 Minutes

```bash
# 1. Copy the template into your project
cp -r organs/financial your-project/organs/

# 2. Register yourself and your entities
# Edit entities.yaml: replace the MICRO entities with yours.
# Follow the entity_template — name, type, jurisdiction, accounts.
vim your-project/organs/financial/entities.yaml

# 3. Enter known balances
# For each account you know, set balance_known: true, balance, and as_of.
# Unknown is honest — the dashboard will show "(needs entry)" instead of $0.

# 4. Map your payrails
# Edit payrail.md to reflect your actual money paths — from revenue source
# to collection account to entity account to obligations.

# 5. Generate your office
python3 your-project/organs/financial/consolidate.py
# Produces: balance-sheet.md, cashflow.md, STATUS.md, balances-history.json,
#           financial-standing.json

# 6. Review
open your-project/organs/financial/balance-sheet.md
open your-project/organs/financial/cashflow.md
open your-project/organs/financial/STATUS.md
```

That is enough to turn a scattered financial life into a governed office. The generator
handles the math, classification, projection, and presentation. You handle truth.

### What You Get On Day One

Even with zero known balances, the artifacts are structurally complete:

- **balance-sheet.md** — shows every registered account, classified as asset or liability,
  with a `-` where balance is unknown. No fake zeros. Every cell honest.
- **cashflow.md** — 12-week rolling projection with revenue pipeline table, known
  obligations, and runway analysis. Pre-revenue? It says so. Post-deploy? It models
  the expected state.
- **STATUS.md** — one-page at-a-glance: entities tracked, revenue products, obligations,
  net worth (or "unknown" if no balances entered), and next deepen steps.
- **financial-standing.json** — machine-readable dashboard for your web UI.

### What It Takes To Go Live

1. Enter real balances (asset and liability accounts).
2. Receive your first dollar through any collection rail.
3. Enter recurring obligation amounts.
4. Add investment accounts for portfolio tracking.

Each of these is a single edit in `entities.yaml`. The generator does the rest.

## Why This Is Different From Every Other Financial Tool

| What you already use | What it gives you | What it doesn't give you |
|---|---|---|
| Mint / Personal Capital | Aggregated view of your accounts | Multi-entity, tax, obligations, disbursement governance, no fake zeros |
| YNAB / EveryDollar | Budget envelope tracking | Net worth, cash-flow projection, entity separation, institutional weight |
| QuickBooks | Business accounting | Personal + business + mission + trust in one governed registry |
| A spreadsheet | Full control | Projection engine, compliance checks, auto-generated dashboards, always-current |
| A family office (hired) | Institutional weight | $500K+/year, staff management, vendor lock-in, you delegate everything |

Aerarium is the **only option that gives you institutional weight without staff** — the
continuous, always-current, projection-capable view of your full financial position, with
AI roles doing what a CPO, tax strategist, analyst, and bill-pay clerk would do, without
the machine ever touching the money itself. And you own the files.

## The 5-Primitive Kernel, Financial Domain

Aerarium is one organ in VLTIMA's institutional body. Every organ — legal, education,
health, governance, social, artist — runs the same 5-primitive kernel with a domain
skin. Here is the financial skin:

| Primitive | Financial meaning | File artifact |
|---|---|---|
| **Member** | **account / entity** | `entities.yaml` — identity, jurisdiction, ownership, accounts, instruments |
| **Mandate** | **goal / allocation** | Staged in `payrail.md` — what money is for: savings target, tax reserve, investment thesis, disbursement rule |
| **Standing** | **net position** | `balance-sheet.md` + `cashflow.md` — what you own, owe, and project |
| **Standard** | **tax / compliance rule** | Staged in tax workpapers — tax code, disbursement policies, risk limits |
| **Governance** | **the office's controls** | `STATUS.md` compliance stamp — approval gates, audit trail, segregation of duties |

The kernel means every organ in the body interoperates through the same primitives.
Your legal organ registers entities as Members. Your financial organ classifies their
accounts. Your obligations come from the mail organ. The governing entity decisions
come from the governance organ.

## How Institutional Weight Happens (The Fleet Capacity Angle)

Aerarium runs on VLTIMA's idle fleet capacity — 14K-16K AI workunits per month that
would otherwise do nothing. The mapping from spare compute to family office:

| Fleet idle capacity | → | Financial office operation |
|---|---|---|
| Unlimited cheap reads + writes | → | Continuous reconciliation of every entity and account |
| Background processing beats (every 2 hours) | → | Daily position updates, cash-flow projection rebuilds, compliance checks |
| Projection-oriented models | → | Rolling 12-week cash-flow forecasts, tax-position estimation, runway alerts |
| Drafting runs (any model, any tier) | → | Disbursement schedules, wire-instruction drafts, tax-prep workpapers |
| Cross-model verification | → | Compliance/audit sentinel on every output — separation of duties for a one-person office |

One financial instance with full entity coverage consumes ~10-20 workunits/month in
steady state. A fleet producing 14K+ idle units monthly can sustain hundreds of family
offices simultaneously. The binding constraint is not capacity — it is getting your
first entity registry populated.

The fleet capacity angle means your financial office gets **more institutional weight
over time, not less**. Every new entity, every new obligation, every new product
revenue stream just adds another row in the registry. The processing cost is unchanged.

## What The Principal Sees

The face answers five questions without a meeting:

1. **What do I own and owe right now?** — consolidated balance sheet, all entities,
   all accounts, real balances and honest unknowns.
2. **How many weeks of runway do I have after known obligations?** — 12-week rolling
   cash-flow projection with surplus/deficit flags.
3. **What money is expected to arrive, through which rail, and under which entity?** —
   revenue pipeline table, collection rails, disbursement map.
4. **What taxes, filings, and reserves are accumulating before they become
   emergencies?** — tax-position estimates, filing deadlines, CPA handoff packets.
5. **Which decisions need my hand, and which ones can the office keep preparing
   without me?** — staged disbursements, open obligations, next gates.

Every answer carries an as-of date, source, confidence level, and next review gate.
Unknown data is not treated as zero. It is treated as a visible hole with an owner.

## The Office Workflows

Six continuous workflows run behind the artifacts, each mapped to kernel primitives:

| Workflow | Primitives | Artifact | Cadence |
|---|---|---|---|
| Entity → Position | Member + Standing | `balance-sheet.md` | Daily + on entity change |
| Cash-flow projection | Standing + Mandate | `cashflow.md` | Daily (12-week rolling) |
| Tax-position estimation | Standard + Member | Tax workpapers | Monthly + delta weekly |
| Disbursement scheduling | Governance + Mandate | Staged instruction packets | Daily |
| Obligations ledger | Standing + Governance | `obligations-ledger.json` | Continuous + weekly audit |
| Compliance sentinel | Governance (cross-cut) | Stamp on every output | Every output |

Every workflow feeds the next. Entity registry feeds cash-flow, tax, and disbursement.
All three feed the obligations ledger. Compliance sentinel gates everything. The
principal stands at the end of every path — no money moves, no filing is submitted,
no commitment is made without human judgment.

## Non-Negotiables

- MONETA intakes product revenue; Aerarium records and governs the institution around it.
- The human executes every transfer, trade, filing, account change, and contract.
- No credentials, private keys, raw bank tokens, or account secrets are stored in the organ.
- Every projection is advisory and assumption-labeled.
- Every tax output is a workpaper for principal/CPA review, not a filed position.
- Privacy is structural: entity boundaries are part of the model, not a UI preference.
- Unknown is not zero. Every unknown balance is a visible gap with an owner.

## The Macro-Micro Relationship

Aerarium is fractal: the MACRO (this face) is the generic platform anyone deploys.
The [MICRO face](MICRO.md) is Anthony's own running instance — his entity registry,
his balance sheet, his payrail, his portfolio and tax automation. The micro instance is
not a demo. It is the production deployment that proves the macro platform. Every
artifact described here is running on his real data.

The platform is portable: plug in a different principal, different entities, different
products, different tax jurisdiction, and different rails. The shape stays the same.
The files are the same. The generator is the same. Only the entity data changes.
