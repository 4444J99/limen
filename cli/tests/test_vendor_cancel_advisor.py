"""Tests for scripts/vendor-cancel-advisor.py — the portable utilization-based cancel/keep verdict.

The advisor answers "cancel a vendor?" from UTILIZATION ONLY: a pool that hits its caps is KEEP (the
relief valve), an idle pool is a CANCEL-CANDIDATE, codex is always KEEP, and Fable-at-cap is named as
the real overspend. It exits non-zero only if it would ever contradict that doctrine.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_ADVISOR = Path(__file__).resolve().parents[2] / "scripts" / "vendor-cancel-advisor.py"


def _load_advisor():
    spec = importlib.util.spec_from_file_location("_advisor_under_test", _ADVISOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_usage(tmp_path: Path, vendors: dict) -> Path:
    p = tmp_path / "usage.json"
    p.write_text(json.dumps({"vendors": vendors}))
    return p


def test_codex_at_caps_is_keep_idle_vendor_is_candidate(tmp_path):
    adv = _load_advisor()
    usage = _write_usage(
        tmp_path,
        {
            # codex hitting its caps → relief valve → KEEP
            "codex": {"health": "rate-limited", "recent_rate_limit": True, "headroom_pct": 5},
            # opencode metered but nearly untouched across resets → CANCEL-CANDIDATE
            "opencode": {"health": "ok", "headroom_pct": 98},
        },
    )
    report = adv.advise(str(usage))
    verdicts = {v["vendor"]: v["verdict"] for v in report["verdicts"]}
    assert verdicts["codex"] == "KEEP"
    assert verdicts["opencode"] == "CANCEL-CANDIDATE"
    assert report["codex_keep"] is True
    assert report["ok"] is True
    assert "opencode" in report["cancel_candidates"]


def test_fable_over_cap_is_named_the_overspend(tmp_path, monkeypatch):
    adv = _load_advisor()
    usage = _write_usage(tmp_path, {"codex": {"health": "ok", "headroom_pct": 50}})
    bal = tmp_path / "fable-allotment.json"
    bal.write_text(json.dumps({"week": "x", "spent_pct": 100.0, "hard_cap": 50, "over_cap": True}))
    monkeypatch.setenv("LIMEN_FABLE_BALANCE_PATH", str(bal))
    report = adv.advise(str(usage))
    assert report["fable_over_cap"] is True
    assert "Fable" in report["real_overspend"]
    assert report["codex_keep"] is True
    assert report["ok"] is True


def test_never_cancels_a_capped_pool_self_check(tmp_path):
    """A capped pool can never be a CANCEL-CANDIDATE; the advisor's own self-check enforces it."""
    adv = _load_advisor()
    # Even with high headroom, a rate-limited pool is KEEP (busy health wins).
    usage = _write_usage(tmp_path, {"codex": {"health": "exhausted", "headroom_pct": 99}})
    report = adv.advise(str(usage))
    verdicts = {v["vendor"]: v["verdict"] for v in report["verdicts"]}
    assert verdicts["codex"] == "KEEP"
    assert report["contradictions"] == []
    assert report["ok"] is True


def test_no_usage_signal_defaults_keep(tmp_path):
    adv = _load_advisor()
    usage = _write_usage(tmp_path, {})  # no telemetry for any vendor
    report = adv.advise(str(usage))
    assert report["cancel_candidates"] == []
    assert all(v["verdict"] == "KEEP" for v in report["verdicts"])
    assert report["ok"] is True
