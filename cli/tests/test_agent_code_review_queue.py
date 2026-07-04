from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "agent-code-review-queue.py"


def load_queue_module():
    spec = importlib.util.spec_from_file_location("agent_code_review_queue", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_queue_splits_changed_board_and_reconstruction_rows() -> None:
    queue_mod = load_queue_module()
    review = {
        "sessions": [
            {
                "agent": "codex",
                "session_id": "code-1",
                "cwd": "/path/that/does/not/exist",
                "risk_score": 10,
                "changed_file_count": 2,
                "changed_files": ["scripts/tool.py", "cli/tests/test_tool.py"],
                "ideal_gaps": ["session outcome lacks verification signal"],
            },
            {
                "agent": "opencode",
                "session_id": "board-1",
                "cwd": "/path/that/does/not/exist",
                "risk_score": 7,
                "changed_file_count": 1,
                "changed_files": ["tasks.yaml"],
                "ideal_gaps": [],
            },
            {
                "agent": "claude",
                "session_id": "reconstruct-1",
                "cwd": "/path/that/does/not/exist",
                "risk_score": 9,
                "changed_file_count": 0,
                "changed_files": [],
                "ideal_gaps": ["prompt missing executable predicate"],
            },
        ]
    }

    queue = queue_mod.build_queue(review)

    assert queue["counts"]["changed_file_review_candidates"] == 1
    assert queue["counts"]["board_or_log_only_sessions"] == 1
    assert queue["counts"]["reconstruction_roots"] == 1
    assert queue["changed_review"][0]["session_id"] == "code-1"
    assert queue["board_only"][0]["session_id"] == "board-1"


def test_depth_stop_status_blocks_on_unreviewed_rows_above_score_floor() -> None:
    queue_mod = load_queue_module()
    queue = {
        "changed_review": [
            {"agent": "codex", "session_id": "done-1", "review_score": 150, "changed_file_count": 3},
            {"agent": "claude", "session_id": "open-1", "review_score": 120, "changed_file_count": 2},
            {"agent": "agy", "session_id": "below-floor", "review_score": 20, "changed_file_count": 5},
        ],
        "board_only": [{"agent": "opencode", "session_id": "board-open", "review_score": 101, "changed_file_count": 1}],
    }

    status = queue_mod.depth_stop_status(
        queue,
        "| 1 | `codex` | `done-1` | reviewed |\n",
        review_score_floor=100,
        max_open=0,
    )

    assert status["passed"] is False
    assert status["eligible_count"] == 3
    assert status["reviewed_count"] == 1
    assert status["open_count"] == 2
    assert [row["session_id"] for row in status["next"]] == ["open-1", "board-open"]


def test_depth_stop_status_passes_when_open_rows_are_within_budget() -> None:
    queue_mod = load_queue_module()
    queue = {
        "changed_review": [
            {"agent": "codex", "session_id": "done-1", "review_score": 150, "changed_file_count": 3},
            {"agent": "claude", "session_id": "open-1", "review_score": 120, "changed_file_count": 2},
        ],
        "board_only": [],
    }

    status = queue_mod.depth_stop_status(
        queue,
        "| 1 | `codex` | `done-1` | reviewed |\n",
        review_score_floor=100,
        max_open=1,
    )

    assert status["passed"] is True
    assert status["open_count"] == 1


def test_private_corpus_relpath_keeps_docs_portable() -> None:
    queue_mod = load_queue_module()

    assert (
        queue_mod.private_corpus_relpath(
            Path("/tmp/other-root/.limen-private/session-corpus/full-stack-review/queue.json")
        )
        == ".limen-private/session-corpus/full-stack-review/queue.json"
    )
