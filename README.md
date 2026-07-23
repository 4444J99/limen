# Limen

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

Limen is a cross-agent, cross-repo, budget-capped task intake system. Every AI agent reads a single `tasks.yaml` to discover work. TABVLARIVS is the deterministic state authority and lease keeper. The CLI + SaaS dashboard provide unified visibility, budget management, and lifecycle control across your entire agent fleet.

## Usage

### Install

```bash
#One-liner (clones repo, installs CLI to venv, sets up PATH)
curl -fsSL https://raw.githubusercontent.com/4444J99/limen/main/install.sh | bash
source ~/.zshenv
```

Custom install paths via `LIMEN_SOURCE`, `LIMEN_TARGET`, `LIMEN_LINK`.

Or install via Homebrew from a local checkout:
```bash
brew install ./limen.rb
```

### Quick start

```bash
#Point the CLI at the authenticated conduct owner, then inspect live capabilities
export LIMEN_CONDUCT_URL=https://<authenticated-conduct-endpoint>
#LIMEN_CONDUCT_TOKEN is injected by the credential wall; never commit or paste it.
limen conduct capabilities

#Submit bounded work; the remote keeper owns tasks.yaml projection
limen conduct submit --packet path/to/work-packet.json

#Check readiness and stale claims before dispatching
limen doctor --agent jules
limen release-stale --agent jules --hours 24
limen release-stale --agent jules --hours 24 --apply

#Dispatch open tasks (default: dry-run preview; add --live to run for real)
limen dispatch --agent jules --limit 100
limen dispatch --agent jules --limit 100 --live

#Check the board and budget
limen status

#Inspect partial board progress, source readiness, and work-loan metadata
limen progress
limen progress --view workstream --scope financial --all

#Harvest results from completed dispatches
limen harvest
```

### Run API & Dashboard locally

```bash
#FastAPI backend (port 8000) + Next.js dashboard (port 3000)
docker compose up
```

Mounts `./tasks.yaml` into the API container.

### CLI reference

| Command | Flags | Description |
|---------|-------|-------------|
| `limen init` | `--root`, `--budget` | Retired local bootstrap; fails closed with the authenticated remote-owner hydration instruction. |
| `limen conduct` | `capabilities`, `register`, `submit`, `split`, `graph`, `heartbeat`, `report`, `harvest`, `adopt`, `cancel`, `request-stop` | Use the symmetric authenticated conduct protocol. |
| `limen fanout` | `plan`, `start`, `status`, `harvest` | Plan and run board-independent, remote-first work graphs through the authenticated keeper. |
| `limen dispatch` | `--agent`, `--budget`, `--dry-run/--live`, `--task`, `--limit` | Inspect the local cache and submit eligible lifecycle work to the conduct keeper. |
| `limen release-stale` | `--hours` (default 24), `--agent`, `--dry-run/--apply`, `--json-output`, `--report-file` | Reopen dispatched/in-progress tasks whose latest event is stale. |
| `limen doctor` | `--agent` (default jules), `--json-output`, `--report-file` | Report local readiness for dispatch and stale-claim recovery. |
| `limen qa` | `--agent` (default jules), `--json-output`, `--report-file` | Report QA lifecycle gates and steering queues without mutating tasks. |
| `limen status` | `--agent`, `--status` | Show the task board. |
| `limen progress` | `--view`, `--scope`, `--level`, `--all`, `--json-output`, `--report-file`, `--ascii` | Inspect the partial board-progress and source-coverage lens. |
| `limen harvest` | `--agent` | Check for completed dispatches and update task states. |
| `limen workstream` | `--from`, `--prompt`, `--prompt-file`, `--agent auto\|LANE`, `--conduct`, `--shell` | Create/reuse a repo worktree plus a private agent-neutral `.limen-workstream/README.md` and `kickstart.sh`; optionally register a protected direct conductor session. |

The installer also creates a terminal-neutral shortcut in `~/.local/bin`:

```bash
workstream --prompt "objective and constraints" limen my-workstream
```

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

## Runtime Modes

Limen now has two backend storage modes:

| Mode | Use | Configuration |
|------|-----|---------------|
| Local file | Development and on-demand local operation | `LIMEN_TASKS=/path/to/tasks.yaml` |
| GitHub Contents | Hosted read projection; repository mutations are deferred to TABVLARIVS | `LIMEN_GITHUB_REPO`, `LIMEN_GITHUB_TOKEN`, optional `LIMEN_GITHUB_BRANCH`, `LIMEN_GITHUB_PATH` |

Runtime adapters currently include the Python/FastAPI adapter and the
Cloudflare Worker adapter in `web/worker`. The Worker uses the same HTTP
contract and GitHub Contents storage; it can be checked locally with
`scripts/probe-local-worker.sh`. GitHub-backed adapters never write the default
branch. Mutation requests return a typed, retryable `409` owned by TABVLARIVS;
inline/disposable adapters remain writable for local contract tests.

The Firebase dashboard at `https://device-streaming-067d747a.web.app` is static hosting backed by a deployed Cloudflare Worker runtime:

```text
https://limen-runtime.ivixivi.workers.dev
```

Firebase hosting ships public-safe static shells and public contracts only. Internal, QA, client, readiness, and task-board data load from the runtime after the appropriate bearer token is supplied. The dashboard deploy workflow reads `NEXT_PUBLIC_API_URL` from the repository variable `LIMEN_API_URL`.

Published surfaces:

| Route | Persona | Purpose | Contract |
|-------|---------|---------|----------|
| `/` | owner only | Token-gated internal operations board with full task details and preview controls | `/api/status` |
| `/qa` | owner only | Token-gated QA and steering surface for recovery, verification, assignment, and archive suppression lifecycle gates | `/api/qa-status` |
| `/client` | owner + sanctioned client | Token-gated redacted delivery status, capacity, and active task signal | `/api/client-status` |
| `/public` | public | Aggregate public status only | `/public-status.json` |

Owner/internal users can navigate all dashboards. Client and public personas only
see sanctioned navigation for their disclosure level; the API and static
manifests both declare `sanctioned_personas` for every surface.
Owner manifests list every surface. Client and public manifests are filtered so
non-owner personas do not receive internal or QA surface contracts.

Backend persona enforcement:

| Token | Persona | Access |
|-------|---------|--------|
| `LIMEN_API_TOKEN` or `LIMEN_OWNER_TOKEN` | owner | all internal, QA, task, dispatch, assignment, readiness, and client/public status endpoints |
| `LIMEN_CLIENT_TOKEN` | client | `/api/client-status`, `/api/public-status`, and `/api/surface-manifest` |
| none | public | `/api/public-status`, `/api/surface-manifest`, and `/health` |

If no persona tokens are configured, the API stays in local development mode and
treats requests as owner-scoped.

The QA surface is derived from `tasks.yaml`; it is not a second backlog. Done
items are counted as archive-ready and suppressed from active steering, while
open, active, stale, and failed work is routed into assign, verify, or recover
gates.

Cloud Run API deployment requires billing on the GCP project because Cloud Run,
Secret Manager, Cloud Build, and Artifact Registry cannot be enabled without it.
Before deploying, run the read-only preflight:

```bash
GCP_PROJECT_ID=device-streaming-067d747a bash scripts/preflight-cloud-run.sh
```

The preflight checks billing, required APIs, and the Secret Manager entries
`limen-github-token`, `limen-api-token`, and `limen-client-token`. It does not
enable services or create secrets. When billing is unavailable, use the local CLI
path from the machine that has the Jules CLI:

```bash
limen doctor --agent jules
limen release-stale --agent jules --hours 24
limen release-stale --agent jules --hours 24 --apply
limen dispatch --agent jules --limit 100
limen dispatch --agent jules --limit 100 --live
```

There is also a manual GitHub Actions workflow named `Operate` for no-billing
operations. It supports `doctor`, `qa`, `release-stale-preview`, and
`release-stale-apply`. It does not run live Jules dispatch.

The API exposes the same lifecycle contract at `GET /api/qa-status` when a
backend runtime is attached. On a disposable local/inline board, mutation uses
explicit `POST /api/release-stale` or `POST /api/dispatch` calls. A
GitHub-backed runtime is read-only and owner-routes those requests to
TABVLARIVS instead of committing to `main`. Verification uses
`POST /api/tasks/{task_id}/verify` to move active work to `done` or back into an
attention state with a QA audit entry. Assignment and reprioritization use
`POST /api/tasks/{task_id}/assign`, which records an `assigned` audit entry
before the task returns to the open steering queue. Closure uses
`POST /api/tasks/{task_id}/archive`, which only accepts `done` tasks and changes
them to `archived` so they are suppressed from active steering.

The durable contract is the lifecycle and persona surface model, not a specific
provider. Firebase, Cloud Run, Next.js, and FastAPI are replaceable adapters as
long as internal, client, public, and QA surfaces keep the same sanctions and
task lifecycle semantics.

Adapter drift is checked by `scripts/validate-lifecycle-adapters.py`, which
compares the CLI QA lifecycle against the generated static QA contract from the
same `tasks.yaml`.
Portable JSON Schemas live in `spec/contracts/`; `node scripts/validate-contract-schemas.mjs`
validates generated surface contracts against them.
Runtime adapters can be checked over HTTP with `scripts/probe-runtime-adapter.py`
against any deployed or local API URL; the probe verifies persona sanctions,
manifest filtering, redaction, QA steering shape, and owner-only mutation
boundaries. Optional `--verify-task-id`, `--assign-task-id`, and
`--archive-task-id` flags exercise owner mutations and must only be used with
disposable local/inline boards; GitHub-backed production adapters deliberately
return the TABVLARIVS deferral receipt.
For the current local Python adapter, `scripts/probe-local-runtime.sh` starts a
temporary API process with a disposable task board and runs the same HTTP probe,
including owner verify, assign, and archive mutations.
For the Cloudflare Worker adapter, `scripts/probe-local-worker.sh` does the same
against Wrangler local dev and inline disposable storage.
The dashboard deploy workflow requires the repository variable `LIMEN_API_URL`
and the Actions secrets `LIMEN_API_TOKEN` and `LIMEN_CLIENT_TOKEN`; after
Firebase hosting is released it probes that runtime with the same schema-backed
adapter check.
For a full local contract pass, run `scripts/verify-whole.sh`; set
`LIMEN_VERIFY_LIVE=1` to include live Firebase surface checks. When
`LIMEN_WORKER_URL` or `NEXT_PUBLIC_API_URL`, `LIMEN_API_TOKEN`, and
`LIMEN_CLIENT_TOKEN` are present, the same live pass also schema-probes the
runtime adapter. Set `LIMEN_VERIFY_LIVE_RUNTIME=1` to fail if those runtime
probe inputs are missing.

## How It Works

Every AI agent reads `tasks.yaml` at session start, finds open tasks matching their name, claims one, executes, and writes results back. Budget is tracked per agent and per day — no agent exceeds its allocation.

## Agents

- **Codex, Claude, OpenCode, Agy, Gemini** — local CLI coding lanes, dispatched in isolated worktrees when a local checkout exists.
- **Jules** — async coding agent (Google). Dispatch via `jules new --repo`.
- **Copilot** — GitHub Copilot coding agent lane. Dispatch assigns an existing GitHub issue to `copilot-swe-agent`; census marks it down until `LIMEN_COPILOT_ENABLED=1` or `LIMEN_COPILOT_HEALTH_REPO` confirms assignability.
- **Warp/Oz** — paid service lanes via `LIMEN_WARP_DISPATCH_CMD`, `LIMEN_OZ_DISPATCH_CMD`, or the generic `agent-dispatch` adapter.
- **GitHub Actions** — public verification-only runner lane for a dedicated verifier child after its implementation parent has merged custody; dispatches the live-discovered `LIMEN_GITHUB_ACTIONS_WORKFLOW` (default `limen-agent.yml`) through a validated control branch/tag independently pinned to an exact control SHA.

## Support / Sponsor

Limen and [MONETA](moneta/) — the sovereign Bitcoin licence mint that powers the Pro tiers,
with no payment processor in the path — are free and open source. If this system or its
organs help you, you can support the work here:

- **[GitHub Sponsors](https://github.com/sponsors/organvm)**
- **[Ko-fi](https://ko-fi.com/4444j99)**

Sponsorship funds maintenance of the mint, the task fabric, and the published surfaces;
nothing here is paywalled.

## Links

- [Quickstart](QUICKSTART.md)
- [Schema](SCHEMA.md)
- [Agent Protocol](AGENTS.md)
- [GitHub](https://github.com/4444J99/limen)

## Contact

For questions, issues, and collaboration, visit the [organvm GitHub](https://github.com/4444J99) or open an issue in this repository.
