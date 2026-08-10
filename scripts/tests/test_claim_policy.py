"""Hermetic policy and quarantine coverage for PSP-P02-W06/W07."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "scripts" / "claim-policy.py"
QUARANTINE = ROOT / "scripts" / "claim-surface-quarantine.py"
DRILL = ROOT / "scripts" / "claim-quarantine-drill.py"
FIXTURE = ROOT / "scripts" / "tests" / "fixtures" / "positioning-claim-drill"


def _run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _claim() -> dict:
    return {
        "id": "claim.public.safe",
        "statement": "A bounded public statement.",
        "publication_status": "publishable",
        "visibility": "public",
        "source": {
            "url": "https://example.invalid/source",
            "observed_at": "2026-08-01T00:00:00Z",
            "sha256": "a" * 64,
        },
        "valid_until": "2026-08-30T00:00:00Z",
    }


def _export(claim: dict) -> dict:
    return {
        "schema_version": "limen.positioning.claim-ledger-export.v1",
        "forbidden_language": ["guaranteed outcome"],
        "claims": [claim],
    }


def _policy(tmp_path: Path, claim: dict) -> tuple[subprocess.CompletedProcess[str], dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    claims = tmp_path / "claims.json"
    report = tmp_path / "report.json"
    claims.write_text(json.dumps(_export(claim)), encoding="utf-8")
    result = _run(sys.executable, str(POLICY), "--claims", str(claims), "--as-of", "2026-08-10T00:00:00Z", "--report", str(report))
    return result, json.loads(report.read_text(encoding="utf-8"))


def test_policy_accepts_current_public_sourced_claim(tmp_path: Path):
    result, report = _policy(tmp_path, _claim())
    assert result.returncode == 0, result.stderr
    assert report["accepted_claim_ids"] == ["claim.public.safe"]
    assert report["rejected_claims"] == []


def test_policy_rejects_unsourced_stale_private_and_forbidden_claims(tmp_path: Path):
    cases = {
        "unsourced": {"source": {}},
        "stale": {"valid_until": "2026-08-09T23:59:59Z"},
        "private_or_restricted": {"visibility": "private"},
        "forbidden_language": {"statement": "A guaranteed outcome is not a public claim."},
    }
    for reason, update in cases.items():
        claim = _claim()
        claim.update(update)
        result, report = _policy(tmp_path / reason, claim)
        assert result.returncode == 1, result.stderr
        assert report["rejected_claims"] == [{"claim_id": "claim.public.safe", "reasons": [reason]}]


def test_policy_rejects_changed_source_without_fetching(tmp_path: Path):
    claim = _claim()
    claim["source"]["current_sha256"] = "b" * 64
    result, report = _policy(tmp_path, claim)
    assert result.returncode == 1, result.stderr
    assert report["rejected_claims"] == [{"claim_id": "claim.public.safe", "reasons": ["source_changed"]}]


def test_quarantine_copies_and_removes_each_declared_public_surface(tmp_path: Path):
    source = tmp_path / "generated"
    shutil.copytree(FIXTURE / "generated", source)
    report = tmp_path / "policy-report.json"
    policy = _run(
        sys.executable, str(POLICY), "--claims", str(FIXTURE / "claims.json"), "--as-of", "2026-08-10T00:00:00Z", "--report", str(report)
    )
    assert policy.returncode == 1, policy.stderr
    output = tmp_path / "quarantined"
    quarantine = _run(
        sys.executable, str(QUARANTINE), "--source-root", str(source), "--output-root", str(output),
        "--manifest", str(FIXTURE / "public-surfaces.json"), "--policy-report", str(report)
    )
    assert quarantine.returncode == 0, quarantine.stderr
    for path in ("frontdoor.md", "profile.md"):
        assert "SYNTHETIC FALSE CLAIM" in (source / path).read_text(encoding="utf-8")
        quarantined = (output / path).read_text(encoding="utf-8")
        assert "SYNTHETIC FALSE CLAIM" not in quarantined
        assert "positioning-claim: claim.synthetic.false:quarantined" in quarantined


def test_synthetic_false_claim_drill_proves_full_surface_quarantine():
    result = _run(sys.executable, str(DRILL), "--fixture-dir", str(FIXTURE), "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["public_surface_count"] == 2
    assert report["publication_effect"] == "none"
