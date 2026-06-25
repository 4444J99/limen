"""obligations-view deadline self-awareness — the lever face's own clock.

A his-hand lever carrying a `deadline` must auto-flag on the surface (overdue / due-today /
due-soon) so it can never silently rot past its date. This pins that the badge is PURE and
DERIVED (no hand-maintained status field) and FAILS OPEN on a missing/malformed date.
"""
import importlib.util
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _mod():
    # obligations-view.py is hyphenated (a script, not a package) — load it by path.
    spec = importlib.util.spec_from_file_location(
        "obligations_view", ROOT / "scripts" / "obligations-view.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_TODAY = date(2026, 6, 25)


def test_overdue():
    badge = _mod()._deadline_badge({"deadline": "2026-06-20"}, today=_TODAY)
    assert "OVERDUE" in badge and "5d" in badge and "overdue" in badge


def test_due_today():
    assert "DUE TODAY" in _mod()._deadline_badge({"deadline": "2026-06-25"}, today=_TODAY)


def test_due_soon():
    assert "due in 2d" in _mod()._deadline_badge({"deadline": "2026-06-27"}, today=_TODAY)


def test_far_future_plain():
    badge = _mod()._deadline_badge({"deadline": "2026-12-01"}, today=_TODAY)
    assert badge.startswith('<span class="due">') and "overdue" not in badge


def test_no_deadline_is_empty():
    assert _mod()._deadline_badge({}, today=_TODAY) == ""


def test_malformed_fails_open():
    assert _mod()._deadline_badge({"deadline": "whenever"}, today=_TODAY) == ""
