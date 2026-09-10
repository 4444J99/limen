"""Claim handoff custody is separate from generic projection acknowledgement."""

from datetime import timedelta
import os

import pytest

import limen.dispatch as dispatch
import limen.tabularius as tabularius
from limen.conduct.client import BrokerUnavailable, client_from_env
from limen.execution_contract import execution_contract_hash
from test_serial_claim_custody import NOW, _open_board, _reserve


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "hermetic-root"))
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "0")
    for name in ("LIMEN_VALUE_REPOS", "LIMEN_VALUE_REPOS_FILE", "LIMEN_VALUE_GATE_STRICT"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("legacy", [False, True])
def test_generic_drain_cannot_consume_serial_claim_handoff(tmp_path, monkeypatch, legacy):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    client = client_from_env()
    submit = client.submit_projection
    committed = []

    def lost_ack(*args, **kwargs):
        committed.append(submit(*args, **kwargs))
        raise BrokerUnavailable("lost acknowledgement")

    monkeypatch.setattr(client, "submit_projection", lost_ack)
    monkeypatch.setattr(tabularius, "client_from_env", lambda: client)
    with pytest.raises(dispatch._SerialClaimUnavailable):
        _reserve(path, board)
    before = client.local_board_projection()
    root = tabularius.tickets_root(path)
    [pending] = list((root / "serial-claims" / "inbox").glob("*.json"))
    original = pending.read_bytes()
    if legacy:
        old = root / "inbox" / pending.name
        old.parent.mkdir(parents=True, exist_ok=True)
        os.link(pending, old)
        pending.unlink()

        def unavailable():
            raise BrokerUnavailable("temporary replay outage")

        monkeypatch.setattr(tabularius, "client_from_env", unavailable)
        with pytest.raises(dispatch._SerialClaimUnavailable):
            _reserve(path, board)
        assert not old.exists()
        assert pending.read_bytes() == original
        monkeypatch.setattr(tabularius, "client_from_env", lambda: client)
    drained = tabularius.drain_once(path)
    assert drained.applied == 0, "a projection ACK must not consume provider handoff custody"
    reserved = _reserve(path, board, NOW + timedelta(minutes=1))
    assert len(committed) == 1
    assert reserved[1].status == "dispatched"
    assert client.local_board_projection() == before
    assert (root / "serial-claims" / "archive" / pending.name).read_bytes() == original


def test_legacy_claim_archive_is_preserved_under_reconciliation_hold(tmp_path, monkeypatch):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)

    def unavailable(*args, **kwargs):
        raise BrokerUnavailable("lost acknowledgement")

    monkeypatch.setattr(dispatch, "apply_limen_file_sync", unavailable)
    with pytest.raises(dispatch._SerialClaimUnavailable):
        _reserve(path, board)
    root = tabularius.tickets_root(path)
    [pending] = list((root / "serial-claims" / "inbox").glob("*.json"))
    old = root / "archive" / pending.name
    old.parent.mkdir(parents=True)
    os.link(pending, old)
    original = old.read_bytes()
    with pytest.raises(RuntimeError, match="terminal ticket custody"):
        _reserve(path, board)
    assert old.read_bytes() == pending.read_bytes() == original


def test_deferred_result_directory_sync_failure_retains_process_receipts(tmp_path, monkeypatch):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    reserved_board, task, owner, _nonce = _reserve(path, board)
    dispatch._MODEL_SELECTION_RECEIPTS[task.id] = {"selected_model": "synthetic-model"}
    sync = dispatch._sync_serial_ticket_custody

    def unavailable(*args, **kwargs):
        raise BrokerUnavailable("lost result acknowledgement")

    def failed_sync(*args):
        raise OSError("result directory could not sync")

    monkeypatch.setattr(dispatch, "apply_limen_file_sync", unavailable)
    monkeypatch.setattr(dispatch, "_sync_serial_ticket_custody", failed_sync)
    try:
        with pytest.raises(OSError, match="result directory"):
            dispatch._commit_serial_reserved_result(
                path, reserved_board, task, "codex", dispatch._NOOP, NOW, execution_contract_hash(task), owner
            )
        assert dispatch._MODEL_SELECTION_RECEIPTS[task.id] == {"selected_model": "synthetic-model"}
        [pending] = list((tabularius.tickets_root(path) / "inbox").glob("*.json"))
        assert tabularius.Ticket.model_validate_json(pending.read_bytes()).task_id == task.id
        original = pending.read_bytes()
        monkeypatch.setattr(dispatch, "_sync_serial_ticket_custody", sync)
        assert (
            dispatch._commit_serial_reserved_result(
                path, reserved_board, task, "codex", dispatch._NOOP, NOW, execution_contract_hash(task), owner
            )
            is None
        )
        assert task.id not in dispatch._MODEL_SELECTION_RECEIPTS
        assert pending.read_bytes() == original
    finally:
        dispatch._clear_result_receipts(task.id)
