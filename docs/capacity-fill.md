# Capacity Fill

Generated: `2026-07-06T10:19:11+00:00`
Status: `blocked`

## Capacity Census

| Agent | Kind | Reachable | Remaining | Limit | Detail |
|---|---|---|---|---|---|
| `codex` | local-cli | `down` | 0 | 100 | /opt/homebrew/bin/codex |
| `claude` | local-cli | `up` | 100 | 100 | /Users/4jp/.local/bin/claude |
| `opencode` | local-cli | `up` | 33 | 100 | /opt/homebrew/bin/opencode |
| `agy` | local-cli | `up` | 76 | 100 | /opt/homebrew/bin/agy |
| `gemini` | local-cli | `up` | 10 | 10 | /opt/homebrew/bin/gemini |
| `ollama` | local-cli | `down` | 309 | 600 | /opt/homebrew/bin/ollama; no model pulled; local disk pressure blocks qwen2.5-coder:7b pull (24.6 GiB free, need >= 50 GiB) |
| `jules` | cloud-cli | `down` | 0 | 100 | /opt/homebrew/bin/jules |
| `copilot` | github-issue | `down` | 309 | 600 | /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent) |
| `warp` | paid-service | `down` | 309 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `oz` | paid-service | `down` | 309 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `github_actions` | github-actions | `up` | 309 | 600 | /opt/homebrew/bin/gh; workflow=limen-agent.yml |

## Signal Quality

| Agent | Signal | Trust | Use | Next Build |
|---|---|---|---|---|
| `codex` | vendor rate-limit meter | measured | usage health=ok; used=32/100 percent; remaining=68; headroom=68%; weekly=29.0%; source=vendor rate_limits; usable for pacing from provider rate_limits; weekly plan headroom is a steering input | Keep harvesting Codex vendor rate_limits into usage telemetry. |
| `claude` | transcript-token estimate | estimate | usage health=ok; used=1292022/100000000 tokens; remaining=98707978; headroom=99%; source=ESTIMATE - tune to plan (/status); usable for pacing; rate-limit events still dominate stop decisions | Calibrate Claude plan pool cap from a trusted account meter. |
| `opencode` | db-meter | measured | token clock health=ok; used=44.31%; accepting_tasks=True; updated=2026-07-06T09:43:24.505365+00:00; usage health=ok; used=22155965/50000000 tokens; remaining=27844035; headroom=56%; source=operator board cap until live vendor meter | Keep opencode-clock fresh from the SQLite usage DB. |
| `agy` | usage-telemetry proxy | proxy + recent-rl | usage health=ok; used=31/100 runs; remaining=69; headroom=69%; source=operator board cap until live vendor meter; reachable; no recent heartbeat rate-limit marker; not proof of provider quota | Add a provider-backed Agy meter or recent rate-limit receipt. |
| `gemini` | usage-telemetry proxy | proxy + recent-rl | usage health=ok; used=0/10 runs; remaining=10; headroom=100%; source=operator board cap until live vendor meter; reachable when auth is configured; no recent heartbeat rate-limit marker; daily cap remains board-derived | Add a Gemini quota/rate-limit receipt if available. |
| `ollama` | local model presence | binary/model | down until a model is pulled | Clear local disk pressure before pulling qwen2.5-coder:7b; current free space is 24.6 GiB. |
| `jules` | dispatch-count cap | known cap | down locally until CLI/service path is available | Restore Jules CLI/service reachability. |
| `copilot` | assignability probe | reachability | down until Copilot coding agent assignment is confirmed | Enable Copilot coding agent and set LIMEN_COPILOT_ENABLED=1. |
| `warp` | credential presence | credential gate | down until WARP_API_KEY is installed | Install WARP_API_KEY locally and as the workflow secret. |
| `oz` | credential presence | credential gate | down until WARP_API_KEY is installed | Install WARP_API_KEY locally and as the workflow secret. |
| `github_actions` | workflow reachability | reachability | can launch workflow packets; not a local quota meter | Surface queued/running workflow capacity from GitHub checks. |

## Blockers

- `codex`: /opt/homebrew/bin/codex
- `ollama`: /opt/homebrew/bin/ollama; no model pulled; local disk pressure blocks qwen2.5-coder:7b pull (24.6 GiB free, need >= 50 GiB)
- `jules`: /opt/homebrew/bin/jules
- `copilot`: /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent)
- `warp`: WARP_API_KEY not set (set env var + add as org/repo Actions secret)
- `oz`: WARP_API_KEY not set (set env var + add as org/repo Actions secret)

## Claude

- Binary/path reachable: `True`.
- Remaining capacity: `100`.
- Limit: `100`.
- Detail: /Users/4jp/.local/bin/claude.

## Contract

- This ledger does not modify tasks, credentials, workflow state, or remote systems.
- Run `python3 scripts/dispatch-health.py --write --probe-async` for a heartbeat/operator snapshot, then re-run `python3 scripts/capacity-fill-ledger.py --write` after repairs.

## Commands

- Refresh this ledger: `python3 scripts/capacity-fill-ledger.py --write`
- Refresh dispatch heartbeat: `python3 scripts/dispatch-health.py --write --probe-async`
