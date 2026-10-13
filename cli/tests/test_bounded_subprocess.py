"""Tests for the shared in-flight subprocess output boundary."""

from __future__ import annotations

import os
import ctypes
import errno
import json
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from pathlib import Path

import pytest
from limen import bounded_subprocess
from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess


def test_spawn_bootstrap_preserves_native_context_and_closes_inherited_handles(tmp_path, monkeypatch):
    captured = []
    real_popen = subprocess.Popen

    def capture(*args, **kwargs):
        captured.append(kwargs)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(bounded_subprocess.subprocess, "Popen", capture)
    with (tmp_path / "private-handle").open("w") as private:
        os.set_inheritable(private.fileno(), True)
        script = """
import json, os, resource, sys
try:
    os.fstat(int(sys.argv[1]))
    inherited = True
except OSError:
    inherited = False
print(json.dumps({'inherited': inherited, 'group': os.getpgrp() == os.getpid(),
                  'cwd': os.getcwd(), 'stdin': sys.stdin.read(), 'env': os.environ['BOOTSTRAP_TEST'],
                  'cpu': resource.getrlimit(resource.RLIMIT_CPU)[0]}))
"""
        result = run_bounded_subprocess(
            [sys.executable, "-c", script, str(private.fileno())],
            cwd=tmp_path,
            env={**os.environ, "BOOTSTRAP_TEST": "literal $(no shell)"},
            input_bytes=b"native input",
            timeout_seconds=10,
            stdout_ceiling=4096,
            stderr_ceiling=1024,
            cpu_seconds=1,
        )
        os.fstat(private.fileno())  # Closing the child's copy never touches the parent.
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "inherited": False,
        "group": True,
        "cwd": str(tmp_path.resolve()),
        "stdin": "native input",
        "env": "literal $(no shell)",
        "cpu": 1,
    }
    assert captured[0].get("preexec_fn") is None
    assert captured[0].get("cwd") is None and not captured[0].get("start_new_session")
    assert captured[0]["close_fds"] is False


def test_spawn_bootstrap_setup_failure_remains_typed_unavailable(tmp_path):
    with pytest.raises(BoundedSubprocessError, match="unavailable"):
        run_bounded_subprocess(
            [str(tmp_path / "missing-executable")],
            cwd=tmp_path,
            timeout_seconds=5,
            stdout_ceiling=1024,
            stderr_ceiling=1024,
            cpu_seconds=1,
        )


def test_darwin_owned_group_uses_pid_count_and_exact_rss(monkeypatch):
    def enumerate_group(pgid, buffer, _size):
        assert pgid == 99
        buffer[0], buffer[1] = 101, 102
        return 2  # Apple proc_listpgrppids returns a count, not byte length.

    def task(pid, flavor, _arg, output, size):
        assert flavor == 4 and size == 96
        ctypes.cast(output, ctypes.POINTER(bounded_subprocess._ProcTaskInfo)).contents.resident_size = pid * 1024
        return size

    monkeypatch.setattr(bounded_subprocess.os, "getpgid", lambda _pid: 99)
    group = bounded_subprocess._DarwinProcessGroup(
        99, SimpleNamespace(proc_listpgrppids=enumerate_group, proc_pidinfo=task)
    )
    assert group.pids() == [101, 102]
    assert group.rss() == 203 * 1024


@pytest.mark.parametrize("count,error", [(1024, 0), (-1, 0), (0, errno.EPERM)])
def test_darwin_incomplete_group_census_fails_closed(count, error):
    def enumerate_group(*_args):
        ctypes.set_errno(error)
        return count

    group = bounded_subprocess._DarwinProcessGroup(99, SimpleNamespace(proc_listpgrppids=enumerate_group))
    with pytest.raises(BoundedSubprocessError) as raised:
        group.pids()
    assert raised.value.stage == "descendant_census"


def test_darwin_unreadable_member_rss_fails_closed(monkeypatch):
    def enumerate_group(_pgid, buffer, _size):
        buffer[0] = 101
        return 1

    monkeypatch.setattr(bounded_subprocess.os, "getpgid", lambda _pid: 99)
    group = bounded_subprocess._DarwinProcessGroup(
        99, SimpleNamespace(proc_listpgrppids=enumerate_group, proc_pidinfo=lambda *_: 0)
    )
    with pytest.raises(BoundedSubprocessError) as raised:
        group.rss()
    assert raised.value.stage == "rss_census"


def test_slow_process_census_uses_original_wall_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(bounded_subprocess.sys, "platform", "linux")
    ceilings = []

    def delayed_census(command, **kwargs):
        if command[0] == "ps":
            ceilings.append(kwargs["timeout"])
            time.sleep(0.55)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(bounded_subprocess.subprocess, "run", delayed_census)
    result = run_bounded_subprocess(
        [sys.executable, "-c", "import time; time.sleep(0.2)"],
        cwd=tmp_path,
        timeout_seconds=8,
        stdout_ceiling=1024,
        stderr_ceiling=1024,
        rss_ceiling=512 * 1024 * 1024,
    )
    assert result.returncode == 0 and len(ceilings) == 2
    assert all(0.5 < ceiling <= 3 for ceiling in ceilings)


def test_unavailable_process_census_still_reaps_child(tmp_path, monkeypatch):
    monkeypatch.setattr(bounded_subprocess.sys, "platform", "linux")
    real_popen = subprocess.Popen
    children = []

    def capture(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    def unavailable(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(bounded_subprocess.subprocess, "Popen", capture)
    monkeypatch.setattr(bounded_subprocess.subprocess, "run", unavailable)
    with pytest.raises(BoundedSubprocessError, match="unavailable") as raised:
        run_bounded_subprocess(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=tmp_path,
            timeout_seconds=5,
            stdout_ceiling=1024,
            stderr_ceiling=1024,
            rss_ceiling=512 * 1024 * 1024,
        )
    assert len(children) == 1 and children[0].poll() is not None
    assert raised.value.stage == "rss_census"


def test_unsupported_platform_fails_closed_before_process_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bounded_subprocess,
        "_supports_posix_process_groups",
        lambda: False,
    )
    monkeypatch.setattr(
        bounded_subprocess.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("unsupported platforms must not spawn"),
    )

    with pytest.raises(BoundedSubprocessError, match="unavailable") as raised:
        run_bounded_subprocess(
            [sys.executable, "-c", "pass"],
            cwd=tmp_path,
            timeout_seconds=1,
            stdout_ceiling=1024,
            stderr_ceiling=1024,
        )

    assert raised.value.kind == "unavailable"


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


def test_rss_ceiling_terminates_process_group(tmp_path: Path) -> None:
    with pytest.raises(BoundedSubprocessError, match="resource") as raised:
        run_bounded_subprocess(
            [sys.executable, "-c", "import time; payload=bytearray(32*1024*1024); time.sleep(10)"],
            cwd=tmp_path,
            timeout_seconds=5,
            stdout_ceiling=1024,
            stderr_ceiling=1024,
            rss_ceiling=8 * 1024 * 1024,
        )
    assert raised.value.kind == "resource"


def test_cpu_limit_is_applied_to_child(tmp_path: Path) -> None:
    result = run_bounded_subprocess(
        [sys.executable, "-c", "while True: pass"],
        cwd=tmp_path,
        # RLIMIT_CPU counts scheduled CPU time, not elapsed wall time. Leave a
        # finite runway for a child competing with the parallel hosted suite.
        timeout_seconds=20,
        stdout_ceiling=1024,
        stderr_ceiling=1024,
        cpu_seconds=1,
    )
    assert result.returncode in {-signal.SIGKILL, -signal.SIGXCPU}


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
            timeout_seconds=5,
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


def test_exited_wrapper_census_kills_detached_pipe_free_descendant(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "detached-child.pid"
    script = (
        "import subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(str(child.pid))\n"
    )
    with pytest.raises(BoundedSubprocessError, match="descendants") as raised:
        run_bounded_subprocess(
            [sys.executable, "-c", script, str(child_pid_path)],
            cwd=tmp_path,
            timeout_seconds=5,
            stdout_ceiling=1024,
            stderr_ceiling=1024,
        )
    assert raised.value.kind == "descendants"
    child_pid = int(child_pid_path.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("post-run process census left a detached descendant alive")


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


@pytest.mark.parametrize(
    "stream_failure",
    [
        KeyboardInterrupt("injected interrupt"),
        RuntimeError("injected stream failure"),
    ],
)
def test_unexpected_stream_failure_terminates_and_reaps_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stream_failure: BaseException,
) -> None:
    created: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def fail_read(_descriptor: int, _size: int) -> bytes:
        raise stream_failure

    def capture_process(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        created.append(process)
        monkeypatch.setattr(bounded_subprocess.os, "read", fail_read)
        return process

    monkeypatch.setattr(bounded_subprocess.subprocess, "Popen", capture_process)

    with pytest.raises(type(stream_failure), match=str(stream_failure)):
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

    assert len(created) == 1
    process = created[0]
    assert process.poll() is not None
    assert process.wait(timeout=0) == process.returncode
    with pytest.raises(ProcessLookupError):
        os.killpg(process.pid, 0)


def test_cleanup_failures_preserve_original_interrupt_and_still_reap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[subprocess.Popen[bytes]] = []
    calls = {
        "kill": 0,
        "poll": 0,
        "selector_close": 0,
        "stream_close": 0,
        "terminate": 0,
        "wait": 0,
    }
    real_popen = subprocess.Popen
    real_selector = bounded_subprocess.selectors.DefaultSelector

    class RaisingCloseSelector:
        def __init__(self) -> None:
            self.inner = real_selector()

        def __getattr__(self, name: str):
            return getattr(self.inner, name)

        def close(self) -> None:
            calls["selector_close"] += 1
            self.inner.close()
            raise RuntimeError("injected selector close failure")

    class RaisingCloseStream:
        def __init__(self, stream) -> None:
            self.stream = stream

        def fileno(self) -> int:
            return self.stream.fileno()

        def close(self) -> None:
            calls["stream_close"] += 1
            self.stream.close()
            raise RuntimeError("injected stream close failure")

    def fail_read(_descriptor: int, _size: int) -> bytes:
        raise KeyboardInterrupt("original interrupt")

    def capture_process(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        created.append(process)
        assert process.stdout is not None
        assert process.stderr is not None
        process.stdout = RaisingCloseStream(process.stdout)
        process.stderr = RaisingCloseStream(process.stderr)
        real_poll = process.poll
        real_wait = process.wait

        def flaky_poll():
            calls["poll"] += 1
            if calls["poll"] == 1:
                raise RuntimeError("injected poll failure")
            return real_poll()

        def flaky_wait(*args, **kwargs):
            calls["wait"] += 1
            if calls["wait"] == 1:
                raise RuntimeError("injected wait failure")
            return real_wait(*args, **kwargs)

        def flaky_terminate():
            calls["terminate"] += 1
            raise RuntimeError("injected terminate failure")

        def flaky_kill():
            calls["kill"] += 1
            raise RuntimeError("injected kill failure")

        process.poll = flaky_poll
        process.wait = flaky_wait
        process.terminate = flaky_terminate
        process.kill = flaky_kill
        monkeypatch.setattr(bounded_subprocess.os, "read", fail_read)
        return process

    monkeypatch.setattr(
        bounded_subprocess.selectors,
        "DefaultSelector",
        RaisingCloseSelector,
    )
    monkeypatch.setattr(bounded_subprocess.subprocess, "Popen", capture_process)

    with pytest.raises(KeyboardInterrupt, match="original interrupt"):
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

    assert len(created) == 1
    process = created[0]
    assert calls == {
        "kill": 1,
        "poll": 1,
        "selector_close": 1,
        "stream_close": 2,
        "terminate": 1,
        "wait": 2,
    }
    assert process.returncode is not None
    assert process.wait(timeout=0) == process.returncode
    with pytest.raises(ProcessLookupError):
        os.killpg(process.pid, 0)
