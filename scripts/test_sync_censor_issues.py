"""Tests for the censor→GitHub mirror's pure core — plan derivation + case-law matching.

No network, no gh: these cover the decision logic only (create/close/keep/veto/cap),
the marker identity, and the precedent annotation lookup.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sync_censor_issues", Path(__file__).resolve().parent / "sync-censor-issues.py")
sci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sci)


def _warn(rid, title="Recurring friction across 4 insights reports: Shallow first approach"):
    return {"id": rid, "severity": "warning", "title": title, "detail": "d", "source": "s"}


def _info(rid):
    return {"id": rid, "severity": "info", "title": "resolved", "detail": "d"}


# ─── plan(): the create/close/keep/veto derivation ───────────────────────────

def test_new_warning_creates():
    p = sci.plan([_warn("a")], {})
    assert p["create"] == ["a"] and not p["close"] and not p["keep"]


def test_info_never_creates():
    p = sci.plan([_info("a")], {})
    assert not p["create"]


def test_open_issue_for_live_warning_is_kept():
    p = sci.plan([_warn("a")], {"a": {"number": 7, "state": "OPEN"}})
    assert p["keep"] == [("a", 7)] and not p["create"] and not p["close"]


def test_cleared_residual_closes_its_issue():
    p = sci.plan([], {"a": {"number": 7, "state": "OPEN"}})
    assert p["close"] == [("a", 7)]


def test_warning_downgraded_to_info_closes():
    p = sci.plan([_info("a")], {"a": {"number": 7, "state": "OPEN"}})
    assert p["close"] == [("a", 7)]


def test_human_close_is_a_veto_never_reopened():
    p = sci.plan([_warn("a")], {"a": {"number": 7, "state": "CLOSED"}})
    assert p["vetoed"] == [("a", 7)] and not p["create"] and not p["close"]


def test_cap_defers_never_floods():
    residuals = [_warn(f"r{i}") for i in range(12)]
    p = sci.plan(residuals, {}, cap=8)
    assert len(p["create"]) == 8 and len(p["deferred"]) == 4


def test_closed_issue_for_cleared_residual_stays_untouched():
    p = sci.plan([], {"a": {"number": 7, "state": "CLOSED"}})
    assert not p["close"] and not p["vetoed"]


# ─── identity: the body marker ───────────────────────────────────────────────

def test_marker_roundtrip():
    body = sci.body_for(_warn("insights-lineage-71ea8fa3"), None)
    m = sci.MARKER_RE.search(body)
    assert m and m.group(1) == "insights-lineage-71ea8fa3"


# ─── case-law annotation ─────────────────────────────────────────────────────

PRECS = [{"id": "PREC-2026-07-04-friction-shallow-first", "type": "recurring_friction",
          "subject": "Shallow first approach", "outcome": "applied-ok",
          "action": "CLAUDE.md § Engage the Real Problem First"}]


def test_precedent_matches_by_subject_in_title():
    pc = sci.precedent_for(_warn("a"), PRECS)
    assert pc and pc["id"] == "PREC-2026-07-04-friction-shallow-first"


def test_precedent_ignores_bad_outcome():
    bad = [dict(PRECS[0], outcome="bad")]
    assert sci.precedent_for(_warn("a"), bad) is None


def test_precedent_miss_returns_none():
    assert sci.precedent_for(_warn("a", title="something else entirely"), PRECS) is None


def test_codified_body_names_the_empirical_close():
    body = sci.body_for(_warn("a"), PRECS[0])
    assert "PREC-2026-07-04-friction-shallow-first" in body and "empirical close" in body
