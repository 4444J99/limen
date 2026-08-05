"""Tests for scripts/emit-tick.py — the tick line carries velocity, not just liveness counts.

2026-07-08 incident: throughput collapsed to near-zero while every liveness metric stayed
green. done_delta (completed = done + archived, vs the previous tick) makes velocity visible
in every beat line so a monitor can gate on it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "emit-tick.py"


def _board(done: int, archived: int, open_count: int = 5) -> str:
    tasks = (
        [{"id": f"o{i}", "status": "open"} for i in range(open_count)]
        + [{"id": f"d{i}", "status": "done"} for i in range(done)]
        + [{"id": f"a{i}", "status": "archived"} for i in range(archived)]
    )
    return json.dumps({"tasks": tasks, "portal": {"budget": {"daily": 600, "per_agent": {}, "track": {"spent": 10}}}})


def _run(root: Path) -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        env={"LIMEN_ROOT": str(root), "PATH": "/usr/bin:/bin"},
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _last_record(root: Path) -> dict:
    lines = (root / "logs" / "ticks.jsonl").read_text().strip().splitlines()
    return json.loads(lines[-1])


def test_first_tick_has_null_delta(tmp_path):
    (tmp_path / "tasks.yaml").write_text(_board(done=3, archived=1))
    out = _run(tmp_path)
    rec = _last_record(tmp_path)
    assert rec["done_delta"] is None
    assert "done_delta=n/a" in out


def test_delta_counts_new_completions(tmp_path):
    (tmp_path / "tasks.yaml").write_text(_board(done=3, archived=1))
    _run(tmp_path)
    (tmp_path / "tasks.yaml").write_text(_board(done=7, archived=1))
    out = _run(tmp_path)
    rec = _last_record(tmp_path)
    assert rec["done_delta"] == 4
    assert "done_delta=4" in out


def test_archival_transition_does_not_fake_a_drop(tmp_path):
    # 5 done tasks archive: done 5→0, archived 0→5 — completed is unchanged, delta must be 0.
    (tmp_path / "tasks.yaml").write_text(_board(done=5, archived=0))
    _run(tmp_path)
    (tmp_path / "tasks.yaml").write_text(_board(done=0, archived=5))
    _run(tmp_path)
    assert _last_record(tmp_path)["done_delta"] == 0


def test_garbage_previous_line_falls_back_to_null(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "ticks.jsonl").write_text("not json\n")
    (tmp_path / "tasks.yaml").write_text(_board(done=2, archived=0))
    _run(tmp_path)
    assert _last_record(tmp_path)["done_delta"] is None
