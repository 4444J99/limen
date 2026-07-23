from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("verify_budget_gauge", ROOT / "scripts" / "verify-budget-gauge.py")
vbg = importlib.util.module_from_spec(spec)
sys.modules["verify_budget_gauge"] = vbg
spec.loader.exec_module(vbg)


def test_codex_live_rate_limits_malformed_payload_fails_open(monkeypatch) -> None:
    monkeypatch.setattr(vbg, "_load_default_limits", dict)
    monkeypatch.setattr(vbg, "_load_override", dict)
    monkeypatch.setattr(
        vbg,
        "codex_live_rate_limits",
        lambda: {
            "plan_type": "pro",
            "primary": {"used_percent": "bad", "window_minutes": "bad"},
            "secondary": {"used_percent": "nan", "window_minutes": "inf"},
        },
    )

    gauge = vbg.build_gauge()

    assert gauge["codex"]["unit"] == "percent"
    assert gauge["codex"]["used_percent"] is None
    assert gauge["codex"]["weekly_used_percent"] is None
    assert "window" not in gauge["codex"]
    assert "weekly_window" not in gauge["codex"]


def test_human_print_tolerates_malformed_used_percent(capsys) -> None:
    report = {
        "rows": [
            {
                "lane": "codex",
                "plane": "fleet",
                "unit": "percent",
                "cap": 100,
                "window": "5h",
                "trust": "measured",
                "pool": "openai-plan",
                "board_cap": None,
                "used_percent": "bad",
                "weekly_used_percent": "bad",
            }
        ],
        "findings": [],
        "errors": 0,
        "warnings": 0,
        "status": "true",
        "exit_code": 0,
    }

    vbg._print_human(report)

    assert "codex" in capsys.readouterr().out
