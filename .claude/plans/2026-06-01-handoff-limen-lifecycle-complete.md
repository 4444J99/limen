# Agent Handoff: Limen Lifecycle Architecture Complete

**From:** Session 00462416 | **Date:** 2026-06-01 | **Phase:** ARCHITECTURE_STABILIZED

## Current State
The Limen pipeline has transitioned from a rigid push-system to a resilient, self-regulating organism. The defense-in-depth architecture is fully deployed, and the dashboard provides full transparency into the new autonomous lifecycle.

### Key Components
- **Limen MCP Server:** Resilient Python/FastMCP server with git-rebase conflict resolution, circuit breakers, hard loop limits (3x), and persistent state in `~/.mcp_state.json`.
- **Autonomous Auto-Scaler:** GitHub Action running every 4h to maintain 100-task depth in `tasks.yaml` from `jules-ready` issues.
- **Dashboard UI:** React/Next.js dashboard implementing the **EXPLORE > PLAN > BUILD > VERIFY > LEARN > REPEAT** lifecycle with completion progress bars and expandable accordion rows.
- **GEMINI.md:** System instructions updated to enforce **Worktree Isolation** and **PR Babysitting Lifecycle** protocols.

## Completed Work
- [x] **Defense-in-Depth:** Implemented git pull-rebase wrappers in MCP server to prevent state corruption.
- [x] **Safety Locks:** Implemented circuit breaker (trip/reset) and hard execution-loop limits to protect budget.
- [x] **State Persistence:** MCP metrics and breakers now survive restarts via `.mcp_state.json`.
- [x] **UI Lifecycle:** Overhauled dashboard to visualize the 6-phase lifecycle and hyperlinked every element to GitHub.
- [x] **Protocol Codification:** Formally documented worktree and PR babysitting rules in `GEMINI.md`.
- [x] **Verification:** Completed full Verification Loop; dashboard builds and server logic is confirmed robust.

## Key Decisions
| Decision | Rationale |
|----------|-----------|
| **Decoupled tasks.yaml from deploy.yml** | To prevent high-frequency agent activity from triggering Firebase 429 rate limits. Relying on hourly cron for UI sync. |
| **In-Memory Rewrite after Pull-Rebase** | Instead of `git stash pop` which can fail with conflicts, the MCP server stashes, rebases, then overwrites `tasks.yaml` from its valid in-memory Pydantic model. |
| **Worktree Isolation** | Mandated `git worktree` for all swarm tasks to enable safe parallel execution without shared directory collisions. |
| **8x Multiplier Cap** | Capped the dynamic failure multiplier to prevent tasks from becoming mathematically un-pickable while still providing an immune response. |

## Critical Context
- **MCP Path:** `mcp/src/limen_mcp/server.py`.
- **State Path:** `~/.mcp_state.json` (Internal tracking for task loops and circuit breaker).
- **Dashboard URL:** `device-streaming-067d747a.web.app`.
- **Swarm Mandate:** Agents are now instructed to "babysit" PRs. This means they do not close their session until the PR is merged or CI fails definitively.

## Next Actions
1. **Trigger Dispatch:** Initiate a batch of 10 tasks through the swarm using the new `git worktree` pattern.
2. **Monitor "VERIFY" Tab:** Observe agents responding to CI failures or comments on the dashboard.
3. **Pheromone Pruning:** Implement the 'Learn' phase logic where successful patterns are extracted from `done` tasks and injected into future `context`.

## Risks & Warnings
- **16GB RAM Constraint:** Running >6 concurrent `git worktree` agents on this machine may cause swapping/instability.
- **Stash Pop Risks:** The MCP server no longer pops stashes during sync to avoid conflict markers; ensure any manual edits to `tasks.yaml` are committed before the server runs.
