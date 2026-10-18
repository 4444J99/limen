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
  C10 A dead start lock (its pid is gone, a zombie or not this script, or it has no pid and its directory
      is at least 3 seconds old) is removed only by the holder of the <lock>.reap recovery mutex, after
      re-checking; a release removes the lock only while its pid file is absent, empty or its own.
  C11 The lock wait bound is max(15, start timeout + 5) seconds.
  C12 --stop: a failed signal to an exited server clears the pid file and exits 0; to a live one exits 1;
      a pid file that now names a newer start survives a successful stop.
  C13 A state directory that cannot be created or written fails at once.
  C14 curl is required: exit 127 before any probe.  C15 --port is a plain decimal from 1 to 65535.
  C16 The header names every changed behavior.
"""

import contextlib
import hashlib
import json
import os
import re
import shutil
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
import signal
import sys
import time

arguments = sys.argv[1:]
port = int(arguments[arguments.index("--port") + 1])


def on_term(signum, frame):
    # A newer start may have rewritten the pid file by the time this server dies: say so.
    with open(os.environ["FAKE_ENGINE_ON_TERM_FILE"], "w", encoding="utf-8") as pid_file:
        pid_file.write(os.environ["FAKE_ENGINE_ON_TERM_TEXT"])
    os._exit(0)


if "FAKE_ENGINE_ON_TERM_FILE" in os.environ:
    signal.signal(signal.SIGTERM, on_term)
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


# Every tool the script runs outside its own interpreter, bar curl, python and the engine.
TOOLS_THE_SCRIPT_RUNS = "bash sh env dirname git cat ps sleep mkdir rm tail nohup uname awk".split()

# A stand-in `curl` that counts every probe the script makes, then runs the real one: the observable
# proof that a start is inside its lock-polling loop.
CURL_LOGGER = """#!/bin/sh
echo probe >>"@LOG@"
exec "@REAL@" "$@"
"""

# A stand-in `ps` that lists one pid as an archive server for its first @LISTED@ lookups, then reports it
# gone (or, with a large @LISTED@, never gone). Every other lookup goes to the real ps.
PS_SHIM = """#!/bin/sh
wanted=""
previous=""
for argument in "$@"; do
  if [ "$previous" = "-p" ]; then wanted="$argument"; fi
  previous="$argument"
done
if [ "$wanted" = "@PID@" ]; then
  calls=$(cat "@COUNT@" 2>/dev/null || echo 0)
  calls=$((calls + 1))
  echo "$calls" >"@COUNT@"
  if [ "$calls" -le @LISTED@ ]; then
    echo "@COMMAND@"
    exit 0
  fi
  exit 1
fi
exec "@REAL@" "$@"
"""


# A stand-in for procps `ps`, which cuts output that is not going to a terminal at the terminal width (80
# columns under TERM=dumb) unless it is given -ww. Here the width is COLUMNS, or 40, and -ww passes through.
NARROW_PS_SHIM = """#!/bin/sh
for argument in "$@"; do
  if [ "$argument" = "-ww" ]; then exec "@REAL@" "$@"; fi
done
"@REAL@" "$@" | cut -c1-"${COLUMNS:-40}"
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


def process_state(pid: int) -> str:
    """The process state letters from ps, empty when no such process is listed."""
    done = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, check=False)
    return done.stdout.strip()


def alive(pid: int) -> bool:
    """Running, as ps sees it: a zombie is dead (kill -0 would still answer for it)."""
    state = process_state(pid)
    return bool(state) and not state.startswith("Z")


def wait_until(condition, seconds: float = 10.0, reason: str = "the condition") -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    pytest.fail(f"timed out after {seconds}s waiting for {reason}")


def wait_dead(pid: int, seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return not alive(pid)


def command_of(pid: int) -> str:
    # -ww: procps ps cuts output that is not going to a terminal at the terminal width without it.
    done = subprocess.run(["ps", "-ww", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False)
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

    def take_lock(on_port, pid=None):
        """The start lock as a holder leaves it; with no pid, as one killed before it wrote its pid."""
        state.mkdir(parents=True, exist_ok=True)
        lock = state / f"open-knowledge-{on_port}.lock"
        lock.mkdir()
        if pid is not None:
            (lock / "pid").write_text(f"{pid}\n")
        return lock

    def zombie():
        """A child that has exited and is not reaped, so ps lists it as a zombie until the finalizer waits."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass", "open-knowledge-zombie"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        spawned.append(proc)
        wait_until(lambda: process_state(proc.pid).startswith("Z"), reason="the child to become a zombie")
        return proc

    def watch_curl():
        """Count every curl probe the script makes; the count rises only while a start is polling."""
        log = tmp_path / "curl-probes.txt"
        real = shutil.which("curl", path=os.environ["PATH"])
        assert real, "these tests need curl"
        shim = binaries / "curl"
        shim.write_text(CURL_LOGGER.replace("@LOG@", str(log)).replace("@REAL@", real))
        shim.chmod(0o755)
        return lambda: len(log.read_text().splitlines()) if log.exists() else 0

    def fake_ps(pid, listed_lookups):
        """Make ps list `pid` as the archive server on this port for its first `listed_lookups` lookups."""
        real = shutil.which("ps", path=os.environ["PATH"])
        assert real, "these tests need ps"
        command = f"{binaries / 'cce'} archive serve --project-root {store} --port {layout_port}"
        shim = binaries / "ps"
        shim.write_text(
            PS_SHIM.replace("@PID@", str(pid))
            .replace("@COUNT@", str(tmp_path / "ps-lookups.txt"))
            .replace("@LISTED@", str(listed_lookups))
            .replace("@COMMAND@", command)
            .replace("@REAL@", real)
        )
        shim.chmod(0o755)

    def path_without_curl():
        """A PATH of links to the tools the script needs, and no curl."""
        tools = tmp_path / "tools-without-curl"
        tools.mkdir()
        for name in TOOLS_THE_SCRIPT_RUNS:
            found = shutil.which(name, path=os.environ["PATH"])
            if found:
                (tools / name).symlink_to(found)
        for name in ("python3", "cce"):
            (tools / name).symlink_to(binaries / name)
        assert shutil.which("curl", path=str(tools)) is None
        return tools

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
            "zombie": zombie,
            "watch_curl": watch_curl,
            "fake_ps": fake_ps,
            "path_without_curl": path_without_curl,
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
            # Only ever signal what is still our stand-in engine, never a recycled number. Its command line
            # carries this test's own directory (the store roots), whichever path the engine was found by.
            if alive(pid) and str(tmp_path) in command_of(pid):
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


@pytest.mark.parametrize("value", ["0", "abc", "9223372036854775808"])
def test_a_start_timeout_that_is_not_a_positive_integer_is_ignored(layout, value):
    """The last value is one digit past the largest bash integer: it would wrap to a negative deadline."""
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
    probes = layout["watch_curl"]()
    waiter = layout["spawn"]("--no-open")
    # Wait for the thing the waiter must be doing, not for a guessed delay: it has probed the port once
    # and is polling behind the held lock.
    wait_until(lambda: probes() >= 1, reason="the waiter to start polling behind the lock")
    engine = layout["serve_engine"](port)
    out, err = waiter.communicate(timeout=30)

    assert waiter.returncode == 0, out + err
    assert f"server already up on port {port}" in out
    assert f"http://127.0.0.1:{port}/" in out
    assert [launched for launched, _ in layout["launches"]()] == [engine.pid], "the waiter launched its own engine"
    assert (lock / "pid").read_text().strip() == str(holder.pid), "the waiter disturbed a lock it did not own"


# The orderings a repeated run only hits by luck are driven here by pausing the lock section at named
# points in this test's own COPY of the script: a `_hook` function and two call sites are added, and each
# is armed through a file in a hooks directory. Every anchor must match exactly once, so a refactor of the
# lock section fails these tests loudly instead of silently un-pausing them.
HOOK_FUNCTION = """
# TEST HOOK (this test's copy only): pause at a named point when armed.
_hook() {
  [[ -n "${OK_HOOK_DIR:-}" && -e "$OK_HOOK_DIR/$1.arm" ]] || return 0
  rm -f "$OK_HOOK_DIR/$1.arm"
  : >"$OK_HOOK_DIR/$1.reached"
  while [[ ! -e "$OK_HOOK_DIR/$1.go" ]]; do sleep 0.05; done
}
"""
HOOK_EDITS = [
    (
        "lock_wait=$(( start_timeout + 5 > 15 ? start_timeout + 5 : 15 ))\n",
        "lock_wait=$(( start_timeout + 5 > 15 ? start_timeout + 5 : 15 ))\n" + HOOK_FUNCTION,
    ),
    (
        '    if mkdir "$lock_dir" 2>/dev/null; then\n',
        '    if mkdir "$lock_dir" 2>/dev/null; then\n      _hook after_mkdir\n',
    ),
    (
        '    if lock_holder_is_dead; then\n      if mkdir "$reap_dir" 2>/dev/null; then\n',
        '    if lock_holder_is_dead; then\n      _hook before_reap\n      if mkdir "$reap_dir" 2>/dev/null; then\n',
    ),
]


def install_pause_hooks(layout) -> Path:
    """Add the pause hooks to this layout's copy of the script; returns the directory that arms them."""
    script = layout["repo"] / "scripts" / "open-knowledge.sh"
    text = script.read_text(encoding="utf-8")
    for anchor, replacement in HOOK_EDITS:
        assert text.count(anchor) == 1, f"the lock section no longer has the line the pause hooks attach to: {anchor!r}"
        text = text.replace(anchor, replacement)
    script.write_text(text, encoding="utf-8")
    hooks = layout["tmp"] / "hooks"
    hooks.mkdir()
    return hooks


def test_a_fresh_lock_that_replaces_a_dead_one_before_the_recheck_is_kept(layout):
    """A recoverer judges a stale pid-less lock dead. Before it takes the recovery mutex, a new start creates a
    fresh pid-less lock in its place. The recheck under the mutex must measure the new lock's own age."""
    hooks = install_pause_hooks(layout)
    lock = layout["take_lock"](layout["port"])
    long_ago = time.time() - 10
    os.utime(lock, (long_ago, long_ago))
    (hooks / "before_reap.arm").touch()
    recoverer = layout["spawn"]("--no-open", extra_env={"OK_HOOK_DIR": str(hooks)})
    wait_until(lambda: (hooks / "before_reap.reached").exists(), 15, "the recoverer to judge the old lock dead")

    shutil.rmtree(lock)
    lock.mkdir()
    fresh = lock.stat().st_ino
    (hooks / "before_reap.go").touch()

    # A negative, so it needs a duration: long enough for a recheck that skips the age test to remove the lock
    # and launch an engine, well short of the 3 seconds the fresh lock needs before it may be recovered.
    time.sleep(1.0)
    assert recoverer.poll() is None, "the recoverer gave up instead of waiting behind the fresh lock"
    assert lock.exists() and lock.stat().st_ino == fresh, "the recheck removed a fresh lock that was not dead"
    assert layout["launches"]() == [], "an engine was launched behind a lock that was alive"


def test_a_holder_that_stalls_before_its_pid_write_cannot_share_the_lock_with_its_replacement(layout):
    """Start A takes the lock directory and stalls before it writes its pid. The lock turns old, start B recovers
    it, takes a new one and launches the engine. When A resumes, its pid write must lose: A must not believe it
    holds the lock and launch a second engine."""
    hooks = install_pause_hooks(layout)
    (hooks / "after_mkdir.arm").touch()
    stalled = layout["spawn"]("--no-open", extra_env={"OK_HOOK_DIR": str(hooks)})
    wait_until(lambda: (hooks / "after_mkdir.reached").exists(), 15, "start A to take the lock directory")
    lock = layout["lock"]()
    long_ago = time.time() - 10
    os.utime(lock, (long_ago, long_ago))

    # A slow-binding engine keeps B inside its start, holding the new lock, while A resumes.
    replacement = layout["spawn"]("--no-open", extra_env={"FAKE_ENGINE_BIND_DELAY": "3.0"})
    wait_until(lambda: len(layout["launches"]()) == 1, 20, "start B to recover the lock and launch the engine")
    assert (lock / "pid").read_text().strip() == str(replacement.pid), "start B does not hold the new lock"
    (hooks / "after_mkdir.go").touch()

    outputs = [proc.communicate(timeout=60) for proc in (stalled, replacement)]
    assert [stalled.returncode, replacement.returncode] == [0, 0], outputs
    assert len(layout["launches"]()) == 1, "the stalled start launched an engine of its own"
    assert not lock.exists(), "the start lock outlived both starts"


def test_a_start_gives_up_at_a_wait_bound_that_follows_the_start_timeout(layout):
    """Behind a live holder a start waits max(15, start timeout + 5) seconds: 15 by default, 17 for a
    12-second start timeout. The two waits run side by side, each on its own port, so the file pays once."""
    cases = {}
    for name, extra_env in (("default", None), ("long timeout", {TIMEOUT_VARIABLE: "12"})):
        on_port = layout["port"] if name == "default" else free_port()
        holder = layout["hold"]("open-knowledge-holder")
        lock = layout["take_lock"](on_port, holder.pid)
        cases[name] = {
            "port": on_port,
            "holder": holder,
            "lock": lock,
            "began": time.monotonic(),
            "proc": layout["spawn"]("--no-open", port=on_port, extra_env=extra_env),
        }

    def finish(case):
        case["output"] = case["proc"].communicate(timeout=60)
        case["elapsed"] = time.monotonic() - case["began"]

    waiters = [threading.Thread(target=finish, args=(case,)) for case in cases.values()]
    for waiter in waiters:
        waiter.start()
    for waiter in waiters:
        waiter.join()

    for name, bound in (("default", 15), ("long timeout", 17)):
        case = cases[name]
        _, err = case["output"]
        assert case["proc"].returncode == 1, (name, case["output"])
        assert (
            f"open-knowledge: another start on port {case['port']} did not finish within {bound} seconds"
            f" (lock {case['lock']})" in err.splitlines()
        ), (name, err)
        assert bound - 2 <= case["elapsed"] < bound + 15, f"{name}: gave up after {case['elapsed']:.1f}s"
        holder = case["holder"]
        assert (case["lock"] / "pid").read_text().strip() == str(holder.pid), "the loser released a lock it did not own"
    assert cases["long timeout"]["elapsed"] > 15.5, "the 12-second start timeout did not lengthen the lock wait"
    assert layout["launches"]() == []


@pytest.mark.parametrize("flag", ["--stop", "--status"])
def test_stop_and_status_never_block_on_the_start_lock(layout, flag):
    holder = layout["hold"]("open-knowledge-holder")
    lock = layout["take_lock"](layout["port"], holder.pid)
    result = layout["run"](flag, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert lock.exists() and (lock / "pid").read_text().strip() == str(holder.pid)


# --- C10: lock recovery ----------------------------------------------------------------------------

# One run of the stale-lock race fails about one time in five on the script without the recovery mutex;
# repeating it this many times inside one test leaves under a one-in-a-hundred chance of missing it.
STALE_LOCK_ROUNDS = 25
STARTERS_PER_ROUND = 6


def reap_of(lock: Path) -> Path:
    """The recovery mutex that sits beside a start lock."""
    return lock.with_name(lock.name + ".reap")


def test_a_lock_with_no_pid_file_is_recovered_once_its_directory_is_three_seconds_old(layout):
    lock = layout["take_lock"](layout["port"])
    began = time.monotonic()
    result = layout["run"]("--no-open", timeout=45)
    elapsed = time.monotonic() - began

    assert result.returncode == 0, result.stdout + result.stderr
    # Not removed at once (a fresh pid-less lock may be a holder between its mkdir and its pid write),
    # and well inside the 15-second give-up bound.
    assert 2.5 <= elapsed < 10, f"recovered after {elapsed:.1f}s"
    assert len(layout["launches"]()) == 1
    assert answers(layout["port"])
    assert not lock.exists(), "the recovered lock was never released"
    assert not reap_of(lock).exists(), "the recovery mutex outlived the recovery"


def test_a_lock_whose_pid_file_is_empty_is_recovered_within_the_bound(layout):
    lock = layout["take_lock"](layout["port"])
    (lock / "pid").write_text("")
    began = time.monotonic()
    result = layout["run"]("--no-open", timeout=45)
    elapsed = time.monotonic() - began

    assert result.returncode == 0, result.stdout + result.stderr
    assert 2.5 <= elapsed < 10, f"recovered after {elapsed:.1f}s"
    assert len(layout["launches"]()) == 1
    assert not lock.exists()
    assert not reap_of(lock).exists()


def test_the_age_of_a_lock_without_a_pid_is_its_directorys_own_modification_time(layout):
    """A start that has only just begun must not need three seconds of its own to condemn a lock that the
    file system already says is old."""
    lock = layout["take_lock"](layout["port"])
    long_ago = time.time() - 60
    os.utime(lock, (long_ago, long_ago))
    began = time.monotonic()
    result = layout["run"]("--no-open", timeout=45)
    elapsed = time.monotonic() - began

    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed < 3, f"an already old lock took {elapsed:.1f}s to recover"
    assert len(layout["launches"]()) == 1
    assert not lock.exists()


def test_a_lock_without_a_pid_that_gains_a_live_holder_is_left_alone_and_the_waiter_joins(layout):
    port = layout["port"]
    holder = layout["hold"]("open-knowledge-holder")
    probes = layout["watch_curl"]()
    lock = layout["take_lock"](port)
    waiter = layout["spawn"]("--no-open")
    wait_until(lambda: probes() >= 1, reason="the waiter to start polling behind the pid-less lock")
    # The holder's pid arrives; the directory itself is old, so only the pid can keep the lock alive.
    (lock / "pid").write_text(f"{holder.pid}\n")
    long_ago = time.time() - 60
    os.utime(lock, (long_ago, long_ago))
    seen = probes()
    wait_until(lambda: probes() >= seen + 3, reason="the waiter to poll the lock again")
    assert waiter.poll() is None
    assert layout["launches"]() == [], "the waiter condemned a lock whose holder is alive"
    engine = layout["serve_engine"](port)
    out, err = waiter.communicate(timeout=30)

    assert waiter.returncode == 0, out + err
    assert f"server already up on port {port}" in out
    assert [launched for launched, _ in layout["launches"]()] == [engine.pid]
    assert (lock / "pid").read_text().strip() == str(holder.pid), "the waiter disturbed a lock it did not own"


def test_a_lock_whose_holder_is_a_zombie_is_recovered(layout):
    gone = layout["zombie"]()
    lock = layout["take_lock"](layout["port"], gone.pid)
    began = time.monotonic()
    result = layout["run"]("--no-open")
    elapsed = time.monotonic() - began

    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed < 5, f"a zombie holder kept the lock for {elapsed:.1f}s"
    assert len(layout["launches"]()) == 1
    assert not lock.exists()


def test_a_recovery_mutex_blocks_recovery_until_it_is_a_minute_old(layout):
    """A mutex left by a recoverer that died stops recovery while it is fresh and is removed once old."""
    port = layout["port"]
    lock = layout["take_lock"](port, layout["dead_pid"]())
    mutex = reap_of(lock)
    mutex.mkdir()
    starter = layout["spawn"]("--no-open")

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        assert starter.poll() is None, starter.communicate()
        assert lock.exists(), "the dead lock was recovered without holding the recovery mutex"
        assert layout["launches"]() == []
        time.sleep(0.1)
    assert mutex.exists()

    a_minute_ago = time.time() - 120
    os.utime(mutex, (a_minute_ago, a_minute_ago))
    out, err = starter.communicate(timeout=30)
    assert starter.returncode == 0, out + err
    assert len(layout["launches"]()) == 1
    assert not lock.exists()
    assert not mutex.exists(), "the aged mutex was left behind"


def test_a_start_that_exits_does_not_remove_a_lock_that_now_names_another_process(layout):
    layout["install_engine"](SILENT_ENGINE)
    starter = layout["spawn"]("--no-open", extra_env={TIMEOUT_VARIABLE: "3"})
    wait_until(layout["launches"], reason="the start to launch its engine")
    holder = layout["hold"]("open-knowledge-holder")
    lock = layout["lock"]()
    assert lock.exists()
    # The start was displaced: another process owns the lock by the time this one exits.
    (lock / "pid").write_text(f"{holder.pid}\n")
    out, err = starter.communicate(timeout=40)

    assert starter.returncode == 1, out + err
    assert lock.exists(), "the exiting start removed a lock that another process had taken"
    assert (lock / "pid").read_text().strip() == str(holder.pid)


def test_many_concurrent_starts_behind_one_stale_lock_launch_exactly_one_engine(layout):
    port = layout["port"]
    for round_number in range(1, STALE_LOCK_ROUNDS + 1):
        lock = layout["take_lock"](port, layout["dead_pid"]())
        starters = [layout["spawn"]("--no-open") for _ in range(STARTERS_PER_ROUND)]
        outputs = [proc.communicate(timeout=60) for proc in starters]

        where = f"round {round_number} of {STALE_LOCK_ROUNDS}"
        assert [proc.returncode for proc in starters] == [0] * STARTERS_PER_ROUND, (where, outputs)
        launched = layout["launches"]()
        assert len(launched) == round_number, f"{where}: {len(launched)} engines were launched in all"
        assert not lock.exists(), f"{where}: the recovered lock was never released"
        assert not reap_of(lock).exists(), f"{where}: the recovery mutex outlived the recovery"
        recorded = int(layout["pid_file"]().read_text().strip())
        assert alive(recorded) and "archive serve" in command_of(recorded), (
            f"{where}: the pid file names {recorded}, which is not a live archive server"
        )
        assert recorded == launched[-1][0], f"{where}: the pid file names an engine that lost the race"
        assert answers(port)

        stopped = layout["run"]("--stop")
        assert stopped.returncode == 0, (where, stopped.stdout + stopped.stderr)
        assert wait_dead(recorded), f"{where}: the engine survived --stop"


def test_the_pid_file_is_created_exclusively_before_the_lock_counts_as_held():
    """A holder stalled past its own recovery must not write its pid into the directory of the process that
    replaced it. That interleaving cannot be driven without hooks, so the exclusive create is pinned as text."""
    text = SCRIPT.read_text(encoding="utf-8")
    body = text.split("acquire_start_lock() {", 1)[1].split("\n}\n", 1)[0]
    code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    exclusive = re.search(r"set -C\b|set -o noclobber", code)
    write = re.search(r">\s*\"\$lock_dir/pid\"", code)
    held = code.find("lock_held=1")
    assert exclusive and write and held >= 0, "acquire_start_lock lost its exclusive pid-file create"
    assert exclusive.start() < write.start() < held, "lock_held is set before the exclusive pid write"


@pytest.mark.parametrize("flag", ["--stop", "--status"])
def test_stop_and_status_ignore_the_start_lock_and_the_recovery_mutex(layout, flag):
    holder = layout["hold"]("open-knowledge-holder")
    lock = layout["take_lock"](layout["port"], holder.pid)
    mutex = reap_of(lock)
    mutex.mkdir()
    began = time.monotonic()
    result = layout["run"](flag, timeout=10)
    elapsed = time.monotonic() - began

    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed < 3, f"{flag} waited {elapsed:.1f}s"
    assert lock.exists() and (lock / "pid").read_text().strip() == str(holder.pid)
    assert mutex.exists()


# --- C12: --stop when the signal fails --------------------------------------------------------------


def test_stop_reports_a_server_that_exited_before_the_signal_and_clears_its_pid_file(layout):
    gone = layout["dead_pid"]()
    layout["state"].mkdir(parents=True, exist_ok=True)
    layout["pid_file"]().write_text(f"{gone}\n")
    # ps lists the pid as our server when the pid file is read, and no longer once the signal has failed.
    layout["fake_ps"](gone, 1)
    result = layout["run"]("--stop")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"open-knowledge: the server (pid {gone}) had already exited; pid file removed" in result.stdout.splitlines()
    assert "stopped the server" not in result.stdout, "a pid that never ran was reported as stopped"
    assert not layout["pid_file"]().exists()


def test_stop_fails_loudly_for_a_pid_that_ps_still_lists_but_cannot_be_signalled(layout):
    stuck = layout["dead_pid"]()
    layout["state"].mkdir(parents=True, exist_ok=True)
    layout["pid_file"]().write_text(f"{stuck}\n")
    layout["fake_ps"](stuck, 10**6)
    result = layout["run"]("--stop")

    assert result.returncode == 1, result.stdout + result.stderr
    assert f"open-knowledge: cannot signal pid {stuck}" in result.stderr.splitlines()
    assert "stopped the server" not in result.stdout


def test_a_successful_stop_keeps_a_pid_file_that_now_names_a_newer_start(layout):
    newer = layout["hold"]("open-knowledge-newer-start")
    started = layout["run"](
        "--no-open",
        extra_env={
            "FAKE_ENGINE_ON_TERM_FILE": str(layout["pid_file"]()),
            "FAKE_ENGINE_ON_TERM_TEXT": f"{newer.pid}\n",
        },
    )
    assert started.returncode == 0, started.stdout + started.stderr
    first = int(layout["pid_file"]().read_text().strip())

    stopped = layout["run"]("--stop")
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert f"stopped the server on port {layout['port']} (pid {first})" in stopped.stdout
    assert not answers(layout["port"])
    # By the time the old server died, the pid file already named the newer start: it must survive.
    assert layout["pid_file"]().exists(), "the stop removed the pid file of a newer start"
    assert layout["pid_file"]().read_text().strip() == str(newer.pid)


# --- C13: state directory errors are immediate ----------------------------------------------------


def test_a_state_path_that_is_a_regular_file_fails_the_start_at_once(layout):
    layout["state"].write_text("this is a file, not a directory")
    began = time.monotonic()
    result = layout["run"]("--no-open", timeout=45)
    elapsed = time.monotonic() - began

    assert result.returncode == 1, result.stdout + result.stderr
    assert f"open-knowledge: cannot create the state directory {layout['state']}" in result.stderr.splitlines()
    assert elapsed < 5, f"waited {elapsed:.1f}s for a lock that could never be taken"
    assert layout["launches"]() == []


def test_an_unwritable_state_directory_fails_the_start_at_once(layout):
    if os.geteuid() == 0:
        pytest.skip("root can write into a mode 555 directory, so the unwritable state cannot be built")
    state = layout["state"]
    state.mkdir(parents=True)
    state.chmod(0o555)
    try:
        if os.access(state, os.W_OK):
            pytest.skip("this file system ignores directory modes, so the unwritable state cannot be built")
        began = time.monotonic()
        result = layout["run"]("--no-open", timeout=45)
        elapsed = time.monotonic() - began
    finally:
        state.chmod(0o755)

    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        f"open-knowledge: cannot take the start lock; the state directory is not writable: {state}"
        in result.stderr.splitlines()
    )
    assert elapsed < 5, f"waited {elapsed:.1f}s for a lock that could never be taken"
    assert layout["launches"]() == []


def test_a_running_server_is_reused_even_when_the_state_directory_is_unwritable(layout):
    """A server that answers needs no lock, so an unwritable state directory must not break its reuse."""
    if os.geteuid() == 0:
        pytest.skip("root can write into a mode 555 directory, so the unwritable state cannot be built")
    state = layout["state"]
    state.mkdir(parents=True)
    engine = layout["serve_engine"](layout["port"])
    state.chmod(0o555)
    try:
        if os.access(state, os.W_OK):
            pytest.skip("this file system ignores directory modes, so the unwritable state cannot be built")
        result = layout["run"]("--no-open", timeout=45)
    finally:
        state.chmod(0o755)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"server already up on port {layout['port']}" in result.stdout
    assert [pid for pid, _ in layout["launches"]()] == [engine.pid], "a second engine was launched"


@pytest.mark.parametrize("how", ["state-path-is-a-file", "read-only-store"])
def test_a_running_server_is_reused_even_when_the_state_directory_cannot_be_created(layout, how):
    """The same reuse when there is no state directory at all and none can be made."""
    engine = layout["serve_engine"](layout["port"])
    store = layout["store"]
    if how == "state-path-is-a-file":
        layout["state"].write_text("this is a file, not a directory")
    else:
        if os.geteuid() == 0:
            pytest.skip("root can create entries in a mode 555 directory, so the read-only store cannot be built")
        store.chmod(0o555)
        if os.access(store, os.W_OK):
            store.chmod(0o755)
            pytest.skip("this file system ignores directory modes, so the read-only store cannot be built")
    try:
        result = layout["run"]("--no-open", timeout=45)
    finally:
        store.chmod(0o755)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"server already up on port {layout['port']}" in result.stdout
    assert [pid for pid, _ in layout["launches"]()] == [engine.pid], "a second engine was launched"


def test_a_dead_lock_in_an_unwritable_state_directory_fails_the_start_at_once(layout):
    """Recovery needs to remove the dead lock and create the recovery mutex; with neither possible the start
    must say so, not wait out the lock bound and blame a start that does not exist."""
    if os.geteuid() == 0:
        pytest.skip("root can write into a mode 555 directory, so the unwritable state cannot be built")
    state = layout["state"]
    layout["take_lock"](layout["port"], layout["dead_pid"]())
    state.chmod(0o555)
    try:
        if os.access(state, os.W_OK):
            pytest.skip("this file system ignores directory modes, so the unwritable state cannot be built")
        began = time.monotonic()
        result = layout["run"]("--no-open", timeout=45)
        elapsed = time.monotonic() - began
    finally:
        state.chmod(0o755)

    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        f"open-knowledge: cannot take the start lock; the state directory is not writable: {state}"
        in result.stderr.splitlines()
    )
    assert "did not finish within" not in result.stderr
    assert elapsed < 5, f"waited {elapsed:.1f}s for a recovery that could never happen"
    assert layout["launches"]() == []


# --- C14: curl is required --------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--stop", "--status", "--no-open"])
def test_a_path_without_curl_stops_every_mode_before_any_probe(layout, flag):
    result = layout["run"](
        flag,
        extra_env={"PATH": str(layout["path_without_curl"]()), TIMEOUT_VARIABLE: "2"},
        timeout=40,
    )
    assert result.returncode == 127, result.stdout + result.stderr
    assert "open-knowledge: curl not found on PATH; the liveness probe needs it" in result.stderr.splitlines()
    assert layout["launches"]() == [], "a start went ahead with no way to tell whether the server answers"


# --- C15: --port is a plain decimal from 1 to 65535 -------------------------------------------------


@pytest.mark.parametrize("value", ["08", "0010", "0", "65536", "18446744073709551617"])
def test_a_port_that_is_octal_zero_or_out_of_range_is_refused(layout, value):
    result = layout["run"]("--status", port=value)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.strip() == f"open-knowledge: --port must be a number from 1 to 65535, got '{value}'"
    assert result.stdout == ""


@pytest.mark.parametrize("value", ["1", "65535"])
def test_the_lowest_and_highest_ports_are_accepted(layout, value):
    result = layout["run"]("--status", port=value)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"server down on port {value}" in result.stdout


# --- C2 again: a pid file for a port that is a prefix of the engine's port ----------------------------


def test_a_pid_file_for_a_short_port_naming_an_engine_on_the_longer_port_is_not_trusted(layout):
    long_port = free_port()
    while long_port < 10000:
        long_port = free_port()
    short_port = long_port // 10
    assert str(long_port).startswith(str(short_port))
    engine = layout["serve_engine"](long_port)
    layout["state"].mkdir(parents=True, exist_ok=True)
    layout["pid_file"](short_port).write_text(f"{engine.pid}\n")

    result = layout["run"]("--stop", port=short_port)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"no server of ours on port {short_port} — nothing to stop" in result.stdout
    assert engine.poll() is None, "--stop killed the engine on the longer port"
    assert answers(long_port)
    assert not layout["pid_file"](short_port).exists(), "the untrusted pid file was kept"


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


@pytest.mark.skipif(sys.platform != "darwin", reason="the browser step only runs on macOS, where `open` exists")
def test_a_vault_link_that_cannot_be_built_never_fails_the_door(layout):
    """The vault is a bonus: when its link cannot be built the door still opens and still exits 0."""
    (layout["store"] / "archive-all" / "vault-all").mkdir()
    binaries = layout["binaries"]
    # Obsidian "is installed" and every open succeeds; only the URL-quoting call of the interpreter fails.
    opener = binaries / "open"
    opener.write_text("#!/bin/sh\nexit 0\n")
    opener.chmod(0o755)
    interpreter = binaries / "python3"
    interpreter.write_text(f'#!/bin/sh\ncase "$*" in *urllib.parse*) exit 1 ;; esac\nexec "{sys.executable}" "$@"\n')
    result = layout["run"]()
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"server started on port {layout['port']}" in result.stdout
    assert "could not build the Obsidian link" in result.stderr


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


def test_probes_ignore_a_proxy_environment(layout):
    """curl sends even a 127.0.0.1 request through http_proxy or all_proxy, which read a live server as down."""
    port = layout["port"]
    engine = layout["serve_engine"](port)
    # Nothing listens on port 9, so a probe that honours a proxy is refused and the server reads as down.
    proxy = "http://127.0.0.1:9"
    proxied = {"http_proxy": proxy, "all_proxy": proxy, "ALL_PROXY": proxy, "HTTP_PROXY": proxy}

    status = layout["run"]("--status", extra_env=proxied)
    assert status.returncode == 0, status.stdout + status.stderr
    assert f"server up on port {port}" in status.stdout, "a proxy environment made the live server read as down"

    again = layout["run"]("--no-open", extra_env=proxied)
    assert again.returncode == 0, again.stdout + again.stderr
    assert f"server already up on port {port}" in again.stdout
    assert [pid for pid, _ in layout["launches"]()] == [engine.pid]


def install_narrow_ps(layout) -> None:
    real = shutil.which("ps", path=os.environ["PATH"])
    assert real, "these tests need ps"
    shim = layout["binaries"] / "ps"
    shim.write_text(NARROW_PS_SHIM.replace("@REAL@", real))
    shim.chmod(0o755)


def test_a_narrow_ps_cannot_hide_a_running_server_from_stop(layout):
    """procps ps cut `archive serve` and the port off the engine's command line, so on Linux --stop found
    nothing it trusted and left the server running. A stand-in ps that cuts the same way must not defeat it."""
    install_narrow_ps(layout)
    narrow = {"COLUMNS": "40"}
    started = layout["run"]("--no-open", extra_env=narrow)
    assert started.returncode == 0, started.stdout + started.stderr
    recorded = int(layout["pid_file"]().read_text().strip())

    stopped = layout["run"]("--stop", extra_env=narrow)
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert f"stopped the server on port {layout['port']} (pid {recorded})" in stopped.stdout, stopped.stdout
    assert wait_dead(recorded), "the engine survived --stop"


def test_a_narrow_ps_cannot_make_a_live_lock_holder_look_dead(layout):
    """The same cut hid `open-knowledge` from the holder check, so a live holder's lock was judged dead and
    taken from it."""
    install_narrow_ps(layout)
    port = layout["port"]
    holder = layout["hold"]("open-knowledge-holder")
    lock = layout["take_lock"](port, holder.pid)
    probes = layout["watch_curl"]()
    waiter = layout["spawn"]("--no-open", extra_env={"COLUMNS": "40"})
    wait_until(lambda: probes() >= 3, reason="the waiter to poll behind the lock")

    assert waiter.poll() is None, "the waiter stopped waiting behind a live holder"
    assert lock.exists() and (lock / "pid").read_text().strip() == str(holder.pid), "a live holder's lock was taken"
    assert layout["launches"]() == [], "the waiter launched an engine behind a live holder"


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


def test_the_header_names_each_changed_behavior_and_the_accepted_residuals():
    header = "\n".join(header_lines(SCRIPT.read_text(encoding="utf-8"))).lower()
    for term in ("curl", ".reap", "3 seconds", "65535"):
        assert term in header, f"the header never mentions {term!r}"
    assert re.search(r"fork\W+to\W+exec", header), "the header does not name the fork-to-exec --stop residual"
    assert "concurrent stop" in header, "the header does not name the unlocked-pid-file residual"


def test_the_script_keeps_strict_mode_and_adds_only_the_one_environment_variable():
    text = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"^set -euo pipefail$", text, re.MULTILINE)
    assert set(re.findall(r"OPEN_KNOWLEDGE_[A-Z0-9_]+", text)) == {TIMEOUT_VARIABLE}
    assert "LIMEN_" not in text, "the parameter ratchet forbids a LIMEN_* parameter here"
