"""POSIX-only subprocess execution with wall-clock and output ceilings.

Unsupported platforms fail closed before process startup because cleanup relies
on POSIX sessions, process groups, and signals.
"""

from __future__ import annotations

import os
import resource
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FailureKind = Literal["descendants", "invalid", "output", "resource", "timeout", "unavailable"]


class BoundedSubprocessError(RuntimeError):
    """A subprocess failed before it could return one bounded result."""

    def __init__(self, kind: FailureKind):
        self.kind = kind
        super().__init__(kind)


@dataclass(frozen=True)
class BoundedCompletedProcess:
    """The complete bounded output and exit status of one subprocess."""

    returncode: int
    stdout: bytes
    stderr: bytes


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

    def apply_child_limits() -> None:
        if cpu_seconds is not None:
            _soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
            effective = cpu_seconds if hard == resource.RLIM_INFINITY else min(cpu_seconds, hard)
            resource.setrlimit(resource.RLIMIT_CPU, (effective, hard))

    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=None if env is None else dict(env),
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            preexec_fn=apply_child_limits if cpu_seconds is not None else None,
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
    deadline = time.monotonic() + timeout_seconds
    next_rss_check = 0.0
    streams: dict[int, tuple[str, object]] = {}

    def process_group_rss() -> int:
        try:
            observed = subprocess.run(
                ["ps", "-axo", "pgid=,rss="],
                capture_output=True,
                text=True,
                timeout=0.5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BoundedSubprocessError("unavailable") from exc
        if observed.returncode != 0:
            raise BoundedSubprocessError("unavailable")
        total_kib = 0
        for line in observed.stdout.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0].isdigit() and fields[1].isdigit() and int(fields[0]) == process.pid:
                total_kib += int(fields[1])
        return total_kib * 1024

    def surviving_process_group_pids() -> list[int]:
        try:
            observed = subprocess.run(
                ["ps", "-axo", "pid=,pgid="],
                capture_output=True,
                text=True,
                timeout=0.5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BoundedSubprocessError("unavailable") from exc
        if observed.returncode != 0:
            raise BoundedSubprocessError("unavailable")
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
        register_stream(process.stdout, selectors.EVENT_READ, "stdout")
        register_stream(process.stderr, selectors.EVENT_READ, "stderr")
        if input_bytes is not None:
            assert process.stdin is not None
            if input_bytes:
                register_stream(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
        while process.poll() is None or any(label != "stdin" for label, _stream in streams.values()):
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
