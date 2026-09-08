"""Production regressions for metadata-only architectural assessments."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "architectural_assessments", ROOT / "scripts/mint_architectural_diagnostics.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _pr(**changes):
    return {
        "repository": "owner/repo",
        "number": 1,
        "title": "Security token refresh changes",
        "head_branch": "fix/security",
        **changes,
    }


def _assert_unverified(data):
    assert data["schema"] == "limen.architectural_assessment.v1"
    assert data["verification_status"] == "unverified"
    assert data["establishes_custody"] is False
    assert data["establishes_landing"] is False
    assert data["diagnostic_assessment"]["disposition"] == "UNVERIFIED_ASSESSMENT"
    assert data["diagnostic_assessment"]["classification"] == "Unverified architectural triage"
    assert "protected_boundary_verification" not in data
    assert data["protected_boundary_assessment"]["zero_touch_verified"] is False
    assert data["protected_boundary_assessment"]["quarantined_from_auto_merge"] is False
    assert "This PR remains OPEN" not in data["diagnostic_comment_body"]
    assert "detached cleanly" not in data["diagnostic_comment_body"]


def test_title_heuristics_cannot_mint_verification_or_lifecycle_proof():
    record = MODULE.analyze_pr_architecture(_pr())
    assert record is not None
    _assert_unverified(record)
    assert record["diagnostic_assessment"]["observed_divergence"].startswith("Unverified hypothesis:")


@pytest.mark.parametrize(
    "title",
    [
        "Sentinel security",
        "conduct principal RBAC",
        "Stripe billing",
        "governance protocol",
        "recovery control plane",
    ],
)
def test_assessment_retains_domain_coverage(title):
    record = MODULE.analyze_pr_architecture(_pr(title=title, head_branch="topic"))
    assert record is not None
    _assert_unverified(record)


@pytest.mark.parametrize(
    "changes",
    [
        {"repository": "owner/universal-mail--automation"},
        {"repository": "4444J99/limen", "number": 2543},
        {"head_branch": "task/private-document-review-20260825"},
        {"head_branch": "feat/conduct-role-hardening-and-permissions"},
    ],
)
def test_generator_excludes_protected_metadata_without_claiming_runtime_isolation(changes):
    assert MODULE.analyze_pr_architecture(_pr(**changes)) is None


def test_cli_uses_explicit_inventory_in_clean_checkout(tmp_path):
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"pull_requests": [_pr()]}))
    output = tmp_path / "output"
    assert MODULE.main(["--inventory", str(inventory), "--output-dir", str(output)]) == 0
    _assert_unverified(json.loads((output / "architectural_diagnostic_owner_repo_1.json").read_text()))
    manifest = json.loads((output / "architectural_diagnostics_manifest.json").read_text())
    assert manifest["verification_status"] == "unverified"
    assert manifest["total_assessments"] == 1
    assert "protected_boundaries_enforced" not in manifest


def test_cli_requires_inventory_instead_of_using_untracked_scratch():
    with pytest.raises(SystemExit) as error:
        MODULE.main([])
    assert error.value.code == 2


def test_historical_outputs_have_no_false_verification_or_preservation_claims():
    records = list((ROOT / "docs/receipts").glob("architectural_diagnostic_*.json"))
    assert records
    keys = set()
    for path in records:
        record = json.loads(path.read_text())
        _assert_unverified(record)
        keys.add((record["target"]["repository"], record["target"]["pull_request"]))
    manifest = json.loads((ROOT / "docs/receipts/architectural_diagnostics_manifest.json").read_text())
    assert manifest["schema"] == "limen.architectural_assessment_manifest.v1"
    assert manifest["verification_status"] == "unverified"
    assert manifest["establishes_custody"] is False
    assert manifest["establishes_landing"] is False
    assert "protected_boundaries_enforced" not in manifest
    assert manifest["total_assessments"] == len(keys)
    assert {(r["repository"], r["pull_request"]) for r in manifest["diagnostics"]} == keys
    assert all(row["disposition"] == "UNVERIFIED_ASSESSMENT" for row in manifest["diagnostics"])
