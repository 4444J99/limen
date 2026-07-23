"""Tests for the SELF-WATCHDOG organ (scripts/watchdog.py): the three health checks
(daemon-up / beating / not-wedged), the ONE-alert + dedupe + resolve state machine,
and the double-gated heal. launchctl/ps are mocked so no system state is touched and
LIMEN_ROOT points at a tmp dir so no live log is read or written."""

import datetime
import importlib
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "watchdog.py"


def _fresh_module(tmp_path, monkeypatch, **env):
    """Reload the module under a tmp LIMEN_ROOT so module-level paths/thresholds rebind."""
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    (tmp_path / "logs").mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("watchdog_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _now_iso(delta_sec=0):
    return (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=delta_sec)).isoformat()


def _write_logs(m, *, pid=4242, tick_age=10, pr_beats=(6, 6, 6)):
    """Lay down a pidfile + beat log with a fresh tick and given PARALLEL beats."""
    m.PIDFILE.write_text(str(pid))
    lines = []
    for n in pr_beats:
        lines.append(
            f"── PARALLEL done: 9 ran · {n} dispatched/PR · 3 no-op · "
            f"{9 - n} failed→cascade · 0 rate-limited · 0 timeout→jules"
        )
    lines.append(f"tick emitted: {_now_iso(tick_age)} total=900 open=100 spent=2/600")
    m.BEATLOG.write_text("\n".join(lines) + "\n")


def _mock_system(m, monkeypatch, *, pid_alive=True, launchd_running=True, pid=4242):
    def fake_run(args, timeout=15):
        cmd = args[0]
        if cmd == "ps":
            rc = 0 if pid_alive else 1
            return _CP(args, rc)
        if cmd == "launchctl" and args[1] == "list":
            row = f"{pid if launchd_running else '-'}\t0\t{m.LABEL}"
            return _CP(args, 0, stdout=row + "\n")
        if cmd == "launchctl" and args[1] == "kickstart":
            return _CP(args, 0, stdout="kickstarted")
        return _CP(args, 1)

    monkeypatch.setattr(m, "_run", fake_run)


class _CP:
    def __init__(self, args, rc, stdout="", stderr=""):
        self.args, self.returncode, self.stdout, self.stderr = args, rc, stdout, stderr


# --- individual checks ----------------------------------------------------------
def test_healthy_all_green(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch)
    _write_logs(m)
    _mock_system(m, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["watchdog", "--dry-run"])
    assert m.main() == 0
    assert not m.ALERT.exists()  # dry-run writes nothing


def test_malformed_numeric_env_falls_back(tmp_path, monkeypatch):
    m = _fresh_module(
        tmp_path,
        monkeypatch,
        LIMEN_LOOP_MAX="bad",
        LIMEN_LANE_TIMEOUT="bad",
        LIMEN_DISPATCH_CEILING="bad",
        LIMEN_WATCHDOG_OVERHEAD_SEC="bad",
        LIMEN_WATCHDOG_STALE_SEC="bad",
        LIMEN_WATCHDOG_MAX_FAILS="bad",
    )

    assert m.STALE_SEC == 1800 + 2400 + 600
    assert m.MAX_FAILS == 3


def test_dead_daemon_detected(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch)
    _write_logs(m)
    _mock_system(m, monkeypatch, pid_alive=False)
    ok, ev = m.check_daemon_up()
    assert ok is False and ev["pid_alive"] is False


def test_launchd_unloaded_detected(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch)
    _write_logs(m)
    _mock_system(m, monkeypatch, launchd_running=False)
    ok, ev = m.check_daemon_up()
    assert ok is False and ev["launchd_running"] is False


def test_stale_tick_detected(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch, LIMEN_WATCHDOG_STALE_SEC=300)
    _write_logs(m, tick_age=9999)
    ok, ev = m.check_beating()
    assert ok is False and ev["age_sec"] > ev["stale_sec_threshold"]


def test_wedged_dispatch_detected(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch, LIMEN_WATCHDOG_MAX_FAILS=3)
    _write_logs(m, pr_beats=(6, 0, 0, 0))  # last 3 beats produced zero PRs
    ok, ev = m.check_not_wedged()
    assert ok is False and ev["recent_pr_counts"] == [0, 0, 0]


def test_not_wedged_single_lull(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch, LIMEN_WATCHDOG_MAX_FAILS=3)
    _write_logs(m, pr_beats=(0, 6, 0))  # only one of last 3 is zero
    ok, _ = m.check_not_wedged()
    assert ok is True


# --- alert state machine: fire ONCE, dedupe, resolve ----------------------------
def test_alert_fires_once_and_is_idempotent(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch)
    _write_logs(m)
    _mock_system(m, monkeypatch, pid_alive=False)  # daemon-up fails
    monkeypatch.setattr(sys, "argv", ["watchdog"])

    assert m.main() == 1
    rec1 = json.loads(m.ALERT.read_text())
    assert rec1["active"] and "daemon-up" in rec1["failed_checks"]
    fired_at = rec1["fired_at"]
    log_lines_1 = m.WDLOG.read_text().splitlines()
    assert sum(1 for line in log_lines_1 if "FIRED" in line) == 1

    # second run, SAME failure → must NOT re-fire (no new FIRED line, fired_at unchanged)
    assert m.main() == 1
    rec2 = json.loads(m.ALERT.read_text())
    assert rec2["fired_at"] == fired_at
    log_lines_2 = m.WDLOG.read_text().splitlines()
    assert sum(1 for line in log_lines_2 if "FIRED" in line) == 1
    assert any("STILL" in line for line in log_lines_2)


def test_alert_clears_when_health_returns(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch)
    _write_logs(m)
    _mock_system(m, monkeypatch, pid_alive=False)
    monkeypatch.setattr(sys, "argv", ["watchdog"])
    m.main()
    assert json.loads(m.ALERT.read_text())["active"] is True

    # daemon recovers → next run resolves the alert
    _mock_system(m, monkeypatch, pid_alive=True)
    assert m.main() == 0
    rec = json.loads(m.ALERT.read_text())
    assert rec["active"] is False and "resolved_at" in rec
    assert any("RESOLVED" in line for line in m.WDLOG.read_text().splitlines())


# --- heal is double-gated -------------------------------------------------------
def test_heal_not_triggered_without_env_gate(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch)  # LIMEN_WATCHDOG_HEAL unset
    _write_logs(m)
    _mock_system(m, monkeypatch, pid_alive=False)
    calls = []
    monkeypatch.setattr(m, "heal", lambda: (calls.append(1), (True, "x"))[1])
    monkeypatch.setattr(sys, "argv", ["watchdog", "--heal"])
    m.main()
    assert calls == []  # flag alone is not enough


def test_heal_triggered_with_both_gates(tmp_path, monkeypatch):
    m = _fresh_module(tmp_path, monkeypatch, LIMEN_WATCHDOG_HEAL=1)
    _write_logs(m)
    _mock_system(m, monkeypatch, pid_alive=False)
    calls = []
    monkeypatch.setattr(m, "heal", lambda: (calls.append(1), (True, "kickstarted"))[1])
    monkeypatch.setattr(sys, "argv", ["watchdog", "--heal"])
    m.main()
    assert calls == [1]
    assert any("HEAL ok" in line for line in m.WDLOG.read_text().splitlines())
