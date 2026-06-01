# Limen Pipeline Resilience Plan: Defense-in-Depth Architecture
**Date:** 2026-06-01
**Methodology:** Ideal Form Logic / Defense-in-Depth ("All of the above")

Rather than selecting single points of failure, the ideal form dictates a layered, defense-in-depth architecture where proactive, structural, and reactive measures compound to create absolute resilience.

## 1. Concurrency & Git Conflicts (The Shattering Glass)
*Objective: Eliminate race conditions during concurrent swarm operations.*
* **Layer 1 (Immediate/Reactive):** Modify the MCP `update_task_status` tool to execute a `git pull --rebase` retry loop with exponential backoff before every `git push`.
* **Layer 2 (Structural/Ideal):** Shard `tasks.yaml` into a `tasks/` directory where each task is its own file (`tasks/LIMEN-015.yaml`). Git handles directory-level concurrency natively.
* **Layer 3 (Proactive):** The MCP server aggregates the sharded files on read (`list_tasks`) to maintain the unified API for the swarm.

## 2. The Zombie Queue (Dependency Poisoning)
*Objective: Prevent blocked tasks from starving the 100-task queue.*
* **Layer 1 (Proactive):** Pre-flight gates. The auto-scaler (`auto-scale.yml`) checks for necessary infrastructure markers (e.g., `requires-pypi`) before pulling the issue from GitHub.
* **Layer 2 (Agent-Driven):** Introduce the `failed_blocked` status. The MCP server allows agents to explicitly evict tasks they determine are unsolvable due to missing dependencies.
* **Layer 3 (Systemic Backstop):** TTL Eviction. A cron job sweeps the `tasks/` directory and automatically evicts any task stuck in `in_progress` for >48 hours (Pheromone Evaporation).

## 3. Runaway Budget Drain (The Ouroboros / Cytokine Storm)
*Objective: Protect the daily execution budget from infinite agent loops.*
* **Layer 1 (Economic):** Dynamic Budget Costing. The `budget_cost` of a task increments on each retry, signaling to the agent via prompt context that the task is becoming too expensive.
* **Layer 2 (Cognitive Reset):** Context Pruning. After 2 failed attempts, the MCP tool explicitly wipes the agent's context of the prior failures, breaking the hallucination ant-mill.
* **Layer 3 (Physical Limit):** Hard Loop Limits. The MCP server physically rejects `get_task` if requested >3 times in 24h for the same ID, forcing the task to `needs_human`.

## 4. API Rate Limits (Icarus / Saturation Diving)
*Objective: Prevent infrastructure bans from hyperactive state updates.*
* **Layer 1 (Decoupling):** Remove the `tasks.yaml` push trigger from `.github/workflows/deploy.yml`. 
* **Layer 2 (Batching):** Rely on the hourly `cron` schedule to sync the dashboard, ensuring a maximum of 24 predictable deployments per day.
* **Layer 3 (Client-Side Augmentation):** In the future, the React app can be augmented to fetch individual task JSONs directly from GitHub raw URLs for real-time updates without triggering a full Firebase build.

## 5. Lack of Graceful Degradation (Severed Umbilical)
*Objective: Ensure the system pauses safely instead of shattering when external APIs fail.*
* **Layer 1 (The Circuit Breaker):** If the MCP server detects HTTP 429/401 from GitHub or LLM providers, it trips a breaker. All agent tools return "SYSTEM OFFLINE - GO TO SLEEP".
* **Layer 2 (Bailout Bottle):** Before sleeping, the MCP server instructs the active agent to save its local state/diffs to a `wip/bailout` branch.
* **Layer 3 (Recovery):** A human operator (or a heartbeat cron) manually resets the circuit breaker once the API storm has passed.