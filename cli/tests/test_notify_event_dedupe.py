"""Cross-process-safe, event-level notification deduplication."""

from __future__ import annotations

import fcntl
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "_notify.py"


def _load():
    name = f"notify_event_uut_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _event(module, root: Path, **overrides):
    values = {
        "source": "routine-freshness",
        "event": "plans-orphan-audit",
        "stable_id": "IC_kwDOSmG6rc8AAAABOe7MzA",
        "local_day": "2026-08-12",
        "message": "routine receipt is green",
        "title": "Claude routine",
        "enabled": True,
    }
    values.update(overrides)
    return module.notify_event(root, **values)


def test_concurrent_replay_delivers_exactly_once(tmp_path, monkeypatch):
    module = _load()
    monkeypatch.setattr(module, "_root_may_speak", lambda _root: True)
    deliveries = []

    def deliver(message, title):
        deliveries.append((message, title))
        time.sleep(0.02)
        return True

    monkeypatch.setattr(module, "_deliver", deliver)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: _event(module, tmp_path), range(8)))

    assert [result.status for result in results].count("emitted") == 1
    assert [result.status for result in results].count("duplicate") == 7
    assert len(deliveries) == 1


def test_same_day_exact_comment_replay_is_suppressed(tmp_path, monkeypatch):
    module = _load()
    monkeypatch.setattr(module, "_root_may_speak", lambda _root: True)
    monkeypatch.setattr(module, "_deliver", lambda *_args: True)

    first = _event(module, tmp_path)
    replay = _event(module, tmp_path)

    assert first.status == "emitted"
    assert replay.status == "duplicate"
    assert replay.event_key == first.event_key


def test_changed_head_and_identifierless_payload_remain_actionable(tmp_path, monkeypatch):
    module = _load()
    monkeypatch.setattr(module, "_root_may_speak", lambda _root: True)
    monkeypatch.setattr(module, "_deliver", lambda *_args: True)

    old_head = _event(module, tmp_path, event="ci-red", stable_id="organvm/limen#2122@old")
    new_head = _event(module, tmp_path, event="ci-red", stable_id="organvm/limen#2122@new")
    old_count = _event(
        module,
        tmp_path,
        event="shipping",
        stable_id=None,
        payload={"count": 10, "status": "green"},
    )
    new_count = _event(
        module,
        tmp_path,
        event="shipping",
        stable_id=None,
        payload={"status": "green", "count": 25},
    )

    assert {old_head.status, new_head.status, old_count.status, new_count.status} == {"emitted"}
    assert old_head.event_key != new_head.event_key
    assert old_count.event_key != new_count.event_key


def test_next_local_day_rearms_same_source_event(tmp_path, monkeypatch):
    module = _load()
    monkeypatch.setattr(module, "_root_may_speak", lambda _root: True)
    monkeypatch.setattr(module, "_deliver", lambda *_args: True)

    first = _event(module, tmp_path, local_day="2026-08-12")
    next_day = _event(module, tmp_path, local_day="2026-08-13")

    assert first.status == next_day.status == "emitted"
    assert first.event_key != next_day.event_key


def test_delivery_failure_is_reserved_before_effector_and_replay_stays_suppressed(tmp_path, monkeypatch):
    module = _load()
    monkeypatch.setattr(module, "_root_may_speak", lambda _root: True)
    outcomes = iter((False, True))
    monkeypatch.setattr(module, "_deliver", lambda *_args: next(outcomes))

    failed = _event(module, tmp_path)
    replay = _event(module, tmp_path)
    ledger = json.loads(module._event_state_path(tmp_path).read_text(encoding="utf-8"))

    assert failed.status == "delivery_failed"
    assert failed.reserved is True
    assert replay.status == "duplicate"
    assert ledger["events"][failed.event_key]["status"] == "delivery_failed"


def test_lock_contention_has_a_finite_withheld_outcome(tmp_path, monkeypatch):
    module = _load()
    monkeypatch.setattr(module, "_root_may_speak", lambda _root: True)
    lock_path = module._event_lock_path(tmp_path)
    lock_path.parent.mkdir(parents=True)
    started = time.monotonic()
    with lock_path.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _event(module, tmp_path, lock_timeout=0.03)
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    assert result.status == "withheld"
    assert "timed out" in str(result.reason)
    assert time.monotonic() - started < 0.5


def test_lock_stream_closes_when_acquisition_setup_fails(tmp_path, monkeypatch):
    module = _load()
    lock = module._EventLock(tmp_path, 0.1)
    monkeypatch.setattr(module.os, "chmod", lambda *_args: (_ for _ in ()).throw(OSError("read-only")))

    with pytest.raises(OSError, match="read-only"):
        lock.__enter__()

    assert lock.stream is None


def test_event_ledger_retention_is_bounded_by_age_and_record_count(monkeypatch):
    module = _load()
    monkeypatch.setattr(module, "EVENT_RETENTION_DAYS", 2)
    monkeypatch.setattr(module, "EVENT_RETENTION_RECORDS", 2)
    state = {
        "events": {
            "old": {"local_day": "2026-08-01", "reserved_at": "2026-08-01T00:00:00"},
            "one": {"local_day": "2026-08-12", "reserved_at": "2026-08-12T01:00:00"},
            "two": {"local_day": "2026-08-12", "reserved_at": "2026-08-12T02:00:00"},
            "three": {"local_day": "2026-08-12", "reserved_at": "2026-08-12T03:00:00"},
        }
    }

    module._prune_event_state(state, "2026-08-12")

    assert set(state["events"]) == {"two", "three"}


def test_event_reservation_prunes_against_today_not_replayed_day(tmp_path, monkeypatch):
    module = _load()
    monkeypatch.setattr(module, "_root_may_speak", lambda _root: True)
    monkeypatch.setattr(module, "_deliver", lambda *_args: True)
    observed = []
    monkeypatch.setattr(module, "_prune_event_state", lambda _state, today: observed.append(today))

    _event(module, tmp_path, local_day="2001-01-01")

    assert observed == [module.datetime.now().astimezone().date().isoformat()]


def test_synthetic_and_linked_worktree_roots_never_reserve_or_deliver(tmp_path, monkeypatch):
    module = _load()
    delivered = []
    monkeypatch.setattr(module, "_deliver", lambda *_args: delivered.append(True) or True)

    synthetic = tmp_path / "synthetic"
    synthetic.mkdir()
    worktree = tmp_path / "worktree"
    (worktree / "institutio" / "governance").mkdir(parents=True)
    (worktree / "institutio" / "governance" / "sensors.yaml").write_text("sensors: {}\n")
    (worktree / ".git").write_text("gitdir: /tmp/example\n")
    voices = worktree / "logs" / ".voice"
    voices.mkdir(parents=True)
    for index in range(6):
        (voices / str(index)).write_text("alive\n")

    synthetic_result = _event(module, synthetic)
    worktree_result = _event(module, worktree)

    assert synthetic_result.status == worktree_result.status == "withheld"
    assert delivered == []
    assert not module._event_state_path(synthetic).exists()
    assert not module._event_state_path(worktree).exists()
