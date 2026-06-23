"""Tests for scripts/_pr_scan.py — the shared full-fleet enumeration + rotating-window coverage
the HEAL and MERGE organs use to drain a PR backlog larger than the old fixed 30-scan window.
Asserts the properties that make it safe to run every beat unattended:
(1) enumerate_open_prs returns the FULL set, stably sorted, and fails open ([]) on gh error,
(2) rotating_window advances + wraps, covering EVERY item within one rotation,
(3) persist=False (dry-run) peeks WITHOUT writing/advancing the cursor,
(4) a corrupt/absent cursor fails open to start-at-0,
(5) scaled_limit lifts the cap with headroom and is a no-op when usage is unreadable.
"""
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "_pr_scan.py"


def _load():
    spec = importlib.util.spec_from_file_location("pr_scan_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _R:
    def __init__(self, out, rc=0):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


_PRS = [
    {"number": 9, "repository": {"nameWithOwner": "organvm/zeta"}, "url": "u/9"},
    {"number": 2, "repository": {"nameWithOwner": "organvm/alpha"}, "url": "u/2"},
    {"number": 5, "repository": {"nameWithOwner": "organvm/mid"}, "url": "u/5"},
]


def test_enumerate_full_set_stable_sort():
    m = _load()
    got = m.enumerate_open_prs(["organvm"], lambda a, timeout=60: _R(json.dumps(_PRS)))
    # full set returned, sorted by (repo, num) — STABLE regardless of gh's input ordering.
    assert got == [("organvm/alpha", 2, "u/2"), ("organvm/mid", 5, "u/5"), ("organvm/zeta", 9, "u/9")]


def test_enumerate_want_url_false_returns_pairs():
    m = _load()
    got = m.enumerate_open_prs(["organvm"], lambda a, timeout=60: _R(json.dumps(_PRS)), want_url=False)
    assert got == [("organvm/alpha", 2), ("organvm/mid", 5), ("organvm/zeta", 9)]


def test_enumerate_fails_open_on_gh_error():
    m = _load()
    assert m.enumerate_open_prs(["organvm"], lambda a, timeout=60: _R("", rc=1)) == []
    assert m.enumerate_open_prs(["organvm"], lambda a, timeout=60: _R("not-json")) == []


def test_rotating_window_advances_wraps_and_covers_all(tmp_path):
    m = _load()
    items = list(range(5))
    cur = str(tmp_path / ".cursor")
    seen = set()
    windows = [m.rotating_window(items, 2, cur) for _ in range(3)]  # 2+2+2 over 5, wrapping
    for w in windows:
        seen.update(w)
    assert windows[0] == [0, 1] and windows[1] == [2, 3]
    assert windows[2] == [4, 0]              # wraps past the end
    assert seen == set(items), "one full rotation must assess every PR at least once"


def test_rotating_window_dry_run_peeks_without_writing(tmp_path):
    m = _load()
    items = list(range(5))
    cur = tmp_path / ".cursor"
    first = m.rotating_window(items, 2, str(cur), persist=False)
    second = m.rotating_window(items, 2, str(cur), persist=False)
    assert first == second == [0, 1], "peek must not advance the cursor"
    assert not cur.exists(), "dry-run must not write the cursor file"


def test_rotating_window_corrupt_cursor_fails_open(tmp_path):
    m = _load()
    cur = tmp_path / ".cursor"
    cur.write_text("garbage")
    assert m.rotating_window(list(range(5)), 2, str(cur)) == [0, 1]  # start-at-0 on bad cursor


def test_scaled_limit_headroom(tmp_path):
    m = _load()
    (tmp_path / "logs").mkdir()
    usage = tmp_path / "logs" / "usage.json"
    # full tank (100%) → 3x ; mid (75%) → 2x ; low (<50%) → base ; unreadable → base.
    usage.write_text(json.dumps({"vendors": {"a": {"headroom_pct": 100}, "b": {"headroom_pct": 100}}}))
    assert m.scaled_limit(10, tmp_path) == 30
    usage.write_text(json.dumps({"vendors": {"a": {"headroom_pct": 75}}}))
    assert m.scaled_limit(10, tmp_path) == 20
    usage.write_text(json.dumps({"vendors": {"a": {"headroom_pct": 10}}}))
    assert m.scaled_limit(10, tmp_path) == 10
    usage.unlink()
    assert m.scaled_limit(10, tmp_path) == 10, "no usage.json → base limit (fail-open)"
