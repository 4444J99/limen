import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "conducting-report.py"


def _load(monkeypatch, root: Path):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_TASKS", str(root / "tasks.yaml"))
    spec = importlib.util.spec_from_file_location("conducting_report_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_census_is_counts_only(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "generated": "2026-07-06T00:00:00Z",
                "vendors": {
                    "private-codex-name": {"headroom_pct": 10, "reserve_pct": 15, "consumed": 90},
                    "private-claude-name": {"headroom_pct": 100, "reserve_pct": 15, "consumed": 0},
                },
            }
        ),
        encoding="utf-8",
    )
    (logs / "ledger.json").write_text(json.dumps({"verdict": "private value verdict"}), encoding="utf-8")
    (tmp_path / "tasks.yaml").write_text(
        """
tasks:
  - id: DISCOVER-PRIVATE
    status: open
    title: private target
  - id: DISCOVER-DONE
    status: done
""",
        encoding="utf-8",
    )

    census = module.census()
    encoded = json.dumps(census, sort_keys=True)

    assert census == {
        "usage_present": True,
        "vendor_count": 2,
        "vendors_with_headroom": 2,
        "vendors_burned": 1,
        "vendors_idle": 1,
        "value_verdict_present": True,
        "open_value_discovery": 1,
        "state_present": False,
    }
    assert "private-codex-name" not in encoded
    assert "private-claude-name" not in encoded
    assert "private value verdict" not in encoded
    assert "private target" not in encoded
