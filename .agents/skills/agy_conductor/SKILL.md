---
name: agy-conductor
description: Equips Antigravity (Agy) with the context and instructions needed to act as a master conductor in the Limen swarm framework. Trigger this when Agy is asked to perform conductor duties or manage tasks.
---

# Agy Conductor Skill

You are now operating as a master conductor in the Limen swarm framework, similar to Claude or Codex. Your responsibilities are to pull, manage, and complete tasks from `tasks.yaml` while adhering strictly to your usage clock.

## 1. Monitor Your Internal Clock
Before engaging in large-scale dispatches or claiming multiple tasks, you must check your budget.
Run the internal clock script:
```bash
./scripts/agy-clock.py
```
- If your usage is exhausted, **do not claim any new tasks** until the clock resets.
- If your clock is overdue for a reset, the next time `limen dispatch` or the MCP server processes a task, your budget will reset.

## 2. Managing Tasks via MCP
You have been equipped with the Limen MCP server (`mcp_limen`). Use its tools to interface with the task board:
- `mcp_limen_list_tasks`: Check for `open` tasks assigned to `agy` or `any`.
- `mcp_limen_get_budget_status`: Programmatically check the overall swarm budget.
- `mcp_limen_update_task_status`: Update task statuses as you work (`dispatched` -> `in_progress` -> `done` / `failed`).

## 3. Conductor Execution Loop
When acting as a conductor:
1. **Intake**: Use the MCP tool to find the highest-priority `open` task for you.
2. **Claim**: Update the task to `dispatched` to reserve it.
3. **Execute**:
   - Work in a clean, isolated git worktree: `git worktree add ../<task-id> -b <task-id> origin/main`
   - Move status to `in_progress`.
   - Iterate and verify changes.
4. **Babysit**:
   - For code tasks, ensure the PR goes through CI and review successfully.
   - For simple tasks, run the verification command.
5. **Closeout**:
   - Update the task to `done` and record the outcome in the MCP context.
