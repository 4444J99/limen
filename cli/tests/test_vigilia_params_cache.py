"""Parsed panel reuse must never freeze configuration or leak mutable defaults."""

import os

import pytest

from limen.vigilia import params


@pytest.fixture
def panel(tmp_path, monkeypatch):
    path = tmp_path / "panel.yaml"
    monkeypatch.setattr(params, "panel_path", lambda: path)
    params._cached_panel.cache_clear()
    yield path
    params._cached_panel.cache_clear()


def write_panel(path, value):
    path.write_text(f"parameters:\n  VALUE:\n    default: {value}\n    env: PANEL_VALUE\n")


def test_unchanged_panel_parses_once_but_environment_remains_live(panel, monkeypatch):
    write_panel(panel, 1)
    original = params.yaml_module.safe_load
    calls = []

    def load(text):
        calls.append(text)
        return original(text)

    monkeypatch.setattr(params.yaml_module, "safe_load", load)
    monkeypatch.delenv("PANEL_VALUE", raising=False)
    for _ in range(20):
        assert params.get("VALUE", 0, cast=int) == 1
    monkeypatch.setenv("PANEL_VALUE", "2")
    assert params.get("VALUE", 0, cast=int) == 2
    monkeypatch.delenv("PANEL_VALUE")
    assert params.get("VALUE", 0, cast=int) == 1
    assert len(calls) == 1


def test_same_size_rewrite_with_preserved_mtime_invalidates(panel):
    write_panel(panel, 1)
    assert params.get("VALUE") == 1
    before = panel.stat()
    write_panel(panel, 2)
    os.utime(panel, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert params.get("VALUE") == 2


def test_atomic_replacement_invalidates(panel):
    write_panel(panel, 1)
    assert params.get("VALUE") == 1
    replacement = panel.with_suffix(".new")
    write_panel(replacement, 3)
    replacement.replace(panel)
    assert params.get("VALUE") == 3


def test_worktree_switch_uses_the_selected_panel(panel, monkeypatch):
    write_panel(panel, 1)
    assert params.get("VALUE") == 1
    other = panel.with_name("other.yaml")
    write_panel(other, 4)
    monkeypatch.setattr(params, "panel_path", lambda: other)
    assert params.get("VALUE") == 4
    monkeypatch.setattr(params, "panel_path", lambda: panel)
    assert params.get("VALUE") == 1


def test_missing_invalid_then_repaired_panel_never_reuses_stale_defaults(panel):
    write_panel(panel, 1)
    assert params.get("VALUE") == 1
    panel.unlink()
    assert params.get("VALUE", 9) == 9
    panel.write_text("parameters: [broken")
    assert params.get("VALUE", 9) == 9
    write_panel(panel, 5)
    assert params.get("VALUE") == 5


def test_callers_cannot_mutate_the_cached_panel(panel):
    write_panel(panel, "[a, b]")
    result = params.get("VALUE")
    result.append("not-persisted")
    params._load_panel()["VALUE"]["default"].append("also-not-persisted")
    assert params.get("VALUE") == ["a", "b"]


def test_racing_read_is_not_cached(panel, monkeypatch):
    write_panel(panel, 1)
    real_version = params._version
    calls = []

    def version(path):
        calls.append(path)
        if len(calls) == 3:
            write_panel(path, 7)
        return real_version(path)

    monkeypatch.setattr(params, "_version", version)
    assert params.get("VALUE", 9) == 9
    assert params.get("VALUE") == 7
    assert params._cached_panel.cache_info().currsize == 1


def test_cache_is_bounded_and_missing_yaml_fails_open(panel, monkeypatch):
    assert params._cached_panel.cache_info().maxsize == 8
    write_panel(panel, 1)
    monkeypatch.setattr(params, "yaml_module", None)
    assert params.get("VALUE", 9) == 9


def test_single_lookup_does_not_copy_unrelated_registry_entries(panel, monkeypatch):
    write_panel(panel, 1)
    calls = []
    original = params.deepcopy

    def copied(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(params, "deepcopy", copied)
    assert params.get("VALUE") == 1
    assert calls == [{"default": 1, "env": "PANEL_VALUE"}]
