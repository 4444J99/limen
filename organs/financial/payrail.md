# Payrail Disbursement Map — MICRO: Anthony's money flow

> **What this is:** the legal/tax scaffolding for how money moves from revenue source
> → institutional accounts → personal accounts → obligations. Every hop is documented
> with its rail, its gate, and whose hand must pull it.
>
> **Boundary:** this is a MAP, not a command. No money moves without the principal's
> hand in their banking portal. Each rail below is a DRAFT — staged, scheduled, surfaced
> — until the human executes it.

## Overview

```
                        ┌─────────────────────────┐
                        │  REVENUE SOURCES         │
                        │  (product sales, grants, │
                        │   consulting)             │
                        └────────┬────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
           ┌─────────────────┐     ┌──────────────────┐
           │ MONETA sovereign │     │ Ko-fi / Lemon    │
           │ cash rail (BTC)  │     │ Squeezy (fiat)   │
           └────────┬────────┘     └────────┬─────────┘
                    │                        │
                    └────────┬───────────────┘
                             ▼
                    ┌──────────────────┐
                    │  COLLECTION       │
                    │  ACCOUNTS         │
                    │  (principal-held) │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
     ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
     │ PERSONAL     │ │ LLC         │ │ NPO         │
     │ CHECKING     │ │ CHECKING    │ │ (Cind & Sol)│
     └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
            │               │               │
            ▼               ▼               ▼
     ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
     │ Obligations │ │ Business    │ │ Grants /    │
     │ (bills,     │ │ expenses,   │ │ Mission     │
     │  subs,      │ │ contractor  │ │ Spending    │
     │  loans)     │ │ payments    │ │             │
     └─────────────┘ └─────────────┘ └─────────────┘
```

## Hop 1: Revenue Source → Collection Account

### 1A. MONETA sovereign rail (preferred — zero processor dependency)

| Property | Value |
|---|---|
| **Route** | Buyer pays BTC → MONETA mint → MINT_BTC_ADDRESS (self-custodied wallet) |
| **Status** | [BUILT] — checkout page, mint, offline license verify all merged. Gated on deploy + MINT_BTC_ADDRESS. |
| **Gate** | Principal deploys MONETA to a $0/low host (Docker-ready) + pastes a self-custodied BTC receive address |
| **His hand** | L-REVENUE-ACCT (#253) — two reversible steps |
| **Tax treatment** | BTC received → USD equivalent at time of receipt = income. Self-custodied = no third-party reporting. Principal tracks cost basis per receipt. |
| **Fallback** | If BTC is impractical, principal swaps to USDC or converts to fiat via a personal exchange account |

### 1B. Ko-fi (individual fiat rail)

| Property | Value |
|---|---|
| **Route** | Buyer pays via card/PayPal → Ko-fi → principal's PayPal or bank |
| **Status** | [LIVE] — account exists, no KYC block (individual, not LLC) |
| **Gate** | Principal verifies Ko-fi dashboard and transfers to personal checking |
| **His hand** | Dashboard access (credential — outside organ scope) |
| **Tax treatment** | Income when received. Ko-fi issues no 1099-K below $20k/200tx. Principal reports as other income on Schedule C or Sch 1. |

### 1C. Lemon Squeezy (individual fiat rail)

| Property | Value |
|---|---|
| **Route** | Buyer pays via card → Lemon Squeezy → principal's bank |
| **Status** | [INTEGRATED] — Pro tier checkout wired, gated on deploy |
| **Gate** | Principal deploys the Exporter, then Lemon Squeezy sends payouts |
| **His hand** | Deploy (one `git push` + `wrangler deploy`) |
| **Tax treatment** | Income when received. Lemon Squeezy handles VAT/sales tax. Principal reports as other income. |

## Hop 2: Collection Account → Entity Account

### 2A. Individual (Anthony personal)

| Property | Value |
|---|---|
| **Default for** | All current product revenue (Exporter, future products) |
| **Collection → Distribution** | Ko-fi → PayPal → personal checking. MONETA BTC → personal exchange → personal checking. |
| **Why this route** | Dead LLC blocks Stripe. Individual rail is unblocked NOW. |
| **Tax treatment** | Revenue flows through the individual. Principal reports on Schedule C (sole proprietor). Self-employment tax applies. QBI deduction may be available. |

### 2B. Sovereign Systems LLC (commercial vehicle)

| Property | Value |
|---|---|
| **Default for** | Consulting contracts, enterprise deals, any revenue needing an EIN |
| **Status** | [DORMANT] — Stripe KYC blocked. Not active until LLC is revived or dissolved. |
| **Gate** | Principal decides: revive the LLC (clear the Stripe KYC) or dissolve and operate entirely as individual |
| **His hand** | Legal decision + state filing |
| **Tax treatment** If revived | LLC income flows to principal via Schedule C (single-member default) or S-election. Business expenses deductible. Self-employment tax on all net income. |

### 2C. Cind & Sol Foundation (non-profit)

| Property | Value |
|---|---|
| **Default for** | Grants, donations, mission-aligned revenue |
| **Status** | [FORMED] — Panama foundation. Grant-finding via Quaestor. |
| **Gate** | Principal directs which revenue is mission-aligned |
| **His hand** | Board direction (see governance organ — cursus honorum) |
| **Tax treatment** | Non-profit income is tax-exempt in jurisdiction. Principal does NOT report foundation income on personal return. Grants must be for exempt purposes. |

## Hop 3: Entity Account → Obligations

### 3A. Personal obligations (paid from personal checking)

| Obligation | Frequency | Est. amount | Rail |
|---|---|---|---|
| Student loan (Nelnet) | Monthly | Unknown (default risk detected) | ACH from personal checking |
| Rent / housing | Monthly | Unknown | Check or ACH |
| Insurance premiums | Monthly/Annual | Unknown | ACH or card |
| Subscriptions (Apple, Netflix, etc.) | Monthly | Unknown | Card on file |
| Credit card (Santander card-0186) | Monthly | Unknown | ACH — currently blocked by fraud hold |

### 3B. Business obligations (paid from LLC — when active)

| Obligation | Frequency | Est. amount | Rail |
|---|---|---|---|
| Domain renewals (Namecheap, etc.) | Annual | ~$50-200 | Card |
| Cloud services (Cloudflare, etc.) | Monthly | ~$5-20 | Card |
| Developer account fees (Apple) | Annual | $99 | Card |
| Contractor payments | Per-engagement | Variable | ACH or PayPal |

### 3C. NPO obligations (paid from Cind & Sol)

| Obligation | Frequency | Est. amount | Rail |
|---|---|---|---|
| Grant distributions | Per-board-decision | Variable | Wire or ACH |
| Foundation admin costs | Annual | Unknown | TBD |

## Hop 4: Discretionary → Goal-based allocation

Not yet modeled. Placeholder for the Mandate primitive:

- **Savings / emergency fund** — target: 3-6 months of obligations
- **Investment** — target: TBD (principal decides allocation)
- **Tax reserve** — auto-calculated from revenue projection
- **Discretionary spending** — remainder after obligations + reserves

## Rail inventory

| Rail | Type | Status | Gate |
|---|---|---|---|
| MONETA (BTC) | Sovereign (self-custodied) | BUILT — pools demand | Deploy + MINT_BTC_ADDRESS |
| Ko-fi | Processor (individual) | LIVE — account exists | Dashboard access |
| Lemon Squeezy | Processor (individual) | INTEGRATED — gated on deploy | `git push` + `wrangler deploy` |
| Stripe (via LLC) | Processor (business) | BLOCKED — dead-LLC KYC | Revive LLC or accept block |
| PayPal | Processor (individual) | LIVE — linked to Ko-fi | Dashboard access |
| ACH / wire | Bank (direct) | LIVE — all personal accounts | Principal's banking portal |
| Paper check | Physical | LIVE | Principal's checkbook |

## Key constraints

1. **No money movement by the organ.** Every rail ends at the principal's review-and-execute step. The organ drafts, schedules, and surfaces — it never sends.
2. **No stored credentials.** Banking/broker APIs are never integrated. The principal moves money in their own portals.
3. **Individual rail is the path of least resistance.** Until the LLC is revived, all product revenue flows through the individual. This is simpler (no EIN needed, no separate return) but means self-employment tax applies.
4. **MONETA is the sovereign ideal — but not the only path.** The self-custodied BTC rail removes all processor dependency but requires a deploy + address. The processor rails (Ko-fi, Lemon Squeezy) are available now.
5. **Tax projection is advisory.** Every hop implies a tax consequence. The Tax Strategist role (see CHARTER.md) estimates positions; a CPA validates every filing.
