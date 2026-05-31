# Limen Quickstart

Universal agent task intake — one file to aim every AI agent across every repo.

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/4444J99/limen/main/install.sh | bash
```

Or via pip (coming soon):

```bash
pip install limen
```

Or via Homebrew (coming soon):

```bash
brew install limen
```

## Setup

```bash
# Initialize limen in the current directory
limen init

# Or set the root explicitly
export LIMEN_ROOT=~/limen
limen init --root $LIMEN_ROOT
```

## Adding Tasks

```bash
# Add a task for Jules
limen add --title "Fix TypeScript errors" --repo owner/repo --agent jules --priority high --cost 2

# Add a documentation task
limen add --title "Write API docs" --repo owner/repo --agent gemini --priority medium --cost 1
```

## Dispatching Tasks

```bash
# Dispatch all open Jules tasks
limen dispatch --agent jules --live

# Dispatch a specific task
limen dispatch --agent jules --task LIMEN-001

# Dry run (show what would be dispatched)
limen dispatch --agent jules
```

## Checking Status

```bash
# Full board
limen status

# Filter by agent
limen status --agent jules

# Filter by status
limen status --status open
```

## Harvesting Results

```bash
# Check all agents for completed tasks
limen harvest --all

# Check a specific agent
limen harvest --agent jules
```

## SaaS Dashboard

When deployed, access the web dashboard at `https://limen.app`:

```
GET  /health          Health check
GET  /api/status      Task board + budget
POST /api/dispatch    Create/dispatch a task
GET  /api/tasks/:id   Get task details
```

## Budget Management

Each agent has a daily budget. Limen tracks spend per agent:

```yaml
# tasks.yaml
portal:
  budget:
    daily: 100
    per_agent:
      jules: 100
      gemini: 10
    track:
      date: "2026-05-31"
      spent: 6
      per_agent:
        jules: 6
        gemini: 0
```

## File Format

Tasks live in `tasks.yaml`:

```yaml
tasks:
  - id: LIMEN-001
    title: "Fix TypeScript errors in public-record-data-scrapper"
    repo: a-organvm/public-record-data-scrapper
    type: code
    target_agent: jules
    priority: high
    budget_cost: 2
    status: open
    labels: [bug, typescript]
    urls:
      - https://github.com/a-organvm/public-record-data-scrapper/issues/236
    context: "Fix missing deps + recharts/resizable version drift."
    created: "2026-05-31"
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────┐
│  tasks.yaml │────▶│  limen CLI   │────▶│  Agents  │
│  (source    │     │  dispatch/   │     │  (Jules, │
│   of truth) │◀────│  harvest/    │◀────│  Gemini, │
└─────────────┘     │  status      │     │  Claude) │
                    └──────────────┘     └──────────┘
                           │
                    ┌──────▼──────┐
                    │  SaaS API   │
                    │  Dashboard  │
                    └─────────────┘
```
