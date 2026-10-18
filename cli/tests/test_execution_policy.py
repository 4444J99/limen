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

def test_policy_binding_fits_provider_and_preserves_complete_policy():
    import base64
    import gzip
    from limen.execution_policy import encode_policy_binding

    policy = {"mode": "recovery", "dispatch_enabled": False, "approved_priorities": [
        {"outcome_id": str(i), "owner": "preserved/" * 100, "work_keys": [str(i)]}
        for i in range(8)
    ]}
    payload = encode_policy_binding(policy)
    assert len(payload.encode("utf-8")) <= 5000
    envelope = json.loads(payload)
    assert envelope["encoding"] == "gzip+base64"
    raw = gzip.decompress(base64.b64decode(envelope["data"], validate=True))
    assert json.loads(raw) == policy
    assert canonical_hash(json.loads(raw)) == canonical_hash(policy)
    assert encode_policy_binding(policy) == payload


def test_small_policy_stays_legacy_json_and_large_incompressible_policy_is_rejected():
    import random
    from limen.execution_policy import encode_policy_binding

    policy = {"mode": "recovery", "approved_priorities": []}
    assert json.loads(encode_policy_binding(policy)) == policy
    assert "encoding" not in json.loads(encode_policy_binding(policy))
    with pytest.raises(ValueError, match="decoded_too_large"):
        encode_policy_binding({"data": "x" * 65536})
    random_source = random.Random(3022)
    with pytest.raises(ValueError, match="binding_too_large"):
        encode_policy_binding({"data": "".join(random_source.choices(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=12000))})
