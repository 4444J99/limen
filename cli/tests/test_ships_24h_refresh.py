"""Tests for the canonical-owner shipping-count producer."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ships-24h-refresh.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ships_24h_refresh", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_owners_derive_from_estate_registry(monkeypatch):
    module = _load_module()
    estate = {"schema_version": 1, "classes": {"core": []}}
    fake = SimpleNamespace(
        load_estate=lambda: estate,
        owners=lambda candidate: ["organvm", "4444J99", "organvm-i-theoria"] if candidate == estate else [],
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


def test_unreadable_canonical_registry_is_rejected(monkeypatch):
    module = _load_module()
    monkeypatch.delenv("LIMEN_OWNERS", raising=False)
    monkeypatch.setattr(
        module,
        "_gitvs",
        lambda: SimpleNamespace(load_estate=lambda: {}, owners=lambda _estate: ["organvm"]),
    )

    with pytest.raises(RuntimeError, match="canonical owner registry"):
        module.canonical_owners()


def test_unexpected_refresh_failure_returns_nonzero_without_overwriting_cache(tmp_path, monkeypatch):
    module = _load_module()
    cache = tmp_path / "ships-24h.json"
    cache.write_text("preserved", encoding="utf-8")
    monkeypatch.setattr(module, "CACHE", cache)
    monkeypatch.setattr(module, "refresh", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(module.sys, "argv", ["ships-24h-refresh.py"])

    assert module.main() == 1
    assert cache.read_text(encoding="utf-8") == "preserved"
