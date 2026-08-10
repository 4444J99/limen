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
            "url": "https://example.com/source",
            "observed_at": "2026-08-01T00:00:00Z",
            "sha256": "a" * 64,
        },
        "valid_until": "2026-08-30T00:00:00Z",
    }


def _export(claims: list[dict]) -> dict:
    return {
        "schema_version": "limen.positioning.claim-ledger-export.v1",
        "forbidden_language": ["guaranteed outcome"],
        "claims": claims,
    }


def _policy(tmp_path: Path, *claims: dict) -> tuple[subprocess.CompletedProcess[str], dict]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    claims_path = tmp_path / "claims.json"
    report = tmp_path / "report.json"
    claims_path.write_text(json.dumps(_export(list(claims))), encoding="utf-8")
    result = _run(
        sys.executable,
        str(POLICY),
        "--claims",
        str(claims_path),
        "--as-of",
        "2026-08-10T00:00:00Z",
        "--report",
        str(report),
    )
    assert report.is_file(), (
        "claim-policy.py did not write its report; "
        f"returncode={result.returncode}; stdout={result.stdout!r}; stderr={result.stderr!r}"
    )
    try:
        report_document = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(
            "claim-policy.py wrote an unreadable report; "
            f"returncode={result.returncode}; stdout={result.stdout!r}; stderr={result.stderr!r}"
        ) from exc
    return result, report_document


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


def test_policy_rejects_nonpublic_future_and_invalid_source_windows(tmp_path: Path):
    cases = {
        "private_or_restricted": {"source": {**_claim()["source"], "url": "file:///private/evidence"}},
        "future_source": {"source": {**_claim()["source"], "observed_at": "2026-08-11T00:00:00Z"}},
        "invalid_validity_window": {"valid_until": "2026-07-31T23:59:59Z"},
    }
    for reason, update in cases.items():
        claim = _claim()
        claim.update(update)
        result, report = _policy(tmp_path / reason, claim)
        assert result.returncode == 1, result.stderr
        reported = report["rejected_claims"][0]["reasons"]
        assert reason in reported


def test_policy_rejects_nonpublic_https_hosts_and_ports(tmp_path: Path):
    urls = {
        "localhost": "https://localhost/evidence",
        "local-domain": "https://source.local/evidence",
        "loopback-ipv4": "https://127.0.0.1/evidence",
        "loopback-ipv6": "https://[::1]/evidence",
        "legacy-loopback": "https://127.1/evidence",
        "legacy-hex-loopback": "https://0x7f.0.0.1/evidence",
        "private-ip": "https://10.0.0.1/evidence",
        "single-label-internal": "https://intranet/evidence",
        "internal-suffix": "https://source.internal/evidence",
        "nonstandard-port": "https://example.com:8443/evidence",
    }
    for suffix, url in urls.items():
        claim = _claim()
        claim["source"]["url"] = url
        result, report = _policy(tmp_path / suffix, claim)
        assert result.returncode == 1, result.stderr
        assert report["rejected_claims"] == [
            {"claim_id": "claim.public.safe", "reasons": ["private_or_restricted"]}
        ]


def test_policy_quarantines_malformed_claim_timestamps_without_aborting_report(tmp_path: Path):
    cases = {
        "source-observed-at": {"source": {**_claim()["source"], "observed_at": "not-a-timestamp"}},
        "valid-until": {"valid_until": "2026-08-30"},
    }
    for suffix, update in cases.items():
        malformed = _claim()
        malformed["id"] = f"claim.public.malformed-{suffix}"
        malformed.update(update)
        valid = _claim()
        result, report = _policy(tmp_path / suffix, malformed, valid)
        assert result.returncode == 1, result.stderr
        assert report["accepted_claim_ids"] == ["claim.public.safe"]
        assert report["rejected_claims"] == [
            {
                "claim_id": f"claim.public.malformed-{suffix}",
                "reasons": ["invalid_timestamp"],
            }
        ]
        serialized = json.dumps(report)
        assert "not-a-timestamp" not in serialized
        assert "2026-08-30" not in serialized


def test_policy_requires_forbidden_language_field_but_allows_empty_list(tmp_path: Path):
    claims_path = tmp_path / "claims.json"
    document = _export([_claim()])
    document["forbidden_language"] = []
    claims_path.write_text(json.dumps(document), encoding="utf-8")
    allowed_report = tmp_path / "allowed-report.json"
    allowed = _run(
        sys.executable,
        str(POLICY),
        "--claims",
        str(claims_path),
        "--as-of",
        "2026-08-10T00:00:00Z",
        "--report",
        str(allowed_report),
    )
    assert allowed.returncode == 0, allowed.stderr
    assert allowed_report.is_file()

    del document["forbidden_language"]
    claims_path.write_text(json.dumps(document), encoding="utf-8")
    omitted_report = tmp_path / "omitted-report.json"
    result = _run(
        sys.executable,
        str(POLICY),
        "--claims",
        str(claims_path),
        "--as-of",
        "2026-08-10T00:00:00Z",
        "--report",
        str(omitted_report),
    )
    assert result.returncode == 2
    assert "forbidden_language is required" in result.stderr
    assert not omitted_report.exists()


def test_policy_rejects_claims_report_file_aliases_without_mutating_source(tmp_path: Path):
    for alias_kind in ("identical", "hardlink"):
        case_dir = tmp_path / alias_kind
        case_dir.mkdir()
        claims_path = case_dir / "claims.json"
        claims_path.write_text(json.dumps(_export([_claim()])), encoding="utf-8")
        original = claims_path.read_bytes()
        if alias_kind == "identical":
            report_path = claims_path
        else:
            report_path = case_dir / "report.json"
            report_path.hardlink_to(claims_path)
        result = _run(
            sys.executable,
            str(POLICY),
            "--claims",
            str(claims_path),
            "--as-of",
            "2026-08-10T00:00:00Z",
            "--report",
            str(report_path),
        )
        assert result.returncode == 2
        assert "must refer to distinct files" in result.stderr
        assert claims_path.read_bytes() == original


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
        "--manifest", str(FIXTURE / "public-surfaces.json"), "--policy-report", str(report), "--json"
    )
    assert quarantine.returncode == 0, quarantine.stderr
    quarantine_report = json.loads(quarantine.stdout)
    assert quarantine_report["affected_surface_count"] == 2
    assert quarantine_report["quarantined_occurrence_count"] == 2
    for path in ("frontdoor.md", "profile.md"):
        assert "SYNTHETIC FALSE CLAIM" in (source / path).read_text(encoding="utf-8")
        quarantined = (output / path).read_text(encoding="utf-8")
        assert "SYNTHETIC FALSE CLAIM" not in quarantined
        assert "positioning-claim: claim.synthetic.false:quarantined" in quarantined


def test_quarantine_removes_claim_absent_from_policy_report_with_public_safe_reason(tmp_path: Path):
    accepted = _claim()
    rejected = _claim()
    rejected["id"] = "claim.public.rejected"
    rejected["source"]["current_sha256"] = "b" * 64
    policy, policy_report = _policy(tmp_path / "policy", accepted, rejected)
    assert policy.returncode == 1, policy.stderr
    report_path = tmp_path / "policy-report.json"
    report_path.write_text(json.dumps(policy_report), encoding="utf-8")

    source = tmp_path / "generated"
    source.mkdir()
    rendered = """# Generated public surface
<!-- positioning-claim: claim.public.safe:start -->
ACCEPTED PUBLIC CLAIM
<!-- positioning-claim: claim.public.safe:end -->
<!-- positioning-claim: claim.public.rejected:start -->
REJECTED PUBLIC CLAIM
<!-- positioning-claim: claim.public.rejected:end -->
<!-- positioning-claim: claim.surface.unknown:start -->
UNKNOWN PUBLIC CLAIM
<!-- positioning-claim: claim.surface.unknown:end -->
"""
    surface = source / "frontdoor.md"
    surface.write_text(rendered, encoding="utf-8")
    manifest = {
        "schema_version": "limen.positioning.public-surface-manifest.v1",
        "surfaces": [{
            "id": "frontdoor",
            "path": "frontdoor.md",
            "claim_ids": [
                "claim.public.safe",
                "claim.public.rejected",
                "claim.surface.unknown",
            ],
        }],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "quarantined"
    quarantine = _run(
        sys.executable,
        str(QUARANTINE),
        "--source-root",
        str(source),
        "--output-root",
        str(output),
        "--manifest",
        str(manifest_path),
        "--policy-report",
        str(report_path),
        "--json",
    )
    assert quarantine.returncode == 0, quarantine.stderr
    result = json.loads(quarantine.stdout)
    assert result["quarantined_claims"] == [
        {"claim_id": "claim.public.rejected", "reasons": ["source_changed"]},
        {"claim_id": "claim.surface.unknown", "reasons": ["absent_from_policy_report"]},
    ]
    assert result["publication_effect"] == "none"
    staged = (output / "frontdoor.md").read_text(encoding="utf-8")
    assert "ACCEPTED PUBLIC CLAIM" in staged
    assert "REJECTED PUBLIC CLAIM" not in staged
    assert "UNKNOWN PUBLIC CLAIM" not in staged
    assert surface.read_text(encoding="utf-8") == rendered


def test_quarantine_rejects_unknown_marker_undeclared_by_surface_manifest(tmp_path: Path):
    policy, policy_report = _policy(tmp_path / "policy", _claim())
    assert policy.returncode == 0, policy.stderr
    report_path = tmp_path / "policy-report.json"
    report_path.write_text(json.dumps(policy_report), encoding="utf-8")
    source = tmp_path / "generated"
    source.mkdir()
    (source / "frontdoor.md").write_text(
        """<!-- positioning-claim: claim.public.safe:start -->safe<!-- positioning-claim: claim.public.safe:end -->
<!-- positioning-claim: claim.surface.unknown:start -->unknown<!-- positioning-claim: claim.surface.unknown:end -->
""",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": "limen.positioning.public-surface-manifest.v1",
        "surfaces": [{
            "id": "frontdoor",
            "path": "frontdoor.md",
            "claim_ids": ["claim.public.safe"],
        }],
    }), encoding="utf-8")
    output = tmp_path / "quarantined"
    quarantine = _run(
        sys.executable,
        str(QUARANTINE),
        "--source-root",
        str(source),
        "--output-root",
        str(output),
        "--manifest",
        str(manifest_path),
        "--policy-report",
        str(report_path),
    )
    assert quarantine.returncode == 2
    assert "marker/manifest mismatch" in quarantine.stderr
    assert not output.exists()


def test_quarantine_validates_accepted_and_rejected_policy_universe_before_writing(tmp_path: Path):
    source = tmp_path / "generated"
    shutil.copytree(FIXTURE / "generated", source)
    policy, base_report = _policy(tmp_path / "policy", {
        **_claim(),
        "id": "claim.synthetic.false",
        "source": {
            **_claim()["source"],
            "current_sha256": "b" * 64,
        },
    })
    assert policy.returncode == 1, policy.stderr
    cases = {
        "missing-accepted": {key: value for key, value in base_report.items() if key != "accepted_claim_ids"},
        "invalid-accepted": {**base_report, "accepted_claim_ids": ["NOT-PUBLIC-SAFE"]},
        "overlap": {**base_report, "accepted_claim_ids": ["claim.synthetic.false"]},
    }
    for suffix, report in cases.items():
        report_path = tmp_path / f"{suffix}-report.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        output = tmp_path / f"{suffix}-quarantined"
        quarantine = _run(
            sys.executable,
            str(QUARANTINE),
            "--source-root",
            str(source),
            "--output-root",
            str(output),
            "--manifest",
            str(FIXTURE / "public-surfaces.json"),
            "--policy-report",
            str(report_path),
        )
        assert quarantine.returncode == 2
        assert not output.exists()


def test_quarantine_rejects_incomplete_manifest_before_writing(tmp_path: Path):
    source = tmp_path / "generated"
    shutil.copytree(FIXTURE / "generated", source)
    manifest = json.loads((FIXTURE / "public-surfaces.json").read_text(encoding="utf-8"))
    for surface in manifest["surfaces"]:
        surface["claim_ids"] = ["claim.some-other-id"]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = tmp_path / "policy-report.json"
    policy = _run(
        sys.executable, str(POLICY), "--claims", str(FIXTURE / "claims.json"), "--as-of", "2026-08-10T00:00:00Z", "--report", str(report)
    )
    assert policy.returncode == 1, policy.stderr
    output = tmp_path / "quarantined"
    quarantine = _run(
        sys.executable, str(QUARANTINE), "--source-root", str(source), "--output-root", str(output),
        "--manifest", str(manifest_path), "--policy-report", str(report)
    )
    assert quarantine.returncode == 2
    assert not output.exists()


def test_quarantine_rejects_marker_omitted_from_one_surface_manifest_entry(tmp_path: Path):
    source = tmp_path / "generated"
    shutil.copytree(FIXTURE / "generated", source)
    manifest = json.loads((FIXTURE / "public-surfaces.json").read_text(encoding="utf-8"))
    manifest["surfaces"][1]["claim_ids"] = ["claim.some-other-id"]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = tmp_path / "policy-report.json"
    policy = _run(
        sys.executable,
        str(POLICY),
        "--claims",
        str(FIXTURE / "claims.json"),
        "--as-of",
        "2026-08-10T00:00:00Z",
        "--report",
        str(report),
    )
    assert policy.returncode == 1, policy.stderr
    output = tmp_path / "quarantined"
    quarantine = _run(
        sys.executable,
        str(QUARANTINE),
        "--source-root",
        str(source),
        "--output-root",
        str(output),
        "--manifest",
        str(manifest_path),
        "--policy-report",
        str(report),
    )
    assert quarantine.returncode == 2
    assert "marker/manifest mismatch" in quarantine.stderr
    assert not output.exists()


def test_quarantine_validates_all_markers_before_writing(tmp_path: Path):
    source = tmp_path / "generated"
    shutil.copytree(FIXTURE / "generated", source)
    (source / "profile.md").write_text("# Missing bounded marker\n", encoding="utf-8")
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
    assert quarantine.returncode == 2
    assert not output.exists()


def test_quarantine_rejects_source_symlink(tmp_path: Path):
    source = tmp_path / "generated"
    shutil.copytree(FIXTURE / "generated", source)
    external = tmp_path / "external.md"
    external.write_text("private source material", encoding="utf-8")
    (source / "profile.md").unlink()
    (source / "profile.md").symlink_to(external)
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
    assert quarantine.returncode == 2
    assert not output.exists()


def test_quarantine_rejects_output_descendant_without_mutating_source(tmp_path: Path):
    source = tmp_path / "generated"
    shutil.copytree(FIXTURE / "generated", source)
    original = {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    report = tmp_path / "policy-report.json"
    policy = _run(
        sys.executable,
        str(POLICY),
        "--claims",
        str(FIXTURE / "claims.json"),
        "--as-of",
        "2026-08-10T00:00:00Z",
        "--report",
        str(report),
    )
    assert policy.returncode == 1, policy.stderr
    output = source / "quarantined"
    quarantine = _run(
        sys.executable,
        str(QUARANTINE),
        "--source-root",
        str(source),
        "--output-root",
        str(output),
        "--manifest",
        str(FIXTURE / "public-surfaces.json"),
        "--policy-report",
        str(report),
    )
    assert quarantine.returncode == 2
    assert "outside the source root" in quarantine.stderr
    assert not output.exists()
    assert {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    } == original


def test_synthetic_false_claim_drill_proves_full_surface_quarantine():
    result = _run(sys.executable, str(DRILL), "--fixture-dir", str(FIXTURE), "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["public_surface_count"] == 2
    assert report["publication_effect"] == "none"
