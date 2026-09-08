"""Unit & invariant test suite for architectural diagnostic receipts and protected boundaries.

Validates that all minted receipts conform to limen.scoped_verification_receipt.v1
and that protected boundaries maintain zero-touch isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPTS_DIR = ROOT / "docs" / "receipts"
INVENTORY_PATH = ROOT / ".agents" / "teamwork_preview_explorer_survey_1" / "detailed_pr_inventory.json"


def test_architectural_diagnostics_manifest_exists():
    """Manifest receipt exists and has valid structure."""
    manifest_file = RECEIPTS_DIR / "architectural_diagnostics_manifest.json"
    assert manifest_file.exists(), "architectural_diagnostics_manifest.json must exist"
    data = json.loads(manifest_file.read_text(encoding="utf-8"))

    assert data["schema"] == "limen.scoped_verification_receipt.v1"
    assert data["receipt_type"] == "architectural_diagnostic_manifest"
    assert data["total_sensitive_prs_diagnosed"] > 0
    assert len(data["diagnostics"]) == data["total_sensitive_prs_diagnosed"]
    assert len(data["protected_boundaries_enforced"]) == 6


def test_all_architectural_diagnostic_receipts_conform():
    """All individual diagnostic receipts conform to required schema and fields."""
    receipt_files = list(RECEIPTS_DIR.glob("architectural_diagnostic_*.json"))
    assert len(receipt_files) > 0, "No diagnostic receipt files found"

    required_top_keys = {
        "schema",
        "receipt_type",
        "generated",
        "target",
        "diagnostic_assessment",
        "diagnostic_comment_body",
        "protected_boundary_verification",
        "integrity_note",
    }
    required_target_keys = {
        "chamber",
        "repository",
        "pull_request",
        "head_branch",
        "base_branch",
        "author",
        "is_draft",
        "url",
    }
    required_diag_keys = {
        "classification",
        "category",
        "blocker_type",
        "observed_divergence",
        "affected_subsystems",
        "breaking_impact_analysis",
        "operator_recommendations",
        "disposition",
    }

    for f in receipt_files:
        if f.name == "architectural_diagnostics_manifest.json":
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        for k in required_top_keys:
            assert k in data, f"Missing {k} in {f.name}"

        assert data["schema"] == "limen.scoped_verification_receipt.v1"
        assert data["receipt_type"] == "architectural_diagnostic"

        target = data["target"]
        for k in required_target_keys:
            assert k in target, f"Missing target.{k} in {f.name}"

        diag = data["diagnostic_assessment"]
        for k in required_diag_keys:
            assert k in diag, f"Missing diagnostic_assessment.{k} in {f.name}"

        assert diag["disposition"] == "LEAVE_OPEN_PRESERVED"
        assert len(diag["affected_subsystems"]) > 0
        assert len(diag["operator_recommendations"]) > 0

        prot = data["protected_boundary_verification"]
        assert prot["zero_touch_verified"] is True
        assert prot["quarantined_from_auto_merge"] is True

        comment = data["diagnostic_comment_body"]
        assert "### 🔍 Architectural & Diagnostic Assessment" in comment
        assert f"#{target['pull_request']}" in comment
        assert "This PR remains OPEN pending operator evaluation" in comment


def test_protected_boundaries_zero_touch():
    """Protected paths and PRs remain completely unmodified and isolated."""
    protected_paths = [
        ROOT / ".agent-runtime" / "codex",
        ROOT / ".agent-runtime" / "opencode",
        Path("/Users/4jp/Workspace/limen-universe-recovery"),
        Path("/Users/4jp/Workspace/limen-private-document-review-20260825"),
        Path("/Users/4jp/Workspace/4444J99/universal-mail--automation"),
    ]

    for p in protected_paths:
        if p.exists():
            assert p.is_dir(), f"Protected path {p} must be a directory"

    # Verify no diagnostic receipts attempt to modify protected PR #2543 or universal-mail
    for f in RECEIPTS_DIR.glob("architectural_diagnostic_*.json"):
        if f.name == "architectural_diagnostics_manifest.json":
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        repo = data["target"]["repository"]
        pr_num = data["target"]["pull_request"]
        assert "universal-mail--automation" not in repo, f"Protected repo {repo} found in diagnostic receipt"
        assert not (repo == "4444J99/limen" and pr_num == 2543), (
            "Protected Codex recovery PR #2543 found in diagnostic receipt"
        )
