"""Mixed-provider caller selections remain canonical reservation identities."""

from datetime import datetime, timezone

import pytest

from limen.io import load_limen_file, save_limen_file
from limen.models import DispatchLogEntry, canonical_dispatch_agent
from limen.tabularius import apply_limen_file_sync
from test_tabularius import _board, _task


def _reservation(tmp_path):
    path = tmp_path / "tasks.yaml"
    board = _board([_task("A", status="open"), _task("B", status="open", target_agent="jules")])
    save_limen_file(path, board)
    for task in board.tasks:
        task.status = "dispatched"
        task.dispatch_log.append(
            DispatchLogEntry(
                timestamp=datetime.now(timezone.utc),
                agent="untrusted-log-label",
                session_id="selected-batch",
                status="dispatched",
            )
        )
    return path, board


def test_mixed_provider_claims_use_explicit_selection_and_keep_dispatcher_correlation(tmp_path):
    path, desired = _reservation(tmp_path)
    result = apply_limen_file_sync(
        path,
        desired,
        agent="dispatch-parallel",
        claim_agents={"A": "codex", "B": "jules"},
        session_id="reserve",
    )
    assert result.applied == 2
    canonical = load_limen_file(path)
    assert canonical.portal.budget.track.per_agent == {"codex": 1, "jules": 1}
    for task in canonical.tasks:
        entry = task.dispatch_log[-1].model_dump()
        assert entry["agent"] == task.target_agent
        assert entry["logical_agent"] == "dispatch-parallel"


@pytest.mark.parametrize("selected", [{}, {"A": "any"}, {"A": ""}, {"A": "codex"}])
def test_missing_concrete_batch_selection_fails_before_any_claim(tmp_path, selected):
    path, desired = _reservation(tmp_path)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="one concrete selected executor"):
        apply_limen_file_sync(path, desired, agent="dispatch-async", claim_agents=selected)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({"agent": "codex", "logical_agent": "dispatch-async"}, "codex"),
        ({"agent": "dispatch-async", "logical_agent": "codex"}, "dispatch-async"),
        ({"logical_agent": "codex"}, ""),
    ],
)
def test_lifecycle_identity_never_promotes_logical_executor(entry, expected):
    assert canonical_dispatch_agent(entry) == expected
