"""Tests for the shared in-flight subprocess output boundary."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess


def test_output_ceiling_terminates_during_execution(tmp_path: Path) -> None:
    with pytest.raises(BoundedSubprocessError, match="output") as raised:
        run_bounded_subprocess(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 65537)"],
            cwd=tmp_path,
            timeout_seconds=5,
            stdout_ceiling=1024,
            stderr_ceiling=1024,
        )
    assert raised.value.kind == "output"


def test_exited_wrapper_does_not_leave_a_pipe_holding_descendant(
    tmp_path: Path,
) -> None:
    child_pid_path = tmp_path / "child.pid"
    script = (
        "import subprocess, sys\n"
        "child = subprocess.Popen("
        "[sys.executable, '-c', 'import time; time.sleep(30)'],"
        " stdout=sys.stdout, stderr=sys.stderr)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(str(child.pid))\n"
    )
    with pytest.raises(BoundedSubprocessError, match="timeout") as raised:
        run_bounded_subprocess(
            [sys.executable, "-c", script, str(child_pid_path)],
            cwd=tmp_path,
            timeout_seconds=0.3,
            stdout_ceiling=1024,
            stderr_ceiling=1024,
        )
    assert raised.value.kind == "timeout"
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("bounded subprocess cleanup left its descendant alive")


def test_stream_oserror_is_closed_as_an_unavailable_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_read(_descriptor: int, _size: int) -> bytes:
        raise OSError("injected read failure")

    monkeypatch.setattr("limen.bounded_subprocess.os.read", fail_read)
    with pytest.raises(BoundedSubprocessError, match="unavailable") as raised:
        run_bounded_subprocess(
            [
                sys.executable,
                "-c",
                "import sys, time; sys.stdout.write('x'); sys.stdout.flush(); time.sleep(30)",
            ],
            cwd=tmp_path,
            timeout_seconds=1,
            stdout_ceiling=1024,
            stderr_ceiling=1024,
        )
    assert raised.value.kind == "unavailable"
