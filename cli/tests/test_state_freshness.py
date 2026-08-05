"""Tests for scripts/state-freshness.py — the generic "did this state file freeze?" guard.

Hermetic: LIMEN_ROOT points at a tmp fixture tree; LIMEN_NOTIFY=0 so dedup bookkeeping
runs but no macOS notification ever pops. Mirrors test_host_pressure_stale.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "state-freshness.py"

MAX_AGE = "46800"  # 13h, the opportunity-status default


def run(tmp_path: Path, *args: str):
    env = os.environ.copy()
    env["LIMEN_ROOT"] = str(tmp_path)
    env["LIMEN_NOTIFY"] = "0"
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)


def write_status(tmp_path: Path, ts: datetime, name: str = "status.json") -> Path:
    p = tmp_path / "logs" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"generated_at": ts.isoformat().replace("+00:00", "Z")}))
    return p


def test_fresh_is_ok(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc))
    proc = run(tmp_path, "--file", "logs/status.json", "--max-age-seconds", MAX_AGE)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout


def test_old_is_stale(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(hours=20))
    proc = run(tmp_path, "--file", "logs/status.json", "--max-age-seconds", MAX_AGE)
    assert proc.returncode == 1
    assert "STALE" in proc.stdout


def test_absent_file_is_stale(tmp_path):
    proc = run(tmp_path, "--file", "logs/nope.json", "--max-age-seconds", MAX_AGE)
    assert proc.returncode == 1
    assert "absent" in proc.stdout


def test_missing_field_is_stale(tmp_path):
    p = tmp_path / "logs" / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"other": 1}))
    proc = run(tmp_path, "--file", "logs/status.json", "--max-age-seconds", MAX_AGE)
    assert proc.returncode == 1
    assert "generated_at" in proc.stdout


def test_unparseable_timestamp_is_stale(tmp_path):
    p = tmp_path / "logs" / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"generated_at": "not-a-date"}))
    proc = run(tmp_path, "--file", "logs/status.json", "--max-age-seconds", MAX_AGE)
    assert proc.returncode == 1
    assert "unparseable" in proc.stdout


def test_absolute_path_and_custom_field(tmp_path):
    p = tmp_path / "custom.json"
    p.write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat()}))
    proc = run(tmp_path, "--file", str(p), "--field", "ts", "--max-age-seconds", MAX_AGE)
    assert proc.returncode == 0, proc.stdout + proc.stderr
