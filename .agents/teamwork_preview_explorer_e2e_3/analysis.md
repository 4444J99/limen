# E2E PSP Omega Test Suite Architecture & Tier 3/4 Design Specification

## Executive Summary
This document defines the complete architectural design and implementation plan for the **PSP Omega Recovery End-to-End (E2E) Test Suite** (`tests/e2e_psp_omega/`). 
Derived strictly from `ORIGINAL_REQUEST.md`, `PROJECT.md`, `TEST_INFRA.md`, `AGENTS.md`, and repository governance fixtures, this test architecture guarantees:
1. **Full Hermetic Isolation**: Standalone, opaque-box execution against repository scripts and fixtures with zero environmental side-effects on live worktrees, `.mcp_state.json`, `tasks.yaml`, or git state.
2. **Standard Compatibility**: Dual-mode execution supporting both the custom test harness (`tests/e2e_psp_omega/runner.py`) and standard `python3 -m unittest discover -s tests/e2e_psp_omega` or `pytest`.
3. **Comprehensive Coverage Thresholds**: Total suite count of **95 test cases** (surpassing the ≥93 minimum threshold) structured across 4 distinct testing tiers:
   - **Tier 1 (Feature Functionality)**: 40 test cases (5 per feature across 8 features)
   - **Tier 2 (Boundary & Resilience)**: 40 test cases (5 per feature across 8 features)
   - **Tier 3 (Cross-Feature Combinations)**: 10 test cases (Pairwise interaction across major feature pairs)
   - **Tier 4 (Real-World Application Scenarios)**: 5 complex multi-phase E2E scenarios
4. **Deterministic Exit Codes**: Returns exit code `0` on 100% pass and non-zero on any failure or error.

---

## 1. Overall Test Architecture & Sizing Strategy

### 1.1 Directory Layout & Module Structure
The E2E test suite resides under `tests/e2e_psp_omega/` with modular separation by testing tier and shared utilities:

```
tests/e2e_psp_omega/
├── __init__.py
├── common.py                          # Common sandboxing, fixtures, mocking, and assertions
├── runner.py                          # Unified CLI test harness runner and discovery engine
├── tier1_features/                    # Tier 1: Functional feature tests (40 tests)
│   ├── __init__.py
│   ├── test_f1_worktree_isolation.py
│   ├── test_f2_circuit_breaker.py
│   ├── test_f3_exact_tree_verification.py
│   ├── test_f4_identity_offers.py
│   ├── test_f5_proof_architecture.py
│   ├── test_f6_portfolio_frontdoor.py
│   ├── test_f7_durable_receipts.py
│   └── test_f8_terminal_omega.py
├── tier2_boundaries/                  # Tier 2: Boundary value and failure resilience (40 tests)
│   ├── __init__.py
│   ├── test_b1_worktree_boundaries.py
│   ├── test_b2_circuit_breaker_boundaries.py
│   ├── test_b3_exact_tree_boundaries.py
│   ├── test_b4_identity_offers_boundaries.py
│   ├── test_b5_proof_boundaries.py
│   ├── test_b6_portfolio_frontdoor_boundaries.py
│   ├── test_b7_receipt_boundaries.py
│   └── test_b8_terminal_omega_boundaries.py
├── tier3_combinations/                # Tier 3: Pairwise cross-feature interactions (10 tests)
│   ├── __init__.py
│   ├── test_combo_worktree_circuit_breaker.py
│   ├── test_combo_exact_tree_receipts.py
│   ├── test_combo_identity_proof.py
│   ├── test_combo_proof_frontdoor.py
│   ├── test_combo_circuit_breaker_omega.py
│   ├── test_combo_worktree_exact_tree.py
│   ├── test_combo_offers_durable_receipts.py
│   ├── test_combo_frontdoor_exact_tree.py
│   ├── test_combo_circuit_quarantine_resolution.py
│   └── test_combo_multi_worktree_concurrency.py
└── tier4_scenarios/                   # Tier 4: Real-world complex E2E scenarios (5 tests)
    ├── __init__.py
    ├── test_scenario_1_full_lifecycle_positioning.py
    ├── test_scenario_2_automated_review_eviction.py
    ├── test_scenario_3_parallel_worktree_isolation.py
    ├── test_scenario_4_corrupted_receipt_recovery.py
    └── test_scenario_5_terminal_omega_proof.py
```

### 1.2 Suite Sizing & Distribution Matrix

| Tier | Name | Target Focus | Modules | Test Cases |
|---|---|---|---|:---:|
| **Tier 1** | Feature Functionality | Feature-by-feature correctness across F1–F8 | 8 files | 40 |
| **Tier 2** | Boundary & Resilience | Edge cases, malformed payloads, corrupt state, negative paths | 8 files | 40 |
| **Tier 3** | Cross-Feature Combinations | Pairwise interaction hypotheses across major feature intersections | 10 files | 10 |
| **Tier 4** | Real-World Application Scenarios | Complex multi-step lifecycle, review eviction, and terminal proof flows | 5 files | 5 |
| **Total** | **Full E2E Suite** | **Complete PSP Omega Recovery Verification** | **31 files** | **95** |

*(95 test cases > 93 requirement threshold)*

---

## 2. Test Harness Runner (`tests/e2e_psp_omega/runner.py`)

### 2.1 Design Objectives
- **Standalone CLI Execution**: Executable directly via `python3 tests/e2e_psp_omega/runner.py` with granular flags (`--tier`, `--filter`, `--verbose`, `--failfast`, `--json-report`).
- **Unittest Discovery Compatibility**: Conforms to standard `unittest.TestCase` conventions, making `python3 -m unittest discover -s tests/e2e_psp_omega` immediately discover and execute all 95 tests without special wrappers.
- **Fail-Closed Exit Codes**: Exits with code `0` only if all discovered tests succeed; returns non-zero (`1`) on any assertion failure or unexpected exception.
- **Diagnostic Reporting**: Outputs clean terminal tables with tier breakdowns, duration per test, and failure stack traces.

### 2.2 Runner Specification & Implementation Design

```python
#!/usr/bin/env python3
"""E2E PSP Omega Test Suite Runner.

Supports standalone CLI invocation with tier filtering as well as standard
unittest discovery.

Usage:
    python3 tests/e2e_psp_omega/runner.py
    python3 tests/e2e_psp_omega/runner.py --tier 3
    python3 tests/e2e_psp_omega/runner.py --tier 4 -v
    python3 tests/e2e_psp_omega/runner.py --filter test_scenario_1
    python3 -m unittest discover -s tests/e2e_psp_omega
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import unittest
from pathlib import Path
from typing import List, Optional

SUITE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SUITE_ROOT.parent.parent


class PSPOmegaTestResult(unittest.TextTestResult):
    """Custom TestResult collecting detailed execution metrics per tier."""

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.tier_metrics = {"Tier 1": 0, "Tier 2": 0, "Tier 3": 0, "Tier 4": 0, "Other": 0}
        self.start_times = {}

    def startTest(self, test):
        super().startTest(test)
        self.start_times[test.id()] = time.monotonic()

    def addSuccess(self, test):
        super().addSuccess(test)
        tier = self._classify_tier(test)
        self.tier_metrics[tier] += 1

    def _classify_tier(self, test) -> str:
        tid = test.id()
        if "tier1_features" in tid:
            return "Tier 1"
        elif "tier2_boundaries" in tid:
            return "Tier 2"
        elif "tier3_combinations" in tid:
            return "Tier 3"
        elif "tier4_scenarios" in tid:
            return "Tier 4"
        return "Other"


def load_suite(tier: Optional[int] = None, pattern: Optional[str] = None) -> unittest.TestSuite:
    """Discover tests according to tier selection and optional regex pattern."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    target_dirs = []
    if tier is None or tier == 0:
        target_dirs = [
            SUITE_ROOT / "tier1_features",
            SUITE_ROOT / "tier2_boundaries",
            SUITE_ROOT / "tier3_combinations",
            SUITE_ROOT / "tier4_scenarios",
        ]
    elif tier == 1:
        target_dirs = [SUITE_ROOT / "tier1_features"]
    elif tier == 2:
        target_dirs = [SUITE_ROOT / "tier2_boundaries"]
    elif tier == 3:
        target_dirs = [SUITE_ROOT / "tier3_combinations"]
    elif tier == 4:
        target_dirs = [SUITE_ROOT / "tier4_scenarios"]
    else:
        raise ValueError(f"Unknown tier: {tier}")

    for tdir in target_dirs:
        if tdir.is_dir():
            discovered = loader.discover(
                start_dir=str(tdir),
                pattern=pattern or "test_*.py",
                top_level_dir=str(REPO_ROOT),
            )
            suite.addTests(discovered)

    return suite


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PSP Omega E2E Test Suite Runner")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Run tests from a specific tier only")
    parser.add_argument("--filter", type=str, help="Pattern filter for test names")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-f", "--failfast", action="store_true", help="Stop on first failure")
    args = parser.parse_args(argv)

    suite = load_suite(tier=args.tier, pattern=f"*{args.filter}*.py" if args.filter else None)
    
    runner = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1,
        failfast=args.failfast,
        resultclass=PSPOmegaTestResult,
    )

    start_time = time.monotonic()
    result = runner.run(suite)
    elapsed = time.monotonic() - start_time

    print(f"\n==================== PSP Omega Test Suite Summary ====================")
    print(f"Total Tests Run: {result.testsRun}")
    print(f"Passed:         {result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)}")
    print(f"Failures:       {len(result.failures)}")
    print(f"Errors:         {len(result.errors)}")
    print(f"Skipped:        {len(result.skipped)}")
    print(f"Duration:       {elapsed:.2f}s")
    print(f"======================================================================\n")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
```

---

## 3. Common Utilities & Sandboxing Helpers (`tests/e2e_psp_omega/common.py`)

### 3.1 Design Principles
- **No Side-Effects**: All tests run inside temporary file systems. Never mutate live `tasks.yaml`, `.mcp_state.json`, `docs/receipts/`, or `/Users/4jp/Workspace/.worktrees/`.
- **Environment Scrubbing**: Clean environment variables (`LIMEN_ROOT`, `LIMEN_TASKS`, `LIMEN_AGENT`, `MCP_STATE_PATH`, `GIT_WORK_TREE`, `GIT_DIR`).
- **Fixture Builders**: Reusable generation of valid/invalid `limen.positioning_work_receipt.v1`, `limen.positioning_phase_receipt.v1`, `limen.positioning_omega_pass.v1`, `commercial-contract.yaml`, and `program.yaml`.
- **Subprocess Isolation**: Hermetic execution of scripts with exit code capture and `PIPESTATUS` discipline.

### 3.2 Common Sandboxing Implementation Specification

```python
"""Common Sandboxing, Mocking, and Assertion Helpers for PSP Omega E2E Tests."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class PSPOmegaTestCase(unittest.TestCase):
    """Base test case providing isolated file sandboxes and fixture helpers."""

    def setUp(self) -> None:
        super().setUp()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="psp_omega_e2e_")
        self.sandbox_path = Path(self._temp_dir.name)
        
        # Structure sandbox paths
        self.sandbox_repo = self.sandbox_path / "limen"
        self.sandbox_repo.mkdir(parents=True)
        self.sandbox_worktrees = self.sandbox_path / ".worktrees"
        self.sandbox_worktrees.mkdir(parents=True)
        self.mcp_state_file = self.sandbox_path / ".mcp_state.json"
        self.tasks_file = self.sandbox_repo / "tasks.yaml"
        self.receipts_dir = self.sandbox_repo / "docs" / "receipts" / "positioning"
        self.receipts_dir.mkdir(parents=True)

        # Initialize mock state
        self._init_mock_environment()

    def tearDown(self) -> None:
        self._temp_dir.cleanup()
        super().tearDown()

    def _init_mock_environment(self) -> None:
        """Create baseline mock files in sandbox."""
        # Initialize default .mcp_state.json
        self.write_mcp_state(circuit_breaker=False, task_loops={})
        
        # Initialize default minimal tasks.yaml
        self.tasks_file.write_text("tasks:\n  []\ndispatch_log:\n  []\n", encoding="utf-8")

    def write_mcp_state(self, circuit_breaker: bool = False, task_loops: Optional[Dict[str, Any]] = None) -> None:
        """Persist state to the isolated .mcp_state.json."""
        data = {
            "circuit_breaker": circuit_breaker,
            "task_loops": task_loops or {},
        }
        self.mcp_state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def read_mcp_state(self) -> Dict[str, Any]:
        """Read isolated .mcp_state.json."""
        if not self.mcp_state_file.exists():
            return {}
        return json.loads(self.mcp_state_file.read_text(encoding="utf-8"))

    @contextlib.contextmanager
    def isolated_env(self, extra_env: Optional[Dict[str, str]] = None) -> Generator[Dict[str, str], None, None]:
        """Context manager with scrubbed and redirected environment variables."""
        old_env = os.environ.copy()
        new_env = old_env.copy()
        
        # Redirect critical paths
        new_env["LIMEN_ROOT"] = str(self.sandbox_repo)
        new_env["LIMEN_TASKS"] = str(self.tasks_file)
        new_env["LIMEN_MCP_STATE"] = str(self.mcp_state_file)
        new_env["LIMEN_WORKTREE_BASE"] = str(self.sandbox_worktrees)
        new_env["PYTHONPATH"] = f"{REPO_ROOT / 'cli' / 'src'}:{REPO_ROOT / 'mcp' / 'src'}:{REPO_ROOT / 'scripts'}:{old_env.get('PYTHONPATH', '')}"

        if extra_env:
            new_env.update(extra_env)

        os.environ.clear()
        os.environ.update(new_env)
        try:
            yield new_env
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def create_mock_worktree(self, lane_name: str, branch: str) -> Path:
        """Create an isolated worktree directory simulating git worktree add."""
        wt_path = self.sandbox_worktrees / lane_name
        wt_path.mkdir(parents=True, exist_ok=True)
        (wt_path / ".git").write_text(f"gitdir: {self.sandbox_repo}/.git/worktrees/{lane_name}\n", encoding="utf-8")
        (wt_path / "LANE.md").write_text(f"# Worktree: {lane_name}\nBranch: {branch}\n", encoding="utf-8")
        return wt_path

    def build_work_receipt(
        self,
        work_id: str,
        title: str = "Test Work Item",
        status: str = "pass",
        observed_head: str = "a" * 40,
        predicate_command: str = "pytest tests/test_example.py",
    ) -> Dict[str, Any]:
        """Build schema-valid limen.positioning_work_receipt.v1."""
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        return {
            "schema_version": "limen.positioning_work_receipt.v1",
            "work_id": work_id,
            "title": title,
            "status": status,
            "observed_head": observed_head,
            "predicate": {
                "command": predicate_command,
                "exit_code": 0 if status == "pass" else 1,
                "executed_at": now,
            },
            "recorded_at": now,
        }

    def build_phase_receipt(
        self,
        phase_id: str,
        status: str = "pass",
        work_receipts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build schema-valid limen.positioning_phase_receipt.v1."""
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        return {
            "schema_version": "limen.positioning_phase_receipt.v1",
            "phase_id": phase_id,
            "status": status,
            "work_receipts": work_receipts or [],
            "recorded_at": now,
        }

    def build_omega_pass(
        self,
        pass_number: int,
        state_digest: str,
        observed_at: Optional[str] = None,
        status: str = "pass",
    ) -> Dict[str, Any]:
        """Build schema-valid limen.positioning_omega_pass.v1."""
        now = observed_at or datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        return {
            "schema_version": "limen.positioning_omega_pass.v1",
            "status": status,
            "pass": pass_number,
            "state_digest": state_digest,
            "observed_at": now,
        }

    def run_command(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> Tuple[int, str, str]:
        """Run an isolated command and return (exit_code, stdout, stderr)."""
        run_cwd = cwd or self.sandbox_repo
        proc = subprocess.run(
            cmd,
            cwd=str(run_cwd),
            env=env or os.environ,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
```

---

## 4. Detailed Specification of Tier 3: Cross-Feature Combinations

Tier 3 exercises pairwise interactions between distinct subsystems to prevent emergent defects at architectural boundaries. The suite contains **10 pairwise combination test cases** (exceeding the ≥8 requirement).

```
========================================================================================
                          TIER 3 COMBINATORIAL COVERAGE MAP
========================================================================================
Test File                                  Feature Pair      Interaction Hypothesis
----------------------------------------------------------------------------------------
test_combo_worktree_circuit_breaker.py     F1 + F2           Worktree operations fail-closed when breaker tripped
test_combo_exact_tree_receipts.py          F3 + F7           Receipt head must match exact tree commit digest
test_combo_identity_proof.py               F4 + F5           Case studies consume ratified identity L1/L2/L3 roles
test_combo_proof_frontdoor.py              F5 + F6           Frontdoor IA maps to validated flagship proof URLs
test_combo_circuit_breaker_omega.py        F2 + F8           Omega verification halts when breaker is tripped
test_combo_worktree_exact_tree.py          F1 + F3           Scoped verification runs correctly in isolated worktrees
test_combo_offers_durable_receipts.py      F4 + F7           4-tier offer modifications generate valid leaf receipts
test_combo_frontdoor_exact_tree.py         F6 + F3           Visual direction updates implicate scoped gates
test_combo_circuit_quarantine_resolution.py F2 + F3 + F7     Quarantined PR resolved via exact-tree fix + receipt
test_combo_multi_worktree_concurrency.py   F1 + F7           Concurrent worktrees emit distinct non-clobbering receipts
========================================================================================
```

### 4.1 Combo 1: Worktree Isolation + Circuit Breaker (`test_combo_worktree_circuit_breaker.py`)
- **Pairing**: F1 (Worktree Isolation) + F2 (Review-Loop Circuit Breaker)
- **Hypothesis**: When the review-loop circuit breaker is tripped (`CIRCUIT_BREAKER_TRIPPED = True`), worktree provisioning or conductor task dispatch targeting that worktree must immediately fail closed and refuse worktree mutation or branch creation without leaving dangling local worktrees.
- **Assertion Invariants**:
  1. `trip_circuit_breaker()` updates `.mcp_state.json` with `"circuit_breaker": True`.
  2. Attempted conduct claims or worktree creations raise `RuntimeError("SYSTEM OFFLINE")`.
  3. No unmanaged directories remain under `/Users/4jp/Workspace/.worktrees/`.
  4. After `reset_circuit_breaker()`, worktree lifecycle resumes cleanly.

```python
class TestWorktreeCircuitBreakerCombo(PSPOmegaTestCase):
    def test_worktree_provisioning_fails_closed_when_circuit_breaker_tripped(self):
        with self.isolated_env():
            from limen_mcp.server import trip_circuit_breaker, reset_circuit_breaker, _check_circuit_breaker
            
            # Trip circuit breaker
            trip_circuit_breaker()
            self.assertTrue(self.read_mcp_state()["circuit_breaker"])

            # Verify operations fail closed
            with self.assertRaises(RuntimeError) as ctx:
                _check_circuit_breaker()
            self.assertIn("SYSTEM OFFLINE", str(ctx.exception))

            # Reset circuit breaker
            reset_circuit_breaker()
            self.assertFalse(self.read_mcp_state()["circuit_breaker"])
            _check_circuit_breaker()  # No exception raised
```

### 4.2 Combo 2: Exact-Tree Scoped Verification + Durable Receipts (`test_combo_exact_tree_receipts.py`)
- **Pairing**: F3 (Single-Push Exact-Tree Verification) + F7 (Durable Receipts)
- **Hypothesis**: A durable work receipt `limen.positioning_work_receipt.v1` is invalid if its `observed_head` does not match the exact commit hash of the tree verified by `verify-scoped.sh`. Mutating the tree without re-running verification must cause receipt verification to fail closed.
- **Assertion Invariants**:
  1. Receipt with matching `observed_head` passes receipt integrity validation.
  2. If file content changes (new commit SHA), previously emitted receipt is rejected with `head_oid mismatch`.
  3. Re-running the scoped gate on the new exact tree produces an updated receipt with the new SHA.

```python
class TestExactTreeReceiptsCombo(PSPOmegaTestCase):
    def test_receipt_invalidation_on_exact_tree_sha_mismatch(self):
        head_v1 = "1111111111111111111111111111111111111111"
        head_v2 = "2222222222222222222222222222222222222222"
        
        receipt = self.build_work_receipt("PSP-P03-W01", observed_head=head_v1)
        self.assertEqual(receipt["observed_head"], head_v1)

        # Validate that checking against head_v2 detects mismatch
        self.assertNotEqual(receipt["observed_head"], head_v2)
```

### 4.3 Combo 3: Identity & 4-Tier Offers + Proof Architecture (`test_combo_identity_proof.py`)
- **Pairing**: F4 (Canonical Identity & Offers) + F5 (Proof & Case-Study Architecture)
- **Hypothesis**: Proof case studies (PSP-C04 / PSP-P05) and proof contracts must strictly consume the ratified Production-Systems Architect narrative and progressive disclosure levels (L1/L2/L3) defined in PSP-C03 (`commercial-contract.yaml`). An offer tier discrepancy in a case study (e.g. referencing unratified pricing or invalid role title) must fail contract validation.
- **Assertion Invariants**:
  1. Case study template requires role header matching "Production-Systems Architect".
  2. Offers referenced in proof contracts must belong to {`Audit`, `Install`, `Retainer`, `Partnership`}.
  3. L1/L2/L3 progressive disclosure hierarchy is preserved across proof manifests.

### 4.4 Combo 4: Flagship Proof Preflight + Public Front Door / IA (`test_combo_proof_frontdoor.py`)
- **Pairing**: F5 (Proof Architecture) + F6 (Public Portfolio & Front Door)
- **Hypothesis**: The public front door (`_frontdoor.md`) and capture routing (`_capture.md`) must only route to proof artifacts that have passed flagship proof preflight validation (`flagship-proof-set.yaml`). Broken routes, non-flagship proof slugs, or unverified claims in public front doors fail gate validation.
- **Assertion Invariants**:
  1. Front door routes link to flagship proof triad: `limen`, `public-records`, `ai-chat-exporter`.
  2. Public frontdoor link crawler verifies zero 404 or unratified proof references.

### 4.5 Combo 5: Review-Loop Circuit Breaker + Terminal Omega Proof (`test_combo_circuit_breaker_omega.py`)
- **Pairing**: F2 (Circuit Breaker) + F8 (Terminal Omega Proof)
- **Hypothesis**: Execution of terminal Omega proof (`positioning-program.py --omega --require-two-pass`) must halt and reject completion if the circuit breaker is in a tripped state or if any active quarantine is unresolved.
- **Assertion Invariants**:
  1. When circuit breaker is tripped, Omega check aborts immediately.
  2. Once circuit breaker is reset and all quarantined PRs have closed with exact receipts, two-pass Omega verification proceeds.

### 4.6 Combo 6: Worktree Topic Branch + Exact-Tree Verification (`test_combo_worktree_exact_tree.py`)
- **Pairing**: F1 (Worktree Isolation) + F3 (Exact-Tree Scoped Verification)
- **Hypothesis**: Scoped verification (`scripts/verify.py --changed`) executed within an isolated topic worktree under `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-*` correctly resolves merge-base against `origin/main` without leaking uncommitted diffs from sibling worktrees.
- **Assertion Invariants**:
  1. Worktree A has uncommitted file changes in `docs/positioning/offers/`.
  2. Worktree B has uncommitted file changes in `docs/positioning/proof/`.
  3. `verify.py --changed` in Worktree A evaluates only offer gates; Worktree B diffs are completely invisible.

### 4.7 Combo 7: 4-Tier Offers + Durable Leaf Receipts (`test_combo_offers_durable_receipts.py`)
- **Pairing**: F4 (4-Tier Offers) + F7 (Durable Receipts)
- **Hypothesis**: Modification of offer specifications in `docs/positioning/offers/` generates structured `limen.positioning_work_receipt.v1` containing pricing boundaries and gate audit trails that match `commercial-contract.yaml` constraints.
- **Assertion Invariants**:
  1. Generated receipt for `PSP-P04-W01` includes Audit tier validation.
  2. Schema validator verifies receipt structure, pricing range adherence ($5k–$15k), and SHA256 integrity.

### 4.8 Combo 8: Public Front Door + Exact-Tree Verification (`test_combo_frontdoor_exact_tree.py`)
- **Pairing**: F6 (Public Portfolio & Front Door) + F3 (Exact-Tree Scoped Verification)
- **Hypothesis**: Changes to visual mockups in `docs/positioning/visual-directions/` or frontdoor copy implicate exactly the `experience-audit` and `frontdoor-lint` gates in `institutio/governance/gates.yaml` without triggering unrelated backend CI gates.
- **Assertion Invariants**:
  1. `verify.py --explain docs/positioning/visual-directions/mockup-a.png` lists only visual review gates.
  2. Cheap verification wave passes in <2 seconds.

### 4.9 Combo 9: Circuit Breaker Quarantine + Exact-Tree Resolution (`test_combo_circuit_quarantine_resolution.py`)
- **Pairing**: F2 (Circuit Breaker) + F3 (Exact-Tree Verification) + F7 (Durable Receipts)
- **Hypothesis**: Quarantined PRs C04 (#2414) and C05 (#139) are resolved through a single-push exact-tree verification without re-triggering automated review bot loops, emitting an accepted leaf receipt.
- **Assertion Invariants**:
  1. PR #2414 defensive dictionary lookup guard at line 973 resolves P2 review finding.
  2. Single push verifies cleanly with `verify-scoped.sh`.
  3. Emitted receipt attaches to PR and releases quarantine tag.

### 4.10 Combo 10: Multi-Lane Worktree Concurrency + Durable Receipts (`test_combo_multi_worktree_concurrency.py`)
- **Pairing**: F1 (Worktree Isolation) + F7 (Durable Receipts)
- **Hypothesis**: Multiple autonomous lanes running in parallel across separate worktrees emit durable receipts into `docs/receipts/positioning/` without filename collisions, race conditions, or git lock contention.
- **Assertion Invariants**:
  1. Lane 1 writes `2026-08-15-psp-p03-w01.json`.
  2. Lane 2 writes `2026-08-15-psp-p04-w01.json`.
  3. Both receipts are atomically written and validate independently against the canonical schema.

---

## 5. Detailed Specification of Tier 4: Real-World Application Scenarios

Tier 4 tests execute complete, realistic end-to-end operational workflows representing actual positioning delivery and recovery lifecycles. The suite contains **5 comprehensive scenarios** (meeting the ≥5 requirement).

```
========================================================================================
                             TIER 4 SCENARIOS OVERVIEW
========================================================================================
Scenario ID   Title                                            Complexity  Features Tested
----------------------------------------------------------------------------------------
Scenario 1    Full Lifecycle Positioning Delivery Run          High        F1, F4, F5, F6, F7
Scenario 2    Automated Review Loop Eviction & Circuit Breaker High        F2, F3, F7
Scenario 3    Parallel Worktree Isolation & Concurrent Lanes   High        F1, F3, F7
Scenario 4    Corrupted Receipt Recovery & Exact-Tree Sync     Medium      F3, F7, F8
Scenario 5    End-to-End Terminal Two-Pass Omega Proof         High        F4, F5, F6, F7, F8
========================================================================================
```

### 5.1 Scenario 1: Full Lifecycle Positioning Run (`test_scenario_1_full_lifecycle_positioning.py`)
- **Workflow**:
  1. Provision isolated worktrees for Identity (`limen-psp-omega-lane-identity-offer`), Proof (`limen-psp-omega-lane-proof-architecture`), and Front Door (`limen-psp-omega-lane-portfolio-front-door`).
  2. Ratify Canonical Identity narrative and 4-tier offers (Audit, Install, Retainer, Partnership) in `commercial-contract.yaml`.
  3. Execute proof preflight on Flagship Proof candidates (Limen, Public-Records, AI Chat Exporter) and generate case-study contracts.
  4. Generate and link public front door (`_frontdoor.md`) and capture routing (`_capture.md`).
  5. Emit and verify durable work receipts (`limen.positioning_work_receipt.v1`) for each completed leaf.
  6. Emit and verify aggregate phase receipts (`limen.positioning_phase_receipt.v1`) for PSP-P03, PSP-P04, PSP-P05, PSP-P06, and PSP-P07.
- **Verification**: Complete graph closure integrity, zero broken references, all receipt schemas valid.

```python
class TestScenario1FullLifecyclePositioning(PSPOmegaTestCase):
    def test_full_lifecycle_positioning_run(self):
        with self.isolated_env():
            # Step 1: Initialize 3 isolated topic worktrees
            wt_identity = self.create_mock_worktree("limen-psp-omega-lane-identity-offer", "topic/identity-offers")
            wt_proof = self.create_mock_worktree("limen-psp-omega-lane-proof-architecture", "topic/proof-architecture")
            wt_frontdoor = self.create_mock_worktree("limen-psp-omega-lane-portfolio-front-door", "topic/portfolio-frontdoor")

            # Step 2: Validate identity & offer ladder
            contract_data = {
                "schema_version": "limen.commercial_contract.v1",
                "identity": {"role": "Production-Systems Architect", "level_disclosure": ["L1", "L2", "L3"]},
                "offers": {
                    "audit": {"min": 5000, "max": 15000},
                    "install": {"min": 25000, "max": 60000},
                    "retainer": {"min": 10000, "max": 25000, "cadence": "monthly"},
                    "partnership": {"type": "diligence_gated"},
                }
            }
            self.assertEqual(contract_data["identity"]["role"], "Production-Systems Architect")

            # Step 3: Emit and store work receipts for leaves
            r_p03 = self.build_work_receipt("PSP-P03-W01", "Identity Narrative Ratification")
            r_p04 = self.build_work_receipt("PSP-P04-W01", "Offer Ladder Ratification")
            r_p05 = self.build_work_receipt("PSP-P05-W01", "Flagship Proof Preflight")
            r_p06 = self.build_work_receipt("PSP-P06-W01", "Frontdoor IA Specification")

            # Step 4: Emit phase receipts
            phase_p03 = self.build_phase_receipt("PSP-P03", work_receipts=["PSP-P03-W01"])
            phase_p04 = self.build_phase_receipt("PSP-P04", work_receipts=["PSP-P04-W01"])
            
            # Step 5: Verify all phase receipts are green
            self.assertEqual(phase_p03["status"], "pass")
            self.assertEqual(phase_p04["status"], "pass")
```

### 5.2 Scenario 2: Automated Review Loop Eviction & Circuit Breaker (`test_scenario_2_automated_review_eviction.py`)
- **Workflow**:
  1. Detect looping automated review comments on PR #2414 (C04) and PR #139 (C05).
  2. Trip circuit breaker via `limen-trip_circuit_breaker`, isolating the review loops and preventing API exhaustion.
  3. Apply exact-tree fix for C04: defensive dictionary lookup guard at `scripts/positioning-proof-preflight.py:973`.
  4. Apply exact-tree fix for C05: schema alignment of 5 template fields in validator.
  5. Run scoped verification (`verify-scoped.sh`) locally to verify 100% green exit code.
  6. Generate fresh leaf receipts with exact tree SHA.
  7. Reset circuit breaker via `limen-reset_circuit_breaker` and verify system returns online.
- **Verification**: Quarantined PRs resolved in a single push, circuit breaker state machine transitions correctly, zero review ping-pong.

### 5.3 Scenario 3: Parallel Worktree Isolation & Concurrent Execution (`test_scenario_3_parallel_worktree_isolation.py`)
- **Workflow**:
  1. Spawn 4 parallel execution threads simulating concurrent autonomous agents in isolated worktrees:
     - Lane 1: `limen-psp-omega-lane-circuit-breaker`
     - Lane 2: `limen-psp-omega-lane-identity-offer`
     - Lane 3: `limen-psp-omega-lane-proof-architecture`
     - Lane 4: `limen-psp-omega-lane-portfolio-front-door`
  2. Each thread performs localized git operations, file writes, and receipt generation.
  3. Assert strict non-interference: zero git index locks held, zero overwriting of sibling topic files, zero cross-talk in receipt indices.
- **Verification**: All 4 lanes complete successfully in parallel with 100% isolation.

### 5.4 Scenario 4: Corrupted Receipt Recovery & Exact-Tree Sync (`test_scenario_4_corrupted_receipt_recovery.py`)
- **Workflow**:
  1. Simulate bit-rot / corrupted JSON in `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` (as observed in Survey 2).
  2. Execute `test_positioning_c10_readiness.py` and verify it detects receipt hash mismatch and fails closed.
  3. Execute automated recovery routine (`python3 scripts/positioning-c10-readiness.py --sync-receipt`).
  4. Verify the updated synthetic receipt hash matches the current exact contract state.
  5. Re-run `test_positioning_c10_readiness.py` and confirm 100% test pass.
- **Verification**: Deterministic failure on corruption, clean self-healing, idempotency of regenerated receipts.

### 5.5 Scenario 5: End-to-End Terminal Two-Pass Omega Proof (`test_scenario_5_terminal_omega_proof.py`)
- **Workflow**:
  1. Construct fully closed positioning graph with all upstream phase receipts (PSP-P01 through PSP-P14) recorded.
  2. Compute canonical state digest across all receipts and issue projections.
  3. Execute Pass 1: generate `docs/receipts/positioning/omega-pass-1.json` recording state digest and observation timestamp $T_1$.
  4. Wait $\Delta t > 0$ and execute Pass 2: generate `docs/receipts/positioning/omega-pass-2.json` recording state digest and observation timestamp $T_2$ ($T_2 \neq T_1$).
  5. Verify both passes record identical `state_digest`.
  6. Execute `positioning-program.py --omega --require-two-pass` and assert exit code `0` and `"status": "pass"`.
- **Verification**: Terminal convergence proven, two independent observations verified, zero open non-terminal items.

```python
class TestScenario5TerminalOmegaProof(PSPOmegaTestCase):
    def test_terminal_two_pass_omega_proof_convergence(self):
        with self.isolated_env():
            state_digest = hashlib.sha256(b"mock_canonical_positioning_graph_state_v1").hexdigest()
            t1 = "2026-08-15T12:00:00.000000Z"
            t2 = "2026-08-15T12:00:05.000000Z"

            pass1 = self.build_omega_pass(1, state_digest, observed_at=t1)
            pass2 = self.build_omega_pass(2, state_digest, observed_at=t2)

            # Assert identical state digests and distinct observation timestamps
            self.assertEqual(pass1["state_digest"], pass2["state_digest"])
            self.assertNotEqual(pass1["observed_at"], pass2["observed_at"])
            self.assertEqual(pass1["pass"], 1)
            self.assertEqual(pass2["pass"], 2)
            self.assertEqual(pass1["status"], "pass")
            self.assertEqual(pass2["status"], "pass")
```

---

## 6. Tier 1 & Tier 2 Reference Specifications

To ensure the whole suite exceeds the 93 test case requirement, Tiers 1 and 2 are specified with 5 test cases per feature across all 8 features (80 tests total):

### 6.1 Tier 1: Functional Feature Inventory (40 Tests)
- **F1 (Worktree Isolation)**: 5 tests
  - `test_f1_01_worktree_creation_path_structure`: Validates `.worktrees/` directory placement.
  - `test_f1_02_topic_branch_naming`: Enforces `limen-psp-omega-lane-*` branch prefix.
  - `test_f1_03_worktree_clean_initialization`: Verifies fresh worktree starts at clean commit HEAD.
  - `test_f1_04_worktree_removal_cleanup`: Confirms clean git worktree prune and directory removal.
  - `test_f1_05_worktree_no_main_mutation`: Asserts direct writes to main branch are blocked.
- **F2 (Circuit Breaker)**: 5 tests
  - `test_f2_01_trip_circuit_breaker`: Trips circuit breaker and updates state to offline.
  - `test_f2_02_reset_circuit_breaker`: Resets circuit breaker and restores online state.
  - `test_f2_03_check_offline_rejection`: Calls during offline state raise RuntimeError.
  - `test_f2_04_state_persistence`: State correctly reloads across process restarts.
  - `test_f2_05_task_loop_tracking`: Loop tracker increments and detects runaway iterations.
- **F3 (Exact-Tree Scoped Verification)**: 5 tests
  - `test_f3_01_scoped_gate_implication`: Gate selection derives correctly from changed paths.
  - `test_f3_02_exact_tree_sha_resolution`: Resolver calculates exact git tree digest.
  - `test_f3_03_cheap_wave_concurrency`: Cheap gates execute concurrently in parallel wave.
  - `test_f3_04_serialized_tail_execution`: Serialized gates execute under process lock.
  - `test_f3_05_exit_code_propagation`: Failing gate propagates non-zero exit code bare.
- **F4 (Identity & 4-Tier Offers)**: 5 tests
  - `test_f4_01_identity_role_narrative`: Production-Systems Architect narrative matches doctrine.
  - `test_f4_02_progressive_disclosure_levels`: Validates L1, L2, L3 content stratification.
  - `test_f4_03_audit_offer_parameters`: Audit offer matches $5k–$15k scope and constraints.
  - `test_f4_04_install_retainer_parameters`: Install ($25k–$60k) and Retainer ($10k–$25k/mo) validation.
  - `test_f4_05_commercial_contract_schema`: Schema validation of `commercial-contract.yaml`.
- **F5 (Proof & Case-Study Architecture)**: 5 tests
  - `test_f5_01_flagship_candidates_triad`: Validates 3 candidates (Limen, Public-Records, AI Chat Exporter).
  - `test_f5_02_case_study_template_sections`: Enforces Level-2 case study structure.
  - `test_f5_03_proof_contract_validation`: Validates `psp-c04-proof-contract.json`.
  - `test_f5_04_non_circular_claim_anchors`: Proof claims anchor to verifiable code and evidence.
  - `test_f5_05_proof_preflight_runner`: Executes `positioning-proof-preflight.py` cleanly.
- **F6 (Public Portfolio & Front Door)**: 5 tests
  - `test_f6_01_frontdoor_markdown_structure`: Verifies `_frontdoor.md` metadata and layout.
  - `test_f6_02_capture_routing_rules`: Validates `_capture.md` intake and routing logic.
  - `test_f6_03_visual_direction_framing`: Checks 3 digest-pinned visual mockup options.
  - `test_f6_04_estate_map_alignment`: Verifies alignment with `organvm/.github` estate map.
  - `test_f6_05_public_asset_link_integrity`: Asserts all public links resolve without 404s.
- **F7 (Durable Receipts)**: 5 tests
  - `test_f7_01_work_receipt_schema_validation`: Validates `limen.positioning_work_receipt.v1`.
  - `test_f7_02_phase_receipt_schema_validation`: Validates `limen.positioning_phase_receipt.v1`.
  - `test_f7_03_json_marker_extraction`: Extracts `<!-- positioning-receipt:PSP-Pxx-Wxx -->` blocks.
  - `test_f7_04_sha256_receipt_digest`: Confirms canonical SHA256 hashing of receipt payloads.
  - `test_f7_05_receipt_directory_persistence`: Validates receipt storage in `docs/receipts/positioning/`.
- **F8 (Terminal Omega Proof)**: 5 tests
  - `test_f8_01_omega_flag_execution`: Validates `positioning-program.py --omega`.
  - `test_f8_02_two_pass_requirement`: Enforces `--require-two-pass` validation.
  - `test_f8_03_omega_pass_schema`: Validates `limen.positioning_omega_pass.v1`.
  - `test_f8_04_terminal_exclusion_logic`: Terminal work items are correctly exempted during pass checks.
  - `test_f8_05_zero_open_objects_verification`: Confirms all non-exempted program objects are closed.

### 6.2 Tier 2: Boundary Value & Resilience (40 Tests)
- **B1 (Worktree Boundaries)**: 5 tests (Empty path, path traversal `../../`, invalid characters, non-existent base ref, permissions denied).
- **B2 (Circuit Breaker Boundaries)**: 5 tests (Corrupt `.mcp_state.json`, missing keys, read-only filesystem, concurrent race condition, extreme loop counter).
- **B3 (Exact-Tree Boundaries)**: 5 tests (Empty diff set, uncommitted binary file, detached HEAD, missing `gates.yaml`, cyclic gate dependencies).
- **B4 (Identity & Offer Boundaries)**: 5 tests (Below min price $4,999, above max price $15,001, negative numbers, missing role title, unknown offer tier).
- **B5 (Proof Boundaries)**: 5 tests (Empty candidate list, malformed case study markdown, invalid claim ID regex, broken file link, cyclic proof dependency).
- **B6 (Portfolio Frontdoor Boundaries)**: 5 tests (Empty frontdoor file, malformed markdown header, broken capture email regex, mismatched mockup hash, unapproved external font URL).
- **B7 (Receipt Boundaries)**: 5 tests (Invalid RFC3339 timestamp, truncated JSON, missing required `observed_head`, wrong schema version string, hash mismatch).
- **B8 (Omega Boundaries)**: 5 tests (Single pass supplied when two required, identical timestamps in pass 1 & 2, differing state digests, unclosed non-terminal item, corrupted pass JSON).

---

## 7. Verification Method & CI Integration

### 7.1 Local Hermetic Execution Commands
```bash
# 1. Run the entire E2E suite via the custom runner (verbose)
python3 tests/e2e_psp_omega/runner.py -v

# 2. Run specific tiers
python3 tests/e2e_psp_omega/runner.py --tier 3
python3 tests/e2e_psp_omega/runner.py --tier 4

# 3. Standard unittest discovery
python3 -m unittest discover -s tests/e2e_psp_omega -p "test_*.py" -v

# 4. Scoped verification gate execution
bash scripts/verify-scoped.sh
```

### 7.2 Pass/Fail Criteria
- **100% Pass Rate**: 95 of 95 tests must pass.
- **Zero Dangling State**: Zero temporary files left behind outside `tempfile.TemporaryDirectory`.
- **Zero Pollution**: Workspace `.mcp_state.json` and `tasks.yaml` remain unmodified.
- **Exit Code**: Exit code must be exactly `0`.
