# AI Vendor Spend Audit

*Phase 0 of [`docs/sovereign-inference-plan.md`](../../docs/sovereign-inference-plan.md). Source: Gmail
receipt sweep, 90–120 days ending 2026-07-08. Amounts are receipt-verified unless marked inferred;
`-` = no receipt found (the `balance_known: false` pattern — principal fills in what email doesn't
show). Card refs use the established last-4 shorthand.*

## Summary

- **Known recurring total: $495.26/mo** (+ Cloudflare variable $0–24/mo) — matches the estimated "$500+".
- Vendors: 6 recurring · 4 pay-per-use/credits ($0 recurring found) · 2 currently failing on the card-0186 hold.
- **Recommended end state after decisions below: ~$265–295/mo** (cut ≈ $200–230/mo, no capability loss to the fleet).

## Vendor Ledger

| Rank | Vendor | Product / Tier | $/mo | Cadence | Status | Keep/Cancel | Next step | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | Anthropic | Claude Max 20x | 217.75 | monthly, 18th | **paused** — Jun 18 charge failed | **KEEP** | resolve card-0186 hold (existing lever), payment resumes | $200 + NY tax. Fleet-native flat-rate sub; heavy agentic use makes this the best token arbitrage in the stack. The last sub to ever cancel (plan Phase 4). |
| 2 | OpenAI | ChatGPT Pro | ~200 (inferred) | monthly | active | **DOWNGRADE → Plus ($20)** | L-AI-SPEND-OPENAI below | No receipt emails found (billing possibly via Apple/other rail — verify at chatgpt.com/settings). Pro's premium is Codex caps + Pro-only features; the Codex fleet lane survives on Plus at lower caps. Biggest single cut: ≈$180/mo. |
| 3 | GitHub | Enterprise Cloud usage (meta-organvm) | 45.73 | monthly usage cycle | **billing failing** (card-0186) | **REVIEW** | L-AI-SPEND-GHE below | $42 + tax. Not an AI sub per se — org infra. Itemization is in the receipt PDF only. Review whether Enterprise features are load-bearing vs Team/Free. |
| 4 | Warp | Build plan | 21.78 | monthly, 10th | active | **CANCEL → free tier** | L-AI-SPEND-WARP below | $20 + tax, card-0920. Warp's AI features duplicate Claude Code in the terminal; free tier keeps the terminal itself. ≈$22/mo cut. |
| 5 | Anomaly | OpenCode Go | 10.00 | monthly, ~31st | active | **KEEP** | — | Cheap lane diversity: opencode is a registered fleet lane in the dispatch cascade. $10/mo is the cheapest working vendor lane in the stack. |
| 6 | Cloudflare | Workers/Pages usage | 0–24.20 | monthly, variable | active | **KEEP** | — | Infra, not AI spend — hosts the live limen runtime (Worker + Pages). Usage-priced. |
| 7 | Perplexity | credits | - | credits | out of credits (Jun 29) | **NO ACTION** | — | No receipts found → no recurring sub detected; credit-exhaustion emails only. Do not add auto-refill. |
| 8 | xAI | Grok tasks / API | - | - | active use, no receipts | **VERIFY $0** | check x.ai billing page | Heavy Grok scheduled-task use Apr–Jul but zero receipts to this inbox — confirm nothing bills elsewhere (X Premium rail). |
| 9 | OpenRouter | prepaid credits | - | ad hoc | account active | **NO ACTION** | — | Newsletter-only; no charges found. This is the Phase 2 open-weight API rail — spend will appear here *by design* later, displacing subscription dollars. |
| 10 | Google | Gemini / GCP AI | 0 | — | **suspended** (CONSUMER_SUSPENDED; card-0186 cascade) | **NO ACTION** | existing card-hold lever | Nothing billing while suspended. Restore is downstream of the card fix, already registered. |

## Decisions (his-hand)

Account changes are spend/send-class actions — they stay on the principal's hand. Each is one
sitting at a vendor billing page; candidates for hoisting into `his-hand-levers.json` by the
registry organ (that file is daemon-contended and not edited here).

| Lever | Action | Monthly delta |
|---|---|---|
| `L-AI-SPEND-OPENAI` | chatgpt.com → Settings → Subscription → downgrade Pro → Plus. Codex lane persists at Plus caps; if Codex throughput visibly starves the fleet, that is new data — revisit, don't pre-pay for it. | **−$180** |
| `L-AI-SPEND-WARP` | app.warp.dev → Settings → Plans → downgrade Build → Free. | **−$21.78** |
| `L-AI-SPEND-GHE` | github.com → meta-organvm → Billing: open the receipt PDF itemization; if Enterprise-only features (SAML/audit-log/etc.) are not load-bearing, downgrade to Team/Free. Also unblocks one of the two card-0186 billing failures. | **−$0 to −$45.73** |
| *(existing)* card-0186 hold | Already registered as its own lever — resolving it un-pauses Claude Max (the fleet's primary sub) and clears the GitHub billing failure. Upstream of everything above. | — |

**Non-decisions (already settled by the plan):** Claude Max stays (fleet-native, Phase 4 decides its
eventual end by eval predicate, not by feeling); OpenCode Go stays (cheapest live lane); Cloudflare
stays (runtime infra); no auto-refill on any credits product.

## Re-audit cadence

Re-run the Gmail receipt sweep when any lever above flips, or monthly otherwise; update this ledger
in place (one row per vendor — no append-only growth). Phase 2 of the plan adds the per-tier token
gauge, which is what eventually justifies (or kills) each remaining row.
