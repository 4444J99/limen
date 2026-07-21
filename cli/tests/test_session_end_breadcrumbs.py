from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / "scripts" / "session-end-breadcrumb.py"
CONSUMER = ROOT / "scripts" / "consume-session-end-breadcrumbs.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _event(session_id: str = "session-a") -> bytes:
    return json.dumps(
        {
            "hook_event_name": "SessionEnd",
            "session_id": session_id,
            "cwd": "/redacted/worktree",
        }
    ).encode()


def test_producer_handles_one_hundred_repeated_events_with_constant_work(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_repeat")
    output = tmp_path / "breadcrumbs.jsonl"
    started = time.monotonic()
    for _ in range(100):
        assert producer.produce(_event(), output=output, source="project", now=100.0)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 100
    assert len({row["event_id"] for row in rows}) == 1
    assert all(row["schema"] == "limen.session_end_breadcrumb.v1" for row in rows)


def test_producer_and_consumer_default_to_one_host_stable_queue(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_default")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_default")
    environment = {"HOME": str(tmp_path / "home"), "XDG_STATE_HOME": str(tmp_path / "state")}
    expected = tmp_path / "state" / "limen" / "session-end-breadcrumbs.jsonl"

    assert producer.default_output(environment) == expected
    assert consumer.default_source(environment) == expected
    override = tmp_path / "shared" / "queue.jsonl"
    environment["LIMEN_SESSION_END_BREADCRUMBS"] = str(override)
    assert producer.default_output(environment) == override
    assert consumer.default_source(environment) == override


def test_producer_redacts_malformed_payload_and_fails_open_on_unwritable_target(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_malformed")
    output = tmp_path / "breadcrumbs.jsonl"
    raw = b'{"session_id":"secret-session",not-json:secret-prompt}'
    assert producer.produce(raw, output=output, source="global", environ={}, now=100.0)
    text = output.read_text(encoding="utf-8")
    row = json.loads(text)
    assert row["payload_valid"] is False
    assert row["session_id"].startswith("unknown-")
    assert "secret-session" not in text
    assert "secret-prompt" not in text

    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("fixture", encoding="utf-8")
    assert producer.produce(_event(), output=parent_file / "breadcrumbs.jsonl", source="project") is False


def test_hook_process_returns_inside_budget_and_writes_only_a_breadcrumb(tmp_path: Path) -> None:
    output = tmp_path / "breadcrumbs.jsonl"
    started = time.monotonic()
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "hooks" / "session-closeout.sh")],
        input=_event(),
        capture_output=True,
        timeout=2,
        env={
            **os.environ,
            "LIMEN_ROOT": str(tmp_path / "stale-root"),
            "LIMEN_SESSION_END_BREADCRUMBS": str(output),
        },
        check=False,
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 0
    assert elapsed < 0.5
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1
    hook = (ROOT / "scripts" / "hooks" / "session-closeout.sh").read_text(encoding="utf-8")
    for forbidden in (
        "handoff-relay.py",
        "orphan-watchers.py",
        "capture-session-claim.py",
        "claude-workflow-guard.py",
        "session-lifecycle-pressure.py",
        "git -C",
    ):
        assert forbidden not in hook


def test_global_and_project_duplicates_run_each_slow_consumer_once(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_duplicate")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_duplicate")
    root = tmp_path / "root"
    source = tmp_path / "state" / "limen" / "session-end-breadcrumbs.jsonl"
    cursor = root / "logs" / "cursor.json"
    receipts = root / "logs" / "receipts"
    producer.produce(_event(), output=source, source="global", now=100.0)
    producer.produce(_event(), output=source, source="project", now=101.0)
    calls: list[str] = []

    def runner(command, _timeout, _cwd):
        calls.append(Path(command[1]).name)
        return consumer.CommandResult(0, b"ok", 1)

    first = consumer.consume(
        root=root,
        source=source,
        cursor_path=cursor,
        receipt_root=receipts,
        runner=runner,
    )
    second = consumer.consume(
        root=root,
        source=source,
        cursor_path=cursor,
        receipt_root=receipts,
        runner=runner,
    )

    assert first == {"ingested": 2, "processed": 1, "attempted": 6, "completed": 6}
    assert second == {"ingested": 0, "processed": 0, "attempted": 0, "completed": 0}
    assert len(calls) == 5
    assert len(list(receipts.glob("*.json"))) == 1
    receipt = json.loads(next(receipts.glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["sources"] == ["global", "project"]
    assert {state["status"] for state in receipt["consumers"].values()} == {"complete"}
    assert len((root / "logs" / "session-closeout.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_consumer_retries_finitely_and_never_reruns_completed_consumers(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_retry")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_retry")
    root = tmp_path / "root"
    source = root / "logs" / "session-end-breadcrumbs.jsonl"
    cursor = root / "logs" / "cursor.json"
    receipts = root / "logs" / "receipts"
    producer.produce(_event("retry-session"), output=source, source="project", now=100.0)
    attempts: dict[str, int] = {}

    def runner(command, _timeout, _cwd):
        name = Path(command[1]).name
        attempts[name] = attempts.get(name, 0) + 1
        if name == "handoff-relay.py" and attempts[name] < 3:
            return consumer.CommandResult(1, b"transient", 1)
        return consumer.CommandResult(0, b"ok", 1)

    for _ in range(4):
        consumer.consume(
            root=root,
            source=source,
            cursor_path=cursor,
            receipt_root=receipts,
            runner=runner,
        )

    assert attempts["handoff-relay.py"] == 3
    assert all(count == 1 for name, count in attempts.items() if name != "handoff-relay.py")
    receipt = json.loads(next(receipts.glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["consumers"]["handoff"]["status"] == "complete"
    assert receipt["consumers"]["handoff"]["attempts"] == 3


def test_malformed_breadcrumb_is_terminal_without_slow_consumers(tmp_path: Path) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_bad_line")
    root = tmp_path / "root"
    source = root / "logs" / "session-end-breadcrumbs.jsonl"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"not-json\n")
    calls = []

    result = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=root / "logs" / "receipts",
        runner=lambda *args: calls.append(args),
    )

    assert result == {"ingested": 1, "processed": 1, "attempted": 0, "completed": 0}
    assert calls == []


def test_settings_and_heartbeat_keep_slow_work_outside_session_end() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    handlers = settings["hooks"]["SessionEnd"][0]["hooks"]
    assert len(handlers) == 1
    assert handlers[0]["timeout"] <= 5
    assert "session-closeout.sh" in handlers[0]["command"]
    assert "CLAUDE_PROJECT_DIR" in handlers[0]["command"]
    assert "$HOME/Workspace/limen" not in handlers[0]["command"]
    assert "session-lifecycle-pressure.sh" not in json.dumps(handlers)
    closeout = (ROOT / "scripts" / "hooks" / "session-closeout.sh").read_text(encoding="utf-8")
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    assert "XDG_STATE_HOME" in closeout
    assert "--output" in closeout
    assert "consume-session-end-breadcrumbs.py" in heartbeat
    assert "XDG_STATE_HOME" in heartbeat
    assert "--source" in heartbeat
