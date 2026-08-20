"""limen.estate — the hot cache reads as evidence-with-TTL, never as an empty estate."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from limen.estate import SCHEMA, append_aliases, load_estate_cache, parse_estate_payload

NOW = dt.datetime(2026, 8, 6, 12, 0, tzinfo=dt.timezone.utc)


def _payload(fetched_at: str = "2026-08-06T10:00:00+00:00") -> dict:
    return {
        "schema": SCHEMA,
        "fetched_at": fetched_at,
        "owners": ["organvm"],
        "repos": {
            "organvm/limen": {"archived": False, "fork": False},
            "organvm/old-idea": {"archived": True, "fork": False},
        },
    }


def test_parse_and_live_members_exclude_archived():
    cache = parse_estate_payload(_payload())
    assert cache is not None
    assert cache.live_members() == {"organvm/limen"}
    assert "organvm/old-idea" in cache.repos  # known, but not underwriteable


def test_parse_rejects_wrong_schema_and_shapes():
    assert parse_estate_payload({"schema": "other", "repos": {}}) is None
    assert parse_estate_payload({"schema": SCHEMA, "fetched_at": "not-a-date", "repos": {}}) is None
    assert parse_estate_payload({"schema": SCHEMA, "fetched_at": "2026-08-06T10:00:00", "repos": []}) is None
    assert parse_estate_payload("nope") is None


def test_load_missing_file_is_absence(tmp_path: Path):
    assert load_estate_cache(tmp_path / "absent.json", now=NOW, ttl_hours=24) is None


def test_load_stale_cache_is_absence(tmp_path: Path):
    path = tmp_path / "estate.json"
    path.write_text(json.dumps(_payload("2026-08-04T10:00:00+00:00")))
    assert load_estate_cache(path, now=NOW, ttl_hours=24) is None
    # the same bytes inside the TTL are evidence
    assert load_estate_cache(path, now=NOW, ttl_hours=72) is not None


def test_load_fresh_cache_round_trips(tmp_path: Path):
    path = tmp_path / "estate.json"
    path.write_text(json.dumps(_payload()))
    cache = load_estate_cache(path, now=NOW, ttl_hours=24)
    assert cache is not None
    assert cache.live_members() == {"organvm/limen"}


def test_resolve_follows_alias_only_onto_the_roster():
    payload = _payload()
    payload["aliases"] = {"organvm/old-path": "organvm/limen", "organvm/dangling": "organvm/nowhere"}
    cache = parse_estate_payload(payload)
    assert cache.resolve("organvm/limen") == "organvm/limen"
    assert cache.resolve("organvm/old-path") == "organvm/limen"
    assert cache.resolve("organvm/dangling") is None  # alias target must be a live roster entry
    assert cache.resolve("organvm/unknown") is None


def test_append_aliases_merges_without_touching_the_stamp(tmp_path: Path):
    path = tmp_path / "estate.json"
    path.write_text(json.dumps(_payload()))
    assert append_aliases(path, {"organvm/old-path": "organvm/limen"})
    reread = json.loads(path.read_text())
    assert reread["aliases"] == {"organvm/old-path": "organvm/limen"}
    assert reread["fetched_at"] == _payload()["fetched_at"]  # TTL not extended by alias folds
    assert append_aliases(tmp_path / "absent.json", {"a/b": "c/d"}) is False
