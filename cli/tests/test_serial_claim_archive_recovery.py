"""Only a locally interrupted, acknowledged handoff proves no provider launch."""

from datetime import timedelta
from pathlib import Path
import os

import pytest

import limen.dispatch as dispatch
import limen.tabularius as tabularius
from limen.conduct.client import BrokerUnavailable, client_from_env
from limen.io import save_limen_file
from limen.models import LimenFile
from test_serial_claim_custody import NOW, _open_board, _reserve


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "hermetic-root"))
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "0")
    for name in ("LIMEN_VALUE_REPOS", "LIMEN_VALUE_REPOS_FILE", "LIMEN_VALUE_GATE_STRICT"):
        monkeypatch.delenv(name, raising=False)


def _interrupt_handoff(monkeypatch, path, boundary):
    root = tabularius.tickets_root(path) / "serial-claims"
    fsync = os.fsync
    unlink = Path.unlink
    interrupted = []

    def fail():
        [archive] = list((root / "archive").glob("*.json"))
        interrupted.append((archive, archive.read_bytes()))
        raise OSError("private preparation path must remain redacted")

    def fsync_at_boundary(descriptor):
        directory = root / ("archive" if boundary == "archive-sync" else "inbox")
        if boundary != "inbox-unlink" and not interrupted and directory.exists():
            target = directory.stat()
            actual = os.fstat(descriptor)
            after_unlink = not list((root / "inbox").glob("*.json"))
            if (actual.st_dev, actual.st_ino) == (target.st_dev, target.st_ino) and (
                boundary == "archive-sync" or after_unlink
            ):
                fail()
        return fsync(descriptor)

    def unlink_at_boundary(self, *args, **kwargs):
        if boundary == "inbox-unlink" and not interrupted and self.parent == root / "inbox":
            fail()
        return unlink(self, *args, **kwargs)

    monkeypatch.setattr(os, "fsync", fsync_at_boundary)
    monkeypatch.setattr(Path, "unlink", unlink_at_boundary)
    return interrupted


@pytest.mark.parametrize("boundary", ["archive-sync", "inbox-unlink", "inbox-sync"])
@pytest.mark.parametrize("release", ["acknowledged", "unavailable", "lost-ack"])
def test_interrupted_handoff_refunds_or_defers_exact_prelaunch_result(tmp_path, monkeypatch, boundary, release):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    client = client_from_env()
    monkeypatch.setattr(tabularius, "client_from_env", lambda: client)
    interrupted = _interrupt_handoff(monkeypatch, path, boundary)
    apply = dispatch.apply_limen_file_sync
    releases = []

    def release_acknowledgement(*args, **kwargs):
        if kwargs.get("session_id") == "serial-results":
            releases.append(kwargs["before"].tasks[0].model_copy(deep=True))
            if release == "unavailable":
                raise BrokerUnavailable("private result transport")
            result = apply(*args, **kwargs)
            if release == "lost-ack":
                raise BrokerUnavailable("private result acknowledgement")
            return result
        return apply(*args, **kwargs)

    monkeypatch.setattr(dispatch, "apply_limen_file_sync", release_acknowledgement)
    with pytest.raises(dispatch._SerialClaimUnavailable, match="handoff custody") as error:
        _reserve(path, board)
    assert "private" not in str(error.value)
    assert len(interrupted) == 1
    archive, original = interrupted[0]
    assert archive.read_bytes() == original
    claim = tabularius.Ticket.model_validate_json(original)
    assert len(releases) == 1
    assert dispatch.dispatch_session_id(releases[0].dispatch_log[-1]) == claim.log["session_id"]
    current = LimenFile.model_validate(client.local_board_projection())
    retained = release == "unavailable"
    assert current.tasks[0].status == ("dispatched" if retained else "open")
    assert current.portal.budget.track.spent == int(retained)
    assert current.portal.budget.track.per_agent["codex"] == int(retained)

    root = tabularius.tickets_root(path)
    pending = list((root / "inbox").glob("serial-result-*.json"))
    if release == "acknowledged":
        assert pending == []
    else:
        [result_path] = pending
        original_result = result_path.read_bytes()
        ticket = tabularius.Ticket.model_validate_json(original_result)
        assert ticket.canonical_base == releases[0].model_dump(mode="json", exclude_none=True)
        assert ticket.log["execution_started"] is False
        assert ticket.log["execution_reservation_id"] == claim.log["session_id"]
        assert "private" not in original_result.decode()
        # The normal keeper drain consumes this exact existing result Ticket.
        # It never consumes or rewrites serial claim custody.
        drained = tabularius.drain_once(path)
        assert drained.applied == 1
        assert (root / "archive" / result_path.name).read_bytes() == original_result
        assert tabularius.drain_once(path).applied == 0

    settled = LimenFile.model_validate(client.local_board_projection())
    assert settled.tasks[0].status == "open"
    assert settled.portal.budget.track.spent == 0
    assert settled.portal.budget.track.per_agent["codex"] == 0
    assert settled.tasks[0].dispatch_log[-1].execution_started is False
    assert archive.read_bytes() == original

    # A stale pre-claim cache remains fenced; only the keeper's released row
    # can start a new reservation with a fresh identity.
    save_limen_file(path, board)
    with pytest.raises(RuntimeError, match="terminal ticket custody"):
        _reserve(path, board, NOW + timedelta(minutes=1))
    save_limen_file(path, settled)
    again = _reserve(path, settled, NOW + timedelta(minutes=2))
    assert again[1].status == "dispatched"
    assert again[3] != claim.log["session_id"]
    assert archive.read_bytes() == original


@pytest.mark.parametrize("pending_link", [False, True])
def test_ambiguous_archived_handoff_never_refunds_or_relaunches(tmp_path, monkeypatch, pending_link):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    client = client_from_env()
    monkeypatch.setattr(tabularius, "client_from_env", lambda: client)
    _reserve(path, board)
    canonical = client.local_board_projection()
    root = tabularius.tickets_root(path)
    [archive] = list((root / "serial-claims" / "archive").glob("*.json"))
    original = archive.read_bytes()
    if pending_link:
        os.link(archive, root / "serial-claims" / "inbox" / archive.name)
    monkeypatch.setattr(
        dispatch,
        "_commit_serial_reserved_result",
        lambda *args, **kwargs: pytest.fail("archive existence cannot prove no launch"),
    )
    save_limen_file(path, board)
    with pytest.raises(RuntimeError, match="terminal ticket custody"):
        _reserve(path, board, NOW + timedelta(minutes=1))
    assert tabularius.drain_once(path).applied == 0
    assert client.local_board_projection() == canonical
    assert canonical["portal"]["budget"]["track"]["spent"] == 1
    assert archive.read_bytes() == original


def test_archive_link_collision_cannot_authorize_prelaunch_refund(tmp_path, monkeypatch):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    client = client_from_env()
    monkeypatch.setattr(tabularius, "client_from_env", lambda: client)
    link = os.link

    def concurrent_archive(source, destination):
        link(source, destination)
        if Path(destination).parent == tabularius.tickets_root(path) / "serial-claims" / "archive":
            raise FileExistsError("another handoff already created this archive")

    monkeypatch.setattr(os, "link", concurrent_archive)
    monkeypatch.setattr(
        dispatch,
        "_commit_serial_reserved_result",
        lambda *args, **kwargs: pytest.fail("a link collision cannot prove no launch"),
    )
    with pytest.raises(dispatch._SerialClaimUnavailable, match="reconcile existing claim"):
        _reserve(path, board)
    current = client.local_board_projection()
    assert current["tasks"][0]["status"] == "dispatched"
    assert current["portal"]["budget"]["track"]["spent"] == 1
    root = tabularius.tickets_root(path) / "serial-claims"
    [archive] = list((root / "archive").glob("*.json"))
    assert (root / "inbox" / archive.name).read_bytes() == archive.read_bytes()
    save_limen_file(path, board)
    with pytest.raises(RuntimeError, match="terminal ticket custody"):
        _reserve(path, board, NOW + timedelta(minutes=1))
    assert client.local_board_projection() == current


@pytest.mark.parametrize("custody_failure", ["write", "sync"])
def test_unacknowledged_prelaunch_release_custody_keeps_claim_debited(tmp_path, monkeypatch, custody_failure):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    client = client_from_env()
    monkeypatch.setattr(tabularius, "client_from_env", lambda: client)
    interrupted = _interrupt_handoff(monkeypatch, path, "inbox-unlink")
    apply = dispatch.apply_limen_file_sync
    submit = dispatch.submit_ticket
    sync = dispatch._sync_serial_ticket_custody
    root = tabularius.tickets_root(path)

    def unavailable_result(*args, **kwargs):
        if kwargs.get("session_id") == "serial-results":
            raise BrokerUnavailable("private broker detail")
        return apply(*args, **kwargs)

    def failed_write(*args, **kwargs):
        if custody_failure == "write" and kwargs.get("custody") != "serial-claims":
            raise OSError("private result write path")
        return submit(*args, **kwargs)

    def failed_sync(directory, tasks_path):
        if custody_failure == "sync" and directory == root / "inbox":
            raise OSError("private result sync path")
        return sync(directory, tasks_path)

    monkeypatch.setattr(dispatch, "apply_limen_file_sync", unavailable_result)
    monkeypatch.setattr(dispatch, "submit_ticket", failed_write)
    monkeypatch.setattr(dispatch, "_sync_serial_ticket_custody", failed_sync)
    with pytest.raises(dispatch._SerialClaimUnavailable, match="prelaunch release custody unacknowledged") as error:
        _reserve(path, board)
    assert "private" not in str(error.value)
    assert "reservation released" not in str(error.value)
    assert "release deferred" not in str(error.value)
    [captured] = interrupted
    archive, original = captured
    assert archive.read_bytes() == original
    current = client.local_board_projection()
    assert current["tasks"][0]["status"] == "dispatched"
    assert current["portal"]["budget"]["track"]["spent"] == 1
    if custody_failure == "sync":
        [pending] = list((root / "inbox").glob("*.json"))
        assert tabularius.Ticket.model_validate_json(pending.read_bytes()).log["execution_started"] is False
