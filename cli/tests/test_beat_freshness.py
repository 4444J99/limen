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


def test_absent_resident_passes(tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(mod, "PLISTS", (tmp_path / "heartbeat.plist", tmp_path / "watchdog.plist"))
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )
    assert mod.main() == 0
    assert "content digests" in capsys.readouterr().out


def test_resident_process_fails_with_retirement_command(tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(mod, "PLISTS", (tmp_path / "heartbeat.plist", tmp_path / "watchdog.plist"))
    monkeypatch.setattr(mod, "_label_loaded", lambda _label: False)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="123\n", stderr=""),
    )
    assert mod.main() == 1
    assert "domus-limen-runtime retire-heartbeat" in capsys.readouterr().out


def test_installed_plist_fails_even_without_process(tmp_path, monkeypatch, capsys):
    mod = _load()
    heartbeat = tmp_path / "heartbeat.plist"
    heartbeat.write_text("stale", encoding="utf-8")
    monkeypatch.setattr(mod, "PLISTS", (heartbeat, tmp_path / "watchdog.plist"))
    monkeypatch.setattr(mod, "_label_loaded", lambda _label: False)
    monkeypatch.setattr(mod, "_resident_pids", lambda: [])
    assert mod.main() == 1
    assert "plist:heartbeat.plist" in capsys.readouterr().out


def test_loaded_label_fails_even_without_plist_or_process(tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(mod, "PLISTS", (tmp_path / "heartbeat.plist", tmp_path / "watchdog.plist"))
    monkeypatch.setattr(mod, "_label_loaded", lambda label: label == "com.limen.watchdog")
    monkeypatch.setattr(mod, "_resident_pids", lambda: [])
    assert mod.main() == 1
    assert "label:com.limen.watchdog" in capsys.readouterr().out


def test_gate_off_skips(monkeypatch, capsys):
    mod = _load()
    monkeypatch.setenv("LIMEN_BEAT_FRESHNESS", "0")
    assert mod.main() == 0
    assert "skip" in capsys.readouterr().out
