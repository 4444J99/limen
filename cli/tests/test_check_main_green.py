"""Tests for scripts/check-main-green.py — the trunk-green invariant sensor.

Verdicts are injected via the cache stamp (logs/main-green.json under a tmp LIMEN_ROOT) with a large
throttle, so the test never calls live `gh`. The emit path writes into a tmp tasks.yaml.
"""

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-main-green.py"

sys.path.insert(0, str(ROOT / "cli" / "src"))
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import Budget, BudgetTrack, LimenFile, Portal  # noqa: E402


def _seed(tmp: Path, conclusion: str) -> None:
    logs = tmp / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "main-green.json").write_text(
        json.dumps(
            {
                "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "conclusion": conclusion,
                "head_sha": "deadbeef",
                "url": "https://github.com/organvm/limen/actions/runs/1",
            }
        ),
        encoding="utf-8",
    )


def _empty_board(tmp: Path) -> Path:
    tasks = tmp / "tasks.yaml"
    today = dt.date.today()
    save_limen_file(
        tasks,
        LimenFile(
            portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=today.isoformat()))),
            tasks=[],
        ),
    )
    return tasks


def run(tmp: Path, *extra, apply=False):
    env = {
        "LIMEN_ROOT": str(tmp),
        "LIMEN_TASKS": str(tmp / "tasks.yaml"),
        "LIMEN_MAIN_GREEN_THROTTLE": "100000",  # force cache use
        "LIMEN_MAIN_GREEN_APPLY": "1" if apply else "0",
        "PATH": "/usr/bin:/bin",
    }
    import os

    child = os.environ.copy()
    child.update(env)
    return subprocess.run([sys.executable, str(CHECK), *extra], capture_output=True, text=True, env=child)


def test_green_verdict_exits_zero(tmp_path):
    _seed(tmp_path, "success")
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "GREEN" in r.stdout


def test_red_verdict_detection_only(tmp_path):
    _seed(tmp_path, "failure")
    _empty_board(tmp_path)
    r = run(tmp_path)  # APPLY off
    assert r.returncode == 1, r.stdout
    assert "RED" in r.stdout and "detection-only" in r.stdout
    # detection-only must NOT write a task
    assert not load_limen_file(tmp_path / "tasks.yaml").tasks


def test_red_verdict_emits_one_idempotent_task(tmp_path):
    _seed(tmp_path, "failure")
    _empty_board(tmp_path)
    r = run(tmp_path, apply=True)
    assert r.returncode == 1, r.stdout
    tasks = load_limen_file(tmp_path / "tasks.yaml").tasks
    assert len(tasks) == 1
    assert tasks[0].id == "HEAL-mainred-organvm-limen-deadbeef"
    assert tasks[0].priority == "critical" and "mainred" in tasks[0].labels
    # idempotent: a second run adds nothing
    run(tmp_path, apply=True)
    assert len(load_limen_file(tmp_path / "tasks.yaml").tasks) == 1


def test_fail_open_when_status_unavailable(tmp_path):
    # no cache seeded + no gh on PATH → gh call fails → unknown → exit 0 (never break the beat)
    r = run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "SKIP" in r.stdout
