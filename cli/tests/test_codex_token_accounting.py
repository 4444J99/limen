from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "codex-token-accounting.py"


def write_fixture(path: Path) -> None:
    rows = [
        {
            "timestamp": "2026-06-30T12:00:00Z",
            "type": "session_meta",
            "payload": {"id": "fixture-session"},
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
