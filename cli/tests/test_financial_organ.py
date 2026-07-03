from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "financial-organ.py"
CONSOLIDATE = ROOT / "organs" / "financial" / "consolidate.py"


def load_financial_organ(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    spec = importlib.util.spec_from_file_location("financial_organ_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_consolidate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    spec = importlib.util.spec_from_file_location("financial_consolidate_under_test", CONSOLIDATE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_financial_maturity_advance_preserves_note_and_unicode(tmp_path: Path, monkeypatch) -> None:
    module = load_financial_organ(tmp_path, monkeypatch)
    ladder = tmp_path / "organ-ladder.json"
    ladder.write_text(
        json.dumps(
            {
                "organs": [
                    {
                        "pillar": "financial",
                        "maturity": 40,
                        "stage": "building",
                        "note": "scale the-invisible-ledger. Maturity 30%→40%.",
                    },
                    {
                        "pillar": "arts",
                        "maturity": 70,
                        "stage": "maturing",
                        "note": "studio/temple platform — all 3/3 validated",
                    },
                ]
            },
            ensure_ascii=False,
        )
    )

    result = module._advance_maturity({"maturity_pct": 70})

    assert result["bumped"] is True
    text = ladder.read_text()
    assert "30%→40%" in text
    assert "platform — all" in text
    assert "\\u2192" not in text
    assert "\\u2014" not in text
    data = json.loads(text)
    financial = data["organs"][0]
    assert financial["maturity"] == 70
    assert financial["stage"] == "maturing"
    assert "scale the-invisible-ledger" in financial["note"]
    assert "Maturity 40%->70% auto-advanced by financial-organ.py beat" in financial["note"]


def test_consolidator_skips_timestamp_only_writes(tmp_path: Path, monkeypatch) -> None:
    module = load_consolidate(tmp_path, monkeypatch)
    path = tmp_path / "STATUS.md"
    original = "**Generated:** 2026-07-03T00:00:00Z  **Maturity:** maturing (70%)\n\nbody\n"
    path.write_text(original)

    changed = module.write_if_changed(
        path,
        "**Generated:** 2026-07-03T10:00:00Z  **Maturity:** maturing (70%)\n\nbody\n",
    )

    assert changed is False
    assert path.read_text() == original

    changed = module.write_if_changed(
        path,
        "**Generated:** 2026-07-03T10:00:00Z  **Maturity:** mature (90%)\n\nbody\n",
    )
    assert changed is True
