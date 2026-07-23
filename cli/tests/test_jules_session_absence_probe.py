from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import limen.dispatch as dispatch_module
import limen.jules_remote as jr
import pytest
from limen.dispatch import release_stale_tasks
from limen.io import load_limen_file, save_limen_file
from limen.jules_remote import (
    JulesRemoteSession,
    JulesRemoteSnapshot,
    JulesSessionAbsenceProbe,
    classify_jules_claim,
    probe_jules_remote_session_absence,
    probe_jules_remote_session_absences,
)
from limen.models import Budget, BudgetTrack, DispatchLogEntry, LimenFile, Portal, Task

SID = "12345678901234567890"
OTHER_SID = "98765432109876543210"


def _api_error(*, code: object = 404, status: object = "NOT_FOUND", extra: dict | None = None) -> bytes:
    payload: dict[str, object] = {
        "error": {
            "code": code,
            "message": "Requested entity was not found.",
            "status": status,
        }
    }
    if extra:
        payload.update(extra)
    return b"Error: api error: status 404, content: " + json.dumps(payload).encode() + b"\n"


def _runner_with(output: bytes, *, returncode: int = 0):
    def runner(command, timeout, output_limit):
        assert timeout > 0
        assert output_limit > 0
        assert command == ("jules-test", "remote", "pull", "--session", SID)
        assert "--apply" not in command
        return jr._BoundedCommandResult(returncode=returncode, output=output)

    return runner


def _write_stale_board(path: Path) -> None:
    stale = datetime(2026, 1, 1, tzinfo=UTC)
    save_limen_file(
        path,
        LimenFile(
            portal=Portal(budget=Budget(daily=100, track=BudgetTrack(date="2026-01-01"))),
            tasks=[
                Task(
                    id="STALE",
                    title="stale Jules claim",
                    repo="organvm/example",
                    target_agent="jules",
                    status="dispatched",
                    created=date(2026, 1, 1),
                    dispatch_log=[
                        DispatchLogEntry(
                            timestamp=stale,
                            agent="jules",
                            session_id=SID,
                            status="dispatched",
                        )
                    ],
                )
            ],
        ),
    )


def test_exact_structured_not_found_confirms_absence_despite_zero_exit() -> None:
    result = probe_jules_remote_session_absence(
        SID,
        binary="jules-test",
        runner=_runner_with(_api_error(), returncode=0),
    )

    assert result == JulesSessionAbsenceProbe(session_id=SID, outcome="confirmed_absent")
    assert result.confirmed_absent is True


@pytest.mark.parametrize(
    "output",
    [
        b"404 NOT_FOUND",
        b"Error: api error: status 404, content: not-json\n",
        _api_error(code="404"),
        _api_error(code=401),
        _api_error(status="PERMISSION_DENIED"),
        _api_error(extra={"transport": "proxy"}),
        _api_error() + b"unexpected trailing response",
        b"patch pulled successfully\n",
        b"",
    ],
)
def test_ambiguous_malformed_auth_and_nonexact_responses_never_confirm(output: bytes) -> None:
    result = probe_jules_remote_session_absence(
        SID,
        binary="jules-test",
        runner=_runner_with(output, returncode=1),
    )

    assert result.outcome == "response_unconfirmed"
    assert result.confirmed_absent is False


@pytest.mark.parametrize("failure", ["timeout", "output_truncated", "cli_unavailable", "pipe_unavailable"])
def test_process_failures_remain_unknown(failure: str) -> None:
    def runner(_command, _timeout, _output_limit):
        return jr._BoundedCommandResult(returncode=None, failure=failure)

    result = probe_jules_remote_session_absence(SID, runner=runner)

    assert result.outcome == failure
    assert result.confirmed_absent is False


def test_malformed_session_id_never_launches_cli() -> None:
    def runner(*_args):  # pragma: no cover - the assertion is that this is never reached
        raise AssertionError("malformed session ID reached subprocess runner")

    result = probe_jules_remote_session_absence("not-a-session", runner=runner)

    assert result.outcome == "invalid_session_id"
    assert result.confirmed_absent is False


def test_bounded_runner_stops_output_overflow() -> None:
    result = jr._run_bounded_command(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 4096); sys.stdout.flush()"],
        timeout=2,
        output_limit=64,
    )

    assert result.failure == "output_truncated"
    assert result.output == b""


def test_bounded_runner_stops_timeout() -> None:
    result = jr._run_bounded_command(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        timeout=0.05,
        output_limit=64,
    )

    assert result.failure == "timeout"
    assert result.output == b""


def test_catalog_enrichment_probes_only_missing_sessions_and_preserves_known_states() -> None:
    snapshot = JulesRemoteSnapshot(
        available=True,
        sessions={
            SID: JulesRemoteSession(SID, "completed"),
            OTHER_SID: JulesRemoteSession(OTHER_SID, "awaiting_user_feedback"),
        },
    )
    missing_absent = "11111111111111111111"
    missing_ambiguous = "22222222222222222222"
    calls: list[str] = []

    def probe(session_id: str, **_kwargs) -> JulesSessionAbsenceProbe:
        calls.append(session_id)
        outcome = "confirmed_absent" if session_id == missing_absent else "timeout"
        return JulesSessionAbsenceProbe(session_id=session_id, outcome=outcome)

    enriched = probe_jules_remote_session_absences(
        snapshot,
        [SID, OTHER_SID, missing_absent, missing_ambiguous, missing_absent],
        probe=probe,
    )

    assert calls == [missing_absent, missing_ambiguous]
    assert classify_jules_claim(enriched, SID) == ("harvest", "completed")
    assert classify_jules_claim(enriched, OTHER_SID) == ("recover", "awaiting_user_feedback")
    assert classify_jules_claim(enriched, missing_absent) == ("release", "absent")
    assert classify_jules_claim(enriched, missing_ambiguous) == ("hold", "absence_unconfirmed")
    assert enriched.absence_probe_outcomes == {
        missing_absent: "confirmed_absent",
        missing_ambiguous: "timeout",
    }


def test_total_probe_budget_exhaustion_holds_every_unprobed_session() -> None:
    snapshot = JulesRemoteSnapshot(available=True, sessions={})

    def probe(*_args, **_kwargs):  # pragma: no cover - zero budget must prevent this call
        raise AssertionError("probe ran after total budget was exhausted")

    enriched = probe_jules_remote_session_absences(
        snapshot,
        [SID, OTHER_SID],
        total_timeout=0,
        probe=probe,
    )

    assert enriched.confirmed_absent == frozenset()
    assert enriched.absence_probe_outcomes == {SID: "budget_exhausted", OTHER_SID: "budget_exhausted"}
    assert classify_jules_claim(enriched, SID) == ("hold", "absence_unconfirmed")


def test_release_stale_consumes_session_specific_absence_before_board_lock(tmp_path: Path, monkeypatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    _write_stale_board(tasks_path)
    catalog = JulesRemoteSnapshot(available=True, sessions={}, exhaustive=False)
    calls: list[tuple[str, ...]] = []
    inside_lock = False

    monkeypatch.setattr(dispatch_module, "probe_jules_remote_sessions", lambda: catalog)

    def enrich(snapshot: JulesRemoteSnapshot, session_ids) -> JulesRemoteSnapshot:
        assert inside_lock is False
        observed = tuple(session_ids)
        calls.append(observed)
        assert observed == (SID,)
        return replace(
            snapshot,
            confirmed_absent=frozenset({SID}),
            absence_probe_outcomes={SID: "confirmed_absent"},
        )

    @contextmanager
    def queue_lock(_path):
        nonlocal inside_lock
        inside_lock = True
        try:
            yield True
        finally:
            inside_lock = False

    monkeypatch.setattr(dispatch_module, "probe_jules_remote_session_absences", enrich)
    monkeypatch.setattr(dispatch_module, "_queue_lock", queue_lock)

    report = release_stale_tasks(load_limen_file(tasks_path), tasks_path, hours=24, dry_run=False)
    task = load_limen_file(tasks_path).tasks[0]

    assert calls == [(SID,)]
    assert task.status == "open"
    assert report["released"] == ["STALE"]
    assert report["remote_probe"]["session_probe_outcomes"] == {"confirmed_absent": 1}
