"""The freshness predicate accepts containment or the reviewed one-shot runtime."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import plistlib

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-beat-freshness.py"


def _load():
    spec = importlib.util.spec_from_file_location("beat_freshness_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _paths(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "HEARTBEAT_PLIST", tmp_path / "com.limen.heartbeat.plist")
    monkeypatch.setattr(mod, "WATCHDOG_PLIST", tmp_path / "com.limen.watchdog.plist")
    monkeypatch.setattr(mod, "PUBLIC_RECEIPT", tmp_path / "public-latest.json")


def test_absent_runtime_is_safe_containment(tmp_path, monkeypatch, capsys):
    mod = _load()
    _paths(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_label_loaded", lambda _label: False)
    monkeypatch.setattr(mod, "_resident_pids", lambda: [])
    assert mod.main() == 0
    assert "safely contained" in capsys.readouterr().out


def test_compliant_one_shot_runtime_passes(tmp_path, monkeypatch, capsys):
    mod = _load()
    _paths(mod, tmp_path, monkeypatch)
    sha = "a" * 40
    with mod.HEARTBEAT_PLIST.open("wb") as handle:
        plistlib.dump(
            {
                "Label": mod.HEARTBEAT_LABEL,
                "ProgramArguments": [f"/store/runtimes/{sha}/venv/bin/limen", "heartbeat", "--once"],
                "KeepAlive": False,
                "RunAtLoad": False,
                "StartInterval": 900,
                "ProcessType": "Background",
                "LowPriorityIO": True,
                "Nice": 15,
            },
            handle,
        )
    mod.PUBLIC_RECEIPT.write_text(json.dumps({"runtime_sha": sha}))
    monkeypatch.setattr(mod, "_label_loaded", lambda label: label == mod.HEARTBEAT_LABEL)
    monkeypatch.setattr(mod, "_resident_pids", lambda: [])
    assert mod.main() == 0
    assert "active one-shot" in capsys.readouterr().out


def test_keepalive_runtime_fails(tmp_path, monkeypatch, capsys):
    mod = _load()
    _paths(mod, tmp_path, monkeypatch)
    with mod.HEARTBEAT_PLIST.open("wb") as handle:
        plistlib.dump({"KeepAlive": True, "ProgramArguments": []}, handle)
    monkeypatch.setattr(mod, "_label_loaded", lambda label: label == mod.HEARTBEAT_LABEL)
    monkeypatch.setattr(mod, "_resident_pids", lambda: [])
    assert mod.main() == 1
    assert "contract:keepalive" in capsys.readouterr().out


def test_watchdog_or_legacy_descendant_fails(tmp_path, monkeypatch, capsys):
    mod = _load()
    _paths(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_label_loaded", lambda label: label == mod.WATCHDOG_LABEL)
    monkeypatch.setattr(mod, "_resident_pids", lambda: [123])
    assert mod.main() == 1
    output = capsys.readouterr().out
    assert "label:com.limen.watchdog" in output
    assert "processes:1" in output


def test_partial_label_plist_state_fails(tmp_path, monkeypatch, capsys):
    mod = _load()
    _paths(mod, tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_label_loaded", lambda label: label == mod.HEARTBEAT_LABEL)
    monkeypatch.setattr(mod, "_resident_pids", lambda: [])
    assert mod.main() == 1
    assert "heartbeat-label-plist-partial" in capsys.readouterr().out


def test_dangling_plist_path_fails_closed(tmp_path, monkeypatch, capsys):
    mod = _load()
    _paths(mod, tmp_path, monkeypatch)
    mod.HEARTBEAT_PLIST.symlink_to(tmp_path / "missing.plist")
    monkeypatch.setattr(mod, "_label_loaded", lambda label: label == mod.HEARTBEAT_LABEL)
    monkeypatch.setattr(mod, "_resident_pids", lambda: [])
    assert mod.main() == 1
    assert "heartbeat-plist-unsafe" in capsys.readouterr().out


def test_gate_off_skips(monkeypatch, capsys):
    mod = _load()
    monkeypatch.setenv("LIMEN_BEAT_FRESHNESS", "0")
    assert mod.main() == 0
    assert "skip" in capsys.readouterr().out
