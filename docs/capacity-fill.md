# Capacity Fill

Generated: `2026-08-21T14:23:26+00:00`
Status: `blocked`

## Capacity Census

| Agent | Kind | Reachable | Remaining | Limit | Detail |
|---|---|---|---|---|---|
| `codex` | local-cli | `up` | 34 | 100 | /opt/homebrew/bin/codex; live usage meter: remaining=34/100, consumed=66 |
| `claude` | local-cli | `up` | 100000000 | 100000000 | /Users/4jp/Workspace/limen/scripts/shims/claude; live usage meter: remaining=100000000/100000000, consumed=0 |
| `opencode` | local-cli | `up` | 100 | 100 | /opt/homebrew/bin/opencode; live usage meter: remaining=100/100, consumed=0 |
| `agy` | local-cli | `up` | 100 | 100 | /opt/homebrew/bin/agy; live usage meter: remaining=100/100, consumed=0 |
| `gemini` | local-cli | `up` | 10 | 10 | /opt/homebrew/bin/gemini; live usage meter: remaining=10/10, consumed=0 |
| `ollama` | local-cli | `down` | 600 | 600 | /opt/homebrew/bin/ollama; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane |
| `jules` | cloud-cli | `up` | 100 | 100 | /opt/homebrew/bin/jules; live usage meter: remaining=100/100, consumed=0 |
| `copilot` | github-issue | `up` | 600 | 600 | /opt/homebrew/bin/gh; copilot-swe-agent assignable on organvm/limen |
| `warp` | paid-service | `down` | 600 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `oz` | paid-service | `down` | 600 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `github_actions` | github-actions | `up` | 600 | 600 | /opt/homebrew/bin/gh; workflow=limen-agent.yml@organvm/limen |

## Signal Quality

| Agent | Signal | Trust | Use | Next Build |
|---|---|---|---|---|
| `codex` | vendor rate-limit meter | measured | usage health=ok; used=66/100 percent; remaining=34; headroom=34%; source=vendor rate_limits; usable for pacing from provider rate_limits; weekly plan headroom is a steering input | Keep harvesting Codex vendor rate_limits into usage telemetry. |
| `claude` | transcript-token estimate | estimate | usage health=ok; used=0/100000000 tokens; remaining=100000000; headroom=100%; source=ESTIMATE - tune to plan (/status); usable for pacing; rate-limit events still dominate stop decisions | Calibrate Claude plan pool cap from a trusted account meter. |
| `opencode` | dispatch-count proxy | proxy | usage health=ok; used=0/100 runs; remaining=100; headroom=100%; source=operator board cap until live vendor meter; usable only as a dispatch-count fallback until opencode-clock writes its DB meter | Restore opencode-clock so the SQLite usage DB emits clock.json. |
| `agy` | usage-telemetry proxy | proxy + recent-rl | usage health=ok; used=0/100 runs; remaining=100; headroom=100%; source=operator board cap until live vendor meter; reachable; no recent heartbeat rate-limit marker; not proof of provider quota | Add a provider-backed Agy meter or recent rate-limit receipt. |
| `gemini` | usage-telemetry proxy | proxy + recent-rl | usage health=ok; used=0/10 runs; remaining=10; headroom=100%; source=operator board cap until live vendor meter; reachable when auth is configured; no recent heartbeat rate-limit marker; daily cap remains board-derived | Add a Gemini quota/rate-limit receipt if available. |
| `ollama` | local model presence | binary/model | down until a model is pulled | Pull the configured local model to light the floor lane. |
| `jules` | usage-telemetry proxy | proxy + known cap | usage health=ok; used=0/100 runs; remaining=100; headroom=100%; source=known hard cap; remote async service; no recent heartbeat rate-limit marker; use for remote batch fill | Keep Jules remote-launch receipts and harvest status fresh. |
| `copilot` | assignability probe | reachability | down until Copilot coding agent assignment is confirmed | Enable Copilot coding agent and set LIMEN_COPILOT_ENABLED=1. |
| `warp` | credential presence | credential gate | down until WARP_API_KEY is installed | Install WARP_API_KEY locally and as the workflow secret. |
| `oz` | credential presence | credential gate | down until WARP_API_KEY is installed | Install WARP_API_KEY locally and as the workflow secret. |
| `github_actions` | workflow reachability | reachability | can launch workflow packets; not a local quota meter | Surface queued/running workflow capacity from GitHub checks. |

## Blockers

- `ollama`: /opt/homebrew/bin/ollama; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane
- `warp`: WARP_API_KEY not set (set env var + add as org/repo Actions secret)
- `oz`: WARP_API_KEY not set (set env var + add as org/repo Actions secret)

## Claude

- Binary/path reachable: `True`.
- Remaining capacity: `100000000`.
- Limit: `100000000`.
- Detail: /Users/4jp/Workspace/limen/scripts/shims/claude; live usage meter: remaining=100000000/100000000, consumed=0.

## Contract

- This ledger does not modify tasks, credentials, workflow state, or remote systems.
- Run `python3 scripts/dispatch-health.py --write` for a campaign-heartbeat/operator snapshot, then re-run `python3 scripts/capacity-fill-ledger.py --write` after repairs.

## Commands

- Refresh this ledger: `python3 scripts/capacity-fill-ledger.py --write`
- Refresh campaign heartbeat: `python3 scripts/dispatch-health.py --write`
