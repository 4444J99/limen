from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "codex-token-accounting.py"


def _iso(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_fixture(
    path: Path,
    sid: str = "fixture-session",
    base_time: dt.datetime | None = None,
    complete: bool = False,
) -> None:
    start = base_time or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2))
    rows = [
        {
            "timestamp": _iso(start),
            "type": "session_meta",
            "payload": {"id": sid},
        },
        {
            "timestamp": _iso(start + dt.timedelta(minutes=1)),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 1000,
                        "cached_input_tokens": 600,
                        "output_tokens": 50,
                        "reasoning_output_tokens": 20,
                        "total_tokens": 1050,
                    },
                    "last_token_usage": {
                        "input_tokens": 1000,
                        "cached_input_tokens": 600,
                        "output_tokens": 50,
                        "reasoning_output_tokens": 20,
                        "total_tokens": 1050,
                    },
                    "model_context_window": 121600,
                },
            },
        },
        {
            "timestamp": _iso(start + dt.timedelta(minutes=3)),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 1800,
                        "cached_input_tokens": 1000,
                        "output_tokens": 90,
                        "reasoning_output_tokens": 30,
                        "total_tokens": 1890,
                    },
                    "last_token_usage": {
                        "input_tokens": 800,
                        "cached_input_tokens": 400,
                        "output_tokens": 40,
                        "reasoning_output_tokens": 10,
                        "total_tokens": 840,
                    },
                    "model_context_window": 121600,
                },
            },
        },
    ]
    if complete:
        rows.append(
            {
                "timestamp": _iso(start + dt.timedelta(minutes=4)),
                "type": "event_msg",
                "payload": {"type": "task_complete"},
            }
        )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_codex_token_accounting_reports_uncached_and_phase_deltas(tmp_path: Path) -> None:
    fixture = tmp_path / "session.jsonl"
    report = tmp_path / "report.json"
    write_fixture(fixture)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(fixture),
            "--since-hours",
            "0",
            "--output",
            str(report),
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(report.read_text())
    session = payload["sessions"][0]
    assert session["session_id"] == "fixture-session"
    assert session["totals"]["cached_input_tokens"] == 1000
    assert session["totals"]["uncached_input_tokens"] == 800
    assert session["totals"]["output_tokens"] == 90
    assert session["totals"]["reasoning_output_tokens"] == 30
    assert session["totals"]["budget_tokens"] == 920
    assert session["phase_deltas"][1]["delta"]["uncached_input_tokens"] == 400
    assert session["phase_deltas"][1]["delta"]["budget_tokens"] == 450


def test_codex_token_accounting_fails_budget_gate(tmp_path: Path) -> None:
    fixture = tmp_path / "session.jsonl"
    write_fixture(fixture)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(fixture),
            "--since-hours",
            "0",
            "--max-budget-tokens",
            "900",
            "--no-write",
            "--fail-on-budget",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "budget_tokens=920" in result.stdout


def test_codex_token_accounting_active_gate_ignores_stale_failures(tmp_path: Path) -> None:
    fixture = tmp_path / "session.jsonl"
    report = tmp_path / "report.json"
    write_fixture(fixture, base_time=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(fixture),
            "--since-hours",
            "0",
            "--max-budget-tokens",
            "900",
            "--active-session-seconds",
            "60",
            "--output",
            str(report),
            "--fail-on-active-budget",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(report.read_text())
    assert payload["status"] == "fail"
    assert payload["active_status"] == "ok"
    assert payload["failures"] == ["fixture-session: budget_tokens=920"]
    assert payload["active_failures"] == []
    assert payload["historical_failures"] == ["fixture-session: budget_tokens=920"]
    assert payload["sessions"][0]["active"] is False


def test_codex_token_accounting_active_gate_fails_fresh_failures(tmp_path: Path) -> None:
    fixture = tmp_path / "session.jsonl"
    write_fixture(fixture)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(fixture),
            "--since-hours",
            "0",
            "--max-budget-tokens",
            "900",
            "--active-session-seconds",
            "3600",
            "--no-write",
            "--fail-on-active-budget",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "active_failures=1" in result.stdout


def test_codex_token_accounting_active_gate_ignores_completed_fresh_failures(tmp_path: Path) -> None:
    fixture = tmp_path / "session.jsonl"
    report = tmp_path / "report.json"
    write_fixture(fixture, complete=True)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(fixture),
            "--since-hours",
            "0",
            "--max-budget-tokens",
            "900",
            "--active-session-seconds",
            "3600",
            "--output",
            str(report),
            "--fail-on-active-budget",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(report.read_text())
    assert payload["status"] == "fail"
    assert payload["active_status"] == "ok"
    assert payload["active_failures"] == []
    assert payload["historical_failures"] == ["fixture-session: budget_tokens=920"]
    assert payload["sessions"][0]["active"] is False


def test_active_gate_ignores_current_codex_thread_by_default(tmp_path: Path) -> None:
    fixture = tmp_path / "session.jsonl"
    report = tmp_path / "report.json"
    write_fixture(fixture, sid="thread-123")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(fixture),
            "--since-hours",
            "0",
            "--max-budget-tokens",
            "900",
            "--active-session-seconds",
            "3600",
            "--output",
            str(report),
            "--fail-on-active-budget",
        ],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "CODEX_THREAD_ID": "thread-123"},
    )

    assert result.returncode == 0
    payload = json.loads(report.read_text())
    assert payload["status"] == "fail"
    assert payload["active_status"] == "ok"
    assert payload["active_failures"] == []
    assert payload["historical_failures"] == ["thread-123: budget_tokens=920"]
    assert payload["sessions"][0]["active"] is True
    assert payload["sessions"][0]["current_thread"] is True
    assert payload["sessions"][0]["active_gate_exclusion"] == "current-codex-thread"


def test_active_gate_can_include_current_codex_thread(tmp_path: Path) -> None:
    fixture = tmp_path / "session.jsonl"
    write_fixture(fixture, sid="thread-123")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(fixture),
            "--since-hours",
            "0",
            "--max-budget-tokens",
            "900",
            "--active-session-seconds",
            "3600",
            "--no-write",
            "--fail-on-active-budget",
            "--include-current-thread",
        ],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "CODEX_THREAD_ID": "thread-123"},
    )

    assert result.returncode == 2
    assert "active_failures=1" in result.stdout


def test_codex_token_accounting_active_gate_mixed_sessions(tmp_path: Path) -> None:
    """One fresh + one finished over-budget session: only the fresh one blocks."""
    fresh = tmp_path / "fresh.jsonl"
    stale = tmp_path / "stale.jsonl"
    report = tmp_path / "report.json"
    write_fixture(fresh, sid="fresh-session")
    write_fixture(stale, sid="stale-session", base_time=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(fresh),
            str(stale),
            "--since-hours",
            "0",
            "--max-budget-tokens",
            "900",
            "--active-session-seconds",
            "60",
            "--output",
            str(report),
            "--fail-on-active-budget",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(report.read_text())
    assert payload["status"] == "fail"
    assert payload["active_status"] == "fail"
    assert payload["active_failures"] == ["fresh-session: budget_tokens=920"]
    assert payload["historical_failures"] == ["stale-session: budget_tokens=920"]
    active_by_id = {s["session_id"]: s["active"] for s in payload["sessions"]}
    assert active_by_id == {"fresh-session": True, "stale-session": False}


def test_codex_token_accounting_active_seconds_zero_treats_all_active(tmp_path: Path) -> None:
    """--active-session-seconds 0 collapses back to strict --fail-on-budget semantics."""
    fixture = tmp_path / "session.jsonl"
    write_fixture(fixture, base_time=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(fixture),
            "--since-hours",
            "0",
            "--max-budget-tokens",
            "900",
            "--active-session-seconds",
            "0",
            "--no-write",
            "--fail-on-active-budget",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "active_status=fail" in result.stdout


def _load_accounting_module():
    spec = importlib.util.spec_from_file_location("codex_token_accounting", str(SCRIPT))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_active_helpers_fail_open_and_window() -> None:
    """Pin active liveness: token timestamp first, mtime fallback, zero-collapse."""
    mod = _load_accounting_module()
    now = dt.datetime(2026, 7, 1, 12, 0, 0, tzinfo=dt.timezone.utc)

    # Unknown liveness -> fail-open: NOT active, routed to historical.
    assert mod.session_age_seconds({}, now) is None
    assert mod.session_age_seconds({"mtime": None}, now) is None
    assert mod.is_active_session({}, now, 900) is False

    # active_seconds <= 0 -> every session counts as active (strict budget gate).
    assert mod.is_active_session({}, now, 0) is True
    assert mod.is_active_session({"last_token_at": None, "mtime": None}, now, 0) is True

    fresh = {"last_token_at": (now - dt.timedelta(seconds=30)).isoformat(timespec="seconds")}
    stale = {"last_token_at": (now - dt.timedelta(seconds=3600)).isoformat(timespec="seconds")}
    assert mod.is_active_session(fresh, now, 900) is True
    assert mod.is_active_session(stale, now, 900) is False
    assert mod.session_age_seconds(stale, now) == 3600

    touched_old_session = {
        "last_token_at": (now - dt.timedelta(seconds=3600)).isoformat(timespec="seconds"),
        "mtime": (now - dt.timedelta(seconds=10)).isoformat(timespec="seconds"),
    }
    assert mod.is_active_session(touched_old_session, now, 900) is False

    mtime_fallback = {"mtime": (now - dt.timedelta(seconds=30)).isoformat(timespec="seconds")}
    assert mod.is_active_session(mtime_fallback, now, 900) is True

    completed = {
        "last_token_at": (now - dt.timedelta(seconds=30)).isoformat(timespec="seconds"),
        "last_task_complete_at": (now - dt.timedelta(seconds=1)).isoformat(timespec="seconds"),
    }
    assert mod.session_age_seconds(completed, now) is None
    assert mod.is_active_session(completed, now, 900) is False

    restarted_after_completion = {
        "last_token_at": (now - dt.timedelta(seconds=30)).isoformat(timespec="seconds"),
        "last_task_started_at": (now - dt.timedelta(seconds=1)).isoformat(timespec="seconds"),
        "last_task_complete_at": (now - dt.timedelta(seconds=60)).isoformat(timespec="seconds"),
    }
    assert mod.is_active_session(restarted_after_completion, now, 900) is True


def test_default_scan_requires_live_resume_process_for_non_current_session(tmp_path: Path, monkeypatch) -> None:
    mod = _load_accounting_module()
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    fixture = sessions_root / "rollout-2026-07-09T09-10-15-019f4700-156d-73c3-9b07-d4b37711e2ec.jsonl"
    write_fixture(fixture, sid="019f4700-156d-73c3-9b07-d4b37711e2ec")
    monkeypatch.setattr(mod, "DEFAULT_SESSIONS_ROOT", sessions_root)
    monkeypatch.setattr(mod, "live_codex_resume_session_ids", lambda: set())
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("LIMEN_CODEX_TOKEN_GATE_REQUIRE_LIVE_PROCESS", raising=False)

    args = SimpleNamespace(
        paths=[],
        sessions_root=sessions_root,
        since_hours=0,
        limit_sessions=25,
        max_phases=0,
        warn_uncached_input=0,
        max_uncached_input=0,
        max_budget_tokens=900,
        max_elapsed_seconds=0,
        active_session_seconds=3600,
        include_current_thread=False,
    )

    report = mod.build_report(args)

    assert report["require_live_process_gate"] is True
    assert report["active_status"] == "ok"
    assert report["active_failures"] == []
    assert report["historical_failures"] == ["019f4700-156d-73c3-9b07-d4b37711e2ec: budget_tokens=920"]
    assert report["sessions"][0]["active"] is False
    assert report["sessions"][0]["active_gate_exclusion"] == "no-live-codex-resume-process"
