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
CHRIS = ROOT / "organs" / "representation" / "records" / "christopher-notarnicola.yaml"
ET4L = ROOT / "organs" / "representation" / "records" / "et4l.yaml"
GENERIC = ROOT / "organs" / "representation" / "records" / "generic-authority-template.yaml"
OPPORTUNITY = ROOT / "organs" / "representation" / "opportunities" / "literary-submission-landscape.yaml"
APPROVAL_TEMPLATE = (
    ROOT / "organs" / "representation" / "approvals" / "chris-yale-review-nonfiction-dry-run.template.yaml"
)
REAL_SEND_TEMPLATE = (
    ROOT / "organs" / "representation" / "approvals" / "chris-yale-review-nonfiction-real-send.template.yaml"
)
READY_CANDIDATE = "chris-metadata-only-nonfiction-candidate"
YALE_ROUTE = "yale-review-nonfiction-route"

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


def mark_approval_dry_run(approval: dict) -> None:
    approval.update(
        {
            "approval_scope": "dry_run",
            "dry_run_only": True,
            "no_outward_action": True,
            "permitted_actions": ["render_review_files", "write_review_files", "dry_run_export"],
        }
    )


def approved_publication_approval_record(tmp_path: Path) -> Path:
    record = load_record(APPROVAL_TEMPLATE)
    record["id"] = "fixture-approved-chris-yale-dry-run"
    for approval in record["approvals"]:
        if approval["approval_type"] != "real_send":
            approval["status"] = "approved"
            approval["note"] = "Copied fixture approval for dry-run test coverage only."
    path = tmp_path / "approved-publication-approval-record.yaml"
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    return path


def approved_real_send_approval_record(tmp_path: Path, *, delivery_adapter: str = "direct_email") -> Path:
    record = load_record(REAL_SEND_TEMPLATE)
    record["id"] = f"fixture-approved-chris-yale-real-send-{delivery_adapter}"
    for approval in record["approvals"]:
        if approval["approval_type"] != "real_send":
            approval["status"] = "approved"
            approval["note"] = "Copied fixture approval for real-send test coverage."
            continue
        approval["status"] = "approved"
        approval["real_send_approval"] = True
        approval["operator_approved_at"] = "2026-07-08T00:00:00Z"
        approval["delivery_adapter"] = delivery_adapter
        approval["sender_address_env"] = "TEST_SUBMISSION_SENDER_EMAIL"
        approval["recipient_address_env"] = "TEST_SUBMISSION_RECIPIENT_EMAIL"
        approval["message_subject_env"] = "TEST_SUBMISSION_SUBJECT"
        approval["message_body_env"] = "TEST_SUBMISSION_BODY"
        approval["payload_path_env"] = "TEST_SUBMISSION_PAYLOAD_PATH"
        approval["permitted_actions"] = ["send_submission", "write_send_receipt"]
        if delivery_adapter == "local_outbox":
            approval["permitted_actions"].append("stage_outbox_message")
        approval["note"] = "Copied fixture approval for real-send test coverage."
    path = tmp_path / f"approved-real-send-{delivery_adapter}.yaml"
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    return path


def test_representation_fleet_passes():
    result = run_validator("--fleet", "--quiet")
    assert result.returncode == 0, result.stdout + result.stderr


def test_fleet_includes_non_writer_project_proof():
    et4l = load_record(ET4L)

    assert et4l["subject"]["type"] == "project"
    assert "writer_submission" not in et4l["subject"]["representation_modes"]
    assert {"canon_dossier", "public_presence_draft", "authority_scorecard"}.issubset(
        set(et4l["subject"]["representation_modes"])
    )
    assert any(output["mode"] == "project_page" for output in et4l["outputs"])
    assert et4l["artifacts"]["next_reviewable_output"]


def test_validator_requires_complete_authority_program_axes_and_outputs(tmp_path: Path):
    doc = load_record(ET4L)
    doc["authority_program"]["axes"].pop("hybrid_presence")
    doc["authority_program"]["axes"]["canonical_institution"]["public_copy"] = "TODO"
    doc["authority_program"]["axes"]["mass_readership"]["claim_ids"] = ["missing-claim"]
    doc["outputs"] = [output for output in doc["outputs"] if output["mode"] != "authority_scorecard"]
    path = tmp_path / "broken-authority.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_validator(path)

    assert result.returncode == 1
    assert "authority_program outputs must declare modes: authority_scorecard" in result.stdout
    assert "authority_program.axes missing required axis/axes: hybrid_presence" in result.stdout
    assert "public_copy contains placeholder text" in result.stdout
    assert "claim_ids references unknown claim_ids: missing-claim" in result.stdout


def test_validator_rejects_unsupported_authority_axes(tmp_path: Path):
    doc = load_record(ET4L)
    doc["authority_program"]["axes"]["cultural_mythology"] = copy.deepcopy(
        doc["authority_program"]["axes"]["canonical_institution"]
    )
    path = tmp_path / "extra-authority-axis.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_validator(path)

    assert result.returncode == 1
    assert "authority_program.axes has unsupported axis/axes: cultural_mythology" in result.stdout


def test_validator_rejects_private_unapproved_public_axis_claims(tmp_path: Path):
    doc = load_record(ET4L)
    doc["authority_program"]["axes"]["canonical_institution"]["public_claim_ids"].append("et4l-artist-chamber")
    path = tmp_path / "private-public-axis-claim.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_validator(path)

    assert result.returncode == 1
    assert (
        "public_claim_ids must reference public-source or claim-approved private claims: et4l-artist-chamber"
    ) in result.stdout


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
        "Christopher Notarnicola was also tied to Speech Score."
    )

    rows = rs.index_mentions(text, profile)
    matches = [row["match"] for row in rows]

    assert "Christian" not in matches
    assert "Christopher Nolan" not in " ".join(matches)
    assert "Chris" in matches
    assert "Christopher Notarnicola" in matches


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


@pytest.mark.parametrize("record", [ET4L, CHRIS, GENERIC])
@pytest.mark.parametrize(
    ("mode", "title"),
    [
        ("canon_dossier", "# Canon Dossier"),
        ("public_presence_draft", "# Public Presence Draft"),
        ("authority_scorecard", "# Authority Scorecard"),
    ],
)
def test_authority_modes_render_for_first_proofs_and_generic_template(record: Path, mode: str, title: str):
    doc = load_record(record)
    text = rs.render_record(doc, mode)

    assert text.startswith(title)
    assert "## Subject Summary" in text
    assert "## Source Appendix Summary" in text
    assert "This packet is review-only." in text


def test_public_presence_draft_excludes_private_unapproved_claims_and_local_refs():
    public_presence = rs.render_record(load_record(CHRIS), "public_presence_draft")

    assert "Public writing record" in public_presence
    assert "Editorial role" in public_presence
    assert "Speech Score lineage" not in public_presence
    assert "Object Lessons lineage" not in public_presence
    assert "local-relationship-pipeline" not in public_presence
    assert "/Users/4jp" not in public_presence


def test_authority_scorecard_reports_staged_blockers_not_achieved_status():
    scorecard = rs.render_record(load_record(CHRIS), "authority_scorecard")

    assert "## Authority Scorecard" in scorecard
    assert "Civilizational gravitas is the program goal, not an achieved public status claim." in scorecard
    assert "canonical_institution: STAGED" in scorecard
    assert "mass_readership: STAGED" in scorecard
    assert "hybrid_presence: STAGED" in scorecard
    assert "public export approval is not_requested" in scorecard


def test_authority_packet_includes_all_artifacts_and_no_outward_action_gate():
    result = run_tool("authority-packet", "--record", CHRIS)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("# Authority Packet: Christopher Notarnicola")
    assert "## Canon Dossier Artifact" in result.stdout
    assert "## Public Presence Draft Artifact" in result.stdout
    assert "## Authority Scorecard Artifact" in result.stdout
    assert "## Packet Blockers" in result.stdout
    assert "## Packet Source Appendix" in result.stdout
    assert "## Packet Approvals Required" in result.stdout
    assert "## No-Outward-Action Gate" in result.stdout
    assert "does not submit, publish, upload, contact, mine private material, or act outward" in result.stdout


def test_chris_public_page_draft_uses_public_profile_evidence_only():
    result = run_tool("packet", CHRIS, "--mode", "public_page_draft")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "## Public Page Draft Copy" in result.stdout
    assert (
        "Christopher Notarnicola can be presented from public evidence and claim-approved context only" in result.stdout
    )
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


def test_candidate_intake_cli_outputs_metadata_only_source_ref():
    result = run_tool(
        "candidate-intake",
        "--id",
        "candidate-with-source-ref",
        "--title",
        "Sourced candidate manuscript",
        "--genre",
        "fiction",
        "--form",
        "short story",
        "--length",
        "4200 words",
        "--rights-status",
        "available for first publication",
        "--content-ref",
        "source://private-manuscripts/chris/candidate-001",
        "--source-id",
        "subject-confirmed-candidate-ref",
        "--claim-id",
        "chris-public-writing",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    doc = yaml.safe_load(result.stdout)
    candidate = doc["candidate_works"][0]
    assert candidate["content_ref"] == "source://private-manuscripts/chris/candidate-001"
    assert candidate["source_ids"] == ["subject-confirmed-candidate-ref"]
    assert "manuscript_text" not in result.stdout
    assert "raw_text" not in result.stdout
    assert "private_message" not in result.stdout


def test_candidate_intake_rejects_contact_data_in_source_ref():
    result = run_tool(
        "candidate-intake",
        "--id",
        "candidate-with-contact-ref",
        "--title",
        "Bad candidate ref",
        "--content-ref",
        "writer@example.com",
        "--source-id",
        "subject-confirmed-candidate-ref",
        "--claim-id",
        "chris-public-writing",
    )

    assert result.returncode == 1
    assert "content-ref must not contain contact data" in result.stderr


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
    assert result.stdout.startswith("# Literary Desk Packet: Christopher Notarnicola")
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


def test_sourced_venue_route_examples_have_guideline_source_refs():
    opportunity = load_record(OPPORTUNITY)
    routes = {route["id"]: route for route in opportunity["opportunity"]["submission_routes"]}

    yale = routes["yale-review-nonfiction-route"]
    masters = routes["masters-review-summer-short-story-route"]

    assert yale["guidelines_source_ids"] == ["web-yale-submissions"]
    assert "web-yale-submissions" in yale["ai_policy_source_ids"]
    assert masters["guidelines_source_ids"] == ["web-masters-review-submissions"]
    assert masters["ai_policy_disclosure_status"] == "ai_generated_or_assisted_submissions_disqualified"


def test_chris_remains_blocked_for_sourced_venue_without_candidate_source_ref():
    result = run_tool(
        "literary-packet",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        "chris-public-profile-readiness",
        "--route",
        "yale-review-nonfiction-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Desk status: BLOCKED" in result.stdout
    assert "Candidate Content/source ref" in result.stdout
    assert "AI policy/disclosure: human_authorship_required_process_ai_allowed_with_transparency." in result.stdout
    assert "Venue AI policy/disclosure source is unresolved." not in result.stdout


def test_validator_rejects_ready_candidate_without_required_publication_metadata(tmp_path: Path):
    doc = load_record(CHRIS)
    candidate = next(candidate for candidate in doc["candidate_works"] if candidate["id"] == READY_CANDIDATE)
    candidate["content_ref"] = ""
    candidate["source_ids"] = []
    candidate["claim_ids"] = []
    path = tmp_path / "ready-candidate-missing-metadata.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_validator(path)

    assert result.returncode == 1
    assert "status READY_FOR_REVIEW requires metadata" in result.stdout
    assert "Content/source ref" in result.stdout
    assert "Source refs" in result.stdout
    assert "Claim refs" in result.stdout


def test_publication_readiness_blocks_placeholder_candidate():
    result = run_tool(
        "publication-readiness",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        "chris-public-profile-readiness",
        "--route",
        "yale-review-nonfiction-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("# Publication Readiness Packet: Christopher Notarnicola")
    assert "Publication readiness: BLOCKED" in result.stdout
    assert "Candidate status: BLOCKED" in result.stdout
    assert "Candidate Content/source ref is missing." in result.stdout
    assert "Route status: READY_FOR_REVIEW" in result.stdout


def test_publication_readiness_reports_ready_metadata_candidate_and_sourced_route():
    result = run_tool(
        "publication-readiness",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        "yale-review-nonfiction-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Publication readiness: BLOCKED" in result.stdout
    assert "Candidate status: READY_FOR_REVIEW" in result.stdout
    assert "Route status: READY_FOR_REVIEW" in result.stdout
    assert "Route guideline source is public, recorded, and matched to the guidelines URL." in result.stdout
    assert "Route AI policy/disclosure status is sourced and resolved." in result.stdout
    assert "Writer submission approval is not_requested." in result.stdout
    assert "Opportunity route submission approval is not_requested." in result.stdout


def test_publication_readiness_blocks_unsourced_route_guidelines(tmp_path: Path):
    opportunity = load_record(OPPORTUNITY)
    for route in opportunity["opportunity"]["submission_routes"]:
        if route["id"] == "yale-review-nonfiction-route":
            route["guidelines_source_ids"] = []
    opportunity_path = tmp_path / "opportunity-missing-route-guidelines.yaml"
    opportunity_path.write_text(yaml.safe_dump(opportunity, sort_keys=False), encoding="utf-8")

    result = run_tool(
        "publication-readiness",
        "--writer",
        CHRIS,
        "--opportunity",
        opportunity_path,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        "yale-review-nonfiction-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Publication readiness: BLOCKED" in result.stdout
    assert "Route status: BLOCKED" in result.stdout
    assert "Route guideline source is missing for the selected route." in result.stdout


def test_publication_readiness_blocks_unsourced_ai_policy(tmp_path: Path):
    opportunity = load_record(OPPORTUNITY)
    for route in opportunity["opportunity"]["submission_routes"]:
        if route["id"] == "yale-review-nonfiction-route":
            route["ai_policy_source_ids"] = []
    opportunity_path = tmp_path / "opportunity-missing-ai-source.yaml"
    opportunity_path.write_text(yaml.safe_dump(opportunity, sort_keys=False), encoding="utf-8")

    result = run_tool(
        "publication-readiness",
        "--writer",
        CHRIS,
        "--opportunity",
        opportunity_path,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        "yale-review-nonfiction-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Publication readiness: BLOCKED" in result.stdout
    assert "Route status: BLOCKED" in result.stdout
    assert "Route AI policy/disclosure source is unresolved." in result.stdout


def test_publication_readiness_blocks_unresolved_ai_policy(tmp_path: Path):
    opportunity = load_record(OPPORTUNITY)
    for route in opportunity["opportunity"]["submission_routes"]:
        if route["id"] == "yale-review-nonfiction-route":
            route["ai_policy_disclosure_status"] = "venue_specific_unresolved"
    opportunity_path = tmp_path / "opportunity-unresolved-ai-policy.yaml"
    opportunity_path.write_text(yaml.safe_dump(opportunity, sort_keys=False), encoding="utf-8")

    result = run_tool(
        "publication-readiness",
        "--writer",
        CHRIS,
        "--opportunity",
        opportunity_path,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        "yale-review-nonfiction-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Publication readiness: BLOCKED" in result.stdout
    assert "Route status: BLOCKED" in result.stdout
    assert "Route AI policy/disclosure status is unresolved." in result.stdout


def test_publication_readiness_export_requires_approvals():
    result = run_tool(
        "publication-readiness",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        "yale-review-nonfiction-route",
        "--export",
    )

    assert result.returncode == 1
    assert "publication readiness export is locked" in result.stderr


def test_publication_readiness_allows_approved_dry_run_export(tmp_path: Path):
    approval_record = approved_publication_approval_record(tmp_path)

    result = run_tool(
        "publication-readiness",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        YALE_ROUTE,
        "--approval-record",
        approval_record,
        "--export",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Export mode: approved dry run only; no publication or delivery occurs." in result.stdout
    assert "Publication readiness: READY_FOR_REVIEW" in result.stdout
    assert "Dry-run export: APPROVED_DRY_RUN" in result.stdout
    assert "Real submission: LOCKED; execution uses publication-send." in result.stdout


def test_approval_templates_validate():
    result = run_validator(APPROVAL_TEMPLATE)
    real_send_result = run_validator(REAL_SEND_TEMPLATE)

    assert result.returncode == 0, result.stdout + result.stderr
    assert real_send_result.returncode == 0, real_send_result.stdout + real_send_result.stderr


def test_real_send_approval_requires_explicit_send_fields(tmp_path: Path):
    record = load_record(REAL_SEND_TEMPLATE)
    for approval in record["approvals"]:
        if approval["approval_type"] == "real_send":
            approval["status"] = "approved"
            approval["real_send_approval"] = True
            approval["permitted_actions"] = ["send_submission"]
            approval.pop("payload_ref")
            approval.pop("operator_approved_at", None)
    path = tmp_path / "bad-real-send-approval.yaml"
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")

    result = run_validator(path)

    assert result.returncode == 1
    assert "approved real-send record missing" in result.stdout
    assert "payload_ref" in result.stdout
    assert "operator_approved_at" in result.stdout


def test_real_send_approval_validates_when_explicitly_approved(tmp_path: Path):
    approval_record = approved_real_send_approval_record(tmp_path)

    result = run_validator(approval_record)

    assert result.returncode == 0, result.stdout + result.stderr


def test_publication_send_blocks_without_real_send_approval(tmp_path: Path):
    approval_record = approved_publication_approval_record(tmp_path)

    result = run_tool(
        "publication-send",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        YALE_ROUTE,
        "--approval-record",
        approval_record,
    )

    assert result.returncode == 1
    assert "Dry-run approvals: APPROVED_DRY_RUN" in result.stdout
    assert "Real send approval: LOCKED" in result.stdout
    assert "Real send approval is missing; publication-send requires an approved real_send record." in result.stdout


def test_publication_send_direct_email_blocks_missing_runtime_config(tmp_path: Path):
    approval_record = approved_real_send_approval_record(tmp_path, delivery_adapter="direct_email")

    result = run_tool(
        "publication-send",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        YALE_ROUTE,
        "--approval-record",
        approval_record,
        "--execute",
    )

    assert result.returncode == 1
    assert "Real send approval: APPROVED_REAL_SEND" in result.stdout
    assert "Send status: BLOCKED" in result.stdout
    assert "REAL_SEND_BLOCKED: direct_email delivery adapter requires --smtp-host." in result.stdout
    assert "REAL_SEND_BLOCKED: recipient address env var TEST_SUBMISSION_RECIPIENT_EMAIL is not set." in result.stdout


def test_publication_send_direct_email_uses_smtp_adapter_with_runtime_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    approval_doc = load_record(approved_real_send_approval_record(tmp_path, delivery_adapter="direct_email"))
    payload_path = tmp_path / "payload.txt"
    payload_path.write_text("fixture payload, no private manuscript text", encoding="utf-8")
    monkeypatch.setenv("TEST_SUBMISSION_SENDER_EMAIL", "sender@example.test")
    monkeypatch.setenv("TEST_SUBMISSION_RECIPIENT_EMAIL", "recipient@example.test")
    monkeypatch.setenv("TEST_SUBMISSION_SUBJECT", "Fixture submission subject")
    monkeypatch.setenv("TEST_SUBMISSION_BODY", "Fixture submission body.")
    monkeypatch.setenv("TEST_SUBMISSION_PAYLOAD_PATH", str(payload_path))
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False
            self.logged_in = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            self.started_tls = True

        def login(self, username: str, password: str):
            self.logged_in = bool(username and password)

        def send_message(self, message):
            sent_messages.append((self.host, self.port, self.timeout, message))

    monkeypatch.setattr(rs.smtplib, "SMTP", FakeSMTP)

    output, ok = rs.render_publication_send_receipt(
        load_record(CHRIS),
        load_record(OPPORTUNITY),
        candidate_id=READY_CANDIDATE,
        route_selector=YALE_ROUTE,
        approval_doc=approval_doc,
        execute=True,
        send_config={
            "smtp_host": "smtp.example.test",
            "smtp_port": 2525,
            "smtp_timeout": 3.0,
        },
    )

    assert ok is True
    assert "Send status: SENT_DIRECT_EMAIL" in output
    assert "Direct email SMTP delivery completed." in output
    assert "sender@example.test" not in output
    assert "recipient@example.test" not in output
    assert str(payload_path) not in output
    assert len(sent_messages) == 1
    host, port, timeout, message = sent_messages[0]
    assert host == "smtp.example.test"
    assert port == 2525
    assert timeout == 3.0
    assert message["From"] == "sender@example.test"
    assert message["To"] == "recipient@example.test"
    assert message["Subject"] == "Fixture submission subject"


def test_publication_send_writes_local_outbox_with_real_send_approval(tmp_path: Path):
    approval_record = approved_real_send_approval_record(tmp_path, delivery_adapter="local_outbox")
    outbox_dir = tmp_path / "outbox"

    result = run_tool(
        "publication-send",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        YALE_ROUTE,
        "--approval-record",
        approval_record,
        "--execute",
        "--outbox-dir",
        outbox_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Real send approval: APPROVED_REAL_SEND" in result.stdout
    assert "Send status: SENT_TO_LOCAL_OUTBOX" in result.stdout
    outbox_files = list(outbox_dir.iterdir())
    assert len(outbox_files) == 1
    outbox_text = outbox_files[0].read_text(encoding="utf-8")
    assert "Status: SENT_TO_LOCAL_OUTBOX" in outbox_text
    assert "External email, upload, form submission, publication, and editor contact were not performed" in outbox_text


def test_publication_stack_contains_all_required_files(tmp_path: Path):
    out_dir = tmp_path / "publication-stack"

    result = run_tool(
        "publication-stack",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        YALE_ROUTE,
        "--out-dir",
        out_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert {path.name for path in out_dir.iterdir()} == rs.PUBLICATION_STACK_FILENAMES
    readme = (out_dir / "README.md").read_text(encoding="utf-8")
    assert "Candidate metadata: READY_FOR_REVIEW." in readme
    assert "Route metadata: READY_FOR_REVIEW." in readme
    assert "Dry-run approval: LOCKED." in readme
    assert "Real send: LOCKED." in readme


def test_publication_stack_approval_fixture_unlocks_dry_run_only(tmp_path: Path):
    out_dir = tmp_path / "approved-publication-stack"
    approval_record = approved_publication_approval_record(tmp_path)

    result = run_tool(
        "publication-stack",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        YALE_ROUTE,
        "--out-dir",
        out_dir,
        "--approval-record",
        approval_record,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    text = (out_dir / "README.md").read_text(encoding="utf-8")
    assert "Dry-run approval: APPROVED_DRY_RUN." in text
    assert "Real send: LOCKED." in text
    assert "No publication, submission, upload, contact, form action, or public export has happened." in text
    fit_report = (out_dir / "fit-report.md").read_text(encoding="utf-8")
    assert "Dry-run export: APPROVED_DRY_RUN" in fit_report
    assert "Real submission: LOCKED; execution uses publication-send." in fit_report


def test_publication_stack_artifacts_are_private_ref_safe(tmp_path: Path):
    out_dir = tmp_path / "safe-publication-stack"
    result = run_tool(
        "publication-stack",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        YALE_ROUTE,
        "--out-dir",
        out_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    forbidden = [
        "/Users/",
        "source://private-manuscripts",
        "local-relationship-pipeline",
        "github.com/organvm/object-lessons",
        "github.com/organvm/speech-score-engine",
        "github.com/organvm/sign-signal",
        "contact_data",
        "has been submitted",
        "was submitted",
        "has been published",
        "was published",
        "accepted for publication",
    ]
    for path in out_dir.iterdir():
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for fragment in forbidden:
            assert fragment.lower() not in lowered, path
        assert rs.EMAIL_RE.search(text) is None


def test_publication_readiness_packet_is_chris_facing_and_private_ref_safe():
    result = run_tool(
        "publication-readiness",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        READY_CANDIDATE,
        "--route",
        "yale-review-nonfiction-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "## What This Is" in result.stdout
    assert "## What Works Now" in result.stdout
    assert "## Still Gated" in result.stdout
    assert "## Privacy, Voice, And Control" in result.stdout
    assert "source://private-manuscripts" not in result.stdout
    assert "local-relationship-pipeline" not in result.stdout
    assert "/Users/4jp" not in result.stdout
    assert "has been submitted" not in result.stdout.lower()
    assert "accepted for publication" not in result.stdout.lower()


def test_validator_requires_public_guideline_sources_for_venue_routes(tmp_path: Path):
    opportunity = load_record(OPPORTUNITY)
    for route in opportunity["opportunity"]["submission_routes"]:
        if route["id"] == "yale-review-nonfiction-route":
            route["guidelines_source_ids"] = []
    opportunity_path = tmp_path / "opportunity-unsourced-venue-guidelines.yaml"
    opportunity_path.write_text(yaml.safe_dump(opportunity, sort_keys=False), encoding="utf-8")

    result = run_validator(opportunity_path)

    assert result.returncode == 1
    assert "guidelines_source_ids must list public web sources for venue-specific routes" in result.stdout


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


def test_chris_handoff_audit_proves_features_and_reports_gates():
    result = run_tool(
        "handoff-audit",
        "--writer",
        CHRIS,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        "chris-public-profile-readiness",
        "--route",
        "yale-review-nonfiction-route",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("# Representation Handoff Audit: Christopher Notarnicola")
    assert "Audit status: PROVEN" in result.stdout
    assert "Broken features: 0" in result.stdout
    assert "SCAN: Opportunity routes" in result.stdout
    assert "MATCH: Writer proof" in result.stdout
    assert "BUILD: Dossiers" in result.stdout
    assert "APPLY: Outbound submission" in result.stdout
    assert "FOLLOW_UP: Blockers and approvals" in result.stdout
    assert "PROVEN: Authority packet" in result.stdout
    assert "PROVEN: Literary desk packet" in result.stdout
    assert "GATE: Literary desk readiness" in result.stdout
    assert "PROVEN: public_page_draft public privacy" in result.stdout
    assert "PROVEN: Literary export lock" in result.stdout
    assert "BROKEN:" not in result.stdout
    assert "N/A" not in result.stdout
    assert "/Users/4jp" not in result.stdout


def test_handoff_audit_fails_closed_for_invalid_writer_record(tmp_path: Path):
    writer = load_record(CHRIS)
    writer["authority_program"]["axes"].pop("hybrid_presence")
    writer_path = tmp_path / "invalid-writer.yaml"
    writer_path.write_text(yaml.safe_dump(writer, sort_keys=False), encoding="utf-8")

    result = run_tool(
        "handoff-audit",
        "--writer",
        writer_path,
        "--opportunity",
        OPPORTUNITY,
        "--candidate",
        "chris-public-profile-readiness",
        "--route",
        "submittable-discover-route",
    )

    assert result.returncode == 1
    assert "Audit status: BROKEN" in result.stdout
    assert "BROKEN: Writer record validation" in result.stdout


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
            mark_approval_dry_run(approval)
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
            source["claim_ids"].extend(["approved-local-context", "unapproved-local-context"])
    for output in doc["outputs"]:
        if output["mode"] == "public_page_draft":
            output["claim_ids"].extend(["approved-local-context", "unapproved-local-context"])

    path = tmp_path / "approved-public-export-copy.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_tool("packet", path, "--mode", "public_page_draft", "--export")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Export mode: approved dry run only; no publication or delivery occurs." in result.stdout
    assert "Approved local context" in result.stdout
    assert "Unapproved local context" not in result.stdout
    assert "source reference withheld" in result.stdout
    assert "local-relationship-pipeline" not in result.stdout
    assert "/Users/4jp" not in result.stdout


def test_public_presence_export_uses_copied_approval_fixture_as_dry_run(tmp_path: Path):
    doc = load_record(CHRIS)
    for approval in doc["approvals"]:
        if approval["approval_type"] == "public_export":
            approval["status"] = "approved"
            mark_approval_dry_run(approval)
            approval["note"] = "Copied fixture approval for authority export-path coverage only."

    path = tmp_path / "approved-public-presence-export.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    result = run_tool("packet", path, "--mode", "public_presence_draft", "--export")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Export mode: approved dry run only; no publication or delivery occurs." in result.stdout
    assert "Public writing record" in result.stdout
    assert "Object Lessons lineage" not in result.stdout
    assert "/Users/4jp" not in result.stdout


def test_export_requires_matching_mode_approval():
    et4l = load_record(ET4L)
    et4l["approvals"].append(
        {
            "id": "generic-public-export",
            "approval_type": "public_export",
            "status": "approved",
            "approval_scope": "dry_run",
            "dry_run_only": True,
            "no_outward_action": True,
            "permitted_actions": ["render_review_files"],
            "claim_ids": ["et4l-public-proof"],
            "note": "Generic public export should not unlock project-page export.",
        }
    )

    with pytest.raises(ValueError, match="matching explicit approval"):
        rs.render_record(et4l, "project_page", export=True)

    for approval in et4l["approvals"]:
        if approval["approval_type"] == "project_page":
            approval["status"] = "approved"
            mark_approval_dry_run(approval)

    packet = rs.render_record(et4l, "project_page", export=True)

    assert packet.startswith("# Project Page Draft")
