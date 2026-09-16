from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-heartbeat-rollout.py"
SPEC = importlib.util.spec_from_file_location("check_heartbeat_rollout", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_registry_has_exact_complete_successor_coverage() -> None:
    assert MODULE.registry_errors() == []


def test_active_proof_requires_consecutive_exact_sha_receipts(tmp_path: Path) -> None:
    for index, status in enumerate(("passed", "finding", "idle"), start=1):
        (tmp_path / f"{index}.json").write_text(
            json.dumps(
                {
                    "run_id": str(index),
                    "observed_epoch": index * 900,
                    "runtime_sha": "merged-sha",
                    "status": status,
                    "surviving_descendant_count": 0,
                    "disabled": False,
                }
            )
        )
    assert MODULE.active_errors(tmp_path, "merged-sha", 3, now=2800) == []


def test_active_proof_rejects_surviving_descendant(tmp_path: Path) -> None:
    (tmp_path / "1.json").write_text(
        json.dumps(
            {
                "run_id": "bad",
                "observed_epoch": 1,
                "runtime_sha": "merged-sha",
                "status": "passed",
                "surviving_descendant_count": 1,
                "disabled": False,
            }
        )
    )
    assert MODULE.active_errors(tmp_path, "merged-sha", 1, now=2) == ["bad: surviving descendants are not zero"]


def test_old_fires_cannot_establish_active_runtime(tmp_path: Path) -> None:
    receipt = {
        "run_id": "old",
        "observed_epoch": 1000,
        "runtime_sha": "merged-sha",
        "status": "idle",
        "surviving_descendant_count": 0,
        "disabled": False,
    }
    (tmp_path / "old.json").write_text(json.dumps(receipt))
    assert MODULE.active_errors(tmp_path, "merged-sha", 1, now=1420) == []
    assert "stale" in MODULE.active_errors(tmp_path, "merged-sha", 1, now=1421)[0]


def test_bad_timestamps_fail_without_crashing_or_sorting_as_fresh(tmp_path: Path) -> None:
    for epoch in (None, "new", True, float("nan"), float("inf"), 10**400, -1, 2001):
        (tmp_path / "bad.json").write_text(json.dumps({"observed_epoch": epoch}))
        errors = MODULE.active_errors(tmp_path, "merged-sha", 1, now=2000)
        assert any("invalid or future" in error for error in errors)
        assert any("recorded fires are 0" in error for error in errors)


@pytest.fixture
def probe_receipts(tmp_path, monkeypatch):
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "processes": {
                    "com.limen.heartbeat": {
                        "launchd": {"start_interval_seconds": 300},
                        "probes": [
                            {"name": "first", "cadence_seconds": 600},
                            {"name": "second", "cadence_seconds": 600},
                        ],
                    }
                }
            }
        )
    )
    monkeypatch.setattr(MODULE, "CONTRACTS", contract)
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    for name in ("first", "second"):
        (receipts / f"{name}.json").write_text(
            json.dumps(
                {
                    "schema": "limen.heartbeat_private_receipt.v1",
                    "runtime_sha": "a" * 40,
                    "probe": name,
                    "observed_epoch": 1000,
                    "status": "passed",
                    "returncode": 0,
                    "disabled": False,
                    "surviving_descendant_count": 0,
                }
            )
        )
    return receipts


def test_current_receipts_prove_execution_without_legacy_stamps(probe_receipts):
    report = MODULE.scheduled_probe_report(probe_receipts, "a" * 40, now=1100)
    assert report["execution_complete"]
    assert report["observed"] == report["scheduled_total"] == 2
    assert report["other_owners"] == "unmeasured_by_this_probe"


@pytest.mark.parametrize(
    "update,bucket",
    [
        ({"runtime_sha": "b" * 40}, "missing"),
        ({"status": "deferred", "returncode": None}, "unmeasured"),
        ({"status": "failed", "returncode": -9}, "unmeasured"),
        ({"surviving_descendant_count": 1}, "unmeasured"),
        ({"surviving_descendant_count": False}, "unmeasured"),
        ({"disabled": True}, "unmeasured"),
        ({"returncode": 1}, "unmeasured"),
        ({"schema": "untrusted"}, "unmeasured"),
    ],
)
def test_partial_unavailable_and_wrong_runtime_stay_visible(probe_receipts, update, bucket):
    path = probe_receipts / "first.json"
    row = json.loads(path.read_text())
    row.update(update)
    path.write_text(json.dumps(row))
    report = MODULE.scheduled_probe_report(probe_receipts, "a" * 40, now=1100)
    assert not report["execution_complete"]
    assert report[bucket] == 1


def test_finding_is_executed_but_not_healthy_and_does_not_poison_future_canary(probe_receipts):
    path = probe_receipts / "first.json"
    row = json.loads(path.read_text())
    row.update(status="finding", returncode=1)
    path.write_text(json.dumps(row))
    report = MODULE.scheduled_probe_report(probe_receipts, "a" * 40, now=1100)
    assert report["execution_complete"]
    assert report["finding"] == 1


def test_stale_and_malformed_receipts_do_not_pass(probe_receipts):
    report = MODULE.scheduled_probe_report(probe_receipts, "a" * 40, now=2201)
    assert report["stale"] == 2
    assert not report["execution_complete"]
    (probe_receipts / "broken.json").write_text("{")
    report = MODULE.scheduled_probe_report(probe_receipts, "a" * 40, now=1100)
    assert report["malformed_receipts"] == 1
    assert not report["execution_complete"]


def test_scheduled_canary_command_matches_observer():
    contract = json.loads((ROOT / "spec/scheduled-process-contracts.json").read_text())
    scheduled = next(p for p in contract["processes"]["com.limen.heartbeat"]["probes"] if p["name"] == "sensor-canary")
    observer = next(p for p in MODULE._load_observer().HOST_PROBES if p[0] == "sensor-canary")
    assert (
        scheduled["command"][1:]
        == observer[1][1:]
        == [
            "scripts/check-heartbeat-rollout.py",
            "--scheduled-probes",
        ]
    )
    assert scheduled["timeout_seconds"] == observer[2] == 30
