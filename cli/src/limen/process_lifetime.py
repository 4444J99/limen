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
