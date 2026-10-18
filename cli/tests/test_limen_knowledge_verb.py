"""`limen knowledge` — the advertised form of the knowledge archive front door, a pure delegate.

The script tests run against a throwaway copy of the repo layout: its own corpora registry, its own
store, and a stand-in `cce` that only serves one page. They never read the real private archive.
"""

import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from click.testing import CliRunner

from limen.cli import main

FINGERPRINT = "ab" * 32

# A stand-in for the engine's `cce archive serve`: it records what it was given and answers 200.
FAKE_ENGINE = """#!{python}
import http.server
import json
import os
import sys

arguments = sys.argv[1:]
port = int(arguments[arguments.index("--port") + 1])
with open(os.environ["FAKE_ENGINE_RECORD"], "w", encoding="utf-8") as record:
    json.dump(
        {{"arguments": arguments, "legacy_store_variable_set": "CCE_CORPUS_STORE_ROOT" in os.environ}},
        record,
    )


class Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"archive")

    def log_message(self, format, *args):
        pass


http.server.HTTPServer(("127.0.0.1", port), Page).serve_forever()
"""


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def answers(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


@pytest.fixture
def layout(tmp_path):
    """A repo copy holding only the script, the resolver and a registry, plus a built store."""
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
    manifest = {"source_fingerprint": FINGERPRINT, "totals": {"conversations": 7, "messages": 21, "words": 99}}
    (store / "archive-all" / "manifest-all.json").write_text(json.dumps(manifest))
    for name in ("receipt-knowledge-alive-1111111111111111-20261001.json", "receipt-knowledge-alive-2222222222222222-20261017.json"):
        (repo / "docs" / "receipts" / name).write_text("{}")

    binaries = tmp_path / "bin"
    binaries.mkdir()
    # A wrapper, not a symlink: a virtual environment's interpreter finds its packages from the path
    # it was started by, so a symlink elsewhere would lose PyYAML.
    interpreter = binaries / "python3"
    interpreter.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    interpreter.chmod(0o755)
    engine = binaries / "cce"
    engine.write_text(FAKE_ENGINE.format(python=sys.executable))
    engine.chmod(0o755)

    environment = {
        "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
        "HOME": os.environ["HOME"],
        "FAKE_ENGINE_RECORD": str(tmp_path / "engine-record.json"),
        "CCE_CORPUS_STORE_ROOT": str(tmp_path / "legacy-store"),
    }
    port = free_port()

    def run(*arguments):
        return subprocess.run(
            ["bash", str(repo / "scripts" / "open-knowledge.sh"), "--port", str(port), *arguments],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
            timeout=60,
        )

    yield {"repo": repo, "store": store, "port": port, "run": run, "record": tmp_path / "engine-record.json"}
    run("--stop")


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
    (layout["store"] / "archive-all" / "manifest-all.json").unlink()
    result = layout["run"]("--no-open")
    assert result.returncode == 2
    assert result.stderr.strip() == (
        "the archive is not built on this host; run cce archive build — see docs/architecture/ai-exports-archive.md"
    )


def test_status_reports_fingerprint_totals_and_newest_receipt_without_starting_anything(layout):
    result = layout["run"]("--status")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "server down" in result.stdout
    assert f"http://127.0.0.1:{layout['port']}/" in result.stdout
    assert FINGERPRINT in result.stdout
    assert "7 conversations, 21 messages" in result.stdout
    assert "receipt-knowledge-alive-2222222222222222-20261017.json" in result.stdout
    assert "1111111111111111" not in result.stdout
    assert not answers(layout["port"])


def test_front_door_starts_once_serves_the_site_and_stops(layout):
    first = layout["run"]("--no-open")
    assert first.returncode == 0, first.stdout + first.stderr
    assert f"http://127.0.0.1:{layout['port']}/" in first.stdout
    assert answers(layout["port"])

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
