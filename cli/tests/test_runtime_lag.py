"""The runtime-lag sensor: does the RUNNING host carry merged main?

The failure this guards is a silent one. A stale runtime install passes every liveness check
the beat already has — it stamps its voice files on time and its canary goes green — while
executing week-old code. So the cases that matter most here are the ones where the predicate
must NOT report success: an unmeasurable SHA, a diverged install, an unreadable receipt.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-runtime-lag.py"


def _module():
    spec = importlib.util.spec_from_file_location("_check_runtime_lag", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lag():
    return _module()


def _install(tmp_path: Path, receipt: dict | None, *, sha_dir: str = "0" * 40) -> Path:
    """Reproduce the rotator's layout: current -> runtimes/<sha>, holding receipt.json."""
    runtime = tmp_path / "runtimes" / sha_dir
    runtime.mkdir(parents=True)
    if receipt is not None:
        (runtime / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    current = tmp_path / "current"
    current.symlink_to(runtime)
    return current


def test_absent_install_is_silent(lag, tmp_path: Path) -> None:
    """No install ⇒ nothing schedules stale code here. CI and containers must stay quiet."""
    assert lag.read_receipt(tmp_path / "nope") is None


def test_receipt_is_read_not_guessed(lag, tmp_path: Path) -> None:
    current = _install(tmp_path, {"sha": "a" * 40, "installed_at": "2026-07-31T13:47:51+00:00"})
    assert lag.read_receipt(current)["sha"] == "a" * 40


def test_unreadable_receipt_falls_back_instead_of_reporting_absence(lag, tmp_path: Path) -> None:
    """The decisive case. A corrupt receipt still has launchd executing that runtime, so
    treating it as "no install" would convert measurable staleness into a silent pass."""
    current = _install(tmp_path, None, sha_dir="b" * 40)
    receipt = lag.read_receipt(current)
    assert receipt is not None, "a missing receipt must not read as a missing install"
    assert receipt["sha"] == "b" * 40
    assert receipt.get("degraded")


def test_unknown_sha_is_unverified_not_ok(lag) -> None:
    """'I could not check' must never render as 'I checked and it is current'."""
    m = lag.measure({"sha": "c" * 40, "default_branch": "main"})
    assert "unmeasurable" in m
    assert "behind" not in m


def test_measures_real_lag_against_the_default_branch(lag) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    m = lag.measure({"sha": head, "default_branch": "main"})
    # HEAD is a real commit, so this must be a measurement rather than a shrug.
    assert "unmeasurable" not in m, m
    assert isinstance(m["behind"], int)


def test_age_survives_a_naive_timestamp(lag) -> None:
    assert lag.install_age_days({"installed_at": "2026-07-31T13:47:51"}) is not None
    assert lag.install_age_days({}) is None


def test_bound_is_a_declared_parameter(lag) -> None:
    """The threshold is registry-owned (LIMEN_RUNTIME_LAG_MAX_COMMITS), not a magic number
    buried in the script — same discipline as every other beat bound."""
    params = (ROOT / "institutio" / "governance" / "parameters.yaml").read_text(encoding="utf-8")
    assert "LIMEN_RUNTIME_LAG_MAX_COMMITS" in params
    assert "LIMEN_RUNTIME_LAG:" in params


def test_registered_as_a_beat_sensor(lag) -> None:
    sensors = (ROOT / "institutio" / "governance" / "sensors.yaml").read_text(encoding="utf-8")
    assert "runtime-lag:" in sensors
    assert "scripts/check-runtime-lag.py" in sensors


def test_runs_clean_as_a_subprocess(lag) -> None:
    """The beat invokes it as a command; --json must stay machine-readable whatever the host
    state, including the exit-1 STALE path this repo's own host is currently in."""
    out = subprocess.run(["python3", str(SCRIPT), "--json"], cwd=ROOT, capture_output=True, text=True, check=False)
    assert out.returncode in (0, 1), out.stderr
    payload = json.loads(out.stdout)
    assert "installed" in payload
