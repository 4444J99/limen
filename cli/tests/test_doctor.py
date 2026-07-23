from __future__ import annotations

import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.doctor import (
    _iso,
    _task_lifecycle,
    next_actions,
    print_qa_report,
    print_readiness,
    qa_report,
    readiness_report,
    stale_tasks,
    write_report,
)
from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task


def _task(**overrides) -> Task:
    defaults = dict(
        id="T-001",
        title="Test task",
        target_agent="jules",
        priority="medium",
        budget_cost=1,
        status="open",
        created=date(2026, 6, 1),
    )
    defaults.update(overrides)
    return Task(**defaults)


def _limen(tasks: list[Task] | None = None) -> LimenFile:
    return LimenFile(
        portal=Portal(
            budget=Budget(
                daily=100,
                per_agent={"jules": 100, "codex": 50},
                track=BudgetTrack(
                    date="2026-06-20",
                    spent=10,
                    per_agent={"jules": 5, "codex": 5},
                ),
            )
        ),
        tasks=tasks or [],
    )


# ── _iso ─────────────────────────────────────────────────────────────────────


def test_iso_none() -> None:
    assert _iso(None) is None


def test_iso_datetime() -> None:
    dt = datetime(2026, 6, 20, 12, 30, 0, tzinfo=UTC)
    assert _iso(dt) == "2026-06-20T12:30:00+00:00"


def test_iso_str() -> None:
    assert _iso("2026-06-20") == "2026-06-20"


def test_iso_int() -> None:
    assert _iso(42) == "42"


# ── _task_lifecycle ──────────────────────────────────────────────────────────


def test_lifecycle_archived() -> None:
    task = _task(status="archived")
    info = _task_lifecycle(task, set())
    assert info["phase"] == "archived"
    assert info["next_gate"] == "suppressed from active steering"


def test_lifecycle_done() -> None:
    task = _task(status="done")
    info = _task_lifecycle(task, set())
    assert info["phase"] == "archive"
    assert info["next_gate"] == "archive evidence and suppress from active steering"


def test_lifecycle_stale() -> None:
    task = _task(id="T-STALE", status="dispatched")
    info = _task_lifecycle(task, {"T-STALE"})
    assert info["phase"] == "recover"
    assert info["stale"] is True


def test_lifecycle_failed() -> None:
    task = _task(status="failed")
    info = _task_lifecycle(task, set())
    assert info["phase"] == "recover"
    assert info["next_gate"] == "release stale claim or reassign with failure note"


def test_lifecycle_failed_blocked() -> None:
    task = _task(status="failed_blocked")
    info = _task_lifecycle(task, set())
    assert info["phase"] == "recover"


def test_lifecycle_needs_human() -> None:
    task = _task(status="needs_human")
    info = _task_lifecycle(task, set())
    assert info["phase"] == "recover"


def test_lifecycle_verify_via_pr() -> None:
    task = _task(
        status="dispatched",
        urls=["https://github.com/org/repo/pull/42"],
    )
    info = _task_lifecycle(task, set())
    assert info["phase"] == "verify"
    assert info["has_pr"] is True
    assert info["next_gate"] == "verify PR/runtime evidence, then close or return"


def test_lifecycle_verify_via_in_progress() -> None:
    task = _task(status="in_progress")
    info = _task_lifecycle(task, set())
    assert info["phase"] == "verify"


def test_lifecycle_assign() -> None:
    task = _task(status="open")
    info = _task_lifecycle(task, set())
    assert info["phase"] == "assign"
    assert info["next_gate"] == "assign to agent with budget and acceptance gate"


def test_lifecycle_with_issue_url() -> None:
    task = _task(
        status="open",
        urls=["https://github.com/org/repo/issues/1"],
    )
    info = _task_lifecycle(task, set())
    assert info["has_issue"] is True


def test_lifecycle_latest_event_is_updated_when_no_events() -> None:
    task = _task(created=date(2026, 6, 1))
    info = _task_lifecycle(task, set())
    assert info["latest_event_at"] is not None


def test_lifecycle_latest_event_from_dispatch_log() -> None:
    task = _task(
        dispatch_log=[
            DispatchLogEntry(
                timestamp=datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC),
                agent="jules",
                session_id="s1",
                status="dispatched",
            ),
            DispatchLogEntry(
                timestamp=datetime(2026, 6, 20, 14, 0, 0, tzinfo=UTC),
                agent="jules",
                session_id="s1",
                status="done",
            ),
        ],
    )
    info = _task_lifecycle(task, set())
    assert "2026-06-20T14:00:00" in info["latest_event_at"]


# ── stale_tasks ──────────────────────────────────────────────────────────────


def test_stale_tasks_returns_empty_for_no_tasks() -> None:
    assert stale_tasks(_limen()) == []


def test_stale_tasks_skips_open_tasks() -> None:
    limen = _limen(tasks=[_task(status="open")])
    assert stale_tasks(limen, hours=1) == []


def test_stale_tasks_skips_done_tasks() -> None:
    limen = _limen(tasks=[_task(status="done")])
    assert stale_tasks(limen, hours=1) == []


def test_stale_tasks_detects_dispatched_without_log() -> None:
    limen = _limen(tasks=[_task(status="dispatched")])
    assert len(stale_tasks(limen, hours=0)) == 1


def test_stale_tasks_respects_agent_filter() -> None:
    t1 = _task(id="T1", status="dispatched", target_agent="jules")
    t2 = _task(id="T2", status="dispatched", target_agent="codex")
    limen = _limen(tasks=[t1, t2])
    assert len(stale_tasks(limen, agent="jules")) == 1
    assert len(stale_tasks(limen, agent="codex")) == 1


def test_stale_tasks_recent_log_not_stale() -> None:
    task = _task(
        status="dispatched",
        dispatch_log=[
            DispatchLogEntry(
                timestamp=datetime.now(UTC),
                agent="jules",
                session_id="s1",
                status="dispatched",
            )
        ],
    )
    limen = _limen(tasks=[task])
    assert stale_tasks(limen, hours=24) == []


def test_stale_tasks_old_log_is_stale() -> None:
    task = _task(
        status="dispatched",
        dispatch_log=[
            DispatchLogEntry(
                timestamp=datetime(2020, 1, 1, tzinfo=UTC),
                agent="jules",
                session_id="s1",
                status="dispatched",
            )
        ],
    )
    limen = _limen(tasks=[task])
    assert len(stale_tasks(limen, hours=1)) == 1


# ── next_actions ─────────────────────────────────────────────────────────────


def test_next_actions_stale_claims() -> None:
    stale = [_task(status="dispatched")]
    actions = next_actions(stale, [], 10, True, "jules")
    assert any("release-stale" in a for a in actions)


def test_next_actions_dispatch_when_open_and_budget_and_cli() -> None:
    open_tasks = [_task(status="open")]
    actions = next_actions([], open_tasks, 10, True, "jules")
    assert any("dispatch" in a for a in actions)


def test_next_actions_install_cli_when_missing() -> None:
    actions = next_actions([], [], 10, False, "jules")
    assert any("Install" in a or "configure" in a.lower() for a in actions)


def test_next_actions_wait_for_budget() -> None:
    actions = next_actions([], [], 0, True, "jules")
    assert any("budget reset" in a or "Wait" in a for a in actions)


def test_next_actions_no_action() -> None:
    actions = next_actions([], [], 10, True, "jules")
    assert any("No immediate action" in a for a in actions)


# ── readiness_report ─────────────────────────────────────────────────────────


def test_readiness_report_all_pass(tmp_path: Path, monkeypatch) -> None:
    p = tmp_path / "tasks.yaml"
    p.write_text(
        "version: '1.0'\nportal:\n  budget:\n    daily: 100\n    track:\n      date: '2026-06-20'\n      spent: 0\n      per_agent:\n        jules: 0\n  name: Test\n"
    )
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "http://localhost:8000")
    monkeypatch.setenv("LIMEN_JULES_BIN", "python3")
    limen = _limen(tasks=[_task(status="open")])
    report = readiness_report(limen, p, agent="jules")
    assert report["status"] in ("ready", "degraded")


def test_readiness_report_uses_lane_catalog_for_local_agents(tmp_path: Path, monkeypatch) -> None:
    for binary in ("opencode", "agy", "gemini"):
        path = tmp_path / binary
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    p = tmp_path / "tasks.yaml"
    p.write_text("version: '1.0'\n")
    for agent in ("opencode", "agy", "gemini"):
        limen = _limen(tasks=[_task(target_agent=agent, status="open")])
        report = readiness_report(limen, p, agent=agent)
        check = next(c for c in report["checks"] if c["id"] == "agent_cli")
        assert check["status"] == "pass"
        assert "agent-dispatch" not in check["detail"]


def test_readiness_report_tasks_file_missing(tmp_path: Path) -> None:
    p = tmp_path / "tasks.yaml"
    limen = _limen(tasks=[_task(status="open")])
    report = readiness_report(limen, p, agent="jules")
    assert any(c["id"] == "tasks_file" and c["status"] == "fail" for c in report["checks"])


def test_readiness_report_no_tasks_warns(tmp_path: Path) -> None:
    p = tmp_path / "tasks.yaml"
    p.write_text(
        "version: '1.0'\nportal:\n  budget:\n    daily: 100\n    track:\n      date: '2026-06-20'\n      spent: 0\n  name: Test\n"
    )
    limen = _limen()
    report = readiness_report(limen, p, agent="jules")
    assert any(c["id"] == "task_count" and c["status"] == "warn" for c in report["checks"])


def test_readiness_report_stale_generates_warn(tmp_path: Path) -> None:
    p = tmp_path / "tasks.yaml"
    p.write_text(
        "version: '1.0'\nportal:\n  budget:\n    daily: 100\n    track:\n      date: '2026-06-20'\n      spent: 0\n  name: Test\n"
    )
    limen = _limen(tasks=[_task(status="dispatched")])
    report = readiness_report(limen, p, agent="jules")
    assert any(c["id"] == "stale_claims" and c["status"] == "warn" for c in report["checks"])


def test_readiness_report_budget_exhausted(tmp_path: Path) -> None:
    p = tmp_path / "tasks.yaml"
    p.write_text("version: '1.0'\n")
    limen = LimenFile(
        portal=Portal(
            budget=Budget(
                daily=10,
                per_agent={"jules": 10},
                track=BudgetTrack(
                    date="2026-06-20",
                    spent=10,
                    per_agent={"jules": 10},
                ),
            )
        ),
        tasks=[_task(status="open")],
    )
    report = readiness_report(limen, p, agent="jules")
    assert any(c["id"] == "budget" and c["status"] == "fail" for c in report["checks"])


def test_readiness_report_open_queue_count(tmp_path: Path) -> None:
    p = tmp_path / "tasks.yaml"
    p.write_text(
        "version: '1.0'\nportal:\n  budget:\n    daily: 100\n    track:\n      date: '2026-06-20'\n      spent: 0\n  name: Test\n"
    )
    limen = _limen(tasks=[_task(id="O1", status="open"), _task(id="O2", status="open")])
    report = readiness_report(limen, p, agent="jules")
    assert report["counts"]["open"] == 2
    assert report["counts"]["total"] == 2


def test_readiness_report_counts_active() -> None:
    limen = _limen(
        tasks=[
            _task(id="D1", status="dispatched"),
            _task(id="D2", status="in_progress"),
        ]
    )
    p = Path("/nonexistent/tasks.yaml")
    report = readiness_report(limen, p, agent="jules")
    assert report["counts"]["active"] == 2


# ── qa_report ────────────────────────────────────────────────────────────────


def test_qa_report_empty_limen(tmp_path: Path) -> None:
    p = tmp_path / "tasks.yaml"
    p.write_text("")
    report = qa_report(_limen(), p, agent="jules")
    assert report["status"] == "ok"
    assert report["lifecycle"]["total"] == 0


def test_qa_report_with_archived_task(tmp_path: Path) -> None:
    p = tmp_path / "tasks.yaml"
    p.write_text("")
    limen = _limen(tasks=[_task(status="archived")])
    report = qa_report(limen, p, agent="jules")
    assert report["lifecycle"]["archived"] == 1


def test_qa_report_all_phases(tmp_path: Path) -> None:
    p = tmp_path / "tasks.yaml"
    p.write_text("")
    now = datetime.now(UTC)
    limen = _limen(
        tasks=[
            _task(id="A", status="open", priority="high"),
            _task(
                id="B",
                status="dispatched",
                urls=["https://github.com/org/repo/pull/1"],
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id="s1",
                        status="dispatched",
                    )
                ],
            ),
            _task(id="C", status="done"),
            _task(id="D", status="archived"),
        ]
    )
    report = qa_report(limen, p, agent="jules")
    assert report["lifecycle"]["assign"] == 1
    assert report["lifecycle"]["verify"] == 1
    assert report["lifecycle"]["archive_ready"] == 1
    assert report["lifecycle"]["archived"] == 1


def test_qa_report_uses_supplied_now_for_stale_boundary(tmp_path: Path) -> None:
    p = tmp_path / "tasks.yaml"
    p.write_text("")
    dispatched_at = datetime(2026, 6, 27, 4, 3, 34, 586517, tzinfo=UTC)
    task = _task(
        id="BOUNDARY",
        status="dispatched",
        dispatch_log=[
            DispatchLogEntry(
                timestamp=dispatched_at,
                agent="jules",
                session_id="s1",
                status="dispatched",
            )
        ],
    )
    before_cutoff = datetime(2026, 6, 28, 4, 3, 33, 908000, tzinfo=UTC)
    after_cutoff = datetime(2026, 6, 28, 4, 3, 35, 0, tzinfo=UTC)

    static_time_report = qa_report(_limen(tasks=[task]), p, agent="jules", now=before_cutoff)
    later_report = qa_report(_limen(tasks=[task]), p, agent="jules", now=after_cutoff)

    assert static_time_report["lifecycle"]["verify"] == 1
    assert static_time_report["lifecycle"]["recover"] == 0
    assert later_report["lifecycle"]["verify"] == 0
    assert later_report["lifecycle"]["recover"] == 1


# ── print_readiness ──────────────────────────────────────────────────────────


def test_print_readiness_ready(capsys) -> None:
    report = {
        "status": "ready",
        "agent": "jules",
        "checks": [
            {"id": "tasks_file", "status": "pass", "detail": "/path/tasks.yaml"},
            {"id": "budget", "status": "pass", "detail": "50/100 runs remaining"},
        ],
        "next_actions": ["No immediate action required"],
    }
    print_readiness(report)
    out = capsys.readouterr().out
    assert "ready" in out
    assert "tasks_file" in out
    assert "No immediate action" in out


def test_print_readiness_blocked(capsys) -> None:
    report = {
        "status": "blocked",
        "agent": "jules",
        "checks": [
            {"id": "agent_cli", "status": "fail", "detail": "jules not found"},
        ],
        "next_actions": ["Install or configure jules dispatch CLI"],
    }
    print_readiness(report)
    out = capsys.readouterr().out
    assert "blocked" in out
    assert "FAIL" in out


# ── print_qa_report ──────────────────────────────────────────────────────────


def test_print_qa_report_ok(capsys) -> None:
    report = {
        "status": "ok",
        "agent": "jules",
        "lifecycle": {"recover": 0, "verify": 0, "assign": 0, "archive_ready": 0},
        "steering": {"next_batch": []},
        "mechanisms": [
            {"id": "release-stale", "label": "Release stale claims", "count": 0, "command": "POST /api/release-stale"},
        ],
    }
    print_qa_report(report)
    out = capsys.readouterr().out
    assert "qa" in out
    assert "release-stale" in out


def test_print_qa_report_with_items(capsys) -> None:
    report = {
        "status": "degraded",
        "agent": "jules",
        "lifecycle": {"recover": 1, "verify": 2, "assign": 3, "archive_ready": 4},
        "steering": {
            "next_batch": [
                {"phase": "RECOVER", "id": "T-001", "assignee": "jules", "title": "Fix bug"},
                {"phase": "VERIFY", "id": "T-002", "assignee": "codex", "title": "Add feature"},
            ]
        },
        "mechanisms": [
            {"id": "release-stale", "label": "Release stale claims", "count": 1, "command": "POST /api/release-stale"},
            {"id": "qa-verify", "label": "Verify PR evidence", "count": 2, "command": "POST /api/tasks/{id}/verify"},
        ],
    }
    print_qa_report(report)
    out = capsys.readouterr().out
    assert "degraded" in out
    assert "RECOVER" in out
    assert "T-001" in out


# ── write_report ─────────────────────────────────────────────────────────────


def test_write_report_with_path(tmp_path: Path) -> None:
    out = tmp_path / "reports" / "doctor.json"
    report = {"status": "ready", "agent": "jules"}
    write_report(report, out)
    assert out.exists()
    assert json.loads(out.read_text()) == report


def test_write_report_creates_parent_dir(tmp_path: Path) -> None:
    out = tmp_path / "a" / "b" / "report.json"
    report = {"status": "ok"}
    write_report(report, out)
    assert out.exists()


def test_write_report_none_path_does_nothing() -> None:
    write_report({"status": "ok"}, None)
