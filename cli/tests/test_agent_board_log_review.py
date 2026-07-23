from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "agent-board-log-review.py"


def load_board_module():
    spec = importlib.util.spec_from_file_location("agent_board_log_review", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changed_tasks_reports_added_removed_and_modified_tasks() -> None:
    board_mod = load_board_module()
    before = {
        "tasks": [
            {"id": "same", "status": "open"},
            {"id": "changed", "status": "open"},
            {"id": "removed", "status": "failed"},
        ]
    }
    after = {
        "tasks": [
            {"id": "same", "status": "open"},
            {"id": "changed", "status": "done"},
            {"id": "added", "status": "open"},
        ]
    }

    changes = board_mod.changed_tasks(before, after)

    assert [task_id for task_id, _old, _new in changes] == ["added", "changed", "removed"]
    assert board_mod.transition(changes[0][1], changes[0][2]) == "<added>->open"
    assert board_mod.transition(changes[1][1], changes[1][2]) == "open->done"
    assert board_mod.transition(changes[2][1], changes[2][2]) == "failed-><deleted>"


def test_evidence_flags_detect_verification_receipts_and_blockers() -> None:
    board_mod = load_board_module()
    task = {
        "id": "LIMEN-1",
        "status": "done",
        "dispatch_log": [
            {
                "status": "done",
                "output": "pytest cli/tests/test_agent_board_log_review.py -q passed; PR #636 merged",
            }
        ],
    }

    assert board_mod.evidence_flags(task) == {
        "verification": True,
        "receipt": True,
        "blocker": False,
    }

    blocked = {
        "id": "LIMEN-2",
        "status": "failed_blocked",
        "dispatch_log": [{"status": "failed_blocked", "output": "blocked on missing auth"}],
    }

    assert board_mod.evidence_flags(blocked)["blocker"] is True


def test_status_counts_ignores_non_task_rows() -> None:
    board_mod = load_board_module()
    board = {"tasks": [{"id": "a", "status": "open"}, "not-a-task", {"id": "b", "status": "done"}]}

    assert board_mod.status_counts(board) == {"open": 1, "done": 1}
