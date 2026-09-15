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


def test_malformed_entries_and_status_are_reported(tmp_path):
    path = tmp_path / "levers.json"
    write_registry(path, [None, [], lever(status={})])
    errors, census = check_his_hand.evaluate(path, datetime.now(timezone.utc))
    assert len(errors) == 3
    assert census["total"] == 3


def test_unknown_and_later_diagnoses(tmp_path):
    path = tmp_path / "levers.json"
    write_registry(path, [lever(diagnosed_at=None), lever(id="later", diagnosed_at="2026-09-17T00:00:00Z")])
    errors, census = check_his_hand.evaluate(path, datetime(2026, 9, 18, tzinfo=timezone.utc))
    assert not errors
    assert census["diagnosed"] == 1


def test_observatory_producer_is_compatible(tmp_path):
    from limen.observatory.lever import to_lever

    path = tmp_path / "levers.json"
    write_registry(path, [to_lever({"id": "L-OBS"}, None)])
    errors, _ = check_his_hand.evaluate(path, datetime.now(timezone.utc))
    assert errors == []


def test_insight_producer_is_compatible(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("insight_route", ROOT / "scripts" / "insight-route.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "levers.json"
    write_registry(path, [])
    monkeypatch.setattr(module, "HIS_HAND_FILE", path)
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: None)
    module.route_anthony_insight({"id": "L-INSIGHT"}, True)
    errors, _ = check_his_hand.evaluate(path, datetime.now(timezone.utc))
    assert errors == []


def test_implementation_report_preserves_registry_bytes():
    spec = importlib.util.spec_from_file_location(
        "lever_decision_report", ROOT / "scripts" / "lever-decision-report.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = ROOT / "his-hand-levers.json"
    before = path.read_bytes()
    result = module.report(path)
    assert result["covered"] == result["nonterminal"]
    assert result["total"] == 107
    assert path.read_bytes() == before
