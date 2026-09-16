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
