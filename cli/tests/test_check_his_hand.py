from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_his_hand", ROOT / "scripts" / "check-his-hand.py")
assert SPEC and SPEC.loader
check_his_hand = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_his_hand)


def lever(**overrides):
    value = {
        "id": "L-TEST",
        "label": "test",
        "unlocks": "test",
        "issue": 1,
        "status": "open",
        "diagnosed_at": "2026-09-15T00:00:00Z",
    }
    value.update(overrides)
    return value


def write_registry(path: Path, levers: list[dict]) -> None:
    path.write_text('{"levers": ' + json.dumps(levers) + "}\n")


def test_valid_registry_derives_age(tmp_path):
    path = tmp_path / "levers.json"
    write_registry(path, [lever()])

    errors, census = check_his_hand.evaluate(path, datetime(2026, 9, 16, tzinfo=timezone.utc))

    assert errors == []
    assert census["diagnosed"] == 1
    assert census["days_since_diagnosed_max"] == 1


def test_future_duplicate_and_invalid_status_fail(tmp_path):
    path = tmp_path / "levers.json"
    write_registry(
        path,
        [lever(id="L-DUP", status="open", diagnosed_at="2026-09-17T00:00:00Z"), lever(id="L-DUP", status="free prose")],
    )

    errors, _ = check_his_hand.evaluate(path, datetime(2026, 9, 16, tzinfo=timezone.utc))

    assert any("duplicate id" in error for error in errors)
    assert any("future" in error for error in errors)
    assert any("invalid status" in error for error in errors)
