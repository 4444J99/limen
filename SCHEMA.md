# Limen Schema — Universal Agent Task Intake

**Version 1.0**

Limen is a specification for a single YAML file that any AI agent (Claude, Gemini,
Jules, Codex, Copilot, Goose, etc.) can read on session start to discover what work
needs doing, claim a task, execute it, and report the result. It is the universal
threshold — one file to aim every agent you have.

---

## 1. Env-Var Contract

All paths and configuration come from environment variables. No hardcoded paths.

| Variable | Required | Default | Description |
|---|---|---|---|
| `LIMEN_ROOT` | yes | — | Path to the directory containing `tasks.yaml` |
| `LIMEN_BUDGET` | no | `100` | Daily run budget cap |
| `LIMEN_AGENT` | no | *(auto-detect)* | Which agent this session is (`claude`, `gemini`, `jules`, `opencode`, `codex`, `copilot`, `goose`) |
| `LIMEN_API_KEY` | no | — | API key for SaaS sync (optional) |
| `LIMEN_API_TOKEN` | no | — | Bearer token required by the FastAPI backend when set |
| `LIMEN_OWNER_TOKEN` | no | — | Additional owner persona bearer token for all sanctioned endpoints |
| `LIMEN_CLIENT_TOKEN` | no | — | Client persona bearer token for client/public status and manifest endpoints |
| `LIMEN_REPO` | no | — | Git remote URL (optional, enables `limen sync`) |
| `LIMEN_TASKS` | no | `$LIMEN_ROOT/tasks.yaml` | Path to the task file |
| `LIMEN_GITHUB_REPO` | no | — | `owner/repo` for hosted API storage via GitHub Contents |
| `LIMEN_GITHUB_BRANCH` | no | `main` | Branch used by hosted API GitHub storage |
| `LIMEN_GITHUB_PATH` | no | `tasks.yaml` | Path to the task YAML in the GitHub repo |
| `LIMEN_GITHUB_TOKEN` | no | — | GitHub token with contents read/write access for hosted API storage |
| `LIMEN_CORS_ORIGINS` | no | `*` | Comma-separated browser origins allowed to call the API |

Auto-detection: `$LIMEN_AGENT` is set from `$CLAUDE_NAME` (Claude), `$GEMINI_NAME` (Gemini),
or falls back to the basename of the calling process.

---

## 2. Tasks File Format (`tasks.yaml`)

### 2.1 Top-Level Structure

```yaml
version: "1.0"
portal:
  name: string                  # Human-readable portal name
  description: string           # Purpose of this intake
  budget:
    daily: integer              # Total daily run budget (default 100)
    unit: string                # Budget unit, usually "runs"
    per_agent:                  # Per-agent daily caps (optional)
      <agent>: integer          # e.g. jules: 100, gemini: 10

tasks:
  - # Task entry (see 2.2)
```

### 2.2 Task Entry Schema

```yaml
- id: string                    # Unique ID, e.g. "LIMEN-001"
  title: string                 # Concise task description
  description: string           # Detailed description (optional)
  repo: string                  # Target repo "owner/name" (optional)
  type: string                  # Task type: code | audit | docs | review | research | config | chore
  target_agent: string          # "jules" | "gemini" | "claude" | "any" | "opencode" | "codex" | "copilot" | "goose"
  priority: string              # critical | high | medium | low | backlog
  budget_cost: integer          # How many runs this consumes (default 1)
  origin: string                # obligation | human_prompt | agent_recommendation | system_debt
  horizon: string               # past | present | future
  value_case: string            # Explicit forecast value bought by this work loan
  owner_surface: string         # Durable repo, issue, or other accountable owner surface
  external_deadline: boolean    # True only when an external obligation owns the date
  due_at: date | datetime       # Required when external_deadline is true
  predicate: string             # One executable completion predicate
  receipt_target: string        # Durable GitHub or repository-owned terminal receipt
  status: string                # See 2.3 State Machine
  labels: string[]              # Free-form labels (optional)
  urls: string[]                # Reference URLs (issue links, PRs, docs) (optional)
  context: string               # Brief context for the agent (optional)
  created: date                 # ISO 8601 date
  updated: date                 # ISO 8601 date (optional, updated on state change)
  dispatch_log:                 # History of dispatch attempts (optional)
    - timestamp: datetime       # ISO 8601 datetime
      agent: string             # Agent that claimed it
      session_id: string        # Agent session/run ID
      status: string            # dispatched | in_progress | done | failed
      output: string            # Summary of result (optional)
```

### 2.3 State Machine

```
                  ┌─────────┐
                  │  open   │
                  └────┬────┘
                       │ agent claims task
                       ▼
               ┌──────────────┐
               │  dispatched  │
               └──────┬───────┘
                      │ agent starts work
                      ▼
               ┌──────────────┐
               │ in_progress  │
               └──┬───────┬───┘
                  │       │
         completed│       │failed
                  ▼       ▼
            ┌──────┐ ┌────────┐
            │ done │ │ failed │
            └──────┘ └────────┘
                  ▲
                  │
           ┌───────────┐
           │ cancelled │ (manual only)
           └───────────┘
```

**Timeout rule**: Any task in `dispatched` or `in_progress` for >24h is automatically
reset to `open` on next `limen dispatch` run. Stale claims expire.

### 2.4 Budget Tracking

```yaml
budget:
  daily: 100
  unit: "runs"
  per_agent:
    jules: 100
    gemini: 10
  track:
    date: "2026-05-31"
    spent: 0
    per_agent:
      jules: 0
      gemini: 0
```

Budget resets daily. Each task's `budget_cost` is subtracted from the daily budget
when status transitions to `dispatched`. If budget is exhausted, `dispatch` skips
remaining open tasks until the next day.

---

## 3. AGENTS.md Protocol

Every repo that uses Limen should include (or reference) an `AGENTS.md` file
containing the following protocol. Agents read this on session start.

### 3.1 Session Start Ritual

```
1. Read $LIMEN_ROOT/tasks.yaml (or tasks.yaml in repo root)
2. Filter tasks by:
   - status == "open"
   - target_agent == <your_name> OR target_agent == "any"
   - budget_cost <= remaining daily budget
3. Sort by priority (critical > high > medium > low > backlog)
4. If no tasks found: report "No pending tasks in limen" and exit
5. Pick the highest-priority task
6. Transition task status to "dispatched":
   - Set status: "dispatched"
   - Append to dispatch_log:
       timestamp: <now>
       agent: <your_name>
       session_id: <current session ID>
       status: "dispatched"
7. Begin work on the task
8. On start of actual work: update status to "in_progress"
9. On completion:
   - Set status: "done"
   - Append to dispatch_log:
       status: "done"
       output: <brief summary of what was done>
10. On failure:
    - Set status: "failed"
    - Append dispatch_log entry with status: "failed" and reason
```

### 3.2 Session End Ritual

```
1. If any tasks are in "dispatched" status (claimed but no completion/failure):
   - Reset them to "open" (session ended without finishing)
2. Commit and push tasks.yaml if under git
```

### 3.3 Agent-Specific Notes

| Agent | Flag | Notes |
|---|---|---|
| **Claude** | `claude` | Reads `$LIMEN_ROOT/AGENTS.md` on session start. Supports `claude tasks.yaml` for file access. |
| **Gemini** | `gemini` | Reads via `gemini -p "read $LIMEN_ROOT/tasks.yaml..."`. Supports `--sandbox` for repo context. |
| **Jules** | `jules` | Async/background. Reads tasks.yaml but dispatches independently. Harvest phase checks results. |
| **OpenCode** | `opencode` | Reads `$LIMEN_ROOT/tasks.yaml` directly. Supports `opencode --task <id>` for targeted dispatch. |
| **Codex** | `codex` | Via CLI. Supports `codex -p "process tasks.yaml..."`. |
| **Copilot** | `copilot` | Via `gh copilot`. Limited CLI integration. |
| **Goose** | `goose` | Via `goose run`. Supports `--instruction` flag for task prompt. |

---

## 4. Dispatch Lifecycle

### 4.1 Local Dispatch (`limen dispatch`)

```
limen dispatch [--agent <name>] [--budget <n>] [--dry-run] [--live]
```

1. Read `tasks.yaml`
2. Filter open tasks matching `--agent` (or all if omitted)
3. Apply budget cap (`--budget` or `$LIMEN_BUDGET` or portal daily budget)
4. Sort by priority
5. For each task:
   a. Mark `dispatched` with agent + timestamp
   b. Call `agent-dispatch <agent> "do: <task.title> in <task.repo>"` (or equivalent)
   c. Log in `dispatch_log`
   d. Spend from budget
6. Write updated `tasks.yaml`

### 4.2 Remote Dispatch (Jules Async)

```
limen dispatch --agent jules --live
```

Follows the Jules dispatch pattern: sends to the Jules cloud fleet asynchronously.
Results are harvested later via `limen harvest`.

### 4.3 Harvest (`limen harvest`)

```
limen harvest [--agent <name>]
```

1. For Jules: reads `session-meta/scheduler/jules/harvest/` for completed session diffs
2. For Gemini: checks Gemini CLI for completed sessions
3. For Claude: checks Claude CLI for completed tasks
4. For each completion:
   a. Update task status to `done` or `failed`
   b. Append dispatch_log with output
5. Write updated `tasks.yaml`

### 4.4 Status (`limen status`)

```
limen status [--agent <name>] [--status <state>]
```

Prints a table of tasks filtered by agent and/or status. Shows:
- Task ID, title, priority, status, agent, repo, budget
- Daily budget used/remaining
- Timeline of recent dispatches

### 4.5 QA and Steering Contract

Limen exposes a derived lifecycle contract for QA and assignment steering. This
contract is generated from `tasks.yaml`; it does not create a second work list.

Static hosting writes:

```
/qa-status.json
```

Portable JSON Schemas for the generated contracts live in `spec/contracts/`:

- `surface-manifest.schema.json`
- `qa-status.schema.json`
- `status-summary.schema.json`
- `readiness.schema.json`

Run `node scripts/validate-contract-schemas.mjs` after generating static data to
validate the current JSON contracts against those schemas.

The CLI exposes the same lifecycle report:

```
limen qa [--agent <name>] [--json-output] [--report-file <path>]
```

The FastAPI backend exposes:

```
GET /api/qa-status
POST /api/tasks/{task_id}/verify
POST /api/tasks/{task_id}/assign
POST /api/tasks/{task_id}/archive
```

Contract shape:

```yaml
status: ok | degraded
surface: qa
generated_at: datetime
lifecycle:
  total: integer
  assign: integer          # open work ready for budgeted dispatch
  verify: integer          # active work or PR-linked work needing evidence
  recover: integer         # stale, failed, blocked, or human-needed work
  archive_ready: integer   # done work suppressed from active steering
  archived: integer        # terminal work already suppressed from steering
steering:
  principle: string
  next_batch: task_lifecycle[]
  qa_queue: task_lifecycle[]
  recovery_queue: task_lifecycle[]
  assignment_queue: task_lifecycle[]
  archive_queue: task_lifecycle[]
mechanisms:
  - id: release-stale | qa-verify | assign-next | archive-done
    label: string
    agent: string
    command: string
    mode: string
    count: integer
```

Surface manifests must declare audience sanctions:

```yaml
surfaces:
  - id: internal
    persona: owner
    sanctioned_personas: [owner]
  - id: qa
    persona: owner
    sanctioned_personas: [owner]
  - id: client
    persona: client
    sanctioned_personas: [owner, client]
  - id: public
    persona: public
    sanctioned_personas: [owner, client, public]
```

Owner users can see every dashboard. Client and public personas must only see
navigation and contracts sanctioned for their disclosure level.

Persona manifests:

- `owner-surface-manifest.json` / owner API response: internal, QA, client, public.
- `client-surface-manifest.json` / client API response: client, public.
- `surface-manifest.json` and `public-surface-manifest.json` / public API response: public only.

Backend authorization must enforce the same sanctions:

| Persona | Token source | Allowed API surface |
|---|---|---|
| owner | `LIMEN_API_TOKEN` or `LIMEN_OWNER_TOKEN` | all endpoints |
| client | `LIMEN_CLIENT_TOKEN` | `/api/client-status`, `/api/public-status`, `/api/surface-manifest`, `/health` |
| public | no token | `/api/public-status`, `/api/surface-manifest`, `/health` |

`qa-status` must not expose dispatch logs, task context, or raw task URLs. It
may expose task IDs, titles, repos, assignees, statuses, priorities, lifecycle
phase, stale flags, issue/PR presence booleans, and latest event timestamps.

Verification is an explicit QA operation. `POST /api/tasks/{task_id}/verify`
accepts active or attention work and records the QA decision as `done`,
`needs_human`, `failed`, or `failed_blocked`. A `done` result moves the task to
the archive-ready gate; attention results return it to recovery steering.

Assignment is an explicit steering operation. `POST /api/tasks/{task_id}/assign`
may update `target_agent`, `priority`, `budget_cost`, `status`, `predicate`,
`receipt_target`, `origin`, `horizon`, `value_case`, `owner_surface`,
`external_deadline`, and `due_at`, and appends an `assigned` dispatch-log entry
for audit. It does not dispatch work by itself.

Archive is the terminal closure operation. `POST /api/tasks/{task_id}/archive`
only accepts tasks whose status is `done`, changes them to `archived`, appends
an `archived` audit entry, and suppresses them from active steering queues.

---

## 5. Directory Layout

```
<LIMEN_ROOT>/
├── tasks.yaml              # Universal task intake (source of truth)
├── AGENTS.md               # Protocol for agents to read
├── .env.template           # Env-var configuration template
├── SCHEMA.md               # This specification
├── cli/                    # CLI implementation (Python/Go/Node)
│   ├── limen               # Entry point script
│   ├── pyproject.toml      # Python package config
│   └── ...                 # Source files
├── web/                    # SaaS platform (optional)
│   ├── api/                # Backend API
│   └── app/                # Frontend dashboard
└── .github/                # GitHub templates, CI, etc.
```

---

## 6. Extension Points

### 6.1 Custom Agent Adapters

Add new agents by extending `$LIMEN_ROOT/agents.yaml`:

```yaml
agents:
  my-agent:
    detect: "which my-agent"
    dispatch: "my-agent --task {id} --repo {repo} --prompt '{title}'"
    harvest: "my-agent status {id}"
    budget_key: "my_agent"
```

### 6.2 Custom Task Types

Define custom task types in the portal header:

```yaml
portal:
  task_types:
    code: "Write or modify source code"
    audit: "Review existing code or config for issues"
    docs: "Create or update documentation"
    review: "Review a PR or proposal"
    research: "Investigate a topic and report findings"
    config: "Update configuration files"
    chore: "Maintenance tasks (deps, cleanup, CI)"
```

### 6.3 Webhook Callbacks

Optional: configure a webhook URL for real-time task state changes:

```yaml
portal:
  webhook: "https://api.limen.dev/webhook"
```

Posted on every state transition with the full task payload.

---

## 7. Versioning

The SCHEMA version (`version` field in tasks.yaml) follows SemVer.

- **Major**: breaking changes to the task schema or protocol
- **Minor**: backward-compatible additions (new fields, new task types)
- **Patch**: clarifications and bug fixes to the spec

Schema version `1.x` is stable. The spec file (`SCHEMA.md`) is the authoritative
reference; implementations must document which schema version they support.
