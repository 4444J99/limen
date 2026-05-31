# Limen Agent Protocol

**Read this file on every session start.** This file tells you where to find work,
how to claim it, and how to report results.

---

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
    updated: "2026-05-31T10:30:00Z"
    dispatch_log:
      - timestamp: "2026-05-31T10:30:00Z"
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
