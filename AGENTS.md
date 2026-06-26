# Limen Agent Protocol

**Read this file on every session start.** This file tells you where to find work,
how to claim it, and how to report results.

> How this file relates to `CLAUDE.md`, `GEMINI.md`, and the ecosystem-wide `ORGANVM:AUTO`
> layer — and why there is no separate "agent-all" repo — is documented in
> [`docs/agent-instruction-standard.md`](docs/agent-instruction-standard.md).

---

## Startup Checklist (fast path)

1. **Identify** yourself — set `LIMEN_AGENT` (`claude | gemini | jules | opencode | codex | copilot | goose`).
2. **Read** `$LIMEN_ROOT/tasks.yaml` (fallback `./tasks.yaml`) — parse the budget and the full task list.
3. **Claim** the highest-priority `open` task targeted at you (or `any`) that fits the remaining budget.
4. **Update status** before (`dispatched` → `in_progress`) and after (`done` / `failed`) execution.
5. **Verify** before reporting `done` — run the repo's predicate (here: `scripts/verify-whole.sh`).
6. **Close out** — release stale claims back to `open`, restore budget, commit `tasks.yaml`.

Each step is detailed below.

## Precedence

When instructions conflict, the higher rule wins:

1. System / developer / runtime constraints (the harness)
2. The human's explicit instructions for this session
3. `tasks.yaml` — the single source of truth for task **state**
4. This file (`AGENTS.md`) — the cross-agent dispatch **protocol**
5. Tool-specific charters (`CLAUDE.md`, `GEMINI.md`) — per-agent behavior
6. General repository docs (`README.md`, `docs/**`)

`tasks.yaml` is authoritative for *state*; `AGENTS.md` is authoritative for *protocol*. Where a
tool charter restates a rule from this file, this file is the source of truth.

## Task States

The canonical state set lives in code — `VALID_STATUSES` in `mcp/src/limen_mcp/server.py` — and
this table is verified against it by `scripts/check-agent-docs.py` (wired into `verify-whole.sh`).
Do not invent states.

| State | Meaning |
|-------|---------|
| `open` | Available to claim |
| `dispatched` | Claimed by an agent, not yet executing |
| `in_progress` | Actively being worked |
| `done` | Completed successfully |
| `failed` | Attempted, did not succeed — retryable |
| `failed_blocked` | Stopped by an external blocker (billing / auth / infra) |
| `needs_human` | Cannot proceed without a human action |
| `archived` | Closed and suppressed from active steering |

Normal flow: `open → dispatched → in_progress → done → archived`. From `in_progress` a task may
instead move to `failed`, `failed_blocked`, or `needs_human`. A stale `dispatched`/`in_progress`
claim is released back to `open` (see Session End Ritual). There is **no** `completed` state — use `done`.

## Where to Find Tasks

```bash
# Path is always:
$LIMEN_ROOT/tasks.yaml

# Fallback if env var is unset:
./tasks.yaml
```

## Session Start Ritual

Execute in order:

### 1. Identify Yourself

```bash
# Limen needs to know which agent you are. Set if not already:
export LIMEN_AGENT="${LIMEN_AGENT:-$(basename $0)}"
# Expected values: claude | gemini | jules | opencode | codex | copilot | goose
```

### 2. Read the Task File

Read `$LIMEN_ROOT/tasks.yaml` (or `./tasks.yaml` if unset). Parse the full file. Pay
attention to:
- `portal.budget.track` — how much budget has been spent today
- `portal.budget.per_agent.<your_name>` — your per-agent cap
- The `tasks` list — all pending and in-progress work

### 3. Find Available Tasks

Filter for tasks matching ALL of:
```
target_agent == "<your_name>" OR target_agent == "any"
AND status == "open"
AND budget_cost <= remaining_daily_budget
```

Sort by priority: `critical > high > medium > low > backlog`.

### 4. If No Tasks Found

Report: "No pending tasks in limen for `<your_name>`."
Then run: `limen status` to show the full board (if CLI installed), or just exit.

### 5. Claim a Task

Pick the highest-priority task. Update `tasks.yaml`:

```yaml
# Change this:
  - id: "LIMEN-001"
    status: open

# To this:
  - id: "LIMEN-001"
    status: dispatched
    updated: "<now>"  # ISO-8601 UTC, e.g. 2026-05-31T10:30:00Z
    dispatch_log:
      - timestamp: "<now>"  # ISO-8601 UTC, e.g. 2026-05-31T10:30:00Z
        agent: "<your_name>"
        session_id: "<current_session_id>"
        status: dispatched
```

Also decrement the daily budget:
```yaml
portal:
  budget:
    track:
      spent: <previous + budget_cost>
      per_agent:
        <your_name>: <previous + budget_cost>
```

### 6. Execute

Begin work on the task. When you start actual execution (not just planning), update
status to `in_progress`.

### 7. Report Results

On completion:
```yaml
  - id: "LIMEN-001"
    status: done
    updated: "<now>"
    dispatch_log:
      - timestamp: "<now>"
        agent: "<your_name>"
        session_id: "<current_session_id>"
        status: done
        output: "<summary of what was done, files changed, outcomes>"
```

On failure:
```yaml
  - id: "LIMEN-001"
    status: failed
    updated: "<now>"
    dispatch_log:
      - timestamp: "<now>"
        agent: "<your_name>"
        session_id: "<current_session_id>"
        status: failed
        output: "<what went wrong, why it failed>"
```

---

## Session End Ritual

### 1. Release Stale Claims

For any tasks you have in `dispatched` status (claimed but not completed):
```yaml
  - id: "LIMEN-001"
    status: open
    updated: "<now>"
```

Also restore the budget those tasks consumed.

### 2. Commit and Push

If `$LIMEN_ROOT` is a git repo, commit and push `tasks.yaml`:
```bash
git -C "$LIMEN_ROOT" add tasks.yaml
git -C "$LIMEN_ROOT" commit -m "limen: update task states"
git -C "$LIMEN_ROOT" push
```

## SaaS Deployment (Production)

When deploying the SaaS stack, set these env vars on the web API:

| Variable | Required | Description |
|----------|----------|-------------|
| `LIMEN_API_TOKEN` | Yes | Bearer token for API auth |
| `LIMEN_ROOT` | Yes | Path to limen root on disk |
| `LIMEN_TASKS` | No | Alternative path to tasks.yaml |

For the Next.js dashboard, set `NEXT_PUBLIC_API_URL` to the API endpoint (defaults to `http://localhost:8000`).

### Railway (API)

```bash
railway login
railway init
railway up
```

### Vercel (Dashboard)

```bash
vercel login
vercel --prod
```

---

## Agent-Specific Notes

### Claude
- You are Claude. Read this file as part of your startup instructions.
- You have access to the full filesystem — `$LIMEN_ROOT/tasks.yaml` is a regular file.
- Support `limen` as a subagent: when asked, run the limen CLI or read/write tasks.yaml directly.

### Gemini
- You are Gemini CLI (v0.44.1+). Read `$LIMEN_ROOT/tasks.yaml` at session start.
- Use `--sandbox $LIMEN_ROOT` if you need repo context.
- You do not have background async dispatch — you claim and execute in the same session.
- Your per-agent budget is tracked separately from Jules.

### Jules
- You are Jules (Google async coding agent). You do not have interactive sessions.
- Your dispatch is managed by `limen dispatch --agent jules` or the scheduler.
- Read `tasks.yaml` to understand the task queue; your harvest cycle checks results.
- You are the workhorse: 100 runs/day budget is primarily allocated to you.

### OpenCode
- You are OpenCode. Read `$LIMEN_ROOT/tasks.yaml` at session start.
- Support `--task <id>` flag for targeted dispatch to a single task.
- Write results back to tasks.yaml on completion.

---

## Quick Reference

| Action | Command |
|---|---|
| Read tasks | `cat $LIMEN_ROOT/tasks.yaml` |
| Claim a task | Edit `status: open` → `status: dispatched` in tasks.yaml |
| Report done | Edit `status: dispatched` → `status: done` + add output |
| Show board | `limen status` (if CLI installed) |
| Dispatch | `limen dispatch --agent <name> --live` |
| Harvest | `limen harvest --agent <name>` |
| Init new | `limen init --root <path>` |
| Sync with SaaS | `limen sync` |
