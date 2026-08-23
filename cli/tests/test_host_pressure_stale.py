"""Tests for scripts/host-pressure-stale.py — the watch-the-watcher rung (sensor 0o).

Hermetic: LIMEN_ROOT points at a tmp fixture tree, never the live logs/vigilia seat.
"""

from __future__ import annotations

import json
import os
import hashlib
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "host-pressure-stale.py"


def run_stale(tmp_path: Path, env: dict | None = None, extra_args: list[str] | None = None):
    child_env = os.environ.copy()
    child_env["LIMEN_ROOT"] = str(tmp_path)
    child_env["LIMEN_NOTIFY"] = "0"  # dedup bookkeeping only — hermetic runs never pop notifications
    child_env["LIMEN_ENV_FILE"] = str(tmp_path / "missing-limen.env")
    child_env.pop("LIMEN_VIGILIA", None)
    child_env.pop("LIMEN_VITALS_STALE_BEATS", None)
    child_env.pop("LIMEN_VITALS_SAMPLE_SECONDS", None)
    child_env.pop("LIMEN_VITALS_SAMPLE_TIMEOUT", None)
    child_env.pop("LIMEN_HOST_PRESSURE_STALE", None)
    if env:
        child_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(extra_args or [])], capture_output=True, text=True, env=child_env
    )


def write_status(tmp_path: Path, sampled_at: datetime, completed_at: datetime | None = None) -> None:
    seat = tmp_path / "logs" / "vigilia"
    seat.mkdir(parents=True, exist_ok=True)
    boot = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=3)
    age = max(0.0, (datetime.now(timezone.utc) - sampled_at).total_seconds())
    active_now = time.clock_gettime(getattr(time, "CLOCK_UPTIME_RAW", time.CLOCK_MONOTONIC))
    (seat / "status.json").write_text(
        json.dumps(
            {
                "sampled_at": sampled_at.isoformat(),
                "completed_at": completed_at.isoformat() if completed_at else None,
                "boot_identity": hashlib.sha256(boot.stdout.strip().encode()).hexdigest()[:20],
                "sampled_monotonic_seconds": active_now - age,
                "wake_state": "FullWake",
            }
        )
    )


def test_fresh_record_is_ok(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc))
    proc = run_stale(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout


def test_stale_record_fails(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(hours=6))
    proc = run_stale(tmp_path)  # budget: 3 x 300s = 15 min
    assert proc.returncode == 1
    assert "flying blind" in proc.stdout


def test_absent_seat_fails_while_vigilia_on(tmp_path):
    proc = run_stale(tmp_path)
    assert proc.returncode == 1
    assert "absent" in proc.stdout


def test_vigilia_off_is_ok(tmp_path):
    proc = run_stale(tmp_path, env={"LIMEN_VIGILIA": "0"})
    assert proc.returncode == 0


def test_watchdog_off_is_ok_without_a_sample(tmp_path):
    proc = run_stale(tmp_path, env={"LIMEN_HOST_PRESSURE_STALE": "0"})

    assert proc.returncode == 0
    assert "watchdog off" in proc.stdout


def test_noninteger_sample_period_matches_heartbeat_fallback(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(minutes=2))

    proc = run_stale(tmp_path, env={"LIMEN_VITALS_SAMPLE_SECONDS": "30.5"})

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "budget 15 min" in proc.stdout


def test_unreadable_sample_timestamp_fails(tmp_path):
    seat = tmp_path / "logs" / "vigilia"
    seat.mkdir(parents=True, exist_ok=True)
    (seat / "status.json").write_text("{not json")
    proc = run_stale(tmp_path)
    assert proc.returncode == 1


def test_read_only_boot_mismatch_is_a_finding_not_permanent_grace(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc))
    status_path = tmp_path / "logs" / "vigilia" / "status.json"
    status = json.loads(status_path.read_text())
    status["boot_identity"] = "prior-boot"
    status_path.write_text(json.dumps(status))

    proc = run_stale(tmp_path, extra_args=["--read-only"])

    assert proc.returncode == 1
    assert "requires one bounded sample-first refresh" in proc.stdout


def test_budget_reads_shared_env_file(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(minutes=10))
    env_file = tmp_path / "limen.env"
    env_file.write_text(
        "LIMEN_VITALS_STALE_BEATS=2 # two missed samples\nLIMEN_VITALS_SAMPLE_SECONDS=120 # two minutes\n",
        encoding="utf-8",
    )

    proc = run_stale(tmp_path, env={"LIMEN_ENV_FILE": str(env_file)})

    assert proc.returncode == 1
    assert "budget 4 min" in proc.stdout


def test_budget_derives_from_env(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(minutes=10))
    # 2 missed declared samples x 120s = 4 min budget -> a 10-min-old record is stale
    proc = run_stale(
        tmp_path,
        env={"LIMEN_VITALS_STALE_BEATS": "2", "LIMEN_VITALS_SAMPLE_SECONDS": "120"},
    )
    assert proc.returncode == 1


def test_old_completion_does_not_make_a_fresh_sample_stale(tmp_path):
    now = datetime.now(timezone.utc)
    write_status(tmp_path, now, completed_at=now - timedelta(hours=4))

    proc = run_stale(
        tmp_path,
        env={"LIMEN_VITALS_STALE_BEATS": "3", "LIMEN_VITALS_SAMPLE_SECONDS": "60"},
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_fresh_completion_cannot_hide_a_stale_sample(tmp_path):
    now = datetime.now(timezone.utc)
    write_status(tmp_path, now - timedelta(minutes=10), completed_at=now)

    proc = run_stale(
        tmp_path,
        env={"LIMEN_VITALS_STALE_BEATS": "3", "LIMEN_VITALS_SAMPLE_SECONDS": "60"},
    )

    assert proc.returncode == 1
    assert "sample" not in proc.stderr.lower()


def test_cadence_boundary_grace_allows_the_due_sample_to_finish(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(seconds=304))

    proc = run_stale(
        tmp_path,
        env={
            "LIMEN_VITALS_STALE_BEATS": "1",
            "LIMEN_VITALS_SAMPLE_SECONDS": "300",
            "LIMEN_VITALS_SAMPLE_TIMEOUT": "1",
        },
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_missing_sample_is_stale_after_the_boundary_grace(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(seconds=306))

    proc = run_stale(
        tmp_path,
        env={
            "LIMEN_VITALS_STALE_BEATS": "1",
            "LIMEN_VITALS_SAMPLE_SECONDS": "300",
            "LIMEN_VITALS_SAMPLE_TIMEOUT": "1",
        },
    )

    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_sampler_timeout_is_inside_staleness_grace(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(seconds=333))

    proc = run_stale(
        tmp_path,
        env={"LIMEN_VITALS_STALE_BEATS": "1", "LIMEN_VITALS_SAMPLE_SECONDS": "300"},
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_darkwake_never_pages(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(days=1))
    path = tmp_path / "logs" / "vigilia" / "status.json"
    payload = json.loads(path.read_text())
    payload["wake_state"] = "MaintenanceDarkWake"
    path.write_text(json.dumps(payload))
    proc = run_stale(tmp_path)
    assert proc.returncode == 0
    assert "cannot page" in proc.stdout


def test_legacy_metadata_gets_sample_first_grace(tmp_path):
    seat = tmp_path / "logs" / "vigilia"
    seat.mkdir(parents=True)
    (seat / "status.json").write_text(json.dumps({"sampled_at": "2020-01-01T00:00:00Z"}))
    proc = run_stale(tmp_path, env={"LIMEN_NOTIFY": "0"})
    assert proc.returncode == 0
    assert "sample-first refresh" in proc.stdout
