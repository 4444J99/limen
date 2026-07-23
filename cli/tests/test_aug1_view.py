from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "aug1-view.py"


def test_aug1_view_fails_false_on_wrong_shaped_state(tmp_path: Path):
    state = tmp_path / "state" / "aug1"
    state.mkdir(parents=True)
    (tmp_path / "logs").mkdir()
    (tmp_path / "his-hand-levers.json").write_text(json.dumps({"levers": ["not-a-row"]}))
    (state / "revenue-received.json").write_text(
        json.dumps({"received": [{"cents": "bad", "at": "not-a-date"}, "not-a-row"]})
    )
    (state / "engagements.json").write_text(json.dumps({"engagements": ["not-a-row"]}))

    env = dict(os.environ)
    env["LIMEN_ROOT"] = str(tmp_path)
    env["AUG1_LIFE_FILE"] = str(tmp_path / "missing-life.json")

    run = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert run.returncode == 0, run.stderr
    view = json.loads((tmp_path / "logs" / "aug1-view.json").read_text())
    assert view["gate"]["pass"] is False
    assert view["ledger"]["received_total_cents"] == 0
    assert view["ledger"]["trailing7_cents"] == 0
    assert view["ledger"]["engagements"] == 0
    assert view["ledger"]["signed"] == 0
