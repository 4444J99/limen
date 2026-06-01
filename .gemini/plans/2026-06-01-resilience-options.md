# Limen Pipeline Resilience Options
**Date:** 2026-06-01
**Context:** Mitigation strategies derived from Expansive Inquiry and Premortem (Pipeline Decapitation).

Below are the 5 core vulnerabilities identified, with at least 3 architectural options to resolve each.

---

## 1. Concurrency & Git Conflicts (The Shattering Glass)
*The Problem:* The auto-scaler (GitHub Action) and the Conductor swarm (local MCP server) both read/write to the flat `tasks.yaml` file. Concurrent writes will cause fatal Git merge conflicts and paralyze the pipeline.

**Options:**
*   **Option 1.1: The Retry-Rebase Wrapper (Lightweight)**
    *   *Mechanism:* Modify the MCP `update_task_status` tool to execute a strict `git pull --rebase` retry loop with exponential backoff before every `git push`.
    *   *Pros:* No architectural changes; keeps `tasks.yaml` as the single source of truth.
    *   *Cons:* Does not eliminate the underlying race condition entirely; Git operations are slow and add friction to the agent loop.
*   **Option 1.2: Sharded State Directory (Structural)**
    *   *Mechanism:* Abandon the single `tasks.yaml` file. Create a directory `tasks/` where every task is its own file (e.g., `tasks/LIMEN-015.yaml`).
    *   *Pros:* Git handles directory-level file additions/modifications flawlessly. Concurrent updates to different tasks will never conflict.
    *   *Cons:* Requires refactoring the dashboard build script and MCP tools to aggregate files on read.
*   **Option 1.3: Dedicated Synchronization Queue (The Lehr)**
    *   *Mechanism:* The swarm never pushes to Git directly. Agents update a local SQLite DB or simple FIFO queue. A separate, single-threaded background process (The Annealer) reads the queue and safely commits changes to Git in batches.
    *   *Pros:* Completely solves the concurrency problem; protects Git history from being spammed with microscopic commits.
    *   *Cons:* Adds a new daemon process to manage.

---

## 2. The Zombie Queue (Dependency Poisoning)
*The Problem:* Tasks that require missing infrastructure (e.g., PyPI token, CF KV namespace) are labeled `jules-ready` but are unsolvable. They sit in the 100-task queue, get picked up, fail, and return, eventually starving the pipeline.

**Options:**
*   **Option 2.1: `failed_blocked` Eviction Protocol**
    *   *Mechanism:* Give the MCP server a tool to mark tasks as `failed_blocked`. This removes the task from the active 100-count, un-labels it on GitHub, and ignores it in future fetches.
    *   *Pros:* AI self-manages the queue; easy to implement.
    *   *Cons:* Requires the agent to correctly identify *why* it failed (auth vs. logic).
*   **Option 2.2: Time-To-Live (TTL) Eviction (Pheromone Evaporation)**
    *   *Mechanism:* If a task cycles between `dispatched` and `in_progress` without completing for 48 hours, a cron job forcibly evicts it back to the GitHub backlog and pulls a fresh task.
    *   *Pros:* Failsafe against *any* type of zombie task, whether from bad infrastructure or bad agent logic.
    *   *Cons:* Might prematurely kill legitimately hard tasks that just take time.
*   **Option 2.3: Pre-flight Infrastructure Gates**
    *   *Mechanism:* `tasks.yaml` gains a `requires: [pypi, kv_namespace]` array. The auto-scaler checks local environment variables before adding the task to the queue. If dependencies are missing, the task is skipped.
    *   *Pros:* Prevents zombies from ever entering the pipeline.
    *   *Cons:* Requires manually categorizing all GitHub issues with dependency labels.

---

## 3. Runaway Budget Drain (The Ouroboros / Cytokine Storm)
*The Problem:* A stubborn task (e.g., persistent TS error) causes an agent to loop, burning through the 100-run daily budget on a single issue and killing the pipeline for the day.

**Options:**
*   **Option 3.1: Hard Execution-Loop Limits**
    *   *Mechanism:* The MCP server tracks the number of times `get_task` or `update_task_status` is called for a specific ID in a 24-hour period. If > 3, it rejects the request and forces the task to `needs_human`.
    *   *Pros:* Absolute protection against runaway loops.
    *   *Cons:* Hard limits might interrupt an agent just as it's about to solve the problem.
*   **Option 3.2: Dynamic Budget Costing (Immunosuppressant)**
    *   *Mechanism:* The `budget_cost` of a task doubles every time an agent picks it up after a failure (1 -> 2 -> 4 -> 8). Agents are prompted to abandon tasks if the cost outweighs the value.
    *   *Pros:* Economic incentive for the swarm to self-regulate.
    *   *Cons:* Relies on the LLM honoring the economic logic rather than a hard physical block.
*   **Option 3.3: Context Pruning (Amnesia Injection)**
    *   *Mechanism:* After 2 failed attempts, the MCP tool explicitly wipes the agent's context of the prior failures, forcing it to look at the codebase fresh.
    *   *Pros:* Breaks the hallucination "ant mill" death spiral.
    *   *Cons:* Destroys potentially useful learning from the previous failures.

---

## 4. API Rate Limits (Icarus / Saturation Diving)
*The Problem:* The auto-scaler pushes every status update. `deploy.yml` triggers a Firebase deploy on every push. 100 tasks x 3 status changes = 300 deployments/day, triggering a 429 Too Many Requests ban.

**Options:**
*   **Option 4.1: Decoupled Batch Deployments (Decompression Chamber)**
    *   *Mechanism:* Modify `deploy.yml` to remove the `push` trigger for `tasks.yaml`. Rely entirely on the hourly `cron` schedule to sync the dashboard.
    *   *Pros:* Guarantees max 24 deployments a day. Zero rate limit risk.
    *   *Cons:* The dashboard is no longer real-time (up to 1 hour latency).
*   **Option 4.2: Debounced GitHub Actions Middleware**
    *   *Mechanism:* Use a GitHub Action debouncer (or `workflow_run`). When a push hits `main`, it waits 15 minutes. If more pushes arrive, the timer resets. It only deploys when the swarm takes a break.
    *   *Pros:* Near real-time when activity stops; prevents rapid-fire deployments.
    *   *Cons:* Complex CI/CD configuration.
*   **Option 4.3: Local-First Client-Side Rendering**
    *   *Mechanism:* Stop generating `tasks.json` at build time. Have the React app fetch `tasks.yaml` directly from the raw GitHub URL on page load.
    *   *Pros:* Zero backend deployments needed for data changes.
    *   *Cons:* Shifts API rate limit risk to the user's browser hitting GitHub.

---

## 5. Lack of Graceful Degradation (Severed Umbilical)
*The Problem:* When API providers (GitHub, Anthropic, GCP) go down or ban the account, the pipeline doesn't pause—it shatters, spewing errors, corrupting state, or getting IP banned for retry spam.

**Options:**
*   **Option 5.1: The Circuit Breaker Protocol**
    *   *Mechanism:* If the MCP server detects HTTP 429 (Rate Limit) or 401 (Auth) from GitHub, it trips a "Circuit Breaker" state. All agent tools immediately return "SYSTEM OFFLINE - GO TO SLEEP".
    *   *Pros:* Protects the account from permanent bans due to automated spam.
    *   *Cons:* Requires manual intervention to reset the breaker.
*   **Option 5.2: Bailout Bottle (Local LLM Fallback)**
    *   *Mechanism:* If the primary Conductor model (e.g., Claude) fails, the MCP server orchestrates a fallback to a local model (Ollama) strictly with the instruction: "Save your state, push to a WIP branch, and terminate."
    *   *Pros:* Zero data loss; fully graceful shutdown.
    *   *Cons:* Requires keeping a local LLM in memory, eating into the 16GB RAM constraint.
*   **Option 5.3: Mocked Flight Simulator Mode**
    *   *Mechanism:* If disconnected from production APIs, the MCP server intercepts all mutating commands (`git push`, `firebase deploy`) and mocks success, logging the actions to a local `.offline_ledger` to be replayed later.
    *   *Pros:* Agents can continue local code analysis and test fixing even if GitHub is down.
    *   *Cons:* High complexity to sync the `.offline_ledger` when the network returns.