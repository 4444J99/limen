"""Offline unit tests for the conversion-funnel diagnosis (scripts/conversion-funnel.py).

Hermetic — no gh calls; synthetic traffic/inbound. Mirrors the importlib load pattern of the
other scripts/ tests.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "conversion-funnel.py"


def load():
    spec = importlib.util.spec_from_file_location("conversion_funnel", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = load()


def test_seen_stage_aggregates_and_skips_errors():
    rows = [
        {"repo": "a", "views": {"count": 10, "uniques": 5}, "referrers": [{"referrer": "Google", "uniques": 3}]},
        {"repo": "b", "views": {"count": 0, "uniques": 0}, "referrers": []},
        {"repo": "c", "views": {"_error": "403 no push access"}},  # skipped
    ]
    s = M.seen_stage(rows)
    assert s["views_14d"] == 10
    assert s["unique_visitors_14d"] == 5
    assert s["repos_measured"] == 2  # c errored → not counted
    assert s["repos_with_zero_views"] == 1  # b
    assert s["discovery_channels"][0]["channel"] == "Google"


def test_diagnose_discovery_when_unseen():
    seen = {"unique_visitors_14d": 56, "repos_measured": 16, "repos_with_zero_views": 9}
    assert M.diagnose(seen, {"leads_total": 0})["stage"] == "DISCOVERY"


def test_diagnose_face_offer_when_seen_but_no_inbound():
    seen = {"unique_visitors_14d": 500, "repos_measured": 16, "repos_with_zero_views": 0}
    assert M.diagnose(seen, {"leads_total": 0})["stage"] == "FACE/OFFER"


def test_diagnose_close_when_inbound_but_no_revenue():
    seen = {"unique_visitors_14d": 500, "repos_measured": 16, "repos_with_zero_views": 0}
    assert M.diagnose(seen, {"leads_total": 5})["stage"] == "CLOSE"


def test_inbound_stage_missing_file_degrades(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "OPP_STATUS", tmp_path / "nope.json")
    r = M.inbound_stage()
    assert r["available"] is False
    assert r["leads_total"] == 0


def test_gates_are_the_aug1_north_star():
    assert M.GATES["revenue_weekly_usd"] == 10000
