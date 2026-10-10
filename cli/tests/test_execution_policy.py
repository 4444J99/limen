import copy
import pytest
from limen.conduct.models import canonical_hash
from limen.execution_policy import native_policy_record, reconcile_policy
import json


def test_addition_preserves_every_existing_field_and_limit():
    source = {
        "mode": "recovery",
        "dispatch_enabled": False,
        "execution_limits": {"attempt_seconds": 1800},
        "approved_priorities": [{"outcome_id": "old", "enabled": True, "work_keys": ["old-exact"]}],
    }
    original = copy.deepcopy(source)
    live = {
        "schema_version": "limen.execution_policy_readback.v1",
        "runtime": {"deployment_id": "v1"},
        "configuration_fingerprint": canonical_hash(source),
    }
    result = reconcile_policy(source, live, outcome="ops6", work_key="ops6-coordinate-20261009", owner="ops#6")
    assert source == original
    assert result["approved_priorities"][:-1] == original["approved_priorities"]
    assert result["execution_limits"] == original["execution_limits"]
    assert result["dispatch_enabled"] is False
    after = {**live, "configuration_fingerprint": canonical_hash(result)}
    assert reconcile_policy(result, after, outcome="ops6", work_key="ops6-coordinate-20261009", owner="ops#6") == result
    with pytest.raises(ValueError, match="generation_mismatch"):
        reconcile_policy({}, live, outcome="ops6", work_key="ops6", owner="ops#6")


def test_conflicting_exact_key_cannot_steal_existing_priority():
    source = {
        "mode": "recovery",
        "dispatch_enabled": False,
        "approved_priorities": [{"outcome_id": "old", "work_keys": ["ops6"]}],
    }
    live = {
        "schema_version": "limen.execution_policy_readback.v1",
        "runtime": {"deployment_id": "v1"},
        "configuration_fingerprint": canonical_hash(source),
    }
    with pytest.raises(ValueError, match="priority_conflict"):
        reconcile_policy(source, live, outcome="new", work_key="ops6", owner="ops#6")


def test_native_recovery_requires_successful_json_record(tmp_path):
    record = tmp_path / "native.jsonl"
    policy = {"mode": "recovery", "approved_priorities": [], "dispatch_enabled": False}
    item = {"type": "CommandExecution", "exit_code": 0, "stdout": json.dumps(policy)}
    record.write_text(json.dumps({"payload": {"item": item}}) + "\n")
    assert native_policy_record(record, 1) == policy
    item["exit_code"] = 1
    record.write_text(json.dumps({"payload": {"item": item}}) + "\n")
    with pytest.raises(ValueError, match="native_record_invalid"):
        native_policy_record(record, 1)
    with pytest.raises(ValueError, match="native_record_invalid"):
        native_policy_record(record, 257)
