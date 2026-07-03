# Capacity Fill

Generated: `2026-07-03T06:18:10+00:00`
Status: `blocked`

## Capacity Census

| Agent | Kind | Reachable | Remaining | Limit | Detail |
|---|---|---|---|---|---|
| `codex` | local-cli | `up` | 20 | 100 | /opt/homebrew/bin/codex |
| `claude` | local-cli | `up` | 100 | 100 | /opt/homebrew/bin/claude |
| `opencode` | local-cli | `up` | 82 | 100 | /opt/homebrew/bin/opencode |
| `agy` | local-cli | `up` | 86 | 100 | /opt/homebrew/bin/agy |
| `gemini` | local-cli | `up` | 10 | 10 | /opt/homebrew/bin/gemini |
| `ollama` | local-cli | `down` | 388 | 600 | /opt/homebrew/bin/ollama; no model pulled; local disk pressure blocks qwen2.5-coder:7b pull (20.5 GiB free, need >= 50 GiB) |
| `jules` | cloud-cli | `down` | 0 | 100 | /opt/homebrew/bin/jules |
| `copilot` | github-issue | `down` | 388 | 600 | /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent) |
| `warp` | paid-service | `down` | 388 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `oz` | paid-service | `down` | 388 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `github_actions` | github-actions | `up` | 388 | 600 | /opt/homebrew/bin/gh; workflow=limen-agent.yml |

## Signal Quality

| Agent | Signal | Trust | Use | Next Build |
|---|---|---|---|---|
| `codex` | transcript-token estimate | estimate | usable for pacing; tune cap against plan status | Calibrate OpenAI plan pool cap from a trusted account meter. |
| `claude` | transcript-token estimate | estimate | usable for pacing; rate-limit events still dominate stop decisions | Calibrate Claude plan pool cap from a trusted account meter. |
| `opencode` | db-meter | measured | best local paid-lane signal when the DB clock is present | Keep opencode-clock fresh from the SQLite usage DB. |
| `agy` | dispatch-count proxy | proxy | reachable, but not proof of provider quota | Add a provider-backed Agy meter or recent rate-limit receipt. |
| `gemini` | dispatch-count proxy | proxy | reachable when auth is configured; daily cap remains board-derived | Add a Gemini quota/rate-limit receipt if available. |
| `ollama` | local model presence | binary/model | down until a model is pulled | Clear local disk pressure before pulling qwen2.5-coder:7b; current free space is 20.5 GiB. |
| `jules` | dispatch-count cap | known cap | down locally until CLI/service path is available | Restore Jules CLI/service reachability. |
| `copilot` | assignability probe | reachability | down until Copilot coding agent assignment is confirmed | Enable Copilot coding agent and set LIMEN_COPILOT_ENABLED=1. |
| `warp` | credential presence | credential gate | down until WARP_API_KEY is installed | Install WARP_API_KEY locally and as the workflow secret. |
| `oz` | credential presence | credential gate | down until WARP_API_KEY is installed | Install WARP_API_KEY locally and as the workflow secret. |
| `github_actions` | workflow reachability | reachability | can launch workflow packets; not a local quota meter | Surface queued/running workflow capacity from GitHub checks. |

## Blockers

- `ollama`: /opt/homebrew/bin/ollama; no model pulled; local disk pressure blocks qwen2.5-coder:7b pull (20.5 GiB free, need >= 50 GiB)
- `jules`: /opt/homebrew/bin/jules
- `copilot`: /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent)
- `warp`: WARP_API_KEY not set (set env var + add as org/repo Actions secret)
- `oz`: WARP_API_KEY not set (set env var + add as org/repo Actions secret)

## Claude

- Binary/path reachable: `True`.
- Remaining capacity: `100`.
- Limit: `100`.
- Detail: /opt/homebrew/bin/claude.

## Contract

- This ledger does not modify tasks, credentials, workflow state, or remote systems.
- Run `python3 scripts/dispatch-health.py --write --probe-async` for a heartbeat/operator snapshot, then re-run `python3 scripts/capacity-fill-ledger.py --write` after repairs.

## Commands

- Refresh this ledger: `python3 scripts/capacity-fill-ledger.py --write`
- Refresh dispatch heartbeat: `python3 scripts/dispatch-health.py --write --probe-async`
