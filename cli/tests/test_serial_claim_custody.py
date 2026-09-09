"""An uncertain canonical claim ACK retains its original replay identity."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import stat

import pytest

import limen.dispatch as dispatch
import limen.tabularius as tabularius
from limen.conduct.client import BrokerUnavailable, client_from_env
from limen.execution_contract import execution_contract_hash
from limen.io import save_limen_file
from limen.models import LimenFile


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def _open_board(path: Path) -> LimenFile:
    board = LimenFile.model_validate(
        {
            "version": "1.0",
            "tasks": [
                {
                    "id": "ACK-CUSTODY",
                    "title": "Preserve canonical claim custody",
                    "repo": "someorg/dispatch-lab",
                    "target_agent": "codex",
                    "created": "2026-09-08",
                    "status": "open",
                    "budget_cost": 1,
                    "source_origin": "human_prompt",
                    "horizon": "present",
                    "value_case": "Recover the original claim after its acknowledgement is lost.",
                    "predicate": "pytest -q -k claim_custody",
                    "receipt_target": "github:someorg/dispatch-lab:pull-request:ACK-CUSTODY",
                }
            ],
        }
    )
    save_limen_file(path, board)
    return board


def _reserve(path: Path, board: LimenFile, now=NOW):
    task = board.tasks[0]
    return dispatch._reserve_serial_dispatch(
        path,
        board,
        task.id,
        "codex",
        execution_contract_hash(task),
        dispatch._lifecycle_ownership_token(task),
        now,
        explicit_task=True,
    )


def test_claim_custody_replays_committed_claim_after_lost_ack(tmp_path, monkeypatch):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    client = client_from_env()
    real_submit = client.submit_projection
    submissions = []

    def commit_then_lose_ack(*args, **kwargs):
        result = real_submit(*args, **kwargs)
        submissions.append(result)
        raise BrokerUnavailable("private transport detail must remain redacted")

    monkeypatch.setattr(client, "submit_projection", commit_then_lose_ack)
    monkeypatch.setattr(tabularius, "client_from_env", lambda: client)
    with pytest.raises(dispatch._SerialClaimUnavailable, match="acknowledgement unavailable") as error:
        _reserve(path, board)
    assert "private transport" not in str(error.value)
    inbox = tabularius.tickets_root(path) / "serial-claims" / "inbox"
    pending = next(inbox.glob("*.json"))
    original = pending.read_bytes()
    ticket = tabularius.Ticket.model_validate_json(original)
    canonical_before = client.local_board_projection()
    assert canonical_before["tasks"][0]["status"] == "dispatched"
    assert len(submissions) == 1

    # The local projection remains open when the keeper commits before the ACK
    # arrives. A later attempt must replay that work_id, not reserve a new one.
    reserved = _reserve(path, board, NOW + timedelta(minutes=1))
    assert len(submissions) == 1
    assert reserved[3] == ticket.log["session_id"]
    assert client.local_board_projection() == canonical_before
    assert not pending.exists()
    archived = tabularius.tickets_root(path) / "serial-claims" / "archive" / pending.name
    assert archived.read_bytes() == original

    # Even another stale open projection cannot use this acknowledged handoff
    # as fresh provider authority. No provider has been invoked by this test.
    save_limen_file(path, board)
    with pytest.raises(RuntimeError, match="terminal ticket custody"):
        _reserve(path, board, NOW + timedelta(minutes=2))


@pytest.mark.parametrize("failure", ["transport", "missing", "malformed", "executor"])
def test_claim_custody_blocks_unacknowledged_or_wrong_executor(tmp_path, monkeypatch, failure):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    tickets = []

    def unavailable(_path, desired, **kwargs):
        tickets.append(kwargs["prepared_claims"][board.tasks[0].id])
        if failure == "transport":
            raise BrokerUnavailable("secret-provider-token")
        projected = desired.tasks[0].model_dump(mode="json", exclude_none=True)
        if failure == "malformed":
            projected = {"id": "ACK-CUSTODY", "status": "not-a-status"}
        elif failure == "executor":
            projected["dispatch_log"][-1]["agent"] = "claude"
        return tabularius.DrainResult(projected_tasks={} if failure == "missing" else {"ACK-CUSTODY": projected})

    monkeypatch.setattr(dispatch, "apply_limen_file_sync", unavailable)
    for now in (NOW, NOW + timedelta(minutes=1)):
        with pytest.raises(dispatch._SerialClaimUnavailable) as error:
            _reserve(path, board, now)
        assert "secret-provider-token" not in str(error.value)
    assert tickets[0] == tickets[1]
    pending = list((tabularius.tickets_root(path) / "serial-claims" / "inbox").glob("*.json"))
    assert len(pending) == 1
    assert "secret-provider-token" not in pending[0].read_text()
    assert not (tabularius.tickets_root(path) / "serial-claims" / "archive").exists()


def test_claim_custody_failure_prevents_broker_submission(tmp_path, monkeypatch):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    monkeypatch.setattr(dispatch, "submit_ticket", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("private disk")))
    monkeypatch.setattr(
        dispatch,
        "apply_limen_file_sync",
        lambda *args, **kwargs: pytest.fail("claim cannot submit before exact request custody"),
    )
    with pytest.raises(dispatch._SerialClaimUnavailable, match="durable custody"):
        _reserve(path, board)


@pytest.mark.parametrize("stage", ["inbox", "archive"])
def test_claim_directory_sync_failure_blocks_submission_or_handoff(tmp_path, monkeypatch, stage):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    real_fsync = os.fsync
    claims = []

    def directory_sync_failure(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode) and (stage == "inbox" or claims):
            raise OSError("private directory sync detail")
        return real_fsync(descriptor)

    def acknowledged(_path, desired, **kwargs):
        claims.append(kwargs["prepared_claims"]["ACK-CUSTODY"])
        return tabularius.DrainResult(
            projected_tasks={"ACK-CUSTODY": desired.tasks[0].model_dump(mode="json", exclude_none=True)}
        )

    monkeypatch.setattr(os, "fsync", directory_sync_failure)
    monkeypatch.setattr(dispatch, "apply_limen_file_sync", acknowledged)
    with pytest.raises(dispatch._SerialClaimUnavailable, match="custody") as error:
        _reserve(path, board)
    assert "private directory" not in str(error.value)
    assert len(claims) == (stage == "archive")
    pending = list((tabularius.tickets_root(path) / "serial-claims" / "inbox").glob("*.json"))
    assert len(pending) == 1
    if stage == "archive":
        archived = tabularius.tickets_root(path) / "serial-claims" / "archive" / pending[0].name
        assert archived.read_bytes() == pending[0].read_bytes()
        with pytest.raises(RuntimeError, match="terminal ticket custody"):
            _reserve(path, board)
