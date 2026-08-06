from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run-pytest-hermetic.sh"


def test_runner_scrubs_the_complete_limen_runtime_namespace(tmp_path: Path) -> None:
    """The child's LIMEN_ namespace is DETERMINED BY THE WRAPPER, never inherited.

    The invariant is not "nothing survives" — it is "nothing *ambient* survives, and what
    does survive is a constant the wrapper pins." Those coincided until the wrapper had to
    re-arm LIMEN_NOTIFY (the osascript kill-switch) after the scrub: that guard is an
    OUTPUT-side safety, not a test input, and scrubbing it restored _notify's "1" default —
    i.e. the hermetic runner was re-enabling an effector a caller had deliberately silenced.

    So this asserts the sharper property in both directions: every ambient LIMEN_ below is
    gone, and the one survivor is pinned to the wrapper's value REGARDLESS of what the
    parent set. LIMEN_NOTIFY=1 is injected ambiently on purpose — inheriting it would be
    the exact regression, and it is invisible to a test that only checks for absence.
    """
    probe = tmp_path / "test_environment_probe.py"
    probe.write_text(
        "import os\n\n"
        "def test_limen_namespace_is_wrapper_determined():\n"
        "    leaked = {n: v for n, v in os.environ.items() if n.startswith('LIMEN_')}\n"
        "    assert set(leaked) == {'LIMEN_NOTIFY'}, leaked\n"
        "    assert leaked['LIMEN_NOTIFY'] == '0', leaked\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "LIMEN_CONDUCTOR_SESSION_ID": "ambient-conductor",
        "LIMEN_CONDUCT_TOKEN": "ambient-secret",
        "LIMEN_HUMAN_PROTECTED": "1",
        "LIMEN_NOTIFY": "1",
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
