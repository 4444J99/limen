"""CLI selection and compatibility tests for scripts/jules-land.py."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jules-land.py"
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import DispatchLogEntry, LimenFile, Task  # noqa: E402


def load_jules_land():
    spec = importlib.util.spec_from_file_location("jules_land_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_main_does_not_change_failed_row_with_existing_session_pr(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-PR",
                    title="already landed",
                    repo="organvm/example",
                    target_agent="jules",
                    status="failed",
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=datetime.now(timezone.utc),
                            agent="jules",
                            session_id="123",
                            status="dispatched",
                        ),
                        DispatchLogEntry(
                            timestamp=datetime.now(timezone.utc),
                            agent="jules",
                            session_id=("https://github.com/organvm/example/pull/42"),
                            status="done",
                            output="jules-land: landed session 123 as PR",
                        ),
                    ],
                )
            ]
        ),
    )
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(
        module,
        "completed_sessions",
        lambda _sid_map: [("123", "T-PR")],
    )
    monkeypatch.setattr(sys, "argv", ["jules-land.py", "--apply", "--recover"])

    assert module.main() == 0
    assert load_limen_file(tasks_path).tasks[0].status == "failed"


def test_main_routes_newer_session_after_older_pr_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    now = datetime.now(timezone.utc)
    save_limen_file(
        tasks_path,
        LimenFile(
            tasks=[
                Task(
                    id="T-PR-NEWER",
                    title="new follow-up session",
                    repo="organvm/example",
                    target_agent="jules",
                    status="failed",
                    created=date(2026, 7, 17),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="123",
                            status="dispatched",
                        ),
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id=("https://github.com/organvm/example/pull/42"),
                            status="done",
                            output="jules-land: landed session 123 as PR",
                        ),
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id="456",
                            status="dispatched",
                        ),
                    ],
                )
            ]
        ),
    )
    attempted: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(
        module,
        "completed_sessions",
        lambda _sid_map: [("456", "T-PR-NEWER")],
    )
    monkeypatch.setattr(
        module,
        "process_session",
        lambda _path, task_id, sid, **_kwargs: attempted.append((task_id, sid)) or False,
    )
    monkeypatch.setattr(sys, "argv", ["jules-land.py", "--apply", "--recover"])

    assert module.main() == 0
    assert attempted == [("T-PR-NEWER", "456")]


def test_main_limit_bounds_attempted_sessions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, LimenFile(tasks=[]))
    attempted: list[tuple[str, str]] = []

    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(
        module,
        "completed_sessions",
        lambda _sid_map: [("101", "T1"), ("102", "T2"), ("103", "T3")],
    )
    monkeypatch.setattr(
        module,
        "process_session",
        lambda _path, task_id, sid, **_kwargs: attempted.append((task_id, sid)) or False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["jules-land.py", "--apply", "--limit", "2"],
    )

    assert module.main() == 0
    assert attempted == [("T1", "101"), ("T2", "102")]
