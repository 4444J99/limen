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
