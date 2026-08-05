from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ianva" / "src"))

from ianva import mcphub  # noqa: E402


def _config() -> SimpleNamespace:
    return SimpleNamespace(host="127.0.0.1", port=7666, path="/mcp")


def test_status_treats_reachable_launchd_endpoint_as_running(monkeypatch):
    monkeypatch.setattr(mcphub, "_read_pid", lambda: 8653)
    monkeypatch.setattr(mcphub, "_alive", lambda _pid: False)
    monkeypatch.setattr(mcphub, "reachable", lambda *_args, **_kwargs: True)

    result = mcphub.status(_config())

    assert result["running"] is True
    assert result["endpoint_reachable"] is True
    assert result["pid_alive"] is False
    assert result["pidfile_state"] == "stale"


def test_status_remains_down_when_pid_and_endpoint_are_dead(monkeypatch):
    monkeypatch.setattr(mcphub, "_read_pid", lambda: None)
    monkeypatch.setattr(mcphub, "reachable", lambda *_args, **_kwargs: False)

    result = mcphub.status(_config())

    assert result["running"] is False
    assert result["pidfile_state"] == "missing"
