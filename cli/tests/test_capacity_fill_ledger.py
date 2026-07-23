from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

CLI_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(CLI_SRC))

from limen.io import save_limen_file
from limen.models import Budget, BudgetTrack, LimenFile, Portal


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


def test_codex_signal_quality_prefers_vendor_rate_limits(monkeypatch):
    module = _load_capacity_fill_module()

    def usage_vendor(agent):
        if agent == "codex":
            return {
                "signal": "vendor-rate-limit",
                "health": "ok",
                "unit": "percent",
                "consumed": 15.0,
                "possible": 100,
                "remaining": 85.0,
                "headroom_pct": 85,
                "weekly_used_percent": 58.0,
                "limit_source": "vendor rate_limits",
            }
        return None

    monkeypatch.setattr(module, "usage_vendor", usage_vendor)

    signal = module.signal_quality("codex")

    assert signal["signal"] == "vendor rate-limit meter"
    assert signal["trust"] == "measured"
    assert "usage health=ok" in signal["use"]
    assert "used=15.0/100 percent" in signal["use"]
    assert "remaining=85.0" in signal["use"]
    assert "weekly=58.0%" in signal["use"]
    assert "source=vendor rate_limits" in signal["use"]


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


def test_census_uses_live_usage_exhaustion_for_reachability(monkeypatch):
    module = _load_capacity_fill_module()
    monkeypatch.setattr(
        module,
        "capacity_census",
        lambda board: [
            {
                "agent": "jules",
                "kind": "cloud-cli",
                "reachable": True,
                "remaining": 51,
                "limit": 100,
                "detail": "/opt/homebrew/bin/jules",
            }
        ],
    )

    def usage_vendor(agent):
        if agent == "jules":
            return {
                "health": "exhausted",
                "remaining": 0,
                "consumed": 141,
                "possible": 100,
                "unit": "runs",
            }
        return None

    monkeypatch.setattr(module, "usage_vendor", usage_vendor)

    snapshot = module.build_snapshot({})
    row = snapshot["census"][0]

    assert row["reachable"] is False
    assert row["remaining"] == 0
    assert "usage health=exhausted" in row["detail"]
    assert snapshot["blocked_agents"] == ["jules"]


def test_census_does_not_block_agy_on_weak_dispatch_count_proxy(monkeypatch):
    module = _load_capacity_fill_module()
    monkeypatch.setattr(
        module,
        "capacity_census",
        lambda board: [
            {
                "agent": "agy",
                "kind": "local-cli",
                "reachable": True,
                "remaining": 31,
                "limit": 100,
                "detail": "/opt/homebrew/bin/agy",
            }
        ],
    )

    def usage_vendor(agent):
        if agent == "agy":
            return {
                "health": "exhausted",
                "signal": "dispatch-count",
                "limit_source": "operator board cap until live vendor meter",
                "remaining": 0,
                "consumed": 107,
                "possible": 100,
                "unit": "runs",
            }
        return None

    monkeypatch.setattr(module, "usage_vendor", usage_vendor)
    monkeypatch.setattr(module, "_down_lanes", lambda: set())

    snapshot = module.build_snapshot({})
    row = snapshot["census"][0]

    assert row["reachable"] is True
    assert row["remaining"] == 31
    assert "usage health=exhausted" not in row["detail"]
    assert snapshot["blocked_agents"] == []


def test_census_uses_dispatch_down_gate_for_reachability(monkeypatch):
    module = _load_capacity_fill_module()
    monkeypatch.setattr(
        module,
        "capacity_census",
        lambda board: [
            {
                "agent": "claude",
                "kind": "local-cli",
                "reachable": True,
                "remaining": 12,
                "limit": 100,
                "detail": "/Users/test/.local/bin/claude",
            }
        ],
    )
    monkeypatch.setattr(module, "usage_vendor", lambda agent: None)
    monkeypatch.setattr(module, "_down_lanes", lambda: {"claude"})

    snapshot = module.build_snapshot({})
    row = snapshot["census"][0]

    assert row["reachable"] is False
    assert row["remaining"] == 0
    assert "dispatch down-lane gate" in row["detail"]
    assert snapshot["blocked_agents"] == ["claude"]


def test_load_tasks_board_projects_stale_budget_reset(tmp_path, monkeypatch):
    module = _load_capacity_fill_module()
    now = dt.datetime.now(dt.UTC)
    stale = (now - dt.timedelta(days=2)).isoformat()
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(
        tasks_path,
        LimenFile(
            portal=Portal(
                budget=Budget(
                    daily=600,
                    per_agent={"jules": 100},
                    track=BudgetTrack(
                        date="2026-07-03",
                        spent=100,
                        per_agent={"jules": 100},
                        per_agent_reset={"jules": stale},
                    ),
                )
            )
        ),
    )
    monkeypatch.setattr(module, "TASKS_PATH", tasks_path)

    board = module.load_tasks_board()

    track = board["portal"]["budget"]["track"]
    assert track["per_agent"]["jules"] == 0
    assert track["spent"] == 0
