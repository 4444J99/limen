"""Tests for the Censor's constitutional core — the cascade + separation of powers.

These cover the PURE decision logic (no actuators): cadence gating, protocol
matching, disposition derivation, and the protocol→precedent→exploration cascade.
"""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location("censor", Path(__file__).resolve().parent / "censor.py")
censor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(censor)


PROTOCOLS = [
    {"id": "PROTO-LANE-REWEIGHT", "when": {"signal": "lane_adjustment", "verdict_in": ["down-weight", "keep"]},
     "action": "apply weights", "reversible": "reversible", "branch": "executive"},
    {"id": "PROTO-RETIRE-PATTERN", "when": {"signal": "retire_pattern"},
     "action": "supersede", "reversible": "irreversible", "branch": "judicial"},
    {"id": "PROTO-BEHAVIOURAL", "when": {"signal": "recurring_friction", "codified": "no"},
     "action": "codify correction", "reversible": "gated", "branch": "judicial",
     "his_lever": "behavioural-rule"},
    {"id": "PROTO-ORGAN-STALE", "when": {"signal": "organ_health", "status_in": ["stale", "down"]},
     "action": "recommend heal", "reversible": "gated", "branch": "judicial"},
]


def _ts(dt):
    return dt.isoformat(timespec="seconds")


# ─── cadence gating: beat-time → calendar-time ───────────────────────

def test_due_tiers_first_run_all_due():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    assert set(censor.due_tiers({"last_run": {}}, now)) == {"hourly", "daily", "weekly", "monthly"}


def test_due_tiers_respects_elapsed():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    state = {"last_run": {
        "hourly": _ts(now - timedelta(minutes=30)),   # not yet (needs 60m)
        "daily": _ts(now - timedelta(hours=25)),       # due (needs 24h)
        "weekly": _ts(now - timedelta(days=2)),        # not yet (needs 7d)
        "monthly": _ts(now - timedelta(days=25)),      # not yet (needs 30d)
    }}
    due = censor.due_tiers(state, now)
    assert "hourly" not in due and "daily" in due and "weekly" not in due and "monthly" not in due


def test_due_tiers_respects_elapsed_monthly():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    state = {"last_run": {
        "monthly": _ts(now - timedelta(days=31)),      # due (needs 30d)
    }}
    due = censor.due_tiers(state, now)
    assert "monthly" in due


def test_force_tier_overrides_cadence():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    fresh = {"last_run": {"hourly": _ts(now)}}
    assert censor.due_tiers(fresh, now, force="hourly") == ["hourly"]


# ─── LEGISLATIVE: protocol matching ──────────────────────────────────

def test_match_protocol_membership():
    sig = {"type": "lane_adjustment", "verdict": "down-weight", "subject": "opencode"}
    assert censor.match_protocol(sig, PROTOCOLS)["id"] == "PROTO-LANE-REWEIGHT"


def test_match_protocol_membership_miss():
    sig = {"type": "lane_adjustment", "verdict": "up-weight"}   # not in [down-weight, keep]
    assert censor.match_protocol(sig, PROTOCOLS) is None


def test_match_protocol_no_match_returns_none():
    assert censor.match_protocol({"type": "unknown_signal"}, PROTOCOLS) is None


# ─── autonomy is DERIVED, never a dial ───────────────────────────────

def test_reversible_executive_is_auto():
    assert censor.disposition_for(PROTOCOLS[0]) == "auto"


def test_irreversible_is_never_auto():
    assert censor.disposition_for(PROTOCOLS[1]) == "propose"


def test_his_lever_always_surfaces():
    assert censor.disposition_for(PROTOCOLS[2]) == "surface"


def test_gated_judicial_is_propose_not_auto():
    assert censor.disposition_for(PROTOCOLS[3]) == "propose"


# ─── THE CASCADE: protocol → precedent → exploration ─────────────────

def test_cascade_protocol_wins_first():
    sig = {"type": "lane_adjustment", "verdict": "keep", "subject": "codex"}
    v = censor.cascade(sig, PROTOCOLS, [])
    assert v["branch"] == "protocol" and v["disposition"] == "auto"


def test_cascade_falls_to_precedent_when_no_protocol():
    sig = {"type": "novel_signal", "subject": "x"}
    precedents = [{"type": "novel_signal", "subject": "x", "action": "did-this",
                   "outcome": "good", "reversible": "reversible", "id": "PC-1"}]
    v = censor.cascade(sig, PROTOCOLS, precedents)
    assert v["branch"] == "precedent" and v["disposition"] == "auto"


def test_cascade_precedent_irreversible_proposes():
    sig = {"type": "novel_signal", "subject": "y"}
    precedents = [{"type": "novel_signal", "subject": "y", "action": "did-this",
                   "outcome": "good", "reversible": "irreversible", "id": "PC-2"}]
    v = censor.cascade(sig, PROTOCOLS, precedents)
    assert v["branch"] == "precedent" and v["disposition"] == "propose"


def test_cascade_explores_when_nothing_matches():
    sig = {"type": "never_seen", "subject": "z"}
    v = censor.cascade(sig, PROTOCOLS, [])
    # never dead-stops — always yields a path forward
    assert v["branch"] == "exploration" and v["disposition"] == "explore"


def test_cascade_ignores_bad_outcome_precedent():
    sig = {"type": "novel_signal", "subject": "w"}
    precedents = [{"type": "novel_signal", "subject": "w", "outcome": "bad", "id": "PC-3"}]
    v = censor.cascade(sig, PROTOCOLS, precedents)
    assert v["branch"] == "exploration"   # a bad precedent is no precedent


# ─── adjudicated behavioural corrections (amendment 2026-07-04) ──────

def test_cascade_uncodified_friction_surfaces_to_him():
    # a NEW recurring friction is still the behavioural-rule lever — surfaced, never auto
    sig = {"type": "recurring_friction", "subject": "brand new habit", "codified": "no"}
    v = censor.cascade(sig, PROTOCOLS, [])
    assert v["branch"] == "protocol" and v["disposition"] == "surface"


def test_cascade_codified_friction_resolves_via_precedent():
    # once the correction is blessed + recorded as case law, the lever does not re-fire
    sig = {"type": "recurring_friction", "subject": "settled habit", "codified": "yes"}
    precedents = [{"type": "recurring_friction", "subject": "settled habit", "id": "PREC-X",
                   "outcome": "applied-ok", "reversible": "reversible",
                   "action": "standing correction in CLAUDE.md"}]
    v = censor.cascade(sig, PROTOCOLS, precedents)
    assert v["branch"] == "precedent" and v["disposition"] == "auto"


def test_gather_weekly_annotates_codified(tmp_path):
    # the weekly gatherer stamps each friction with codified yes/no from the case law
    (tmp_path / "insights-drift.json").write_text(
        '{"recurring": [{"label": "settled habit"}, {"label": "new habit"}]}')
    prec = tmp_path / "precedents.jsonl"
    prec.write_text('{"type": "recurring_friction", "subject": "settled habit", '
                    '"outcome": "applied-ok"}\n')
    old_logs, old_prec = censor.LOGS, censor.PRECEDENTS_PATH
    censor.LOGS, censor.PRECEDENTS_PATH = tmp_path, prec
    try:
        sigs = censor.gather_signals("weekly", refresh=False)
    finally:
        censor.LOGS, censor.PRECEDENTS_PATH = old_logs, old_prec
    flags = {s["subject"]: s["codified"] for s in sigs if s["type"] == "recurring_friction"}
    assert flags == {"settled habit": "yes", "new habit": "no"}
