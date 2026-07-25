from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "agent-state-metabolism.py"


def test_resume_requires_explicit_run_id(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cold-tree",
            "codex-sessions",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--resume",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--resume requires --run-id" in result.stderr


def test_cloud_eviction_requires_both_signed_inputs(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--evict",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--evict requires --eviction-authorization and --eviction-signature" in result.stderr


def test_cloud_authorization_plan_requires_principal(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--prepare-eviction-authorization",
            str(tmp_path / "authorization.json"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "requires --eviction-authorizer" in result.stderr


def test_exact_retention_rejects_age_or_size_heuristics(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cold-tree",
            "opencode-residual",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--retain-relative",
            "opencode.db",
            "--hot-days",
            "0",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--retain-relative cannot be combined" in result.stderr


def test_cloud_restore_requires_path_free_receipt_pair(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--restore-item-hash",
            "a" * 64,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--restore-item-hash and --restore-receipt are required together" in result.stderr


def test_cloud_restore_cannot_be_combined_with_eviction(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "cloudkit-materialized",
            "icloud-drive",
            "--root",
            str(tmp_path),
            "--private-receipt",
            str(tmp_path / "receipt.json"),
            "--run-id",
            "run",
            "--resume",
            "--restore-item-hash",
            "a" * 64,
            "--restore-receipt",
            str(tmp_path / "restore.json"),
            "--evict",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "item restoration cannot be combined with eviction operations" in result.stderr
