# Sovereign Inference Plan — Liberation from AI Providers

*Filed 2026-07-08. Owner: the model-selection organ (`cli/src/limen/model_selection.py`) — this doc
is the plan of record; the routing ladder and its env pins are the executable surface.*

> **Built out 2026-07-09 → the MANVMISSIO organ, [`organvm/manumissio`](https://github.com/organvm/manumissio)**
> (rank-13 on the organ ladder; limen anchor at [`organs/sovereignty/`](../organs/sovereignty/CHARTER.md)).
> The engine — generalized token-value gauge, owned-weights deed book (qwen3:8b registered,
> digest-verified), and the `parity` gate that arms every switchover — lives there, with the phase
> backlog as 13 seeded issues across 4 milestones. Operator-private numbers stay in
> [`organs/financial/`](../organs/financial/ai-vendor-spend.md). Hard rule: $0 execution; nothing
> switches over until the math maths (parity gate exit 0 per class; hardware gauge-gated).

**The ask:** stop paying ~$500+/mo across Anthropic, OpenAI, and other AI vendors; run our own
models. **The honest answer:** liberation is a ladder you climb tier-by-tier as open weights close
the capability gap — not a switch you flip. Flipping it today trades away exactly the frontier-class
long-horizon agentic capability that runs this fleet. The plan below cuts ~70-80% of the spend this
quarter with zero capex, makes the remainder measurable, and gates the hardware buy on measured
data instead of vibes.

## Ground truth (measured 2026-07-08)

| Fact | Value | Consequence |
|------|-------|-------------|
| Host machine | Apple M5, **16 GB RAM**, 36 GB free disk | Can run ~4-8B quantized models only. This box is the *floor*, never the frontier. Owned frontier inference = a second machine. |
| Ollama | installed, **zero models pulled** | The FLAME.md "ollama floor" is aspirational, not enacted. Phase 1 makes it real. |
| Routing layer | `_CLAUDE_TIER_ORDER = (haiku, sonnet, opus, fable)` + `LIMEN_CLAUDE_<TIER>_MODEL` env pins | The provider-liberation seam already exists. A local/open tier is one adapter + env pins, not a rewrite. |
| Spend | "~$500+/mo, probably for different AIs" — **not itemized anywhere** | Phase 0 is an audit. You cannot liberate from a bill you can't enumerate. |

## The capability ledger (be honest about the gap)

- **Open weights are Sonnet-class now.** DeepSeek-V3.x/R1, Qwen3 (Coder/235B), GLM-4.x, Kimi K2
  are genuinely strong at coding and tool use, and their hosted APIs run **10-30× cheaper per
  token** than frontier vendors.
- **They do not yet match Opus/Fable-class long-horizon agentic reliability** — the tier the limen
  fleet's `synthesis`/`canon`/`kernel` classes reserve. That is the part still worth renting.
- **Open weights = no lock-in even when hosted.** The same model file runs on DeepSeek's API,
  OpenRouter, Fireworks, or your own box. The provider becomes a replaceable adapter — the same
  thesis limen applies to its own surfaces.
- **The flat-rate trap:** a heavily-used Claude Max subscription burns far more tokens than its
  sticker price would buy at API rates. Naively "switching to API" can *raise* cost. Liberation
  order: cancel the *other* subscriptions first; the fleet-native flat-rate sub is the last to go.

## The plan

### Phase 0 — Audit + subscription arbitrage (this week, $0 capex, expected cut $150-250/mo)

1. **Itemize the bill.** One ledger row per AI vendor: name, $/mo, what it uniquely does, last
   time it was load-bearing. Home: `organs/financial/cashflow.md` (the financial organ already
   tracks vendor atoms; the card-0186 → Anthropic/GCP payment cascade shows the data flows there).
2. **Kill overlap.** Multiple frontier chat subscriptions are redundant with one fleet-native sub
   plus per-token API keys. Keep vendor *diversity* as API keys (pay-per-use burst capacity —
   never serialize vendors), not as parallel fixed subscriptions.
3. **Keep exactly one flat-rate frontier sub** — the one the fleet is native to (Claude Code).

### Phase 1 — Enact the local floor (this month, $0)

1. Pull one small model into ollama sized to this box (~5 GB, e.g. a Qwen3-8B-class quant; disk
   is at 36 GB free — one model, small, no collection).
2. Add a `local` rung below `haiku`: ollama exposes an OpenAI-compatible endpoint; route the
   cheap job classes (`scan`/`verify`-grade: classification, link checks, summaries, routing)
   to it via the existing tier machinery.
3. This also makes FLAME.md true: the continuity kernel actually runs when every provider is down
   or every card is frozen — the current payment-cascade lever is a live demonstration of why a
   floor that needs a working credit card is not a floor.

### Phase 2 — Open-weight API tier (month 1-2, the deepest cut)

1. Route `sonnet`-class bulk work to open-weight hosted APIs (DeepSeek direct, or
   Qwen3/GLM/Kimi via OpenRouter/Fireworks/Together) — pennies per million tokens.
2. **Stamp the gauge.** Per-tier token volume must be recorded by the organ (gauges lie unless
   organs stamp): tokens/mo per tier × price per token = the number every later decision derives
   from.
3. End state of this phase: one frontier sub + open-weight API keys ≈ **$100-150/mo**, with the
   fleet's cheap and mid tiers already provider-sovereign (weights portable to any host, including
   Phase 3 hardware, with zero rerouting).

### Phase 3 — Owned hardware, sized by the gauge (only when measured demand proves it)

- **Trigger:** ≥ ~$200/mo sustained open-weight API spend for 2 consecutive months (from the
  Phase 2 gauge). Below that, hosted open weights stay cheaper than owning.
- **Default buy:** a dedicated high-unified-memory Mac (128 GB class ≈ $3.5-4.7k → runs
  GLM-Air/Qwen3-30B-class fast; 512 GB M3-Ultra class ≈ $9.5k → runs DeepSeek/Kimi-class quants).
  Payback at absorbed spend: ~8-19 months. Mac over GPU rig for this operation: silent, low
  watts, macOS-native tooling (the host-is-factory doctrine), MLX ecosystem. A used-GPU rig is
  the escalation only if parallel-agent throughput becomes the bottleneck.
- **The M5 16 GB box is not upgradeable into this role.** Owned inference is a second machine,
  bought with measured numbers, or not bought at all.

### Phase 4 — The last subscription dies by predicate, not by feeling

Liberation's Definition of Done is executable: an eval harness that replays real fleet job classes
against a candidate open model and flips a tier to local/open **when it passes at parity on our own
tasks** (never on public benchmarks). The frontier sub dies when the last reserved class
(`synthesis`, `canon`, `kernel`) passes — or is consciously retained as a $20-100/mo burst tier.
Realistic 2026 end state: **80-90% of tokens local/open-weight; the top tier rented until open
weights catch it.** Each tier flip is a routing-config change, because Phases 1-2 made providers
adapters.

## Money summary

| Stage | $/mo | Capex |
|-------|------|-------|
| Today | ~$500+ (unitemized) | — |
| After Phase 0 | ~$250-350 | $0 |
| After Phase 2 | ~$100-150 | $0 |
| After Phase 3 (optional) | ~$50-120 | $3.5-9.5k, payback 8-19 mo, gauge-gated |

## Non-goals

- **Not** dropping frontier capability for the reserved classes to hit $0/mo — the fleet's output
  funds the operation; a capability haircut there costs more than it saves.
- **Not** buying hardware first. Every $ of capex is derived from a stamped gauge, per
  *value is discovered, never assumed*.
- **Not** adding a new provider *dependency*: every routing change in this plan must keep the
  model swappable by env pin alone.
