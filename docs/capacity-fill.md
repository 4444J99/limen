# Capacity Fill

Generated: `2026-07-02T20:56:34+00:00`
Status: `blocked`

## Capacity Census

| Agent | Kind | Reachable | Remaining | Limit | Detail |
|---|---|---|---|---|---|
| `codex` | local-cli | `up` | 24 | 100 | /opt/homebrew/bin/codex |
| `claude` | local-cli | `up` | 100 | 100 | /opt/homebrew/bin/claude |
| `opencode` | local-cli | `up` | 83 | 100 | /opt/homebrew/bin/opencode |
| `agy` | local-cli | `up` | 86 | 100 | /opt/homebrew/bin/agy |
| `gemini` | local-cli | `up` | 10 | 10 | /opt/homebrew/bin/gemini |
| `ollama` | local-cli | `down` | 393 | 600 | /opt/homebrew/bin/ollama; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane |
| `jules` | cloud-cli | `down` | 0 | 100 | /opt/homebrew/bin/jules |
| `copilot` | github-issue | `down` | 393 | 600 | /opt/homebrew/bin/gh; copilot-swe-agent not confirmed assignable (set LIMEN_COPILOT_ENABLED=1 after enabling Copilot coding agent) |
| `warp` | paid-service | `down` | 393 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `oz` | paid-service | `down` | 393 | 600 | WARP_API_KEY not set (set env var + add as org/repo Actions secret) |
| `github_actions` | github-actions | `up` | 393 | 600 | /opt/homebrew/bin/gh; workflow=limen-agent.yml |

## Blockers

- `ollama`: /opt/homebrew/bin/ollama; no model pulled — run `ollama pull qwen2.5-coder:7b` to light the floor lane
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
