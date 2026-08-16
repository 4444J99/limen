# E2E Test Suite Specification (Features 1–4): Handoff Report

**Agent:** teamwork_preview_explorer_e2e_1  
**Working Directory:** `/Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_e2e_1`  
**Parent ID:** `1de93b40-afd7-4994-824e-895814f42697`  
**Date:** 2026-08-15  

---

## 1. Observation

Directly observed the following codebase implementations, schemas, and test infrastructures across Features 1 through 4:

1. **Feature 1 (Worktree Isolation & Topic Branches):**
   - File `cli/src/limen/worktree_initialization.py:16-19`:
     ```python
     WORKTREE_INITIALIZATION_SCHEMA = "limen.worktree_initialization.v1"
     InitializationState = Literal["staging", "validated", "moving", "published", "crashed"]
     InitializationPhase = Literal["preflight", "add", "validate-staging", "move", "validate-final"]
     ```
   - Lines `202-277`: Staging checkout validation checks `head == expected_head`, `branch == branch_name`, `index_tree == head_tree`, zero cached diff, zero working diff, and zero untracked paths via `git status --porcelain=v1 -z`. Crashes record typed crash receipts to `<common_git_dir>/limen-worktree-initialization/<key>.json` without deleting the dirty root.
   - File `cli/src/limen/worktree_roots.py:69-89`: `default_worktrees_root()` falls back to `/Volumes/Scratch/limen-worktrees` or `<workdir>/.limen-worktrees`, and `effective_worktree_root()` checks `LIMEN_WORKTREE_ROOT`.

2. **Feature 2 (Review-Loop Circuit Breaker & Quarantine):**
   - File `mcp/src/limen_mcp/server.py:213-246`:
     ```python
     CIRCUIT_BREAKER_TRIPPED = False
     TASK_LOOP_TRACKER: Dict[str, int] = {}
     STATE_FILE = Path.home() / "Workspace" / "limen" / ".mcp_state.json"
     ```
   - Lines `369-384`: `trip_circuit_breaker()` sets `CIRCUIT_BREAKER_TRIPPED = True`, saves state to `.mcp_state.json`, and returns `"Circuit breaker TRIPPED. System offline."`. `reset_circuit_breaker()` sets it to `False` and returns `"Circuit breaker RESET. System online."`.
   - Lines `519-524`: In `get_task(task_id)`:
     ```python
     TASK_LOOP_TRACKER[task_id] = TASK_LOOP_TRACKER.get(task_id, 0) + 1
     _save_state()
     if TASK_LOOP_TRACKER[task_id] > 3:
         raise ValueError(
             f"HARD LOOP LIMIT REACHED: Task {task_id} requested >3 times today. Moving to 'needs_human'. Abandon task immediately."
         )
     ```
   - Lines `393, 401, 409, 417, 425, 438, 456, 469, 477, 485, 493, 502, 516, 574, 633, 683, 701, 727, 851`: Every MCP tool invokes `_check_circuit_breaker()`, raising `RuntimeError("SYSTEM OFFLINE - GO TO SLEEP...")` when tripped.

3. **Feature 3 (Single-Push Exact-Tree Verification):**
   - File `scripts/verify-scoped.sh:14`: `exec python3 "$ROOT/scripts/verify.py" --changed "$@"`.
   - File `scripts/verify.py:785-836`: `cmd_changed()` validates exact merge-base ancestor for `--integration`, fails closed if `--require-base` cannot resolve merge-base or changed set is empty, and guards against private history leaks (`private_history_leak()`) and unvalidated custody version reversions (`transient_custody_reversion()`).
   - Lines `534-635`: `run_command()` spawns gates in a new process group session (`start_new_session=True`), drains I/O without blocking, enforces `--gate-output-bytes` ceiling, terminates runaway processes with `terminate_process_group()`, and returns bare exit codes (0 on success, 1 on test failure, 124 on timeout, 125 on output limit/cleanup failure, 130 on cancel).
   - Lines `870-957`: Executes gates in tiered waves: `cheap` parallel wave, then machine-wide `heavy_admission` lease for `heavy` wave, then machine-wide `fcntl.flock` for `serialized` tail.

4. **Feature 4 (Canonical Identity & 4-Tier Offers):**
   - File `institutio/positioning/commercial-contract.yaml:1-19, 149-195, 403-587`:
     - Schema: `limen.positioning_commercial_contract.v1`.
     - Canonical Identity: Title = `"Production-systems architect"`, Headline = `"I build production systems that solve expensive problems."`, Authorship = `"Architected and directed by one person through a governed, multi-agent production system."`.
     - 4-Tier Offers:
       - `audit` (Diagnose, Primary Entry, Read-Only, 2-3 weeks, `fixed_scope_decision_fee`, `RANGE-AUDIT`, private anchor $5k-$15k).
       - `install` (Implement, Primary Expansion, Bounded-Write, 4-8 weeks, `milestone_fixed_scope`, `RANGE-INSTALL`, private anchor $25k-$60k).
       - `retainer` (Sustain, Primary Continuity, Advisory with named changes, `capacity_reservation`, `RANGE-RETAINER`, private anchor $10k-$25k/mo).
       - `partnership_review` (Diligence, Secondary Only, Diligence-Only, `negotiated_after_diligence`, `RANGE-PARTNERSHIP`, non-public CTA, requires `HG-OPERATOR-TERMS`).
     - Economics Boundary: `public_price: prohibited`; all numeric fees strictly banned from public copy and repository artifacts.
   - File `docs/positioning/narrative-ladder.md:10-93`: Progressive disclosure levels L1 (10 seconds), L2 (5 minutes), and L3 (Diligence index).

---

## 2. Logic Chain

1. **From Observation 1 to Worktree Isolation Test Specification:**
   - Because `initialize_worktree()` follows a strict 5-phase crash-visible lifecycle with atomic renames and untracked file assertions, the Tier 1 tests must verify the successful transition across all phases (`preflight` -> `published`) and clean checkout status.
   - Because failures record `state="crashed"` to `<common_git_dir>/limen-worktree-initialization/<key>.json` without deleting the dirty staging directory, the Tier 2 tests must inject faults (existing destination collision, existing branch collision, untracked staging file, crash after rename, cross-filesystem device mismatch) and assert that `WorktreeInitializationError` is raised, state is recorded as crashed, and dirty roots are preserved for the abandonment reaper.

2. **From Observation 2 to Circuit Breaker & Quarantine Test Specification:**
   - Because MCP tools check global `CIRCUIT_BREAKER_TRIPPED` persisted in `.mcp_state.json`, Tier 1 tests must verify `trip_circuit_breaker()`, `reset_circuit_breaker()`, and state reload across process restarts.
   - Because `get_task()` tracks per-task access and raises `ValueError("HARD LOOP LIMIT REACHED...")` when count > 3, Tier 1 tests must verify loop tracking and threshold tripping.
   - Tier 2 tests must evaluate boundary cases: corrupted non-JSON `.mcp_state.json`, unwritable filesystem permissions, malformed task IDs (`""`, `../escape`), multi-threaded concurrent access, and mid-execution trip events.

3. **From Observation 3 to Single-Push Verification Test Specification:**
   - Because `scripts/verify.py` selects gates from `gates.yaml` based on changed files and executes them in tiered waves (`cheap` -> `heavy` -> `serialized`), Tier 1 tests must verify changed set computation, registry gate selection, tiered execution, and bare exit code preservation.
   - Because `--require-base` and `--integration` enforce strict ancestor matching and security leak prevention, Tier 2 tests must verify failure-closed behavior on unresolvable merge-bases, empty PR diffs, non-ancestor bases, committed private history leaks (`.limen-private/`), command timeouts, and stdout flooding.

4. **From Observation 4 to Canonical Identity & Offer Test Specification:**
   - Because `commercial-contract.yaml` is the single source of truth for identity, progressive disclosure (L1/L2/L3), 4-tier offers, qualification routing, and symbolic economic ranges, Tier 1 tests must validate semantic integrity, qualification scenarios, and generated markdown alignment.
   - Because public copy strictly prohibits numeric rates ($5k, 25k, etc.) and private paths, Tier 2 tests must inject numeric prices, private filesystem paths, unsupported superlatives, and unauthorized public partnership CTAs, asserting that validators fail closed.

---

## 3. Caveats

- **No Caveats on Features 1–4 Scope:** The codebase implementations for Features 1–4 are fully inspectable, concrete, and covered by existing production scripts and contracts.
- **Out of Scope for this Explorer:** Features 5 through 8 (Proof Architecture, Public Front Door, Durable Receipts, Terminal Omega Proof) and Tiers 3–5 (Pairwise Combinations, Scenario E2E, Adversarial Hardening) are assigned to separate explorer and implementer tracks in Milestone E2E.
- **Read-Only Constraint:** In accordance with the Explorer archetype role, no production code was modified. Complete test specifications and architecture designs are delivered in `analysis.md` and this handoff.

---

## 4. Conclusion

- A total of **48 test specifications** (24 Tier 1 Feature Coverage tests + 24 Tier 2 Boundary & Corner Case tests, 6 per feature across Features 1–4) have been fully designed and documented.
- All test specifications include exact test names, inputs, assertions, error handling expectations, and sandboxing strategies (hermetic git repositories, isolated mock MCP state files, temporary gate registries, and contract fixtures).
- The test suite is organized under `tests/e2e_psp_omega/tier1_features/` and `tests/e2e_psp_omega/tier2_boundaries/`, executable via standard `python3 -m unittest discover` with bare exit code semantics.

---

## 5. Verification Method

Independent verification of the analysis and findings:

1. **Verify Report Files:**
   ```bash
   cat /Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_e2e_1/analysis.md
   cat /Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_e2e_1/handoff.md
   ```

2. **Verify Codebase Ground Truth:**
   - Worktree initialization: `python3 -m pytest cli/tests/test_worktree_initialization.py`
   - MCP Server & Circuit Breaker: `python3 -m pytest cli/tests/test_mcp_server.py`
   - Gate Resolver: `python3 scripts/verify.py --explain docs/positioning/narrative-ladder.md`
   - Commercial Contract & Offers: `python3 scripts/tests/positioning-commercial-contract.test.py` and `python3 scripts/tests/positioning-offer-artifacts.test.py`

3. **Invalidation Conditions:**
   - Modification of `limen.worktree_initialization.v1` schema or phases in `cli/src/limen/worktree_initialization.py`.
   - Changing the circuit breaker error message or loop threshold (`TASK_LOOP_TRACKER > 3`) in `mcp/src/limen_mcp/server.py`.
   - Changing gate selection logic or tier structure in `scripts/verify.py` or `gates.yaml`.
   - Changing the 4-tier offer ladder or private anchor IDs in `institutio/positioning/commercial-contract.yaml`.
