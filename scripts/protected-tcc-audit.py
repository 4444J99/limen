#!/usr/bin/env python3
"""Bootstrap the source-bound one-shot native audit without a mutable PATH import."""

import sys
import os
import signal
import resource
import json
import time
import ctypes
import struct
from pathlib import Path

if len(sys.argv) == 3 and sys.argv[1] == "--job":
    # Native application launches do not inherit the caller's process limits.
    # Establish a finite import bound and owner claim before loading Limen.
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
    request_path = Path(sys.argv[2]).resolve()
    fd = os.open(request_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 16384:
        os.close(fd)
        raise SystemExit(69)
    with os.fdopen(fd) as stream:
        request = json.load(stream)
    remaining = request["deadline"] - time.monotonic()
    if remaining <= 1:
        raise SystemExit(69)
    import_deadline = time.monotonic() + min(22, remaining - 1)

    def owner_present():
        try:
            pid = request["owner_pid"]
            if sys.platform == "darwin":
                native = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True).proc_pidinfo
                native.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
                native.restype = ctypes.c_int
                # Darwin <sys/proc_info.h> proc_bsdinfo: PID at12, start timeval at120.
                value = ctypes.create_string_buffer(136)
                if native(pid, 3, 0, value, 136) != 136 or struct.unpack_from("=I", value.raw, 12)[0] != pid:
                    return False
                seconds, micros = struct.unpack_from("=QQ", value.raw, 120)
                identity = f"darwin-proc-start:{seconds}:{micros}"
            else:
                tail = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                identity = f"proc-start:{tail[19]}"
            return identity == request["owner_identity"]
        except (OSError, ValueError, IndexError):
            return False

    def guard(*_args):
        if time.monotonic() >= import_deadline or not owner_present():
            os._exit(69)

    signal.signal(signal.SIGALRM, guard)
    guard()
    signal.setitimer(signal.ITIMER_REAL, 0.25, 0.25)
    claim_fd = os.open(
        request_path.parent / "bootstrap.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(claim_fd, "w") as stream:
        json.dump({"nonce": request["nonce"], "host_pid": os.getppid(), "receiver_pid": os.getpid()}, stream)
        stream.flush()
        os.fsync(stream.fileno())

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli/src"))
from limen.protected_tcc_audit import main

raise SystemExit(main())
