"""Tests for the insight-cadence producer."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "insight_cadence", Path(__file__).resolve().parent.parent.parent / "scripts" / "insight-cadence.py"
)
insight_cadence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(insight_cadence)


def _ts(dt):
    return dt.isoformat(timespec="seconds")


# ─── cadence gating: beat-time → calendar-time ───────────────────────


def test_due_tiers_first_run_all_due():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    assert set(insight_cadence.due_tiers({"last_run": {}}, now)) == {"hourly", "daily", "weekly", "monthly"}


def test_due_tiers_respects_elapsed():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    state = {
        "last_run": {
            "hourly": _ts(now - timedelta(minutes=30)),  # not yet (needs 60m)
            "daily": _ts(now - timedelta(hours=25)),  # due (needs 24h)
            "weekly": _ts(now - timedelta(days=2)),  # not yet (needs 7d)
            "monthly": _ts(now - timedelta(days=25)),  # not yet (needs 30d)
        }
    }
    due = insight_cadence.due_tiers(state, now)
    assert "hourly" not in due and "daily" in due and "weekly" not in due and "monthly" not in due


def test_due_tiers_respects_elapsed_monthly():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    state = {
        "last_run": {
            "monthly": _ts(now - timedelta(days=31)),  # due (needs 30d)
        }
    }
    due = insight_cadence.due_tiers(state, now)
    assert "monthly" in due


def test_force_tier_overrides_cadence():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    fresh = {"last_run": {"hourly": _ts(now)}}
    assert insight_cadence.due_tiers(fresh, now, force="hourly") == ["hourly"]


# ─── schema validation ───────────────────────────────────────────────


def test_schema_valid_report():
    report = insight_cadence._generate_report(
        "hourly",
        "2026-06-24T12:00:00+00:00",
        "2026-06-24T13:00:00+00:00",
        [
            {
                "id": "test-123",
                "severity": "info",
                "title": "Test Insight",
                "detail": "Test Detail",
                "owner": "anthony",
                "source": "test",
                "suggested_action": "Do nothing",
                "healable": True,
            }
        ],
    )

    assert report["tier"] == "hourly"
    assert report["generated_at"] == "2026-06-24T13:00:00+00:00"
    assert report["window_start"] == "2026-06-24T12:00:00+00:00"
    assert len(report["insights"]) == 1

    insight = report["insights"][0]
    assert "id" in insight
    assert insight["severity"] in ("critical", "warning", "info", "low")
    assert "title" in insight
    assert "detail" in insight
    assert "owner" in insight
    assert "source" in insight
    assert "suggested_action" in insight
    assert isinstance(insight["healable"], bool)


# ─── idempotency (sort of) ────────────────────────────────────────────


def test_idempotence_skips_when_window_not_elapsed():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    state = {
        "last_run": {
            "hourly": _ts(now - timedelta(minutes=10))  # ran 10m ago, not 60m yet
        }
    }

    # due_tiers should not return hourly
    due = insight_cadence.due_tiers(state, now)
    assert "hourly" not in due


# ─── suggestion-coverage gatherer (censor/insights-suggestions.jsonl) ──


def test_suggestion_coverage_flags_unaudited_snapshot(tmp_path, monkeypatch):
    archive = tmp_path / "snapshots"
    (archive / "2026-01-01T0000").mkdir(parents=True)
    (archive / "2026-02-02T0000").mkdir()
    root = tmp_path / "limen"
    (root / "censor").mkdir(parents=True)
    (root / "censor" / "insights-suggestions.jsonl").write_text(
        '{"cluster": "x", "reports": ["2026-01-01T0000"], "disposition": "exists"}\n'
    )
    monkeypatch.setenv("LIMEN_INSIGHTS_ARCHIVE", str(archive))
    monkeypatch.setattr(insight_cadence, "LIMEN_ROOT", root)

    flagged = [i for i in insight_cadence._gather_insights() if i["source"] == "insights-suggestions.jsonl"]
    assert any("2026-02-02T0000" in i["title"] for i in flagged), "uncovered snapshot must be flagged"
    assert not any("2026-01-01T0000" in i["title"] for i in flagged), "covered snapshot must not be flagged"


def test_suggestion_coverage_fails_open_without_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_INSIGHTS_ARCHIVE", str(tmp_path / "absent"))
    monkeypatch.setattr(insight_cadence, "LIMEN_ROOT", tmp_path)
    flagged = [i for i in insight_cadence._gather_insights() if i["source"] == "insights-suggestions.jsonl"]
    assert flagged == []


# ─── frictions field in snapshot reports ─────────────────────────────


def test_report_frictions_derived_from_warning_insights():
    """Every new snapshot report carries a structured frictions list (GAP-censor-3).

    Frictions are warning/critical insights promoted to the censor cascade;
    info/low insights are excluded so the lineage tool only clusters actionable items.
    """
    insights = [
        {
            "id": "a",
            "severity": "warning",
            "title": "Organ X is stale",
            "detail": "stale for 2h",
            "owner": "x",
            "source": "organ-health.json",
            "suggested_action": "restart",
            "healable": True,
        },
        {
            "id": "b",
            "severity": "critical",
            "title": "Budget exceeded",
            "detail": "burn > budget",
            "owner": "anthony",
            "source": "usage.json",
            "suggested_action": "reduce",
            "healable": True,
        },
        {
            "id": "c",
            "severity": "info",
            "title": "Nominal",
            "detail": "all good",
            "owner": "system",
            "source": "internal",
            "suggested_action": "none",
            "healable": True,
        },
        {
            "id": "d",
            "severity": "low",
            "title": "Minor note",
            "detail": "ok",
            "owner": "system",
            "source": "internal",
            "suggested_action": "none",
            "healable": True,
        },
    ]
    report = insight_cadence._generate_report(
        "hourly", "2026-07-15T00:00:00+00:00", "2026-07-15T01:00:00+00:00", insights
    )

    assert "frictions" in report, "snapshot report must carry a 'frictions' field"
    frictions = report["frictions"]

    # only warning+critical make it through
    assert len(frictions) == 2
    categories = {f["category"] for f in frictions}
    assert "Organ X is stale" in categories
    assert "Budget exceeded" in categories

    # each friction has required keys
    for f in frictions:
        assert "category" in f
        assert "description" in f
        assert "severity" in f

    # info/low not in frictions
    titles = {f["category"] for f in frictions}
    assert "Nominal" not in titles
    assert "Minor note" not in titles


def test_report_frictions_empty_when_no_warnings():
    """When all insights are info/low, frictions list is present but empty."""
    insights = [
        {
            "id": "c",
            "severity": "info",
            "title": "Nominal",
            "detail": "all good",
            "owner": "system",
            "source": "internal",
            "suggested_action": "none",
            "healable": True,
        },
    ]
    report = insight_cadence._generate_report(
        "daily", "2026-07-14T00:00:00+00:00", "2026-07-15T00:00:00+00:00", insights
    )
    assert report["frictions"] == []
