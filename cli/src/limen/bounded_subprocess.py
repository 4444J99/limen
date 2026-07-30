"""Subprocess execution with wall-clock and in-flight output ceilings."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

FailureKind = Literal["invalid", "output", "timeout", "unavailable"]


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


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    with suppress(OSError):
        os.killpg(process.pid, signal.SIGTERM)
    if process.poll() is None:
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=0.25)
    with suppress(OSError):
        os.killpg(process.pid, signal.SIGKILL)
    if process.poll() is None:
        with suppress(OSError):
            process.kill()
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=1.0)


def run_bounded_subprocess(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    stdout_ceiling: int,
    stderr_ceiling: int,
    env: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None,
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
    ):
        raise BoundedSubprocessError("invalid")
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=None if env is None else dict(env),
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
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
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_size = 0
    stderr_size = 0
    input_offset = 0
    deadline = time.monotonic() + timeout_seconds
    streams: dict[int, tuple[str, object]] = {}

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
        while any(label != "stdin" for label, _stream in streams.values()):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BoundedSubprocessError("timeout")
            events = selector.select(timeout=min(remaining, 0.1))
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
        try:
            returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise BoundedSubprocessError("timeout") from exc
    except BoundedSubprocessError:
        _terminate_process_group(process)
        raise
    except OSError as exc:
        _terminate_process_group(process)
        raise BoundedSubprocessError("unavailable") from exc
    finally:
        selector.close()
        for _label, stream in streams.values():
            with suppress(OSError):
                stream.close()  # type: ignore[attr-defined]

    return BoundedCompletedProcess(
        returncode=returncode,
        stdout=b"".join(stdout_chunks),
        stderr=b"".join(stderr_chunks),
    )
