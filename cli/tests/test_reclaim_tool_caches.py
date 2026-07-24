from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reclaim-tool-caches.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _configure(monkeypatch, mod, tmp_path, *, processes=None, sensor_error=""):
    monkeypatch.setattr(mod, "HOME", tmp_path)
    monkeypatch.setattr(
        mod,
        "CACHE_SPECS",
        (mod.CacheSpec("~/.cache/npm", ("npm", "node")),),
    )
    monkeypatch.setattr(
        mod,
        "process_snapshot",
        lambda: (list(processes or []), sensor_error),
    )
    monkeypatch.setattr(mod, "LOG_PATH", tmp_path / "reclaim.jsonl")


def test_check_apply_removes_only_exact_allowlisted_plan(monkeypatch, tmp_path):
    mod = _load("reclaim_tool_caches_uut")
    cache = tmp_path / ".cache" / "npm"
    excluded = tmp_path / ".local" / "share" / "opencode"
    cache.mkdir(parents=True)
    excluded.mkdir(parents=True)
    (cache / "blob").write_text("generated cache", encoding="utf-8")
    (excluded / "snapshot").write_text("agent state", encoding="utf-8")
    _configure(monkeypatch, mod, tmp_path)

    checked = mod.check_payload()
    assert checked["candidate_count"] == 1
    assert len(checked["plan_sha256"]) == 64
    assert checked["rows"][0]["classification"] == "candidate"

    applied = mod.apply_plan(checked["plan_sha256"])
    assert applied["removed_count"] == 1
    assert applied["total_reclaimed_kib"] > 0
    assert applied["residual_candidate_count"] == 0
    assert not cache.exists()
    assert (excluded / "snapshot").exists()


def test_active_process_excludes_cache_from_candidate_manifest(monkeypatch, tmp_path):
    mod = _load("reclaim_tool_caches_active_uut")
    cache = tmp_path / ".cache" / "npm"
    cache.mkdir(parents=True)
    (cache / "blob").write_text("generated cache", encoding="utf-8")
    _configure(
        monkeypatch,
        mod,
        tmp_path,
        processes=[{"pid": 44, "command": "node server.js", "cwd": str(tmp_path)}],
    )

    checked = mod.check_payload()

    assert checked["candidate_count"] == 0
    assert checked["blocked_count"] == 1
    assert checked["rows"][0]["classification"] == "active-process"
    assert checked["rows"][0]["active_pids"] == [44]
    assert cache.exists()


def test_unknown_process_sensor_fails_closed(monkeypatch, tmp_path):
    mod = _load("reclaim_tool_caches_sensor_uut")
    cache = tmp_path / ".cache" / "npm"
    cache.mkdir(parents=True)
    (cache / "blob").write_text("generated cache", encoding="utf-8")
    _configure(monkeypatch, mod, tmp_path, sensor_error="process-sensor-returncode")

    checked = mod.check_payload()

    assert checked["candidate_count"] == 0
    assert checked["rows"][0]["classification"] == "sensor-unknown"
    assert cache.exists()


def test_candidate_drift_blocks_apply_without_deletion(monkeypatch, tmp_path):
    mod = _load("reclaim_tool_caches_drift_uut")
    cache = tmp_path / ".cache" / "npm"
    cache.mkdir(parents=True)
    blob = cache / "blob"
    blob.write_text("first", encoding="utf-8")
    _configure(monkeypatch, mod, tmp_path)
    checked = mod.check_payload()

    blob.write_text("changed and larger", encoding="utf-8")

    with pytest.raises(ValueError, match="candidate drift"):
        mod.apply_plan(checked["plan_sha256"])
    assert cache.exists()
    assert not mod.LOG_PATH.exists()


def test_unchanged_second_check_after_apply_is_zero_candidate_fixed_point(monkeypatch, tmp_path):
    mod = _load("reclaim_tool_caches_fixed_point_uut")
    cache = tmp_path / ".cache" / "npm"
    cache.mkdir(parents=True)
    (cache / "blob").write_text("generated cache", encoding="utf-8")
    _configure(monkeypatch, mod, tmp_path)
    first = mod.check_payload()
    mod.apply_plan(first["plan_sha256"])

    second = mod.check_payload()
    third = mod.check_payload()

    assert second["candidate_count"] == 0
    assert second["plan_sha256"] == third["plan_sha256"]
