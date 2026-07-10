from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "substrate-storage-pressure.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_reclaim_summary_sums_total_and_reclaimed_keys(tmp_path):
    mod = _load("substrate_storage_pressure_uut")
    log = tmp_path / "reclaim.jsonl"
    log.write_text(
        json.dumps({"apply": True, "generated_at": "t1", "total_reclaimed_kib": 1024})
        + "\n"
        + json.dumps({"apply": True, "generated_at": "t2", "reclaimed_kib": 2048})
        + "\n",
        encoding="utf-8",
    )

    summary = mod.reclaim_summary(log)

    assert summary["apply_events"] == 2
    assert summary["cumulative_reclaimed_kib"] == 3072
    assert summary["cumulative_reclaimed_size"] == "3.0 MiB"
    assert summary["latest_generated_at"] == "t2"


def test_build_snapshot_classifies_configured_bucket(monkeypatch, tmp_path):
    mod = _load("substrate_storage_pressure_build_uut")
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    (bucket / "payload").write_text("x" * 4096, encoding="utf-8")
    monkeypatch.setattr(mod, "HOME", tmp_path)
    monkeypatch.setattr(mod, "ROOT", tmp_path / "limen")
    monkeypatch.setattr(
        mod,
        "BUCKETS",
        (
            {
                "id": "bucket",
                "path": str(bucket),
                "class": "protected-test",
                "owner": "owner",
                "gate": "gate",
            },
        ),
    )
    monkeypatch.setattr(mod, "RECLAIM_LOGS", {})
    monkeypatch.setattr(mod, "disk_free_gib", lambda: 50.0)
    monkeypatch.setattr(mod, "TARGET_FREE_GIB", 200.0)

    snapshot = mod.build_snapshot()

    assert snapshot["status"] == "needs-owner-gates"
    assert snapshot["shortfall_gib"] == 150.0
    assert snapshot["buckets"][0]["id"] == "bucket"
    assert snapshot["buckets"][0]["exists"] is True
