"""The compatibility freshness predicate enforces heartbeat retirement."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-beat-freshness.py"


def _load():
    spec = importlib.util.spec_from_file_location("beat_freshness_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_absent_resident_passes(monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )
    assert mod.main() == 0
    assert "content digests" in capsys.readouterr().out


def test_resident_process_fails_with_retirement_command(monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="123\n", stderr=""),
    )
    assert mod.main() == 1
    assert "domus-limen-runtime retire-heartbeat" in capsys.readouterr().out


def test_gate_off_skips(monkeypatch, capsys):
    mod = _load()
    monkeypatch.setenv("LIMEN_BEAT_FRESHNESS", "0")
    assert mod.main() == 0
    assert "skip" in capsys.readouterr().out
