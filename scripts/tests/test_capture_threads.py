"""Fixture-backed idempotency tests for the private channel capture owner."""

import importlib.util
import json
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "capture-threads.py"
    spec = importlib.util.spec_from_file_location("capture_threads", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(seq: int) -> dict:
    return {
        "seq": seq,
        "ts": {"utc": f"2026-08-03 12:00:{seq:02d}", "et": "2026-08-03 08:00:00 EDT"},
        "direction": "received",
        "kind": "message",
        "text": f"fixture {seq}",
        "attachment_hashes": [],
    }


def test_normalized_observation_has_stable_private_id_and_receipt():
    module = _module()
    first = module.normalize_observations([_row(1)], person="fixture", channel="imessage")
    second = module.normalize_observations([_row(1)], person="fixture", channel="imessage")

    assert first[0]["source_message_id"] == second[0]["source_message_id"]
    assert first[0]["observation_receipt"] == {
        "schema": "limen.interaction_event.v1",
        "source": "imessage",
        "source_message_id": first[0]["source_message_id"],
        "state": "observed",
    }


def test_append_jsonl_is_idempotent_and_checkpoint_is_atomic(tmp_path):
    module = _module()
    tape = tmp_path / "imessage.jsonl"
    rows = module.normalize_observations([_row(1), _row(2)], person="fixture", channel="imessage")

    assert module.append_jsonl(str(tape), rows, person="fixture", channel="imessage") == 2
    assert module.append_jsonl(str(tape), rows, person="fixture", channel="imessage") == 0
    assert len(tape.read_text().splitlines()) == 2

    module.write_checkpoint(str(tmp_path), "fixture", "imessage", rows, appended=0)
    checkpoint = json.loads((tmp_path / "fixture" / "tape" / ".checkpoints" / "imessage.json").read_text())
    assert checkpoint["schema"] == "limen.capture_checkpoint.v1"
    assert checkpoint["last_source_message_id"] == rows[-1]["source_message_id"]
