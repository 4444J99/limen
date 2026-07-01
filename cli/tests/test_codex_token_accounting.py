from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "codex-token-accounting.py"


def write_fixture(path: Path, sid: str = "fixture-session") -> None:
    rows = [
        {
            "timestamp": "2026-06-30T12:00:00Z",
            "type": "session_meta",
            "payload": {"id": sid},
        },
        {
            "timestamp": "2026-06-30T12:01:00Z",
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
            "timestamp": "2026-06-30T12:03:00Z",
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
    write_fixture(fixture)
    stale = time.time() - 3600
    os.utime(fixture, (stale, stale))

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


def test_codex_token_accounting_active_gate_mixed_sessions(tmp_path: Path) -> None:
    """One fresh + one finished over-budget session: only the fresh one blocks."""
    fresh = tmp_path / "fresh.jsonl"
    stale = tmp_path / "stale.jsonl"
    report = tmp_path / "report.json"
    write_fixture(fresh, sid="fresh-session")
    write_fixture(stale, sid="stale-session")
    old = time.time() - 3600
    os.utime(stale, (old, old))

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
    write_fixture(fixture)
    old = time.time() - 86400
    os.utime(fixture, (old, old))

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
    """Pin the liveness contract: fail-open on unknown mtime, window boundary, zero-collapse."""
    mod = _load_accounting_module()
    now = dt.datetime(2026, 7, 1, 12, 0, 0, tzinfo=dt.timezone.utc)

    # Unknown liveness (no / null mtime) -> fail-open: NOT active, routed to historical.
    assert mod.session_age_seconds({}, now) is None
    assert mod.session_age_seconds({"mtime": None}, now) is None
    assert mod.is_active_session({}, now, 900) is False

    # active_seconds <= 0 -> every session counts as active (strict budget gate).
    assert mod.is_active_session({}, now, 0) is True
    assert mod.is_active_session({"mtime": None}, now, 0) is True

    fresh = {"mtime": (now - dt.timedelta(seconds=30)).isoformat(timespec="seconds")}
    stale = {"mtime": (now - dt.timedelta(seconds=3600)).isoformat(timespec="seconds")}
    assert mod.is_active_session(fresh, now, 900) is True
    assert mod.is_active_session(stale, now, 900) is False
    assert mod.session_age_seconds(stale, now) == 3600
