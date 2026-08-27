"""Tests for the canonical-owner shipping-count producer."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ships-24h-refresh.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ships_24h_refresh", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_owners_derive_from_estate_registry(monkeypatch):
    module = _load_module()
    fake = SimpleNamespace(
        load_estate=lambda: {"registry": "estate"},
        owners=lambda estate: ["organvm", "4444J99", "organvm-i-theoria"] if estate == {"registry": "estate"} else [],
    )
    monkeypatch.delenv("LIMEN_OWNERS", raising=False)
    monkeypatch.setattr(module, "_gitvs", lambda: fake)

    assert module.canonical_owners() == ["organvm", "4444J99", "organvm-i-theoria"]


def test_explicit_owner_override_is_deduplicated(monkeypatch):
    module = _load_module()
    monkeypatch.setenv("LIMEN_OWNERS", "one,two,one")
    monkeypatch.setattr(
        module,
        "_gitvs",
        lambda: (_ for _ in ()).throw(AssertionError("registry should not be loaded")),
    )

    assert module.canonical_owners() == ["one", "two"]
