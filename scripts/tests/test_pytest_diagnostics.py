"""Exercise real pytest processes, including evidence surviving a group timeout."""

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/run-pytest-hermetic.sh"


def events(directory):
    return [json.loads(line) for path in directory.glob("*/events.jsonl") for line in path.read_text().splitlines()]


@pytest.mark.parametrize("workers, distribution", [("0", "load"), ("2", "load"), ("2", "worksteal")])
def test_reports_all_phases_and_preserves_failure_exit(tmp_path, workers, distribution):
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "import pytest\n"
        "@pytest.fixture\ndef bad_setup():\n    assert False, 'setup-broken'\n"
        "@pytest.fixture\ndef bad_teardown():\n    yield\n    assert False, 'teardown-broken'\n"
        "def test_setup(bad_setup): pass\n"
        "def test_call(): assert False, 'call-broken'\n"
        "def test_teardown(bad_teardown): pass\n"
        "@pytest.mark.skip(reason='intentional')\ndef test_skip(): pass\n"
    )
    directory = tmp_path / "evidence"
    result = subprocess.run(
        [
            "bash",
            str(RUNNER),
            str(probe),
            "-q",
            "-n",
            workers,
            "--dist",
            distribution,
            f"--limen-diagnostics={directory}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    records = events(directory)
    failures = [r for r in records if r.get("outcome") == "failed"]
    assert {r["phase"] for r in failures} == {"setup", "call", "teardown"}
    assert all(r["duration"] >= 0 and "broken" in r["longrepr"] for r in failures)
    assert records[-1]["event"] == "sessionfinish"
    assert records[-1]["exitstatus"] == 1
    assert "pytest-diagnostic FAILED" in result.stdout
    assert any(r.get("outcome") == "skipped" for r in records)


@pytest.mark.parametrize("workers, distribution", [("0", "load"), ("2", "load"), ("2", "worksteal")])
def test_timeout_keeps_failed_names_and_active_test(tmp_path, workers, distribution):
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "import time\ndef test_01_fail(): assert False, 'failure-before-timeout'\ndef test_02_hang(): time.sleep(60)\n"
    )
    directory = tmp_path / "evidence"
    process = subprocess.Popen(
        [
            "bash",
            str(RUNNER),
            str(probe),
            "-q",
            "-n",
            workers,
            "--dist",
            distribution,
            f"--limen-diagnostics={directory}",
            "--limen-diagnostics-interval=0.1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    ready = False
    try:
        deadline = time.monotonic() + 10
        while process.poll() is None and time.monotonic() < deadline:
            records = events(directory)
            if any(r.get("outcome") == "failed" for r in records) and any(
                r["event"] == "heartbeat" and any("test_02_hang" in a["nodeid"] for a in r["active"]) for r in records
            ):
                ready = True
                break
            time.sleep(0.02)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        output, _ = process.communicate(timeout=5)
    assert ready, output
    assert process.returncode != 0
    records = events(directory)
    assert any(r.get("outcome") == "failed" and "failure-before-timeout" in r["longrepr"] for r in records)
    assert not any(r["event"] == "sessionfinish" for r in records)
    assert "test_02_hang" in output
    journal = next(directory.glob("*/events.jsonl"))
    # A kill may interrupt the final JSON write. Earlier evidence remains usable.
    with journal.open("a") as stream:
        stream.write('{"event":')
    summary = subprocess.run(
        ["python3", str(ROOT / "scripts/pytest_diagnostics.py"), str(journal)],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    result = json.loads(summary.stdout)
    assert result["complete"] is False
    assert result["exitstatus"] is None
    assert any("test_02_hang" in nodeid for nodeid in result["unfinished"])
    assert any("test_01_fail" in row["nodeid"] for row in result["failures"])


def test_collection_errors_are_written_before_session_end(tmp_path):
    probe = tmp_path / "test_broken.py"
    probe.write_text("raise RuntimeError('collection-broken')\n")
    directory = tmp_path / "evidence"
    result = subprocess.run(
        ["bash", str(RUNNER), str(probe), "-q", f"--limen-diagnostics={directory}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert any(r.get("event") == "collection" and "collection-broken" in r["longrepr"] for r in events(directory))


def test_heartbeat_survives_test_clock_patch_and_names_teardown(tmp_path):
    probe = tmp_path / "test_clock.py"
    probe.write_text(
        "import pytest, time\n"
        "@pytest.fixture\n"
        "def clock(monkeypatch):\n"
        "    monkeypatch.setattr(time, 'monotonic', lambda: 0)\n"
        "    yield\n"
        "    time.sleep(0.3)\n"
        "def test_clock(clock): pass\n"
    )
    directory = tmp_path / "evidence"
    result = subprocess.run(
        [
            "bash",
            str(RUNNER),
            str(probe),
            "-q",
            f"--limen-diagnostics={directory}",
            "--limen-diagnostics-interval=0.05",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    records = events(directory)
    assert any(
        r["event"] == "heartbeat" and any(a["phase"] == "teardown" and a["seconds"] > 0 for a in r["active"])
        for r in records
    )
    assert "teardown" in result.stdout


def test_diagnostics_are_opt_in(tmp_path):
    probe = tmp_path / "test_ok.py"
    probe.write_text("def test_ok(): pass\n")
    result = subprocess.run(
        ["bash", str(RUNNER), str(probe), "-q"], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0
    assert "pytest-diagnostic" not in result.stdout
    assert not list(tmp_path.rglob("events.jsonl"))
