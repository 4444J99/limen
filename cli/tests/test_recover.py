import datetime as dt
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "recover.py"


def test_recover_reopens_failed_jules_remote_session(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
        tasks=[
            Task(
                id="HEAL-rebase-organvm-public-record-data-scrapper-335",
                title="rebase public record",
                repo="organvm/public-record-data-scrapper",
                target_agent="jules",
                status="dispatched",
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id="16647959386662614769",
                        status="dispatched",
                    )
                ],
            )
        ],
    )
    save_limen_file(tasks_path, lf)

    spec = importlib.util.spec_from_file_location("recover_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "live_jules_sessions", lambda: {"16647959386662614769": "failed"})
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

    assert module.main() == 0
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "open"
    assert task.target_agent == "codex"
    assert "is failed" in task.dispatch_log[-1].output


def test_recover_reopens_jules_session_awaiting_feedback(tmp_path, monkeypatch):
    tasks_path = tmp_path / "tasks.yaml"
    now = dt.datetime.now(dt.timezone.utc)
    lf = LimenFile(
        portal=Portal(budget=Budget(daily=300, per_agent={}, track=BudgetTrack(date=str(now.date())))),
        tasks=[
            Task(
                id="HEAL-cifix-organvm-mirror-mirror-106",
                title="fix mirror CI",
                repo="organvm/mirror-mirror",
                target_agent="jules",
                status="dispatched",
                created=now.date(),
                dispatch_log=[
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id="15175913208909090857",
                        status="dispatched",
                    )
                ],
            )
        ],
    )
    save_limen_file(tasks_path, lf)

    spec = importlib.util.spec_from_file_location("recover_uut_feedback", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "live_jules_sessions", lambda: {"15175913208909090857": "awaiting_user_feedback"})
    monkeypatch.setattr(sys, "argv", ["recover", "--tasks", str(tasks_path), "--apply"])

    assert module.main() == 0
    task = load_limen_file(tasks_path).tasks[0]
    assert task.status == "open"
    assert task.target_agent == "codex"
    assert "awaiting_user_feedback" in task.dispatch_log[-1].output
