"""The ONE predicate: exit 0 ⟺ the compound loop turns; exit 1 names clause + owner."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task
from limen.io import save_limen_file

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jules-flywheel.py"

NOW = dt.datetime(2026, 8, 6, 20, 0, tzinfo=dt.timezone.utc)  # past the 18:00Z alarm hour


def _entry(status: str, *, hours_ago: float, session_id: str = "s") -> DispatchLogEntry:
    return DispatchLogEntry(
        timestamp=NOW - dt.timedelta(hours=hours_ago),
        agent="jules",
        session_id=session_id,
        status=status,
        output="",
    )


def _board(entries: list[DispatchLogEntry]) -> LimenFile:
    task = Task(
        id="T1",
        title="t",
        target_agent="jules",
        status="open",
        created=NOW.date(),
        dispatch_log=entries,
    )
    return LimenFile(
        portal=Portal(
            budget=Budget(
                daily=600,
                per_agent={"jules": 100},
                track=BudgetTrack(
                    date=NOW.date().isoformat(),
                    spent=0,
                    per_agent={"jules": 0},
                    per_agent_reset={"jules": NOW.isoformat()},
                ),
            )
        ),
        tasks=[task],
    )


def _load(monkeypatch, tmp_path: Path, board: LimenFile):
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, board)
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_TASKS", str(tasks_path))
    spec = importlib.util.spec_from_file_location("jules_flywheel_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _freeze_now(monkeypatch, mod):
    monkeypatch.setattr(mod, "_now", lambda: NOW)


def _gh_count(monkeypatch, mod, count):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=f"{count}\n", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)


def test_healthy_flywheel_exits_zero(monkeypatch, tmp_path, capsys):
    entries = [_entry("dispatched", hours_ago=float(i % 20) + 1, session_id=f"s{i}") for i in range(80)]
    entries += [_entry("done", hours_ago=2.0, session_id=f"d{i}") for i in range(30)]
    mod = _load(monkeypatch, tmp_path, _board(entries))
    _freeze_now(monkeypatch, mod)
    _gh_count(monkeypatch, mod, 100)
    assert mod.main() == 0
    assert "OK" in capsys.readouterr().out


def test_quota_clause_fails_after_alarm_hour_and_names_owners(monkeypatch, tmp_path, capsys):
    mod = _load(monkeypatch, tmp_path, _board([]))
    _freeze_now(monkeypatch, mod)
    _gh_count(monkeypatch, mod, 100)
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "quota" in out
    assert "jules-supply" in out and "dispatch-beat" in out


def test_landing_clause_skipped_below_bootstrap_min(monkeypatch, tmp_path, capsys):
    # 85 dispatches today (quota green), but only 10 in... window counts include today's, so
    # use a low-rate board UNDER bootstrap_min by pinning bootstrap_min high via env.
    monkeypatch.setenv("LIMEN_THROUGHPUT_BOOTSTRAP_MIN", "500")
    entries = [_entry("dispatched", hours_ago=1.0, session_id=f"s{i}") for i in range(85)]
    mod = _load(monkeypatch, tmp_path, _board(entries))
    _freeze_now(monkeypatch, mod)
    _gh_count(monkeypatch, mod, 100)
    assert mod.main() == 0
    assert "landing skipped" in capsys.readouterr().out


def test_landing_clause_fails_and_names_landing_organs(monkeypatch, tmp_path, capsys):
    entries = [_entry("dispatched", hours_ago=1.0, session_id=f"s{i}") for i in range(85)]
    entries += [_entry("done", hours_ago=2.0, session_id="d0")]  # 1/85 ≈ 1%
    mod = _load(monkeypatch, tmp_path, _board(entries))
    _freeze_now(monkeypatch, mod)
    _gh_count(monkeypatch, mod, 100)
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "landing" in out and "owner-route-drain" in out


def test_debt_rise_fails_and_snapshot_updates(monkeypatch, tmp_path, capsys):
    entries = [_entry("dispatched", hours_ago=float(i % 20) + 1, session_id=f"s{i}") for i in range(80)]
    entries += [_entry("done", hours_ago=2.0, session_id=f"d{i}") for i in range(30)]
    mod = _load(monkeypatch, tmp_path, _board(entries))
    _freeze_now(monkeypatch, mod)
    mod.SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    mod.SNAPSHOT.write_text(json.dumps({"open_jules_prs": 300}))
    _gh_count(monkeypatch, mod, 310)
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "debt" in out and "300 -> 310" in out
    assert json.loads(mod.SNAPSHOT.read_text())["open_jules_prs"] == 310


def test_gh_unavailable_fails_open_on_debt(monkeypatch, tmp_path, capsys):
    entries = [_entry("dispatched", hours_ago=float(i % 20) + 1, session_id=f"s{i}") for i in range(80)]
    entries += [_entry("done", hours_ago=2.0, session_id=f"d{i}") for i in range(30)]
    mod = _load(monkeypatch, tmp_path, _board(entries))
    _freeze_now(monkeypatch, mod)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="no gh"))
    assert mod.main() == 0
    assert "probe_unavailable" in capsys.readouterr().out
