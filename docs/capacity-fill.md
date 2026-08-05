# Capacity Fill

Generated: `2026-07-10T12:43:56+00:00`
Status: `blocked`

## Capacity Census

| Agent | Kind | Reachable | Remaining | Limit | Detail |
|---|---|---|---|---|---|
| `codex` | local-cli | `up` | 69 | 100 | /opt/homebrew/bin/codex; live usage meter: remaining=69/100, consumed=31 |
| `claude` | local-cli | `up` | 98317080 | 100000000 | /Users/4jp/.local/bin/claude; live usage meter: remaining=98317080/100000000, consumed=1682920 |
| `opencode` | local-cli | `up` | 19749889 | 50000000 | /opt/homebrew/bin/opencode; live usage meter: remaining=19749889/50000000, consumed=30250111 |
| `agy` | local-cli | `up` | 57 | 100 | /opt/homebrew/bin/agy; live usage meter: remaining=57/100, consumed=43 |
| `gemini` | local-cli | `down` | 0 | 10 | /opt/homebrew/bin/gemini; live usage meter: remaining=0/10, consumed=11; usage health=exhausted; live remaining=0; dispatch down-lane gate |
| `ollama` | local-cli | `down` | 592 | 600 | /opt/homebrew/bin/ollama; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane |
| `jules` | cloud-cli | `down` | 0 | 100 | /opt/homebrew/bin/jules; live usage meter: remaining=0/100, consumed=109; usage health=exhausted; live remaining=0; dispatch down-lane gate |
| `copilot` | github-issue | `down` | 592 | 600 | /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent) |
| `warp` | paid-service | `down` | 592 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `oz` | paid-service | `down` | 592 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `github_actions` | github-actions | `down` | 592 | 600 | /opt/homebrew/bin/gh; workflow=limen-agent.yml@organvm/limen unavailable: HTTP 404: workflow limen-agent.yml not found on the default branch (https://api.github.com/repos/organvm/limen/actions/workflows/limen-agent.yml) |

## Signal Quality

| Agent | Signal | Trust | Use | Next Build |
|---|---|---|---|---|
| `codex` | vendor rate-limit meter | measured | usage health=ok; used=31/100 percent; remaining=69; headroom=69%; weekly=26.0%; source=vendor rate_limits; usable for pacing from provider rate_limits; weekly plan headroom is a steering input | Keep harvesting Codex vendor rate_limits into usage telemetry. |
| `claude` | transcript-token estimate | estimate | usage health=ok; used=1682920/100000000 tokens; remaining=98317080; headroom=98%; source=ESTIMATE - tune to plan (/status); usable for pacing; rate-limit events still dominate stop decisions | Calibrate Claude plan pool cap from a trusted account meter. |
| `opencode` | db-meter | measured | token clock health=ok; used=60.5%; accepting_tasks=True; updated=2026-07-10T12:43:19.937267+00:00; usage health=ok; used=30250111/50000000 tokens; remaining=19749889; headroom=39%; source=operator board cap until live vendor meter | Keep opencode-clock fresh from the SQLite usage DB. |
| `agy` | usage-telemetry proxy | proxy + recent-rl | usage health=ok; used=43/100 runs; remaining=57; headroom=57%; source=operator board cap until live vendor meter; reachable; no recent heartbeat rate-limit marker; not proof of provider quota | Add a provider-backed Agy meter or recent rate-limit receipt. |
| `gemini` | usage-telemetry proxy | proxy + recent-rl | usage health=exhausted; used=11/10 runs; remaining=0; headroom=0%; source=operator board cap until live vendor meter; reachable when auth is configured; no recent heartbeat rate-limit marker; daily cap remains board-derived | Add a Gemini quota/rate-limit receipt if available. |
| `ollama` | local model presence | binary/model | down until a model is pulled | Pull the configured local model to light the floor lane. |
| `jules` | usage-telemetry proxy | proxy + known cap | usage health=exhausted; used=109/100 runs; remaining=0; headroom=0%; source=known hard cap; remote async service; no recent heartbeat rate-limit marker; use for remote batch fill | Keep Jules remote-launch receipts and harvest status fresh. |
| `copilot` | assignability probe | reachability | down until Copilot coding agent assignment is confirmed | Enable Copilot coding agent and set LIMEN_COPILOT_ENABLED=1. |
| `warp` | credential presence | credential gate | down until WARP_API_KEY is installed | Install WARP_API_KEY locally and as the workflow secret. |
| `oz` | credential presence | credential gate | down until WARP_API_KEY is installed | Install WARP_API_KEY locally and as the workflow secret. |
| `github_actions` | workflow reachability | reachability | can launch workflow packets; not a local quota meter | Surface queued/running workflow capacity from GitHub checks. |

## Blockers

- `gemini`: /opt/homebrew/bin/gemini; live usage meter: remaining=0/10, consumed=11; usage health=exhausted; live remaining=0; dispatch down-lane gate
- `ollama`: /opt/homebrew/bin/ollama; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane
- `jules`: /opt/homebrew/bin/jules; live usage meter: remaining=0/100, consumed=109; usage health=exhausted; live remaining=0; dispatch down-lane gate
- `copilot`: /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent)
- `warp`: WARP_API_KEY not set (set env var + add as org/repo Actions secret)
- `oz`: WARP_API_KEY not set (set env var + add as org/repo Actions secret)
- `github_actions`: /opt/homebrew/bin/gh; workflow=limen-agent.yml@organvm/limen unavailable: HTTP 404: workflow limen-agent.yml not found on the default branch (https://api.github.com/repos/organvm/limen/actions/workflows/limen-agent.yml)

## Claude

- Binary/path reachable: `True`.
- Remaining capacity: `98317080`.
- Limit: `100000000`.
- Detail: /Users/4jp/.local/bin/claude; live usage meter: remaining=98317080/100000000, consumed=1682920.

## Contract

- This ledger does not modify tasks, credentials, workflow state, or remote systems.
- Run `python3 scripts/dispatch-health.py --write --probe-async` for a heartbeat/operator snapshot, then re-run `python3 scripts/capacity-fill-ledger.py --write` after repairs.

## Commands

- Refresh this ledger: `python3 scripts/capacity-fill-ledger.py --write`
- Refresh dispatch heartbeat: `python3 scripts/dispatch-health.py --write --probe-async`
