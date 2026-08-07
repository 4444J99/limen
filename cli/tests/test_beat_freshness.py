"""beat-freshness: exit 1 ⟺ the resident daemon predates its own loop body on disk."""

from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-beat-freshness.py"


def _load():
    spec = importlib.util.spec_from_file_location("beat_freshness_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_ps(monkeypatch, mod, *, pids: str, etime: str):
    def fake_run(cmd, **kwargs):
        if cmd[0] == "pgrep":
            return SimpleNamespace(returncode=0, stdout=pids, stderr="")
        if cmd[0] == "ps":
            return SimpleNamespace(returncode=0, stdout=etime + "\n", stderr="")
        raise AssertionError(f"unexpected command {cmd}")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)


def test_fresh_daemon_exits_zero(monkeypatch, tmp_path, capsys):
    mod = _load()
    loop = tmp_path / "heartbeat-loop.sh"
    loop.write_text("while true; do :; done\n")
    monkeypatch.setattr(mod, "LOOP", loop)
    _fake_ps(monkeypatch, mod, pids="123\n", etime="00:05")  # daemon started 5s ago
    old = time.time() - 3600
    os.utime(loop, (old, old))  # loop body last changed an hour ago -> daemon is newer
    assert mod.main() == 0
    assert "OK" in capsys.readouterr().out


def test_stale_daemon_exits_one_and_names_the_kickstart(monkeypatch, tmp_path, capsys):
    mod = _load()
    loop = tmp_path / "heartbeat-loop.sh"
    loop.write_text("while true; do :; done\n")  # mtime = now
    monkeypatch.setattr(mod, "LOOP", loop)
    _fake_ps(monkeypatch, mod, pids="123\n", etime="3-01:02:03")  # started 3+ days ago
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "STALE" in out
    assert "launchctl kickstart" in out


def test_no_daemon_is_liveness_problem_not_staleness(monkeypatch, tmp_path, capsys):
    mod = _load()
    loop = tmp_path / "heartbeat-loop.sh"
    loop.write_text("x\n")
    monkeypatch.setattr(mod, "LOOP", loop)
    _fake_ps(monkeypatch, mod, pids="", etime="")
    assert mod.main() == 0
    assert "LAUNCH_AGENT_LIVENESS" in capsys.readouterr().out


def test_gate_off_skips(monkeypatch, capsys):
    mod = _load()
    monkeypatch.setenv("LIMEN_BEAT_FRESHNESS", "0")
    assert mod.main() == 0
    assert "skip" in capsys.readouterr().out


def test_etime_parse_forms(monkeypatch, tmp_path):
    mod = _load()
    loop = tmp_path / "heartbeat-loop.sh"
    loop.write_text("x\n")
    monkeypatch.setattr(mod, "LOOP", loop)
    for raw, age in [("00:30", 30), ("05:00", 300), ("02:00:00", 7200), ("1-00:00:00", 86400)]:
        _fake_ps(monkeypatch, mod, pids="9\n", etime=raw)
        started = mod._daemon_start_epoch()
        assert started is not None
        assert abs((time.time() - started) - age) < 5, raw
