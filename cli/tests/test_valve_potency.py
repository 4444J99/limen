"""The POTENCY rung: a valve that SUCCEEDS at doing nothing must not read as healthy.

The defect this covers shipped and stayed live for a day (organvm/limen#2150). ``self-heal.py``'s
retirement pass was beat-wired and scheduled; it ran every beat, exited 0 every beat, and retired
nothing on any beat, because its enumeration was capped below the live open-PR count and the
truncation guard refused to retire from a prefix. The guard was RIGHT — the organ failed safe rather
than wrong. That is exactly what made it invisible: a valve failing safe and a valve with nothing to
do emit the same quiet beat and the same zero.

Every existing observer was structurally blind to it, not merely unlucky:

  * ``armed-valve-audit.py`` classifies ARMING. The valve was ARMED.
  * enactment WIRING proves the flag resolves ON. It did.
  * enactment LIVENESS proves the daemon post-dates its wiring. It did.
  * enactment EFFICACY goes RED on consecutive NON-ZERO exits. Every exit was 0.

So the tests below are mostly about the DENOMINATOR, because that is the whole mechanism: an alarm
on "effects == 0" alone fires forever on a healthy valve with a drained backlog, gets muted, and
takes the real signal with it. ``0 of 0`` is idle; ``0 of 257`` is dead.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts" / "enactment-audit.py"
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def ve():
    return _load("valve_effects_under_test", SCRIPTS / "_valve_effects.py")


@pytest.fixture()
def audit():
    return _load("enactment_audit_potency_under_test", AUDIT)


def _row(**kw):
    base = {"valve": "heal-retirement", "authorized": True, "candidates": 0, "effects": 0, "dry_run": False}
    base.update(kw)
    return base


def _ledger(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "valve-effects.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


# --- the denominator: the distinction the whole rung rests on -------------------------------


def test_zero_effects_with_zero_candidates_is_healthy_idle(ve):
    """A drained backlog reports 0 forever. Alarming on it is how a real alarm gets muted."""
    rows = [_row(candidates=0, effects=0) for _ in range(20)]
    assert ve.idle_streaks(rows) == {}


def test_zero_effects_with_candidates_waiting_is_the_defect(ve):
    """The shipped bug's live shape, with its measured number: authorized, 257 waiting, 0 done."""
    rows = [_row(candidates=257, effects=0) for _ in range(5)]
    streaks = ve.idle_streaks(rows)
    assert streaks["heal-retirement"]["streak"] == 5
    assert "257 candidate(s)" in streaks["heal-retirement"]["why"]


def test_refusal_is_idle_even_though_it_is_the_correct_behavior(ve):
    """The organ failed SAFE. That is right, and it must still be loud — the day-long outage was
    made of correct refusals, so 'the guard worked' cannot be the same signal as 'all is well'."""
    rows = [_row(authorized=False, candidates=257, effects=0, detail="enumeration truncated") for _ in range(4)]
    streaks = ve.idle_streaks(rows)
    assert streaks["heal-retirement"]["streak"] == 4
    assert "refused to act" in streaks["heal-retirement"]["why"]
    assert "truncated" in streaks["heal-retirement"]["why"]


def test_an_effect_breaks_the_streak(ve):
    rows = [_row(candidates=9, effects=0), _row(candidates=9, effects=0), _row(candidates=9, effects=3)]
    assert ve.idle_streaks(rows) == {}


def test_streak_is_trailing_not_total(ve):
    """A valve that was dead last week and fires now is healthy. Counting history pins it red
    permanently, and a permanently-red gate is an ignored gate."""
    rows = [_row(candidates=5, effects=0) for _ in range(10)]
    rows.append(_row(candidates=5, effects=5))
    rows += [_row(candidates=2, effects=0)]
    assert ve.idle_streaks(rows)["heal-retirement"]["streak"] == 1


def test_dry_runs_never_count(ve):
    """A dry run does not act BY DESIGN. Counting operator pokes as defects trains muting."""
    rows = [_row(dry_run=True, candidates=257, effects=0) for _ in range(9)]
    assert ve.idle_streaks(rows) == {}


def test_dry_runs_do_not_break_a_real_streak_either(ve):
    """Neither evidence for nor against — an operator's --dry-run between two dead beats must not
    silently reset the counter and hide the outage."""
    rows = [
        _row(candidates=257, effects=0),
        _row(dry_run=True, candidates=257, effects=0),
        _row(candidates=257, effects=0),
    ]
    assert ve.idle_streaks(rows)["heal-retirement"]["streak"] == 2


def test_valves_are_tracked_independently(ve):
    rows = [
        _row(valve="heal-retirement", candidates=257, effects=0),
        _row(valve="merge-drain", candidates=4, effects=4),
        _row(valve="heal-retirement", candidates=257, effects=0),
    ]
    streaks = ve.idle_streaks(rows)
    assert set(streaks) == {"heal-retirement"}


# --- the rung's verdicts --------------------------------------------------------------------


def test_rung_reds_at_threshold(audit, tmp_path, monkeypatch):
    led = _ledger(tmp_path, [_row(candidates=257, effects=0) for _ in range(3)])
    monkeypatch.setenv("LIMEN_VALVE_EFFECT_LOG", str(led))
    monkeypatch.setenv("LIMEN_VALVE_IDLE_STREAK_RED", "3")
    rows = audit.potency_rung()
    assert [r["status"] for r in rows] == [audit.RED]
    assert "INERT" in rows[0]["detail"]


def test_rung_is_only_informational_below_threshold(audit, tmp_path, monkeypatch):
    """One quiet run is noise. Matching the efficacy rung's posture deliberately."""
    led = _ledger(tmp_path, [_row(candidates=257, effects=0) for _ in range(2)])
    monkeypatch.setenv("LIMEN_VALVE_EFFECT_LOG", str(led))
    monkeypatch.setenv("LIMEN_VALVE_IDLE_STREAK_RED", "3")
    rows = audit.potency_rung()
    assert [r["status"] for r in rows] == [audit.INFO]


def test_rung_is_green_when_every_valve_acted_or_had_nothing_to_do(audit, tmp_path, monkeypatch):
    led = _ledger(tmp_path, [_row(candidates=3, effects=3), _row(valve="merge-drain", candidates=0, effects=0)])
    monkeypatch.setenv("LIMEN_VALVE_EFFECT_LOG", str(led))
    rows = audit.potency_rung()
    assert [r["status"] for r in rows] == [audit.GREEN]


def test_missing_ledger_skips_rather_than_passing(audit, tmp_path, monkeypatch):
    """'I read nothing' and 'nothing is wrong' must not print the same thing — the inference defect
    this entire rung exists to close, applied to the rung itself."""
    monkeypatch.setenv("LIMEN_VALVE_EFFECT_LOG", str(tmp_path / "absent.jsonl"))
    rows = audit.potency_rung()
    assert [r["status"] for r in rows] == [audit.SKIP]
    assert "no valve-effect ledger" in rows[0]["detail"]


def test_unreadable_rows_are_skipped_not_fatal(audit, ve, tmp_path, monkeypatch):
    p = tmp_path / "valve-effects.jsonl"
    p.write_text("not json\n" + json.dumps(_row(candidates=9, effects=0)) + "\n{}\n", encoding="utf-8")
    assert len(ve.read_rows(p)) == 1  # the bare {} has no `valve` key and is not a record
    monkeypatch.setenv("LIMEN_VALVE_EFFECT_LOG", str(p))
    monkeypatch.setenv("LIMEN_VALVE_IDLE_STREAK_RED", "1")
    assert [r["status"] for r in audit.potency_rung()] == [audit.RED]


# --- the writer -----------------------------------------------------------------------------


def test_record_round_trips(ve, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_VALVE_EFFECT_LOG", str(tmp_path / "l.jsonl"))
    assert ve.record("heal-retirement", authorized=False, candidates=257, effects=0, detail="truncated") is True
    rows = ve.read_rows(ve.ledger_path())
    assert rows[0]["candidates"] == 257 and rows[0]["authorized"] is False


def test_record_fails_open_on_an_unwritable_path(ve, monkeypatch):
    """A sensor that can wedge the organ it observes is worse than no sensor."""
    monkeypatch.setenv("LIMEN_VALVE_EFFECT_LOG", "/proc/nonexistent/l.jsonl")
    assert ve.record("v", authorized=True, candidates=1, effects=0) is False


def test_ledger_is_trimmed(ve, tmp_path, monkeypatch):
    p = tmp_path / "l.jsonl"
    monkeypatch.setenv("LIMEN_VALVE_EFFECT_LOG", str(p))
    monkeypatch.setattr(ve, "MAX_ROWS", 10)
    for _ in range(25):
        ve.record("v", authorized=True, candidates=0, effects=0)
    assert len(ve.read_rows(p)) == 10
