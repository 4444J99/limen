"""Regression tests for scripts/dispatch-async.py's reap_stale marker/lock ordering.

The lock-honoring fix deferred the `.running` marker unlink until AFTER the reopen is committed
under the queue lock — so a lock timeout can no longer leave a leaked slot (marker gone, task still
'dispatched'). These tests pin the normal (lock-acquired) behavior the restructure must preserve:
a stale marker reopens its task AND removes the marker; a marker with a result file present is left
for harvest.
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import LimenFile, Task  # noqa: E402

_spec = importlib.util.spec_from_file_location("dispatch_async", str(ROOT / "scripts" / "dispatch-async.py"))
dispatch_async = importlib.util.module_from_spec(_spec)
sys.modules["dispatch_async"] = dispatch_async
_spec.loader.exec_module(dispatch_async)


@pytest.fixture
def board(tmp_path, monkeypatch):
    """A tmp tasks.yaml + async-runs dir wired into the module's module-level path constants."""
    tasks_path = tmp_path / "tasks.yaml"
    runs = tmp_path / "logs" / "async-runs"
    runs.mkdir(parents=True)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[Task(id="T1", title="t", target_agent="jules", status="dispatched", created=date(2026, 7, 1))]
        ),
    )
    monkeypatch.setattr(dispatch_async, "TASKS", tasks_path)
    monkeypatch.setattr(dispatch_async, "RUNS", runs)
    return tasks_path, runs


def _old_marker(runs: Path, tid: str, agent: str) -> Path:
    marker = runs / f"{tid}__{agent}.running"
    marker.write_text((dispatch_async._now().replace(year=2020)).isoformat())  # ancient → always stale
    return marker


def test_reap_stale_reopens_and_removes_marker(board):
    tasks_path, runs = board
    marker = _old_marker(runs, "T1", "jules")

    reaped = dispatch_async.reap_stale(max_age_s=1)

    assert reaped == ["T1"]
    assert not marker.exists()  # marker removed — but only AFTER the reopen committed
    got = {t.id: t for t in load_limen_file(tasks_path).tasks}
    assert got["T1"].status == "open"  # dead worker's task reopened for retry


def test_reap_stale_leaves_marker_when_result_present(board):
    tasks_path, runs = board
    marker = _old_marker(runs, "T1", "jules")
    (runs / "T1.result.json").write_text("{}")  # worker actually finished → harvest's job, not reap's

    reaped = dispatch_async.reap_stale(max_age_s=1)

    assert reaped == []
    assert marker.exists()  # left in place for harvest
    got = {t.id: t for t in load_limen_file(tasks_path).tasks}
    assert got["T1"].status == "dispatched"  # untouched
