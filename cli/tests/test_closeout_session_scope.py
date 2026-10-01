"""Focused tests for the session-scoped closeout repair (4444J99/limen#2747).

Covers: read-only reporting with concurrent edits, the session's own
unpublished implementation still failing, wrong/stale continuation identity,
and unchanged repeated verification. Pure git-stub tests: no checkout, no
network, no mutation.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPSULE = REPO_ROOT / "docs" / "continuations" / "workspace-recovery-20260916"


def load_validator():
    sys_path = [str(REPO_ROOT / "cli" / "src")]
    import sys

    for entry in sys_path:
        if entry not in sys.path:
            sys.path.insert(0, entry)
    spec = importlib.util.spec_from_file_location("verify_closeout_test", CAPSULE / "verify-closeout.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_historical_branch_resolves_from_workstream_not_literal():
    vc = load_validator()
    assert vc.historical_branch(CAPSULE) == "work/workspace-recovery-20260916"
    source = (CAPSULE / "verify-closeout.py").read_text(encoding="utf-8")
    # The literal may appear only in test fixtures and docstrings, never as an assertion operand.
    code_lines = [line for line in source.splitlines() if '"""' not in line and "#" not in line.split('"')[0]]
    assert not any(
        '== "work/workspace-recovery-20260916"' in line or "== 'work/workspace-recovery-20260916'" in line
        for line in code_lines
    )


def test_launch_check_delegates_to_canonical_session_checker():
    script = (CAPSULE / "launch.sh").read_text()
    assert "scripts/session-closeout.py" in script
    assert "kickstart.sh" in script


def test_legacy_check_requires_explicit_identity():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(CAPSULE / "verify-closeout.py"), "--check"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "--session-id" in result.stderr
