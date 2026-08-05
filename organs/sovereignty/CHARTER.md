# MANVMISSIO — the sovereignty organ (charter pointer)

**The engine lives in its own repository: [`organvm/manumissio`](https://github.com/organvm/manumissio)**
— the first standalone-repo organ on the ladder. This directory is the limen-side anchor so
dispatch/backlog generation never hits a dead clone; build work belongs in the repo.

| What | Where |
|---|---|
| Thesis (who owns the tokens; 4-layer freedom stack) | `manumissio/docs/freedom-stack.md` + founding Discussion |
| Token-value gauge (generalized) | `manumissio/gauge/token_value_gauge.py` |
| Owned-weights deed book (qwen3:8b registered, digest-verified) | `manumissio/weights/MANIFEST.json` + `acquire.py` |
| Parity harness — the math-maths predicate | `manumissio/src/parity/` (`parity gate` exit 0 ⟺ arm a class) |
| Phase backlog (issues-as-data, idempotent seeder) | `manumissio/backlog.yaml` + 13 seeded issues, 4 milestones |
| Operator-private data (spend ledger, measured token value) | **stays here**: [`organs/financial/ai-vendor-spend.md`](../financial/ai-vendor-spend.md), [`token-usage.md`](../financial/token-usage.md) |
| Plan of record | [`docs/sovereign-inference-plan.md`](../../docs/sovereign-inference-plan.md) |

**Operating rule (operator, 2026-07-09): $0 execution; nothing switches over until the math maths.**
Local-floor routing in limen ships DARK (`LIMEN_LOCAL_FLOOR` default off); a class arms only when
`parity gate --model qwen3:8b --class <c> --threshold 0.9` exits 0. First real gate run: classify,
verify, scan, link-check all 100%; summarize failed and stays rented. Hardware stays gauge-gated
(≥$200/mo sustained absorbable; measured ≈$135/mo → not met). Paid rails (OpenRouter) are pooled
as `blocked-on-spend` issues, never day-1 actions.
