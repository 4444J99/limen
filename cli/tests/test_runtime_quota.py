import json
from limen.runtime_quota import maintenance_requests
from limen.tabularius import tickets_root


def test_warning_threshold_and_duplicate_intake(tmp_path):
    board = tmp_path / "tasks.yaml"
    payload = {"runtime_root": str(tmp_path), "agents": {"codex": {"size_bytes": 79, "quota_bytes": 100}}}
    assert maintenance_requests(payload, board) == []
    payload["agents"]["codex"]["size_bytes"] = 80
    first = maintenance_requests(payload, board)
    assert len(first) == 1
    assert maintenance_requests(payload, board) == first
    files = list((tickets_root(board) / "inbox").glob("*.json"))
    assert len(files) == 1
    ticket = json.loads(files[0].read_text())
    assert ticket["precondition"] == {"absent": True}
    assert "70" in ticket["patch"]["predicate"]
    assert "Preserve SQLite" in ticket["patch"]["description"]


def test_total_warning_and_invalid_observation(tmp_path):
    import pytest

    observation = {"runtime_root": str(tmp_path), "agents": {}, "total_size_bytes": 80, "total_quota_bytes": 100}
    assert len(maintenance_requests(observation, tmp_path / "tasks.yaml")) == 1
    with pytest.raises(ValueError, match="observation_invalid"):
        maintenance_requests({}, tmp_path / "tasks.yaml")
