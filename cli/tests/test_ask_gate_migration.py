from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-ask-gate-migration.py"
RECEIPT = ROOT / "docs" / "ask-gate-migration-2026-07-12.json"


def _module():
    spec = importlib.util.spec_from_file_location("check_ask_gate_migration", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_receipt_passes_cli() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--receipt", str(RECEIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "52 frozen tasks" in result.stdout
    assert "29 children" in result.stdout


def test_verifier_rejects_hash_and_coverage_drift() -> None:
    verifier = _module()
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    broken = copy.deepcopy(payload)
    broken["frozen_ids"] = broken["frozen_ids"][1:]
    errors = verifier.verify_receipt(broken)
    assert any("digest mismatch" in error for error in errors)
    assert any("tasks mapping" in error for error in errors)


def test_verifier_rejects_raw_secret_or_private_path() -> None:
    verifier = _module()
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    broken = copy.deepcopy(payload)
    broken["safety"]["bad_example"] = "-" * 5 + "BEGIN PGP PRIVATE KEY" + "-" * 5
    broken["safety"]["local_path"] = "/Users/example/private-corpus"
    errors = verifier.verify_receipt(broken)
    assert any("private-key-block" in error for error in errors)
    assert any("private/local path" in error for error in errors)


def test_verifier_rejects_supersession_drift() -> None:
    verifier = _module()
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    broken = copy.deepcopy(payload)
    broken["tasks"]["GH-organvm-limen-775"]["receipt_target"] = "https://github.com/organvm/limen/issues/775"
    errors = verifier.verify_receipt(broken)
    assert any("canonical issue #790" in error for error in errors)


def test_verifier_rejects_split_archive_without_admitted_children() -> None:
    verifier = _module()
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    broken = copy.deepcopy(payload)
    broken["tasks"]["DISCOVER-organvm-arca"]["predicate"] = "test -f docs/ask-gate-migration-2026-07-12.json"
    errors = verifier.verify_receipt(broken)
    assert any("split archive predicate" in error for error in errors)


def test_verifier_rejects_terminal_issue_without_completed_reason() -> None:
    verifier = _module()
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    broken = copy.deepcopy(payload)
    broken["tasks"]["GH-organvm-limen-793"]["predicate"] = (
        'test "$(gh issue view 793 --repo organvm/limen --json state --jq .state)" = CLOSED'
    )
    errors = verifier.verify_receipt(broken)
    assert any("stateReason COMPLETED" in error for error in errors)


def test_verifier_rejects_application_phase_or_rejection_drift() -> None:
    verifier = _module()
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    broken = copy.deepcopy(payload)
    broken["application_contract"]["phases"].reverse()
    broken["application_contract"]["rejection_policy"] = "continue"
    errors = verifier.verify_receipt(broken)
    assert any("application_contract.children.name" in error for error in errors)
    assert any("rejection_policy" in error for error in errors)
