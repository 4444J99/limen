"""Tests for scripts/_ships_24h.py — the shared reader for the ships-24h-refresh.py cache.

Regression pin for the 2026-08-15 notification blackout: money-view.py/omni-view.py used to count
"PRs shipped in the last 24h" by grep-parsing logs/merge-drain.log, which only ever saw the batch
merge-drain.py daemon's own merges — self-merged PRs (the majority of real throughput) were
structurally invisible, so notify-events.py's ship-milestone push could never fire from real
activity. This module replaces the log-scrape with a cached ground-truth count; these tests pin
its fail-open contract so a broken/missing/stale cache degrades to "0 ships", never a crash or a
silently-stale number.
"""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "_ships_24h.py"


def _load():
    spec = importlib.util.spec_from_file_location("ships_24h_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _write_cache(root: Path, *, generated_at: str, total=0, by_repo=None, recent=None):
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "ships-24h.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "total": total,
                "by_repo": by_repo or {},
                "recent": recent or [],
            }
        )
    )


def test_happy_path_reads_through(tmp_path):
    m = _load()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_cache(
        tmp_path,
        generated_at=now,
        total=63,
        by_repo={"organvm/limen": 63},
        recent=["organvm/limen#2482"],
    )
    total, by_repo, recent = m.read_ships_24h(tmp_path)
    assert total == 63
    assert by_repo == {"organvm/limen": 63}
    assert recent == ["organvm/limen#2482"]


def test_missing_cache_fails_open(tmp_path):
    m = _load()
    assert m.read_ships_24h(tmp_path) == (0, {}, [])


def test_malformed_cache_fails_open(tmp_path):
    m = _load()
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "ships-24h.json").write_text("not json at all")
    assert m.read_ships_24h(tmp_path) == (0, {}, [])


def test_stale_cache_fails_open(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setenv("LIMEN_SHIPS_24H_STALE_MINUTES", "40")
    stale = (datetime.now(timezone.utc) - timedelta(minutes=41)).isoformat(timespec="seconds")
    _write_cache(tmp_path, generated_at=stale, total=99)
    assert m.read_ships_24h(tmp_path) == (0, {}, [])


def test_fresh_cache_within_stale_window_is_served(tmp_path, monkeypatch):
    m = _load()
    monkeypatch.setenv("LIMEN_SHIPS_24H_STALE_MINUTES", "40")
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")
    _write_cache(tmp_path, generated_at=fresh, total=12)
    total, _, _ = m.read_ships_24h(tmp_path)
    assert total == 12
