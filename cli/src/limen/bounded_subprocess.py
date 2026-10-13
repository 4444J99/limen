"""POSIX-only subprocess execution with wall-clock and output ceilings.

Unsupported platforms fail closed before process startup because cleanup relies
on POSIX sessions, process groups, and signals.
"""

from __future__ import annotations

import os
import ctypes
import errno
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FailureKind = Literal["descendants", "invalid", "output", "resource", "timeout", "unavailable"]
_BOOTSTRAP_FAILURE = b"limen: bounded child setup unavailable\n"
_CHILD_BOOTSTRAP = """
import os, resource, sys
try:
    os.setsid()
    os.chdir(sys.argv[2])
    names = os.listdir('/dev/fd' if os.path.isdir('/dev/fd') else '/proc/self/fd')
    if len(names) > 4096:
        raise RuntimeError('descriptor census exceeds bound')
    for name in names:
        fd = int(name)
        if fd > 2:
            try:
                os.close(fd)
            except OSError as error:
                if error.errno != 9:
                    raise
    if sys.argv[1] != 'none':
        soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
        limit = int(sys.argv[1])
        resource.setrlimit(resource.RLIMIT_CPU, (limit if hard == resource.RLIM_INFINITY else min(limit, hard), hard))
    os.execvpe(sys.argv[3], sys.argv[3:], os.environ)
except BaseException:
    os.write(2, b'limen: bounded child setup unavailable\\n')
    os._exit(125)
"""


class BoundedSubprocessError(RuntimeError):
    """A subprocess failed before it could return one bounded result."""

    def __init__(self, kind: FailureKind, *, stage: Literal["rss_census", "descendant_census"] | None = None):
        self.kind = kind
        self.stage = stage
        super().__init__(kind)


@dataclass(frozen=True)
class BoundedCompletedProcess:
    """The complete bounded output and exit status of one subprocess."""

    returncode: int
    stdout: bytes
    stderr: bytes


class _ProcTaskInfo(ctypes.Structure):
    # Darwin sys/proc_info.h: PROC_PIDTASKINFO, six uint64 and twelve int32 fields.
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in ("virtual_size", "resident_size", "total_user", "total_system", "threads_user", "threads_system")
    ] + [(f"counter_{index}", ctypes.c_int32) for index in range(12)]


class _DarwinProcessGroup:
    """Measure only the owned group through libproc, never spawn a host-wide ps."""

    def __init__(self, pgid: int, library=None, check_budget=lambda: None):
        self.pgid = pgid
        self.check_budget = check_budget
        self.library = library or ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        if library is None:
            self.library.proc_listpgrppids.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
            self.library.proc_listpgrppids.restype = ctypes.c_int
            self.library.proc_pidinfo.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint64,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            self.library.proc_pidinfo.restype = ctypes.c_int

    def pids(self) -> list[int]:
        self.check_budget()
        buffer = (ctypes.c_int * 1024)()
        ctypes.set_errno(0)
        count = self.library.proc_listpgrppids(self.pgid, buffer, ctypes.sizeof(buffer))
        # Unlike proc_listpids, proc_listpgrppids returns a PID count, not bytes.
        if count < 0 or count >= len(buffer) or (count == 0 and ctypes.get_errno() not in (0, errno.ESRCH)):
            raise BoundedSubprocessError("unavailable", stage="descendant_census")
        pids = list(buffer[:count])
        if any(pid <= 0 for pid in pids) or len(set(pids)) != len(pids):
            raise BoundedSubprocessError("unavailable", stage="descendant_census")
        verified = []
        for pid in pids:
            self.check_budget()
            try:
                if os.getpgid(pid) != self.pgid:
                    raise BoundedSubprocessError("unavailable", stage="descendant_census")
            except ProcessLookupError:
                continue
            verified.append(pid)
        return verified

    def rss(self) -> int:
        total = 0
        for pid in self.pids():
            self.check_budget()
            info = _ProcTaskInfo()
            ctypes.set_errno(0)
            size = self.library.proc_pidinfo(pid, 4, 0, ctypes.byref(info), ctypes.sizeof(info))
            if size == 0 and ctypes.get_errno() == errno.ESRCH:
                continue  # This exact member exited between enumeration and measurement.
            if size != ctypes.sizeof(info):
                raise BoundedSubprocessError("unavailable", stage="rss_census")
            total += info.resident_size
        return total


def _supports_posix_process_groups() -> bool:
    return os.name == "posix" and hasattr(os, "killpg") and hasattr(signal, "SIGTERM") and hasattr(signal, "SIGKILL")


def _terminate_process_group(process: subprocess.Popen[bytes]) -> bool:
    """Best-effort terminate and reap without replacing the triggering failure."""

    def reaped() -> bool:
        try:
            return process.poll() is not None
        except BaseException:  # noqa: BLE001 - cleanup must preserve the triggering failure
            return False

    def wait(timeout: float) -> bool:
        try:
            process.wait(timeout=timeout)
        except BaseException:  # noqa: BLE001 - cleanup must preserve the triggering failure
            return False
        return True

    was_reaped = reaped()
    with suppress(BaseException):
        os.killpg(process.pid, signal.SIGTERM)
    if not was_reaped:
        with suppress(BaseException):
            process.terminate()
        was_reaped = wait(0.25)

    # The group kill remains unconditional so a wrapper that exited first
    # cannot leave a descendant holding either output pipe.
    with suppress(BaseException):
        os.killpg(process.pid, signal.SIGKILL)
    if not was_reaped:
        with suppress(BaseException):
            process.kill()
        was_reaped = wait(1.0)
    return was_reaped or reaped()


def run_bounded_subprocess(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    stdout_ceiling: int,
    stderr_ceiling: int,
    env: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None,
    cpu_seconds: int | None = None,
    rss_ceiling: int | None = None,
) -> BoundedCompletedProcess:
    """Run one command while terminating it as soon as either output cap is crossed."""

    if (
        not command
        or isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
        or isinstance(stdout_ceiling, bool)
        or not isinstance(stdout_ceiling, int)
        or stdout_ceiling < 0
        or isinstance(stderr_ceiling, bool)
        or not isinstance(stderr_ceiling, int)
        or stderr_ceiling < 0
        or (input_bytes is not None and not isinstance(input_bytes, bytes))
        or (
            cpu_seconds is not None
            and (isinstance(cpu_seconds, bool) or not isinstance(cpu_seconds, int) or cpu_seconds <= 0)
        )
        or (
            rss_ceiling is not None
            and (isinstance(rss_ceiling, bool) or not isinstance(rss_ceiling, int) or rss_ceiling <= 0)
        )
    ):
        raise BoundedSubprocessError("invalid")
    if not _supports_posix_process_groups():
        raise BoundedSubprocessError("unavailable")

    deadline = time.monotonic() + timeout_seconds
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                _CHILD_BOOTSTRAP,
                str(cpu_seconds) if cpu_seconds is not None else "none",
                str(cwd),
                *command,
            ],
            env=None if env is None else dict(env),
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # Use posix_spawn, then close actual inherited descriptors and
            # establish the owned session in an isolated exec bootstrap. A
            # Python preexec callback forces fork/descriptor-close work before
            # Popen returns, outside the parent's monitor on a high-FD host.
            close_fds=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BoundedSubprocessError("unavailable") from exc
    if (
        process.stdout is None or process.stderr is None or (input_bytes is not None and process.stdin is None)
    ):  # pragma: no cover - subprocess.PIPE invariants
        _terminate_process_group(process)
        raise BoundedSubprocessError("unavailable")

    try:
        selector = selectors.DefaultSelector()
    except OSError as exc:
        _terminate_process_group(process)
        raise BoundedSubprocessError("unavailable") from exc
    except BaseException:
        _terminate_process_group(process)
        raise
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_size = 0
    stderr_size = 0
    input_offset = 0
    next_rss_check = 0.0
    streams: dict[int, tuple[str, object]] = {}
    native_group = None

    def census_timeout() -> float:
        # A busy host can take more than 0.5s to enumerate its protected jobs.
        # Census remains mandatory and consumes the original wall budget.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BoundedSubprocessError("timeout")
        return min(3.0, remaining)

    def process_group_rss() -> int:
        if native_group is not None:
            return native_group.rss()
        try:
            observed = subprocess.run(
                ["ps", "-axo", "pgid=,rss="],
                capture_output=True,
                text=True,
                timeout=census_timeout(),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BoundedSubprocessError("unavailable", stage="rss_census") from exc
        if observed.returncode != 0:
            raise BoundedSubprocessError("unavailable", stage="rss_census")
        total_kib = 0
        for line in observed.stdout.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0].isdigit() and fields[1].isdigit() and int(fields[0]) == process.pid:
                total_kib += int(fields[1])
        return total_kib * 1024

    def surviving_process_group_pids() -> list[int]:
        if native_group is not None:
            return [pid for pid in native_group.pids() if pid != process.pid]
        try:
            observed = subprocess.run(
                ["ps", "-axo", "pid=,pgid="],
                capture_output=True,
                text=True,
                timeout=census_timeout(),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BoundedSubprocessError("unavailable", stage="descendant_census") from exc
        if observed.returncode != 0:
            raise BoundedSubprocessError("unavailable", stage="descendant_census")
        survivors: list[int] = []
        for line in observed.stdout.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0].isdigit() and fields[1].isdigit() and int(fields[1]) == process.pid:
                pid = int(fields[0])
                if pid != process.pid:
                    survivors.append(pid)
        return survivors

    def register_stream(stream: object, events: int, label: str) -> None:
        descriptor = stream.fileno()  # type: ignore[attr-defined]
        os.set_blocking(descriptor, False)
        selector.register(descriptor, events, data=label)
        streams[descriptor] = (label, stream)

    try:
        if sys.platform == "darwin":
            try:
                native_group = _DarwinProcessGroup(process.pid, check_budget=census_timeout)
            except (OSError, AttributeError) as exc:
                raise BoundedSubprocessError("unavailable", stage="descendant_census") from exc
        register_stream(process.stdout, selectors.EVENT_READ, "stdout")
        register_stream(process.stderr, selectors.EVENT_READ, "stderr")
        if input_bytes is not None:
            assert process.stdin is not None
            if input_bytes:
                register_stream(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
        while any(label != "stdin" for label, _stream in streams.values()) or process.poll() is None:
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                raise BoundedSubprocessError("timeout")
            if rss_ceiling is not None and process.poll() is None and now >= next_rss_check:
                next_rss_check = now + 1.0
                if process_group_rss() > rss_ceiling:
                    raise BoundedSubprocessError("resource")
            if streams:
                events = selector.select(timeout=min(remaining, 0.1))
            else:
                time.sleep(min(remaining, 0.1))
                events = []
            if not events:
                continue
            for key, _mask in events:
                descriptor = key.fd
                label, stream = streams[descriptor]
                if label == "stdin":
                    assert input_bytes is not None
                    try:
                        written = os.write(descriptor, input_bytes[input_offset : input_offset + 65_536])
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        written = len(input_bytes) - input_offset
                    input_offset += written
                    if input_offset >= len(input_bytes):
                        selector.unregister(descriptor)
                        streams.pop(descriptor)
                        stream.close()  # type: ignore[attr-defined]
                    continue

                ceiling = stdout_ceiling if label == "stdout" else stderr_ceiling
                size = stdout_size if label == "stdout" else stderr_size
                try:
                    chunk = os.read(descriptor, min(65_536, ceiling - size + 1))
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(descriptor)
                    streams.pop(descriptor)
                    stream.close()  # type: ignore[attr-defined]
                    continue
                if label == "stdout":
                    stdout_size += len(chunk)
                    if stdout_size > stdout_ceiling:
                        raise BoundedSubprocessError("output")
                    stdout_chunks.append(chunk)
                else:
                    stderr_size += len(chunk)
                    if stderr_size > stderr_ceiling:
                        raise BoundedSubprocessError("output")
                    stderr_chunks.append(chunk)
        returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        if surviving_process_group_pids():
            raise BoundedSubprocessError("descendants")
        if returncode == 125 and b"".join(stderr_chunks).startswith(_BOOTSTRAP_FAILURE):
            raise BoundedSubprocessError("unavailable")
    except BoundedSubprocessError:
        _terminate_process_group(process)
        raise
    except OSError as exc:
        _terminate_process_group(process)
        raise BoundedSubprocessError("unavailable") from exc
    except BaseException:
        _terminate_process_group(process)
        raise
    finally:
        with suppress(BaseException):
            selector.close()
        for _label, stream in streams.values():
            with suppress(BaseException):
                stream.close()  # type: ignore[attr-defined]

    return BoundedCompletedProcess(
        returncode=returncode,
        stdout=b"".join(stdout_chunks),
        stderr=b"".join(stderr_chunks),
    )
