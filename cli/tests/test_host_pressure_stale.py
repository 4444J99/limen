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
        [
            sys.executable,
            "-c",
            "import runpy,sys; m=runpy.run_path(sys.argv[1]); "
            "m['main'].__globals__.update("
            '_boot_identity=lambda: "fixture-boot", _active_monotonic=lambda: 200000.0); '
            "sys.exit(m['main'](sys.argv[2:]))",
            str(SCRIPT),
            *(extra_args or []),
        ],
        capture_output=True,
        text=True,
        env=child_env,
    )


def write_status(tmp_path: Path, sampled_at: datetime, completed_at: datetime | None = None) -> None:
    seat = tmp_path / "logs" / "vigilia"
    seat.mkdir(parents=True, exist_ok=True)
    boot_identity = "fixture-boot"
    age = max(0.0, (datetime.now(timezone.utc) - sampled_at).total_seconds())
    active_now = 200000.0
    (seat / "status.json").write_text(
        json.dumps(
            {
                "sampled_at": sampled_at.isoformat(),
                "completed_at": completed_at.isoformat() if completed_at else None,
                "boot_identity": boot_identity,
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


def test_persisted_darkwake_cannot_hide_a_stale_sample(tmp_path):
    write_status(tmp_path, datetime.now(timezone.utc) - timedelta(days=1))
    path = tmp_path / "logs" / "vigilia" / "status.json"
    payload = json.loads(path.read_text())
    payload["wake_state"] = "MaintenanceDarkWake"
    payload["sampled_monotonic_seconds"] = max(0.0, payload["sampled_monotonic_seconds"])
    path.write_text(json.dumps(payload))
    proc = run_stale(tmp_path)
    assert proc.returncode == 1
    assert "STALE" in proc.stdout


def test_legacy_metadata_requires_successful_explicit_refresh(tmp_path):
    seat = tmp_path / "logs" / "vigilia"
    seat.mkdir(parents=True)
    (seat / "status.json").write_text(json.dumps({"sampled_at": "2020-01-01T00:00:00Z"}))
    proc = run_stale(tmp_path, env={"LIMEN_NOTIFY": "0"})
    assert proc.returncode == 1
    assert "sample-first refresh" in proc.stdout


def _load_watchdog():
    import importlib.util

    spec = importlib.util.spec_from_file_location("watchdog_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unavailable_boot_is_not_a_compatible_identity(monkeypatch):
    module = _load_watchdog()
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", "unsupported"))
    assert module._boot_identity() == "unavailable"


def test_failed_refresh_cannot_report_success(tmp_path, monkeypatch):
    module = _load_watchdog()
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_ENV_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("LIMEN_VIGILIA", "1")
    monkeypatch.setenv("LIMEN_HOST_PRESSURE_STALE", "1")
    monkeypatch.setattr(module, "_boot_identity", lambda: "current")
    monkeypatch.setattr(module._notify, "notify_once", lambda *a: None)
    seat = tmp_path / "logs/vigilia/status.json"
    seat.parent.mkdir(parents=True)
    seat.write_text(json.dumps({"boot_identity": "prior"}))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1))
    assert module.main(["--apply"]) == 1
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    assert module.main(["--apply"]) == 1  # exit zero without a compatible written record


def test_successful_refresh_rechecks_record_and_read_only_never_refreshes(tmp_path, monkeypatch):
    module = _load_watchdog()
    for name, value in {
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_ENV_FILE": str(tmp_path / "none"),
        "LIMEN_VIGILIA": "1",
        "LIMEN_HOST_PRESSURE_STALE": "1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_boot_identity", lambda: "current")
    monkeypatch.setattr(module, "_active_monotonic", lambda: 1000.0)
    monkeypatch.setattr(module._notify, "clear_condition", lambda *a: None)
    seat = tmp_path / "logs/vigilia/status.json"
    seat.parent.mkdir(parents=True)
    seat.write_text(json.dumps({"boot_identity": "prior"}))
    calls = []

    def refresh(*args, **kwargs):
        calls.append(args)
        seat.write_text(
            json.dumps(
                {
                    "boot_identity": "current",
                    "sampled_monotonic_seconds": 999.0,
                    "sampled_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(module.subprocess, "run", refresh)
    assert module.main(["--apply", "--read-only"]) == 1
    assert calls == []
    assert module.main(["--apply"]) == 0
    assert len(calls) == 1
