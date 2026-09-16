"""Reference observations must not become acceptance or absence claims."""
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "reconcile-closeouts.py"


def load():
    spec = importlib.util.spec_from_file_location("closeout_evidence", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def claim():
    return {"id": "one", "subject": "widget", "text": "done #1", "repo": "o/r"}


def test_merge_reference_is_not_acceptance():
    mod = load()
    report = mod._run([claim()], lambda *a: (True, "MERGED"), lambda *a: "widget")
    assert report["counts"] == {"MERGE_OBSERVED": 1}
    assert len(report["acceptance_unmeasured"]) == 1
    assert report["failing"] == []


def test_failed_lookup_does_not_prove_missing_or_create_remediation():
    mod = load()
    finding = mod.classify_claim(claim(), lambda *a: (False, None))
    assert finding["verdict"] == "PR_UNMEASURED"
    assert mod._finding_to_insight(finding, "o/r") is None


def test_external_home_name_does_not_prove_custody(tmp_path, monkeypatch):
    mod = load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    item = {**claim(), "repo_artifact": "absent", "external_home": "named-only"}
    report = mod._run([item])
    assert len(report["acceptance_unmeasured"]) == 1


def test_cli_returns_unavailable_for_reference_only_evidence(tmp_path, monkeypatch):
    mod = load()
    fixture = tmp_path / "claims.json"
    fixture.write_text(json.dumps([claim()]))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--fixture", str(fixture), "--quiet"])
    run = mod._run
    monkeypatch.setattr(mod, "_run", lambda claims: run(claims, lambda *a: (True, "MERGED"), lambda *a: "widget"))
    assert mod.main() == 77


def test_board_done_claim_without_pr_is_retained(tmp_path, monkeypatch):
    mod = load()
    board = tmp_path / "board.yaml"
    board.write_text("tasks:\n  - id: task-1\n    status: done\n    title: widget\n    repo: o/r\n    dispatch_log:\n      - status: done\n        output: finished without evidence\n")
    monkeypatch.setattr(mod, "board_path", lambda _: board)
    claims = mod._board_claims(0, None)
    assert len(claims) == 1
    assert mod._run(claims)["counts"] == {"UNRECEIPTED": 1}


def test_latest_session_state_replaces_old_closed_record(tmp_path, monkeypatch):
    mod = load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    (tmp_path / "logs").mkdir()
    records = [dict(id="reopened", closed=True, text="done #1"),
               dict(id="reopened", closed=False, text="more work"),
               dict(id="unreceipted", closed=True, text="finished")]
    (tmp_path / "logs/session-claims.jsonl").write_text("\n".join(json.dumps(r) for r in records))
    claims = mod._session_claims(0, None)
    assert [c["id"] for c in claims] == ["unreceipted"]
    assert mod._run(claims)["counts"] == {"UNRECEIPTED": 1}


def test_missing_session_source_remains_unmeasured(tmp_path, monkeypatch):
    mod = load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    errors = []
    assert mod._session_claims(0, None, source_errors=errors) == []
    assert errors == ["session_ledger_unavailable"]


def test_malformed_session_rows_are_counted_without_private_output(tmp_path, monkeypatch):
    mod = load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/session-claims.jsonl").write_text('PRIVATE invalid\n' + json.dumps(dict(id="valid", closed=True, text="done")))
    errors = []
    claims = mod._session_claims(0, None, source_errors=errors)
    assert len(claims) == 1
    assert errors == ["session_record_malformed"]
    assert "PRIVATE" not in json.dumps(errors)


def test_cli_missing_source_cannot_return_empty_success(tmp_path, monkeypatch):
    mod = load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "_board_claims", lambda *args: [])
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check", "--quiet"])
    assert mod.main() == 77
    report = json.loads((tmp_path / "logs/closeout-reconcile.json").read_text())
    assert report["source_errors"] == ["session_ledger_unavailable"]
    assert report["inspected_claim_count"] == 0


def test_limit_preserves_uninspected_denominator(tmp_path, monkeypatch):
    mod = load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    fixture = tmp_path / "claims.json"
    fixture.write_text(json.dumps([dict(id=str(i), text="done") for i in range(3)]))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--fixture", str(fixture), "--limit", "1", "--json", "--quiet"])
    assert mod.main() == 77
    report = json.loads((tmp_path / "logs/closeout-reconcile.json").read_text())
    assert (report["eligible_claim_count"], report["inspected_claim_count"], report["omitted_claim_count"]) == (3, 1, 2)


def test_incomplete_source_suppresses_routing(tmp_path, monkeypatch):
    mod = load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "_board_claims", lambda *args: [claim()])
    run = mod._run
    monkeypatch.setattr(mod, "_run", lambda claims: run(claims, lambda *a: (True, "OPEN")))
    def forbidden(*args):
        raise AssertionError("incomplete source must not route")
    monkeypatch.setattr(mod, "_route_findings", forbidden)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--apply", "--quiet"])
    assert mod.main() == 1
