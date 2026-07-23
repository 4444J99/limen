from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "setup-rulesets.py"
REPORT = ROOT / "docs" / "RULESETS-DRYRUN.md"


def test_setup_rulesets_preserves_source_branches() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    report = REPORT.read_text(encoding="utf-8")

    assert "allow_auto_merge=true" in text
    assert "delete_branch_on_merge=false" in text
    assert "delete_branch_on_merge=true" not in text
    assert "source branches remain after merge" in report
    assert "receipt-backed reaping" in report
    assert "delete_branch_on_merge=true" not in report
