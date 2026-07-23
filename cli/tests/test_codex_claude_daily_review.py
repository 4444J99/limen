from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "codex-claude-daily-review.py"


def _load():
    spec = importlib.util.spec_from_file_location("codex_claude_daily_review", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _session(path: Path, sid: str, first: str, last: str | None, budget: int, *, active: bool = False) -> dict:
    return {
        "session_id": sid,
        "path": str(path),
        "first_token_at": first,
        "last_token_at": last or first,
        "mtime": last or first,
        "elapsed_seconds": 60,
        "active": active,
        "totals": {
            "input_tokens": budget + 10,
            "cached_input_tokens": 10,
            "uncached_input_tokens": budget,
            "output_tokens": 100,
            "reasoning_output_tokens": 20,
            "total_tokens": budget + 110,
            "budget_tokens": budget + 120,
        },
    }


def test_local_day_window_filters_codex_sessions_at_edt_boundaries(tmp_path: Path) -> None:
    review = _load()
    tz = ZoneInfo("America/New_York")
    now = dt.datetime(2026, 7, 9, 12, 0, tzinfo=dt.UTC)
    since, until = review.local_day_window("2026-07-08", local_tz=tz, now=now)

    assert review.iso_z(since) == "2026-07-08T04:00:00Z"
    assert review.iso_z(until) == "2026-07-09T04:00:00Z"

    raw = {
        "sessions": [
            _session(tmp_path / "before.jsonl", "before", "2026-07-08T03:59:59Z", None, 100),
            _session(tmp_path / "start.jsonl", "start", "2026-07-08T04:00:00Z", None, 200, active=True),
            _session(tmp_path / "late.jsonl", "late", "2026-07-09T03:59:59Z", None, 300),
            _session(tmp_path / "after.jsonl", "after", "2026-07-09T04:00:00Z", None, 400),
        ],
        "thresholds": {"max_budget_tokens": 300},
        "failures": ["start: budget_tokens=320", "after: budget_tokens=520"],
        "active_failures": ["start: budget_tokens=320"],
        "historical_failures": ["after: budget_tokens=520"],
        "warnings": [],
        "active_warnings": [],
    }

    codex = review.summarize_codex(
        raw,
        since,
        until,
        generated_at=dt.datetime(2026, 7, 9, 5, 0, tzinfo=dt.UTC),
    )

    assert [session["session_id"] for session in codex["sessions"]] == ["start", "late"]
    assert codex["aggregate_totals"]["budget_tokens"] == 320 + 420
    assert codex["active_failures"] == []
    assert codex["historical_failures"] == ["start: budget_tokens=320", "late: budget_tokens=420"]


def test_current_local_day_window_ends_at_now() -> None:
    review = _load()
    tz = ZoneInfo("America/New_York")
    now = dt.datetime(2026, 7, 8, 15, 30, tzinfo=dt.UTC)

    since, until = review.local_day_window("2026-07-08", local_tz=tz, now=now)

    assert review.iso_z(since) == "2026-07-08T04:00:00Z"
    assert review.iso_z(until) == "2026-07-08T15:30:00Z"


def test_claude_summary_aggregates_guard_json_with_fable_and_subagents() -> None:
    review = _load()
    reports = [
        {
            "ok": False,
            "session": "claude-a",
            "path": "/tmp/claude-a.jsonl",
            "files": ["/tmp/claude-a.jsonl", "/tmp/claude-a/subagents/agent.jsonl"],
            "usageMessages": 2,
            "billableTokens": 2_500_000,
            "opusBillableTokens": 1_500_000,
            "fableBillableTokens": 1_100_000,
            "outputTokens": 20_000,
            "cacheReadTokens": 500_000,
            "agentCalls": 9,
            "expensiveSubagents": 2,
            "fableSubagents": 1,
            "fableAcceptanceSeen": False,
            "violations": [
                "Fable run lacks written acceptance command",
                "agent/workflow fanout exceeded (9 > 8)",
            ],
        },
        {
            "ok": True,
            "session": "claude-b",
            "path": "/tmp/claude-b.jsonl",
            "files": ["/tmp/claude-b.jsonl"],
            "usageMessages": 1,
            "billableTokens": 10,
            "opusBillableTokens": 0,
            "fableBillableTokens": 0,
            "outputTokens": 5,
            "cacheReadTokens": 0,
            "agentCalls": 0,
            "expensiveSubagents": 0,
            "fableSubagents": 0,
            "fableAcceptanceSeen": False,
            "violations": [],
        },
    ]

    claude = review.summarize_claude(reports)

    assert claude["session_count"] == 2
    assert claude["failed_count"] == 1
    assert claude["totals"]["billableTokens"] == 2_500_010
    assert claude["totals"]["opusBillableTokens"] == 1_500_000
    assert claude["totals"]["fableBillableTokens"] == 1_100_000
    assert claude["totals"]["expensiveSubagents"] == 2
    assert claude["unaccepted_fable_sessions"] == ["claude-a"]
    assert claude["threshold_violation_sessions"] == ["claude-a"]
    assert claude["violation_counts"]["Fable run lacks written acceptance command"] == 1


def test_markdown_report_omits_raw_prompt_bodies() -> None:
    review = _load()
    raw_prompt = "RAW_PROMPT_BODY_SHOULD_NOT_APPEAR keep going until ideal form"
    payload = {
        "date": "2026-07-08",
        "generated_at": "2026-07-09T04:01:00Z",
        "window": {
            "since": "2026-07-08T04:00:00Z",
            "until": "2026-07-09T04:00:00Z",
            "timezone": "America/New_York",
        },
        "snapshot_at": "2026-07-09T01:15:22Z",
        "verdict": "High activity created code movement, but session-lifecycle closure did not justify the premium-model spend.",
        "codex": {
            "session_count": 1,
            "active_status": "ok",
            "aggregate_totals": {
                "budget_tokens": 100,
                "uncached_input_tokens": 70,
                "output_tokens": 20,
                "reasoning_output_tokens": 10,
            },
            "active_failures": [],
            "historical_failures": ["old: budget_tokens=100"],
            "top_sessions_by_budget": [],
        },
        "claude": {
            "session_count": 1,
            "failed_count": 1,
            "totals": {
                "billableTokens": 2_000_001,
                "opusBillableTokens": 900_000,
                "fableBillableTokens": 0,
                "agentCalls": 9,
                "expensiveSubagents": 2,
                "fableSubagents": 0,
            },
            "unaccepted_fable_sessions": [],
            "violation_counts": {"agent/workflow fanout exceeded (9 > 8)": 1},
            "top_sessions_by_billable": [
                {
                    "session_id": "claude-a",
                    "billableTokens": 2_000_001,
                    "opusBillableTokens": 900_000,
                    "fableBillableTokens": 0,
                    "agentCalls": 9,
                    "ok": False,
                    "unboundedGoalEvidence": [{"text": raw_prompt}],
                }
            ],
        },
        "value_context": {"metrics": {"commits": 186, "batch_receipts": 0, "prompt_events_recorded": 0}},
        "violations": [
            {
                "code": "claude_thresholds",
                "summary": "1 Claude session crossed spend or fanout guard thresholds.",
                "evidence": ["claude-a"],
            }
        ],
        "outputs": {"private_json": ".limen-private/session-corpus/daily-reviews/codex-claude-2026-07-08.json"},
    }

    markdown = review.render_markdown(payload)

    assert raw_prompt not in markdown
    assert "Codex/Claude Session Review" in markdown
    assert "prompt-batch receipts" in markdown
