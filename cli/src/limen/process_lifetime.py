"""Bounded Darwin kernel witnesses for an explicit responsible-host bridge.

Matching pipes alone confer no ownership. A source-owned contract and a finally
verified native peer are separate required inputs to the ownership assessor.
ABI: macOS SDK sys/proc_info.h pipe_fdinfo, 24+136+24 bytes.
"""

from __future__ import annotations

import ctypes
import struct
import sys

from limen.process_ownership import Process, native_details


def decode_pipe(payload: bytes) -> dict:
    if len(payload) != 184:
        raise ValueError("native_pipe_abi_size")
    flags = struct.unpack_from("<I", payload, 0)[0]
    device = struct.unpack_from("<I", payload, 24)[0]
    mode = struct.unpack_from("<H", payload, 28)[0]
    inode = struct.unpack_from("<Q", payload, 32)[0]
    uid = struct.unpack_from("<I", payload, 40)[0]
    handle, peer = struct.unpack_from("<QQ", payload, 160)
    if mode & 0o170000 != 0o010000 or not handle or not peer or handle == peer:
        raise ValueError("native_pipe_not_connected_fifo")
    return {"flags": flags, "device": device, "inode": inode, "uid": uid, "handle": handle, "peer": peer}


def kernel_pipe(pid: int, descriptor: int) -> dict:
    if sys.platform != "darwin" or sys.byteorder != "little" or pid <= 0 or not 0 <= descriptor < 4096:
        raise ValueError("native_pipe_unsupported_subject")
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_pidfdinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
    library.proc_pidfdinfo.restype = ctypes.c_int
    payload = ctypes.create_string_buffer(184)
    if library.proc_pidfdinfo(pid, descriptor, 6, payload, 184) != 184:
        raise ValueError("native_pipe_unmeasured")
    return decode_pipe(payload.raw)


def reciprocal_pipe(reader: dict, writer: dict, uid: int) -> bool:
    return bool(
        reader.get("uid") == writer.get("uid") == uid
        and reader.get("handle")
        and reader.get("peer")
        and reader["handle"] != reader["peer"]
        and reader["handle"] == writer.get("peer")
        and reader["peer"] == writer.get("handle")
        and reader.get("device") == writer.get("device")
        and reader.get("inode") == writer.get("inode")
        and reader.get("flags", 0) & 3 == 1
        and writer.get("flags", 0) & 3 == 2
    )


def kernel_pipes(pid: int, limit: int) -> list[tuple[int, dict]]:
    """Bound the complete FD census; truncation is not an empty pipe set."""
    if sys.platform != "darwin" or sys.byteorder != "little" or pid <= 0 or not 1 <= limit <= 128:
        raise ValueError("native_descriptor_scope_unsupported")
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    library.proc_pidinfo.restype = ctypes.c_int
    payload = ctypes.create_string_buffer((limit + 1) * 8)
    size = library.proc_pidinfo(pid, 1, 0, payload, len(payload))
    if size <= 0 or size % 8 or size > limit * 8:
        raise ValueError("native_descriptor_census_unmeasured_or_truncated")
    result = []
    seen = set()
    for offset in range(0, size, 8):
        descriptor, kind = struct.unpack_from("<iI", payload.raw, offset)
        if descriptor < 0 or descriptor in seen:
            raise ValueError("native_descriptor_census_ambiguous")
        seen.add(descriptor)
        if kind == 6:  # PROX_FDTYPE_PIPE, SDK sys/proc_info.h.
            result.append((descriptor, kernel_pipe(pid, descriptor)))
    return result


def find_lifetime_descriptors(host_pid: int, peer_pid: int, uid: int, limit: int) -> tuple[int, int] | None:
    """Exactly one reader/writer pair, over two bounded complete censuses."""
    if host_pid == peer_pid:
        return None
    readers, writers = kernel_pipes(host_pid, limit), kernel_pipes(peer_pid, limit)
    matches = [
        (read_fd, write_fd)
        for read_fd, reader in readers
        for write_fd, writer in writers
        if reciprocal_pipe(reader, writer, uid)
    ]
    return matches[0] if len(matches) == 1 else None


def live_lifetime_bridge(host: Process, peer: Process, read_fd: int, write_fd: int, identity) -> bool:
    """Reject PID reuse, exec, closed/replaced descriptors and crossed users."""
    if (
        host.pid == peer.pid
        or host.uid != peer.uid
        or not host.readable
        or not peer.readable
        or not host.started
        or not peer.started
        or identity(host.pid) != host.started
        or identity(peer.pid) != peer.started
    ):
        return False
    try:
        if native_details(host.pid)[0] != host.argv or native_details(peer.pid)[0] != peer.argv:
            return False
        reader, writer = kernel_pipe(host.pid, read_fd), kernel_pipe(peer.pid, write_fd)
        if not reciprocal_pipe(reader, writer, host.uid):
            return False
        return bool(
            identity(host.pid) == host.started
            and identity(peer.pid) == peer.started
            and native_details(host.pid)[0] == host.argv
            and native_details(peer.pid)[0] == peer.argv
            and kernel_pipe(host.pid, read_fd) == reader
            and kernel_pipe(peer.pid, write_fd) == writer
        )
    except (OSError, ValueError, TypeError):
        return False
