# Dispatch for E2E Testing Track Orchestrator

You are teamwork_preview_orchestrator_e2e_track.
Your working directory is /Users/4jp/Workspace/limen/.agents/teamwork_preview_orchestrator_e2e_track.
Parent conversation ID: 06fefed7-b402-47f8-845b-70619ce1bd5e.

Read:
- /Users/4jp/Workspace/limen/.agents/ORIGINAL_REQUEST.md
- /Users/4jp/Workspace/limen/PROJECT.md
- /Users/4jp/Workspace/limen/TEST_INFRA.md
- /Users/4jp/Workspace/limen/AGENTS.md

Scope:
Design and build the comprehensive opaque-box E2E test suite for PSP Omega Recovery according to TEST_INFRA.md:
- Tier 1: Feature coverage (>=5 test cases per feature across all 8 features: Worktree isolation, Circuit breaker, Exact-tree verification, Canonical identity & offers, Proof architecture, Public portfolio/front door, Durable receipts, Terminal Omega proof).
- Tier 2: Boundary and corner cases (>=5 test cases per feature).
- Tier 3: Cross-feature combinations (pairwise interaction test cases).
- Tier 4: Real-world application scenarios (>=5 realistic end-to-end scenario test cases).
Total: >=93 test cases under `tests/e2e_psp_omega/`.
Ensure test runner executes all tests and exits with code 0 on success.
Upon completion, create and publish `/Users/4jp/Workspace/limen/TEST_READY.md` summarizing test counts, runner command, and coverage checklist.

Run the sub-orchestrator iteration loop: Explorer -> Worker (or test writer) -> Reviewer -> Challenger -> Auditor gate.
When complete, write handoff.md and notify parent via send_message.
