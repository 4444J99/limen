"""Runtime configuration must not silently retrieve from a different corpus."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "corpus_resolve_under_test", Path(__file__).resolve().parents[1] / "corpus_resolve.py"
)
resolver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resolver)


@pytest.fixture(autouse=True)
def isolated_roots(monkeypatch, tmp_path):
    for name in ("LIMEN_CORPUS_ROOT", "CCE_CORPUS_STORE_ROOT", "CCE_SOURCE_DROP_ROOT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(resolver, "live_root", lambda: tmp_path / "checkout")
    monkeypatch.setattr(resolver, "registry_store_roots", list)


@pytest.mark.parametrize("exists", [False, True])
def test_configured_empty_or_missing_store_never_falls_back(monkeypatch, tmp_path, exists):
    configured = tmp_path / "configured"
    if exists:
        configured.mkdir()
    stale = tmp_path / "stale"
    (stale / "populated-corpus").mkdir(parents=True)
    monkeypatch.setattr(resolver, "registry_store_roots", lambda: [stale])
    monkeypatch.setenv("CCE_CORPUS_STORE_ROOT", str(configured))
    assert resolver.corpus_home_candidates() == [configured]
    assert resolver.corpus_home() == configured


def test_explicit_consumer_override_has_precedence(monkeypatch, tmp_path):
    override = tmp_path / "override"
    monkeypatch.setenv("LIMEN_CORPUS_ROOT", str(override))
    monkeypatch.setenv("CCE_CORPUS_STORE_ROOT", str(tmp_path / "shared"))
    monkeypatch.setenv("CCE_SOURCE_DROP_ROOT", str(tmp_path / "legacy" / "source-drop"))
    assert resolver.corpus_home() == override


def test_shared_store_precedes_legacy_drop(monkeypatch, tmp_path):
    shared = tmp_path / "shared"
    monkeypatch.setenv("CCE_CORPUS_STORE_ROOT", str(shared))
    monkeypatch.setenv("CCE_SOURCE_DROP_ROOT", str(tmp_path / "legacy" / "source-drop"))
    assert resolver.corpus_home() == shared


def test_only_legacy_drop_variable_is_normalized(monkeypatch, tmp_path):
    drop = tmp_path / "store" / "source-drop"
    monkeypatch.setenv("CCE_SOURCE_DROP_ROOT", str(drop))
    assert resolver.corpus_home() == drop.parent
    monkeypatch.setenv("CCE_CORPUS_STORE_ROOT", str(drop))
    assert resolver.corpus_home() == drop


def test_unconfigured_discovery_retains_registry_precedence(monkeypatch, tmp_path):
    registered = tmp_path / "registered"
    (registered / "corpus").mkdir(parents=True)
    monkeypatch.setattr(resolver, "registry_store_roots", lambda: [registered])
    assert resolver.corpus_home() == registered


@pytest.mark.parametrize("variable", ["LIMEN_CORPUS_ROOT", "CCE_CORPUS_STORE_ROOT", "CCE_SOURCE_DROP_ROOT"])
def test_relative_configuration_is_rejected(monkeypatch, variable):
    monkeypatch.setenv(variable, "relative/store")
    with pytest.raises(ValueError, match="absolute"):
        resolver.corpus_home()


def test_explicit_repository_root_is_rejected(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    (checkout / "scripts").mkdir(parents=True)
    (checkout / "cli").mkdir()
    monkeypatch.setenv("CCE_CORPUS_STORE_ROOT", str(checkout))
    with pytest.raises(ValueError, match="repository checkout"):
        resolver.corpus_home()
