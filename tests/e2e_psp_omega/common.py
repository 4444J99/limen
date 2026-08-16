"""Common Sandboxing, Mocking, and Assertion Helpers for PSP Omega E2E Tests."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_module_from_path(module_name: str, file_path: Path) -> types.ModuleType:
    """Load a Python module dynamically from an arbitrary filesystem path."""
    if not file_path.exists():
        raise FileNotFoundError(f"Module file not found: {file_path}")
    loader = importlib.machinery.SourceFileLoader(module_name, str(file_path))
    spec = importlib.util.spec_from_loader(module_name, loader)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to create spec for module {module_name} at {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def get_positioning_program_module() -> types.ModuleType:
    """Get or load scripts/positioning-program.py."""
    return load_module_from_path(
        "positioning_program_e2e", REPO_ROOT / "scripts" / "positioning-program.py"
    )


def get_positioning_commercial_contract_module() -> types.ModuleType:
    """Get or load scripts/positioning-commercial-contract.py."""
    return load_module_from_path(
        "positioning_commercial_contract_e2e",
        REPO_ROOT / "scripts" / "positioning-commercial-contract.py",
    )


def get_positioning_proof_preflight_module() -> types.ModuleType:
    """Get or load scripts/positioning-proof-preflight.py."""
    return load_module_from_path(
        "positioning_proof_preflight_e2e",
        REPO_ROOT / "scripts" / "positioning-proof-preflight.py",
    )


def get_generate_positioning_module() -> types.ModuleType:
    """Get or load scripts/generate-positioning.py."""
    return load_module_from_path(
        "generate_positioning_e2e", REPO_ROOT / "scripts" / "generate-positioning.py"
    )


def get_positioning_offer_artifacts_module() -> types.ModuleType:
    """Get or load scripts/positioning-offer-artifacts.py."""
    return load_module_from_path(
        "positioning_offer_artifacts_e2e",
        REPO_ROOT / "scripts" / "positioning-offer-artifacts.py",
    )


def get_positioning_cost_failure_module() -> types.ModuleType:
    """Get or load scripts/positioning-cost-failure-reproduction.py."""
    return load_module_from_path(
        "positioning_cost_failure_reproduction_e2e",
        REPO_ROOT / "scripts" / "positioning-cost-failure-reproduction.py",
    )


def get_positioning_flagship_receipt_module() -> types.ModuleType:
    """Get or load scripts/positioning-flagship-receipt.py."""
    return load_module_from_path(
        "positioning_flagship_receipt_e2e",
        REPO_ROOT / "scripts" / "positioning-flagship-receipt.py",
    )


def get_verify_module() -> types.ModuleType:
    """Get or load scripts/verify.py."""
    return load_module_from_path("verify_script_e2e", REPO_ROOT / "scripts" / "verify.py")


def get_worktree_init_module() -> types.ModuleType:
    """Get or load cli/src/limen/worktree_initialization.py."""
    return load_module_from_path(
        "worktree_initialization_e2e",
        REPO_ROOT / "cli" / "src" / "limen" / "worktree_initialization.py",
    )


def get_mcp_server_module() -> types.ModuleType:
    """Get or load mcp/src/limen_mcp/server.py."""
    return load_module_from_path(
        "limen_mcp_server_e2e", REPO_ROOT / "mcp" / "src" / "limen_mcp" / "server.py"
    )


class PSPOmegaTestCase(unittest.TestCase):
    """Base test case providing isolated file sandboxes and fixture helpers."""

    def setUp(self) -> None:
        super().setUp()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="psp_omega_e2e_")
        self.sandbox_path = Path(self._temp_dir.name).resolve()

        # Structure sandbox paths
        self.sandbox_repo = self.sandbox_path / "repo"
        self.sandbox_repo.mkdir(parents=True)
        self.sandbox_worktrees = self.sandbox_path / ".worktrees"
        self.sandbox_worktrees.mkdir(parents=True)
        self.mcp_state_file = self.sandbox_path / ".mcp_state.json"
        self.tasks_file = self.sandbox_repo / "tasks.yaml"
        self.receipts_dir = self.sandbox_repo / "docs" / "receipts" / "positioning"
        self.receipts_dir.mkdir(parents=True)

        # Initialize hermetic git repo in sandbox_repo
        self._init_sandbox_git_repo()

        # Initialize mock state
        self._init_mock_environment()

    def tearDown(self) -> None:
        # Reset any in-memory MCP state
        try:
            mcp_mod = sys.modules.get("limen_mcp_server_e2e") or sys.modules.get("limen_mcp.server")
            if mcp_mod:
                mcp_mod.CIRCUIT_BREAKER_TRIPPED = False
                if hasattr(mcp_mod, "TASK_LOOP_TRACKER"):
                    mcp_mod.TASK_LOOP_TRACKER.clear()
        except Exception:
            pass

        self._temp_dir.cleanup()
        super().tearDown()

    def _init_sandbox_git_repo(self) -> None:
        """Initialize a valid git repository with standard initial commit."""
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=str(self.sandbox_repo),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "PSP Omega Tester"],
            cwd=str(self.sandbox_repo),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "tester@limen.local"],
            cwd=str(self.sandbox_repo),
            capture_output=True,
            check=True,
        )
        readme = self.sandbox_repo / "README.md"
        readme.write_text("# PSP Omega Sandbox Repo\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=str(self.sandbox_repo),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(self.sandbox_repo),
            capture_output=True,
            check=True,
        )
        self.initial_head = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.sandbox_repo),
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
        )

    def _init_mock_environment(self) -> None:
        """Create baseline mock files in sandbox."""
        self.write_mcp_state(circuit_breaker=False, task_loops={})
        self.tasks_file.write_text("tasks:\n  []\ndispatch_log:\n  []\n", encoding="utf-8")

    def write_mcp_state(
        self, circuit_breaker: bool = False, task_loops: Optional[Dict[str, Any]] = None
    ) -> None:
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
    def isolated_env(
        self, extra_env: Optional[Dict[str, str]] = None
    ) -> Generator[Dict[str, str], None, None]:
        """Context manager with scrubbed and redirected environment variables."""
        old_env = os.environ.copy()
        new_env = old_env.copy()

        # Redirect critical paths
        new_env["LIMEN_ROOT"] = str(self.sandbox_repo)
        new_env["LIMEN_TASKS"] = str(self.tasks_file)
        new_env["LIMEN_MCP_STATE"] = str(self.mcp_state_file)
        new_env["LIMEN_WORKTREE_BASE"] = str(self.sandbox_worktrees)
        new_env["LIMEN_WORKTREES"] = str(self.sandbox_worktrees)
        new_env["PYTHONPATH"] = (
            f"{REPO_ROOT / 'cli' / 'src'}:{REPO_ROOT / 'mcp' / 'src'}:{REPO_ROOT / 'scripts'}:{old_env.get('PYTHONPATH', '')}"
        )

        if extra_env:
            new_env.update(extra_env)

        os.environ.clear()
        os.environ.update(new_env)
        try:
            yield new_env
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def git_commit(
        self, repo_path: Path, filename: str, content: str, commit_msg: str = "Test update"
    ) -> str:
        """Create or modify a file in the repo and commit it, returning the new HEAD SHA."""
        target_file = repo_path / filename
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        subprocess.run(
            ["git", "add", filename],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
        )
        return (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
        )

    def git_branch(self, repo_path: Path, branch_name: str) -> None:
        """Create a new branch in the given repo."""
        subprocess.run(
            ["git", "branch", branch_name],
            cwd=str(repo_path),
            capture_output=True,
            check=True,
        )

    def create_mock_worktree(self, lane_name: str, branch: str) -> Path:
        """Create an isolated worktree directory simulating git worktree add."""
        wt_path = self.sandbox_worktrees / lane_name
        wt_path.mkdir(parents=True, exist_ok=True)
        (wt_path / ".git").write_text(
            f"gitdir: {self.sandbox_repo}/.git/worktrees/{lane_name}\n", encoding="utf-8"
        )
        (wt_path / "LANE.md").write_text(
            f"# Worktree: {lane_name}\nBranch: {branch}\n", encoding="utf-8"
        )
        return wt_path

    def build_work_receipt(
        self,
        work_id: str,
        title: str = "Test Work Item",
        status: str = "pass",
        observed_heads: Optional[Dict[str, str]] = None,
        observed_head: Optional[str] = None,
        acceptance_sha256: Optional[str] = None,
        predicate_command: str = "pytest tests/test_example.py",
        authority: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build schema-valid limen.positioning_work_receipt.v1."""
        now = (
            datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
        heads = observed_heads or {"organvm/limen": observed_head or "a" * 40}
        auth = authority or {
            "kind": "broker",
            "run_id": "run-001",
            "lease_id": "lease-001",
            "executor": "test-agent",
        }
        return {
            "schema_version": "limen.positioning_work_receipt.v1",
            "work_id": work_id,
            "title": title,
            "status": status,
            "acceptance_sha256": acceptance_sha256 or hashlib.sha256(b"mock_acceptance").hexdigest(),
            "authority": auth,
            "observed_heads": heads,
            "predicate": {
                "command": predicate_command,
                "exit_code": 0 if status == "pass" else 1,
                "output_sha256": hashlib.sha256(b"mock_output").hexdigest(),
                "executed_at": now,
            },
            "recorded_at": now,
        }

    def build_phase_receipt(
        self,
        phase_id: str,
        status: str = "pass",
        work_receipts: Optional[List[str]] = None,
        exit_gate_sha256: Optional[str] = None,
        child_receipts_sha256: Optional[str] = None,
        remote_state_sha256: Optional[str] = None,
        parity_sha256: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build schema-valid limen.positioning_phase_receipt.v1."""
        now = (
            datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
        return {
            "schema_version": "limen.positioning_phase_receipt.v1",
            "phase_id": phase_id,
            "status": status,
            "exit_gate_sha256": exit_gate_sha256 or hashlib.sha256(b"mock_exit_gate").hexdigest(),
            "child_receipts_sha256": child_receipts_sha256
            or hashlib.sha256(b"mock_child_receipts").hexdigest(),
            "remote_state_sha256": remote_state_sha256
            or hashlib.sha256(b"mock_remote_state").hexdigest(),
            "parity_sha256": parity_sha256 or hashlib.sha256(b"mock_parity").hexdigest(),
            "work_receipts": work_receipts or [],
            "predicate": {
                "command": f"python3 scripts/positioning-program.py --phase-proof {phase_id}",
                "exit_code": 0 if status == "pass" else 1,
                "output_sha256": hashlib.sha256(b"mock_phase_output").hexdigest(),
                "executed_at": now,
            },
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
        now = (
            observed_at
            or datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
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
