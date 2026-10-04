"""Retired paths retain their original custody and dependency denominator."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from limen.portable_custody import PortableCustodyError
from limen.scope_retirement import validate_retirement
from portable_custody_fixtures import make_graph, make_retirement

SID = "retired-session"
SCOPES = {"first": "a" * 64, "second": "b" * 64}
NOW = datetime(2026, 10, 3, 2, tzinfo=UTC)


@pytest.fixture
def retirement():
    bundle, files = make_graph(session_id=SID, scope_paths=SCOPES, now=NOW)
    record, custody, dependency, execution, put = make_retirement(
        bundle, files, session_id=SID, scope_paths=SCOPES, retired_root_ids={"first"}
    )
    return record, custody, dependency, execution, files, put


def validate(retirement, **changes):
    record, custody, _, _, files, _ = retirement
    return validate_retirement(
        json.dumps(record).encode(),
        custody,
        session_id=changes.get("session_id", SID),
        original_scope_paths=changes.get("scope_paths", SCOPES),
        absent_root_ids=changes.get("absent_root_ids", {"first"}),
        read_evidence=lambda packet: files[packet["evidence"]],
        now=NOW,
    )


def test_full_retirement_graph_is_read_only_and_idempotent(retirement):
    before = dict(retirement[4])
    result = validate(retirement)
    assert result["original_root_ids"] == ["first", "second"]
    assert result["retired_root_ids"] == ["first"]
    assert result["recorded_retirement_verified"] and not result["retirement_authorized"]
    assert validate(retirement) == result
    assert retirement[4] == before


@pytest.mark.parametrize(
    "changes",
    [
        {"session_id": "foreign"},
        {"scope_paths": {"first": "a" * 64}},
        {"scope_paths": {"first": "c" * 64, "second": "b" * 64}},
        {"absent_root_ids": set()},
        {"absent_root_ids": {"first", "second"}},
    ],
)
def test_retirement_binds_exact_session_scope_and_absence(retirement, changes):
    with pytest.raises(PortableCustodyError):
        validate(retirement, **changes)


@pytest.mark.parametrize(
    "field,value", [("custody_sha256", "c" * 64), ("executions", []), ("retired_root_ids", ["first", "first"])]
)
def test_retirement_summary_cannot_replace_execution(retirement, field, value):
    retirement[0][field] = value
    with pytest.raises(PortableCustodyError):
        validate(retirement)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope_root_ids", ["first"]),
        ("retired_root_ids", ["second"]),
        ("observation_complete", False),
        ("git_store_consumers", None),
        ("git_store_consumers", [{"store_root_id": "first", "consumer_root_id": "second"}]),
        ("git_store_consumers", [{"store_root_id": "first", "consumer_root_id": "outside"}]),
        ("external_consumers", None),
        ("external_consumers", [{"path_sha256": "d" * 64}]),
        ("observed_at", "2026-10-03T00:00:00+00:00"),
        ("observed_at", "2026-10-03T01:45:00+00:00"),
    ],
)
def test_dependency_readings_cannot_omit_consumers_or_scope(retirement, field, value):
    record, _, dependency, execution, _, put = retirement
    dependency[field] = value
    execution["dependencies"] = put(dependency)
    record["executions"] = [put(execution)]
    with pytest.raises(PortableCustodyError):
        validate(retirement)


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "foreign"),
        ("schema", "group02.retirement-execution.v1"),
        ("executed_at", "2026-10-03T00:30:00+00:00"),
        ("executed_at", "2026-10-03T03:00:00+00:00"),
        ("executed_at", "2026-10-03T01:30:00"),
        ("retired_root_ids", []),
        ("exit_code", 1),
        ("exit_code", False),
        ("absence_measured", False),
    ],
)
def test_execution_requires_bound_completed_post_custody_observation(retirement, field, value):
    record, _, _, execution, _, put = retirement
    execution[field] = value
    record["executions"] = [put(execution)]
    with pytest.raises(PortableCustodyError):
        validate(retirement)


def test_changed_execution_bytes_fail_even_when_summary_is_unchanged(retirement):
    record, _, _, _, files, _ = retirement
    files[record["executions"][0]["evidence"]] = b"{}"
    with pytest.raises(PortableCustodyError, match="digest"):
        validate(retirement)


def test_execution_denominator_cannot_overlap(retirement):
    retirement[0]["executions"] *= 2
    with pytest.raises(PortableCustodyError, match="overlap"):
        validate(retirement)


def test_retirement_cannot_replace_full_original_custody(retirement):
    record, custody, dependency, execution, files, put = retirement
    bundle = json.loads(custody)
    bundle["custody_receipt"]["restoration_proofs"][0]["full_restore"] = False
    custody = json.dumps(bundle).encode()
    digest = hashlib.sha256(custody).hexdigest()
    record["custody_sha256"] = dependency["custody_sha256"] = execution["custody_sha256"] = digest
    execution["dependencies"] = put(dependency)
    record["executions"] = [put(execution)]
    with pytest.raises(PortableCustodyError):
        validate_retirement(
            json.dumps(record).encode(),
            custody,
            session_id=SID,
            original_scope_paths=SCOPES,
            absent_root_ids={"first"},
            read_evidence=lambda packet: files[packet["evidence"]],
            now=NOW,
        )


@pytest.mark.parametrize("case", ["closed", "outside_link", "cross_root", "unknown_group", "missing_group"])
def test_retirement_hardlink_cut_set_requires_original_full_membership(case):
    bundle, files = make_graph(session_id=SID, scope_paths=SCOPES, now=NOW)
    packet = bundle["supporting_evidence"][bundle["custody_receipt"]["native_metadata_digest"]]
    entries = json.loads(files[packet["evidence"]])["entries"]
    file = deepcopy(entries["first"]["."])
    file["metadata"].update(
        type="file", size=0, content=hashlib.sha256(b"").hexdigest(), nlink=2, hardlink_group="first/a"
    )
    entries["first"]["a"] = file
    if case != "outside_link":
        entries["second" if case == "cross_root" else "first"]["b"] = deepcopy(file)
    if case == "unknown_group":
        for entry in entries["first"].values():
            if entry["metadata"]["type"] == "file":
                entry["metadata"]["hardlink_group"] = "outside/missing"
    if case == "missing_group":
        for entry in entries["first"].values():
            if entry["metadata"]["type"] == "file":
                entry["metadata"]["hardlink_group"] = None
    bundle, files = make_graph(session_id=SID, scope_paths=SCOPES, now=NOW, native_entries=entries)
    record, custody, dependency, execution, put = make_retirement(
        bundle, files, session_id=SID, scope_paths=SCOPES, retired_root_ids={"first"}
    )
    graph = record, custody, dependency, execution, files, put
    if case == "closed":
        assert validate(graph)["recorded_retirement_verified"]
    else:
        with pytest.raises(PortableCustodyError, match="hardlink"):
            validate(graph)
