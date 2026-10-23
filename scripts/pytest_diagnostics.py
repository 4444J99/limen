"""Opt-in, controller-side pytest evidence that survives a gate timeout.

No scheduling, timeout, outcome or selection changes. The hermetic runner loads
this plugin, but it does nothing unless --limen-diagnostics is supplied.
"""

from __future__ import annotations

import json
import argparse
import hashlib
import importlib.metadata
import math
import os
import platform
import tempfile
import threading
from pathlib import Path
from time import monotonic


def positive_seconds(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("diagnostic interval must be finite and positive")
    return seconds


def pytest_addoption(parser):
    group = parser.getgroup("limen diagnostics")
    group.addoption(
        "--limen-diagnostics", metavar="DIRECTORY", help="parent of a unique, private diagnostic run directory"
    )
    group.addoption(
        "--limen-diagnostics-interval", type=positive_seconds, default=30.0, help="heartbeat seconds (default: 30)"
    )


def pytest_configure(config):
    directory = config.getoption("limen_diagnostics")
    # xdist forwards options to workers; only the controller writes evidence.
    if directory and not hasattr(config, "workerinput"):
        config.pluginmanager.register(Diagnostics(config, Path(directory)), "limen-run-diagnostics")


class Diagnostics:
    def __init__(self, config, parent):
        parent.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
        self.path = self.directory / "events.jsonl"
        self.stream = self.path.open("x", encoding="utf-8", buffering=1)
        os.chmod(self.path, 0o600)
        self.config = config
        self.started = monotonic()
        self.active = {}
        self.slowest = []
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.console = None

    def record(self, event, **fields):
        with self.lock:
            self.stream.write(json.dumps({"event": event, "elapsed": monotonic() - self.started, **fields}) + "\n")

    def announce(self, message):
        # A heartbeat occurs while the test's capture is active. Writing through
        # TerminalReporter there would hide it until the hung test returns.
        if self.console:
            self.console.write("\n" + message + "\n")
            self.console.flush()

    def pytest_sessionstart(self, session):
        # Keep the session's real output descriptor before per-test fd capture
        # redirects fd 1. sys.__stdout__ alone still targets that redirected fd.
        self.console = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
        self.record(
            "sessionstart",
            pid=os.getpid(),
            args=list(self.config.invocation_params.args),
            observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            python=platform.python_version(),
            platform=platform.system(),
            cpu_count=os.cpu_count(),
            pytest=importlib.metadata.version("pytest"),
        )
        self.announce(f"pytest-diagnostic journal: {self.path.resolve()}")
        self.thread = threading.Thread(target=self.heartbeat, daemon=True, name="pytest-diagnostics")
        self.thread.start()

    def heartbeat(self):
        while not self.stop.wait(self.config.getoption("limen_diagnostics_interval")):
            with self.lock:
                now = monotonic()
                active = sorted(
                    (
                        {"nodeid": nodeid, "phase": state["phase"], "seconds": now - state["started"]}
                        for nodeid, state in self.active.items()
                    ),
                    key=lambda row: row["seconds"],
                    reverse=True,
                )
                detail = "; ".join(f"{row['seconds']:.1f}s {row['phase']} {row['nodeid']}" for row in active[:10])
                self.announce(
                    f"pytest-diagnostic active={len(active)}: {detail or 'collecting or waiting for workers'}"
                )
                self.record("heartbeat", active=active, slowest=self.slowest)

    def pytest_runtest_logstart(self, nodeid, location):
        with self.lock:
            self.active[nodeid] = {"started": monotonic(), "phase": "setup"}
            self.record("start", nodeid=nodeid)

    def pytest_runtest_logreport(self, report):
        with self.lock:
            row = dict(nodeid=report.nodeid, phase=report.when, outcome=report.outcome, duration=report.duration)
            row["worker"] = getattr(report, "worker_id", "master")
            if report.failed:
                row["longrepr"] = report.longreprtext
                row["sections"] = list(report.sections)
            self.record("report", **row)
            if report.when in ("setup", "call") and report.nodeid in self.active:
                self.active[report.nodeid] = {
                    "started": monotonic(),
                    "phase": "call" if report.when == "setup" and report.passed else "teardown",
                }
            self.slowest = sorted(
                [*self.slowest, {key: row[key] for key in ("nodeid", "phase", "duration")}],
                key=lambda item: item["duration"],
                reverse=True,
            )[:30]
            if report.failed:
                self.announce(
                    f"pytest-diagnostic FAILED {report.when} {report.nodeid} ({report.duration:.3f}s); detail in {self.path}"
                )

    def pytest_runtest_logfinish(self, nodeid, location):
        with self.lock:
            self.active.pop(nodeid, None)
            self.record("finish", nodeid=nodeid)

    def pytest_collectreport(self, report):
        if report.failed:
            self.record("collection", nodeid=report.nodeid, outcome=report.outcome, longrepr=report.longreprtext)
            self.announce(f"pytest-diagnostic FAILED collection {report.nodeid}; detail in {self.path}")

    def pytest_sessionfinish(self, session, exitstatus):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.record("sessionfinish", exitstatus=int(exitstatus), slowest=self.slowest)
        for row in self.slowest:
            self.announce(f"pytest-diagnostic slow {row['duration']:.3f}s {row['phase']} {row['nodeid']}")

    def pytest_unconfigure(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        self.stream.close()
        if self.console:
            self.console.close()


def summarize(path):
    """Read even a killed run; only an incomplete final line may be discarded."""
    lines = Path(path).read_text().splitlines(keepends=True)
    records = []
    for index, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1 or line.endswith("\n"):
                raise
    active = {}
    phases = []
    failures = []
    terminal = None
    for row in records:
        if row["event"] == "start":
            active[row["nodeid"]] = "setup"
        elif row["event"] == "finish":
            active.pop(row["nodeid"], None)
        elif row["event"] == "report":
            phases.append({key: row[key] for key in ("nodeid", "phase", "duration")})
            if row["nodeid"] in active:
                active[row["nodeid"]] = "call" if row["phase"] == "setup" and row["outcome"] == "passed" else "teardown"
        elif row["event"] == "sessionfinish":
            terminal = row
        if row.get("outcome") == "failed":
            failures.append({"nodeid": row["nodeid"], "phase": row.get("phase", "collection")})
    return {
        "complete": terminal is not None,
        "exitstatus": terminal["exitstatus"] if terminal else None,
        "elapsed": records[-1]["elapsed"] if records else None,
        "unfinished": active,
        "failures": failures,
        "slowest": sorted(phases, key=lambda row: row["duration"], reverse=True)[:30],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Summarize a pytest diagnostic journal, including interrupted runs.")
    parser.add_argument("journal", type=Path)
    print(json.dumps(summarize(parser.parse_args().journal), indent=2))
