import datetime
import importlib.util
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "health-organ.py"


def _load():
    spec = importlib.util.spec_from_file_location("health_organ", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fmt_time():
    health_organ = _load()
    assert health_organ._fmt_time("13:45") == "1:45 PM"
    assert health_organ._fmt_time("00:15") == "12:15 AM"
    assert health_organ._fmt_time("12:00") == "12:00 PM"
    assert health_organ._fmt_time("invalid") == "invalid"
    assert health_organ._fmt_time(None) == ""


def test_days_since():
    health_organ = _load()
    with patch.object(health_organ, "date") as mock_date:
        mock_date.today.return_value = datetime.date(2026, 6, 28)
        mock_date.fromisoformat = datetime.date.fromisoformat

        assert health_organ._days_since("2026-06-20") == 8
        assert health_organ._days_since("invalid") is None
        assert health_organ._days_since(None) is None


def test_next_appt_days():
    health_organ = _load()
    with patch.object(health_organ, "date") as mock_date:
        # 2026-06-28 is a Sunday (weekday 6)
        mock_date.today.return_value = datetime.date(2026, 6, 28)

        # Monday is weekday 0, so 1 day away
        assert health_organ._next_appt_days({"day_of_week": "monday"}) == 1
        # Sunday is weekday 6, so 0 days away
        assert health_organ._next_appt_days({"day_of_week": "sunday"}) == 0
        assert health_organ._next_appt_days({"day_of_week": "invalid"}) is None
        assert health_organ._next_appt_days({}) is None


def test_ledger():
    health_organ = _load()
    assert health_organ._ledger({}) == []
    assert health_organ._ledger({"results_ledger": [{"status": "ordered"}]}) == [{"status": "ordered"}]
    assert health_organ._ledger({"results_ledger": {"entries": [{"status": "ordered"}]}}) == [{"status": "ordered"}]
    assert health_organ._ledger({"results_ledger": "invalid"}) == []


def test_parse_start():
    health_organ = _load()
    d, approx = health_organ._parse_start("2023-05-12")
    assert d == datetime.date(2023, 5, 12)
    assert approx is False

    d, approx = health_organ._parse_start("2023-05")
    assert d == datetime.date(2023, 5, 1)
    assert approx is True

    d, approx = health_organ._parse_start("~2023-05-12")
    assert d == datetime.date(2023, 5, 12)
    assert approx is True

    d, approx = health_organ._parse_start("approx 2023-05-12")
    assert d == datetime.date(2023, 5, 12)
    assert approx is True

    d, approx = health_organ._parse_start("invalid")
    assert d is None
    assert approx is True


def test_to_min():
    health_organ = _load()
    assert health_organ._to_min("01:30") == 90
    assert health_organ._to_min("00:00") == 0
    assert health_organ._to_min("invalid") is None
    assert health_organ._to_min(None) is None


def test_from_min():
    health_organ = _load()
    assert health_organ._from_min(90) == "01:30"
    assert health_organ._from_min(0) == "00:00"
    assert health_organ._from_min(1440) == "00:00"


def test_median():
    health_organ = _load()
    assert health_organ._median([]) is None
    assert health_organ._median([5]) == 5
    assert health_organ._median([1, 2, 3]) == 2
    assert health_organ._median([1, 2, 3, 4]) == 2.5
    assert health_organ._median([4, 1, 3, 2]) == 2.5


def test_round5():
    health_organ = _load()
    assert health_organ._round5(12) == 10
    assert health_organ._round5(13) == 15
    assert health_organ._round5(0) == 0
    assert health_organ._round5(17.5) == 20
