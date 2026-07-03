from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_capacity_fill_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "capacity-fill-ledger.py"
    spec = importlib.util.spec_from_file_location("capacity_fill_ledger", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ollama_blocker_prefers_disk_pressure_before_model_pull(monkeypatch):
    module = _load_capacity_fill_module()
    monkeypatch.setattr(module, "disk_free_gib", lambda path=module.HOME: 20.6)
    monkeypatch.setattr(
        module,
        "capacity_census",
        lambda board: [
            {
                "agent": "ollama",
                "kind": "local-cli",
                "reachable": False,
                "remaining": 100,
                "limit": 100,
                "detail": "/opt/homebrew/bin/ollama; no model pulled - run `ollama pull qwen2.5-coder:7b`",
            }
        ],
    )

    snapshot = module.build_snapshot({})
    detail = snapshot["blocked_details"]["ollama"]

    assert "local disk pressure blocks qwen2.5-coder:7b pull" in detail
    assert "run `ollama pull" not in detail
    assert "20.6 GiB free" in detail
    assert "Clear local disk pressure before pulling" in module.render_markdown(snapshot)


def test_ollama_blocker_preserves_pull_instruction_without_disk_pressure(monkeypatch):
    module = _load_capacity_fill_module()
    original = "/opt/homebrew/bin/ollama; no model pulled - run `ollama pull qwen2.5-coder:7b`"
    monkeypatch.setattr(module, "disk_free_gib", lambda path=module.HOME: 80.0)

    assert module.ollama_capacity_detail(original) == original
