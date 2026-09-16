"""Missing coverage is not health or evidence that a historical finding cleared."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def keeper(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "decorum-keeper.py"
    spec = importlib.util.spec_from_file_location("decorum_coverage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "FACE", tmp_path / "face.html")
    monkeypatch.setattr(module, "_value_repos", lambda _: set())
    monkeypatch.setattr(module, "polish_findings", lambda _: ([], False))
    return module


def test_declared_captures_and_skipped_departments_cannot_report_green(keeper, capsys):
    result = keeper.sweep({"off_platform": {"profile": {"capture": "human"}}}, offline=True)
    assert result["status"] == "unmeasured"
    assert result["pass"] is False
    assert result["counts"]["scope_total"] == 2
    assert result["counts"]["unmeasured"] == 2
    assert result["off_platform"] == {"profile": "unmeasured"}
    keeper._print_summary(result)
    assert "UNMEASURED" in capsys.readouterr().out
    keeper._write_face(result)
    face = keeper.FACE.read_text()
    assert "unmeasured" in face
    assert "green — no egg-face" not in face


def test_complete_measured_fixture_can_pass(keeper, monkeypatch):
    monkeypatch.setattr(keeper, "polish_findings", lambda _: ([], True))
    result = keeper.sweep({}, offline=True)
    assert result["status"] == "pass"
    assert result["pass"] is True


@pytest.mark.parametrize("slots", [None, [], "invalid"])
def test_malformed_capture_registry_is_unmeasured(keeper, monkeypatch, slots):
    monkeypatch.setattr(keeper, "polish_findings", lambda _: ([], True))
    result = keeper.sweep({"off_platform": slots}, offline=True)
    assert result["status"] == "unmeasured"
    assert result["counts"]["off_platform_unmeasured"] == 1


def test_known_failure_and_unknown_coverage_both_remain_visible(keeper, monkeypatch):
    finding = keeper._finding("polish", "fixture", "high", "fixture failure", "fixture")
    monkeypatch.setattr(keeper, "polish_findings", lambda _: ([finding], True))
    result = keeper.sweep({"off_platform": {"profile": {}}}, offline=True)
    assert result["status"] == "fail"
    assert result["unmeasured"] is True
    assert result["counts"]["blocking"] == 1


def test_unmeasured_sweep_cannot_close_issue(keeper, monkeypatch):
    calls = []

    def github(args):
        calls.append(args)
        return json.dumps([{"number": 1, "state": "open", "body": f"<!-- {keeper._ISSUE_MARKER}:fixture -->"}])

    monkeypatch.setattr(keeper, "_gh", github)
    result = keeper.mirror_issues({}, {"unmeasured": True, "egg_face_findings": []}, armed=True)
    assert result["closed"] == []
    assert result["closure_unmeasured"] == ["fixture"]
    assert len(calls) == 1
    assert calls[0][0] == "api"


def test_unmeasured_sweep_preserves_prior_recurrence_state(keeper, monkeypatch):
    prior = {"fixture": {"first_seen": "2026-09-01", "sweeps": 1, "cleared": 0, "was_clear": False}}
    monkeypatch.setattr(keeper, "_load_json", lambda _: prior)
    keeper.recurrence_precedents({}, {"unmeasured": True, "egg_face_findings": []}, armed=True)
    state = json.loads((keeper.ROOT / ".limen-private/decorum/recurrence.json").read_text())
    assert state["fixture"]["was_clear"] is False


def test_cli_returns_unmeasured_without_external_effects(keeper, monkeypatch, capsys):
    monkeypatch.setattr(keeper.sys, "argv", ["decorum-keeper", "--json"])
    monkeypatch.setattr(keeper, "_load_yaml", lambda _: {})
    monkeypatch.setattr(keeper, "OUT", keeper.ROOT / "verdict.json")
    monkeypatch.setattr(keeper, "mirror_issues", lambda *_: {})
    monkeypatch.setattr(keeper, "recurrence_precedents", lambda *_: {})
    monkeypatch.setattr(keeper, "_stamp_voice", lambda: None)
    assert keeper.main() == 77
    assert json.loads(capsys.readouterr().out)["status"] == "unmeasured"
