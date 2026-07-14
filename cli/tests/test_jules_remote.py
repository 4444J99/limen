from __future__ import annotations

import subprocess
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import limen.jules_remote as jr
import limen.dispatch as dispatch_module
from limen.dispatch import release_stale_tasks
from limen.io import load_limen_file, save_limen_file
from limen.jules_remote import (
    JulesRemoteSession,
    JulesRemoteSnapshot,
    classify_jules_claim,
    coerce_jules_snapshot,
    parse_jules_remote_sessions,
)
from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task


SID = "12345678901234567890"


def _write_stale_board(path: Path, *, target_agent: str = "jules") -> None:
    stale = datetime(2026, 1, 1, tzinfo=timezone.utc)
    save_limen_file(
        path,
        LimenFile(
            portal=Portal(budget=Budget(daily=100, track=BudgetTrack(date="2026-01-01"))),
            tasks=[
                Task(
                    id="STALE",
                    title="stale claim",
                    repo="organvm/limen",
                    target_agent=target_agent,
                    status="dispatched",
                    created=date(2026, 1, 1),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=stale,
                            agent=target_agent,
                            session_id=SID if target_agent == "jules" else "local-session",
                            status="dispatched",
                        )
                    ],
                )
            ],
        ),
    )


def _snapshot(
    status: str | None,
    *,
    available: bool = True,
    exhaustive: bool = False,
    confirmed_absent: frozenset[str] = frozenset(),
) -> JulesRemoteSnapshot:
    sessions = {} if status is None else {SID: JulesRemoteSession(SID, status)}
    return JulesRemoteSnapshot(
        available=available,
        sessions=sessions,
        exhaustive=exhaustive,
        confirmed_absent=confirmed_absent,
    )


def _apply(path: Path, snapshot: JulesRemoteSnapshot, *, target_agent: str = "jules"):
    _write_stale_board(path, target_agent=target_agent)
    report = release_stale_tasks(
        load_limen_file(path),
        path,
        hours=24,
        dry_run=False,
        jules_snapshot=snapshot,
    )
    return report, load_limen_file(path).tasks[0]


def test_present_unknown_jules_session_is_held(tmp_path: Path) -> None:
    report, task = _apply(tmp_path / "tasks.yaml", _snapshot("unknown"))

    assert task.status == "dispatched"
    assert report["held"] == ["STALE"]
    assert report["released"] == []


def test_completed_jules_session_routes_to_harvest_without_reopening(tmp_path: Path) -> None:
    report, task = _apply(tmp_path / "tasks.yaml", _snapshot("completed"))

    assert task.status == "dispatched"
    assert report["harvest_ready"] == ["STALE"]
    assert report["released"] == []


def test_failed_jules_session_routes_to_recovery_without_reopening(tmp_path: Path) -> None:
    report, task = _apply(tmp_path / "tasks.yaml", _snapshot("failed"))

    assert task.status == "dispatched"
    assert report["recover_ready"] == ["STALE"]
    assert report["released"] == []


@pytest.mark.parametrize("status", ["awaiting_user_feedback", "awaiting_plan_approval"])
def test_awaiting_jules_session_routes_to_recovery_without_reopening(tmp_path: Path, status: str) -> None:
    report, task = _apply(tmp_path / "tasks.yaml", _snapshot(status))

    assert task.status == "dispatched"
    assert report["recover_ready"] == ["STALE"]
    assert report["released"] == []


def test_confirmed_absent_jules_session_is_reopened(tmp_path: Path) -> None:
    report, task = _apply(tmp_path / "tasks.yaml", _snapshot(None, exhaustive=True))

    assert task.status == "open"
    assert report["released"] == ["STALE"]
    assert report["candidates"][0]["remote_status"] == "absent"


def test_non_exhaustive_catalog_miss_holds_jules_claim(tmp_path: Path) -> None:
    other_sid = "99999999999999999999"
    snapshot = JulesRemoteSnapshot(
        available=True,
        sessions={other_sid: JulesRemoteSession(other_sid, "in_progress")},
        exhaustive=False,
    )

    report, task = _apply(tmp_path / "tasks.yaml", snapshot)

    assert task.status == "dispatched"
    assert report["held"] == ["STALE"]
    assert report["released"] == []
    assert report["candidates"][0]["remote_status"] == "absence_unconfirmed"
    assert report["remote_probe"]["catalog_exhaustive"] is False


def test_session_specific_confirmed_absence_reopens_without_complete_catalog(tmp_path: Path) -> None:
    report, task = _apply(
        tmp_path / "tasks.yaml",
        _snapshot(None, confirmed_absent=frozenset({SID})),
    )

    assert task.status == "open"
    assert report["released"] == ["STALE"]
    assert report["remote_probe"]["catalog_exhaustive"] is False
    assert report["remote_probe"]["confirmed_absent_count"] == 1


def test_legacy_mapping_preserves_statuses_but_cannot_prove_absence() -> None:
    snapshot = coerce_jules_snapshot({"99999999999999999999": "completed"})

    assert snapshot.exhaustive is False
    assert classify_jules_claim(snapshot, SID) == ("hold", "absence_unconfirmed")


def test_jules_cli_unavailable_holds_claim(tmp_path: Path) -> None:
    report, task = _apply(tmp_path / "tasks.yaml", _snapshot(None, available=False))

    assert task.status == "dispatched"
    assert report["held"] == ["STALE"]
    assert report["remote_probe"]["status"] == "unavailable"


def test_non_jules_stale_claim_keeps_age_based_release_behavior(tmp_path: Path) -> None:
    report, task = _apply(
        tmp_path / "tasks.yaml",
        _snapshot(None, available=False),
        target_agent="codex",
    )

    assert task.status == "open"
    assert report["released"] == ["STALE"]
    assert report["remote_probe"]["status"] == "not_requested"


def test_remote_list_parser_classifies_shared_status_vocabulary() -> None:
    sessions = parse_jules_remote_sessions(
        "\n".join(
            [
                f"{SID}  ordinary task  organvm/limen  1h2m ago  Completed",
                "222222222222  ordinary task  organvm/limen  1h ago  Awaiting User F",
                "333333333333  ordinary task  organvm/limen  2h ago  Failed",
                "444444444444  Fix failed CI  organvm/limen  3h ago",
                "555555555555  Completed migration audit  organvm/limen  4h ago",
                "666666666666  Fix failed CI  organvm/limen  5h ago  Completed",
            ]
        )
    )

    assert sessions[SID].status == "completed"
    assert sessions["222222222222"].status == "awaiting_user_feedback"
    assert sessions["333333333333"].status == "failed"
    assert sessions["444444444444"].status == "unknown"
    assert sessions["555555555555"].status == "unknown"
    assert sessions["666666666666"].status == "completed"


def test_remote_probe_completes_before_single_writer_lock(tmp_path: Path, monkeypatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    _write_stale_board(tasks_path)
    inside_lock = False

    def probe():
        assert inside_lock is False
        return _snapshot("unknown")

    @contextmanager
    def queue_lock(_path):
        nonlocal inside_lock
        inside_lock = True
        try:
            yield True
        finally:
            inside_lock = False

    monkeypatch.setattr(dispatch_module, "probe_jules_remote_sessions", probe)
    monkeypatch.setattr(dispatch_module, "_queue_lock", queue_lock)

    report = release_stale_tasks(load_limen_file(tasks_path), tasks_path, hours=24, dry_run=False)

    assert report["held"] == ["STALE"]
    assert inside_lock is False


def test_remote_probe_distinguishes_unavailable_from_confirmed_empty(monkeypatch) -> None:
    monkeypatch.setattr(jr.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    unavailable = jr.probe_jules_remote_sessions()

    monkeypatch.setattr(
        jr.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    )
    empty = jr.probe_jules_remote_sessions()

    assert unavailable.available is False
    assert empty.available is True
    assert empty.sessions == {}
    assert empty.exhaustive is False
