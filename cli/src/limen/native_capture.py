"""Bounded, read-only native capture; no ignores and no symlink traversal.

Capture bytes are private. They must enter the encrypted custody workflow, not a
public report. Unsupported native metadata or a changing source fails closed.
Capture alone is neither restoration proof nor permission to retire a source.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import math
import os
import re
import stat
import struct
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


class NativeCaptureError(ValueError):
    """A complete stable native source observation could not be established."""


def mac_birthtime_ns(path: Path) -> int:
    """Read ATTR_CMN_CRTIME exactly; Python exposes only a float on macOS."""
    if sys.platform != "darwin":
        raise NativeCaptureError("native creation timestamp backend is unavailable")

    class AttrList(ctypes.Structure):
        _fields_ = [
            ("bitmapcount", ctypes.c_uint16),
            ("reserved", ctypes.c_uint16),
            ("commonattr", ctypes.c_uint32),
            ("volattr", ctypes.c_uint32),
            ("dirattr", ctypes.c_uint32),
            ("fileattr", ctypes.c_uint32),
            ("forkattr", ctypes.c_uint32),
        ]

    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    lib.getattrlist.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(AttrList),
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_ulong,
    ]
    lib.getattrlist.restype = ctypes.c_int
    attrs = AttrList(5, 0, 0x00000200, 0, 0, 0, 0)
    # getattrlist packs the length and returned timespec on four-byte boundaries.
    buffer = ctypes.create_string_buffer(20)
    if lib.getattrlist(os.fsencode(path), ctypes.byref(attrs), buffer, len(buffer), 1):
        raise NativeCaptureError("native creation timestamp observation failed")
    if struct.unpack_from("=I", buffer.raw)[0] != 20:
        raise NativeCaptureError("native creation timestamp record is malformed")
    seconds, nanoseconds = struct.unpack_from("=qq", buffer.raw, 4)
    if not 0 <= nanoseconds < 1_000_000_000:
        raise NativeCaptureError("native creation timestamp precision is malformed")
    return seconds * 1_000_000_000 + nanoseconds


def _fingerprint(value: os.stat_result) -> tuple:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_nlink,
        getattr(value, "st_birthtime_ns", None),
        getattr(value, "st_flags", None),
    )


def mac_native_attributes(path: Path) -> tuple[dict[str, str], str]:
    """Read link-local xattrs and ACL; return digests, never native value bytes."""
    if sys.platform != "darwin":
        raise NativeCaptureError("native ACL/xattr backend is unavailable on this host")
    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    lib.listxattr.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    lib.listxattr.restype = ctypes.c_ssize_t
    lib.getxattr.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    lib.getxattr.restype = ctypes.c_ssize_t
    lib.acl_get_link_np.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.acl_get_link_np.restype = ctypes.c_void_p
    lib.acl_to_text.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ssize_t)]
    lib.acl_to_text.restype = ctypes.c_void_p
    lib.acl_free.argtypes = [ctypes.c_void_p]
    lib.acl_free.restype = ctypes.c_int

    def checked(count: int) -> int:
        if count < 0:
            raise NativeCaptureError("native xattr observation failed")
        return count

    raw = os.fsencode(path)
    size = checked(lib.listxattr(raw, None, 0, 1))  # XATTR_NOFOLLOW
    buffer = ctypes.create_string_buffer(size)
    used = checked(lib.listxattr(raw, buffer, size, 1))
    attrs = {}
    for name in buffer.raw[:used].split(b"\0"):
        if name:
            size = checked(lib.getxattr(raw, name, None, 0, 0, 1))
            value = ctypes.create_string_buffer(size)
            count = checked(lib.getxattr(raw, name, value, size, 0, 1))
            attrs[os.fsdecode(name)] = hashlib.sha256(value.raw[:count]).hexdigest()
    before = path.lstat()
    ctypes.set_errno(0)
    handle = lib.acl_get_link_np(raw, 0x100)  # ACL_TYPE_EXTENDED, no link following
    if not handle:
        error = ctypes.get_errno()
        if error == errno.ENOENT and _fingerprint(before) == _fingerprint(path.lstat()):
            return attrs, "absent"
        raise NativeCaptureError("native ACL observation is unmeasured")
    text = None
    try:
        length = ctypes.c_ssize_t()
        text = lib.acl_to_text(handle, ctypes.byref(length))
        if not text:
            raise NativeCaptureError("native ACL text observation failed")
        return attrs, hashlib.sha256(ctypes.string_at(text, length.value)).hexdigest()
    finally:
        if text:
            lib.acl_free(text)
        lib.acl_free(handle)


def capture_manifests(
    scope_roots: Mapping[str, Path],
    *,
    session_id: str,
    max_atoms: int,
    max_file_bytes: int,
    timeout_seconds: float,
    read_native: Callable[[Path], tuple[dict[str, str], str]] = mac_native_attributes,
) -> tuple[bytes, bytes]:
    """Capture every source member with finite caller-supplied resource bounds.

    The caller admits the workload before invoking this function. Exceeding a bound
    fails the whole capture, never silently truncates its denominator. Opaque root
    IDs bind canonical source path hashes; every native field is explicitly read.
    """
    if (
        not scope_roots
        or not session_id
        or type(max_atoms) is not int
        or max_atoms <= 0
        or type(max_file_bytes) is not int
        or max_file_bytes < 0
        or type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise NativeCaptureError("explicit scope identity and finite positive bounds are required")
    deadline = time.monotonic() + timeout_seconds
    logical: dict[str, dict[str, dict[str, Any]]] = {}
    native: dict[str, dict[str, dict[str, Any]]] = {}
    scopes: dict[str, str] = {}
    witnesses: dict[Path, tuple] = {}
    atoms = file_bytes = 0
    hardlinks: dict[tuple[int, int], str] = {}

    def budget() -> None:
        if time.monotonic() >= deadline:
            raise NativeCaptureError("native capture deadline exceeded")

    for identifier, root in scope_roots.items():
        budget()
        if (
            not isinstance(identifier, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", identifier) is None
            or not root.is_absolute()
            or root != root.resolve(strict=True)
        ):
            raise NativeCaptureError("native capture scope is not canonical")
        if root.is_symlink() or not root.is_dir():
            raise NativeCaptureError("native capture root is not an exact directory")
        scopes[identifier] = hashlib.sha256(os.fsencode(root)).hexdigest()
        logical[identifier], native[identifier] = {}, {}
        pending = [root]
        while pending:
            budget()
            path = pending.pop()
            before = path.lstat()
            kind = (
                "file"
                if stat.S_ISREG(before.st_mode)
                else "directory"
                if stat.S_ISDIR(before.st_mode)
                else "symlink"
                if stat.S_ISLNK(before.st_mode)
                else None
            )
            if kind is None:
                raise NativeCaptureError("special file requires a separate full native custodian")
            atoms += 1
            file_bytes += before.st_size if kind == "file" else 0
            if atoms > max_atoms or file_bytes > max_file_bytes:
                raise NativeCaptureError("native capture resource bound exceeded")
            relative = path.relative_to(root).as_posix()
            group = None
            if kind == "file" and before.st_nlink > 1:
                group = hardlinks.setdefault((before.st_dev, before.st_ino), identifier + "/" + relative)
            content = None
            if kind == "file":
                with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
                    if _fingerprint(os.fstat(stream.fileno())) != _fingerprint(before):
                        raise NativeCaptureError("native source changed before content observation")
                    hasher = hashlib.sha256()
                    read_size = 0
                    while block := stream.read(1024 * 1024):
                        budget()
                        read_size += len(block)
                        if read_size > before.st_size:
                            raise NativeCaptureError("native source exceeded its captured byte bound")
                        hasher.update(block)
                    content = hasher.hexdigest()
            elif kind == "symlink":
                content = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
            else:
                pending.extend(sorted(path.iterdir(), reverse=True))
            if not hasattr(before, "st_birthtime") or not hasattr(before, "st_flags"):
                raise NativeCaptureError("native birthtime or file flags are unavailable")
            attrs, acl = read_native(path)
            metadata: dict[str, Any] = {
                "type": kind,
                "mode": stat.S_IMODE(before.st_mode),
                "uid": before.st_uid,
                "gid": before.st_gid,
                "mtime_ns": before.st_mtime_ns,
                "birthtime_ns": mac_birthtime_ns(path),
                "atime_ns": before.st_atime_ns,
                "ctime_ns": before.st_ctime_ns,
                "flags": before.st_flags,
                "nlink": before.st_nlink,
                "xattrs": attrs,
                "acl": acl,
                "hardlink_group": group,
                "size": before.st_size if kind == "file" else None,
                "content": content,
            }
            if _fingerprint(path.lstat()) != _fingerprint(before):
                raise NativeCaptureError("native source changed during observation")
            if path in witnesses and witnesses[path] != _fingerprint(before):
                raise NativeCaptureError("overlapping native source changed between scope observations")
            witnesses[path] = _fingerprint(before)
            logical[identifier][relative] = {
                key: metadata[key] for key in ("type", "size", "content", "hardlink_group")
            }
            native[identifier][relative] = {
                "measured": True,
                "acl_measured": True,
                "xattrs_measured": True,
                "metadata": metadata,
            }
    # A file measured early must not change while later roots are being captured.
    for path, expected in witnesses.items():
        budget()
        if _fingerprint(path.lstat()) != expected:
            raise NativeCaptureError("native source changed before capture completed")
    if len(set(scopes.values())) != len(scopes):
        raise NativeCaptureError("duplicate native scope root")
    packets = []
    for schema, entries in (("limen.logical_capture.v1", logical), ("limen.native_capture.v1", native)):
        packets.append(
            json.dumps(
                {"schema": schema, "session_id": session_id, "scope_paths": scopes, "entries": entries},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
    return packets[0], packets[1]
