"""Failure episode custody survives retries, overlap, and interrupted callbacks."""

import importlib.util
from pathlib import Path
import threading

import pytest

SPEC = importlib.util.spec_from_file_location(
    "mcp_healing", Path(__file__).resolve().parents[2] / "scripts/mcp_healing.py"
)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def bindings():
    return dict.fromkeys(("registration", "configuration", "dependency", "policy", "failure"), "a" * 64)


def run(root, repair, verify, bound=None):
    return M.heal(
        root,
        owner="domus-genoma",
        repair_id="serena-partial-config",
        bindings=bound or bindings(),
        repair=repair,
        verify=verify,
    )


def test_one_repair_and_verification_per_changed_episode(tmp_path):
    calls = []

    def repair():
        calls.append("repair")
        return {"outcome": "verified", "episode": "owner-rollback", "backup": "private-path"}

    def verify():
        calls.append("verify")
        return "unmeasured"

    first = run(tmp_path, repair, verify)
    second = run(tmp_path, repair, verify)
    assert calls == ["repair", "verify"]
    assert first["verification"] == "unmeasured"
    assert second["reused"] is True
    assert second["rollback_episode"] == "owner-rollback"
    assert "private-path" not in next(tmp_path.glob("*.json")).read_text()
    for key in bindings():
        changed = {**bindings(), key: "b" * 64}
        assert run(tmp_path, repair, verify, changed)["reused"] is False
    assert calls == ["repair", "verify"] * 6


def test_concurrent_attempt_does_not_duplicate_side_effect(tmp_path):
    entered, release = threading.Event(), threading.Event()
    results = []

    def repair():
        entered.set()
        assert release.wait(5)
        return {"outcome": "verified"}

    worker = threading.Thread(target=lambda: results.append(run(tmp_path, repair, lambda: "pass")))
    worker.start()
    try:
        assert entered.wait(5)
        result = run(tmp_path, lambda: pytest.fail("duplicate repair"), lambda: pytest.fail("duplicate verify"))
        assert result["outcome"] == "busy"
    finally:
        release.set()
        worker.join(5)
    assert len(results) == 1


@pytest.mark.parametrize("stage", ["repair", "verify"])
def test_process_death_requires_owner_disposition_without_replay(tmp_path, stage):
    def crash():
        raise SystemExit("simulated process death")

    with pytest.raises(SystemExit):
        run(
            tmp_path,
            crash if stage == "repair" else lambda: {"outcome": "verified"},
            crash if stage == "verify" else lambda: "pass",
        )
    result = run(tmp_path, lambda: pytest.fail("repair replay"), lambda: pytest.fail("verify replay"))
    assert result["outcome"] == "owner_record_required"
    assert result["verification"] == "unmeasured"


def test_durable_repair_can_resume_unstarted_verification(tmp_path, monkeypatch):
    original = M._write

    def die_after_commit(path, value):
        original(path, value)
        if value["state"] == "verify_pending":
            raise SystemExit("crash after durable repair receipt")

    monkeypatch.setattr(M, "_write", die_after_commit)
    with pytest.raises(SystemExit):
        run(tmp_path, lambda: {"outcome": "verified", "episode": "rollback-id"}, lambda: pytest.fail("not yet"))
    monkeypatch.setattr(M, "_write", original)
    result = run(tmp_path, lambda: pytest.fail("must not replay repair"), lambda: "pass")
    assert result["state"] == "finished"
    assert result["rollback_episode"] == "rollback-id"


def test_unsafe_custody_and_missing_bindings_fail_before_mutation(tmp_path):
    state = tmp_path / "state"
    state.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="custody"):
        run(state, lambda: pytest.fail("unsafe mutation"), lambda: "pass")
    bad = bindings()
    bad.pop("policy")
    with pytest.raises(ValueError, match="bindings"):
        run(tmp_path, lambda: pytest.fail("unbound mutation"), lambda: "pass", bad)


def test_malformed_owner_response_is_not_replayed(tmp_path):
    with pytest.raises(ValueError, match="owner repair receipt"):
        run(tmp_path, lambda: [], lambda: pytest.fail("unknown repair must not verify"))
    result = run(tmp_path, lambda: pytest.fail("repair replay"), lambda: pytest.fail("verify replay"))
    assert result["outcome"] == "owner_record_required"
