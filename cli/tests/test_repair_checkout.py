from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from limen import repair_checkout as repair
from limen.storage_headroom import StorageAdmissionError


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(repair, "storage_identity", lambda path: "pool")
    monkeypatch.setattr(repair.os, "statvfs", lambda path: SimpleNamespace(f_bavail=12 * 1024**3, f_frsize=1))
    info = dict(
        storage_repair=True,
        run_id="run",
        outcome_id="outcome",
        verification_seconds=600,
        attempt_deadline=(datetime.now(UTC) + timedelta(minutes=20)).isoformat(),
    )
    client = SimpleNamespace(execution_info=lambda key: info, reserve_growth=lambda *args: None)

    def run(args, **kwargs):
        if "ls-tree" in args:
            return SimpleNamespace(stdout="100644 blob " + "a" * 40 + " 10\tfile\n")
        destination = args[-2]
        from pathlib import Path

        Path(destination).mkdir()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(repair.subprocess, "run", run)
    return client, info, tmp_path


def test_single_checkout_survives_restart_and_expiry(setup):
    client, info, root = setup
    receipt = repair.create_repair_checkout(client, "key", root, root / "checkout", "a" * 40)
    assert receipt["allocated_bytes"] <= repair.MAX_BYTES
    info["attempt_deadline"] = (datetime.now(UTC) + timedelta(minutes=29)).isoformat()
    with pytest.raises(StorageAdmissionError, match="retention-unresolved"):
        repair.create_repair_checkout(client, "key", root, root / "replacement", "a" * 40)


def test_allocation_violation_is_retained(setup, monkeypatch):
    client, info, root = setup
    monkeypatch.setattr(repair, "allocated_bytes", lambda path: repair.MAX_BYTES + 1)
    with pytest.raises(StorageAdmissionError, match="allocation-exceeded-retained"):
        repair.create_repair_checkout(client, "key", root, root / "checkout", "a" * 40)
    assert (root / "checkout").exists()
    assert (root / "state/limen/repair-checkout.json").exists()


@pytest.mark.parametrize("field,value", [("storage_repair", False), ("verification_seconds", 601)])
def test_no_unapproved_or_expanded_attempt(setup, field, value):
    client, info, root = setup
    info[field] = value
    with pytest.raises(StorageAdmissionError, match="admission-required"):
        repair.create_repair_checkout(client, "key", root, root / "checkout", "a" * 40)


def test_budget_and_floor(setup, monkeypatch):
    client, info, root = setup
    with pytest.raises(StorageAdmissionError, match="allocation-invalid"):
        repair.create_repair_checkout(client, "key", root, root / "checkout", "a" * 40, repair.MAX_BYTES + 1)
    monkeypatch.setattr(
        repair.os, "statvfs", lambda path: SimpleNamespace(f_bavail=repair.FLOOR_BYTES + repair.MAX_BYTES, f_frsize=1)
    )
    with pytest.raises(StorageAdmissionError, match="storage-floor"):
        repair.create_repair_checkout(client, "key", root, root / "checkout", "a" * 40)


def test_concurrent_writer_fails_closed(setup):
    client, info, root = setup
    state = root / "state/limen"
    state.mkdir(mode=0o700, parents=True)
    import os
    import fcntl

    fd = os.open(state / "repair-checkout.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(StorageAdmissionError, match="writer-occupied"):
            repair.create_repair_checkout(client, "key", root, root / "checkout", "a" * 40)
    finally:
        os.close(fd)
