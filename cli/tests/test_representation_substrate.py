from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "organs" / "representation" / "validate-representation.py"
MODULE = ROOT / "organs" / "representation" / "representation_substrate.py"
CHRIS = ROOT / "organs" / "representation" / "records" / "christopher-author-one.yaml"
ET4L = ROOT / "organs" / "representation" / "records" / "et4l.yaml"
OPPORTUNITY = ROOT / "organs" / "representation" / "opportunities" / "literary-submission-landscape.yaml"

spec = importlib.util.spec_from_file_location("representation_substrate", MODULE)
rs = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["representation_substrate"] = rs
spec.loader.exec_module(rs)


def run_validator(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *(str(arg) for arg in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def run_tool(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE), *(str(arg) for arg in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def load_record(path: Path = CHRIS) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_representation_fleet_passes():
    result = run_validator("--fleet", "--quiet")
    assert result.returncode == 0, result.stdout + result.stderr


def test_fleet_includes_non_writer_project_proof():
    et4l = load_record(ET4L)

    assert et4l["subject"]["type"] == "project"
    assert "writer_submission" not in et4l["subject"]["representation_modes"]
    assert any(output["mode"] == "project_page" for output in et4l["outputs"])
    assert et4l["artifacts"]["next_reviewable_output"]


def test_validator_requires_next_reviewable_output_and_acceptance_gates(tmp_path: Path):
    doc = load_record()
    doc.pop("artifacts")
    doc["outputs"][0].pop("acceptance_gates")
    path = tmp_path / "missing-review-gates.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_validator(path)

    assert result.returncode == 1
    assert "artifacts.next_reviewable_output is required" in result.stdout
    assert "outputs[0] acceptance_gates must be a non-empty list" in result.stdout


def test_report_grade_record_requires_local_remote_and_web_sources(tmp_path: Path):
    doc = load_record()
    doc["sources"] = [source for source in doc["sources"] if source["source_type"] != "web"]
    path = tmp_path / "chris-missing-web.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_validator(path)

    assert result.returncode == 1
    assert "report-grade records must include local_repo, remote_repo, and web sources" in result.stdout


def test_private_relational_claim_requires_message_source(tmp_path: Path):
    doc = load_record()
    doc["claims"].append(
        {
            "id": "private-fit",
            "label": "Private fit",
            "summary": "Private persona fit.",
            "visibility": "private",
            "source_ids": ["local-relationship-pipeline"],
            "private_relational_insight": True,
            "public_ok": False,
        }
    )
    path = tmp_path / "chris-private-fit.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_validator(path)

    assert result.returncode == 1
    assert "private relational/persona claims require messages source evidence" in result.stdout


def test_privacy_validator_blocks_private_excerpts_and_contact_data(tmp_path: Path):
    doc = load_record()
    doc["sources"].append(
        {
            "id": "message-leak",
            "source_type": "messages",
            "privacy_level": "sensitive",
            "source_ref": "messages://thread/redacted",
            "captured_at": "2026-07-08T00:00:00Z",
            "claim_ids": ["message-research-authorized-later"],
            "confidence": "medium",
            "note": "direct quote from a private thread",
            "excerpt": "private text should not be tracked",
        }
    )
    doc["contact_data"] = "writer@example.com"
    path = tmp_path / "leaky.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_validator(path)

    assert result.returncode == 1
    assert "forbidden tracked/public private field" in result.stdout
    assert "contact email detected" in result.stdout
    assert "appears to expose private text" in result.stdout


def test_mention_indexer_filters_false_positive_names():
    profile = load_record()
    text = (
        "Christian sent a note about Christopher Nolan. "
        "Chris and the Object Lessons relaunch came up later. "
        "Christopher Author-One was also tied to Speech Score."
    )

    rows = rs.index_mentions(text, profile)
    matches = [row["match"] for row in rows]

    assert "Christian" not in matches
    assert "Christopher Nolan" not in " ".join(matches)
    assert "Chris" in matches
    assert "Christopher Author-One" in matches


def test_public_renderer_excludes_private_message_claim_without_claim_approval():
    doc = load_record()
    doc["claims"].append(
        {
            "id": "approved-later-message-claim",
            "label": "Message-derived claim",
            "summary": "This should not render without claim-level public approval.",
            "visibility": "private",
            "source_ids": ["authorized-message-source"],
            "public_ok": True,
            "private_relational_insight": True,
        }
    )
    doc["sources"].append(
        {
            "id": "authorized-message-source",
            "source_type": "messages",
            "privacy_level": "sensitive",
            "source_ref": "messages://thread/redacted",
            "captured_at": "2026-07-08T00:00:00Z",
            "claim_ids": ["approved-later-message-claim"],
            "confidence": "high",
            "note": "Authorized message source reference only, with no private text.",
        }
    )

    public_page = rs.render_record(doc, "public_page_draft")

    assert "Message-derived claim" not in public_page
    assert "authorized-message-source" not in public_page
    assert "Public writing record" in public_page


def test_public_page_excludes_private_local_only_claim_without_claim_approval():
    doc = load_record()
    doc["claims"].append(
        {
            "id": "local-only-public-request",
            "label": "Local-only claim",
            "summary": "This private local source must not appear without claim-level approval.",
            "visibility": "private",
            "source_ids": ["local-relationship-pipeline"],
            "public_ok": True,
        }
    )
    for output in doc["outputs"]:
        if output["mode"] == "public_page_draft":
            output["claim_ids"].append("local-only-public-request")

    public_page = rs.render_record(doc, "public_page_draft")

    assert "Local-only claim" not in public_page
    assert "relationship-pipeline" not in public_page
    assert "/Users/4jp" not in public_page


def test_public_renderer_can_include_claim_level_approved_private_claim():
    doc = load_record()
    approved = copy.deepcopy(doc)
    approved["claims"].append(
        {
            "id": "public-approved-private-context",
            "label": "Approved private context",
            "summary": "Subject approved this private-source context for public copy.",
            "visibility": "private",
            "source_ids": ["local-relationship-pipeline"],
            "public_ok": True,
        }
    )
    approved["approvals"].append(
        {
            "id": "claim-public-approval",
            "approval_type": "public_claim",
            "status": "approved",
            "claim_ids": ["public-approved-private-context"],
            "note": "Claim-level public approval recorded without exposing source text.",
        }
    )
    for output in approved["outputs"]:
        if output["mode"] == "public_page_draft":
            output["claim_ids"].append("public-approved-private-context")

    public_page = rs.render_record(approved, "public_page_draft")

    assert "Approved private context" in public_page


def test_mode_renderers_share_one_source_backed_chris_record():
    doc = load_record()

    private_dossier = rs.render_record(doc, "private_dossier")
    public_page = rs.render_record(doc, "public_page_draft")
    submission_packet = rs.render_record(doc, "writer_submission")
    collaboration_packet = rs.render_record(doc, "collaboration_packet")

    assert private_dossier.startswith("# Private Dossier")
    assert public_page.startswith("# Public Page Draft")
    assert submission_packet.startswith("# Writer Submission Packet")
    assert collaboration_packet.startswith("# Collaboration Packet")
    for section in (
        "## Subject Summary",
        "## Works",
        "## Relations",
        "## Source Appendix Summary",
        "## Approvals Required",
        "## No-Outward-Action Notice",
    ):
        assert section in private_dossier
    assert "Speech Score lineage" in private_dossier
    assert "Speech Score lineage" not in public_page
    assert "No submission, outreach, or form action" in submission_packet
    assert "Object Lessons lineage" in collaboration_packet


def test_chris_public_page_draft_uses_public_profile_evidence_only():
    result = run_tool("packet", CHRIS, "--mode", "public_page_draft")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "## Public Page Draft Copy" in result.stdout
    assert "Christopher Author-One can be presented from public evidence and claim-approved context only" in result.stdout
    assert "Public writing record" in result.stdout
    assert "Speech Score lineage" not in result.stdout
    assert "Object Lessons lineage" not in result.stdout
    assert "/Users/4jp" not in result.stdout


def test_chris_writer_submission_has_readiness_blockers_not_invented_manuscript_details():
    result = run_tool("packet", CHRIS, "--mode", "writer_submission")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "## Submission Readiness" in result.stdout
    assert "Candidate work metadata staged: Public-profile submission readiness packet." in result.stdout
    assert "Missing manuscript data: Genre, Form, Length, Rights status, Content/source ref." in result.stdout
    assert "Speech Score lineage" not in result.stdout
    assert "Object Lessons lineage" not in result.stdout


def test_literary_packet_cli_smoke_for_chris_and_market_record():
    result = run_tool(
        "literary-packet",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        "chris-public-profile-readiness",
        "--route",
        "submittable-discover-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("# Literary Desk Packet: Christopher Author-One")
    assert "Opportunity record: literary-submission-landscape-v3" in result.stdout
    assert "Candidate work/profile: chris-public-profile-readiness" in result.stdout
    assert "Selected venue/route: submittable-discover-route" in result.stdout
    assert "Desk status: BLOCKED" in result.stdout
    assert "## Fit Check" in result.stdout
    assert "No submission, outreach, upload, publication, contact, or form action is performed" in result.stdout


def test_literary_packet_marks_blocked_when_candidate_work_metadata_is_missing(tmp_path: Path):
    writer = load_record()
    writer.pop("candidate_works", None)
    writer_path = tmp_path / "writer-missing-candidate.yaml"
    writer_path.write_text(yaml.safe_dump(writer, sort_keys=False), encoding="utf-8")

    result = run_tool(
        "literary-packet",
        "--writer",
        writer_path,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        "chris-public-profile-readiness",
        "--route",
        "submittable-discover-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Desk status: BLOCKED" in result.stdout
    assert "Candidate work metadata is missing for 'chris-public-profile-readiness'." in result.stdout


def test_venue_specific_literary_packet_marks_ai_policy_unresolved_without_source(tmp_path: Path):
    opportunity = load_record(OPPORTUNITY)
    opportunity["opportunity"]["submission_routes"] = [
        {
            "id": "unsourced-review",
            "route_type": "venue",
            "platform": "custom_journal_form",
            "venue": "Unsourced Review",
            "guidelines_url": "https://example.invalid/guidelines",
            "deadline": "2026-12-31",
            "word_limits": "up to 5000 words",
            "fee": "unknown",
            "pay": "unknown",
            "ai_policy_disclosure_status": "not_sourced",
            "ai_policy_source_ids": [],
        }
    ]
    opportunity_path = tmp_path / "opportunity-unsourced-ai.yaml"
    opportunity_path.write_text(yaml.safe_dump(opportunity, sort_keys=False), encoding="utf-8")

    result = run_tool(
        "literary-packet",
        "--writer",
        CHRIS,
        "--opportunity",
        opportunity_path,
        "--candidate",
        "chris-public-profile-readiness",
        "--route",
        "unsourced-review",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "AI policy/disclosure: unresolved." in result.stdout
    assert "Venue AI policy/disclosure source is unresolved." in result.stdout


def test_venue_specific_literary_packet_blocks_unresolved_ai_policy_even_with_source(
    tmp_path: Path,
):
    writer = load_record(CHRIS)
    writer["candidate_works"][0].update(
        {
            "genre": "fiction",
            "form": "short story",
            "length": "3000 words",
            "rights_status": "available for first publication",
            "content_ref": "metadata://fixture/candidate-work-no-text",
        }
    )
    writer_path = tmp_path / "writer-complete-candidate.yaml"
    writer_path.write_text(yaml.safe_dump(writer, sort_keys=False), encoding="utf-8")

    opportunity = load_record(OPPORTUNITY)
    opportunity["opportunity"]["submission_routes"] = [
        {
            "id": "sourced-but-unresolved-review",
            "route_type": "venue",
            "platform": "custom_journal_form",
            "venue": "Sourced But Unresolved Review",
            "guidelines_url": "https://example.invalid/guidelines",
            "deadline": "2026-12-31",
            "word_limits": "up to 5000 words",
            "fee": "$0",
            "pay": "unknown",
            "ai_policy_disclosure_status": "venue_specific_unresolved",
            "ai_policy_source_ids": ["web-yale-ai-policy"],
        }
    ]
    opportunity_path = tmp_path / "opportunity-sourced-unresolved-ai.yaml"
    opportunity_path.write_text(yaml.safe_dump(opportunity, sort_keys=False), encoding="utf-8")

    result = run_tool(
        "literary-packet",
        "--writer",
        writer_path,
        "--opportunity",
        opportunity_path,
        "--candidate",
        "chris-public-profile-readiness",
        "--route",
        "sourced-but-unresolved-review",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Desk status: BLOCKED" in result.stdout
    assert "AI policy/disclosure: unresolved." in result.stdout
    assert "Venue AI policy/disclosure status is unresolved." in result.stdout


def test_literary_no_send_packet_never_claims_outward_action_happened():
    packet = rs.render_literary_packet(
        load_record(CHRIS),
        load_record(OPPORTUNITY),
        candidate_id="chris-public-profile-readiness",
        route_selector="submittable-discover-route",
    ).lower()

    forbidden_phrases = [
        "has been submitted",
        "was submitted",
        "outreach sent",
        "has been uploaded",
        "was uploaded",
        "has been published",
        "was published",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in packet
    assert "no submission, outreach, upload, publication, contact, or form action is performed" in packet


@pytest.mark.parametrize(
    ("record", "mode", "needle"),
    [
        (CHRIS, "private_dossier", "Speech Score lineage"),
        (CHRIS, "public_page_draft", "Public writing record"),
        (CHRIS, "writer_submission", "Submission: not_requested"),
        (CHRIS, "collaboration_packet", "Object Lessons lineage"),
        (ET4L, "private_dossier", "Exhibition logic"),
        (ET4L, "project_page", "Public project proof"),
        (ET4L, "collaboration_packet", "Artist organ chamber"),
    ],
)
def test_packet_cli_smoke_for_key_modes(record: Path, mode: str, needle: str):
    result = run_tool("packet", record, "--mode", mode)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("# ")
    assert "## Subject Summary" in result.stdout
    assert "## Source Appendix Summary" in result.stdout
    assert "This packet is review-only." in result.stdout
    assert needle in result.stdout


@pytest.mark.parametrize(
    ("record", "mode"),
    [
        (CHRIS, "private_dossier"),
        (CHRIS, "public_page_draft"),
        (CHRIS, "writer_submission"),
        (CHRIS, "collaboration_packet"),
        (ET4L, "private_dossier"),
        (ET4L, "project_page"),
        (ET4L, "collaboration_packet"),
    ],
)
def test_packet_renderers_only_use_declared_output_claims(record: Path, mode: str):
    doc = load_record(record)
    text = rs.render_record(doc, mode)
    declared = rs._output_claim_ids(doc, mode)

    for claim in doc["claims"]:
        if claim["id"] not in declared:
            assert claim["label"] not in text
            assert claim["summary"] not in text

    for source in doc["sources"]:
        source_claims = {str(claim_id) for claim_id in source["claim_ids"]}
        if not declared.intersection(source_claims):
            assert source["id"] not in text


def test_public_export_stays_locked_without_subject_approval():
    doc = load_record()

    with pytest.raises(ValueError, match="export is locked"):
        rs.render_record(doc, "public_page_draft", export=True)


def test_public_page_export_uses_copied_approval_fixture_without_private_leak(tmp_path: Path):
    doc = load_record()
    for approval in doc["approvals"]:
        if approval["approval_type"] == "public_export":
            approval["status"] = "approved"
            approval["note"] = "Copied fixture approval for export-path coverage only."

    doc["claims"].extend(
        [
            {
                "id": "approved-local-context",
                "label": "Approved local context",
                "summary": "Subject approved this private-source context for public copy.",
                "visibility": "private",
                "source_ids": ["local-relationship-pipeline"],
                "public_ok": True,
            },
            {
                "id": "unapproved-local-context",
                "label": "Unapproved local context",
                "summary": "This local-only context must stay out of public export.",
                "visibility": "private",
                "source_ids": ["local-relationship-pipeline"],
                "public_ok": True,
            },
        ]
    )
    doc["approvals"].append(
        {
            "id": "approved-local-context-public-claim",
            "approval_type": "public_claim",
            "status": "approved",
            "claim_ids": ["approved-local-context"],
            "note": "Copied fixture claim approval; no real public approval is asserted.",
        }
    )
    for source in doc["sources"]:
        if source["id"] == "local-relationship-pipeline":
            source["claim_ids"].extend(
                ["approved-local-context", "unapproved-local-context"]
            )
    for output in doc["outputs"]:
        if output["mode"] == "public_page_draft":
            output["claim_ids"].extend(
                ["approved-local-context", "unapproved-local-context"]
            )

    path = tmp_path / "approved-public-export-copy.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_tool("packet", path, "--mode", "public_page_draft", "--export")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Approved local context" in result.stdout
    assert "Unapproved local context" not in result.stdout
    assert "source reference withheld" in result.stdout
    assert "local-relationship-pipeline" not in result.stdout
    assert "/Users/4jp" not in result.stdout


def test_export_requires_matching_mode_approval():
    et4l = load_record(ET4L)
    et4l["approvals"].append(
        {
            "id": "generic-public-export",
            "approval_type": "public_export",
            "status": "approved",
            "claim_ids": ["et4l-public-proof"],
            "note": "Generic public export should not unlock project-page export.",
        }
    )

    with pytest.raises(ValueError, match="matching explicit approval"):
        rs.render_record(et4l, "project_page", export=True)

    for approval in et4l["approvals"]:
        if approval["approval_type"] == "project_page":
            approval["status"] = "approved"

    packet = rs.render_record(et4l, "project_page", export=True)

    assert packet.startswith("# Project Page Draft")
