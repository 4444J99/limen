"""Tests for scripts/jules-quota.py — the Jules daily-quota sensor."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jules-quota.py"
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.io import save_limen_file
from limen.jules_remote import JulesRemoteSession, JulesRemoteSnapshot
from limen.models import DispatchLogEntry, LimenFile, Task


def load_jules_quota():
    spec = importlib.util.spec_from_file_location("jules_quota_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _board_with_dispatches(now: datetime) -> LimenFile:
    return LimenFile(
        tasks=[
            Task(
                id="T-1",
                title="one jules launch today",
                repo="organvm/example",
                target_agent="jules",
                status="in_progress",
                created=date(2026, 7, 23),
                dispatch_log=[
                    DispatchLogEntry(timestamp=now, agent="jules", session_id="111000000000", status="dispatched"),
                    DispatchLogEntry(timestamp=now, agent="codex", session_id="other-lane", status="dispatched"),
                    DispatchLogEntry(timestamp=now, agent="jules", session_id="111000000000", status="done"),
                ],
            )
        ]
    )


def test_used_today_counts_only_jules_dispatch_receipts_today() -> None:
    module = load_jules_quota()
    now = datetime.now(UTC)
    board = _board_with_dispatches(now)
    assert module.used_today(board, now.date()) == 1
    assert module.used_today(board, date(2000, 1, 1)) == 0


def test_main_alarms_on_orphans_and_prints_gauge(monkeypatch, tmp_path: Path, capsys) -> None:
    """An unmapped completed session turns the sensor advisory-red and shows in the gauge."""
    module = load_jules_quota()
    now = datetime.now(UTC)
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, _board_with_dispatches(now))
    snapshot = JulesRemoteSnapshot(
        available=True,
        sessions={
            "999000000000": JulesRemoteSession("999000000000", "completed", raw="999000000000  x  Completed"),
        },
    )
    monkeypatch.delenv("LIMEN_JULES_DAILY_TASKS", raising=False)
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(module, "ADOPTIONS", tmp_path / "adoptions.jsonl")
    monkeypatch.setattr(module, "probe_jules_remote_sessions", lambda: snapshot)

    assert module.main() == 1
    assert "jules-quota: used=1 target=100 orphans=1 recovery=0" in capsys.readouterr().out


def test_main_healthy_when_adopted_and_no_recovery(monkeypatch, tmp_path: Path, capsys) -> None:
    """Adopted sessions and a pre-alarm clock leave the sensor green."""
    module = load_jules_quota()
    now = datetime.now(UTC)
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, _board_with_dispatches(now))
    adoptions = tmp_path / "adoptions.jsonl"
    adoptions.write_text('{"session": "999000000000", "adopted_by": "landed by hand"}\n')
    snapshot = JulesRemoteSnapshot(
        available=True,
        sessions={
            "999000000000": JulesRemoteSession("999000000000", "completed", raw="999000000000  x  Completed"),
        },
    )
    monkeypatch.delenv("LIMEN_JULES_DAILY_TASKS", raising=False)
    monkeypatch.setenv("LIMEN_JULES_QUOTA_ALARM_HOUR", "24")
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(module, "ADOPTIONS", adoptions)
    monkeypatch.setattr(module, "probe_jules_remote_sessions", lambda: snapshot)

    assert module.main() == 0
    assert "orphans=0 recovery=0" in capsys.readouterr().out


def test_main_recovery_states_alarm(monkeypatch, tmp_path: Path, capsys) -> None:
    """Failed / awaiting-feedback sessions turn the sensor advisory-red."""
    module = load_jules_quota()
    now = datetime.now(UTC)
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, _board_with_dispatches(now))
    snapshot = JulesRemoteSnapshot(
        available=True,
        sessions={
            "888000000000": JulesRemoteSession("888000000000", "awaiting_user_feedback"),
        },
    )
    monkeypatch.delenv("LIMEN_JULES_DAILY_TASKS", raising=False)
    monkeypatch.setenv("LIMEN_JULES_QUOTA_ALARM_HOUR", "24")
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(module, "ADOPTIONS", tmp_path / "adoptions.jsonl")
    monkeypatch.setattr(module, "probe_jules_remote_sessions", lambda: snapshot)

    assert module.main() == 1
    assert "recovery=1" in capsys.readouterr().out
