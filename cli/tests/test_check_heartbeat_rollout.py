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
    assert MODULE.active_errors(tmp_path, "merged-sha", 3) == []


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
    assert MODULE.active_errors(tmp_path, "merged-sha", 1) == ["bad: surviving descendants are not zero"]
