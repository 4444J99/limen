# Aerarium MACRO Face — Family Office in a Box

> **Promise:** deploy the operating system a family office gives a wealthy principal:
> every entity known, every account classified, every obligation visible, every cash
> path modeled, every tax exposure staged for review, and every disbursement governed
> before anyone touches a bank portal.
>
> **Boundary:** Aerarium does not move money, execute trades, open accounts, file taxes,
> or sign anything. MONETA owns sovereign intake at `moneta/`. Aerarium owns the census,
> ledger, forecast, payrail map, tax workpapers, and review gates around that intake.

## What It Is

Aerarium is the personal family office layer built from the-invisible-ledger's accounting
core. The old shape was a B2B CPA tool: organize books for a business and its accountant.
The scaled shape is broader and more valuable: one deployable financial office for a person,
family, or small institution that needs institutional weight without hiring a staff.

The platform turns scattered financial facts into one operating surface:

- **Entity registry:** people, LLCs, nonprofits, trusts, products, wallets, accounts, and
  obligations are registered as first-class financial members.
- **Consolidated balance sheet:** assets and liabilities roll up across every entity, with
  unknown balances explicitly marked instead of hidden.
- **Rolling cash-flow projection:** known inflows, obligations, runway, and reserve needs are
  rebuilt on cadence.
- **Payrail disbursement map:** money paths are modeled from revenue source to collection
  account to entity account to obligation, with the gate and tax treatment for each hop.
- **Tax-position desk:** estimated liabilities, installments, filing windows, deductions,
  and CPA handoff packets are staged from the same ledger.
- **Compliance sentinel:** every output is checked for source timestamp, approval gate,
  segregation of duties, assumption labels, and policy limits.

This is not another budgeting app. A budget app asks a person to remember. Aerarium makes the
institution remember.

## The Deployable Office

Anyone deploying the macro instance gets the same structure Anthony's micro instance uses:

| Office desk | What it holds | Primary artifact |
|---|---|---|
| Census | Entities, accounts, instruments, jurisdictions, ownership, and access boundaries | `entities.yaml` |
| Books | Classified assets/liabilities and balance snapshots | `balance-sheet.md`, `balances-history.json` |
| Treasury | Inflows, obligations, runway, reserve needs, and weekly cash posture | `cashflow.md` |
| Rail map | Revenue intake and disbursement paths, with gates and tax notes | `payrail.md` |
| Tax desk | Estimated exposure, prep packet checklist, deadline calendar, CPA review notes | tax-position workpapers |
| Governance | Human approvals, policy thresholds, audit stamps, no-action boundaries | `STATUS.md` + compliance stamp |

The operating model is deliberately boring: structured files first, generated dashboards second,
live integrations only after the file-backed truth is correct. A person can run the office by
editing YAML and Markdown. A product can run the same office through UI and feeds.

## How The-Invisible-Ledger Scales

The-invisible-ledger becomes the accounting engine underneath Aerarium:

1. **From business books to entity census.** A customer is no longer only a company with
   transactions. The office can hold a natural person, an LLC, a nonprofit, a product line,
   a wallet, a receivable, and a liability in one governed registry.
2. **From reconciliation to position.** Reconciled entries roll into net worth, runway,
   tax exposure, and open decisions.
3. **From CPA handoff to continuous desk.** Tax work is not a yearly scramble. The tax desk
   maintains current estimates and hands a CPA a clean packet when filing time arrives.
4. **From processor billing to sovereign intake.** MONETA is the cash rail for processor-free
   product revenue. Aerarium never becomes the rail; it records the receipt, cost basis, route,
   reserve, and disbursement plan around the rail.
5. **From dashboard to controls.** The office does not merely display numbers. It prevents
   unreviewed money movement by making every disbursement a staged instruction with a human gate.

The macro platform is therefore portable: plug in a different principal, different entities,
different products, different tax jurisdiction, and different rails. The shape stays the same.

## What The Principal Sees

The face should answer five questions without a meeting:

1. **What do I own and owe right now?**
2. **How many weeks of runway do I have after known obligations?**
3. **What money is expected to arrive, through which rail, and under which entity?**
4. **What taxes, filings, and reserves are accumulating before they become emergencies?**
5. **Which decisions need my hand, and which ones can the office keep preparing without me?**

Every answer carries an as-of date, source, confidence level, and next review gate. Unknown data
is not treated as zero. It is treated as a visible hole with an owner.

## First Useful Deployment

The first deployment can run without bank credentials:

1. Copy the `entity_template` from `entities.yaml`.
2. Register the principal, operating entities, products, collection rails, and known liabilities.
3. Enter manual balances with `balance_known: true`, `balance`, and `as_of` where available.
4. Run `python3 organs/financial/consolidate.py`.
5. Review `balance-sheet.md`, `cashflow.md`, `payrail.md`, `STATUS.md`, and
   `web/app/public/financial-standing.json`.
6. Add tax deadlines, reserve rules, and recurring obligations as they are discovered.

That is enough to turn a scattered financial life into a governed office. Automation can deepen
the office later, but it is not allowed to become a precondition for knowing where the money stands.

## Non-Negotiables

- MONETA intakes product revenue; Aerarium records and governs the institution around it.
- The human executes every transfer, trade, filing, account change, and contract.
- No credentials, private keys, raw bank tokens, or account secrets are stored in the organ.
- Every projection is advisory and assumption-labeled.
- Every tax output is a workpaper for principal/CPA review, not a filed position.
- Privacy is structural: entity boundaries are part of the model, not a UI preference.

