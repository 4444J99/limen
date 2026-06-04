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
# Reopen stale active claims first; preview before mutation
limen release-stale --agent jules --hours 24
limen release-stale --agent jules --hours 24 --apply

# Dispatch all open Jules tasks
limen dispatch --agent jules --live --limit 100

# Dispatch a specific task
limen dispatch --agent jules --task LIMEN-001

# Dry run (show what would be dispatched)
limen dispatch --agent jules --limit 10
```

## Checking Status

```bash
# Readiness and next actions
limen doctor --agent jules

# QA lifecycle gates and steering queues
limen qa --agent jules

# Full board
limen status

# Filter by agent
limen status --agent jules

# Filter by status
limen status --status open
```

## No-Billing Operations

When Cloud Run is unavailable, use the GitHub Actions `Operate` workflow for
governed board maintenance:

- `doctor` reports readiness without mutation.
- `qa` uploads lifecycle gates and steering queues without mutation.
- `release-stale-preview` lists stale active claims without mutation.
- `release-stale-apply` reopens stale claims and commits `tasks.yaml`.

Live Jules dispatch remains an explicit local/API action, not part of the
workflow.

## Harvesting Results

```bash
# Check all agents for completed tasks
limen harvest --all

# Check a specific agent
limen harvest --agent jules
```

## SaaS Dashboard

The current Firebase dashboard is static hosting:

```text
https://device-streaming-067d747a.web.app
```

It is currently built with this Cloudflare Worker runtime attached:

```text
https://limen-runtime.ivixivi.workers.dev
```

Static hosting displays public-safe shells and public contracts only. Internal,
QA, client, readiness, and task-board data load from the runtime after the
appropriate bearer token is supplied. The GitHub Actions deploy workflow reads
the runtime URL from the repository variable `LIMEN_API_URL` and requires the
Actions secrets `LIMEN_API_TOKEN` and `LIMEN_CLIENT_TOKEN` so the deployed
runtime is schema-probed after Firebase release.

Surfaces:

- `/` token-gated internal operations board.
- `/qa` token-gated QA and steering lifecycle gates.
- `/client` token-gated redacted client delivery status.
- `/public` aggregate public status.

The QA surface is a control layer over the same task lifecycle: recover stale or
failed claims through `POST /api/release-stale`, verify evidence, assign
budgeted work, and archive closed items out of active steering.

Before deploying the hosted API, run the read-only GCP preflight:

```bash
GCP_PROJECT_ID=device-streaming-067d747a bash scripts/preflight-cloud-run.sh
```

It fails early if billing, required APIs, or the `limen-github-token`,
`limen-api-token`, and `limen-client-token` secrets are missing. It does not
enable APIs, create secrets, or deploy anything.

Backend endpoints:

```
GET  /health                Health check
GET  /api/status            Task board + budget
GET  /api/qa-status         QA lifecycle and steering contract
GET  /api/readiness         Runtime readiness and next actions
GET  /api/surface-manifest  Surface/contract manifest
POST /api/dispatch          Preview or dispatch open tasks
GET  /api/tasks/:id         Get task details
POST /api/tasks/:id/verify  Record QA evidence decision and route next lifecycle gate
POST /api/tasks/:id/assign  Assign or reassign task owner, priority, cost, and open status
POST /api/tasks/:id/archive Archive a done task out of active steering
POST /api/release-stale     Preview or reopen stale active tasks
```

The frontend/backend choices are adapters. Keep or replace them based on the
shortest path to the lifecycle contract: sanctioned surfaces, explicit QA gates,
audited assignment, evidence verification, archive suppression, and no extra
manual work for the user.

Probe any attached runtime without caring what framework serves it:

```bash
scripts/verify-whole.sh
LIMEN_VERIFY_LIVE=1 scripts/verify-whole.sh
LIMEN_VERIFY_LIVE=1 LIMEN_VERIFY_LIVE_RUNTIME=1 scripts/verify-whole.sh

scripts/probe-local-runtime.sh
scripts/probe-local-worker.sh

scripts/probe-runtime-adapter.py \
  --api-url http://127.0.0.1:8000 \
  --owner-token "$LIMEN_API_TOKEN" \
  --client-token "$LIMEN_CLIENT_TOKEN"
```

Add `--verify-task-id`, `--assign-task-id`, and `--archive-task-id` only for
disposable or explicitly approved task IDs; those flags perform real owner
mutations.

### Hosted API Storage

For a hosted API, prefer GitHub-backed storage so `tasks.yaml` remains the durable source of truth:

```bash
export LIMEN_GITHUB_REPO=4444J99/limen
export LIMEN_GITHUB_BRANCH=main
export LIMEN_GITHUB_PATH=tasks.yaml
export LIMEN_GITHUB_TOKEN=ghp_...
export LIMEN_API_TOKEN='choose-a-dashboard-token'
export LIMEN_CLIENT_TOKEN='choose-a-client-token'
export LIMEN_CORS_ORIGINS='https://device-streaming-067d747a.web.app'
```

`LIMEN_API_TOKEN` and `LIMEN_OWNER_TOKEN` are owner persona tokens. Owner tokens
can reach internal, QA, task mutation, assignment, dispatch, and readiness
endpoints. `LIMEN_CLIENT_TOKEN` can reach client/public status and the surface
manifest, but receives `403` for owner-only endpoints.

Local development can keep using:

```bash
export LIMEN_TASKS="$PWD/tasks.yaml"
uvicorn main:app --host 127.0.0.1 --port 8000
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
