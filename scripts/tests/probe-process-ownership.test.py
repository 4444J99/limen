#!/usr/bin/env python3
"""Hermetic regressions for local probe process ownership and bounded cleanup."""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ProbeCase:
    name: str
    script_name: str
    port_variable: str


CASES = (
    ProbeCase("runtime", "probe-local-runtime.sh", "LIMEN_PROBE_PORT"),
    ProbeCase("worker", "probe-local-worker.sh", "LIMEN_WORKER_PROBE_PORT"),
)


def wait_for(predicate: Callable[[], bool], *, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def unused_port(excluded: set[int]) -> int:
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        if port not in excluded:
            excluded.add(port)
            return port


def port_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
            return True
    except OSError:
        return False


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def terminate_process_group(pgid: int) -> None:
    """Best-effort test cleanup that never targets the test runner's group."""
    if pgid == os.getpgrp() or not process_group_exists(pgid):
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, signal.SIGTERM)
    if wait_for(lambda: not process_group_exists(pgid), timeout=1.0):
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, signal.SIGKILL)
    wait_for(lambda: not process_group_exists(pgid), timeout=1.0)


def collect(process: subprocess.Popen[str], *, timeout: float = 10.0) -> str:
    """Collect output and always reap the wrapper, even when an assertion path times out."""
    try:
        output, _ = process.communicate(timeout=timeout)
        return output
    except subprocess.TimeoutExpired:
        terminate_process_group(process.pid)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            process.kill()
        output, _ = process.communicate(timeout=2)
        raise AssertionError(f"probe wrapper {process.pid} did not exit\n{output}")


def write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def prepare_fixture(fixture: Path) -> None:
    scripts = fixture / "scripts"
    worker_root = fixture / "web/worker"
    wrangler_cli = worker_root / "node_modules/wrangler/wrangler-dist/cli.js"
    scripts.mkdir(parents=True)
    (fixture / "web/api").mkdir(parents=True)
    (worker_root / "node_modules/yaml").mkdir(parents=True)
    wrangler_cli.parent.mkdir(parents=True)
    wrangler_cli.write_text("// fixture: the fake node executable handles this path\n")

    for case in CASES:
        shutil.copy2(ROOT / "scripts" / case.script_name, scripts / case.script_name)

    fake_server = fixture / "fake-server.py"
    write_executable(
        fake_server,
        """#!/usr/bin/env python3
import os
import signal
import socket
import sys
from pathlib import Path

port = int(sys.argv[sys.argv.index("--port") + 1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", port))
sock.listen()
sock.settimeout(0.2)
Path(os.environ["PROBE_TEST_PID_FILE"]).write_text(f"{os.getpid()} {os.getppid()}\\n")

def stop(_signum, _frame):
    if os.environ.get("PROBE_TEST_SERVER_MODE") == "ignore-term":
        return
    sock.close()
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
while True:
    try:
        connection, _ = sock.accept()
    except TimeoutError:
        continue
    connection.close()
""",
    )

    write_executable(
        scripts / "probe-runtime-adapter.py",
        """#!/usr/bin/env python3
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

mode = os.environ.get("PROBE_TEST_ADAPTER_MODE", "release")
if call_file := os.environ.get("PROBE_TEST_ADAPTER_CALL_FILE"):
    Path(call_file).write_text("called\\n")
if mode == "always-fail":
    raise SystemExit(1)
if mode == "release" and not Path(os.environ["PROBE_TEST_RELEASE_FILE"]).exists():
    raise SystemExit(1)
url = sys.argv[sys.argv.index("--api-url") + 1]
parsed = urlparse(url)
try:
    with socket.create_connection((parsed.hostname, parsed.port), timeout=0.2):
        pass
except OSError:
    raise SystemExit(1)
print("hermetic adapter probe passed")
""",
    )

    fake_bin = fixture / "bin"
    fake_bin.mkdir()
    write_executable(
        fake_bin / "python3",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-m" && "${2:-}" == "uvicorn" ]]; then
  shift 2
  exec "$REAL_PYTHON" "$FAKE_SERVER" "$@"
fi
exec "$REAL_PYTHON" "$@"
""",
    )
    write_executable(
        fake_bin / "node",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--no-warnings" ]]; then
  shift
fi
printf '%s\\n' "${1:-}" > "$PROBE_TEST_WRANGLER_CLI_FILE"
shift
exec "$REAL_PYTHON" "$FAKE_SERVER" "$@"
""",
    )


@dataclass
class RunningProbe:
    process: subprocess.Popen[str]
    server_pid: int
    temp_parent: Path
    release_file: Path
    cli_file: Path
    port: int


def start_case(
    fixture: Path,
    case: ProbeCase,
    port: int,
    *,
    adapter_mode: str = "release",
    server_mode: str = "cooperative",
    attempts: int = 200,
) -> RunningProbe:
    stem = f"{case.name}-{adapter_mode}-{server_mode}-{port}"
    pid_file = fixture / f"{stem}.pid"
    release_file = fixture / f"{stem}.release"
    cli_file = fixture / f"{stem}.cli"
    temp_parent = fixture / f"{stem}-tmp"
    temp_parent.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "FAKE_SERVER": str(fixture / "fake-server.py"),
            "PATH": f"{fixture / 'bin'}:{env['PATH']}",
            "PROBE_TEST_ADAPTER_MODE": adapter_mode,
            "PROBE_TEST_PID_FILE": str(pid_file),
            "PROBE_TEST_RELEASE_FILE": str(release_file),
            "PROBE_TEST_SERVER_MODE": server_mode,
            "PROBE_TEST_WRANGLER_CLI_FILE": str(cli_file),
            "REAL_PYTHON": sys.executable,
            "TMPDIR": str(temp_parent),
            "LIMEN_PROBE_ATTEMPTS": str(attempts),
            "LIMEN_PROBE_RETRY_DELAY": "0.02",
            "LIMEN_PROBE_TERM_GRACE": "0.15",
            case.port_variable: str(port),
        }
    )
    process = subprocess.Popen(
        ["bash", str(fixture / "scripts" / case.script_name)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )

    if not wait_for(lambda: pid_file.exists() and port_listening(port)):
        output = collect(process, timeout=1)
        raise AssertionError(f"{case.name}: fake server did not become ready\n{output}")

    server_pid, server_parent = (int(value) for value in pid_file.read_text().split())
    assert server_parent == process.pid, (
        f"{case.name}: server pid {server_pid} is owned by {server_parent}, not probe pid {process.pid}"
    )
    assert process_group_exists(server_pid), f"{case.name}: server group {server_pid} was not isolated"

    run_dirs = list(temp_parent.iterdir())
    assert len(run_dirs) == 1 and run_dirs[0].is_dir(), f"{case.name}: expected one private run dir: {run_dirs}"
    assert stat.S_IMODE(run_dirs[0].stat().st_mode) == 0o700, (
        f"{case.name}: run dir mode is {stat.S_IMODE(run_dirs[0].stat().st_mode):o}, not 700"
    )

    if case.name == "worker":
        assert cli_file.exists(), "worker: fake node did not record its CLI argument"
        assert cli_file.read_text().strip() == str(
            fixture / "web/worker/node_modules/wrangler/wrangler-dist/cli.js"
        ), "worker: probe did not invoke Wrangler's real CLI entrypoint"

    return RunningProbe(process, server_pid, temp_parent, release_file, cli_file, port)


def assert_reaped(run: RunningProbe, case: ProbeCase) -> None:
    assert wait_for(lambda: not process_exists(run.server_pid)), (
        f"{case.name}: server pid {run.server_pid} survived cleanup"
    )
    assert wait_for(lambda: not process_group_exists(run.server_pid)), (
        f"{case.name}: server group {run.server_pid} survived cleanup"
    )
    assert wait_for(lambda: not port_listening(run.port)), f"{case.name}: port {run.port} still accepts connections"
    assert not list(run.temp_parent.iterdir()), f"{case.name}: per-run temp state survived cleanup"


def finish_case(run: RunningProbe, case: ProbeCase, *, expected_returncode: int) -> str:
    try:
        output = collect(run.process)
        assert run.process.returncode == expected_returncode, (
            f"{case.name}: expected rc {expected_returncode}, got {run.process.returncode}\n{output}"
        )
        assert_reaped(run, case)
        return output
    finally:
        terminate_process_group(run.process.pid)
        if run.process.poll() is None:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                run.process.kill()
            run.process.wait(timeout=2)


def exercise_success(fixture: Path, case: ProbeCase, port: int) -> None:
    run = start_case(fixture, case, port)
    run.release_file.touch()
    output = finish_case(run, case, expected_returncode=0)
    assert "sending KILL" not in output, f"{case.name}: cooperative success escalated to KILL"


def exercise_failure(fixture: Path, case: ProbeCase, port: int) -> None:
    run = start_case(fixture, case, port, adapter_mode="always-fail", attempts=20)
    output = finish_case(run, case, expected_returncode=1)
    assert "sending KILL" not in output, f"{case.name}: cooperative failure escalated to KILL"


def exercise_signal(fixture: Path, case: ProbeCase, port: int) -> None:
    run = start_case(fixture, case, port, adapter_mode="always-fail")
    run.process.send_signal(signal.SIGTERM)
    output = finish_case(run, case, expected_returncode=143)
    assert "sending KILL" not in output, f"{case.name}: cooperative signal escalated to KILL"


def exercise_noncooperative(fixture: Path, case: ProbeCase, port: int) -> None:
    run = start_case(fixture, case, port, server_mode="ignore-term")
    run.release_file.touch()
    output = finish_case(run, case, expected_returncode=0)
    assert "did not exit after TERM; sending KILL" in output, f"{case.name}: KILL escalation was not exercised"


def exercise_occupied_port(fixture: Path, case: ProbeCase, port: int) -> None:
    stem = f"{case.name}-occupied-{port}"
    pid_file = fixture / f"{stem}.pid"
    release_file = fixture / f"{stem}.release"
    release_file.touch()
    call_file = fixture / f"{stem}.adapter-called"
    cli_file = fixture / f"{stem}.cli"
    temp_parent = fixture / f"{stem}-tmp"
    temp_parent.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "FAKE_SERVER": str(fixture / "fake-server.py"),
            "PATH": f"{fixture / 'bin'}:{env['PATH']}",
            "PROBE_TEST_ADAPTER_CALL_FILE": str(call_file),
            "PROBE_TEST_ADAPTER_MODE": "release",
            "PROBE_TEST_PID_FILE": str(pid_file),
            "PROBE_TEST_RELEASE_FILE": str(release_file),
            "PROBE_TEST_SERVER_MODE": "cooperative",
            "PROBE_TEST_WRANGLER_CLI_FILE": str(cli_file),
            "REAL_PYTHON": sys.executable,
            "TMPDIR": str(temp_parent),
            case.port_variable: str(port),
        }
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unrelated:
        unrelated.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        unrelated.bind(("127.0.0.1", port))
        unrelated.listen()
        process = subprocess.Popen(
            ["bash", str(fixture / "scripts" / case.script_name)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        try:
            output = collect(process, timeout=5)
            assert process.returncode == 1, (
                f"{case.name}: occupied port should fail, got {process.returncode}\\n{output}"
            )
            assert "already in use; refusing to probe an unrelated process" in output, (
                f"{case.name}: occupied-port refusal was not explicit\\n{output}"
            )
            assert not call_file.exists(), f"{case.name}: adapter ran against an unrelated listener"
            assert not pid_file.exists(), f"{case.name}: owned server started despite occupied port"
            assert port_listening(port), f"{case.name}: unrelated listener was disturbed"
            assert not list(temp_parent.iterdir()), f"{case.name}: occupied-port failure left temp residue"
        finally:
            terminate_process_group(process.pid)
            if process.poll() is None:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    process.kill()
                process.wait(timeout=2)


def main() -> int:
    used_ports: set[int] = set()
    with tempfile.TemporaryDirectory(prefix="limen-probe-ownership-") as raw_fixture:
        fixture = Path(raw_fixture)
        prepare_fixture(fixture)
        exercises = (
            ("success", exercise_success),
            ("failure", exercise_failure),
            ("signal", exercise_signal),
            ("noncooperative", exercise_noncooperative),
        )
        for case in CASES:
            for label, exercise in exercises:
                port = unused_port(used_ports)
                exercise(fixture, case, port)
                print(f"PASS {case.name}: {label} cleanup reaped listener on {port}")
            occupied_port = unused_port(used_ports)
            exercise_occupied_port(fixture, case, occupied_port)
            print(f"PASS {case.name}: occupied port {occupied_port} was rejected without probing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
