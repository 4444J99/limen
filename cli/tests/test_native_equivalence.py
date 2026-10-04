import copy
import json

import pytest
from limen.native_equivalence import compare_native_manifests
from limen.portable_custody import PortableCustodyError


@pytest.fixture
def manifests():
    metadata = {
        "type": "directory",
        "mode": 0o700,
        "uid": 501,
        "gid": 20,
        "mtime_ns": 1,
        "birthtime_ns": 2,
        "atime_ns": 3,
        "ctime_ns": 4,
        "flags": 0,
        "nlink": 1,
        "xattrs": {},
        "acl": "absent",
        "hardlink_group": None,
        "size": None,
        "content": None,
    }
    original = {
        "schema": "limen.native_capture.v1",
        "session_id": "session",
        "scope_paths": {"root": "a" * 64},
        "entries": {
            "root": {
                ".": {
                    "measured": True,
                    "acl_measured": True,
                    "xattrs_measured": True,
                    "metadata": metadata,
                }
            }
        },
    }
    observed = copy.deepcopy(original)
    observed["scope_paths"] = {"root": "b" * 64}
    return original, observed


def compare(original, observed):
    return compare_native_manifests(
        json.dumps(original).encode(),
        json.dumps(observed).encode(),
        session_id="session",
        original_scope_paths={"root": "a" * 64},
        observed_scope_paths={"root": "b" * 64},
    )


def test_distinct_clocks_are_recorded_not_claimed_recreated(manifests):
    original, observed = manifests
    observed["entries"]["root"]["."]["metadata"].update(atime_ns=30, ctime_ns=40)
    report = compare(original, observed)
    assert report["atom_count"] == 1
    assert report["atoms_with_distinct_historical_clocks"] == 1
    assert report["historical_clock_records_required"] == ["atime_ns", "ctime_ns"]
    for field in (
        "clock_equality_claimed",
        "custody_verified",
        "freshness_verified",
        "relocation_authorized",
        "retirement_authorized",
        "session_release_certified",
    ):
        assert report[field] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", 0o755),
        ("uid", 502),
        ("gid", 21),
        ("mtime_ns", 10),
        ("birthtime_ns", 20),
        ("flags", 1),
        ("nlink", 2),
        ("xattrs", {"user.fixture": "c" * 64}),
        ("acl", "d" * 64),
    ],
)
def test_materialized_metadata_cannot_drift(manifests, field, value):
    original, observed = manifests
    observed["entries"]["root"]["."]["metadata"][field] = value
    with pytest.raises(PortableCustodyError):
        compare(original, observed)


@pytest.mark.parametrize("field", ["atime_ns", "ctime_ns", "birthtime_ns", "acl", "xattrs"])
def test_historical_fields_cannot_be_omitted(manifests, field):
    original, observed = manifests
    del observed["entries"]["root"]["."]["metadata"][field]
    with pytest.raises(PortableCustodyError):
        compare(original, observed)


def test_missing_atom_cannot_be_relabelled_equivalent(manifests):
    original, observed = manifests
    observed["entries"]["root"].clear()
    with pytest.raises(PortableCustodyError):
        compare(original, observed)


@pytest.mark.parametrize("mutation", ["content", "size", "hardlink", "missing", "extra"])
def test_file_membership_and_recovery_bytes_are_exact(manifests, mutation):
    original, observed = manifests
    entry = copy.deepcopy(original["entries"]["root"]["."])
    entry["metadata"].update(type="file", size=12, content="e" * 64, hardlink_group="root/file")
    original["entries"]["root"]["file"] = entry
    observed["entries"]["root"]["file"] = copy.deepcopy(entry)
    rows = observed["entries"]["root"]
    if mutation == "content":
        rows["file"]["metadata"]["content"] = "f" * 64
    elif mutation == "size":
        rows["file"]["metadata"]["size"] = 13
    elif mutation == "hardlink":
        rows["file"]["metadata"]["hardlink_group"] = "root/other"
    elif mutation == "missing":
        del rows["file"]
    else:
        rows["extra"] = copy.deepcopy(entry)
    with pytest.raises(PortableCustodyError):
        compare(original, observed)


def test_changed_session_or_locator_cannot_rebind_original_scope(manifests):
    original, observed = manifests
    observed["session_id"] = "different-session"
    with pytest.raises(PortableCustodyError):
        compare(original, observed)
    observed["session_id"] = "session"
    observed["scope_paths"] = {"root": "c" * 64}
    with pytest.raises(PortableCustodyError):
        compare(original, observed)
