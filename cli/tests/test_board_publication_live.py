"""Public/private acceptance rejects stale snapshots and never emits private task material."""

import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "board_publication_live", ROOT / "scripts/check-board-publication-live.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SHA = "a" * 40
HEAD = "b" * 40


class Keeper:
    def __init__(self):
        self.board = {
            "schema_version": "limen.private_board.v1",
            "tasks": [{"id": "PRIVATE-ID", "title": "PRIVATE-TITLE", "status": "open", "priority": "high"}],
        }
        self.reads = 0
        self.move = False

    def capabilities(self):
        return {"runtime_identity": {"git_sha": SHA, "deployment_id": "deployment"}}

    def private_board(self):
        self.reads += 1
        board = deepcopy(self.board)
        if self.move and self.reads == 2:
            board["tasks"][0]["title"] = "changed with identical counts"
        return board


def sources(keeper, *, mutate=None, move_head=False):
    public = {
        "schema_version": "limen.public_board_projection.v1",
        "tasks": [],
        "portal": {
            "name": "Universal Task Intake",
            "description": "Aggregate operational health; authenticated board details are private.",
            "public_projection": {
                "schema_version": "limen.public_board_projection.v1",
                "generated_at": "2026-01-01T00:00:00Z",
                **m.private_counts(keeper.board),
            },
        },
    }
    if mutate:
        mutate(public)
    reads = 0

    def read(path):
        nonlocal reads
        if path == "":
            return {"full_name": m.REPOSITORY, "id": 1, "default_branch": "main"}
        if path.startswith("/git/ref"):
            reads += 1
            return {"object": {"sha": "c" * 40 if move_head and reads == 2 else HEAD}}
        if path.startswith("/compare/"):
            return {"status": "ahead"}
        assert path == f"/contents/tasks.yaml?ref={HEAD}"
        return {
            "type": "file",
            "encoding": "base64",
            "sha": "d" * 40,
            "content": base64.b64encode(json.dumps(public).encode()).decode(),
        }

    return read


def test_live_parity_is_counts_only():
    keeper = Keeper()
    result = m.observe(keeper, SHA, read=sources(keeper))
    assert result["status"] == "passed"
    assert result["counts"]["total"] == 1
    assert "PRIVATE" not in json.dumps(result)
    assert keeper.reads == 2


def test_integer_zero_rate_from_javascript_is_valid():
    keeper = Keeper()
    result = m.observe(
        keeper, SHA, read=sources(keeper, mutate=lambda p: p["portal"]["public_projection"].update(completion_rate=0))
    )
    assert result["status"] == "passed"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["portal"]["public_projection"].update(total=2),
        lambda p: p["portal"]["public_projection"].update(total=True),
        lambda p: p.update(context="PRIVATE-CONTEXT"),
        lambda p: p.update(tasks=[{"id": "PRIVATE-ID"}]),
    ],
)
def test_public_mismatch_fails_without_leaking(mutation):
    keeper = Keeper()
    result = m.observe(keeper, SHA, read=sources(keeper, mutate=mutation))
    assert result["status"] == "failed"
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("move_private", [True, False])
def test_movement_is_unmeasured(move_private):
    keeper = Keeper()
    keeper.move = move_private
    with pytest.raises(ValueError, match="source_changed"):
        m.observe(keeper, SHA, read=sources(keeper, move_head=not move_private))


def test_duplicate_private_identity_rejected():
    keeper = Keeper()
    keeper.board["tasks"] *= 2
    with pytest.raises(ValueError, match="private_identity"):
        m.private_counts(keeper.board)


def test_missing_runtime_rejected():
    keeper = Keeper()
    with pytest.raises(ValueError, match="runtime_identity"):
        m.observe(keeper, "c" * 40, read=sources(keeper))


def test_provider_error_is_redacted(monkeypatch, capsys):
    from limen.conduct import client
    from limen import dispatch

    monkeypatch.setattr(dispatch, "_load_limen_env", lambda: None)

    def unavailable():
        raise RuntimeError("PRIVATE-TOKEN")

    monkeypatch.setattr(client, "client_from_env", unavailable)
    monkeypatch.setattr("sys.argv", ["check", "--expected-runtime-sha", SHA])
    assert m.main() == 77
    assert "PRIVATE" not in capsys.readouterr().out
