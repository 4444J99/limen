# Limen — Engineering Report

**Status:** live with demonstrated use
**Authorship:** Human and Multi-Agent Orchestration
**Evidence anchors:** https://github.com/organvm/limen

### The expensive problem
Enterprise organizations struggle to reliably coordinate autonomous agent swarms to deliver deterministic, high-quality, durable code. Existing multi-agent frameworks fail because they rely on unverified probabilistic outputs or lack robust lifecycle and error-handling constraints, leading to unpredictable loops and stranded work.

### What was built
Limen is a deterministic, multi-agent continuous integration and orchestration system. It wraps probabilistic agent models in strict execution constraints, forcing every mutation to pass scoped verification and durable homing protocols before it can be merged. 

### Decisions and tradeoffs
1. **Isolated Worktrees**: Rejected multi-agent collaboration on a single branch due to collision risk. Each agent is forced to operate in an isolated Git worktree, submitting PRs to the broker.
2. **Deterministic Verification**: Rejected LLM-based self-evaluation for completion. Limen requires an exact-tree verification via `scripts/verify-scoped.sh` before allowing merges, ensuring that probabilistic models are constrained by deterministic rules.
3. **Receipt-based Handoffs**: Rejected context-window passing for state. Instead, agents must leave durable receipts in the repository (`RunReceiptV1`), providing immutable evidence of completion.

### The verification story
Every autonomous action is gated by the conduct broker. Completion is enforced by the execution of a defined `predicate` against an exact Git head. If `scripts/verify-scoped.sh` passes, a receipt is generated, linking the exact head, predicate, exit code, and artifact digest. Failure modes (like `swap-fraction` overload) are caught and returned as `blocked_external`, cleanly aborting the loop rather than retrying blindly.

### What it proves about the method
Limen demonstrates that probabilistic models can safely perform complex multi-step delivery if they are bound by rigorous lifecycle constraints, exact-tree verification, and durable receipts.

### Current state and honest limits
Limen is live and orchestrating autonomous workflows across multiple repositories. However, its task-board parsing is heavily tied to its specific `tasks.yaml` projection layer, and its rigorous constraints can occasionally lead to quarantine loops if a required artifact is fundamentally blocked by the environment.

### Doors
- **Deploy the Broker**: Integrate the `limen conduct` CLI into your orchestrator.
- **Join the Swarm**: Contribute new agent workflows.
