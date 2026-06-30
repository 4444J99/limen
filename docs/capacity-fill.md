# Capacity Fill

Generated: `2026-06-30T14:25:28+00:00`
Status: `blocked`

## Capacity Census

| Agent | Kind | Reachable | Remaining | Limit | Detail |
|---|---|---|---|---|---|
| `codex` | local-cli | `up` | 99 | 100 | /opt/homebrew/bin/codex |
| `claude` | local-cli | `up` | 100 | 100 | /Users/4jp/.local/bin/claude |
| `opencode` | local-cli | `up` | 99 | 100 | /opt/homebrew/bin/opencode |
| `agy` | local-cli | `up` | 95 | 100 | /opt/homebrew/bin/agy |
| `gemini` | local-cli | `down` | 10 | 10 | gemini auth not configured |
| `ollama` | local-cli | `down` | 543 | 600 | /usr/local/bin/ollama; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane |
| `jules` | cloud-cli | `up` | 50 | 100 | /opt/homebrew/bin/jules |
| `copilot` | github-issue | `down` | 543 | 600 | /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent) |
| `warp` | paid-service | `down` | 543 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `oz` | paid-service | `down` | 543 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `github_actions` | github-actions | `up` | 543 | 600 | /opt/homebrew/bin/gh; workflow=limen-agent.yml |

## Blockers

- `gemini`: gemini auth not configured
- `ollama`: /usr/local/bin/ollama; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane
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
