"""Tests for OBSERVATORY P2-SYNTH — weekly KEEP/TEST/REJECT synthesis (synthesis.py).

Hermetic: temp obs root, seeded mechanisms.jsonl, pinned clock (``_now``). Asserts ships-dark
(off → inert, writes nothing), correct buckets, and the once-per-ISO-week gate (idempotent).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from limen.observatory import config, ledger, synthesis


@pytest.fixture
def obs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "repo_root", lambda: tmp_path)
    (tmp_path / "logs" / "observatory").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _seed_mechanisms():
    for p in (7.0, 8.0, 6.0, 7.0):  # recurs high → KEEP
        ledger.append_jsonl("mechanisms.jsonl", {"mechanism": "names_outcome", "priority": p, "winner": "o/w"})
    for p in (0.2, 0.3, 0.1):  # recurs low → REJECT
        ledger.append_jsonl("mechanisms.jsonl", {"mechanism": "comparison", "priority": p, "winner": "o/w"})
    ledger.append_jsonl(
        "mechanisms.jsonl", {"mechanism": "api_example", "priority": 5.0, "winner": "o/w"}
    )  # rare → TEST


def _pin_week(monkeypatch, iso="2026-06-15"):
    monkeypatch.setattr(synthesis, "_now", lambda: datetime.fromisoformat(iso).replace(tzinfo=UTC))


def _arm(monkeypatch, on=True):
    monkeypatch.setattr(
        synthesis.config,
        "get",
        lambda key, default=None, cast=None: (1 if on else 0) if key == "OBSERVATORY_SYNTH_ENABLED" else default,
    )


def test_bucket_classifies_keep_test_reject():
    mechs = (
        [{"mechanism": "names_outcome", "priority": 7.0}] * 4
        + [{"mechanism": "comparison", "priority": 0.2}] * 3
        + [{"mechanism": "api_example", "priority": 5.0}]
    )
    b = synthesis._bucket(mechs)
    assert [r["mechanism"] for r in b["keep"]] == ["names_outcome"]
    assert [r["mechanism"] for r in b["reject"]] == ["comparison"]
    assert [r["mechanism"] for r in b["test"]] == ["api_example"]


def test_run_off_is_inert(obs_root, monkeypatch):
    _arm(monkeypatch, on=False)
    r = synthesis.run()
    assert r["status"] == "off"
    assert not (obs_root / "logs" / "observatory" / "synthesis-weekly-latest.json").exists()


def test_run_synthesizes_once_per_week(obs_root, monkeypatch):
    _arm(monkeypatch)
    _pin_week(monkeypatch)
    _seed_mechanisms()
    r1 = synthesis.run()
    assert r1["status"] == "ok" and r1["keep"] == 1 and r1["reject"] == 1 and r1["test"] == 1
    doc = json.loads((obs_root / "logs" / "observatory" / "synthesis-weekly-latest.json").read_text())
    assert doc["iso_week"] == r1["iso_week"] and doc["window_mechanisms"] == 3
    # second run in the same week → idempotent skip
    assert synthesis.run()["status"] == "current"


def test_run_reruns_on_a_new_week(obs_root, monkeypatch):
    _arm(monkeypatch)
    _seed_mechanisms()
    _pin_week(monkeypatch, "2026-06-15")
    assert synthesis.run()["status"] == "ok"
    _pin_week(monkeypatch, "2026-06-25")  # a later ISO week
    assert synthesis.run()["status"] == "ok"
