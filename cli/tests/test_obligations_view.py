import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "obligations-view.py"


def _load(monkeypatch, root: Path):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_OBLIGATIONS_LEDGER", str(root / "obligations-ledger.json"))
    monkeypatch.setenv("LIMEN_HIS_HAND_LEVERS", str(root / "his-hand-levers.json"))
    spec = importlib.util.spec_from_file_location("obligations_view_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_view_fail_open_on_wrong_ledger_shape(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    (tmp_path / "obligations-ledger.json").write_text('["not", "a", "ledger"]')

    view = module.build_view()
    html = module.render_html(view)

    assert view["obligations"] == []
    assert view["accounts"] == []
    assert view["totals"] == {}
    assert "no obligations" in html


def test_build_view_filters_scalar_entries(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    (tmp_path / "obligations-ledger.json").write_text(
        json.dumps(
            {
                "obligations": ["bad", {"title": "Reply", "priority": 50, "verify_first": True}],
                "accounts": ["bad", {"account": "me@example.com", "fires": 1, "total": 2}],
                "totals": ["bad"],
                "noise_killers": ["bad", {"name": "Noise", "domain": "example.com"}],
                "levers": ["bad", {"id": "LEV-1", "label": "Open write door"}],
            }
        )
    )

    view = module.build_view()
    html = module.render_html(view)

    assert [o["title"] for o in view["obligations"]] == ["Reply"]
    assert [a["account"] for a in view["accounts"]] == ["me@example.com"]
    assert [n["name"] for n in view["noise_killers"]] == ["Noise"]
    assert [lev["id"] for lev in view["levers"]] == ["LEV-1"]
    assert "Reply" in html
