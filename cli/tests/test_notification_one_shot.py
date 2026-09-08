"""Tests for the bounded processless notification one-shot."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "notification-one-shot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("notification_one_shot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state_paths(module, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(module, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(module, "RECEIPT", tmp_path / "notification-one-shot.json")
    monkeypatch.setattr(module, "LOCK", tmp_path / "notification-one-shot.lock")
    monkeypatch.setattr(module, "FAILURE_STATE", tmp_path / "notification-one-shot-failures.json")


def test_default_invocation_is_plan_only(tmp_path, monkeypatch, capsys):
    module = _load_module()
    _state_paths(module, tmp_path / "state", monkeypatch)
    monkeypatch.setattr(
        module,
        "_run_step",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("producer invoked")),
    )

    assert module.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["apply_required"] is True
    assert not module.STATE_ROOT.exists()


def test_apply_fails_when_a_producer_exits_zero_without_complete_evidence(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path, monkeypatch)
    monkeypatch.setattr(module, "_steps", lambda: [("ships-24h", ["python", "producer.py"], 1)])
    monkeypatch.setattr(
        module,
        "_run_step",
        lambda *_args, **_kwargs: {
            "name": "ships-24h",
            "returncode": 0,
            "producer_complete": False,
            "timed_out": False,
        },
    )

    assert module.main(["--apply"]) == 1
    receipt = json.loads(module.RECEIPT.read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["consecutive_failures"] == 1


def test_consecutive_failure_kill_switch_prevents_producer_execution(tmp_path, monkeypatch):
    module = _load_module()
    _state_paths(module, tmp_path, monkeypatch)
    module.FAILURE_STATE.write_text(
        json.dumps({"consecutive_failures": module.MAX_CONSECUTIVE_FAILURES}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "_run_step",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("producer invoked")),
    )

    assert module.main(["--apply"]) == 78


def test_shipping_producer_requires_fresh_complete_cache(tmp_path, monkeypatch):
    module = _load_module()
    live = tmp_path / "live"
    cache = live / "logs" / "ships-24h.json"
    cache.parent.mkdir(parents=True)
    monkeypatch.setattr(module, "LIVE_ROOT", live)
    cache.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "complete": False,
                "error": "partial-owner-query",
            }
        ),
        encoding="utf-8",
    )

    assert module._producer_complete("ships-24h", 0) is False
    payload = json.loads(cache.read_text(encoding="utf-8"))
    payload.update({"complete": True, "error": None})
    cache.write_text(json.dumps(payload), encoding="utf-8")
    assert module._producer_complete("ships-24h", 0) is True
