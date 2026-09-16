"""Required facts with unsupported verification cannot become presence evidence."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def identity(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "identity.py"
    spec = importlib.util.spec_from_file_location("identity_verification", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_reference_integrity", lambda: [])
    monkeypatch.setattr(module, "_load_home", lambda _: {"name": "fixture"})
    return module


@pytest.mark.parametrize("mode", ["unsupported-private-value", None, [], {}])
def test_unknown_required_mode_is_unmeasured(identity, monkeypatch, capsys, mode):
    monkeypatch.setattr(
        identity, "_registry", lambda: {"fixture": {"applicable": True, "required": True, "verify": mode}}
    )
    with pytest.raises(SystemExit) as result:
        identity.cmd_verify(None)
    assert result.value.code == 77
    output = capsys.readouterr().out
    assert "UNMEASURED 1/1" in output
    assert "OK" not in output
    assert "unsupported-private-value" not in output


def test_supported_presence_mode_still_checks_fact(identity, monkeypatch, capsys):
    monkeypatch.setattr(
        identity, "_registry", lambda: {"fixture": {"applicable": True, "required": True, "atom": "name"}}
    )
    with pytest.raises(SystemExit) as result:
        identity.cmd_verify(None)
    assert result.value.code == 0
    assert "all 1" in capsys.readouterr().out


def test_known_missing_fact_and_unknown_mode_both_remain_visible(identity, monkeypatch, capsys):
    monkeypatch.setattr(
        identity,
        "_registry",
        lambda: {
            "missing": {"applicable": True, "required": True, "atom": "absent"},
            "unknown": {"applicable": True, "required": True, "verify": "unsupported"},
        },
    )
    with pytest.raises(SystemExit) as result:
        identity.cmd_verify(None)
    assert result.value.code == 1
    output = capsys.readouterr().out
    assert "UNMEASURED 1/2" in output
    assert "MISSING 1/2" in output
    assert "OK" not in output
