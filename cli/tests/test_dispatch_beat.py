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


def test_a_stale_host_marker_is_dropped_rather_than_forwarded(monkeypatch, tmp_path, capsys):
    """The beat reaches dispatch as a GRANDCHILD of DomusAgentHost: heartbeat-loop.sh holds the
    lifetime pipe, beat-sensors' Popen closes it, and only the env survives. The engine then
    inherited `ACTIVE=1` with a dead (or already reused) descriptor and refused every launch —
    "refusing an unstable TCC principal" on every jules task, silent behind this script's exit 0,
    for 19 days. A claim that cannot be backed must be dropped so the engine takes its first-launch
    path and wraps the agent CLI in a fresh host holding a real pipe."""
    mod = _load(monkeypatch, tmp_path)
    read_fd, write_fd = os.pipe()
    os.close(read_fd)
    os.close(write_fd)  # the descriptor a nested child would NOT have inherited
    env = {
        "DOMUS_AGENT_HOST_ACTIVE": "1",
        "DOMUS_AGENT_HOST_LIFETIME_FD": str(write_fd),
        "DOMUS_AGENT_HOST_LIFETIME_ID": f"{'0' * 16}:1:1",
    }

    assert mod._forwardable_lifetime_fds(env) == ()
    assert env == {}, "a claim that cannot be backed must not reach the engine"
    assert "stale" in capsys.readouterr().out


def test_a_live_host_marker_is_forwarded_and_kept(monkeypatch, tmp_path):
    """The other half: a descriptor that still verifies is handed down via pass_fds with its
    markers intact, so the engine correctly declines to nest a second host."""
    mod = _load(monkeypatch, tmp_path)
    read_fd, write_fd = os.pipe()
    try:
        lifetime = os.fstat(write_fd)
        env = {
            "DOMUS_AGENT_HOST_ACTIVE": "1",
            "DOMUS_AGENT_HOST_LIFETIME_FD": str(write_fd),
            "DOMUS_AGENT_HOST_LIFETIME_ID": f"{'0' * 16}:{lifetime.st_dev}:{lifetime.st_ino}",
        }
        assert mod._forwardable_lifetime_fds(env) == (write_fd,)
        assert env["DOMUS_AGENT_HOST_ACTIVE"] == "1", "a verified identity must be preserved"
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_no_host_marker_is_left_alone(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    env = {"PATH": "/usr/bin"}
    assert mod._forwardable_lifetime_fds(env) == ()
    assert env == {"PATH": "/usr/bin"}


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
