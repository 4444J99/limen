from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run-pytest-hermetic.sh"


def test_runner_scrubs_the_complete_limen_runtime_namespace(tmp_path: Path) -> None:
    probe = tmp_path / "test_environment_probe.py"
    probe.write_text(
        "import os\n\n"
        "def test_no_limen_runtime_state_leaks():\n"
        "    assert not [name for name in os.environ if name.startswith('LIMEN_')]\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "LIMEN_CONDUCTOR_SESSION_ID": "ambient-conductor",
        "LIMEN_CONDUCT_TOKEN": "ambient-secret",
        "LIMEN_HUMAN_PROTECTED": "1",
        "LIMEN_RUN_ID": "ambient-run",
        "LIMEN_WORKSTREAM_DEADLINE_EPOCH": "1785195283",
        "LIMEN_WORKSTREAM_STARTED_EPOCH": "1785166483",
    }

    result = subprocess.run(
        ["bash", str(RUNNER), str(probe), "-q"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
