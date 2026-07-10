from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reclaim-tool-caches.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_tool_cache_reclaim_removes_only_allowlisted_paths(monkeypatch, tmp_path):
    mod = _load("reclaim_tool_caches_uut")
    cache = tmp_path / ".cache" / "npm"
    excluded = tmp_path / ".local" / "share" / "opencode"
    cache.mkdir(parents=True)
    excluded.mkdir(parents=True)
    (cache / "blob").write_text("generated cache", encoding="utf-8")
    (excluded / "snapshot").write_text("agent state", encoding="utf-8")
    monkeypatch.setattr(mod, "HOME", tmp_path)
    monkeypatch.setattr(mod, "CACHE_PATHS", ("~/.cache/npm",))

    dry_rows = mod.cache_rows(apply=False)
    assert dry_rows[0]["exists"] is True
    assert dry_rows[0]["reclaimable_kib"] > 0
    assert dry_rows[0]["reclaimed_kib"] == 0

    applied_rows = mod.cache_rows(apply=True)
    assert applied_rows[0]["ok"] is True
    assert applied_rows[0]["reclaimed_kib"] > 0
    assert not cache.exists()
    assert (excluded / "snapshot").exists()
