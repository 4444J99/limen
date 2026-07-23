import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_drain_census_is_counts_only(tmp_path):
    limen = tmp_path / "limen"
    home = tmp_path / "home"
    (limen / "logs").mkdir(parents=True)
    home.mkdir()
    tasks = limen / "tasks.yaml"
    tasks.write_text(
        """
tasks:
  - id: PRIVATE-OPEN
    title: private task title
    status: open
  - id: PRIVATE-DONE
    title: private done title
    status: done
""",
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "drain.sh"), "--census"],
        capture_output=True,
        text=True,
        env={**os.environ, "LIMEN_ROOT": str(limen), "LIMEN_TASKS": str(tasks), "HOME": str(home)},
        check=True,
    )
    census = json.loads(proc.stdout)
    encoded = json.dumps(census, sort_keys=True)

    assert census["tasks_present"] is True
    assert census["task_status_counts"] == {"done": 1, "open": 1}
    assert census["reclaim_enabled"] is True
    assert census["reclaim_apply_enabled"] is True
    assert "private task title" not in encoded
    assert "PRIVATE-OPEN" not in encoded
