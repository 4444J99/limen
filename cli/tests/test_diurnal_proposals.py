"""A proposal the evening raises must have a home, an age, and a way to be answered.

One file per concern, per the sibling-branch reasoning in test_diurnal_ledger.py.

What is under test: `apply_cuts()` has always been able to say "this producer is dead — retire or
repair it." Until the proposal book existed, saying it was ALL that happened. The list was built,
put on ctx, printed into the page, and never read back: no file, no dedup, no age, no owner.
Measured on the live root 2026-08-02, the organ had printed the same three proposals on every
evening page since 2026-07-31 while their sources aged to 10, 22 and 36 days.

The book does not grant the organ authority to retire anything — "retire or repair" is a judgment
it cannot make, and organs.yaml owns that residual. It makes the judgment owed on a clock.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "diurnal.py"


@pytest.fixture()
def mod():
    spec = importlib.util.spec_from_file_location("diurnal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["diurnal"] = module
    spec.loader.exec_module(module)
    return module


def _book(root: Path) -> dict:
    return json.loads((root / "logs" / "diurnal" / "proposals.json").read_text(encoding="utf-8"))


def _cuts(root: Path) -> list[dict]:
    path = root / "logs" / "diurnal" / "cuts.jsonl"
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


P1 = {"what": "logs/omega.json", "reason": "source stale 10d — retire or repair the producer"}
P2 = {"what": "section:routines", "reason": "blind 5 consecutive engaged days"}


def test_a_proposal_lands_in_the_book_with_its_first_sighting(mod, tmp_path):
    mod.record_proposals(tmp_path, [P1], "2026-08-02")
    rec = _book(tmp_path)["logs/omega.json"]
    assert rec["first_seen"] == "2026-08-02"
    assert rec["last_seen"] == "2026-08-02"
    assert rec["disposition"] is None, "an unanswered proposal is what the gate counts"


def test_the_first_sighting_is_the_age_and_survives_every_later_evening(mod, tmp_path):
    """The whole point. An undated 'needs a PR' reads the same on day 1 and day 40."""
    mod.record_proposals(tmp_path, [P1], "2026-08-02")
    for day in ("2026-08-03", "2026-08-04", "2026-08-05"):
        mod.record_proposals(tmp_path, [P1], day)
    rec = _book(tmp_path)["logs/omega.json"]
    assert rec["first_seen"] == "2026-08-02", "re-proposing must not reset the clock"
    assert rec["last_seen"] == "2026-08-05"


def test_the_same_proposal_is_recorded_once_not_once_per_evening(mod, tmp_path):
    for day in ("2026-08-02", "2026-08-03", "2026-08-04"):
        mod.record_proposals(tmp_path, [P1, P2], day)
    assert len(_book(tmp_path)) == 2
    assert len([r for r in _cuts(tmp_path) if r["action"] == "propose"]) == 2


def test_the_history_lands_in_the_cuts_log_not_a_new_substrate(mod, tmp_path):
    """Route through an existing canonical surface — cuts.jsonl already records what the organ did."""
    mod.record_proposals(tmp_path, [P1], "2026-08-02")
    row = next(r for r in _cuts(tmp_path) if r["action"] == "propose")
    assert row["what"] == "logs/omega.json"
    assert "retire or repair" in row["reason"]


def test_a_proposal_that_stops_recurring_resolves_itself(mod, tmp_path):
    """The producer was repaired. A gate that stayed red on a solved problem is the same defect
    wearing the opposite sign."""
    mod.record_proposals(tmp_path, [P1, P2], "2026-08-02")
    mod.record_proposals(tmp_path, [P2], "2026-08-03")
    book = _book(tmp_path)
    assert book["logs/omega.json"]["disposition"] == "resolved 2026-08-03 — the condition stopped recurring"
    assert book["section:routines"]["disposition"] is None


def test_a_hand_written_disposition_is_never_overwritten(mod, tmp_path):
    """Answering a proposal is how a human closes it; the next evening must not reopen it."""
    mod.record_proposals(tmp_path, [P1], "2026-08-02")
    path = tmp_path / "logs" / "diurnal" / "proposals.json"
    book = json.loads(path.read_text())
    book["logs/omega.json"]["disposition"] = "PR #1799 retires the producer"
    path.write_text(json.dumps(book))

    mod.record_proposals(tmp_path, [P1], "2026-08-03")
    assert _book(tmp_path)["logs/omega.json"]["disposition"] == "PR #1799 retires the producer"


def test_an_unengaged_evening_never_reaches_the_book(mod, tmp_path, monkeypatch):
    """apply_cuts() returns ([], []) when the day was not engaged. If that empty list reached
    record_proposals(), a week away would silently resolve every open proposal by not observing
    them — the auto-resolve rule turned into an amnesia rule."""
    monkeypatch.setattr(mod, "engaged_today", lambda _root: False)
    (tmp_path / "institutio" / "governance").mkdir(parents=True)
    (tmp_path / "institutio" / "governance" / "diurnal.yaml").write_text(
        (ROOT / "institutio" / "governance" / "diurnal.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    mod.record_proposals(tmp_path, [P1], "2026-08-02")
    assert mod.emit(tmp_path, "evening", dry_run=False) == 0
    assert _book(tmp_path)["logs/omega.json"]["disposition"] is None


def test_the_page_shows_how_long_a_proposal_has_been_open(mod, tmp_path):
    book = mod.record_proposals(tmp_path, [P1], "2026-08-02")
    lines = mod.r_cuts(tmp_path, {"title": "cuts"}, {"cuts_proposed": [P1], "proposal_book": book}).lines
    assert "open since 2026-08-02" in lines[0]


def test_the_page_still_renders_before_any_book_exists(mod, tmp_path):
    """Midday and dry-run paths carry no book; the renderer must degrade, not raise."""
    lines = mod.r_cuts(tmp_path, {"title": "cuts"}, {"cuts_proposed": [P1]}).lines
    assert "needs a PR" in lines[0]
    assert "open since" not in lines[0]


def test_a_corrupt_book_is_rebuilt_rather_than_crashing_the_evening(mod, tmp_path):
    """The evening is a sensor on the beat: it fails open, never closed."""
    (tmp_path / "logs" / "diurnal").mkdir(parents=True)
    (tmp_path / "logs" / "diurnal" / "proposals.json").write_text("not json at all")
    mod.record_proposals(tmp_path, [P1], "2026-08-02")
    assert _book(tmp_path)["logs/omega.json"]["first_seen"] == "2026-08-02"


def test_a_dry_run_writes_no_book(mod, tmp_path):
    """A rehearsal that starts a proposal's clock is not a rehearsal."""
    (tmp_path / "institutio" / "governance").mkdir(parents=True)
    (tmp_path / "institutio" / "governance" / "diurnal.yaml").write_text(
        (ROOT / "institutio" / "governance" / "diurnal.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert mod.emit(tmp_path, "evening", dry_run=True) == 0
    assert not (tmp_path / "logs" / "diurnal" / "proposals.json").exists()
