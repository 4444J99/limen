import hashlib
import json

import pytest
from limen import runtime_maintenance_observation as observation
from limen.bounded_subprocess import BoundedCompletedProcess


@pytest.fixture
def source(tmp_path):
    hashes = {}
    for name in observation.PATHS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"reviewed controller")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return tmp_path, {
        "schema": "limen.runtime_maintenance_observation.v1",
        "source_revision": "a" * 40,
        "sha256": hashes,
    }


def test_observation_records_bookkeeping_without_requesting_worker(source):
    home, manifest = source
    calls = []
    payload = {
        "schema": "domus.runtime_maintenance.v1",
        "recorded": True,
        "status": "healthy",
        "observed_at": 123,
        "worker": {"recovery_status": "not_requested"},
        "quota": {
            "schema": "domus.agent_runtime.v2",
            "census_complete": True,
            "total_size_bytes": 12,
            "pool": {"allowed": True},
        },
    }

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return BoundedCompletedProcess(0, json.dumps(payload).encode(), b"")

    code, report = observation.observe(home, manifest, runner=runner)
    assert code == 0 and report["bookkeeping_only"] and not report["worker_requested"]
    assert calls[0][0] == [str(home / observation.PATHS[0]), "--record", "--json"]
    assert calls[0][1]["timeout_seconds"] == 60
    payload["status"] = "maintenance_required"
    code, report = observation.observe(
        home, manifest, runner=lambda *a, **k: BoundedCompletedProcess(1, json.dumps(payload).encode(), b"")
    )
    assert code == 1 and report["status"] == "maintenance_required"


@pytest.mark.parametrize(
    "reason, expected", [("runtime maintenance is already running", 1), ("unexpected blockage", 78)]
)
def test_only_known_controller_contention_is_deferred(source, reason, expected):
    home, manifest = source
    payload = {"schema": "domus.runtime_maintenance.v1", "status": "blocked", "reason": reason}
    code, report = observation.observe(
        home, manifest, runner=lambda *a, **k: BoundedCompletedProcess(1, json.dumps(payload).encode(), b"")
    )
    assert code == expected
    assert report["status"] == ("deferred" if expected == 1 else "failed")


@pytest.mark.parametrize("damage", ["drift", "symlink", "incomplete", "worker", "during_run"])
def test_source_or_protocol_failure_never_runs_worker_and_is_system_failure(source, damage):
    home, manifest = source
    target = home / observation.PATHS[1]
    if damage == "drift":
        target.write_text("unreviewed")
    if damage == "symlink":
        target.unlink()
        target.symlink_to(home / observation.PATHS[2])
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if damage == "during_run":
            target.write_text("concurrent update")
        payload = {
            "schema": "domus.runtime_maintenance.v1",
            "recorded": True,
            "quota": {"schema": "domus.agent_runtime.v2", "census_complete": damage != "incomplete"},
            "worker": {"recovery_status": "requested" if damage == "worker" else "not_requested"},
        }
        return BoundedCompletedProcess(0, json.dumps(payload).encode(), b"")

    code, report = observation.observe(home, manifest, runner=runner)
    assert code == 78 and report["status"] == "failed"
    if damage in {"drift", "symlink"}:
        assert not calls
