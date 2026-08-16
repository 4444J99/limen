# E2E Test Suite Specification: PSP Omega Features 1–4 (Tier 1 & Tier 2)

**Author:** teamwork_preview_explorer_e2e_1  
**Milestone:** E2E Testing Track (PSP Omega Recovery)  
**Target Test Directory:** `tests/e2e_psp_omega/`  
**Date:** 2026-08-15  

---

## 1. Executive Summary & Problem Boundary

This document establishes the comprehensive, opaque-box and grey-box test specifications for **Features 1 through 4** of the PSP Omega Recovery program:
1. **Feature 1: Worktree Isolation & Topic Branches** — Transactional setup under `/Users/4jp/Workspace/.worktrees/`, topic branch naming (`limen-psp-omega-lane-*`), atomic moves, clean status validation, crash-visible journals, and lifecycle independence.
2. **Feature 2: Review-Loop Circuit Breaker & Quarantine** — MCP circuit breaker trip/reset mechanics (`.mcp_state.json`), review-loop detection (`TASK_LOOP_TRACKER > 3`), runaway PR quarantine (C04 #2414, C05 #139), and unblocking of independent lanes.
3. **Feature 3: Single-Push Exact-Tree Verification** — Scoped push gate execution (`scripts/verify-scoped.sh`, `scripts/verify.py`), exact merge-base and HEAD matching (`--require-base`, `--integration`), tiered concurrent gate execution (cheap/heavy/serialized), bounded output/timeout process containment, and bare exit code preservation.
4. **Feature 4: Canonical Identity & 4-Tier Offers** — Production-systems architect narrative validation, 3-tier progressive disclosure (L1 10s, L2 5m, L3 diligence), 4-tier offer ladder (`audit`, `install`, `retainer`, `partnership_review`), private pricing anchor boundaries ($5k–$15k, $25k–$60k, $10k–$25k/mo, partnership), qualification routing, and anti-leak validation.

The test suite covers:
- **Tier 1 (Feature Coverage):** 24 distinct test specifications (6 per feature, exceeding the ≥5 requirement).
- **Tier 2 (Boundary & Corner Cases):** 24 distinct test specifications (6 per feature, exceeding the ≥5 requirement).
- Total test specifications specified: **48 test cases**.

---

## 2. Codebase Investigation & Ground Truth Evidence

### 2.1 Feature 1: Worktree Isolation & Topic Branches
- **Primary Source Code:**
  - `cli/src/limen/worktree_initialization.py` (lines 1–286): Implements `initialize_worktree()` with `WORKTREE_INITIALIZATION_SCHEMA = "limen.worktree_initialization.v1"`.
  - `cli/src/limen/worktree_roots.py` (lines 1–432): Implements root derivation (`default_worktrees_root()`, `effective_worktree_root()`) and discovery across dispatch roots, repo-local worktrees, and scratch roots.
  - `cli/src/limen/worktree_abandonment.py` (lines 1–820): Implements recoverable same-filesystem `quarantine_path()` and atomic metadata capture.
  - `cli/src/limen/worktree_debt.py` & `scripts/reclaim-worktrees.py`: Lifecycle accounting and disposal.
- **Key Mechanics Observed:**
  1. *Phased Lifecycle:* `preflight` -> `add` -> `validate-staging` -> `move` -> `validate-final` -> `published`.
  2. *Crash Visibility:* Any failure preserves the staging or published root and writes `state="crashed"` to `<common-git-dir>/limen-worktree-initialization/<sha256>.json`. No silent destructive cleanup.
  3. *Validation Predicates:* Validates `HEAD == expected_head`, `branch == symbolic_ref`, `index_tree == head_tree`, zero cached diff, zero working diff, zero untracked files (`git status --porcelain -z`), and same-filesystem `st_dev` invariant.

### 2.2 Feature 2: Review-Loop Circuit Breaker & Quarantine
- **Primary Source Code:**
  - `mcp/src/limen_mcp/server.py` (lines 213–247, 368–384, 513–531):
    - `CIRCUIT_BREAKER_TRIPPED` global state persisted in `.mcp_state.json` (`STATE_FILE = Path.home() / "Workspace" / "limen" / ".mcp_state.json"`).
    - `trip_circuit_breaker()`: Sets `CIRCUIT_BREAKER_TRIPPED = True`, saves state, returns `"Circuit breaker TRIPPED. System offline."`.
    - `reset_circuit_breaker()`: Sets `CIRCUIT_BREAKER_TRIPPED = False`, saves state, returns `"Circuit breaker RESET. System online."`.
    - `_check_circuit_breaker()`: Raises `RuntimeError("SYSTEM OFFLINE - GO TO SLEEP. Circuit breaker is tripped due to API rate limits or severance.")` if tripped.
    - `TASK_LOOP_TRACKER`: Tracks per-task access count. In `get_task(task_id)`: if `TASK_LOOP_TRACKER[task_id] > 3`, raises `ValueError("HARD LOOP LIMIT REACHED: Task {task_id} requested >3 times today. Moving to 'needs_human'. Abandon task immediately.")`.
  - `PROJECT.md` & `ORIGINAL_REQUEST.md §R2`: Quarantining failing PR review loops (C04 #2414, C05 #139) to dedicated topic branches while unblocking sibling lanes.

### 2.3 Feature 3: Single-Push Exact-Tree Verification
- **Primary Source Code:**
  - `scripts/verify-scoped.sh` (lines 1–15): Wrapper around `scripts/verify.py --changed "$@"`.
  - `scripts/verify.py` (lines 1–1079): The central gate execution engine.
  - `institutio/governance/gates.yaml`: Canonical registry of verification gates.
- **Key Mechanics Observed:**
  1. *Changed Set Computation:* `changed_set(base)` computes PR commits after merge-base + staged + unstaged + untracked files.
  2. *Exact History & Ref Validation:* `resolve_merge_base()`, `integration_base()`, `_reject_legacy_grafts()`. Rejects rewritten Git history, requires exact merge-base ancestors when `--integration` or `--require-base` is enabled.
  3. *Leak Guards:* `private_history_leak()` (detects committed `.limen-private` entries absent in HEAD) and `transient_custody_reversion()` (detects deleted/reverted unvalidated custody versions).
  4. *Tiered Concurrency:* `cheap` (parallel wave via `ThreadPoolExecutor`), `heavy` (requires `heavy_admission` lease), and `serialized` (held under `fcntl.flock` on `/tmp/limen-verify-whole.lock`).
  5. *Execution Sandbox & Containment:* `run_command` sets `start_new_session=True`, non-blocking I/O drain, output ceiling limit (`--gate-output-bytes`), finite timeout with `terminate_process_group()`, returning bare exit codes.

### 2.4 Feature 4: Canonical Identity & 4-Tier Offers
- **Primary Source Code:**
  - `institutio/positioning/commercial-contract.yaml` (lines 1–766): Authoritative contract schema (`limen.positioning_commercial_contract.v1`).
  - `docs/positioning/narrative-ladder.md` (lines 1–93): L1, L2, L3 progressive disclosure.
  - `docs/positioning/offers/` (`agentic-delivery-audit.md`, `governance-install.md`, `bounded-delivery-governance-retainer.md`, `product-operating-partnership-review.md`, `qualification-and-routing.md`, `agentic-delivery-audit-decision-record.json`).
  - `scripts/positioning-commercial-contract.py` & `scripts/positioning-offer-artifacts.py`: Deterministic validators and renderers.
- **Key Mechanics Observed:**
  1. *Identity Anchors:* Title = "Production-systems architect", Headline = "I build production systems that solve expensive problems.", Authorship = "Architected and directed by one person through a governed, multi-agent production system."
  2. *Progressive Disclosure:*
     - L1 (10s): Direct client CTA ("Discuss a fixed-scope Agentic Delivery Audit") & Recruiter CTA ("Discuss a senior systems architecture or engineering role with a named mandate"). Partnership is excluded from L1.
     - L2 (5m): Delivery problem map, Limen method proof, UCC & AI Chat Exporter supporting proofs with bounded claims.
     - L3 (Diligence): Controlled diligence index, claims ledger, private anchor IDs, gated partnership review.
  3. *4-Tier Offer Ladder:*
     - `audit`: Fixed-scope diagnose ($5k–$15k private anchor `RANGE-AUDIT` / `PRICE-AUDIT`), read-only.
     - `install`: Milestone implement ($25k–$60k private anchor `RANGE-INSTALL` / `PRICE-INSTALL`), bounded-write.
     - `retainer`: Capacity sustain ($10k–$25k/mo private anchor `RANGE-RETAINER` / `PRICE-RETAINER`), advisory.
     - `partnership_review`: Diligence-only (`RANGE-PARTNERSHIP`), non-public CTA, requires `HG-OPERATOR-TERMS`.
  4. *Anti-Leak Policy:* Numeric prices (`$5k`, `25000`, etc.) and private paths (`/Users/`, `.limen-private/`) are strictly forbidden in public copy and repository artifacts.

---

## 3. Tier 1: Feature Coverage Test Specifications (`tests/e2e_psp_omega/tier1_features/`)

Tier 1 focuses on standard, valid functional paths under normal operating conditions.

### 3.1 Feature 1: Worktree Isolation & Topic Branches (`test_f1_worktree_isolation.py`)

| Test ID | Test Name | Target Function / Capability | Test Description & Inputs | Assertions & Expected Output | Sandboxing / Mocks |
|---|---|---|---|---|---|
| **T1-F1-01** | `test_clean_worktree_initialization` | `initialize_worktree()` | Initialize a new topic branch `work/lane-1` from `main` into a target path under a sandbox worktrees root. | - Receipt schema == `limen.worktree_initialization.v1`<br>- State == `published`<br>- Final directory exists and contains clean git status<br>- Staging directory is removed<br>- Git worktree list contains final path | Isolated temporary git repository created via `git init` in `tempfile.TemporaryDirectory()`. |
| **T1-F1-02** | `test_topic_branch_naming_convention` | `initialize_worktree()` with lane naming | Initialize worktree using canonical lane branch naming `limen-psp-omega-lane-identity-offer`. | - Branch created in git is `refs/heads/limen-psp-omega-lane-identity-offer`<br>- Symbolic HEAD of worktree matches the branch<br>- HEAD matches repository checkout ref commit SHA | Hermetic git repo fixture with initial commit. |
| **T1-F1-03** | `test_worktree_root_resolution` | `default_worktrees_root()`, `effective_worktree_root()` | Test root derivation with `LIMEN_WORKTREES` set, unset (falling back to workspace or scratch), and `LIMEN_WORKTREE_ROOT`. | - Explicit env returns exact expanded path<br>- Unset returns default `.limen-worktrees` or `/Volumes/Scratch/limen-worktrees`<br>- Target directory is valid Path object | `unittest.mock.patch.dict(os.environ)` |
| **T1-F1-04** | `test_multi_lane_concurrent_independence` | Concurrent `initialize_worktree()` calls | Initialize two distinct worktrees (`lane-alpha`, `lane-beta`) on distinct branches from the same base repository. | - Both worktrees reach `published` state<br>- Committing a file in `lane-alpha` does not affect `lane-beta`<br>- `git status` in both worktrees remains clean independently | Multi-directory filesystem sandbox with shared bare/base repo. |
| **T1-F1-05** | `test_worktree_journal_persistence` | `_journal_path()` & atomic JSON persistence | Verify that the initialization journal is written to `<common-git-dir>/limen-worktree-initialization/<hash>.json` upon successful publish. | - Journal file exists at derived hash path<br>- Content parses as JSON<br>- `receipt["state"] == "published"`<br>- `receipt["final_validation"]["head"] == expected_head` | Hermetic git repo fixture. |
| **T1-F1-06** | `test_worktree_target_enumeration` | `iter_worktree_targets()` in `worktree_roots.py` | Create active worktree directories under simulated dispatch roots and enumerate targets. | - Target list contains all created worktrees with source `"dispatch-root"`<br>- Target deduplication preserves distinct paths<br>- Targets match configured minimum age | Temporary directory hierarchy mimicking dispatch root. |

---

### 3.2 Feature 2: Review-Loop Circuit Breaker & Quarantine (`test_f2_review_circuit_breaker.py`)

| Test ID | Test Name | Target Function / Capability | Test Description & Inputs | Assertions & Expected Output | Sandboxing / Mocks |
|---|---|---|---|---|---|
| **T1-F2-01** | `test_trip_circuit_breaker_sets_offline` | `trip_circuit_breaker()` | Call `trip_circuit_breaker()` while system is online. | - Returns string containing `"Circuit breaker TRIPPED. System offline."`<br>- `.mcp_state.json` is created/updated with `{"circuit_breaker": true}`<br>- Subsequent tool invocation raises `RuntimeError("SYSTEM OFFLINE...")` | Mock `STATE_FILE` path using `tempfile` and monkeypatch `limen_mcp.server.STATE_FILE`. |
| **T1-F2-02** | `test_reset_circuit_breaker_restores_online` | `reset_circuit_breaker()` | Trip circuit breaker, verify offline, then call `reset_circuit_breaker()`. | - Reset returns `"Circuit breaker RESET. System online."`<br>- `.mcp_state.json` contains `{"circuit_breaker": false}`<br>- Subsequent tool invocation (e.g. `list_tasks`) executes without `RuntimeError` | Mock `STATE_FILE` and sample `tasks.yaml`. |
| **T1-F2-03** | `test_task_loop_tracker_increments_on_get_task` | `get_task()` in `server.py` | Load sample tasks and call `get_task("TASK-001")` consecutively 3 times. | - Returns valid task dictionary for calls 1, 2, and 3<br>- `TASK_LOOP_TRACKER["TASK-001"] == 3`<br>- `STATE_FILE` reflects updated loop count | Mock `_load_data()` with `Task(id="TASK-001", ...)` and mock `STATE_FILE`. |
| **T1-F2-04** | `test_hard_loop_limit_trips_needs_human` | `get_task()` exceeding threshold | Call `get_task("TASK-001")` for the 4th time in a session. | - Raises `ValueError` containing `"HARD LOOP LIMIT REACHED: Task TASK-001 requested >3 times today"`<br>- Directs to abandon task immediately / move to `needs_human` | Mock `_load_data()` and mock `STATE_FILE`. |
| **T1-F2-05** | `test_all_mcp_tools_enforce_circuit_breaker` | `_check_circuit_breaker()` on all MCP tools | Test that calling `conduct_capabilities()`, `conduct_submit()`, `list_tasks()`, `add_task()`, `update_task_status()` while tripped raises `RuntimeError`. | - Each tool invocation raises `RuntimeError` matching `"SYSTEM OFFLINE"`<br>- No underlying broker or filesystem writes occur | Mock `CIRCUIT_BREAKER_TRIPPED = True`. |
| **T1-F2-06** | `test_state_file_persistence_and_reload` | `_save_state()` & `_load_state()` | Simulate process restart by reloading module or re-calling `_load_state()` with pre-existing `.mcp_state.json`. | - Global `CIRCUIT_BREAKER_TRIPPED` reflects persisted JSON value<br>- `TASK_LOOP_TRACKER` dictionary is restored with all task loop counts | Mock file system path with pre-seeded JSON state. |

---

### 3.3 Feature 3: Single-Push Exact-Tree Verification (`test_f3_single_push_verification.py`)

| Test ID | Test Name | Target Function / Capability | Test Description & Inputs | Assertions & Expected Output | Sandboxing / Mocks |
|---|---|---|---|---|---|
| **T1-F3-01** | `test_scoped_verification_changed_set_detection` | `changed_set()` in `scripts/verify.py` | In a git sandbox, commit changes to a file, stage another, and leave one untracked. | - `changed_set("HEAD~1")` returns all 3 file paths<br>- Deleted paths are included in the returned list<br>- Unmodified paths are excluded | Temporary git repository sandbox with commit history. |
| **T1-F3-02** | `test_gate_selection_from_registry` | `select()` in `scripts/verify.py` | Supply a list of changed paths (e.g. `["docs/positioning/narrative-ladder.md"]`) to `select()`. | - Returns selected gate IDs matching path filters in `gates.yaml`<br>- Returns skipped gate IDs with explicit filter reasons<br>- Does not run unimplicated gates | Mock or load canonical `institutio/governance/gates.yaml`. |
| **T1-F3-03** | `test_tiered_wave_execution_cheap_and_heavy` | `cmd_changed()` / `run_gate_wave()` | Run verification where selected gates include both `cheap` tier and `heavy` tier mock commands. | - `cheap` wave runs first and prints `WAVE cheap: START`<br>- `heavy` wave executes only after cheap passes<br>- Returns exit code 0 on all passes | Mock `gates.yaml` with synthetic echo/true commands. |
| **T1-F3-04** | `test_exact_merge_base_resolution` | `resolve_merge_base()`, `integration_base()` | Create a branched history with an ancestor commit and query `resolve_merge_base("main")`. | - Returns exact 40-char SHA of merge-base commit<br>- `integration_base()` returns SHA when supplied ref is exact ancestor<br>- Returns empty string when ref is unrelated | Sandbox git repo with branch and merge history. |
| **T1-F3-05** | `test_process_group_containment_and_bounded_output` | `run_command()` in `verify.py` | Execute a gate command that outputs text within `--gate-output-bytes` limit (e.g. 50KB). | - Process exits with code 0<br>- Output is captured and flushed to log stream<br>- Process group is cleanly terminated | Subprocess sandbox executing bash commands. |
| **T1-F3-06** | `test_bare_exit_code_propagation` | Scoped verification CLI execution | Run `verify.py --changed` against a clean tree and against a failing gate command. | - Clean tree exits with code 0<br>- Failing gate command exits with code 1<br>- Exit code is returned directly without filter masking | Subprocess invocation of `python3 scripts/verify.py`. |

---

### 3.4 Feature 4: Canonical Identity & 4-Tier Offers (`test_f4_canonical_identity_offers.py`)

| Test ID | Test Name | Target Function / Capability | Test Description & Inputs | Assertions & Expected Output | Sandboxing / Mocks |
|---|---|---|---|---|---|
| **T1-F4-01** | `test_canonical_identity_narrative_fields` | `validate_contract()` in `positioning-commercial-contract.py` | Load canonical contract and validate identity fields (`canonical_title`, `headline`, `authorship_disclosure`, `operating_thesis`). | - `canonical_title == "Production-systems architect"`<br>- `headline == "I build production systems that solve expensive problems."`<br>- `authorship_disclosure` matches required multi-agent statement<br>- Zero validation errors returned | Load `institutio/positioning/commercial-contract.yaml`. |
| **T1-F4-02** | `test_progressive_disclosure_levels_1_to_3` | `narrative_ladder` validation | Validate structure of `narrative_ladder` in commercial contract across L1 (10s), L2 (5m), and L3 (diligence). | - L1 defines direct_client and recruiter_executive next actions<br>- L1 stop rule identifies role, buyer, problem, proof, next action<br>- L2 covers method, 3 proof roles, authorship disclosure<br>- L3 defines diligence index (claim truth, system proof, method, economics, partnership) | Parse `commercial-contract.yaml` and `narrative-ladder.md`. |
| **T1-F4-03** | `test_4_tier_offer_ladder_specifications` | `offer_ladder` in `commercial-contract.yaml` | Validate all 4 offers: `audit`, `install`, `retainer`, and secondary `partnership_review`. | - `audit`: stage = `diagnose`, mode = `read_only`, range_id = `RANGE-AUDIT`<br>- `install`: stage = `implement`, mode = `bounded_write`, range_id = `RANGE-INSTALL`<br>- `retainer`: stage = `sustain`, mode = `advisory_with_named_changes`, range_id = `RANGE-RETAINER`<br>- `partnership_review`: stage = `diligence`, mode = `diligence_only`, public_cta = `False` | Parse `commercial-contract.yaml`. |
| **T1-F4-04** | `test_symbolic_economic_ranges_and_private_anchors` | Economics contract validation | Verify that all 4 offers reference symbolic range IDs (`RANGE-AUDIT`, `RANGE-INSTALL`, `RANGE-RETAINER`, `RANGE-PARTNERSHIP`) and require human gates (`HG-PRICE-ANCHORS`, `HG-OPERATOR-TERMS`). | - All 4 offers have `public_price: prohibited`<br>- Range IDs match `RANGE-*`<br>- Approval gates are present (`HG-PRICE-ANCHORS`, `HG-OPERATOR-TERMS`)<br>- No numeric prices in contract public copy | Load `commercial-contract.yaml`. |
| **T1-F4-05** | `test_qualification_routing_rules_and_scenarios` | `_rule_matches()`, `qualification` matrix | Execute all 8 canonical qualification scenarios (`stalled_agent_pilot`, `accepted_audit_one_team`, `installed_controls_drifting`, `senior_role_with_mandate`, `qualified_operator_after_diligence`, `operator_terms_requested_early`, `rescue_without_sponsor`, `emergency_takeover_request`). | - Each scenario resolves to its exact `expected_route` (`audit`, `install`, `retainer`, `recruiter`, `partnership_review`, `human_review`, `decline`, `decline`)<br>- Priority hierarchy (`human_review` > `decline` > `recruiter` > `partnership_review` > `retainer` > `install` > `audit`) holds | Execute `qualification` evaluator against `commercial-contract.yaml`. |
| **T1-F4-06** | `test_generated_offer_markdown_artifacts` | `validate_repository()` in `positioning-offer-artifacts.py` | Verify that all generated markdown files in `docs/positioning/offers/` match canonical YAML definitions. | - Files exist: `agentic-delivery-audit.md`, `governance-install.md`, `bounded-delivery-governance-retainer.md`, `product-operating-partnership-review.md`, `qualification-and-routing.md`<br>- Zero drift errors returned by validator | Compare `docs/positioning/offers/*.md` against rendered output. |

---

## 4. Tier 2: Boundary & Corner Case Test Specifications (`tests/e2e_psp_omega/tier2_boundaries/`)

Tier 2 focuses on fault injection, boundary values, invalid schemas, timeouts, permission errors, and anti-leak enforcement.

### 4.1 Feature 1: Worktree Isolation Boundaries (`test_f1_worktree_boundaries.py`)

| Test ID | Test Name | Target Failure / Edge Condition | Injected Fault / Boundary Input | Assertions & Expected Error Handling | Sandboxing Strategy |
|---|---|---|---|---|---|
| **T2-F1-01** | `test_existing_final_path_collision_fails_closed` | Destination directory collision | Pre-create `final_path` directory with existing files before calling `initialize_worktree()`. | - Raises `WorktreeInitializationError`<br>- `receipt["state"] == "crashed"`<br>- `receipt["phase"] == "preflight"`<br>- `receipt["crash"]["code"] == "final-path-already-exists"`<br>- Pre-existing files in `final_path` remain unmodified | Temporary git repo with existing destination folder. |
| **T2-F1-02** | `test_branch_name_collision_preserves_branch` | Branch name already exists | Create git branch `work/collision` before calling `initialize_worktree(branch="work/collision")`. | - Raises `WorktreeInitializationError`<br>- `receipt["phase"] == "add"`<br>- Existing branch is not deleted or force-overwritten<br>- `final_path` is not published | Temporary git repo with pre-existing branch ref. |
| **T2-F1-03** | `test_dirty_staging_validation_failure_preserves_root` | Untracked file in staging | Inject a phase hook at `validate-staging` that creates an untracked file `untracked.txt` in the staging root. | - Raises `WorktreeInitializationError`<br>- `receipt["state"] == "crashed"`<br>- `receipt["crash"]["code"] == "worktree-has-untracked-paths"`<br>- Staging directory is preserved (NOT deleted) for inspection<br>- `final_path` does not exist | Temporary git repo with `phase_hook` injection. |
| **T2-F1-04** | `test_crash_after_move_records_crashed_state` | Crash after atomic rename | Inject phase hook at `move` that raises `RuntimeError("simulated-io-crash")`. | - Raises `WorktreeInitializationError`<br>- `receipt["state"] == "crashed"`<br>- `receipt["phase"] == "move"`<br>- Journal file records crashed state<br>- Moved directory is preserved | Temporary git repo with `phase_hook` injection. |
| **T2-F1-05** | `test_cross_filesystem_worktree_rejected` | Cross-device worktree staging | Mock `os.stat().st_dev` on staging to differ from parent directory `st_dev`. | - Raises `WorktreeInitializationError`<br>- `receipt["crash"]["code"] == "staging-path-is-not-on-final-filesystem"`<br>- Halts before atomic rename | Mock `os.stat` returning differing device IDs. |
| **T2-F1-06** | `test_worktree_inventory_strict_mode_fault` | Unreadable/missing lifecycle root | Call `iter_worktree_targets(strict=True)` where a configured root in `LIMEN_RECLAIM_WORKSPACE_ROOTS` causes an `OSError` (e.g. permission denied). | - Raises `WorktreeInventoryError` naming the unstatable path<br>- Prevents silent partial enumeration or false zero-debt claim | Mock `Path.iterdir()` or `Path.stat()` raising `PermissionError`. |

---

### 4.2 Feature 2: Circuit Breaker Boundaries (`test_f2_circuit_breaker_boundaries.py`)

| Test ID | Test Name | Target Failure / Edge Condition | Injected Fault / Boundary Input | Assertions & Expected Error Handling | Sandboxing Strategy |
|---|---|---|---|---|---|
| **T2-F2-01** | `test_corrupt_mcp_state_json_handles_gracefully` | Malformed JSON in state file | Write invalid non-JSON data (`"{corrupted_json:::"`) to `.mcp_state.json` and initialize server state. | - `_load_state()` catches exception without crashing process<br>- Defaults to `CIRCUIT_BREAKER_TRIPPED = False` and `TASK_LOOP_TRACKER = {}`<br>- System remains recoverable | Mock `STATE_FILE` path populated with garbage bytes. |
| **T2-F2-02** | `test_unwritable_mcp_state_json_does_not_crash` | Read-only state file filesystem | Mock `open()` on `STATE_FILE` to raise `PermissionError` during `_save_state()`. | - `_save_state()` suppresses error gracefully (`except Exception: pass`)<br>- In-memory state remains updated<br>- Tool execution continues | Mock `builtins.open` to raise `PermissionError` when writing `STATE_FILE`. |
| **T2-F2-03** | `test_empty_task_id_and_special_character_validation` | Invalid task IDs in loop tracker | Call `get_task("")`, `get_task("../escape")`, `get_task("TASK-9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999")`. | - `_validate_task_id()` raises `ValueError`<br>- Malformed task ID does not pollute `TASK_LOOP_TRACKER`<br>- Loop tracker does not increment | Direct call to MCP tools with edge-case strings. |
| **T2-F2-04** | `test_concurrent_task_loop_increment_boundary` | Multi-threaded task access | Spawn 10 threads concurrently calling `get_task("CONCURRENT-TASK")`. | - Exactly first 3 calls succeed (or up to limit), and subsequent calls raise `ValueError("HARD LOOP LIMIT REACHED...")`<br>- `TASK_LOOP_TRACKER["CONCURRENT-TASK"]` accurately records count<br>- No race condition corrupts state | `ThreadPoolExecutor` invoking `get_task()`. |
| **T2-F2-05** | `test_circuit_breaker_trip_during_active_execution` | Mid-flight trip event | Simulate trip event occurring immediately prior to `conduct_submit()`. | - `_check_circuit_breaker()` trips immediately and aborts submit<br>- Zero child packets dispatched<br>- Zero budget debited | Thread event triggering `trip_circuit_breaker()` before submit call. |
| **T2-F2-06** | `test_quarantine_path_nesting_and_collision_checks` | `quarantine_path()` safety checks | Test `quarantine_path()` where source == destination, source is parent of destination, or destination exists. | - Raises `RuntimeError("quarantine-source-destination-nesting")`<br>- Raises `RuntimeError("quarantine-destination-exists")`<br>- Source path is not destroyed or partially moved | Filesystem sandbox with nested paths. |

---

### 4.3 Feature 3: Single-Push Verification Boundaries (`test_f3_verification_boundaries.py`)

| Test ID | Test Name | Target Failure / Edge Condition | Injected Fault / Boundary Input | Assertions & Expected Error Handling | Sandboxing Strategy |
|---|---|---|---|---|---|
| **T2-F3-01** | `test_require_base_with_unresolvable_merge_base_fails_closed` | Missing merge-base in CI | Call `cmd_changed(require_base=True, base="nonexistent-branch")`. | - Prints error to stderr: `require-base: no merge-base resolves...`<br>- Returns exit code `1`<br>- Fails closed instead of defaulting to empty changed set | Mock `git("merge-base", ...)` raising `CalledProcessError`. |
| **T2-F3-02** | `test_require_base_with_empty_changed_set_fails_closed` | Empty PR diff resolution anomaly | Call `cmd_changed(require_base=True, base="main")` when changed set is empty. | - Prints error: `require-base: base resolved but the changed set is empty...`<br>- Returns exit code `1` (refuses to fail open) | Sandbox git repo with zero changes against base. |
| **T2-F3-03** | `test_integration_mode_rejects_non_ancestor_base` | Non-ancestor base in merge queue | Call `cmd_changed(integration=True, base="unrelated-commit")`. | - `integration_base()` returns `""`<br>- Prints error: `--integration requires the supplied --base commit to be an ancestor...`<br>- Returns exit code `1` | Sandbox git repo with divergent branch. |
| **T2-F3-04** | `test_private_history_leak_detection_fails_closed` | Committed private namespace file | Create a git commit introducing `.limen-private/secret.json`, then delete it in a subsequent commit. | - `private_history_leak()` returns `True`<br>- `cmd_changed()` prints error: `private-history: a committed private namespace entry is absent from HEAD...`<br>- Returns exit code `1` | Sandbox git repo with committed-then-deleted private file. |
| **T2-F3-05** | `test_gate_command_timeout_kills_process_group` | Long-running runaway test command | Execute a gate command running `sleep 60` with a timeout of 0.2 seconds. | - Gate times out<br>- Process group is terminated via `SIGTERM` / `SIGKILL`<br>- Log contains `gate-command-timeout: shared gate deadline expired`<br>- Returns exit code `124` (or wave failure `1`) | Subprocess executing timed sleep. |
| **T2-F3-06** | `test_gate_output_exceeding_byte_limit_is_truncated_safely` | Massive stdout flood (e.g. 50MB) | Execute a gate command producing 10MB of continuous text with output limit set to 10KB. | - Output is capped at exact limit<br>- Process group is cleanly terminated<br>- Log contains `gate-command-output-limit: >10240 bytes`<br>- Exits with code `125` / gate failure | Subprocess generating infinite yes/counter stream. |

---

### 4.4 Feature 4: Identity & Offer Boundaries (`test_f4_identity_offer_boundaries.py`)

| Test ID | Test Name | Target Failure / Edge Condition | Injected Fault / Boundary Input | Assertions & Expected Error Handling | Sandboxing Strategy |
|---|---|---|---|---|---|
| **T2-F4-01** | `test_numeric_price_leak_in_contract_fails_closed` | Leaked numeric dollar amount | Inject `capacity_rule: "Minimum $25,000 USD fee"` into `commercial-contract.yaml`. | - `validate_contract()` returns error containing `"numeric price leaked"`<br>- `validate_repository()` flags failure | Copy canonical contract dict and mutate. |
| **T2-F4-02** | `test_numeric_price_leak_in_markdown_artifact_fails_closed` | Leaked rate in markdown | Inject `Fee: $15k` into `docs/positioning/offers/agentic-delivery-audit.md`. | - `validate_artifact_directory()` returns error containing `"numeric price leaked"`<br>- Validates across `$`, `USD`, `dollars`, `k`, `/hr`, `per month` patterns | Render offer artifacts to temporary directory and inject text. |
| **T2-F4-03** | `test_private_path_leak_in_contract_or_markdown_fails_closed` | Leaked private filesystem path | Inject `source: /Users/4jp/Workspace/.limen-private/notes.md` into offer copy. | - `validate_artifact_text()` returns error naming private-source marker<br>- Detects `/Users/`, `.limen-private/`, `.copilot/`, `session-state/`, private session UUIDs | Temporary text validator. |
| **T2-F4-04** | `test_forbidden_identity_claims_fail_closed` | Inflated executive title or superlative | Inject `headline: "The best systems architect in the world"` or title `CAIO` into identity block. | - `validate_contract()` returns error naming `"unsupported public language"` or forbidden claim<br>- Fails closed | Contract validator with mutated identity block. |
| **T2-F4-05** | `test_public_partnership_cta_promotion_fails_closed` | Partnership made public | Set `public_cta: True` or add front-door marker to `product-operating-partnership-review.md`. | - `validate_contract()` returns error: `"public partnership promotion is prohibited"`<br>- `validate_front_door_ctas()` returns error: partnership must not contain front-door CTA | Mutated contract / rendered artifact. |
| **T2-F4-06** | `test_unbounded_audit_authority_mode_fails_closed` | Audit authority escalated to write | Set `audit.authority.mode = "unbounded_write"` or `"full_access"` in contract. | - `validate_contract()` returns error: `"Audit authority must be read-only"`<br>- Prevents ungoverned mutation scope in diagnose phase | Mutated contract dict. |

---

## 5. Python Unittest Structure & Test Harness Architecture

### 5.1 Directory Layout
```
tests/
└── e2e_psp_omega/
    ├── __init__.py
    ├── runner.py                          # Dedicated multi-tier test runner
    ├── conftest_utils.py                  # Shared fixtures: git sandbox, mock MCP state, temp registry
    ├── tier1_features/
    │   ├── __init__.py
    │   ├── test_f1_worktree_isolation.py
    │   ├── test_f2_review_circuit_breaker.py
    │   ├── test_f3_single_push_verification.py
    │   └── test_f4_canonical_identity_offers.py
    └── tier2_boundaries/
        ├── __init__.py
        ├── test_f1_worktree_boundaries.py
        ├── test_f2_circuit_breaker_boundaries.py
        ├── test_f3_verification_boundaries.py
        └── test_f4_identity_offer_boundaries.py
```

### 5.2 Shared Utilities & Sandboxing Strategy (`conftest_utils.py`)
1. **`GitSandbox` Context Manager:**
   - Initializes a fresh, fully-configured git repository in a `tempfile.TemporaryDirectory()`.
   - Commits standard baseline tracked files (`README.md`, `tracked.txt`).
   - Provides helper methods: `commit(filename, content, msg)`, `branch(name)`, `worktree_add(path, branch)`, `raw_git(*args)`.
2. **`MockMcpState` Context Manager:**
   - Redirects `limen_mcp.server.STATE_FILE` to an isolated file in `tempfile.TemporaryDirectory()`.
   - Initializes fresh `CIRCUIT_BREAKER_TRIPPED = False` and `TASK_LOOP_TRACKER = {}`.
   - Cleans up state file upon exit.
3. **`TemporaryGatesRegistry` Context Manager:**
   - Creates a synthetic `gates.yaml` and mock gate scripts for testing scoped selection and tiered execution without invoking long-running whole-matrix suites.
4. **`ContractFixture` Helper:**
   - Loads canonical `institutio/positioning/commercial-contract.yaml` as immutable baseline and yields deep copies for mutation testing.

### 5.3 Runner Semantics (`runner.py`)
- Invocation: `python3 -m unittest discover -s tests/e2e_psp_omega` or `python3 tests/e2e_psp_omega/runner.py --tier 1,2`.
- Pass/Fail Semantics:
  - Exit code `0` on 100% test pass.
  - Exit code `1` on any failure.
  - Generates structured JUnit XML or JSON test report for integration into CI.

---

## 6. Synthesis & Next Steps

1. **Test Specification Completeness:** All 4 features have both functional happy-path (Tier 1) and failure/boundary-resilience (Tier 2) test suites specified with exact names, inputs, and assertions.
2. **Deterministic Hermetic Execution:** Every test uses sandboxed temporary git repositories, in-memory mocks, or isolated state files, ensuring zero side-effects on the live workspace or git history.
3. **Traceability:** Every test links directly to `ORIGINAL_REQUEST.md (§R1, §R2, §Acceptance)` and `PROJECT.md (Features 1–4)`.

The test specifications are ready for test suite implementation in Milestone E2E.
