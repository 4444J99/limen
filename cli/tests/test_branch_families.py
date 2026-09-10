"""Regression tests for generated branch-family governance."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check-branch-families.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python3", str(CHECKER), *args], capture_output=True, text=True)


def test_branch_constitution_matches_its_registry() -> None:
    result = run("--branch", "main", "--branch", "successor/keeper-publication-recovery")
    assert result.returncode == 0, result.stderr


def test_unknown_branch_is_rejected() -> None:
    result = run("--branch", "unowned-experiment")
    assert result.returncode == 1
    assert "expected exactly one owning family" in result.stderr
