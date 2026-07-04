from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "quicken.py"


def _load():
    spec = importlib.util.spec_from_file_location("quicken", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_malformed_numeric_env_falls_back(monkeypatch):
    monkeypatch.setenv("LIMEN_QUICKEN_STALE_MIN", "not-an-int")
    monkeypatch.setenv("LIMEN_QUICKEN_HORIZON_DAYS", "0")
    monkeypatch.setenv("LIMEN_QUICKEN_CLOSED_HRS", "-1")

    quicken = _load()

    assert quicken.STALE_MIN == 20
    assert quicken.HORIZON_DAYS == 3
    assert quicken.CLOSED_HRS == 18


def test_breathe_numeric_env_falls_back(monkeypatch, capsys):
    monkeypatch.setenv("LIMEN_QUICKEN_BREATHE_CAP", "bad")
    monkeypatch.setenv("LIMEN_QUICKEN_BREATHE_TIMEOUT", "0")
    quicken = _load()

    quicken.breathe([], "all", dry=True)

    assert "within cap=1" in capsys.readouterr().out
