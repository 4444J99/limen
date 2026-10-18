"""`limen knowledge` — the advertised form of the knowledge archive front door, a pure delegate.

The script tests run against a throwaway copy of the repo layout: its own corpora registry, its own
store, and a stand-in `cce` that only serves two pages. They never read the real private archive.

The contract under test (scripts/open-knowledge.sh):
  C1 --stop and --status never need the built archive manifest.
  C2 Identity is protocol: a listener is the archive server only if GET /api/ping answers 200 with
     "ok": true, and a recorded pid is trusted only if it names `archive serve` on this exact port.
  C3 A start that times out reaps its own child and removes the pid file.
  C4 Starts are serialized per port by an atomic lock directory that stale holders cannot wedge.
  C5 The browser step comes after readiness and never fails the door.
  C6 --status binds the receipt to the live fingerprint.
  C7 Portable to bash 3.2 and bash 5.  C8 Loopback probes ignore a user ~/.curlrc.
  C9 Strict mode stays, --help prints the whole header, one new environment variable.
"""

import contextlib
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from click.testing import CliRunner

from limen.cli import main

SCRIPT = ROOT / "scripts" / "open-knowledge.sh"
FINGERPRINT = "ab" * 32
BOUND_HEX = hashlib.sha256(FINGERPRINT.encode("utf-8")).hexdigest()[:16]
FOREIGN_RECEIPTS = (
    "receipt-knowledge-alive-1111111111111111-20261001.json",
    "receipt-knowledge-alive-2222222222222222-20261017.json",
)
TIMEOUT_VARIABLE = "OPEN_KNOWLEDGE_START_TIMEOUT_SECONDS"
ARCHIVE_NOT_BUILT = "not built on this host — run cce archive build (see docs/architecture/ai-exports-archive.md)"
NOT_THE_ARCHIVE = "is held by something that is not the archive server"

# A stand-in for the engine's `cce archive serve`: it records what it was given, appends "<pid> <port>"
# to the launch log, and answers the engine's own liveness contract on /api/ping.
FAKE_ENGINE = """#!@PY@
import http.server
import json
import os
import sys
import time

arguments = sys.argv[1:]
port = int(arguments[arguments.index("--port") + 1])
with open(os.environ["FAKE_ENGINE_RECORD"], "w", encoding="utf-8") as record:
    json.dump(
        {"arguments": arguments, "legacy_store_variable_set": "CCE_CORPUS_STORE_ROOT" in os.environ},
        record,
    )
with open(os.environ["FAKE_ENGINE_LAUNCHES"], "a", encoding="utf-8") as launches:
    launches.write(f"{os.getpid()} {port}\\n")
time.sleep(float(os.environ.get("FAKE_ENGINE_BIND_DELAY", "0")))
ping_body = os.environ.get("FAKE_ENGINE_PING_BODY", '{"ok": true}').encode("utf-8")


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/ping":
            body, kind = ping_body, "application/json"
        else:
            body, kind = b"archive", "text/plain"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


http.server.HTTPServer(("127.0.0.1", port), Page).serve_forever()
"""

# An engine that never answers: it logs its launch, optionally ignores SIGTERM, and sleeps.
SILENT_ENGINE = """#!@PY@
import os
import signal
import sys
import time

arguments = sys.argv[1:]
port = arguments[arguments.index("--port") + 1]
if os.environ.get("FAKE_ENGINE_IGNORE_TERM") == "1":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
with open(os.environ["FAKE_ENGINE_LAUNCHES"], "a", encoding="utf-8") as launches:
    launches.write(f"{os.getpid()} {port}\\n")
time.sleep(120)
"""

# Somebody else's server on the port: 200 on every page, but no archive ping.
FOREIGN_SERVER = """#!@PY@
import http.server
import sys

port = int(sys.argv[1])
mode = sys.argv[2]


class Page(http.server.BaseHTTPRequestHandler):
    def reply(self, status, kind, body):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/ping":
            if mode == "ping-false":
                self.reply(200, "application/json", b'{"ok": false}')
            else:
                self.reply(404, "text/plain", b"not found")
        else:
            self.reply(200, "text/plain", b"somebody else's page")

    def log_message(self, format, *args):
        pass


http.server.HTTPServer(("127.0.0.1", port), Page).serve_forever()
"""

# A stand-in `open` that records when it ran, whether the archive already answered, and then fails.
FAKE_OPEN = """#!@PY@
import json
import os
import sys
import urllib.request

answered = False
if len(sys.argv) > 1 and sys.argv[1].startswith("http://"):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(sys.argv[1] + "api/ping", timeout=2) as response:
            answered = response.status == 200
    except OSError:
        answered = False
with open(os.environ["FAKE_OPEN_RECORD"], "a", encoding="utf-8") as record:
    record.write(json.dumps({"arguments": sys.argv[1:], "answered": answered}) + "\\n")
sys.exit(1)
"""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def answers(port: int) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def label(name: str) -> str:
    """The status block's left column: two spaces, the name and a colon, padded to sixteen."""
    return f"  {name}:".ljust(16)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_dead(pid: int, seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return not alive(pid)


def command_of(pid: int) -> str:
    done = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False)
    return done.stdout.strip()


def stop_pid(pid: int) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not alive(pid):
            return
        with contextlib.suppress(OSError):
            os.kill(pid, sig)
        wait_dead(pid, 1.0)


def header_lines(text: str) -> list[str]:
    """The script's leading comment block: every `#` line after the shebang up to the first other line."""
    lines = []
    for line in text.splitlines()[1:]:
        if not line.startswith("#"):
            break
        lines.append(line)
    return lines


def executable(path: Path, template: str) -> Path:
    path.write_text(template.replace("@PY@", sys.executable))
    path.chmod(0o755)
    return path


@pytest.fixture
def layout(tmp_path):
    """A repo copy holding only the script, the resolver and a registry, plus a built store.

    Every process a test starts is reaped in the finalizer, even when an assertion failed."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "institutio" / "governance").mkdir(parents=True)
    (repo / "docs" / "receipts").mkdir(parents=True)
    for name in ("open-knowledge.sh", "corpus_resolve.py"):
        (repo / "scripts" / name).write_text((ROOT / "scripts" / name).read_text())
    store = tmp_path / "store"
    (store / "archive-all").mkdir(parents=True)
    (repo / "institutio" / "governance" / "corpora.yaml").write_text(
        f'stores:\n  test-archive:\n    root: "{store}"\ncorpora:\n  archive-all:\n    store: test-archive\n'
    )
    manifest = store / "archive-all" / "manifest-all.json"
    manifest.write_text(
        json.dumps({"source_fingerprint": FINGERPRINT, "totals": {"conversations": 7, "messages": 21, "words": 99}})
    )
    # Receipts that belong to some other fingerprint: one older and one newer than any bound receipt a test adds.
    for name in FOREIGN_RECEIPTS:
        (repo / "docs" / "receipts" / name).write_text("{}")

    binaries = tmp_path / "bin"
    binaries.mkdir()
    # A wrapper, not a symlink: a virtual environment's interpreter finds its packages from the path
    # it was started by, so a symlink elsewhere would lose PyYAML.
    interpreter = binaries / "python3"
    interpreter.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    interpreter.chmod(0o755)
    engine = executable(binaries / "cce", FAKE_ENGINE)

    launch_log = tmp_path / "engine-launches.txt"
    environment = {
        "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
        "HOME": os.environ["HOME"],
        "FAKE_ENGINE_RECORD": str(tmp_path / "engine-record.json"),
        "FAKE_ENGINE_LAUNCHES": str(launch_log),
        "CCE_CORPUS_STORE_ROOT": str(tmp_path / "legacy-store"),
    }
    port = free_port()
    state = store / "state"
    spawned: list[subprocess.Popen] = []

    def command(shell, on_port, arguments):
        return [shell, str(repo / "scripts" / "open-knowledge.sh"), "--port", str(on_port), *arguments]

    def run(*arguments, port=None, extra_env=None, shell="bash", timeout=60):
        return subprocess.run(
            command(shell, port or layout_port, arguments),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**environment, **(extra_env or {})},
            check=False,
            timeout=timeout,
        )

    def spawn(*arguments, port=None, extra_env=None):
        proc = subprocess.Popen(
            command("bash", port or layout_port, arguments),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**environment, **(extra_env or {})},
        )
        spawned.append(proc)
        return proc

    def launches():
        rows = []
        if launch_log.exists():
            for line in launch_log.read_text().splitlines():
                parts = line.split()
                if len(parts) == 2:
                    rows.append((int(parts[0]), parts[1]))
        return rows

    def serve_engine(on_port, extra_env=None):
        """An archive engine started directly, as if by an earlier session, answering before it returns."""
        proc = subprocess.Popen(
            [
                str(engine),
                "archive",
                "serve",
                "--project-root",
                str(store),
                "--corpus-store-root",
                str(store),
                "--archive-root",
                str(store / "archive-all"),
                "--port",
                str(on_port),
            ],
            env={**environment, **(extra_env or {})},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        spawned.append(proc)
        # Reap it the moment it dies: a killed child left as a zombie would still answer `kill -0`.
        threading.Thread(target=proc.wait, daemon=True).start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not answers(on_port):
            time.sleep(0.1)
        assert answers(on_port), "the stand-in engine never came up"
        return proc

    def serve_foreign(on_port, mode="no-ping"):
        proc = subprocess.Popen(
            [str(executable(binaries / "foreign-server", FOREIGN_SERVER)), str(on_port), mode],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        spawned.append(proc)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not answers(on_port):
            time.sleep(0.1)
        assert answers(on_port), "the foreign server never came up"
        return proc

    def hold(tag):
        """A live process whose command line carries `tag`, standing in for another invocation."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)", tag],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        spawned.append(proc)
        return proc

    def dead_pid():
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        return proc.pid

    def take_lock(on_port, pid):
        state.mkdir(parents=True, exist_ok=True)
        lock = state / f"open-knowledge-{on_port}.lock"
        lock.mkdir()
        (lock / "pid").write_text(f"{pid}\n")
        return lock

    layout_port = port
    try:
        yield {
            "repo": repo,
            "store": store,
            "state": state,
            "port": port,
            "run": run,
            "spawn": spawn,
            "record": tmp_path / "engine-record.json",
            "manifest": manifest,
            "receipts": repo / "docs" / "receipts",
            "binaries": binaries,
            "home": tmp_path / "home",
            "tmp": tmp_path,
            "launches": launches,
            "serve_engine": serve_engine,
            "serve_foreign": serve_foreign,
            "hold": hold,
            "dead_pid": dead_pid,
            "take_lock": take_lock,
            "pid_file": lambda on_port=port: state / f"open-knowledge-{on_port}.pid",
            "lock": lambda on_port=port: state / f"open-knowledge-{on_port}.lock",
            "log": lambda on_port=port: state / f"open-knowledge-{on_port}.log",
            "install_engine": lambda template: executable(engine, template),
            "environment": environment,
        }
    finally:
        for proc in spawned:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            for stream in (proc.stdout, proc.stderr):
                if stream:
                    stream.close()
        recorded = [pid for pid, _ in launches()]
        if state.exists():
            for pid_file in state.glob("open-knowledge-*.pid"):
                with contextlib.suppress(ValueError, OSError):
                    recorded.append(int(pid_file.read_text().strip()))
        for pid in recorded:
            # Only ever signal what is still our stand-in engine, never a recycled number.
            if alive(pid) and str(binaries / "cce") in command_of(pid):
                stop_pid(pid)


def test_knowledge_help_names_the_three_commands():
    result = CliRunner().invoke(main, ["knowledge", "--help"])
    assert result.exit_code == 0
    assert "--status" in result.output
    assert "--stop" in result.output
    assert "--no-open" in result.output
    assert "search" in result.output


def test_knowledge_is_a_pure_delegate_to_the_one_front_door():
    """The CLI must never grow its own serving logic — one script, one story. Pin the delegation:
    exactly one subprocess call, and its target is open-knowledge.sh."""
    src = (ROOT / "cli" / "src" / "limen" / "cli.py").read_text()
    body = src.split('@main.command("knowledge")', 1)[1].split("@main.command", 1)[0]
    assert body.count("subprocess.run") == 1, "the verb grew execution paths beyond the delegate"
    assert "open-knowledge.sh" in body
    assert "cce archive serve" not in body and "nohup" not in body, "the verb grew server logic of its own"


def test_knowledge_passes_every_flag_through_to_the_script(monkeypatch):
    calls = []

    def fake_run(args, **_):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = CliRunner().invoke(main, ["knowledge", "--status", "--stop", "--port", "8500", "--no-open"])
    assert result.exit_code == 0
    (args,) = calls
    assert args[0] == "bash" and args[1].endswith("scripts/open-knowledge.sh")
    assert args[2:] == ["--status", "--stop", "--port", "8500", "--no-open"]


def test_script_refuses_with_one_line_when_the_archive_is_not_built(layout):
    layout["manifest"].unlink()
    result = layout["run"]("--no-open")
    assert result.returncode == 2
    assert result.stderr.strip() == (
        "the archive is not built on this host; run cce archive build — see docs/architecture/ai-exports-archive.md"
    )
    assert layout["launches"]() == []


def test_status_reports_fingerprint_and_totals_without_starting_anything(layout):
    result = layout["run"]("--status")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "server down" in result.stdout
    assert label("url") + f"http://127.0.0.1:{layout['port']}/" in result.stdout.splitlines()
    assert FINGERPRINT in result.stdout
    assert "7 conversations, 21 messages" in result.stdout
    assert not answers(layout["port"])
    assert layout["launches"]() == []


def test_front_door_starts_once_serves_the_site_and_stops(layout):
    first = layout["run"]("--no-open")
    assert first.returncode == 0, first.stdout + first.stderr
    assert f"http://127.0.0.1:{layout['port']}/" in first.stdout
    assert answers(layout["port"])
    assert not layout["lock"]().exists(), "the start lock outlived the start"

    record = json.loads(layout["record"].read_text())
    arguments = record["arguments"]
    store, archive = str(layout["store"]), str(layout["store"] / "archive-all")
    assert arguments[:2] == ["archive", "serve"]
    assert arguments[arguments.index("--project-root") + 1] == store
    assert arguments[arguments.index("--corpus-store-root") + 1] == store
    assert arguments[arguments.index("--archive-root") + 1] == archive
    assert record["legacy_store_variable_set"] is False, "the legacy store variable reached the engine"

    second = layout["run"]("--no-open")
    assert second.returncode == 0, second.stdout + second.stderr
    assert "already up" in second.stdout
    assert len(layout["launches"]()) == 1

    status = layout["run"]("--status")
    assert "server up" in status.stdout

    stopped = layout["run"]("--stop")
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert "stopped" in stopped.stdout
    assert not answers(layout["port"])


def test_front_door_refuses_a_port_held_by_something_else(layout):
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", layout["port"]))
        holder.listen()
        result = layout["run"]("--no-open")
    assert result.returncode == 1
    assert "not the archive server" in result.stderr
    assert not layout["record"].exists(), "the engine was started on a held port"
    assert not layout["lock"]().exists(), "the start lock outlived a refused start"


# --- C1: stop and status never need the built archive ---------------------------------------------


def test_stop_with_no_manifest_and_nothing_running_says_so_and_exits_zero(layout):
    layout["manifest"].unlink()
    result = layout["run"]("--stop")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"no server of ours on port {layout['port']} — nothing to stop" in result.stdout
    assert layout["launches"]() == []


def test_status_with_no_manifest_reports_server_url_and_an_unbuilt_archive(layout):
    layout["manifest"].unlink()
    port = layout["port"]
    result = layout["run"]("--status")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert f"server down on port {port}" in result.stdout
    assert label("url") + f"http://127.0.0.1:{port}/" in lines
    assert label("archive") + ARCHIVE_NOT_BUILT in lines
    for absent in ("fingerprint", "vault", "receipt"):
        assert absent not in result.stdout, f"a manifest-less status printed a {absent} line"
    assert layout["launches"]() == []


def test_status_with_no_manifest_still_sees_the_running_server_and_its_pid(layout):
    started = layout["run"]("--no-open")
    assert started.returncode == 0, started.stdout + started.stderr
    layout["manifest"].unlink()
    result = layout["run"]("--status")
    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(rf"server up on port {layout['port']} \(pid \d+\)", result.stdout), result.stdout
    assert label("archive") + ARCHIVE_NOT_BUILT in result.stdout.splitlines()


def test_stop_reaches_a_running_server_after_the_manifest_disappears(layout):
    port = layout["port"]
    started = layout["run"]("--no-open")
    assert started.returncode == 0, started.stdout + started.stderr
    assert answers(port)
    layout["manifest"].unlink()

    stopped = layout["run"]("--stop")
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert re.search(rf"stopped the server on port {port} \(pid \d+\)", stopped.stdout), stopped.stdout
    assert not answers(port)
    assert not layout["pid_file"]().exists()


@pytest.mark.parametrize("flag", ["--stop", "--status"])
def test_stop_and_status_still_refuse_a_registry_without_the_archive_row(layout, flag):
    registry = layout["repo"] / "institutio" / "governance" / "corpora.yaml"
    registry.write_text(
        f'stores:\n  test-archive:\n    root: "{layout["store"]}"\ncorpora:\n  other:\n    store: test-archive\n'
    )
    result = layout["run"](flag)
    assert result.returncode == 2
    assert "corpora.yaml does not declare the archive-all corpus with a store" in result.stderr


# --- C2: identity is protocol ---------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["no-ping", "ping-false"])
def test_start_refuses_a_listener_that_answers_on_root_but_not_on_ping(layout, mode):
    port = layout["port"]
    foreign = layout["serve_foreign"](port, mode)
    result = layout["run"]("--no-open")
    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        f"open-knowledge: port {port} is held by something that is not the archive server — pick another with --port"
        in result.stderr.splitlines()
    )
    assert layout["launches"]() == [], "an engine was launched onto a foreign listener"
    assert foreign.poll() is None
    assert not layout["lock"]().exists(), "the start lock outlived a refused start"


def test_status_reports_a_foreign_listener_as_down_with_a_note(layout):
    port = layout["port"]
    layout["serve_foreign"](port)
    result = layout["run"]("--status")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"server down on port {port}" in result.stdout
    assert "server up" not in result.stdout
    assert label("note") + f"port {port} {NOT_THE_ARCHIVE}" in result.stdout.splitlines()


@pytest.mark.parametrize("with_manifest", [True, False], ids=["manifest-present", "manifest-absent"])
def test_stop_signals_nothing_on_a_foreign_listener(layout, with_manifest):
    port = layout["port"]
    if not with_manifest:
        layout["manifest"].unlink()
    foreign = layout["serve_foreign"](port)
    # A stale pid file that happens to name the foreign process must not make it ours.
    layout["state"].mkdir(parents=True, exist_ok=True)
    layout["pid_file"]().write_text(f"{foreign.pid}\n")

    result = layout["run"]("--stop")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "stopped the server" not in result.stdout
    assert "nothing to stop" in result.stdout or "nothing stopped" in result.stdout
    assert foreign.poll() is None, "--stop signalled a process this script did not start"
    assert answers(port)
    assert not layout["pid_file"]().exists(), "the stale pid file was kept"


def test_a_pid_file_for_one_port_naming_an_engine_on_another_is_not_trusted(layout):
    port_a, port_b = layout["port"], free_port()
    engine_b = layout["serve_engine"](port_b)
    layout["state"].mkdir(parents=True, exist_ok=True)
    layout["pid_file"](port_a).write_text(f"{engine_b.pid}\n")

    result = layout["run"]("--stop")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"no server of ours on port {port_a} — nothing to stop" in result.stdout
    assert engine_b.poll() is None, "--stop killed the engine serving a different port"
    assert answers(port_b)
    assert not layout["pid_file"](port_a).exists(), "the untrusted pid file was kept"


def test_a_dead_pid_in_the_pid_file_is_cleared_without_signalling_anything(layout):
    layout["state"].mkdir(parents=True, exist_ok=True)
    layout["pid_file"]().write_text(f"{layout['dead_pid']()}\n")
    result = layout["run"]("--stop")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"no server of ours on port {layout['port']} — nothing to stop" in result.stdout
    assert not layout["pid_file"]().exists()


def test_a_compact_ping_body_still_counts_as_the_archive_server(layout):
    engine = layout["serve_engine"](layout["port"], {"FAKE_ENGINE_PING_BODY": '{"ok":true}'})
    result = layout["run"]("--no-open")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"server already up on port {layout['port']}" in result.stdout
    assert [pid for pid, _ in layout["launches"]()] == [engine.pid], "a second engine was launched"


# --- C3: a start that times out reaps its own child -----------------------------------------------


def test_a_start_that_times_out_leaves_no_live_child_and_no_pid_file(layout):
    """The engine ignores SIGTERM, so only the SIGKILL escalation can leave no live child."""
    port = layout["port"]
    layout["install_engine"](SILENT_ENGINE)
    result = layout["run"](
        "--no-open",
        extra_env={TIMEOUT_VARIABLE: "2", "FAKE_ENGINE_IGNORE_TERM": "1"},
        timeout=40,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"open-knowledge: no answer on port {port} after 2 seconds; see {layout['log']()}" in (
        result.stderr.splitlines()
    )
    launched = layout["launches"]()
    assert len(launched) == 1, "the silent engine was never launched, so the timeout was not exercised"
    assert wait_dead(launched[0][0]), "the timed-out start left its engine running"
    assert not layout["pid_file"]().exists()
    assert not layout["lock"]().exists(), "the start lock outlived a timed-out start"


@pytest.mark.parametrize("value", ["0", "abc"])
def test_a_start_timeout_that_is_not_a_positive_integer_is_ignored(layout, value):
    result = layout["run"]("--no-open", extra_env={TIMEOUT_VARIABLE: value})
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"server started on port {layout['port']}" in result.stdout
    assert answers(layout["port"])


# --- C4: starts are serialized per port -----------------------------------------------------------


def test_two_concurrent_starts_launch_exactly_one_engine(layout):
    port = layout["port"]
    # A slow-binding engine widens the window in which an unserialized second start would also launch.
    slow = {"FAKE_ENGINE_BIND_DELAY": "1.0"}
    first = layout["spawn"]("--no-open", extra_env=slow)
    second = layout["spawn"]("--no-open", extra_env=slow)
    outputs = [proc.communicate(timeout=60) for proc in (first, second)]

    assert [first.returncode, second.returncode] == [0, 0], outputs
    assert len(layout["launches"]()) == 1, "two starts launched two engines"
    stdout = "\n".join(out for out, _ in outputs)
    assert stdout.count(f"server started on port {port}") == 1
    assert stdout.count(f"server already up on port {port}") == 1
    assert answers(port)
    assert not layout["lock"]().exists(), "the start lock outlived both starts"


def test_a_stale_start_lock_with_a_dead_holder_is_recovered(layout):
    lock = layout["take_lock"](layout["port"], layout["dead_pid"]())
    result = layout["run"]("--no-open")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(layout["launches"]()) == 1
    assert answers(layout["port"])
    assert not lock.exists(), "the recovered lock was never released"


def test_a_start_lock_whose_holder_is_an_unrelated_live_process_is_recovered(layout):
    stranger = layout["hold"]("unrelated-process")
    lock = layout["take_lock"](layout["port"], stranger.pid)
    result = layout["run"]("--no-open")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(layout["launches"]()) == 1
    assert not lock.exists(), "the recovered lock was never released"
    assert stranger.poll() is None, "the recovery signalled the unrelated process that recycled the pid"


def test_a_start_waiting_on_a_held_lock_joins_the_server_that_comes_up(layout):
    port = layout["port"]
    holder = layout["hold"]("open-knowledge-holder")
    lock = layout["take_lock"](port, holder.pid)
    waiter = layout["spawn"]("--no-open")
    time.sleep(1.0)
    engine = layout["serve_engine"](port)
    out, err = waiter.communicate(timeout=30)

    assert waiter.returncode == 0, out + err
    assert f"server already up on port {port}" in out
    assert f"http://127.0.0.1:{port}/" in out
    assert [launched for launched, _ in layout["launches"]()] == [engine.pid], "the waiter launched its own engine"
    assert (lock / "pid").read_text().strip() == str(holder.pid), "the waiter disturbed a lock it did not own"


def test_a_start_gives_up_after_fifteen_seconds_behind_a_live_holder(layout):
    port = layout["port"]
    holder = layout["hold"]("open-knowledge-holder")
    lock = layout["take_lock"](port, holder.pid)
    began = time.monotonic()
    result = layout["run"]("--no-open", timeout=45)
    elapsed = time.monotonic() - began

    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        f"open-knowledge: another start on port {port} did not finish within 15 seconds (lock {lock})"
        in result.stderr.splitlines()
    )
    assert 13 <= elapsed < 30, f"gave up after {elapsed:.1f}s"
    assert layout["launches"]() == []
    assert (lock / "pid").read_text().strip() == str(holder.pid), "the loser released a lock it did not own"


@pytest.mark.parametrize("flag", ["--stop", "--status"])
def test_stop_and_status_never_block_on_the_start_lock(layout, flag):
    holder = layout["hold"]("open-knowledge-holder")
    lock = layout["take_lock"](layout["port"], holder.pid)
    result = layout["run"](flag, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert lock.exists() and (lock / "pid").read_text().strip() == str(holder.pid)


# --- C5: the browser step stays after readiness and never fails the door ---------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="the browser step only runs on macOS, where `open` exists")
def test_the_browser_opens_only_after_readiness_and_its_failure_never_fails_the_door(layout):
    record = layout["tmp"] / "open-record.jsonl"
    executable(layout["binaries"] / "open", FAKE_OPEN)
    result = layout["run"](extra_env={"FAKE_OPEN_RECORD": str(record)})
    url = f"http://127.0.0.1:{layout['port']}/"
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"server started on port {layout['port']}" in result.stdout
    assert f"open-knowledge: {url}" in result.stdout
    assert "could not open the browser" in result.stderr
    calls = [json.loads(line) for line in record.read_text().splitlines()]
    assert calls == [{"arguments": [url], "answered": True}], calls


# --- C6: status binds the receipt to the live fingerprint ------------------------------------------


def test_status_binds_the_receipt_to_the_live_fingerprint(layout):
    bound_old = f"receipt-knowledge-alive-{BOUND_HEX}-20260915.json"
    bound_new = f"receipt-knowledge-alive-{BOUND_HEX}-20261005.json"
    for name in (bound_old, bound_new):
        (layout["receipts"] / name).write_text("{}")
    result = layout["run"]("--status")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    # The foreign receipt dated 20261017 is the newest file on disk, but it is not this archive's.
    assert label("receipt") + bound_new in lines
    for other in (bound_old, *FOREIGN_RECEIPTS):
        assert other not in result.stdout


def test_status_marks_receipts_for_some_other_fingerprint_as_stale(layout):
    result = layout["run"]("--status")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        label("receipt")
        + f"none for the current fingerprint (newest on disk: {FOREIGN_RECEIPTS[1]}, stale)"
        + " — run check-knowledge-alive.py --live --write-receipt"
        in result.stdout.splitlines()
    )


def test_status_without_any_receipt_says_none_yet(layout):
    for name in FOREIGN_RECEIPTS:
        (layout["receipts"] / name).unlink()
    result = layout["run"]("--status")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        label("receipt") + "none yet — run check-knowledge-alive.py --live --write-receipt"
        in result.stdout.splitlines()
    )


# --- C7: portability -------------------------------------------------------------------------------

BASH_CANDIDATES = ("/bin/bash", "/opt/homebrew/bin/bash", "/usr/local/bin/bash")
FORBIDDEN_CONSTRUCTS = {
    "associative array": r"\b(declare|typeset|local)\s+-[A-Za-z]*A",
    "mapfile or readarray": r"\b(mapfile|readarray)\b",
    "case-changing expansion": r"\$\{[A-Za-z_][A-Za-z0-9_]*(,,?|\^\^?)",
    "wait -n": r"\bwait\s+-[A-Za-z]*n",
    "nameref": r"\b(declare|typeset|local)\s+-[A-Za-z]*n",
    "GNU stat -c": r"\bstat\s+-c\b",
    "GNU date -d": r"\bdate\s+-d\b",
    "readlink -f": r"\breadlink\s+-f\b",
    "quoted regex operand": r"=~\s*[\"']",
}


def test_the_script_uses_no_construct_that_bash_3_2_or_macos_tools_lack():
    code = [line for line in SCRIPT.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")]
    for name, pattern in FORBIDDEN_CONSTRUCTS.items():
        hits = [line.strip() for line in code if re.search(pattern, line)]
        assert not hits, f"{name} is not portable to bash 3.2 / macOS: {hits}"


@pytest.mark.parametrize(
    "shell",
    [
        pytest.param(path, marks=pytest.mark.skipif(not os.path.exists(path), reason=f"{path} is not installed here"))
        for path in BASH_CANDIDATES
    ],
)
def test_the_whole_lifecycle_runs_under_each_installed_bash(layout, shell):
    parse = subprocess.run([shell, "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert parse.returncode == 0, parse.stderr

    port = layout["port"]
    results = {}
    results["start"] = layout["run"]("--no-open", shell=shell)
    results["again"] = layout["run"]("--no-open", shell=shell)
    results["status"] = layout["run"]("--status", shell=shell)
    layout["manifest"].unlink()
    results["status-bare"] = layout["run"]("--status", shell=shell)
    results["stop"] = layout["run"]("--stop", shell=shell)
    results["stop-again"] = layout["run"]("--stop", shell=shell)

    for step, result in results.items():
        assert result.returncode == 0, f"{step}: {result.stdout}{result.stderr}"
        for broken in ("unbound variable", "syntax error", "bad substitution", "command not found", "illegal option"):
            assert broken not in result.stderr, f"{step} under {shell}: {result.stderr}"
    assert f"server started on port {port}" in results["start"].stdout
    assert "already up" in results["again"].stdout
    assert "server up" in results["status"].stdout
    assert label("archive") + ARCHIVE_NOT_BUILT in results["status-bare"].stdout.splitlines()
    assert "stopped the server" in results["stop"].stdout
    assert "nothing to stop" in results["stop-again"].stdout
    assert not answers(port)


# --- C8: loopback probes ignore a user ~/.curlrc ---------------------------------------------------


def test_probes_ignore_a_user_curlrc_that_breaks_plain_curl(layout):
    port = layout["port"]
    engine = layout["serve_engine"](port)
    layout["home"].mkdir()
    (layout["home"] / ".curlrc").write_text("http2-prior-knowledge\n")
    broken_home = {"HOME": str(layout["home"])}

    status = layout["run"]("--status", extra_env=broken_home)
    assert status.returncode == 0, status.stdout + status.stderr
    assert f"server up on port {port}" in status.stdout, "a user curlrc made the live server read as down"

    again = layout["run"]("--no-open", extra_env=broken_home)
    assert again.returncode == 0, again.stdout + again.stderr
    assert f"server already up on port {port}" in again.stdout
    assert [pid for pid, _ in layout["launches"]()] == [engine.pid]


# --- C9: strict mode, the whole --help header, one new environment variable ------------------------


def test_help_prints_the_whole_header(layout):
    result = layout["run"]("--help")
    assert result.returncode == 0, result.stdout + result.stderr
    printed = {line.lstrip("#").strip() for line in result.stdout.splitlines()}
    header = header_lines(SCRIPT.read_text(encoding="utf-8"))
    assert header, "the script has no header comment"
    for line in header:
        content = line.lstrip("#").strip()
        assert not content or content in printed, f"--help dropped a header line: {content!r}"
    assert TIMEOUT_VARIABLE in result.stdout
    assert "set -euo pipefail" not in result.stdout, "--help printed code, not just the header"


def test_the_script_keeps_strict_mode_and_adds_only_the_one_environment_variable():
    text = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"^set -euo pipefail$", text, re.MULTILINE)
    assert set(re.findall(r"OPEN_KNOWLEDGE_[A-Z0-9_]+", text)) == {TIMEOUT_VARIABLE}
    assert "LIMEN_" not in text, "the parameter ratchet forbids a LIMEN_* parameter here"
