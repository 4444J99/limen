from __future__ import annotations

import importlib.util
import json
import subprocess
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
    monkeypatch.setattr(
        mod,
        "worktree_lifecycle_summary",
        lambda: {
            "present": True,
            "ok": True,
            "total": 2,
            "debt": 0,
            "reapable": 0,
            "debt_target": 0,
            "reapable_limit": 0,
            "by_reason": {"active(<6h)": 2},
            "by_reapable_reason": {},
            "summary": "0 debt roots / 2 scanned; 0 reapable roots",
        },
    )

    snapshot = mod.build_snapshot()

    assert snapshot["status"] == "needs-owner-gates"
    assert snapshot["shortfall_gib"] == 150.0
    assert snapshot["buckets"][0]["id"] == "bucket"
    assert snapshot["buckets"][0]["exists"] is True
    assert snapshot["worktree_lifecycle"]["summary"] == "0 debt roots / 2 scanned; 0 reapable roots"


def test_opencode_bucket_reflects_verified_intake(monkeypatch, tmp_path):
    mod = _load("substrate_storage_pressure_opencode_uut")
    root = tmp_path / "limen"
    db = tmp_path / "opencode.db"
    db.write_text("db", encoding="utf-8")
    log = root / "logs" / "opencode-db-corpus-intake.jsonl"
    doc = root / "docs" / "opencode-db-corpus-intake.md"
    log.parent.mkdir(parents=True)
    doc.parent.mkdir(parents=True)
    doc.write_text("# receipt\n", encoding="utf-8")
    log.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-10T01:00:00Z",
                "run_id": "run",
                "status": "archived_private_intake",
                "archive_status": "verified",
                "private_manifest": {
                    "path": ".limen-private/session-corpus/lifecycle/opencode-db-intake/run/manifest.json"
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "HOME", tmp_path)
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "OPENCODE_INTAKE_LOG", log)
    monkeypatch.setattr(mod, "OPENCODE_INTAKE_DOC", doc)
    monkeypatch.setattr(
        mod,
        "BUCKETS",
        (
            {
                "id": "opencode-db",
                "path": str(db),
                "class": "protected-agent-state",
                "owner": "aw-opencode-db-corpus-intake-0709",
                "gate": "extract/export into prompt-corpus intake before vendor retention decision; never delete outright",
            },
        ),
    )
    monkeypatch.setattr(mod, "RECLAIM_LOGS", {})
    monkeypatch.setattr(mod, "disk_free_gib", lambda: 90.0)
    monkeypatch.setattr(mod, "TARGET_FREE_GIB", 200.0)
    monkeypatch.setattr(mod, "worktree_lifecycle_summary", lambda: {"present": True, "ok": True})

    snapshot = mod.build_snapshot()

    assert snapshot["opencode_intake"]["archive_status"] == "verified"
    assert snapshot["buckets"][0]["gate"] == (
        "external archive and private intake verified; local retention decision remains; never delete outright"
    )
    assert snapshot["buckets"][0]["evidence"]["opencode_intake"]["status"] == "archived_private_intake"


def test_worktree_lifecycle_summary_parses_worktree_debt(monkeypatch, tmp_path):
    mod = _load("substrate_storage_pressure_worktree_uut")
    root = tmp_path / "limen"
    script = root / "scripts" / "worktree-debt.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", root)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0],
            0,
            json.dumps(
                {
                    "total": 3,
                    "debt": 0,
                    "reapable": 1,
                    "debt_target": 0,
                    "reapable_limit": 0,
                    "by_reason": {"active(<6h)": 2, "clean+merged+idle": 1},
                    "by_reapable_reason": {"clean+merged+idle": 1},
                }
            ),
            "",
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    summary = mod.worktree_lifecycle_summary()

    assert summary["ok"] is True
    assert summary["total"] == 3
    assert summary["reapable"] == 1
    assert summary["debt_target"] == 0
    assert summary["complete"] is True
    assert summary["by_reason"]["clean+merged+idle"] == 1
    assert summary["summary"] == "0 debt roots / 3 scanned; 1 reapable roots"


def test_render_includes_worktree_lifecycle(monkeypatch, tmp_path):
    mod = _load("substrate_storage_pressure_render_uut")
    snapshot = {
        "generated_at": "2026-07-10T00:00:00Z",
        "status": "needs-owner-gates",
        "internal_free_gib": 90.0,
        "target_free_gib": 200.0,
        "shortfall_gib": 110.0,
        "safe_reclaim": {},
        "worktree_lifecycle": {
            "ok": True,
            "summary": "0 debt roots / 3 scanned; 1 reapable roots",
            "debt_target": 0,
            "complete": True,
            "reapable_limit": 0,
            "by_reason": {"active(<6h)": 2, "clean+merged+idle": 1},
        },
        "buckets": [],
    }

    rendered = mod.render(snapshot)

    assert "## Scratch / Worktree Lifecycle" in rendered
    assert "`0 debt roots / 3 scanned; 1 reapable roots`" in rendered
    assert "Debt target: `0`; complete: `True`; reapable cap: `0`" in rendered
    assert "| `clean+merged+idle` | `1` |" in rendered
