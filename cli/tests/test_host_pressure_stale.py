"""Tests for scripts/host-pressure-stale.py — the watch-the-watcher rung (sensor 0o).

Hermetic: LIMEN_ROOT points at a tmp fixture tree, never the live logs/vigilia seat.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "host-pressure-stale.py"


def run_stale(tmp_path: Path, env: dict | None = None):
    child_env = os.environ.copy()
    child_env["LIMEN_ROOT"] = str(tmp_path)
    child_env.pop("LIMEN_VIGILIA", None)
    child_env.pop("LIMEN_VITALS_STALE_BEATS", None)
    child_env.pop("LIMEN_LOOP_MAX", None)
    if env:
        child_env.update(env)
    return subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, env=child_env)


def write_status(tmp_path: Path, ts: datetime) -> None:
    seat = tmp_path / "logs" / "vigilia"
    seat.mkdir(parents=True, exist_ok=True)
    (seat / "status.json").write_text(json.dumps({"ts": ts.isoformat()}))


def test_fresh_record_is_ok(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc))
    proc = run_stale(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout


def test_stale_record_fails(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(hours=6))
    proc = run_stale(tmp_path)  # budget: 3 x 1800s = 90 min
    assert proc.returncode == 1
    assert "flying blind" in proc.stdout


def test_absent_seat_fails_while_vigilia_on(tmp_path):
    proc = run_stale(tmp_path)
    assert proc.returncode == 1
    assert "absent" in proc.stdout


def test_vigilia_off_is_ok(tmp_path):
    proc = run_stale(tmp_path, env={"LIMEN_VIGILIA": "0"})
    assert proc.returncode == 0


def test_unreadable_ts_fails(tmp_path):
    seat = tmp_path / "logs" / "vigilia"
    seat.mkdir(parents=True, exist_ok=True)
    (seat / "status.json").write_text("{not json")
    proc = run_stale(tmp_path)
    assert proc.returncode == 1


def test_budget_derives_from_env(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(minutes=10))
    # 2 beats x 120s = 4 min budget -> a 10-min-old record is stale
    proc = run_stale(tmp_path, env={"LIMEN_VITALS_STALE_BEATS": "2", "LIMEN_LOOP_MAX": "120"})
    assert proc.returncode == 1
