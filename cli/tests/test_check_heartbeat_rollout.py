from __future__ import annotations

import importlib.util
import json
from pathlib import Path


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
