"""Tests for the `limen status` budget-window label.

`spent`/`per_agent` are scoped to `track.date`, not to the wall clock. Printing them as "used
today" made the one surface an operator checks to answer "is the quota moving?" answer confidently
and wrongly for 12 days while the board was frozen at 2026-07-26 (#1995).
"""

from __future__ import annotations

from datetime import date

from limen.status import _track_window_label


def test_matching_window_is_today():
    assert _track_window_label("2026-08-07", today=date(2026, 8, 7)) == "today"


def test_stale_window_names_its_own_date_and_age():
    label = _track_window_label("2026-07-26", today=date(2026, 8, 7))
    assert "2026-07-26" in label
    assert "STALE" in label
    assert "12d" in label
    assert "not today" in label


def test_stale_window_never_claims_today():
    for recorded in ("2026-07-26", "2026-08-06", "2026-08-08", "not-a-date", ""):
        label = _track_window_label(recorded, today=date(2026, 8, 7))
        assert label != "today", recorded
        assert "not today" in label, recorded


def test_timestamped_window_is_read_as_its_date():
    assert _track_window_label("2026-08-07T19:04:11+00:00", today=date(2026, 8, 7)) == "today"


def test_unparseable_window_is_flagged_rather_than_crashing():
    label = _track_window_label("whenever", today=date(2026, 8, 7))
    assert "UNPARSEABLE" in label
    assert "not today" in label
