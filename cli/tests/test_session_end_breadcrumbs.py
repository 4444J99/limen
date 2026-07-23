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


def _event(
    session_id: str = "session-a",
    *,
    cwd: str = "/redacted/.worktrees/session",
    transcript_path: Path | None = None,
) -> bytes:
    payload = {
        "hook_event_name": "SessionEnd",
        "session_id": session_id,
        "cwd": cwd,
    }
    if transcript_path is not None:
        payload["transcript_path"] = str(transcript_path)
    return json.dumps(payload).encode()


def _receipt_paths(receipt_root: Path) -> list[Path]:
    return sorted(
        [
            *receipt_root.glob("*.json"),
            *(receipt_root / "active").glob("*.json"),
            *(receipt_root / "terminal").glob("*.json"),
        ]
    )


def _only_receipt(receipt_root: Path) -> Path:
    paths = _receipt_paths(receipt_root)
    assert len(paths) == 1
    return paths[0]


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

    def runner(command, _timeout, _cwd, _environment):
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
    assert len(_receipt_paths(receipts)) == 1
    receipt = json.loads(_only_receipt(receipts).read_text(encoding="utf-8"))
    assert receipt["sources"] == ["global", "project"]
    assert {state["status"] for state in receipt["consumers"].values()} == {"complete"}
    assert len((root / "logs" / "session-closeout.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_occurrence_id_tracks_transcript_growth_without_splitting_duplicate_sources(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_occurrence")
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("first\n", encoding="utf-8")
    raw = _event(transcript_path=transcript)

    global_event = producer.breadcrumb(raw, source="global", now=100.0)
    project_event = producer.breadcrumb(raw, source="project", now=101.0)
    assert global_event["event_id"] == project_event["event_id"]

    transcript.write_text("first\nresumed work\n", encoding="utf-8")
    resumed = producer.breadcrumb(raw, source="project", now=101.0)
    assert resumed["event_id"] != project_event["event_id"]


def test_fallback_pairing_crosses_time_boundary_and_repeated_source_starts_new_occurrence(
    tmp_path: Path,
) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_fallback_pair")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_fallback_pair")
    root = tmp_path / "root"
    source = tmp_path / "state" / "breadcrumbs.jsonl"
    receipts = root / "logs" / "receipts"
    raw = _event()

    global_event = producer.breadcrumb(raw, source="global", now=104.999)
    project_event = producer.breadcrumb(raw, source="project", now=105.001)
    assert global_event["event_id"] == project_event["event_id"]
    assert global_event["delivery_id"] != project_event["delivery_id"]
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(global_event) + "\n" + json.dumps(project_event) + "\n",
        encoding="utf-8",
    )

    first = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=receipts,
        runner=lambda *_args: consumer.CommandResult(0, b"ok", 1),
    )
    producer.produce(raw, output=source, source="project", now=106.0)
    second = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=receipts,
        runner=lambda *_args: consumer.CommandResult(0, b"ok", 1),
    )

    assert first == {"ingested": 2, "processed": 1, "attempted": 6, "completed": 6}
    assert second == {"ingested": 1, "processed": 1, "attempted": 6, "completed": 6}
    assert len(_receipt_paths(receipts)) == 2


def test_resumed_session_creates_a_new_occurrence_and_reruns_consumers(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_resumed")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_resumed")
    root = tmp_path / "root"
    source = tmp_path / "state" / "breadcrumbs.jsonl"
    cursor = root / "logs" / "cursor.json"
    receipts = root / "logs" / "receipts"
    calls: list[str] = []

    def runner(command, _timeout, _cwd, _environment):
        calls.append(Path(command[1]).name)
        return consumer.CommandResult(0, b"ok", 1)

    producer.produce(_event(), output=source, source="global", now=100.0)
    producer.produce(_event(), output=source, source="project", now=101.0)
    first = consumer.consume(
        root=root,
        source=source,
        cursor_path=cursor,
        receipt_root=receipts,
        runner=runner,
    )
    producer.produce(_event(), output=source, source="global", now=200.0)
    producer.produce(_event(), output=source, source="project", now=201.0)
    second = consumer.consume(
        root=root,
        source=source,
        cursor_path=cursor,
        receipt_root=receipts,
        runner=runner,
    )

    assert first == {"ingested": 2, "processed": 1, "attempted": 6, "completed": 6}
    assert second == {"ingested": 2, "processed": 1, "attempted": 6, "completed": 6}
    assert len(calls) == 10
    assert len(_receipt_paths(receipts)) == 2
    assert len((root / "logs" / "session-closeout.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_resumed_session_is_not_conflated_with_a_cross_source_delivery(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_cross_source_resume")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_cross_source_resume")
    root = tmp_path / "root"
    source = tmp_path / "state" / "breadcrumbs.jsonl"
    receipts = root / "logs" / "receipts"
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("first\n", encoding="utf-8")
    calls: list[str] = []

    def runner(command, _timeout, _cwd, _environment):
        calls.append(Path(command[1]).name)
        return consumer.CommandResult(0, b"ok", 1)

    producer.produce(_event(transcript_path=transcript), output=source, source="global", now=100.0)
    first = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=receipts,
        runner=runner,
    )
    transcript.write_text("first\nresumed\n", encoding="utf-8")
    producer.produce(_event(transcript_path=transcript), output=source, source="project", now=105.0)
    second = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=receipts,
        runner=runner,
    )

    assert first == {"ingested": 1, "processed": 1, "attempted": 6, "completed": 6}
    assert second == {"ingested": 1, "processed": 1, "attempted": 6, "completed": 6}
    assert len(calls) == 10
    assert len(_receipt_paths(receipts)) == 2


def test_valid_duplicate_upgrades_a_malformed_first_delivery(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_upgrade")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_upgrade")
    root = tmp_path / "root"
    source = tmp_path / "state" / "breadcrumbs.jsonl"
    source.parent.mkdir(parents=True)
    valid = producer.breadcrumb(_event(), source="project", now=101.0)
    malformed = {
        **valid,
        "event_id": valid["event_id"],
        "source": "global",
        "ended_epoch": 100.0,
        "payload_valid": False,
        "payload_sha256": "malformed",
    }
    source.write_text(
        json.dumps(malformed) + "\n" + json.dumps(valid) + "\n",
        encoding="utf-8",
    )

    result = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=root / "logs" / "receipts",
        runner=lambda *_args: consumer.CommandResult(0, b"ok", 1),
    )

    receipt_paths = _receipt_paths(root / "logs" / "receipts")
    assert result == {"ingested": 2, "processed": 1, "attempted": 6, "completed": 6}
    assert len(receipt_paths) == 1
    receipt = json.loads(receipt_paths[0].read_text(encoding="utf-8"))
    assert receipt["payload_valid"] is True
    assert receipt["sources"] == ["global", "project"]
    assert {state["status"] for state in receipt["consumers"].values()} == {"complete"}


def test_consumer_retries_finitely_and_never_reruns_completed_consumers(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_retry")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_retry")
    root = tmp_path / "root"
    source = root / "logs" / "session-end-breadcrumbs.jsonl"
    cursor = root / "logs" / "cursor.json"
    receipts = root / "logs" / "receipts"
    producer.produce(_event("retry-session"), output=source, source="project", now=100.0)
    attempts: dict[str, int] = {}

    def runner(command, _timeout, _cwd, _environment):
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
    receipt = json.loads(_only_receipt(receipts).read_text(encoding="utf-8"))
    assert receipt["consumers"]["handoff"]["status"] == "complete"
    assert receipt["consumers"]["handoff"]["attempts"] == 3


def test_malformed_numeric_event_and_cursor_fields_recover_without_wedging_queue(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_numeric_recovery")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_numeric_recovery")
    root = tmp_path / "root"
    source = root / "state" / "breadcrumbs.jsonl"
    cursor = root / "logs" / "cursor.json"
    receipts = root / "logs" / "receipts"
    source.parent.mkdir(parents=True)
    bad = {
        "schema": "limen.session_end_breadcrumb.v1",
        "event_id": "bad-number",
        "provider": "claude",
        "session_id": "bad-number-session",
        "source": "global",
        "ended_epoch": "not-a-number",
        "cwd": "/redacted/.worktrees/bad",
        "payload_valid": True,
        "payload_sha256": "bad",
    }
    source.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    producer.produce(_event("good-session"), output=source, source="project", now=100.0)
    cursor.parent.mkdir(parents=True)
    cursor.write_text(
        json.dumps(
            {
                "schema": "limen.session_end_cursor.v1",
                "offset": "corrupt",
                "device": "corrupt",
                "inode": "corrupt",
            }
        ),
        encoding="utf-8",
    )

    result = consumer.consume(
        root=root,
        source=source,
        cursor_path=cursor,
        receipt_root=receipts,
        runner=lambda *_args: consumer.CommandResult(0, b"ok", 1),
    )

    recovered_cursor = json.loads(cursor.read_text(encoding="utf-8"))
    assert result == {"ingested": 2, "processed": 2, "attempted": 6, "completed": 6}
    assert recovered_cursor["offset"] == source.stat().st_size
    assert isinstance(recovered_cursor["device"], int)
    assert isinstance(recovered_cursor["inode"], int)
    assert len(_receipt_paths(receipts)) == 2


def test_non_worktree_session_never_appends_quicken_compatibility_closeout(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_non_worktree")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_non_worktree")
    root = tmp_path / "root"
    source = root / "state" / "breadcrumbs.jsonl"
    receipts = root / "logs" / "receipts"
    producer.produce(
        _event(cwd="/Users/example/Workspace/limen"),
        output=source,
        source="project",
        now=100.0,
    )

    result = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=receipts,
        runner=lambda *_args: consumer.CommandResult(0, b"ok", 1),
    )

    receipt = json.loads(_only_receipt(receipts).read_text(encoding="utf-8"))
    assert result == {"ingested": 1, "processed": 1, "attempted": 5, "completed": 5}
    assert receipt["consumers"]["compatibility_closeout"] == {
        "status": "not_applicable",
        "attempts": 0,
    }
    assert not (root / "logs" / "session-closeout.jsonl").exists()


def test_scratch_limen_worktree_gets_compatibility_closeout(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_scratch_worktree")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_scratch_worktree")
    root = tmp_path / "root"
    source = root / "state" / "breadcrumbs.jsonl"
    producer.produce(
        _event(cwd="/Volumes/Scratch/limen-worktrees/task"),
        output=source,
        source="project",
        now=100.0,
    )

    result = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=root / "logs" / "receipts",
        runner=lambda *_args: consumer.CommandResult(0, b"ok", 1),
    )

    assert result == {"ingested": 1, "processed": 1, "attempted": 6, "completed": 6}
    assert len((root / "logs" / "session-closeout.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_model_audit_violation_is_a_durable_warning_and_terminal_success(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_model_warning")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_model_warning")
    root = tmp_path / "root"
    source = root / "state" / "breadcrumbs.jsonl"
    receipts = root / "logs" / "receipts"
    producer.produce(_event(), output=source, source="project", now=100.0)

    def runner(command, _timeout, _cwd, _environment):
        if Path(command[1]).name == "claude-workflow-guard.py":
            report = {
                "ok": False,
                "violations": ["Opus subagent fanout (2 subagents on Opus; max 1)"],
                "expensiveSubagents": 2,
                "agentCalls": 2,
            }
            return consumer.CommandResult(2, json.dumps(report).encode(), 1)
        return consumer.CommandResult(0, b"ok", 1)

    result = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=receipts,
        runner=runner,
    )

    receipt = json.loads(_only_receipt(receipts).read_text(encoding="utf-8"))
    model_state = receipt["consumers"]["model_audit"]
    warning_path = root / model_state["warning_receipt"]
    warning = json.loads(warning_path.read_text(encoding="utf-8"))
    assert result == {"ingested": 1, "processed": 1, "attempted": 6, "completed": 6}
    assert model_state["status"] == "complete"
    assert model_state["warning"] is True
    assert model_state["audit_exit_code"] == 2
    assert warning["schema"] == "limen.model_tier_audit_warning.v1"
    assert warning["violations"] == ["Opus subagent fanout (2 subagents on Opus; max 1)"]
    assert len((root / "logs" / "model-tier-audit.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_model_audit_preserves_violations_beyond_four_kibibytes(tmp_path: Path) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_large_model_warning")
    report = {
        "files": ["/redacted/" + ("x" * 180) for _ in range(40)],
        "ok": False,
        "violations": ["bounded violation survives"],
    }
    encoded = json.dumps(report, indent=2, sort_keys=True).encode()
    assert len(encoded) > consumer.MAX_OUTPUT_BYTES
    result = consumer.run_bounded(
        (sys.executable, "-c", f"import sys;sys.stdout.buffer.write({encoded!r})"),
        5,
        tmp_path,
    )

    warning = consumer._model_warning_payload(
        {"event_id": "event", "session_id": "session", "last_seen_epoch": 1},
        consumer.CommandResult(
            2,
            result.output,
            result.duration_ms,
            evidence_tail=result.evidence_tail,
            output_total_bytes=result.output_total_bytes,
        ),
    )

    assert len(result.output) == consumer.MAX_OUTPUT_BYTES
    assert warning["output_truncated"] is True
    assert warning["violations"] == ["bounded violation survives"]


def test_model_warning_terminal_state_preserves_large_output_metadata(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_model_metadata")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_model_metadata")
    root = tmp_path / "root"
    source = root / "state" / "breadcrumbs.jsonl"
    receipts = root / "logs" / "receipts"
    report = b'{"violations":["bounded"]}'
    producer.produce(_event(), output=source, source="project", now=100.0)

    def runner(command, _timeout, _cwd, _environment):
        if Path(command[1]).name == "claude-workflow-guard.py":
            return consumer.CommandResult(
                2,
                report,
                1,
                evidence_tail=report,
                output_total_bytes=9000,
            )
        return consumer.CommandResult(0, b"ok", 1)

    consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=receipts,
        runner=runner,
    )

    receipt = json.loads(_only_receipt(receipts).read_text(encoding="utf-8"))
    assert receipt["consumers"]["model_audit"]["status"] == "complete"
    assert receipt["consumers"]["model_audit"]["output_truncated"] is True


def test_model_warning_retries_until_receipt_and_ledger_are_both_durable(tmp_path: Path, monkeypatch) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_warning_retry")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_warning_retry")
    root = tmp_path / "root"
    source = root / "state" / "breadcrumbs.jsonl"
    receipts = root / "logs" / "receipts"
    producer.produce(
        _event(cwd="/Users/example/Workspace/limen"),
        output=source,
        source="project",
        now=100.0,
    )
    original_append = consumer._append_json_line_once

    def fail_model_ledger(path, payload, *, marker_path, identity):
        if path.name == "model-tier-audit.jsonl":
            return False
        return original_append(path, payload, marker_path=marker_path, identity=identity)

    def runner(command, _timeout, _cwd, _environment):
        if Path(command[1]).name == "claude-workflow-guard.py":
            return consumer.CommandResult(2, b'{"violations":["v"]}', 1)
        return consumer.CommandResult(0, b"ok", 1)

    monkeypatch.setattr(consumer, "_append_json_line_once", fail_model_ledger)
    first = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=receipts,
        runner=runner,
    )
    first_receipt = json.loads(_only_receipt(receipts).read_text(encoding="utf-8"))
    assert first["completed"] == 4
    assert first_receipt["consumers"]["model_audit"]["status"] == "retry"
    assert not (root / "logs" / "model-tier-audit.jsonl").exists()

    monkeypatch.setattr(consumer, "_append_json_line_once", original_append)
    second = consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=receipts,
        runner=runner,
    )
    final_receipt = json.loads(_only_receipt(receipts).read_text(encoding="utf-8"))
    assert second == {"ingested": 0, "processed": 1, "attempted": 1, "completed": 1}
    assert final_receipt["consumers"]["model_audit"]["status"] == "complete"
    assert len((root / "logs" / "model-tier-audit.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_lifecycle_consumer_receives_narrow_worktree_timeout(tmp_path: Path, monkeypatch) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_lifecycle_env")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_lifecycle_env")
    root = tmp_path / "root"
    source = root / "state" / "breadcrumbs.jsonl"
    observed: dict[str, str] = {}
    monkeypatch.setenv("LIMEN_SESSION_WORKTREE_DEBT_TIMEOUT", "17")
    producer.produce(_event(), output=source, source="project", now=100.0)

    def runner(command, _timeout, _cwd, environment):
        if Path(command[1]).name == "session-lifecycle-pressure.py":
            observed.update(environment or {})
        return consumer.CommandResult(0, b"ok", 1)

    consumer.consume(
        root=root,
        source=source,
        cursor_path=root / "logs" / "cursor.json",
        receipt_root=root / "logs" / "receipts",
        runner=runner,
    )

    assert observed["LIMEN_WORKTREE_DEBT_TIMEOUT"] == "17"


def test_spawn_oserror_becomes_a_finite_retryable_result(tmp_path: Path, monkeypatch) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_spawn_error")

    def fail_spawn(*_args, **_kwargs):
        raise FileNotFoundError(2, "missing executable")

    monkeypatch.setattr(consumer.subprocess, "Popen", fail_spawn)
    result = consumer.run_bounded(("/missing/consumer",), 1, tmp_path)

    assert result.exit_code == 127
    assert result.output == b"spawn-oserror:2"
    assert result.timed_out is False


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


def test_cross_entrypoint_lock_skips_a_competing_drain_without_advancing_cursor(tmp_path: Path) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_lock")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_lock")
    root = tmp_path / "root"
    source = root / "state" / "breadcrumbs.jsonl"
    cursor = root / "logs" / "cursor.json"
    receipts = root / "logs" / "receipts"
    producer.produce(_event(), output=source, source="project", now=100.0)

    with consumer._consumer_lock(receipts) as acquired:
        assert acquired is True
        result = consumer.consume(
            root=root,
            source=source,
            cursor_path=cursor,
            receipt_root=receipts,
            runner=lambda *_args: consumer.CommandResult(0, b"ok", 1),
        )

    assert result == {"ingested": 0, "processed": 0, "attempted": 0, "completed": 0}
    assert not cursor.exists()


def test_terminal_receipts_are_not_rescanned_after_active_index_converges(tmp_path: Path, monkeypatch) -> None:
    producer = _load(PRODUCER, "session_end_breadcrumb_producer_active_index")
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_active_index")
    root = tmp_path / "root"
    source = root / "state" / "breadcrumbs.jsonl"
    cursor = root / "logs" / "cursor.json"
    receipts = root / "logs" / "receipts"
    producer.produce(_event(), output=source, source="project", now=100.0)
    consumer.consume(
        root=root,
        source=source,
        cursor_path=cursor,
        receipt_root=receipts,
        runner=lambda *_args: consumer.CommandResult(0, b"ok", 1),
    )
    terminal = _only_receipt(receipts)
    original_load = consumer._load_json
    terminal_reads = 0

    def track_load(path, default):
        nonlocal terminal_reads
        if path == terminal:
            terminal_reads += 1
        return original_load(path, default)

    monkeypatch.setattr(consumer, "_load_json", track_load)
    result = consumer.consume(
        root=root,
        source=source,
        cursor_path=cursor,
        receipt_root=receipts,
        runner=lambda *_args: consumer.CommandResult(0, b"ok", 1),
    )

    assert result == {"ingested": 0, "processed": 0, "attempted": 0, "completed": 0}
    assert terminal_reads == 0
    assert not list((receipts / consumer.ACTIVE_RECEIPT_DIR).glob("*.json"))
    assert terminal.parent.name == consumer.TERMINAL_RECEIPT_DIR


def test_legacy_migration_is_bounded_resumable_and_never_evicts_active_receipts(tmp_path: Path) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_lossless_migration")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    total = 2049
    receipt = {
        "schema": consumer.RECEIPT_SCHEMA,
        "event_id": "event",
        "session_id": "session",
        "consumers": {"handoff": {"status": "pending", "attempts": 0}},
    }
    for number in range(total):
        (receipts / f"{number:04d}.json").write_text(json.dumps(receipt), encoding="utf-8")

    batch_sizes: list[int] = []
    while True:
        migrated, pending = consumer._migrate_legacy_receipts(receipts)
        batch_sizes.append(len(migrated))
        if not pending:
            break

    assert max(batch_sizes) <= consumer.MAX_MIGRATION_RECEIPTS
    assert len(list((receipts / consumer.ACTIVE_RECEIPT_DIR).glob("*.json"))) == total
    assert not list(receipts.glob("*.json"))


def test_check_rejects_corrupt_cursor_and_index_json(tmp_path: Path) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_strict_check")
    cursor = tmp_path / "cursor.json"
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    cursor.write_text("{broken", encoding="utf-8")
    assert consumer.check(cursor, receipts) == 1

    cursor.unlink()
    (receipts / consumer.ACTIVE_INDEX_NAME).write_text("{broken", encoding="utf-8")
    assert consumer.check(cursor, receipts) == 1


def test_check_rejects_corrupt_active_receipt_without_moving_it(tmp_path: Path) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_strict_active_check")
    receipts = tmp_path / "receipts"
    active = receipts / consumer.ACTIVE_RECEIPT_DIR
    active.mkdir(parents=True)
    corrupt = active / "broken.json"
    corrupt.write_text("{broken", encoding="utf-8")

    assert consumer.check(tmp_path / "cursor.json", receipts) == 1
    assert corrupt.read_text(encoding="utf-8") == "{broken"


def test_check_covers_active_receipts_beyond_heartbeat_batch_prefix(tmp_path: Path) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_full_active_check")
    receipts = tmp_path / "receipts"
    active = receipts / consumer.ACTIVE_RECEIPT_DIR
    active.mkdir(parents=True)
    valid = {
        "schema": consumer.RECEIPT_SCHEMA,
        "consumers": {"handoff": {"status": "pending", "attempts": 0}},
    }
    paths = []
    for number in range(129):
        path = active / f"{number:04d}.json"
        path.write_text(json.dumps(valid), encoding="utf-8")
        paths.append(path)
    bounded = set(consumer._bounded_active_paths(receipts, 128))
    unselected = next(path for path in paths if path not in bounded)
    unselected.write_text("{broken", encoding="utf-8")

    assert consumer.check(tmp_path / "cursor.json", receipts) == 1


def test_compatibility_append_is_idempotent_after_append_before_commit_crash(tmp_path: Path) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_compatibility_transaction")
    receipt = {
        "event_id": "event",
        "session_id": "session",
        "cwd": "/redacted/.worktrees/task",
        "last_seen_epoch": 100,
    }
    first = consumer._append_compatibility(tmp_path, receipt)
    marker = next((tmp_path / "logs" / "session-closeout-events").glob("*.json"))
    marker_state = json.loads(marker.read_text(encoding="utf-8"))
    marker_state["status"] = "prepared"
    marker.write_text(json.dumps(marker_state), encoding="utf-8")
    second = consumer._append_compatibility(tmp_path, receipt)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert len((tmp_path / "logs" / "session-closeout.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_append_transaction_recovers_partial_line_before_intervening_identity(tmp_path: Path) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_append_interleave")
    ledger = tmp_path / "ledger.jsonl"
    marker_root = tmp_path / "markers"
    marker_root.mkdir()
    first_payload = {"identity": "first", "value": 1}
    second_payload = {"identity": "second", "value": 2}
    first_line = (json.dumps(first_payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    first_marker = marker_root / "first.json"
    prepared = {
        "schema": consumer.APPEND_TRANSACTION_SCHEMA,
        "identity": "first",
        "status": "prepared",
        "offset": 0,
        "line_sha256": consumer.hashlib.sha256(first_line).hexdigest(),
        "line": first_line.decode("utf-8"),
        "marker": first_marker.name,
    }
    consumer._atomic_json(first_marker, prepared)
    consumer._atomic_json(marker_root / ".pending", prepared)
    ledger.write_bytes(first_line[: len(first_line) // 2])

    assert consumer._append_json_line_once(
        ledger,
        second_payload,
        marker_path=marker_root / "second.json",
        identity="second",
    )
    assert consumer._append_json_line_once(
        ledger,
        first_payload,
        marker_path=first_marker,
        identity="first",
    )

    assert [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()] == [
        first_payload,
        second_payload,
    ]


def test_atomic_json_is_byte_stable_when_payload_does_not_change(tmp_path: Path) -> None:
    consumer = _load(CONSUMER, "session_end_breadcrumb_consumer_atomic_json")
    path = tmp_path / "receipt.json"

    assert consumer._atomic_json(path, {"schema": "test", "value": 1}) is True
    before = path.stat()
    assert consumer._atomic_json(path, {"value": 1, "schema": "test"}) is False
    after = path.stat()

    assert after.st_ino == before.st_ino
    assert after.st_mtime_ns == before.st_mtime_ns


def test_settings_and_heartbeat_keep_slow_work_outside_session_end() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    handlers = settings["hooks"]["SessionEnd"][0]["hooks"]
    assert len(handlers) == 1
    assert handlers[0]["timeout"] <= 5
    assert "session-closeout.sh" in handlers[0]["command"]
    assert "CLAUDE_PROJECT_DIR" in handlers[0]["command"]
    assert "LIMEN_LIVE_ROOT" in handlers[0]["command"]
    assert "session-lifecycle-pressure.sh" not in json.dumps(handlers)
    closeout = (ROOT / "scripts" / "hooks" / "session-closeout.sh").read_text(encoding="utf-8")
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")
    assert "XDG_STATE_HOME" in closeout
    assert "--output" in closeout
    assert "consume-session-end-breadcrumbs.py" in heartbeat
    assert "XDG_STATE_HOME" in heartbeat
    assert "--source" in heartbeat
