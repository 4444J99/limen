from __future__ import annotations

import copy
import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from limen.io import load_limen_file, save_limen_file
from limen.models import LimenFile, Task
from limen.tabularius import drain_once, tickets_root

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply-ask-gate-owner-contracts.py"


def _module():
    spec = importlib.util.spec_from_file_location("apply_ask_gate_owner_contracts", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _task(number: int, *, legacy_pass: bool = False) -> Task:
    return Task(
        id=f"LIMEN-{number}",
        title=("Checks go green for imported issue" if legacy_pass else f"Imported issue {number}"),
        description="One exact owner issue.",
        repo="organvm/peer-audited--behavioral-blockchain",
        target_agent="codex",
        status="open",
        urls=[f"https://github.com/organvm/peer-audited--behavioral-blockchain/issues/{number}"],
        context="Ingested via script",
        created=date(2026, 7, 19),
    )


def _fixture(tmp_path: Path, monkeypatch) -> tuple[object, Path, dict]:
    compiler = _module()
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, LimenFile(tasks=[_task(11), _task(12), _task(13, legacy_pass=True)]))
    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(compiler, "EXPECTED_COUNT", 2)
    monkeypatch.setattr(compiler, "DEFAULT_RECEIPT", receipt)
    payload = compiler.build_receipt(board, generated_at="2026-07-25T16:39:34Z", expected_count=2)
    receipt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return compiler, board, payload


def test_receipt_freezes_only_real_split_cohort(tmp_path: Path, monkeypatch) -> None:
    compiler, _board, payload = _fixture(tmp_path, monkeypatch)

    assert payload["expected_count"] == 2
    assert payload["source_candidate_count"] == 3
    assert [row["task_id"] for row in payload["rows"]] == ["LIMEN-11", "LIMEN-12"]
    assert payload["baseline"] == {"intake_window_tasks": 404, "split_tasks": 297}
    assert compiler.verify_receipt(payload, expected_count=2) == payload["cohort_sha256"]
    for row in payload["rows"]:
        assert row["receipt_target"] == row["source_url"]
        assert "gh issue view" in row["predicate"]
        assert row["predicate"].endswith("= CLOSED")


def test_compilation_is_deterministic_exact_and_append_only(tmp_path: Path, monkeypatch) -> None:
    compiler, board, payload = _fixture(tmp_path, monkeypatch)
    timestamp = compiler.parse_timestamp("2026-07-25T16:40:00Z")
    first, state = compiler.compile_tickets(
        payload,
        board,
        timestamp=timestamp,
        agent="codex",
        session_id="first",
    )
    retry, retry_state = compiler.compile_tickets(
        payload,
        board,
        timestamp=timestamp + timedelta(minutes=5),
        agent="agy",
        session_id="retry",
    )

    assert state == retry_state == {"pending": 2, "present": 0}
    assert [ticket.ticket_id for ticket in first] == [ticket.ticket_id for ticket in retry]
    assert len({ticket.ticket_id for ticket in first}) == 2
    assert all(ticket.intent == "task.upsert" for ticket in first)
    assert all(set(ticket.patch or {}) == {"predicate", "receipt_target"} for ticket in first)
    assert all(ticket.precondition and set(ticket.precondition) == {"status", "task_sha256"} for ticket in first)
    assert all(ticket.log and ticket.log["status"] == "open" for ticket in first)


def test_keeper_round_trip_verifies_and_retries_idempotently(tmp_path: Path, monkeypatch) -> None:
    compiler, board, payload = _fixture(tmp_path, monkeypatch)
    timestamp = compiler.parse_timestamp("2026-07-25T16:40:00Z")
    tickets, _ = compiler.compile_tickets(
        payload,
        board,
        timestamp=timestamp,
        agent="codex",
        session_id="round-trip",
    )

    assert compiler.submit_compiled_tickets(board, tickets) == {"submitted": 2, "pending": 0, "archived": 0}
    drained = drain_once(board)
    assert (drained.applied, drained.rejected) == (2, 0)
    assert compiler.verify_applied(payload, board) == {"verified": 2, "pending": 0, "rejected": 0}

    retry, state = compiler.compile_tickets(
        payload,
        board,
        timestamp=timestamp + timedelta(hours=1),
        agent="agy",
        session_id="retry",
    )
    assert state == {"pending": 0, "present": 2}
    assert compiler.submit_compiled_tickets(board, retry) == {"submitted": 0, "pending": 0, "archived": 2}
    assert compiler.verify_applied(payload, board) == {"verified": 2, "pending": 0, "rejected": 0}


def test_canonical_tamper_and_live_drift_fail_closed(tmp_path: Path, monkeypatch) -> None:
    compiler, board, payload = _fixture(tmp_path, monkeypatch)
    timestamp = compiler.parse_timestamp("2026-07-25T16:40:00Z")
    broken = copy.deepcopy(payload)
    broken["rows"][0]["predicate"] = "true"
    with pytest.raises(compiler.MigrationError, match="differs from the canonical"):
        compiler.compile_tickets(
            broken,
            board,
            timestamp=timestamp,
            agent="codex",
            session_id="tamper",
        )

    live = load_limen_file(board)
    live.tasks[0] = live.tasks[0].model_copy(update={"title": "Concurrent owner edit"})
    save_limen_file(board, live)
    with pytest.raises(compiler.MigrationError, match="source state drifted"):
        compiler.compile_tickets(
            payload,
            board,
            timestamp=timestamp,
            agent="codex",
            session_id="drift",
        )


def test_partial_contract_and_rejected_ticket_submit_no_prefix(tmp_path: Path, monkeypatch) -> None:
    compiler, board, payload = _fixture(tmp_path, monkeypatch)
    timestamp = compiler.parse_timestamp("2026-07-25T16:40:00Z")
    live = load_limen_file(board)
    live.tasks[0] = live.tasks[0].model_copy(update={"predicate": payload["rows"][0]["predicate"]})
    save_limen_file(board, live)
    with pytest.raises(compiler.MigrationError, match="partial or different owner contract"):
        compiler.compile_tickets(
            payload,
            board,
            timestamp=timestamp,
            agent="codex",
            session_id="partial",
        )

    save_limen_file(board, LimenFile(tasks=[_task(11), _task(12), _task(13, legacy_pass=True)]))
    tickets, _ = compiler.compile_tickets(
        payload,
        board,
        timestamp=timestamp,
        agent="codex",
        session_id="reject",
    )
    reason = tickets_root(board) / "rejected" / f"{tickets[-1].ticket_id}.json.reason.txt"
    reason.parent.mkdir(parents=True, exist_ok=True)
    reason.write_text("synthetic rejection", encoding="utf-8")
    with pytest.raises(compiler.MigrationError, match="was rejected"):
        compiler.submit_compiled_tickets(board, tickets)
    assert not list((tickets_root(board) / "inbox").glob("*.json"))
