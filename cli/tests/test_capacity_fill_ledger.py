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


def test_opencode_signal_quality_reports_clock_health(monkeypatch):
    module = _load_capacity_fill_module()
    monkeypatch.setattr(
        module,
        "read_opencode_clock",
        lambda: {
            "health": "ok",
            "used_pct": 15,
            "accepting_tasks": True,
            "updated_at": "2026-07-03T06:00:00+00:00",
        },
    )
    monkeypatch.setattr(module, "usage_vendor", lambda agent: None)

    signal = module.signal_quality("opencode")

    assert signal["signal"] == "db-meter"
    assert signal["trust"] == "measured"
    assert "health=ok" in signal["use"]
    assert "used=15%" in signal["use"]
    assert "accepting_tasks=True" in signal["use"]


def test_opencode_signal_quality_falls_back_without_clock(monkeypatch):
    module = _load_capacity_fill_module()
    monkeypatch.setattr(module, "read_opencode_clock", lambda: None)
    monkeypatch.setattr(module, "usage_vendor", lambda agent: None)

    signal = module.signal_quality("opencode")

    assert signal["signal"] == "dispatch-count proxy"
    assert signal["trust"] == "proxy"


def test_proxy_lane_signal_reports_rate_limit_watch(monkeypatch):
    module = _load_capacity_fill_module()
    monkeypatch.setattr(module, "recent_rate_limit", lambda agent: agent == "agy")
    monkeypatch.setattr(module, "usage_vendor", lambda agent: None)

    agy = module.signal_quality("agy")
    gemini = module.signal_quality("gemini")

    assert "recent heartbeat rate-limit marker present" in agy["use"]
    assert "no recent heartbeat rate-limit marker" in gemini["use"]


def test_proxy_lane_signal_includes_usage_telemetry(monkeypatch):
    module = _load_capacity_fill_module()

    def usage_vendor(agent):
        if agent == "agy":
            return {
                "health": "ok",
                "consumed": 14,
                "possible": 100,
                "unit": "runs",
                "remaining": 86,
                "headroom_pct": 86,
            }
        return None

    monkeypatch.setattr(module, "usage_vendor", usage_vendor)
    monkeypatch.setattr(module, "recent_rate_limit", lambda agent: False)

    signal = module.signal_quality("agy")

    assert signal["signal"] == "usage-telemetry proxy"
    assert signal["trust"] == "proxy + recent-rl"
    assert "usage health=ok" in signal["use"]
    assert "used=14/100 runs" in signal["use"]
    assert "remaining=86" in signal["use"]
    assert "headroom=86%" in signal["use"]
