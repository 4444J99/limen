"""The beat's jules dispatch valve rung: governed, throttled, bounded, never a red beat."""

from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dispatch-beat.py"


def _load(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    spec = importlib.util.spec_from_file_location("dispatch_beat_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakePopen:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.pid = 4242

    def communicate(self, timeout=None):
        return "── limen dispatch (LIVE) — agent=jules\n  dispatched: T-1\n", None

    def wait(self, timeout=None):
        return 0


def test_governor_hold_means_quiet_noop(monkeypatch, tmp_path, capsys):
    mod = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=2, stdout="autonomy mode is observe\n", stderr=""),
    )

    def forbidden_popen(*a, **k):
        raise AssertionError("engine must not launch when the governor holds the valve")

    monkeypatch.setattr(mod.subprocess, "Popen", forbidden_popen)
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "governor holds the valve" in out
    assert "autonomy mode is observe" in out


def test_governor_ok_runs_serial_engine_jules_only(monkeypatch, tmp_path, capsys):
    mod = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(
        mod.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="dispatch allowed\n", stderr="")
    )
    launched: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        launched.append(list(cmd))
        return _FakePopen(cmd, **kwargs)

    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)
    assert mod.main() == 0
    assert len(launched) == 1
    cmd = launched[0]
    assert cmd[1:] == ["-m", "limen", "dispatch", "--agent", "jules", "--live", "--limit", "10"]
    assert mod.STAMP.exists()  # stamped so the next pass throttles
    assert "dispatched: T-1" in capsys.readouterr().out


def test_wall_clock_throttle_skips_within_window(monkeypatch, tmp_path, capsys):
    mod = _load(monkeypatch, tmp_path)
    mod.STAMP.parent.mkdir(parents=True, exist_ok=True)
    mod.STAMP.write_text("now\n")
    os.utime(mod.STAMP, (time.time(), time.time()))

    def forbidden(*a, **k):
        raise AssertionError("nothing may run while throttled")

    monkeypatch.setattr(mod.subprocess, "run", forbidden)
    monkeypatch.setattr(mod.subprocess, "Popen", forbidden)
    assert mod.main() == 0
    assert "throttled" in capsys.readouterr().out


def test_stale_stamp_is_not_a_throttle(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    mod.STAMP.parent.mkdir(parents=True, exist_ok=True)
    mod.STAMP.write_text("old\n")
    old = time.time() - 7200
    os.utime(mod.STAMP, (old, old))
    monkeypatch.setattr(
        mod.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="dispatch allowed\n", stderr="")
    )
    launched: list[list[str]] = []
    monkeypatch.setattr(mod.subprocess, "Popen", lambda cmd, **k: (launched.append(list(cmd)), _FakePopen(cmd))[1])
    assert mod.main() == 0
    assert launched


def test_heartbeat_loop_runs_metabolize_pass_above_observe_short_circuit():
    """The metabolize sensor pass (starvation alarm, quota/supply gauges) must fire in
    observe mode — the 15-day outage was an observe-mode outage — while dispatch stays
    impossible there because dispatch-beat self-gates on the governor."""
    source = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    pass_at = source.index("--run --source metabolize")
    observe_at = source.index('if [ "$MODE" != "dispatch" ]')
    assert pass_at < observe_at
    # the campaign-wake contract stays intact: no dispatcher strings in the loop file
    assert "dispatch-beat.py" not in source
