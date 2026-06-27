# Limen Project Context and Integration Patterns

This file is the Gemini/conductor adapter guide. It does not redefine task states, budget rules,
or dispatch ownership; those live in `AGENTS.md` and `mcp/src/limen_mcp/server.py`.

## Conductor Swarm MCP Integration

The primary agent swarm (`conductor`) is configured to use the Limen MCP server for real-time task intake and management. The MCP server is implemented in Python using FastMCP and located in the `mcp/` directory.

### Available Tools

The MCP server exposes the following tools for the conductor swarm:
- `list_tasks`: Retrieves the current list of tasks from the pipeline.
- `get_task`: Fetches details of a specific task by its ID (e.g., LIMEN-001).
- `add_task`: Adds a new task to the pipeline.
- `update_task_status`: Updates the status of an existing task (e.g., to `dispatched`, `in_progress`, `done`). The canonical state set is defined in `AGENTS.md` → **Task States** and enforced by the MCP server (`VALID_STATUSES`); there is no `completed` state.
- `get_budget_status`: Checks the current daily budget and usage to prevent over-burn.

### Workflow & Best Practices

1. **Task Intake**: Agents should poll `list_tasks` or accept a `get_task` assignment. Normal agents claim only `open` tasks. A `dispatched` task is already reserved; the conductor or scheduler may create a `dispatched` assignment for a named downstream agent, and that agent should move it to `in_progress` when execution begins.
2. **Budget Enforcement**: Before picking up or executing large tasks, agents MUST call `get_budget_status` to ensure there is sufficient budget remaining for the day. Do not proceed if the daily budget is exhausted.
3. **Status Updates**: As work progresses, use `update_task_status` to keep the pipeline state accurate. This directly reflects in the dashboard via the sync pipeline. Append evidence for every transition; do not overwrite prior history.
4. **Task Consistency**: Ensure any new tasks added via `add_task` maintain the `LIMEN-XXX` ID format and include the relevant GitHub URL (`urls` array) to prevent duplicates.

## Execution Protocols

### 1. Worktree Isolation
Instead of cloning or checking out branches in the main repository checkout, the Conductor Swarm MUST spawn tasks in isolated git worktrees.
- **Command Pattern:** `git fetch origin && git worktree add ../<task-id> -b <task-id> origin/main`
- **Rationale:** Ensures parallel tasks managed by the swarm do not conflict in the shared working directory.
- **Path Safety:** If `../<task-id>` already exists, do not reuse it blindly. Reuse only when it is the same task and clean; otherwise create a uniquely suffixed worktree path from the task ID and short timestamp/commit.
- **CRITICAL — always branch from `origin/main`, never from local HEAD.** Omitting the base ref (`git worktree add ../<id> -b <id>`) branches from whatever the live checkout currently points at. If the live checkout has drifted onto a stale topic branch, every new worktree inherits that stale base — and because the CAPTURE organ auto-commits the working tree to whatever branch is checked out, while squash-merges land work on `main` under new hashes, those forks silently accrete commits and *look* "ahead" of `main` while actually being far behind it. That is exactly how a thicket of stale-base forks accumulated (incident 2026-06-26: ~20 worktrees, the live daemon itself stranded on a stale fork). Always `git fetch origin` first and pass `origin/main` as the explicit base.

### 2. PR Babysitting Loop (End-to-End Lifecycle)
The agent responsible for a task will NOT just push its code and exit. It is explicitly required to babysit the pull request through the entire review lifecycle:
1. **Open PR:** Use the GitHub tool to `create_pull_request`. Open as draft if known gates are still failing; mark ready only when local predicates pass or the task explicitly asks for an exploratory PR.
2. **Watch Status:** Poll `pull_request_read` (methods: `get_status` and `get_check_runs`) with bounded backoff to monitor CI checks until they resolve. Use the task budget or CI timeout as the stop condition; if checks do not resolve, update the task to `failed_blocked` or `needs_human` with the last observed status.
3. **Address Comments:** Poll `pull_request_read` (method: `get_review_comments`). If comments appear, apply the requested fixes to the isolated worktree, commit, and push again.
4. **Merge:** Once CI passes and all review comments are resolved, invoke `merge_pull_request`.
5. **Report & Sync:** Document the successful merge, update `tasks.yaml` via MCP (`update_task_status` to `done`), and notify the necessary stakeholders. Include PR URL, merge commit, checks observed, and any follow-up task IDs.
