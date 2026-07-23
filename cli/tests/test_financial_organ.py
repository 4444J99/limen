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


def test_financial_dashboard_surfaces_macro_and_micro_faces(tmp_path: Path, monkeypatch) -> None:
    fin = tmp_path / "organs" / "financial"
    fin.mkdir(parents=True)
    (fin / "MACRO.md").write_text("# Macro\n")
    (fin / "MICRO.md").write_text("# Micro\n")
    module = load_consolidate(tmp_path, monkeypatch)

    dashboard = module.build_dashboard(
        {"entities": []},
        {"products": []},
        {"obligations": []},
        {"snapshot_count": 0},
    )
    web_face = module.build_web_dashboard({"entities": []}, {"snapshot_count": 0})

    assert "| Macro Face | `MACRO.md` | Deepened" in dashboard
    assert "| Micro Instance Face | `MICRO.md` | Deepened" in dashboard
    faces = {face["id"]: face for face in web_face["faces"]}
    assert faces["macro"]["path"] == "organs/financial/MACRO.md"
    assert faces["micro"]["status"] == "deepened"
    assert "MONETA intakes value" in web_face["rail_boundary"]


def test_public_census_is_counts_only(tmp_path: Path, monkeypatch) -> None:
    fin = tmp_path / "organs" / "financial"
    fin.mkdir(parents=True)
    (fin / "CHARTER.md").write_text("# Charter\n")
    (fin / "balance-sheet.md").write_text("# Balance\n")
    (fin / "cashflow.md").write_text("# Cashflow\n")
    (fin / "entities.yaml").write_text("entities: []\n")
    (fin / "balances-history.json").write_text("[]\n")
    (fin / "consolidate.py").write_text("# generated\n")
    cache = fin / "__pycache__"
    cache.mkdir()
    (cache / "consolidate.cpython-314.pyc").write_bytes(b"compiled")

    module = load_financial_organ(tmp_path, monkeypatch)
    census = module._financial_public_census()

    assert census["public_artifacts"] == 6
    assert census["markdown_artifacts"] == 3
    assert census["registry_artifacts"] == 2
    assert census["has_consolidator"] is True
    assert census["has_balance_sheet"] is True
    assert census["has_cashflow"] is True
    assert census["has_payrail"] is False
    assert "__pycache__" not in json.dumps(census)
    assert "entities.yaml" not in json.dumps(census)
    assert str(tmp_path) not in json.dumps(census)


def test_cashflow_uses_registry_obligation_fallback(tmp_path: Path, monkeypatch) -> None:
    module = load_consolidate(tmp_path, monkeypatch)
    entities = {
        "obligation_sources": [
            {
                "source": "$LIMEN_ROOT/obligations-ledger.json",
                "financial_obligations": [
                    {
                        "priority": 88,
                        "title": "Student loan default risk",
                        "entity": "anthony-personal",
                        "next_step": "Check servicer status",
                    }
                ],
            }
        ]
    }

    cashflow = module.build_cashflow(entities, {"products": []}, {}, {})
    dashboard = module.build_dashboard(entities, {"products": []}, {}, {"snapshot_count": 0})

    assert "1 protocol-class obligations" in cashflow
    assert "entities.yaml registry fallback" in cashflow
    assert "Student loan default risk" in cashflow
    assert "1 financial-material (registry fallback)" in dashboard
    assert "using `entities.yaml` fallback" in dashboard
