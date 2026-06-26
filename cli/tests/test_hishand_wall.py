"""sync-hishand-issues --wall — the aggregate his-hand Wall body.

Pins that the Wall lists every lever with its issue link and carries its own marker (so the
per-lever sync never mistakes the Wall for a lever), purely and offline.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _mod():
    spec = importlib.util.spec_from_file_location("sync_hishand", ROOT / "scripts" / "sync-hishand-issues.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_LEVERS = [
    {"id": "L-FOO", "label": "Do the foo thing: a long clause that should be truncated for the table",
     "unlocks": "the foo capability", "cost": "~2 min once", "issue": 111},
    {"id": "L-BAR", "label": "Bar lever", "unlocks": "bar", "cost": "one paste", "issue": 222},
    {"id": "L-NOISSUE", "label": "Unstamped lever", "unlocks": "x", "cost": "y"},
]


def test_wall_lists_every_lever_and_issue():
    m = _mod()
    body = m.wall_body(_LEVERS)
    assert "L-FOO" in body and "#111" in body
    assert "L-BAR" in body and "#222" in body
    # an unstamped lever still appears, with an em-dash for its issue
    assert "L-NOISSUE" in body
    assert m.WALL_MARKER in body
    assert "3 levers" in body


def test_wall_marker_distinct_from_lever_marker():
    m = _mod()
    # the Wall must NOT carry a lever: marker, else the per-lever sync would adopt it
    assert "<!-- lever:" not in m.wall_body(_LEVERS)


def test_head_truncates():
    m = _mod()
    assert m._head("short", 90) == "short"
    long = "x" * 200
    assert len(m._head(long, 70)) <= 70
