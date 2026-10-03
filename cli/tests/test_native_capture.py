"""Capture all native members without writes, ignore rules or symlink traversal."""

import ctypes
import hashlib
import json
import os
import sys

import pytest

from limen.native_capture import NativeCaptureError, capture_manifests, mac_native_attributes


def capture(roots, **changes):
    return capture_manifests(
        roots,
        session_id="native-session",
        max_atoms=changes.pop("max_atoms", 100),
        max_file_bytes=changes.pop("max_file_bytes", 1000),
        timeout_seconds=changes.pop("timeout_seconds", 10),
        **changes,
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS native metadata observer")
def test_real_native_capture_includes_ignored_data_links_and_attributes(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / ".gitignore").write_text("ignored\n")
    (root / "ignored").write_bytes(b"captured despite ignore")
    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    lib.setxattr.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    lib.setxattr.restype = ctypes.c_int
    value = b"fixture native attribute"
    assert lib.setxattr(os.fsencode(root / "ignored"), b"com.limen.fixture", value, len(value), 0, 1) == 0
    os.link(root / "ignored", root / "hardlink")
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside the scope")
    (root / "symbolic").symlink_to(outside)
    before = {path: path.lstat() for path in root.iterdir()}
    logical_raw, native_raw = capture({"source": root})
    logical, native = json.loads(logical_raw), json.loads(native_raw)
    assert set(logical["entries"]["source"]) == {".", ".gitignore", "ignored", "hardlink", "symbolic"}
    rows = native["entries"]["source"]
    assert rows["ignored"]["metadata"]["content"] == hashlib.sha256(b"captured despite ignore").hexdigest()
    assert (
        rows["ignored"]["metadata"]["xattrs"]["com.limen.fixture"]
        == hashlib.sha256(b"fixture native attribute").hexdigest()
    )
    assert rows["ignored"]["metadata"]["hardlink_group"] == rows["hardlink"]["metadata"]["hardlink_group"]
    assert rows["symbolic"]["metadata"]["type"] == "symlink"
    assert rows["symbolic"]["metadata"]["content"] == hashlib.sha256(os.fsencode(outside)).hexdigest()
    assert "outside the scope" not in native_raw.decode()
    for path, old in before.items():
        assert path.lstat().st_mtime_ns == old.st_mtime_ns
        assert path.lstat().st_ctime_ns == old.st_ctime_ns


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS native metadata observer")
def test_hardlink_membership_spans_declared_roots(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "file").write_bytes(b"linked")
    os.link(first / "file", second / "file")
    _, raw = capture({"first": first, "second": second})
    entries = json.loads(raw)["entries"]
    assert entries["first"]["file"]["metadata"]["hardlink_group"] == "first/file"
    assert entries["second"]["file"]["metadata"]["hardlink_group"] == "first/file"


@pytest.mark.parametrize(
    "changes",
    [
        {"max_atoms": 0},
        {"max_atoms": True},
        {"max_file_bytes": -1},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": 0},
    ],
)
def test_nonfinite_or_invalid_bounds_do_not_start_capture(tmp_path, changes):
    with pytest.raises(NativeCaptureError):
        capture({"scope": tmp_path}, **changes)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS native metadata observer")
@pytest.mark.parametrize("changes", [{"max_atoms": 1}, {"max_file_bytes": 0}])
def test_bounds_fail_whole_capture_instead_of_truncating(tmp_path, changes):
    (tmp_path / "file").write_bytes(b"payload")
    with pytest.raises(NativeCaptureError):
        capture({"scope": tmp_path}, **changes)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS native metadata observer")
def test_changed_native_source_never_produces_a_manifest(tmp_path):
    file = tmp_path / "file"
    file.write_bytes(b"before")

    def changing_attributes(path):
        result = mac_native_attributes(path)
        if path == file:
            file.write_bytes(b"after")
        return result

    with pytest.raises(NativeCaptureError, match="changed"):
        capture({"scope": tmp_path}, read_native=changing_attributes)


def test_unsupported_native_backend_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "unsupported")
    with pytest.raises(NativeCaptureError):
        mac_native_attributes(tmp_path)
