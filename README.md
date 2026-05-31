# Limen

Universal agent task intake — one file to aim every AI agent across every repo.

Limen is a cross-agent, cross-repo, budget-capped task intake system. It lives in a single `tasks.yaml` that every agent reads, and provides a CLI + SaaS dashboard for managing the pipeline.

## Quick Start

```bash
curl -sSL https://raw.githubusercontent.com/4444J99/limen/main/install.sh | bash
limen init
limen add --title 'Refactor auth' --repo my-org/my-repo --agent jules
limen dispatch --agent jules --live
limen status
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `limen init` | Initialize a portal in the current directory |
| `limen add` | Add a new task (interactive or flags) |
| `limen dispatch` | Claim open tasks and dispatch to agents |
| `limen status` | Show the task board with budget tracking |
| `limen harvest` | Collect results from completed agent runs |
| `limen sync` | Sync with the SaaS API |

## Architecture

```
tasks.yaml (source of truth)
    │
    ├── limen CLI (dispatch → harvest → status)
    │
    ├── Agent fleet (Jules, Gemini, Claude, OpenCode)
    │
    └── SaaS API + Dashboard (optional)
```

## How It Works

Every AI agent reads `tasks.yaml` at session start, finds open tasks matching their name, claims one, executes, and writes results back. Budget is tracked per agent and per day — no agent exceeds its allocation.

## Agents

- **Jules** — async coding agent (Google). 100 runs/day budget. Dispatch via `jules new --repo`.
- **Gemini** — interactive CLI agent. Executes in-session.
- **Claude** — interactive agent. Reads tasks.yaml on session start.
- **OpenCode** — CLI coding agent. Supports `--task <id>` for targeted dispatch.

## Links

- [Quickstart](QUICKSTART.md)
- [Schema](SCHEMA.md)
- [Agent Protocol](AGENTS.md)
- [GitHub](https://github.com/4444J99/limen)
