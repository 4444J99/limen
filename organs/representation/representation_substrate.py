#!/usr/bin/env python3
"""Representation Substrate source, privacy, mention, and mode gates."""

from __future__ import annotations

import argparse
import mimetypes
import os
import re
import smtplib
import sys
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(2)


SOURCE_TYPES = {
    "local_repo",
    "remote_repo",
    "web",
    "messages",
    "user_assertion",
    "subject_confirmed",
    "writer_confirmed",
}
SUBJECT_TYPES = {"person", "creator", "collaborator", "project", "venue", "opportunity"}
PRIVACY_LEVELS = {"public", "private", "sensitive"}
VISIBILITY_LEVELS = {"public", "private", "sensitive"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
APPROVAL_TYPES = {
    "public_export",
    "public_claim",
    "co_branded_page",
    "submission",
    "outreach",
    "project_page",
    "real_send",
}
APPROVAL_STATUSES = {"not_requested", "pending", "approved", "denied", "locked"}
OUTPUT_MODES = {
    "canon_dossier",
    "public_presence_draft",
    "authority_scorecard",
    "private_dossier",
    "creator_presence_preview",
    "public_page_draft",
    "writer_submission",
    "market_fit",
    "collaboration_packet",
    "project_page",
    "co_branded_page",
}
PACKET_MODES = {
    "canon_dossier",
    "public_presence_draft",
    "authority_scorecard",
    "private_dossier",
    "public_page_draft",
    "writer_submission",
    "market_fit",
    "collaboration_packet",
    "project_page",
}
PUBLIC_RENDER_MODES = {
    "public_presence_draft",
    "creator_presence_preview",
    "public_page_draft",
    "project_page",
    "co_branded_page",
}
PRIVATE_RENDER_MODES = {
    "canon_dossier",
    "authority_scorecard",
    "private_dossier",
    "writer_submission",
    "market_fit",
    "collaboration_packet",
}
AUTHORITY_GOAL = "civilizational_gravitas"
AUTHORITY_AXES = ("canonical_institution", "mass_readership", "hybrid_presence")
AUTHORITY_MODES = {"canon_dossier", "public_presence_draft", "authority_scorecard"}
AUTHORITY_ARCHETYPE_FUNCTIONS = ("canonical_institution", "mass_readership")
PUBLIC_APPROVAL_TYPES = {"public_export", "public_claim", "co_branded_page", "project_page"}
APPROVAL_RECORD_KIND = "representation_approval_record"
DRY_RUN_APPROVAL_SCOPE = "dry_run"
DRY_RUN_APPROVAL_TYPES = {"public_export", "submission"}
REAL_SEND_APPROVAL_TYPE = "real_send"
REAL_SEND_APPROVAL_SCOPE = "real_send"
REAL_SEND_APPROVAL_TARGET = "real_submission"
PUBLICATION_APPROVAL_TARGETS = {
    "writer_public_export",
    "writer_submission",
    "opportunity_route_submission",
}
REAL_SEND_APPROVAL_TARGETS = {REAL_SEND_APPROVAL_TARGET}
SAFE_DRY_RUN_ACTIONS = {
    "render_review_files",
    "write_review_files",
    "dry_run_export",
    "review_packet",
}
SAFE_REAL_SEND_ACTIONS = {
    "send_submission",
    "stage_outbox_message",
    "write_send_receipt",
}
REAL_SEND_DELIVERY_ADAPTERS = {
    "direct_email",
    "submission_form",
    "local_outbox",
}
DIRECT_EMAIL_ADAPTER = "direct_email"
SUBMISSION_FORM_ADAPTER = "submission_form"
LOCAL_OUTBOX_ADAPTER = "local_outbox"
REAL_SEND_REQUIRED_FIELDS = {
    "subject_id": "subject_id",
    "opportunity_id": "opportunity_id",
    "candidate_id": "candidate_id",
    "route_id": "route_id",
    "delivery_adapter": "delivery_adapter",
    "recipient_ref": "recipient_ref",
    "payload_ref": "payload_ref",
    "operator_approved_at": "operator_approved_at",
}
FORBIDDEN_APPROVAL_ACTIONS = {
    "contact",
    "deliver",
    "delivery",
    "email",
    "form_submit",
    "outreach",
    "publish",
    "send",
    "submit",
    "submission",
    "upload",
}
SEND_PATH_FIELDS = {
    "contact_target",
    "delivery_path",
    "email",
    "form_action",
    "outbound_url",
    "publish_url",
    "recipient",
    "recipient_email",
    "send_path",
    "submission_url",
    "submit_url",
    "upload_url",
}
REQUIRED_SOURCE_FIELDS = {
    "id",
    "source_type",
    "privacy_level",
    "source_ref",
    "captured_at",
    "claim_ids",
    "confidence",
    "note",
}
REQUIRED_REPORT_SOURCE_TYPES = {"local_repo", "remote_repo", "web"}
PLACEHOLDERS = {"todo", "tbd", "fixme", "placeholder", "to be determined"}
CANDIDATE_REVIEW_FIELDS = {
    "genre": "Genre",
    "form": "Form",
    "length": "Length",
    "status": "Status",
    "rights_status": "Rights status",
    "content_ref": "Content/source ref",
}
ROUTE_REVIEW_FIELDS = {
    "route_type": "Route type",
    "guidelines_url": "Guidelines URL",
    "deadline": "Deadline",
    "word_limits": "Word limits",
    "fee": "Fee",
    "pay": "Pay",
    "ai_policy_disclosure_status": "AI policy/disclosure status",
}
CANDIDATE_READY_STATUS = "READY_FOR_REVIEW"
CANDIDATE_READY_REQUIRED_FIELDS = {
    "genre": "Genre",
    "form": "Form",
    "length": "Length",
    "rights_status": "Rights status",
    "content_ref": "Content/source ref",
}
FORBIDDEN_PRIVATE_KEYS = {
    "excerpt",
    "raw_excerpt",
    "raw_text",
    "message_text",
    "private_message",
    "manuscript_text",
    "submission_text",
    "work_text",
    "phone",
    "email",
    "contact_data",
    "creative_text",
}
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}")

MODE_TITLES = {
    "canon_dossier": "Canon Dossier",
    "public_presence_draft": "Public Presence Draft",
    "authority_scorecard": "Authority Scorecard",
    "private_dossier": "Private Dossier",
    "creator_presence_preview": "Creator Presence Preview",
    "public_page_draft": "Public Page Draft",
    "writer_submission": "Writer Submission Packet",
    "market_fit": "Market Fit Packet",
    "collaboration_packet": "Collaboration Packet",
    "project_page": "Project Page Draft",
    "co_branded_page": "Co-Branded Page Draft",
}
EXPORT_APPROVAL_TYPES_BY_MODE = {
    "public_presence_draft": {"public_export"},
    "creator_presence_preview": {"public_export"},
    "public_page_draft": {"public_export"},
    "writer_submission": {"submission"},
    "market_fit": {"submission"},
    "collaboration_packet": {"outreach"},
    "project_page": {"project_page"},
    "co_branded_page": {"co_branded_page"},
}
APPROVAL_LABELS = {
    "public_export": "Public export",
    "public_claim": "Public claim",
    "co_branded_page": "Co-branded page",
    "submission": "Submission",
    "outreach": "Outreach",
    "project_page": "Project page",
    "real_send": "Real send",
}
PUBLICATION_STACK_FILENAMES = {
    "README.md",
    "fit-report.md",
    "cover-letter-options.md",
    "ai-disclosure-note.md",
    "rights-checklist.md",
    "submission-checklist.md",
    "public-presence-copy-preview.md",
}
HANDOFF_PUBLIC_FORBIDDEN_FRAGMENTS = (
    "/Users/",
    "local-relationship-pipeline",
    "manuscript_text",
    "raw_text",
    "private_message",
    "submission_text",
    "contact_data",
    "creative_text",
    "source://private-manuscripts",
)
HANDOFF_LOOP_STEPS = (
    (
        "SCAN",
        "Opportunity routes, guidelines, fees, deadlines, and AI-policy posture are source-backed records.",
    ),
    (
        "MATCH",
        "Writer proof, candidate metadata, and venue route fields render into an explicit fit check.",
    ),
    (
        "BUILD",
        "Dossiers, public drafts, authority scorecards, and literary packets are generated artifacts with validators.",
    ),
    (
        "APPLY",
        "Outbound submission is approval-gated: dry-run packets render first, and real sends require explicit real_send approval.",
    ),
    (
        "FOLLOW_UP",
        "Blockers and approvals required become the next work surface instead of hidden manual labor.",
    ),
)


def _load_yaml(path: Path) -> dict[str, Any] | list[str]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"cannot read file: {exc}"]
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"]
    if not isinstance(doc, dict):
        return ["document is not a YAML mapping"]
    return doc


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_text(v) for v in value)
    return str(value or "")


def _walk(value: Any, path: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            rows.extend(_walk(child, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            rows.extend(_walk(child, f"{path}[{idx}]"))
    return rows


def _parse_time(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _claims(doc: dict[str, Any]) -> list[dict[str, Any]]:
    claims = doc.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _claim_ids(doc: dict[str, Any]) -> set[str]:
    return {str(claim.get("id")) for claim in _claims(doc) if claim.get("id")}


def _sources(doc: dict[str, Any]) -> list[dict[str, Any]]:
    sources = doc.get("sources", [])
    return [source for source in sources if isinstance(source, dict)] if isinstance(sources, list) else []


def _source_types(doc: dict[str, Any]) -> set[str]:
    return {str(source.get("source_type")) for source in _sources(doc) if source.get("source_type")}


def _source_by_id(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(source.get("id")): source for source in _sources(doc) if source.get("id")}


def _approvals(doc: dict[str, Any]) -> list[dict[str, Any]]:
    approvals = doc.get("approvals", [])
    if not isinstance(approvals, list):
        return []
    return [approval for approval in approvals if isinstance(approval, dict)]


def _works(doc: dict[str, Any]) -> list[dict[str, Any]]:
    works = doc.get("works", [])
    return [work for work in works if isinstance(work, dict)] if isinstance(works, list) else []


def _relations(doc: dict[str, Any]) -> list[dict[str, Any]]:
    relations = doc.get("relations", [])
    return [relation for relation in relations if isinstance(relation, dict)] if isinstance(relations, list) else []


def _candidate_works(doc: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = doc.get("candidate_works", [])
    if not isinstance(candidates, list):
        return []
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def _submission_routes(doc: dict[str, Any]) -> list[dict[str, Any]]:
    opportunity = doc.get("opportunity", {})
    if not isinstance(opportunity, dict):
        return []
    routes = opportunity.get("submission_routes", [])
    if not isinstance(routes, list):
        return []
    return [route for route in routes if isinstance(route, dict)]


def _source_is_public_web(source: dict[str, Any]) -> bool:
    return str(source.get("source_type")) == "web" and str(source.get("privacy_level")) == "public"


def _approved_public_claim_ids(doc: dict[str, Any]) -> set[str]:
    approved: set[str] = set()
    for approval in _approvals(doc):
        if str(approval.get("status")) != "approved":
            continue
        if str(approval.get("approval_type")) not in PUBLIC_APPROVAL_TYPES:
            continue
        claim_ids = approval.get("claim_ids", [])
        if isinstance(claim_ids, list):
            approved.update(str(claim_id) for claim_id in claim_ids)
    return approved


def _requires_message_sources(doc: dict[str, Any]) -> bool:
    if doc.get("claims_private_relational_insight") is True:
        return True
    for relation in doc.get("relations", []):
        if isinstance(relation, dict) and relation.get("private_relational_insight") is True:
            return True
    for claim in _claims(doc):
        if claim.get("private_relational_insight") is True:
            return True
        if claim.get("persona_claim") is True:
            return True
    return False


def _is_report_grade(doc: dict[str, Any]) -> bool:
    if doc.get("report_grade") is True:
        return True
    for claim in _claims(doc):
        if claim.get("report_grade") is True:
            return True
    outputs = doc.get("outputs", [])
    if isinstance(outputs, list):
        return any(isinstance(output, dict) and output.get("report_grade") is True for output in outputs)
    return False


def _validate_core_schema(doc: dict[str, Any], report_label: str) -> list[str]:
    violations: list[str] = []
    claim_ids = _claim_ids(doc)
    if str(doc.get("schema_version")) != "representation.v3":
        violations.append(f"{report_label}: schema_version must be representation.v3")
    if str(doc.get("kind")) not in {"representation_record", "representation_opportunity"}:
        violations.append(f"{report_label}: kind must be representation_record or representation_opportunity")

    subject = doc.get("subject")
    if not isinstance(subject, dict):
        violations.append(f"{report_label}: subject must be a mapping")
    else:
        subject_type = str(subject.get("type", ""))
        if subject_type not in SUBJECT_TYPES:
            violations.append(f"{report_label}: subject.type has invalid value {subject_type!r}")
        if not str(subject.get("name", "")).strip():
            violations.append(f"{report_label}: subject.name must be non-empty")

    for field in ("works", "relations", "claims", "sources", "approvals", "outputs"):
        if not isinstance(doc.get(field), list):
            violations.append(f"{report_label}: {field} must be a list")

    outputs = doc.get("outputs", [])
    if isinstance(outputs, list):
        for idx, output in enumerate(outputs):
            prefix = f"{report_label}: outputs[{idx}]"
            if not isinstance(output, dict):
                violations.append(f"{prefix} must be a mapping")
                continue
            mode = str(output.get("mode", ""))
            if mode not in OUTPUT_MODES:
                violations.append(f"{prefix} has invalid mode {mode!r}")
            if output.get("no_outward_action") is not True:
                violations.append(f"{prefix} must set no_outward_action: true")
            refs = output.get("claim_ids", [])
            if not isinstance(refs, list) or not refs:
                violations.append(f"{prefix} claim_ids must be a non-empty list")
            else:
                unknown = [str(claim_id) for claim_id in refs if str(claim_id) not in claim_ids]
                if unknown:
                    violations.append(f"{prefix} references unknown claim_ids: {', '.join(unknown)}")
            gates = output.get("acceptance_gates", [])
            if not isinstance(gates, list) or not gates:
                violations.append(f"{prefix} acceptance_gates must be a non-empty list")
            else:
                for gate in gates:
                    lowered = str(gate).lower()
                    if not str(gate).strip():
                        violations.append(f"{prefix} acceptance_gates must not include empty gates")
                    for placeholder in PLACEHOLDERS:
                        if placeholder in lowered:
                            violations.append(f"{prefix} acceptance gate contains placeholder text {placeholder!r}")

    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, dict) or not str(artifacts.get("next_reviewable_output", "")).strip():
        violations.append(f"{report_label}: artifacts.next_reviewable_output is required")

    return violations


def _validate_claims(doc: dict[str, Any], report_label: str) -> list[str]:
    violations: list[str] = []
    source_ids = set(_source_by_id(doc))
    approval_ids = {str(approval.get("id")) for approval in _approvals(doc) if approval.get("id")}

    for idx, claim in enumerate(_claims(doc)):
        prefix = f"{report_label}: claims[{idx}]"
        claim_id = str(claim.get("id", ""))
        if not claim_id:
            violations.append(f"{prefix} must include id")
        if not str(claim.get("summary", "")).strip():
            violations.append(f"{prefix} must include summary")
        visibility = str(claim.get("visibility", ""))
        if visibility not in VISIBILITY_LEVELS:
            violations.append(f"{prefix} has invalid visibility {visibility!r}")
        refs = claim.get("source_ids")
        if not isinstance(refs, list) or not refs:
            violations.append(f"{prefix} source_ids must be a non-empty list")
        else:
            unknown = [str(source_id) for source_id in refs if str(source_id) not in source_ids]
            if unknown:
                violations.append(f"{prefix} references unknown source_ids: {', '.join(unknown)}")
        public_ok = claim.get("public_ok")
        if public_ok is not True and public_ok is not False:
            violations.append(f"{prefix} public_ok must be true or false")
        approval_refs = claim.get("approval_ids", [])
        if approval_refs is not None:
            if not isinstance(approval_refs, list):
                violations.append(f"{prefix} approval_ids must be a list when present")
            else:
                unknown_approvals = [
                    str(approval_id) for approval_id in approval_refs if str(approval_id) not in approval_ids
                ]
                if unknown_approvals:
                    violations.append(f"{prefix} references unknown approval_ids: {', '.join(unknown_approvals)}")
    return violations


def _validate_sources(doc: dict[str, Any], report_label: str) -> list[str]:
    violations: list[str] = []
    sources = doc.get("sources")
    if not isinstance(sources, list) or not sources:
        return [f"{report_label}: sources must list at least one source"]

    claim_ids = _claim_ids(doc)
    seen_ids: set[str] = set()
    for idx, source in enumerate(sources):
        prefix = f"{report_label}: sources[{idx}]"
        if not isinstance(source, dict):
            violations.append(f"{prefix} must be a mapping")
            continue
        missing = sorted(REQUIRED_SOURCE_FIELDS - set(source))
        if missing:
            violations.append(f"{prefix} missing required field(s): {', '.join(missing)}")

        source_id = str(source.get("id", ""))
        if source_id:
            if source_id in seen_ids:
                violations.append(f"{prefix} duplicates source id {source_id!r}")
            seen_ids.add(source_id)
        source_type = str(source.get("source_type", ""))
        privacy = str(source.get("privacy_level", ""))
        confidence = str(source.get("confidence", ""))
        if source_type not in SOURCE_TYPES:
            violations.append(f"{prefix} has invalid source_type {source_type!r}")
        if privacy not in PRIVACY_LEVELS:
            violations.append(f"{prefix} has invalid privacy_level {privacy!r}")
        if confidence not in CONFIDENCE_LEVELS:
            violations.append(f"{prefix} has invalid confidence {confidence!r}")
        if not _parse_time(source.get("captured_at")):
            violations.append(f"{prefix} captured_at must be ISO-8601")

        claim_refs = source.get("claim_ids")
        if not isinstance(claim_refs, list) or not claim_refs:
            violations.append(f"{prefix} claim_ids must be a non-empty list")
        elif claim_ids:
            unknown = [str(claim_id) for claim_id in claim_refs if str(claim_id) not in claim_ids]
            if unknown:
                violations.append(f"{prefix} references unknown claim_ids: {', '.join(unknown)}")

        note = str(source.get("note", ""))
        if not note.strip():
            violations.append(f"{prefix} note must be non-empty and non-sensitive")
        if len(note) > 220:
            violations.append(f"{prefix} note must stay short enough to be non-sensitive")
        lowered = note.lower()
        for placeholder in PLACEHOLDERS:
            if placeholder in lowered:
                violations.append(f"{prefix} note contains placeholder text {placeholder!r}")
        if source_type == "messages" and privacy == "public":
            violations.append(f"{prefix} message evidence cannot be public")
        if source_type in {"local_repo", "remote_repo"} and privacy == "sensitive":
            violations.append(f"{prefix} repo source should be private/public, not sensitive")

    present = _source_types(doc)
    if _is_report_grade(doc):
        missing = sorted(REQUIRED_REPORT_SOURCE_TYPES - present)
        if missing:
            violations.append(
                f"{report_label}: report-grade records must include local_repo, remote_repo, "
                f"and web sources; missing {', '.join(missing)}"
            )
    if _requires_message_sources(doc) and "messages" not in present:
        violations.append(f"{report_label}: private relational/persona claims require messages source evidence")

    return violations


def _approval_action_violations(approval: dict[str, Any], prefix: str) -> list[str]:
    violations: list[str] = []
    real_send_approved = _approval_is_real_send_approval(approval)
    if approval.get("creates_send_path") is True and not real_send_approved:
        violations.append(f"{prefix} must not create a send path")

    for key in SEND_PATH_FIELDS:
        if not _missing(approval.get(key)):
            violations.append(f"{prefix} must not include outbound field {key!r}")

    actions = approval.get("permitted_actions", [])
    if actions is None:
        actions = []
    if not isinstance(actions, list):
        violations.append(f"{prefix} permitted_actions must be a list when present")
        return violations

    for action in actions:
        normalized = str(action).strip().lower().replace("-", "_").replace(" ", "_")
        if not normalized:
            continue
        if real_send_approved:
            if normalized in FORBIDDEN_APPROVAL_ACTIONS:
                violations.append(f"{prefix} permitted action {normalized!r} is ambiguous; use send_submission")
            elif normalized not in SAFE_REAL_SEND_ACTIONS:
                violations.append(f"{prefix} permitted action {normalized!r} is not an allowed real-send action")
        elif normalized in FORBIDDEN_APPROVAL_ACTIONS:
            violations.append(f"{prefix} permitted action {normalized!r} is an outward action")
        elif normalized not in SAFE_DRY_RUN_ACTIONS:
            violations.append(f"{prefix} permitted action {normalized!r} is not an allowed dry-run action")
    return violations


def _approval_is_real_send_approval(approval: dict[str, Any]) -> bool:
    return (
        str(approval.get("approval_type")) == REAL_SEND_APPROVAL_TYPE
        and str(approval.get("status")) == "approved"
        and str(approval.get("approval_scope")) == REAL_SEND_APPROVAL_SCOPE
    )


def _approval_is_dry_run(approval: dict[str, Any]) -> bool:
    return (
        str(approval.get("approval_scope")) == DRY_RUN_APPROVAL_SCOPE
        and approval.get("dry_run_only") is True
        and approval.get("no_outward_action") is True
    )


def _validate_approval_common(
    approval: dict[str, Any],
    prefix: str,
    claim_ids: set[str] | None,
    *,
    approval_record: bool = False,
) -> list[str]:
    violations: list[str] = []
    approval_id = str(approval.get("id", ""))
    if not approval_id:
        violations.append(f"{prefix} must include id")

    approval_type = str(approval.get("approval_type", ""))
    status = str(approval.get("status", ""))
    if approval_type not in APPROVAL_TYPES:
        violations.append(f"{prefix} has invalid approval_type {approval_type!r}")
    if status not in APPROVAL_STATUSES:
        violations.append(f"{prefix} has invalid status {status!r}")

    refs = approval.get("claim_ids", [])
    if refs is not None:
        if not isinstance(refs, list):
            violations.append(f"{prefix} claim_ids must be a list when present")
        elif claim_ids is not None:
            unknown = [str(claim_id) for claim_id in refs if str(claim_id) not in claim_ids]
            if unknown:
                violations.append(f"{prefix} references unknown claim_ids: {', '.join(unknown)}")

    violations.extend(_approval_action_violations(approval, prefix))

    if approval_type == REAL_SEND_APPROVAL_TYPE:
        if str(approval.get("approval_scope")) != REAL_SEND_APPROVAL_SCOPE:
            violations.append(f"{prefix} approval_scope must be {REAL_SEND_APPROVAL_SCOPE!r}")
        if approval_record:
            target = str(approval.get("approval_target") or REAL_SEND_APPROVAL_TARGET)
            if target not in REAL_SEND_APPROVAL_TARGETS:
                violations.append(
                    f"{prefix} approval_target must be one of: {', '.join(sorted(REAL_SEND_APPROVAL_TARGETS))}"
                )
            if _missing(approval.get("subject_id")):
                violations.append(f"{prefix} must include subject_id")
            if _missing(approval.get("opportunity_id")):
                violations.append(f"{prefix} must include opportunity_id")
            if _missing(approval.get("candidate_id")):
                violations.append(f"{prefix} must include candidate_id")
            if _missing(approval.get("route_id")):
                violations.append(f"{prefix} must include route_id")

        if status == "locked":
            if approval.get("real_send_lock") is not True:
                violations.append(f"{prefix} real-send lock must set real_send_lock: true")
            if approval.get("no_outward_action") is not True:
                violations.append(f"{prefix} real-send lock must set no_outward_action: true")
            return violations

        if status == "approved":
            if approval.get("real_send_lock") is True:
                violations.append(f"{prefix} approved real-send record must not set real_send_lock: true")
            if approval.get("real_send_approval") is not True:
                violations.append(f"{prefix} approved real-send record must set real_send_approval: true")
            if approval.get("dry_run_only") is True:
                violations.append(f"{prefix} approved real-send record must not set dry_run_only: true")
            if approval.get("no_outward_action") is True:
                violations.append(f"{prefix} approved real-send record must not set no_outward_action: true")
            missing_fields = [
                label for field, label in REAL_SEND_REQUIRED_FIELDS.items() if _missing(approval.get(field))
            ]
            if missing_fields:
                violations.append(f"{prefix} approved real-send record missing: {', '.join(missing_fields)}")
            adapter = str(approval.get("delivery_adapter") or "")
            if adapter and adapter not in REAL_SEND_DELIVERY_ADAPTERS:
                violations.append(
                    f"{prefix} delivery_adapter must be one of: {', '.join(sorted(REAL_SEND_DELIVERY_ADAPTERS))}"
                )
            if not _missing(approval.get("operator_approved_at")) and not _parse_time(
                approval.get("operator_approved_at")
            ):
                violations.append(f"{prefix} operator_approved_at must be ISO-8601")
            actions = approval.get("permitted_actions", [])
            normalized_actions = (
                {
                    str(action).strip().lower().replace("-", "_").replace(" ", "_")
                    for action in actions
                    if str(action).strip()
                }
                if isinstance(actions, list)
                else set()
            )
            if "send_submission" not in normalized_actions:
                violations.append(f"{prefix} approved real-send record must permit send_submission")
            return violations

        if approval.get("real_send_lock") is True:
            violations.append(f"{prefix} real_send_lock is only valid when status is locked")
        return violations

    if status == "approved" and approval_type in DRY_RUN_APPROVAL_TYPES:
        if not _approval_is_dry_run(approval):
            violations.append(f"{prefix} approved {approval_type} must be explicit dry-run-only approval")

    if approval_record and approval_type in DRY_RUN_APPROVAL_TYPES:
        target = str(approval.get("approval_target", ""))
        if target not in PUBLICATION_APPROVAL_TARGETS:
            violations.append(
                f"{prefix} approval_target must be one of: {', '.join(sorted(PUBLICATION_APPROVAL_TARGETS))}"
            )
        if str(approval.get("approval_scope")) != DRY_RUN_APPROVAL_SCOPE:
            violations.append(f"{prefix} approval_scope must be {DRY_RUN_APPROVAL_SCOPE!r}")
        if approval.get("dry_run_only") is not True:
            violations.append(f"{prefix} must set dry_run_only: true")
        if approval.get("no_outward_action") is not True:
            violations.append(f"{prefix} must set no_outward_action: true")
        if _missing(approval.get("subject_id")):
            violations.append(f"{prefix} must include subject_id")
        if _missing(approval.get("candidate_id")):
            violations.append(f"{prefix} must include candidate_id")
        if _missing(approval.get("route_id")):
            violations.append(f"{prefix} must include route_id")
        if target == "opportunity_route_submission" and _missing(approval.get("opportunity_id")):
            violations.append(f"{prefix} must include opportunity_id for route submission")

    return violations


def _validate_approvals(doc: dict[str, Any], report_label: str) -> list[str]:
    violations: list[str] = []
    claim_ids = _claim_ids(doc)
    seen_ids: set[str] = set()

    for idx, approval in enumerate(_approvals(doc)):
        prefix = f"{report_label}: approvals[{idx}]"
        approval_id = str(approval.get("id", ""))
        if not approval_id:
            violations.append(f"{prefix} must include id")
        elif approval_id in seen_ids:
            violations.append(f"{prefix} duplicates approval id {approval_id!r}")
        seen_ids.add(approval_id)

        violations.extend(_validate_approval_common(approval, prefix, claim_ids))

    return violations


def _validate_approval_record(doc: dict[str, Any], report_label: str) -> list[str]:
    violations: list[str] = []
    if str(doc.get("schema_version")) != "representation.v3":
        violations.append(f"{report_label}: schema_version must be representation.v3")
    if str(doc.get("kind")) != APPROVAL_RECORD_KIND:
        violations.append(f"{report_label}: kind must be {APPROVAL_RECORD_KIND}")
    if _missing(doc.get("id")):
        violations.append(f"{report_label}: id is required")
    approval_mode = str(doc.get("approval_mode") or DRY_RUN_APPROVAL_SCOPE)
    if approval_mode not in {DRY_RUN_APPROVAL_SCOPE, REAL_SEND_APPROVAL_SCOPE}:
        violations.append(
            f"{report_label}: approval_mode must be one of: {DRY_RUN_APPROVAL_SCOPE}, {REAL_SEND_APPROVAL_SCOPE}"
        )
    if approval_mode == DRY_RUN_APPROVAL_SCOPE:
        if doc.get("dry_run_only") is not True:
            violations.append(f"{report_label}: dry_run_only must be true")
        if doc.get("no_outward_action") is not True:
            violations.append(f"{report_label}: no_outward_action must be true")
    if approval_mode == REAL_SEND_APPROVAL_SCOPE:
        if doc.get("dry_run_only") is True:
            violations.append(f"{report_label}: real-send approval records must not set dry_run_only: true")
        if doc.get("no_outward_action") is True:
            violations.append(f"{report_label}: real-send approval records must not set no_outward_action: true")

    approvals = _approvals(doc)
    if not approvals:
        violations.append(f"{report_label}: approvals must list at least one approval")

    seen_ids: set[str] = set()
    has_real_send_lock = False
    has_real_send_record = False
    for idx, approval in enumerate(approvals):
        prefix = f"{report_label}: approvals[{idx}]"
        approval_id = str(approval.get("id", ""))
        if approval_id and approval_id in seen_ids:
            violations.append(f"{prefix} duplicates approval id {approval_id!r}")
        seen_ids.add(approval_id)
        approval_type = str(approval.get("approval_type", ""))
        if approval_type == REAL_SEND_APPROVAL_TYPE:
            has_real_send_record = True
            if str(approval.get("status")) == "locked":
                has_real_send_lock = True
        violations.extend(
            _validate_approval_common(
                approval,
                prefix,
                claim_ids=None,
                approval_record=True,
            )
        )

    if approval_mode == DRY_RUN_APPROVAL_SCOPE and not has_real_send_lock:
        violations.append(f"{report_label}: approvals must include a real-send lock record")
    if approval_mode == REAL_SEND_APPROVAL_SCOPE and not has_real_send_record:
        violations.append(f"{report_label}: approvals must include a real-send approval record")

    violations.extend(_validate_privacy(doc, report_label))
    return violations


def _validate_literary_metadata(doc: dict[str, Any], report_label: str) -> list[str]:
    violations: list[str] = []
    claim_ids = _claim_ids(doc)
    sources_by_id = _source_by_id(doc)
    source_ids = set(sources_by_id)
    candidate_ids: set[str] = set()

    candidates = doc.get("candidate_works", [])
    if candidates is not None and not isinstance(candidates, list):
        violations.append(f"{report_label}: candidate_works must be a list when present")
    for idx, candidate in enumerate(_candidate_works(doc)):
        prefix = f"{report_label}: candidate_works[{idx}]"
        candidate_id = str(candidate.get("id", ""))
        if not candidate_id:
            violations.append(f"{prefix} must include id")
        elif candidate_id in candidate_ids:
            violations.append(f"{prefix} duplicates candidate id {candidate_id!r}")
        candidate_ids.add(candidate_id)

        refs = candidate.get("source_ids", [])
        if refs is not None:
            if not isinstance(refs, list):
                violations.append(f"{prefix} source_ids must be a list when present")
            else:
                unknown = [str(source_id) for source_id in refs if str(source_id) not in source_ids]
                if unknown:
                    violations.append(f"{prefix} references unknown source_ids: {', '.join(unknown)}")

        claim_refs = candidate.get("claim_ids", [])
        if claim_refs is not None:
            if not isinstance(claim_refs, list):
                violations.append(f"{prefix} claim_ids must be a list when present")
            else:
                unknown_claims = [str(claim_id) for claim_id in claim_refs if str(claim_id) not in claim_ids]
                if unknown_claims:
                    violations.append(f"{prefix} references unknown claim_ids: {', '.join(unknown_claims)}")

        if _ready_for_review_status(candidate.get("status")):
            missing_ready = _missing_field_labels(candidate, CANDIDATE_READY_REQUIRED_FIELDS)
            if not isinstance(refs, list) or not refs:
                missing_ready.append("Source refs")
            if not isinstance(claim_refs, list) or not claim_refs:
                missing_ready.append("Claim refs")
            if missing_ready:
                violations.append(
                    f"{prefix} status {CANDIDATE_READY_STATUS} requires metadata: {', '.join(missing_ready)}"
                )

    route_ids: set[str] = set()
    for idx, route in enumerate(_submission_routes(doc)):
        prefix = f"{report_label}: opportunity.submission_routes[{idx}]"
        route_id = str(route.get("id", ""))
        if not route_id:
            violations.append(f"{prefix} must include id")
        elif route_id in route_ids:
            violations.append(f"{prefix} duplicates route id {route_id!r}")
        route_ids.add(route_id)
        if not str(route.get("route_type", "")).strip():
            violations.append(f"{prefix} must include route_type")

        guideline_refs = route.get("guidelines_source_ids", [])
        if guideline_refs is not None:
            if not isinstance(guideline_refs, list):
                violations.append(f"{prefix} guidelines_source_ids must be a list when present")
                guideline_refs = []
            else:
                unknown_guideline_refs = [
                    str(source_id) for source_id in guideline_refs if str(source_id) not in source_ids
                ]
                if unknown_guideline_refs:
                    violations.append(
                        f"{prefix} references unknown guidelines_source_ids: {', '.join(unknown_guideline_refs)}"
                    )

        if _route_is_venue_specific(route):
            if not isinstance(guideline_refs, list) or not guideline_refs:
                violations.append(
                    f"{prefix} guidelines_source_ids must list public web sources for venue-specific routes"
                )
            else:
                non_public_web = [
                    str(source_id)
                    for source_id in guideline_refs
                    if str(source_id) in sources_by_id and not _source_is_public_web(sources_by_id[str(source_id)])
                ]
                if non_public_web:
                    violations.append(
                        f"{prefix} guidelines_source_ids must reference public web sources: {', '.join(non_public_web)}"
                    )
                guidelines_url = str(route.get("guidelines_url") or "").strip()
                if guidelines_url:
                    source_urls = {
                        str(sources_by_id[str(source_id)].get("source_ref"))
                        for source_id in guideline_refs
                        if str(source_id) in sources_by_id
                    }
                    if guidelines_url not in source_urls:
                        violations.append(f"{prefix} guidelines_url must match a guidelines_source_ids source_ref")

        ai_refs = route.get("ai_policy_source_ids", [])
        if ai_refs is not None:
            if not isinstance(ai_refs, list):
                violations.append(f"{prefix} ai_policy_source_ids must be a list when present")
            else:
                unknown_ai_refs = [str(source_id) for source_id in ai_refs if str(source_id) not in source_ids]
                if unknown_ai_refs:
                    violations.append(f"{prefix} references unknown ai_policy_source_ids: {', '.join(unknown_ai_refs)}")

    return violations


def _contains_placeholder_text(value: Any) -> str | None:
    lowered = _text(value).lower()
    for placeholder in PLACEHOLDERS:
        if placeholder in lowered:
            return placeholder
    return None


def _subject_representation_modes(doc: dict[str, Any]) -> set[str]:
    subject = doc.get("subject")
    if not isinstance(subject, dict):
        return set()
    modes = subject.get("representation_modes", [])
    if not isinstance(modes, list):
        return set()
    return {str(mode) for mode in modes if str(mode).strip()}


def _validate_authority_program(doc: dict[str, Any], report_label: str) -> list[str]:
    violations: list[str] = []
    declares_authority = bool(
        AUTHORITY_MODES.intersection(_output_modes(doc))
        or AUTHORITY_MODES.intersection(_subject_representation_modes(doc))
        or doc.get("authority_program") is not None
    )
    if not declares_authority:
        return violations

    program = doc.get("authority_program")
    if not isinstance(program, dict):
        return [f"{report_label}: authority_program must be a mapping"]

    if str(program.get("goal", "")) != AUTHORITY_GOAL:
        violations.append(f"{report_label}: authority_program.goal must be {AUTHORITY_GOAL!r}")

    archetypes = program.get("archetype_functions")
    if not isinstance(archetypes, dict):
        violations.append(f"{report_label}: authority_program.archetype_functions must be a mapping")
    else:
        for archetype in AUTHORITY_ARCHETYPE_FUNCTIONS:
            value = archetypes.get(archetype)
            if _missing(value):
                violations.append(f"{report_label}: authority_program.archetype_functions.{archetype} is required")
            else:
                placeholder = _contains_placeholder_text(value)
                if placeholder:
                    violations.append(
                        f"{report_label}: authority_program.archetype_functions.{archetype} "
                        f"contains placeholder text {placeholder!r}"
                    )

    outputs = _output_modes(doc)
    missing_outputs = sorted(AUTHORITY_MODES - outputs)
    if missing_outputs:
        violations.append(f"{report_label}: authority_program outputs must declare modes: {', '.join(missing_outputs)}")

    claim_ids = _claim_ids(doc)
    public_renderable_ids = _public_renderable_claim_ids(doc)
    axes = program.get("axes")
    if not isinstance(axes, dict):
        violations.append(f"{report_label}: authority_program.axes must be a mapping")
        return violations

    axis_keys = set(str(key) for key in axes)
    missing_axes = sorted(set(AUTHORITY_AXES) - axis_keys)
    extra_axes = sorted(axis_keys - set(AUTHORITY_AXES))
    if missing_axes:
        violations.append(
            f"{report_label}: authority_program.axes missing required axis/axes: {', '.join(missing_axes)}"
        )
    if extra_axes:
        violations.append(f"{report_label}: authority_program.axes has unsupported axis/axes: {', '.join(extra_axes)}")

    for axis_name in AUTHORITY_AXES:
        axis = axes.get(axis_name)
        prefix = f"{report_label}: authority_program.axes.{axis_name}"
        if not isinstance(axis, dict):
            violations.append(f"{prefix} must be a mapping")
            continue

        refs = axis.get("claim_ids")
        if not isinstance(refs, list) or not refs:
            violations.append(f"{prefix}.claim_ids must be a non-empty list")
            axis_claim_ids: set[str] = set()
        else:
            axis_claim_ids = {str(claim_id) for claim_id in refs}
            unknown = sorted(claim_id for claim_id in axis_claim_ids if claim_id not in claim_ids)
            if unknown:
                violations.append(f"{prefix}.claim_ids references unknown claim_ids: {', '.join(unknown)}")

        summary = axis.get("summary")
        if _missing(summary):
            violations.append(f"{prefix}.summary must be non-empty")
        else:
            placeholder = _contains_placeholder_text(summary)
            if placeholder:
                violations.append(f"{prefix}.summary contains placeholder text {placeholder!r}")

        gates = axis.get("output_gates")
        if not isinstance(gates, list) or not gates:
            violations.append(f"{prefix}.output_gates must be a non-empty list")
        else:
            for gate in gates:
                if _missing(gate):
                    violations.append(f"{prefix}.output_gates must not include empty gates")
                    continue
                placeholder = _contains_placeholder_text(gate)
                if placeholder:
                    violations.append(f"{prefix}.output_gates contains placeholder text {placeholder!r}")

        public_copy = axis.get("public_copy")
        public_refs = axis.get("public_claim_ids")
        if _missing(public_copy):
            violations.append(f"{prefix}.public_copy must be non-empty")
        else:
            placeholder = _contains_placeholder_text(public_copy)
            if placeholder:
                violations.append(f"{prefix}.public_copy contains placeholder text {placeholder!r}")
            if not isinstance(public_refs, list) or not public_refs:
                violations.append(f"{prefix}.public_claim_ids must be non-empty when public_copy is present")

        if public_refs is not None:
            if not isinstance(public_refs, list):
                violations.append(f"{prefix}.public_claim_ids must be a list when present")
            else:
                public_ids = {str(claim_id) for claim_id in public_refs}
                unknown = sorted(claim_id for claim_id in public_ids if claim_id not in claim_ids)
                if unknown:
                    violations.append(f"{prefix}.public_claim_ids references unknown claim_ids: {', '.join(unknown)}")
                outside_axis = sorted(public_ids - axis_claim_ids)
                if outside_axis:
                    violations.append(
                        f"{prefix}.public_claim_ids must be a subset of axis claim_ids: {', '.join(outside_axis)}"
                    )
                not_public = sorted(public_ids - public_renderable_ids)
                if not_public:
                    violations.append(
                        f"{prefix}.public_claim_ids must reference public-source or "
                        f"claim-approved private claims: {', '.join(not_public)}"
                    )

    return violations


def _validate_privacy(doc: dict[str, Any], report_label: str) -> list[str]:
    violations: list[str] = []
    for dotted, value in _walk(doc):
        key = dotted.split(".")[-1].split("[")[0]
        if key in FORBIDDEN_PRIVATE_KEYS:
            violations.append(
                f"{report_label}: forbidden tracked/public private field {dotted!r}; "
                "store only source refs and non-sensitive notes"
            )
        if isinstance(value, str):
            if EMAIL_RE.search(value):
                violations.append(f"{report_label}: contact email detected at {dotted!r}")
            if PHONE_RE.search(value):
                violations.append(f"{report_label}: phone-like contact data detected at {dotted!r}")

    for idx, source in enumerate(_sources(doc)):
        if source.get("source_type") == "messages":
            source_text = _text(source).lower()
            for phrase in ("direct quote", "verbatim", "excerpt", "raw transcript"):
                if phrase in source_text:
                    violations.append(f"{report_label}: message source {idx} appears to expose private text")

    return violations


def validate_doc(doc: dict[str, Any], label: str = "<doc>") -> list[str]:
    """Return validation violations for one Representation Substrate record."""
    if str(doc.get("kind")) == APPROVAL_RECORD_KIND:
        return _validate_approval_record(doc, label)

    violations: list[str] = []
    violations.extend(_validate_core_schema(doc, label))
    violations.extend(_validate_claims(doc, label))
    violations.extend(_validate_sources(doc, label))
    violations.extend(_validate_approvals(doc, label))
    violations.extend(_validate_literary_metadata(doc, label))
    violations.extend(_validate_authority_program(doc, label))
    violations.extend(_validate_privacy(doc, label))
    return violations


def validate_path(path: Path) -> list[str]:
    doc = _load_yaml(path)
    if isinstance(doc, list):
        return doc
    return validate_doc(doc, str(path))


def fleet_paths(base: Path) -> list[Path]:
    roots = [base / "records", base / "opportunities", base / "approvals"]
    paths: list[Path] = []
    for root in roots:
        if root.exists():
            paths.extend(root.glob("*.yaml"))
    return sorted(paths)


def _phrase_spans(text: str, phrases: list[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for phrase in phrases:
        pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        spans.extend((m.start(), m.end()) for m in pattern.finditer(text))
    return spans


def _inside_spans(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start >= span_start and end <= span_end for span_start, span_end in spans)


def index_mentions(text: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Index mentions with explicit aliases and deny/context filters."""
    mention_cfg = profile.get("mention_index", {}) if isinstance(profile, dict) else {}
    aliases = [str(alias) for alias in mention_cfg.get("aliases", [])]
    ambiguous = [str(alias) for alias in mention_cfg.get("ambiguous_aliases", [])]
    deny_phrases = [str(phrase) for phrase in mention_cfg.get("deny_phrases", [])]
    context_terms = [str(term).lower() for term in mention_cfg.get("context_terms", [])]
    denied = _phrase_spans(text, deny_phrases)

    rows: list[dict[str, Any]] = []
    for alias in aliases + ambiguous:
        if not alias:
            continue
        pattern = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            start, end = match.span()
            if _inside_spans(start, end, denied):
                continue
            if alias in ambiguous and context_terms:
                window = text[max(0, start - 100) : min(len(text), end + 100)].lower()
                if not any(term in window for term in context_terms):
                    continue
            rows.append(
                {
                    "alias": alias,
                    "match": match.group(0),
                    "start": start,
                    "end": end,
                    "context": text[max(0, start - 48) : min(len(text), end + 48)],
                }
            )

    rows.sort(key=lambda row: (int(row["start"]), -len(str(row["match"]))))
    deduped: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for row in rows:
        span = (int(row["start"]), int(row["end"]))
        if _inside_spans(span[0], span[1], occupied):
            continue
        occupied.append(span)
        deduped.append(row)
    return deduped


def _claim_source_privacies(claim: dict[str, Any], sources: dict[str, dict[str, Any]]) -> list[str]:
    privacies: list[str] = []
    for source_id in claim.get("source_ids", []):
        source = sources.get(str(source_id))
        if source:
            privacies.append(str(source.get("privacy_level", "")))
    return privacies


def _claim_source_types(claim: dict[str, Any], sources: dict[str, dict[str, Any]]) -> list[str]:
    source_types: list[str] = []
    for source_id in claim.get("source_ids", []):
        source = sources.get(str(source_id))
        if source:
            source_types.append(str(source.get("source_type", "")))
    return source_types


def _claim_has_public_approval(claim: dict[str, Any], approved_claim_ids: set[str]) -> bool:
    claim_id = str(claim.get("id", ""))
    return claim_id in approved_claim_ids


def _claim_is_public_renderable(
    claim: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    approved_claim_ids: set[str],
) -> bool:
    if claim.get("public_ok") is not True:
        return False
    source_ids = [str(source_id) for source_id in claim.get("source_ids", [])]
    if not source_ids or any(source_id not in sources for source_id in source_ids):
        return False
    privacies = _claim_source_privacies(claim, sources)
    source_types = _claim_source_types(claim, sources)
    all_public = bool(privacies) and all(privacy == "public" for privacy in privacies)
    public_approved = _claim_has_public_approval(claim, approved_claim_ids)
    if "messages" in source_types and not public_approved:
        return False
    return all_public or public_approved


def public_claims(doc: dict[str, Any]) -> list[dict[str, Any]]:
    sources = _source_by_id(doc)
    approved_claim_ids = _approved_public_claim_ids(doc)
    out: list[dict[str, Any]] = []

    for claim in _claims(doc):
        if _claim_is_public_renderable(claim, sources, approved_claim_ids):
            out.append(claim)

    return out


def _public_renderable_claim_ids(doc: dict[str, Any]) -> set[str]:
    return {str(claim.get("id")) for claim in public_claims(doc) if claim.get("id")}


def _output_modes(doc: dict[str, Any]) -> set[str]:
    outputs = doc.get("outputs", [])
    if not isinstance(outputs, list):
        return set()
    return {str(output.get("mode")) for output in outputs if isinstance(output, dict) and output.get("mode")}


def _output_claim_ids(doc: dict[str, Any], mode: str) -> set[str]:
    outputs = doc.get("outputs", [])
    if not isinstance(outputs, list):
        return set()
    for output in outputs:
        if not isinstance(output, dict) or str(output.get("mode")) != mode:
            continue
        refs = output.get("claim_ids", [])
        if isinstance(refs, list):
            return {str(claim_id) for claim_id in refs}
    return set()


def _output_config(doc: dict[str, Any], mode: str) -> dict[str, Any]:
    outputs = doc.get("outputs", [])
    if not isinstance(outputs, list):
        return {}
    for output in outputs:
        if isinstance(output, dict) and str(output.get("mode")) == mode:
            return output
    return {}


def _approved_export(doc: dict[str, Any], mode: str) -> bool:
    required_types = EXPORT_APPROVAL_TYPES_BY_MODE.get(mode, set())
    for approval in _approvals(doc):
        if str(approval.get("status")) != "approved":
            continue
        if not _approval_is_dry_run(approval):
            continue
        approval_type = str(approval.get("approval_type"))
        if approval_type in required_types:
            return True
    return False


def _comma_list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "none declared"
    return ", ".join(str(value) for value in values if str(value).strip()) or "none declared"


def _sentence(value: Any, fallback: str = "not declared") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    if text.endswith((".", "!", "?")):
        return text
    return f"{text}."


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = value.strip().lower().replace("_", " ").replace("-", " ")
        return normalized in {
            "",
            "none",
            "null",
            "unknown",
            "not declared",
            "not sourced",
            "missing",
            "unresolved",
            "tbd",
        }
    if isinstance(value, list):
        return not value
    if isinstance(value, dict):
        return not value
    return False


def _ready_for_review_status(value: Any) -> bool:
    normalized = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    return normalized == CANDIDATE_READY_STATUS


def _display_value(value: Any) -> str:
    if _missing(value):
        return "missing"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "missing"
    if isinstance(value, dict):
        pairs = [f"{key}: {val}" for key, val in value.items() if not _missing(val)]
        return "; ".join(pairs) if pairs else "missing"
    return str(value)


def _safe_metadata_text(value: Any, field: str, max_len: int = 260) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if "\n" in text or "\r" in text:
        raise ValueError(f"{field} must be a single metadata line")
    if len(text) > max_len:
        raise ValueError(f"{field} must be {max_len} characters or fewer")
    if EMAIL_RE.search(text) or PHONE_RE.search(text):
        raise ValueError(f"{field} must not contain contact data")
    lowered = text.lower()
    for phrase in ("direct quote", "verbatim", "raw transcript", "manuscript text"):
        if phrase in lowered:
            raise ValueError(f"{field} appears to contain private or creative text")
    return text


def _safe_optional_metadata_text(value: Any, field: str, max_len: int = 220) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return _safe_metadata_text(text, field, max_len=max_len)


def candidate_intake_row(
    *,
    candidate_id: str,
    title: str,
    content_ref: str,
    source_ids: list[str],
    claim_ids: list[str],
    genre: str = "",
    form: str = "",
    length: str = "",
    status: str = "metadata_only_source_ref_supplied",
    rights_status: str = "",
    note: str = "Metadata-only candidate intake; no creative text stored.",
) -> dict[str, Any]:
    """Build a metadata-only candidate row without storing manuscript content."""
    cleaned_source_ids = [
        _safe_metadata_text(source_id, "source-id", max_len=120) for source_id in source_ids if str(source_id).strip()
    ]
    cleaned_claim_ids = [
        _safe_metadata_text(claim_id, "claim-id", max_len=120) for claim_id in claim_ids if str(claim_id).strip()
    ]
    if not cleaned_source_ids:
        raise ValueError("at least one source-id is required")
    if not cleaned_claim_ids:
        raise ValueError("at least one claim-id is required")

    return {
        "id": _safe_metadata_text(candidate_id, "id", max_len=120),
        "title": _safe_metadata_text(title, "title"),
        "genre": _safe_optional_metadata_text(genre, "genre", max_len=80),
        "form": _safe_optional_metadata_text(form, "form", max_len=80),
        "length": _safe_optional_metadata_text(length, "length", max_len=80),
        "status": _safe_metadata_text(status, "status", max_len=120),
        "rights_status": _safe_optional_metadata_text(rights_status, "rights-status"),
        "content_ref": _safe_metadata_text(content_ref, "content-ref"),
        "source_ids": cleaned_source_ids,
        "claim_ids": cleaned_claim_ids,
        "note": _safe_metadata_text(note, "note", max_len=220),
    }


def _missing_field_labels(row: dict[str, Any], fields: dict[str, str]) -> list[str]:
    return [label for field, label in fields.items() if _missing(row.get(field))]


def _candidate_by_id(doc: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    for candidate in _candidate_works(doc):
        if str(candidate.get("id")) == candidate_id:
            return candidate
    return None


def _route_by_selector(doc: dict[str, Any], selector: str) -> dict[str, Any] | None:
    selector_lower = selector.lower()
    for route in _submission_routes(doc):
        values = [
            route.get("id"),
            route.get("platform"),
            route.get("venue"),
            route.get("name"),
        ]
        if selector_lower in {str(value).lower() for value in values if value}:
            return route
    return None


def _append_bullet_section(lines: list[str], title: str, rows: list[str], empty: str) -> None:
    lines.extend(["", f"## {title}", ""])
    if rows:
        lines.extend(rows)
    else:
        lines.append(f"- {empty}")


def _items_for_claims(items: list[dict[str, Any]], claim_ids: set[str]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in items:
        refs = item.get("claim_ids", [])
        if isinstance(refs, list) and claim_ids.intersection(str(ref) for ref in refs):
            selected.append(item)
    return selected


def _work_line(work: dict[str, Any]) -> str:
    title = str(work.get("title") or work.get("id") or "Untitled work")
    work_type = str(work.get("type") or "work")
    relation = str(work.get("relation") or "related")
    return f"- {title}: {work_type}; relation {relation}."


def _relation_line(relation: dict[str, Any]) -> str:
    relation_id = str(relation.get("id") or "relation")
    relation_type = str(relation.get("relation_type") or "relation")
    posture = str(relation.get("posture_source") or "not declared")
    line = f"- {relation_id}: {relation_type}; posture source {posture}."
    constraints = relation.get("consent_constraints", [])
    if isinstance(constraints, list) and constraints:
        line += " Consent constraints: " + "; ".join(str(item) for item in constraints) + "."
    return line


def _claim_line(claim: dict[str, Any]) -> str:
    label = str(claim.get("label", claim.get("id", "claim")))
    summary = str(claim.get("summary", ""))
    visibility = str(claim.get("visibility", ""))
    return f"- {label}: {summary} [{visibility}]"


def _source_line(source: dict[str, Any], public_mode: bool) -> str:
    source_type = str(source.get("source_type") or "source")
    privacy = str(source.get("privacy_level") or "unknown")
    confidence = str(source.get("confidence") or "unknown")
    note = str(source.get("note") or "No note.")
    if public_mode and privacy != "public":
        source_id = "approved-private-source"
        ref = "source reference withheld"
    else:
        source_id = str(source.get("id") or "source")
        ref = str(source.get("source_ref") or "source reference not declared")
    return f"- {source_id}: {source_type}; {privacy}; confidence {confidence}; {ref}. {note}"


def _mode_approval_types(mode: str) -> set[str]:
    if mode == "private_dossier":
        return set(APPROVAL_TYPES)
    return EXPORT_APPROVAL_TYPES_BY_MODE.get(mode, set())


def _approval_line(approval: dict[str, Any]) -> str:
    approval_type = str(approval.get("approval_type") or "approval")
    label = APPROVAL_LABELS.get(approval_type, approval_type)
    status = str(approval.get("status") or "not_recorded")
    note = str(approval.get("note") or "No note.")
    return f"- {label}: {status}. {note}"


def _approval_rows(doc: dict[str, Any], mode: str, claim_ids: set[str]) -> list[str]:
    rows: list[str] = []
    wanted_types = _mode_approval_types(mode)
    recorded_types: set[str] = set()
    for approval in _approvals(doc):
        approval_type = str(approval.get("approval_type"))
        approval_claim_ids = approval.get("claim_ids", [])
        claim_specific = isinstance(approval_claim_ids, list) and claim_ids.intersection(
            str(claim_id) for claim_id in approval_claim_ids
        )
        if approval_type in wanted_types or approval_type == "public_claim" and claim_specific:
            recorded_types.add(approval_type)
            rows.append(_approval_line(approval))
    for missing_type in sorted(wanted_types - recorded_types):
        rows.append(
            f"- {APPROVAL_LABELS.get(missing_type, missing_type)}: not_recorded. "
            "Required before outward use of this mode."
        )
    return rows


def _authority_program(doc: dict[str, Any]) -> dict[str, Any]:
    program = doc.get("authority_program")
    return program if isinstance(program, dict) else {}


def _authority_axes(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    axes = _authority_program(doc).get("axes")
    if not isinstance(axes, dict):
        return {}
    return {str(key): value for key, value in axes.items() if isinstance(value, dict)}


def _claim_map(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(claim.get("id")): claim for claim in _claims(doc) if claim.get("id")}


def _claim_labels(doc: dict[str, Any], claim_ids: set[str]) -> str:
    claims = _claim_map(doc)
    labels = [str(claims[claim_id].get("label") or claim_id) for claim_id in sorted(claim_ids) if claim_id in claims]
    return ", ".join(labels) if labels else "none"


def _axis_claim_ids(axis: dict[str, Any], field: str = "claim_ids") -> set[str]:
    refs = axis.get(field, [])
    if not isinstance(refs, list):
        return set()
    return {str(claim_id) for claim_id in refs if str(claim_id).strip()}


def _approval_status(doc: dict[str, Any], approval_type: str) -> str:
    statuses = [
        str(approval.get("status") or "not_recorded")
        for approval in _approvals(doc)
        if str(approval.get("approval_type")) == approval_type
    ]
    return statuses[0] if statuses else "not_recorded"


def authority_axis_evaluations(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Score authority axes without claiming that the long-range goal is achieved."""
    axes = _authority_axes(doc)
    public_renderable_ids = _public_renderable_claim_ids(doc)
    public_output = _output_config(doc, "public_presence_draft")
    public_output_gates = public_output.get("acceptance_gates", [])
    if not isinstance(public_output_gates, list):
        public_output_gates = []
    public_export_status = _approval_status(doc, "public_export")

    rows: list[dict[str, Any]] = []
    for axis_name in AUTHORITY_AXES:
        axis = axes.get(axis_name, {})
        claim_ids = _axis_claim_ids(axis)
        public_claim_ids = _axis_claim_ids(axis, "public_claim_ids")
        if not public_claim_ids:
            public_claim_ids = claim_ids
        renderable_public_ids = public_claim_ids.intersection(public_renderable_ids)
        private_or_unapproved_ids = claim_ids - public_renderable_ids
        blockers: list[str] = []
        gates: list[str] = []

        if not claim_ids:
            blockers.append("source-backed claim references are missing")
        if not renderable_public_ids:
            blockers.append("public-renderable proof is missing for the axis")
        if "public_presence_draft" not in _output_modes(doc):
            blockers.append("public_presence_draft output is not declared")
        if not public_output_gates:
            blockers.append("public presence output gates are missing")

        if private_or_unapproved_ids:
            gates.append(
                "private or unapproved claims withheld from public copy: "
                + _claim_labels(doc, private_or_unapproved_ids)
            )
        if public_export_status != "approved":
            gates.append(f"public export approval is {public_export_status}")
        axis_gates = axis.get("output_gates", [])
        if isinstance(axis_gates, list) and axis_gates:
            gates.extend(str(gate) for gate in axis_gates)

        if blockers:
            status = "BLOCKED"
        elif public_export_status == "approved":
            status = "PUBLIC_READY"
        else:
            status = "STAGED"

        rows.append(
            {
                "axis": axis_name,
                "status": status,
                "claim_ids": claim_ids,
                "public_claim_ids": public_claim_ids,
                "renderable_public_ids": renderable_public_ids,
                "private_or_unapproved_ids": private_or_unapproved_ids,
                "approval_state": public_export_status,
                "blockers": blockers,
                "gates": gates,
                "summary": str(axis.get("summary") or ""),
                "public_copy": str(axis.get("public_copy") or ""),
            }
        )

    return rows


def _authority_dossier_rows(doc: dict[str, Any]) -> list[str]:
    program = _authority_program(doc)
    if not program:
        return ["- No authority_program is declared."]
    rows = [
        f"- Goal: {program.get('goal', 'not declared')}.",
        "- Civilizational status: not claimed; this is a long-range apparatus, not an achieved rank.",
    ]
    archetypes = program.get("archetype_functions", {})
    if isinstance(archetypes, dict):
        for key in AUTHORITY_ARCHETYPE_FUNCTIONS:
            rows.append(f"- Archetype function {key}: {_sentence(archetypes.get(key))}")
    for axis_name, axis in _authority_axes(doc).items():
        claim_ids = _axis_claim_ids(axis)
        rows.append(
            f"- Axis {axis_name}: {_sentence(axis.get('summary'))} Claim refs: {_claim_labels(doc, claim_ids)}."
        )
    return rows


def _authority_public_presence_rows(doc: dict[str, Any]) -> list[str]:
    rows = [
        "- Public copy is limited to public-source claims and claim-approved private claims.",
        "- No equivalence to Stephen King, T. S. Eliot, or any achieved canonical rank is asserted.",
    ]
    public_renderable_ids = _public_renderable_claim_ids(doc)
    for axis_name in AUTHORITY_AXES:
        axis = _authority_axes(doc).get(axis_name, {})
        public_claim_ids = _axis_claim_ids(axis, "public_claim_ids").intersection(public_renderable_ids)
        if not public_claim_ids:
            rows.append(f"- {axis_name}: public proof is not renderable yet.")
            continue
        copy = str(axis.get("public_copy") or "").strip()
        if not copy:
            rows.append(f"- {axis_name}: public copy is not staged.")
            continue
        rows.append(f"- {axis_name}: {copy} Proof: {_claim_labels(doc, public_claim_ids)}.")
    return rows


def _authority_scorecard_rows(doc: dict[str, Any]) -> list[str]:
    rows = [
        "- Civilizational gravitas is the program goal, not an achieved public status claim.",
        "- Allowed statuses: BLOCKED, STAGED, PUBLIC_READY.",
    ]
    for evaluation in authority_axis_evaluations(doc):
        axis = str(evaluation["axis"])
        status = str(evaluation["status"])
        claim_ids = evaluation["claim_ids"]
        renderable_public_ids = evaluation["renderable_public_ids"]
        approval_state = str(evaluation["approval_state"])
        blockers = evaluation["blockers"]
        gates = evaluation["gates"]
        rows.append(
            f"- {axis}: {status}. Source-backed claims: {_claim_labels(doc, claim_ids)}. "
            f"Public-renderable proof: {_claim_labels(doc, renderable_public_ids)}. "
            f"Approval state: public_export {approval_state}."
        )
        if blockers:
            rows.append(f"  Blockers: {'; '.join(str(blocker) for blocker in blockers)}.")
        if gates:
            rows.append(f"  Gates: {'; '.join(str(gate) for gate in gates)}.")
    return rows


def _source_rows(doc: dict[str, Any], rendered_claim_ids: set[str], mode: str) -> list[str]:
    rows: list[str] = []
    public_mode = mode in PUBLIC_RENDER_MODES
    for source in _sources(doc):
        refs = source.get("claim_ids", [])
        if isinstance(refs, list) and rendered_claim_ids.intersection(str(ref) for ref in refs):
            rows.append(_source_line(source, public_mode))
    return rows


def _submission_readiness_rows(doc: dict[str, Any], claims: list[dict[str, Any]]) -> list[str]:
    sources = _source_by_id(doc)
    public_profile_claims: list[dict[str, Any]] = []
    for claim in claims:
        source_ids = [str(source_id) for source_id in claim.get("source_ids", [])]
        if source_ids and all(sources.get(source_id, {}).get("privacy_level") == "public" for source_id in source_ids):
            public_profile_claims.append(claim)

    rows: list[str] = []
    if public_profile_claims:
        labels = ", ".join(str(claim.get("label", claim.get("id"))) for claim in public_profile_claims)
        rows.append(f"- Public/profile evidence available: {labels}.")
    else:
        rows.append("- Public/profile evidence available: missing.")

    candidates = _candidate_works(doc)
    if candidates:
        candidate = candidates[0]
        title = str(candidate.get("title") or candidate.get("id") or "candidate work")
        rows.append(f"- Candidate work metadata staged: {title}.")
        missing = _missing_field_labels(candidate, CANDIDATE_REVIEW_FIELDS)
    else:
        rows.append("- Candidate work metadata staged: missing.")
        missing = list(CANDIDATE_REVIEW_FIELDS.values())

    if missing:
        rows.append(f"- Missing manuscript data: {', '.join(missing)}.")
        rows.append(
            "- Readiness blocker: no venue-facing submission packet should be treated as complete until these fields are supplied."
        )
    else:
        rows.append("- Missing manuscript data: none detected.")

    rows.append("- Private collaboration claims are excluded unless separately approved for this mode.")
    return rows


def _public_page_draft_rows(subject_name: str, claims: list[dict[str, Any]]) -> list[str]:
    if not claims:
        return ["- No public-source claims are available for draft copy."]

    proof_points = "; ".join(str(claim.get("summary", claim.get("label", "claim"))).rstrip(".!?") for claim in claims)
    rows = [
        f"- {subject_name} can be presented from public evidence and claim-approved context only in this draft.",
        f"- Public proof points: {proof_points}.",
        "- Private collaboration, message, local-only, and unapproved source references are excluded.",
    ]
    return rows


def render_record(doc: dict[str, Any], mode: str, export: bool = False) -> str:
    """Render one representation mode without taking outward action."""
    if mode not in OUTPUT_MODES:
        raise ValueError(f"unknown representation mode: {mode}")
    if mode not in _output_modes(doc):
        raise ValueError(f"record does not declare output mode: {mode}")
    if export and not _approved_export(doc, mode):
        raise ValueError("export is locked until matching explicit approval is recorded")

    subject = doc.get("subject", {})
    if not isinstance(subject, dict):
        raise ValueError("record lacks subject configuration")
    subject_name = str(subject.get("name", doc.get("name", "Unnamed subject")))
    title = MODE_TITLES[mode]
    output = _output_config(doc, mode)
    if mode in PUBLIC_RENDER_MODES:
        visible_claims = public_claims(doc)
    else:
        visible_claims = _claims(doc)
    output_claim_ids = _output_claim_ids(doc, mode)
    claims = [claim for claim in visible_claims if not output_claim_ids or str(claim.get("id")) in output_claim_ids]
    rendered_claim_ids = {str(claim.get("id")) for claim in claims if claim.get("id")}
    works = _items_for_claims(_works(doc), rendered_claim_ids)
    relations = _items_for_claims(_relations(doc), rendered_claim_ids)

    standing = doc.get("standing", {})
    if not isinstance(standing, dict):
        standing = {}
    artifacts = doc.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
    mandate = doc.get("mandate", {})
    mandate_description = str(mandate.get("description", "")) if isinstance(mandate, dict) else str(mandate or "")
    acceptance_gates = output.get("acceptance_gates", [])
    if not isinstance(acceptance_gates, list):
        acceptance_gates = []

    lines = [
        f"# {title}: {subject_name}",
        "",
        f"Mode: {mode}",
        "Outward action: locked; this renderer stages a draft only.",
    ]
    if export:
        lines.append("Export mode: approved dry run only; no publication or delivery occurs.")
    lines.extend(
        [
            "",
            "## Subject Summary",
            "",
            f"- Subject: {subject_name} ({subject.get('type', 'unknown')}).",
            f"- Roles: {_comma_list(subject.get('roles', []))}.",
            f"- Standing: {standing.get('current', 'unknown')} -> {standing.get('next', 'unknown')}.",
            f"- Mandate: {_sentence(mandate_description)}",
            f"- Next reviewable output: {_sentence(artifacts.get('next_reviewable_output'))}",
            "",
            "## Acceptance Gates",
            "",
        ]
    )
    if acceptance_gates:
        lines.extend(f"- {gate}" for gate in acceptance_gates)
    else:
        lines.append("- No acceptance gates declared.")

    _append_bullet_section(
        lines,
        "Works",
        [_work_line(work) for work in works],
        "No mode-scoped works declared.",
    )
    _append_bullet_section(
        lines,
        "Relations",
        [_relation_line(relation) for relation in relations],
        "No mode-scoped relations declared.",
    )

    lines.extend(
        [
            "",
            "## Claims",
            "",
        ]
    )
    if claims:
        lines.extend(_claim_line(claim) for claim in claims)
    else:
        lines.append("- No approved public claims available.")

    if mode == "canon_dossier":
        _append_bullet_section(
            lines,
            "Authority Program",
            _authority_dossier_rows(doc),
            "No authority program rows are available.",
        )
    if mode == "public_presence_draft":
        _append_bullet_section(
            lines,
            "Public Presence Draft Copy",
            _authority_public_presence_rows(doc),
            "No public presence rows are available.",
        )
    if mode == "authority_scorecard":
        _append_bullet_section(
            lines,
            "Authority Scorecard",
            _authority_scorecard_rows(doc),
            "No authority scorecard rows are available.",
        )

    subject_type = str(subject.get("type", ""))
    if mode == "writer_submission" and subject_type in {"person", "creator"}:
        _append_bullet_section(
            lines,
            "Submission Readiness",
            _submission_readiness_rows(doc, claims),
            "No submission readiness rows are available.",
        )
    if mode == "public_page_draft":
        _append_bullet_section(
            lines,
            "Public Page Draft Copy",
            _public_page_draft_rows(subject_name, claims),
            "No public draft rows are available.",
        )

    _append_bullet_section(
        lines,
        "Source Appendix Summary",
        _source_rows(doc, rendered_claim_ids, mode),
        "No sources are renderable for this mode.",
    )
    _append_bullet_section(
        lines,
        "Approvals Required",
        _approval_rows(doc, mode, rendered_claim_ids),
        "No additional approval records are declared for this mode.",
    )
    lines.extend(
        [
            "",
            "## No-Outward-Action Notice",
            "",
            "This packet is review-only. It does not submit, publish, contact, mine private messages, or act outward.",
        ]
    )

    if mode in {"writer_submission", "market_fit"}:
        lines.extend(
            [
                "",
                "## Submission Gate",
                "",
                "No submission, outreach, or form action is performed by this renderer.",
            ]
        )
    elif mode in {"collaboration_packet", "project_page", "co_branded_page"}:
        lines.extend(
            [
                "",
                "## Collaboration Gate",
                "",
                "No collaborator-facing page or co-branded surface is published without approval.",
            ]
        )
    elif mode in AUTHORITY_MODES:
        lines.extend(
            [
                "",
                "## Authority Gate",
                "",
                "No canon, readership, institution, press, publication, upload, or outreach status is claimed or acted on by this renderer.",
            ]
        )

    lines.extend(
        [
            "",
            "## Privacy",
            "",
            "No raw private messages, contact data, or creative text are rendered.",
        ]
    )
    return "\n".join(lines) + "\n"


def packet_record(doc: dict[str, Any], mode: str, export: bool = False) -> str:
    """Generate a reviewable packet for one of the packet-facing modes."""
    if mode not in PACKET_MODES:
        raise ValueError(f"mode does not have a packet command: {mode}")
    return render_record(doc, mode, export=export)


def _authority_claim_ids(doc: dict[str, Any]) -> set[str]:
    claim_ids: set[str] = set()
    for mode in AUTHORITY_MODES:
        claim_ids.update(_output_claim_ids(doc, mode))
    for axis in _authority_axes(doc).values():
        claim_ids.update(_axis_claim_ids(axis))
    return claim_ids


def _authority_packet_blocker_rows(doc: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for evaluation in authority_axis_evaluations(doc):
        axis = str(evaluation["axis"])
        status = str(evaluation["status"])
        blockers = [str(item) for item in evaluation["blockers"]]
        gates = [str(item) for item in evaluation["gates"]]
        if status == "PUBLIC_READY" and not blockers and not gates:
            continue
        details = blockers + gates
        if details:
            rows.append(f"- {axis}: {status}; {'; '.join(details)}.")
        else:
            rows.append(f"- {axis}: {status}.")
    if not rows:
        rows.append("- none")
    rows.append("- Achieved civilizational status is not claimed; the packet stages authority-building evidence only.")
    return rows


def render_authority_packet(doc: dict[str, Any]) -> str:
    """Render the combined no-outward-action authority packet."""
    for mode in ("canon_dossier", "public_presence_draft", "authority_scorecard"):
        if mode not in _output_modes(doc):
            raise ValueError(f"record does not declare output mode: {mode}")

    subject = doc.get("subject", {})
    if not isinstance(subject, dict):
        subject = {}
    subject_name = str(subject.get("name") or doc.get("name") or "Unnamed subject")
    authority_claim_ids = _authority_claim_ids(doc)

    lines = [
        f"# Authority Packet: {subject_name}",
        "",
        "Mode: authority_packet",
        f"Goal: {AUTHORITY_GOAL}",
        "Outward action: locked; this packet stages review artifacts only.",
        "Civilizational status: not claimed or achieved.",
        "",
        "## Packet Contents",
        "",
        "- Canon dossier artifact",
        "- Public presence draft artifact",
        "- Authority scorecard artifact",
        "- Blockers, source appendix, and approvals required",
        "",
        "## Canon Dossier Artifact",
        "",
        render_record(doc, "canon_dossier").rstrip(),
        "",
        "## Public Presence Draft Artifact",
        "",
        render_record(doc, "public_presence_draft").rstrip(),
        "",
        "## Authority Scorecard Artifact",
        "",
        render_record(doc, "authority_scorecard").rstrip(),
    ]

    _append_bullet_section(
        lines,
        "Packet Blockers",
        _authority_packet_blocker_rows(doc),
        "No authority blockers are currently detected.",
    )
    _append_bullet_section(
        lines,
        "Packet Source Appendix",
        _source_rows(doc, authority_claim_ids, "canon_dossier"),
        "No authority sources are renderable for this packet.",
    )
    _append_bullet_section(
        lines,
        "Packet Approvals Required",
        _approval_rows(doc, "public_presence_draft", authority_claim_ids),
        "No authority approval rows are declared.",
    )
    lines.extend(
        [
            "",
            "## No-Outward-Action Gate",
            "",
            "This authority packet is review-only. It does not submit, publish, upload, contact, mine private material, or act outward.",
            "It does not store raw manuscript text, private messages, contact data, generated art as source work, or fabricated status claims.",
        ]
    )
    return "\n".join(lines) + "\n"


def _literary_writer_claims(writer_doc: dict[str, Any]) -> list[dict[str, Any]]:
    output_claim_ids = _output_claim_ids(writer_doc, "writer_submission")
    return [
        claim for claim in public_claims(writer_doc) if not output_claim_ids or str(claim.get("id")) in output_claim_ids
    ]


def _literary_opportunity_claims(opportunity_doc: dict[str, Any]) -> list[dict[str, Any]]:
    output_claim_ids = _output_claim_ids(opportunity_doc, "market_fit") or _output_claim_ids(
        opportunity_doc, "writer_submission"
    )
    return [
        claim for claim in _claims(opportunity_doc) if not output_claim_ids or str(claim.get("id")) in output_claim_ids
    ]


def _route_ai_policy_sourced(route: dict[str, Any], opportunity_doc: dict[str, Any]) -> bool:
    sources = _source_by_id(opportunity_doc)
    refs = route.get("ai_policy_source_ids", [])
    return isinstance(refs, list) and bool(refs) and all(str(ref) in sources for ref in refs)


def _ai_policy_status_unresolved(value: Any) -> bool:
    if _missing(value):
        return True
    normalized = str(value).strip().lower().replace("_", " ").replace("-", " ")
    return any(
        phrase in normalized
        for phrase in (
            "unresolved",
            "unsourced",
            "not sourced",
            "unknown",
            "not declared",
            "pending research",
        )
    )


def _route_is_venue_specific(route: dict[str, Any]) -> bool:
    route_type = str(route.get("route_type", "")).strip().lower().replace("-", "_")
    return route_type == "venue" or not _missing(route.get("venue"))


def _literary_approval_rows(writer_doc: dict[str, Any], opportunity_doc: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for label, doc in (("Writer", writer_doc), ("Opportunity", opportunity_doc)):
        submission_approvals = [
            approval for approval in _approvals(doc) if str(approval.get("approval_type")) == "submission"
        ]
        if submission_approvals:
            for approval in submission_approvals:
                rows.append(f"- {label} {_approval_line(approval).removeprefix('- ')}")
        else:
            rows.append(f"- {label} submission approval: not_recorded. Required before any send.")
    return rows


def render_literary_packet(
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
    export: bool = False,
) -> str:
    """Render the no-send literary desk packet that combines writer, market, work, and route."""
    if export and (
        not _approved_export(writer_doc, "writer_submission")
        or not _approved_export(opportunity_doc, "writer_submission")
    ):
        raise ValueError("export is locked until matching writer and opportunity submission approvals are recorded")

    writer_subject = writer_doc.get("subject", {})
    opportunity_subject = opportunity_doc.get("subject", {})
    if not isinstance(writer_subject, dict):
        writer_subject = {}
    if not isinstance(opportunity_subject, dict):
        opportunity_subject = {}

    writer_name = str(writer_subject.get("name") or writer_doc.get("name") or "Unnamed writer")
    opportunity_id = str(opportunity_doc.get("id") or "unknown-opportunity")
    candidate = _candidate_by_id(writer_doc, candidate_id)
    route = _route_by_selector(opportunity_doc, route_selector)
    writer_claims = _literary_writer_claims(writer_doc)
    opportunity_claims = _literary_opportunity_claims(opportunity_doc)

    matched: list[str] = []
    missing: list[str] = []
    blockers: list[str] = []

    if writer_claims:
        matched.append("Writer public/profile evidence is available.")
    else:
        missing.append("Writer public/profile evidence")
        blockers.append("Writer profile evidence is missing or not public-approved.")

    if candidate is None:
        missing.extend(CANDIDATE_REVIEW_FIELDS.values())
        blockers.append(f"Candidate work metadata is missing for {candidate_id!r}.")
        candidate = {"id": candidate_id}
    else:
        candidate_missing = _missing_field_labels(candidate, CANDIDATE_REVIEW_FIELDS)
        missing.extend(f"Candidate {field}" for field in candidate_missing)
        if candidate_missing:
            blockers.append("Candidate work metadata is incomplete: " + ", ".join(candidate_missing) + ".")
        else:
            matched.append("Candidate work metadata is complete enough for venue fit review.")

    if route is None:
        missing.extend(ROUTE_REVIEW_FIELDS.values())
        blockers.append(f"Selected venue/route metadata is missing for {route_selector!r}.")
        route = {"id": route_selector}
    else:
        route_missing = _missing_field_labels(route, ROUTE_REVIEW_FIELDS)
        missing.extend(f"Route {field}" for field in route_missing)
        if not _missing(route.get("guidelines_url")):
            matched.append("Guidelines URL is recorded.")
        else:
            blockers.append("Guidelines URL is missing for the selected venue/route.")

    ai_policy_sourced = _route_ai_policy_sourced(route, opportunity_doc)
    ai_policy_status_unresolved = _ai_policy_status_unresolved(route.get("ai_policy_disclosure_status"))
    venue_label = "Venue" if _route_is_venue_specific(route) else "Route"
    if ai_policy_sourced and not ai_policy_status_unresolved:
        matched.append("AI policy/disclosure source is recorded for the selected venue/route.")
        ai_policy_status = _display_value(route.get("ai_policy_disclosure_status"))
    else:
        ai_policy_status = "unresolved"
        if not ai_policy_sourced:
            missing.append("Route AI policy/disclosure source")
            blockers.append(f"{venue_label} AI policy/disclosure source is unresolved.")
        else:
            missing.append("Route AI policy/disclosure status")
            blockers.append(f"{venue_label} AI policy/disclosure status is unresolved.")

    if opportunity_claims:
        matched.append("Opportunity market context is available.")
    else:
        missing.append("Opportunity market context")

    status = "BLOCKED" if blockers else "READY_FOR_REVIEW"
    title = str(candidate.get("title") or candidate.get("id") or "candidate work")
    route_name = str(route.get("venue") or route.get("platform") or route.get("id") or route_selector)

    lines = [
        f"# Literary Desk Packet: {writer_name}",
        "",
        "Mode: literary_submission_desk",
        f"Writer record: {writer_doc.get('id', 'unknown-writer')}",
        f"Opportunity record: {opportunity_id}",
        f"Candidate work/profile: {candidate.get('id', candidate_id)}",
        f"Selected venue/route: {route.get('id', route_selector)}",
        "Outward action: locked; this renderer stages a no-send desk packet only.",
        f"Desk status: {status}",
        "",
        "## Writer Profile Evidence",
        "",
    ]
    if writer_claims:
        lines.extend(_claim_line(claim) for claim in writer_claims)
    else:
        lines.append("- No public/profile claims are renderable for this writer.")

    lines.extend(["", "## Candidate Work Metadata", ""])
    lines.append(f"- Title/profile: {_display_value(title)}.")
    for field, label in CANDIDATE_REVIEW_FIELDS.items():
        lines.append(f"- {label}: {_display_value(candidate.get(field))}.")
    source_ids = candidate.get("source_ids", [])
    lines.append(f"- Source refs: {_display_value(source_ids)}.")

    lines.extend(["", "## Venue / Route Metadata", ""])
    lines.append(f"- Route name: {_display_value(route_name)}.")
    for field, label in ROUTE_REVIEW_FIELDS.items():
        if field == "ai_policy_disclosure_status":
            lines.append(f"- {label}: {ai_policy_status}.")
        else:
            lines.append(f"- {label}: {_display_value(route.get(field))}.")
    lines.append(f"- Guidelines source refs: {_display_value(route.get('guidelines_source_ids', []))}.")
    lines.append(f"- AI policy/disclosure: {ai_policy_status}.")

    lines.extend(["", "## Opportunity Context", ""])
    if opportunity_claims:
        lines.extend(_claim_line(claim) for claim in opportunity_claims)
    else:
        lines.append("- No opportunity claims are available.")

    lines.extend(["", "## Fit Check", "", "### Matched Fields", ""])
    if matched:
        lines.extend(f"- {row}" for row in matched)
    else:
        lines.append("- none")
    lines.extend(["", "### Missing Fields", ""])
    if missing:
        lines.extend(f"- {row}" for row in missing)
    else:
        lines.append("- none")
    lines.extend(["", "### Blockers", ""])
    if blockers:
        lines.extend(f"- {row}" for row in blockers)
    else:
        lines.append("- none")

    _append_bullet_section(
        lines,
        "Approvals Required",
        _literary_approval_rows(writer_doc, opportunity_doc),
        "Submission approval records are missing.",
    )
    lines.extend(
        [
            "",
            "## No-Send Notice",
            "",
            "No submission, outreach, upload, publication, contact, or form action is performed by this packet.",
            "No raw private messages, contact data, or creative manuscript text are rendered.",
        ]
    )
    return "\n".join(lines) + "\n"


def _candidate_publication_status(
    writer_doc: dict[str, Any], candidate: dict[str, Any] | None, candidate_id: str
) -> tuple[str, list[str], list[str]]:
    matched: list[str] = []
    blockers: list[str] = []
    if candidate is None:
        blockers.append(f"Candidate work metadata is missing for {candidate_id!r}.")
        for label in CANDIDATE_READY_REQUIRED_FIELDS.values():
            blockers.append(f"Candidate {label} is missing.")
        blockers.append("Candidate Source refs are missing.")
        blockers.append("Candidate Claim refs are missing.")
        return "BLOCKED", matched, blockers

    missing = _missing_field_labels(candidate, CANDIDATE_READY_REQUIRED_FIELDS)
    for label in missing:
        blockers.append(f"Candidate {label} is missing.")

    source_ids = candidate.get("source_ids", [])
    if not isinstance(source_ids, list) or not source_ids:
        blockers.append("Candidate Source refs are missing.")
    else:
        sources = _source_by_id(writer_doc)
        unknown_sources = [str(source_id) for source_id in source_ids if str(source_id) not in sources]
        if unknown_sources:
            blockers.append("Candidate Source refs are unknown: " + ", ".join(unknown_sources) + ".")
        else:
            matched.append("Candidate source refs are recorded and withheld from public copy.")

    claim_ids = candidate.get("claim_ids", [])
    if not isinstance(claim_ids, list) or not claim_ids:
        blockers.append("Candidate Claim refs are missing.")
    else:
        known_claim_ids = _claim_ids(writer_doc)
        unknown_claims = [str(claim_id) for claim_id in claim_ids if str(claim_id) not in known_claim_ids]
        if unknown_claims:
            blockers.append("Candidate Claim refs are unknown: " + ", ".join(unknown_claims) + ".")

    if blockers:
        return "BLOCKED", matched, blockers

    if not _ready_for_review_status(candidate.get("status")):
        blockers.append(f"Candidate status is {_display_value(candidate.get('status'))}, not {CANDIDATE_READY_STATUS}.")
        return "BLOCKED", matched, blockers

    matched.append("Candidate metadata is complete enough for venue fit review.")
    return CANDIDATE_READY_STATUS, matched, blockers


def _route_guideline_blockers(route: dict[str, Any], opportunity_doc: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    sources = _source_by_id(opportunity_doc)
    guideline_refs = route.get("guidelines_source_ids", [])
    guidelines_url = str(route.get("guidelines_url") or "").strip()
    if not guidelines_url:
        blockers.append("Route Guidelines URL is missing.")
    if not isinstance(guideline_refs, list) or not guideline_refs:
        blockers.append("Route guideline source is missing for the selected route.")
        return blockers

    unknown = [str(source_id) for source_id in guideline_refs if str(source_id) not in sources]
    if unknown:
        blockers.append("Route guideline source refs are unknown: " + ", ".join(unknown) + ".")

    non_public = [
        str(source_id)
        for source_id in guideline_refs
        if str(source_id) in sources and not _source_is_public_web(sources[str(source_id)])
    ]
    if non_public:
        blockers.append("Route guideline source refs must be public web sources: " + ", ".join(non_public) + ".")

    if guidelines_url:
        source_urls = {
            str(sources[str(source_id)].get("source_ref")) for source_id in guideline_refs if str(source_id) in sources
        }
        if guidelines_url not in source_urls:
            blockers.append("Route Guidelines URL does not match the recorded guideline source.")

    return blockers


def _route_publication_status(
    opportunity_doc: dict[str, Any], route: dict[str, Any] | None, route_selector: str
) -> tuple[str, list[str], list[str]]:
    matched: list[str] = []
    blockers: list[str] = []
    if route is None:
        blockers.append(f"Selected venue/route metadata is missing for {route_selector!r}.")
        for label in ROUTE_REVIEW_FIELDS.values():
            blockers.append(f"Route {label} is missing.")
        return "BLOCKED", matched, blockers

    missing = _missing_field_labels(route, ROUTE_REVIEW_FIELDS)
    for label in missing:
        blockers.append(f"Route {label} is missing.")

    guideline_blockers = _route_guideline_blockers(route, opportunity_doc)
    blockers.extend(guideline_blockers)
    if not guideline_blockers:
        matched.append("Route guideline source is public, recorded, and matched to the guidelines URL.")

    ai_policy_sourced = _route_ai_policy_sourced(route, opportunity_doc)
    ai_policy_unresolved = _ai_policy_status_unresolved(route.get("ai_policy_disclosure_status"))
    if not ai_policy_sourced:
        blockers.append("Route AI policy/disclosure source is unresolved.")
    elif ai_policy_unresolved:
        blockers.append("Route AI policy/disclosure status is unresolved.")
    else:
        matched.append("Route AI policy/disclosure status is sourced and resolved.")

    return ("BLOCKED" if blockers else CANDIDATE_READY_STATUS), matched, blockers


def _approval_matches_publication_requirement(
    approval: dict[str, Any],
    *,
    approval_type: str,
    target: str,
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
) -> bool:
    if str(approval.get("approval_type")) != approval_type:
        return False
    if str(approval.get("status")) != "approved":
        return False
    if not _approval_is_dry_run(approval):
        return False

    approval_target = str(approval.get("approval_target") or target)
    if approval_target != target:
        return False

    subject_id = str(writer_doc.get("id") or "")
    if not _missing(approval.get("subject_id")) and str(approval.get("subject_id")) != subject_id:
        return False
    if not _missing(approval.get("candidate_id")) and str(approval.get("candidate_id")) != candidate_id:
        return False
    if not _missing(approval.get("route_id")) and str(approval.get("route_id")) != route_selector:
        return False
    if target == "opportunity_route_submission":
        opportunity_id = str(opportunity_doc.get("id") or "")
        if not _missing(approval.get("opportunity_id")) and str(approval.get("opportunity_id")) != opportunity_id:
            return False
    return True


def _matching_publication_approval(
    approvals: list[dict[str, Any]],
    *,
    approval_type: str,
    target: str,
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
) -> dict[str, Any] | None:
    for approval in approvals:
        if _approval_matches_publication_requirement(
            approval,
            approval_type=approval_type,
            target=target,
            writer_doc=writer_doc,
            opportunity_doc=opportunity_doc,
            candidate_id=candidate_id,
            route_selector=route_selector,
        ):
            return approval
    return None


def _publication_approval_status(
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
    approval_doc: dict[str, Any] | None = None,
) -> tuple[bool, list[str], list[str]]:
    matched: list[str] = []
    blockers: list[str] = []
    requirements = (
        ("Writer public export", writer_doc, "public_export", "writer_public_export"),
        ("Writer submission", writer_doc, "submission", "writer_submission"),
        ("Opportunity route submission", opportunity_doc, "submission", "opportunity_route_submission"),
    )
    extra_approvals = _approvals(approval_doc) if approval_doc else []
    for label, doc, approval_type, target in requirements:
        approval = _matching_publication_approval(
            [*_approvals(doc), *extra_approvals],
            approval_type=approval_type,
            target=target,
            writer_doc=writer_doc,
            opportunity_doc=opportunity_doc,
            candidate_id=candidate_id,
            route_selector=route_selector,
        )
        if approval:
            matched.append(f"{label} approval is APPROVED_DRY_RUN via {approval.get('id', 'approval-record')}.")
        else:
            status = _approval_status(doc, approval_type)
            if extra_approvals:
                status = f"{status}; no matching dry-run approval record"
            blockers.append(f"{label} approval is {status}.")
    return not blockers, matched, blockers


def _approval_matches_real_send_requirement(
    approval: dict[str, Any],
    *,
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
) -> bool:
    if not _approval_is_real_send_approval(approval):
        return False
    if approval.get("real_send_approval") is not True:
        return False
    subject_id = str(writer_doc.get("id") or "")
    opportunity_id = str(opportunity_doc.get("id") or "")
    if str(approval.get("subject_id") or "") != subject_id:
        return False
    if str(approval.get("opportunity_id") or "") != opportunity_id:
        return False
    if str(approval.get("candidate_id") or "") != candidate_id:
        return False
    if str(approval.get("route_id") or "") != route_selector:
        return False
    return True


def _matching_real_send_approval(
    approvals: list[dict[str, Any]],
    *,
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
) -> dict[str, Any] | None:
    for approval in approvals:
        if _approval_matches_real_send_requirement(
            approval,
            writer_doc=writer_doc,
            opportunity_doc=opportunity_doc,
            candidate_id=candidate_id,
            route_selector=route_selector,
        ):
            return approval
    return None


def _real_send_status(
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
    approval_doc: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None, list[str]]:
    approvals = [*_approvals(writer_doc), *_approvals(opportunity_doc)]
    if approval_doc:
        approvals.extend(_approvals(approval_doc))
    approval = _matching_real_send_approval(
        approvals,
        writer_doc=writer_doc,
        opportunity_doc=opportunity_doc,
        candidate_id=candidate_id,
        route_selector=route_selector,
    )
    if approval:
        return (
            "APPROVED_REAL_SEND",
            approval,
            [f"Real send approval is APPROVED_REAL_SEND via {approval.get('id', 'approval-record')}."],
        )
    return "LOCKED", None, []


def _readiness_value_recorded(value: Any) -> str:
    return "recorded and withheld" if not _missing(value) else "missing"


def _publication_output_rows(
    *,
    candidate_ready: bool,
    route_ready: bool,
    ai_ready: bool,
    approvals_ready: bool,
    rights_ready: bool,
) -> list[str]:
    fit_status = CANDIDATE_READY_STATUS if candidate_ready and route_ready else "BLOCKED"
    disclosure_status = CANDIDATE_READY_STATUS if ai_ready else "BLOCKED"
    rights_status = CANDIDATE_READY_STATUS if rights_ready else "BLOCKED"
    submission_status = "APPROVED_DRY_RUN" if approvals_ready else "LOCKED"
    return [
        f"- Fit report: {fit_status}.",
        "- Cover letter options: GATED until Chris reviews voice and purpose.",
        f"- AI-process disclosure note: {disclosure_status}.",
        f"- Rights checklist: {rights_status}.",
        f"- Submission checklist: {submission_status}.",
    ]


def render_publication_readiness(
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
    export: bool = False,
    approval_doc: dict[str, Any] | None = None,
) -> str:
    """Render a Chris-facing publication readiness report without exposing private refs."""
    if approval_doc is not None:
        approval_label = str(approval_doc.get("id") or "approval-record")
        approval_violations = validate_doc(approval_doc, approval_label)
        if approval_violations:
            raise ValueError("approval record invalid: " + "; ".join(approval_violations[:6]))

    writer_subject = writer_doc.get("subject", {})
    if not isinstance(writer_subject, dict):
        writer_subject = {}
    writer_name = str(writer_subject.get("name") or writer_doc.get("name") or "Unnamed writer")
    candidate = _candidate_by_id(writer_doc, candidate_id)
    route = _route_by_selector(opportunity_doc, route_selector)

    candidate_status, candidate_matched, candidate_blockers = _candidate_publication_status(
        writer_doc, candidate, candidate_id
    )
    route_status, route_matched, route_blockers = _route_publication_status(opportunity_doc, route, route_selector)
    approvals_ready, approval_matched, approval_blockers = _publication_approval_status(
        writer_doc,
        opportunity_doc,
        candidate_id,
        route_selector,
        approval_doc=approval_doc,
    )
    real_send_state, _, real_send_matched = _real_send_status(
        writer_doc,
        opportunity_doc,
        candidate_id,
        route_selector,
        approval_doc,
    )
    if export and not approvals_ready:
        raise ValueError(
            "publication readiness export is locked until writer public_export, "
            "writer submission, and opportunity submission approvals are approved"
        )

    blockers = candidate_blockers + route_blockers + approval_blockers
    matched = candidate_matched + route_matched + approval_matched + real_send_matched
    publication_status = "BLOCKED" if blockers else CANDIDATE_READY_STATUS
    route_ready = route_status == CANDIDATE_READY_STATUS
    candidate_ready = candidate_status == CANDIDATE_READY_STATUS
    ai_ready = bool(
        route is not None
        and _route_ai_policy_sourced(route, opportunity_doc)
        and not _ai_policy_status_unresolved(route.get("ai_policy_disclosure_status"))
    )
    rights_ready = bool(candidate is not None and not _missing(candidate.get("rights_status")))

    route_name = "missing"
    if route is not None:
        route_name = str(route.get("venue") or route.get("platform") or route.get("id") or route_selector)
    candidate_title = "missing"
    if candidate is not None:
        candidate_title = str(candidate.get("title") or candidate.get("id") or candidate_id)

    lines = [
        f"# Publication Readiness Packet: {writer_name}",
        "",
        "Mode: publication_readiness",
        f"Writer record: {writer_doc.get('id', 'unknown-writer')}",
        f"Opportunity record: {opportunity_doc.get('id', 'unknown-opportunity')}",
        f"Approval record: {approval_doc.get('id', 'not supplied') if approval_doc else 'not supplied'}",
        f"Candidate: {candidate_id}",
        f"Selected venue/route: {route_selector}",
        "Outward action: staged; this readiness command does not submit, upload, publish, contact, or impersonate.",
    ]
    if export:
        lines.append("Export mode: approved dry run only; no publication or delivery occurs.")
    lines.extend(
        [
            f"Publication readiness: {publication_status}",
            f"Candidate status: {candidate_status}",
            f"Route status: {route_status}",
            f"Dry-run export: {'APPROVED_DRY_RUN' if approvals_ready else 'LOCKED'}",
            f"Real submission: {real_send_state}; execution uses publication-send.",
            "",
            "## What This Is",
            "",
            "- A source-backed readiness packet for matching one metadata-only candidate work to one venue route.",
            "- It renders fit, cover-letter, disclosure, rights, and submission-checklist readiness without sending anything.",
            "- It is not a public announcement, submission receipt, publication claim, or editor contact.",
            "",
            "## What Works Now",
            "",
        ]
    )
    if matched:
        lines.extend(f"- {row}" for row in matched)
    else:
        lines.append("- No ready publication workstream fields are proven yet.")

    lines.extend(["", "## Still Gated", ""])
    if blockers:
        lines.extend(f"- {row}" for row in blockers)
    else:
        lines.append("- No readiness blockers remain for an approved dry-run packet.")
    if real_send_state == "APPROVED_REAL_SEND":
        lines.append(
            "- Real submission approval is recorded; publication-send must still produce the execution receipt."
        )
    else:
        lines.append(
            "- Real submission requires an approved real_send approval record before publication-send can execute."
        )

    lines.extend(["", "## Candidate Metadata", ""])
    lines.append(f"- Title/profile: {_display_value(candidate_title)}.")
    if candidate is None:
        for label in CANDIDATE_READY_REQUIRED_FIELDS.values():
            lines.append(f"- {label}: missing.")
        lines.append("- Source refs: missing.")
        lines.append("- Claim refs: missing.")
    else:
        for field, label in CANDIDATE_READY_REQUIRED_FIELDS.items():
            if field == "content_ref":
                lines.append(f"- {label}: {_readiness_value_recorded(candidate.get(field))}.")
            else:
                lines.append(f"- {label}: {_display_value(candidate.get(field))}.")
        lines.append(f"- Source refs: {_readiness_value_recorded(candidate.get('source_ids'))}.")
        lines.append(f"- Claim refs: {_readiness_value_recorded(candidate.get('claim_ids'))}.")

    lines.extend(["", "## Venue Route Facts", ""])
    lines.append(f"- Route name: {_display_value(route_name)}.")
    if route is None:
        for label in ROUTE_REVIEW_FIELDS.values():
            lines.append(f"- {label}: missing.")
        lines.append("- Guidelines source refs: missing.")
    else:
        for field, label in ROUTE_REVIEW_FIELDS.items():
            if field == "ai_policy_disclosure_status" and not ai_ready:
                lines.append(f"- {label}: unresolved.")
            else:
                lines.append(f"- {label}: {_display_value(route.get(field))}.")
        lines.append(f"- Guidelines source refs: {_readiness_value_recorded(route.get('guidelines_source_ids'))}.")
        lines.append(f"- AI policy source refs: {_readiness_value_recorded(route.get('ai_policy_source_ids'))}.")

    _append_bullet_section(
        lines,
        "Generated Packet Outputs",
        _publication_output_rows(
            candidate_ready=candidate_ready,
            route_ready=route_ready,
            ai_ready=ai_ready,
            approvals_ready=approvals_ready,
            rights_ready=rights_ready,
        ),
        "No packet output rows are available.",
    )
    lines.extend(
        [
            "",
            "## Privacy, Voice, And Control",
            "",
            "- Manuscript content is not stored or rendered; only metadata and the presence of a private content ref are checked.",
            "- Private source refs, local paths, message refs, and contact data are withheld from this packet.",
            "- Chris controls voice review, public export, submission approval, outreach approval, and any actual send.",
            "- The packet does not claim acceptance, publication, editor interest, or achieved literary status.",
            "",
            "## Readiness Command Boundary",
            "",
            "This readiness command performs no submission, outreach, upload, publication, contact, form action, or public-presence export.",
        ]
    )
    return "\n".join(lines) + "\n"


def _publication_stack_status_rows(
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
    approval_doc: dict[str, Any] | None,
) -> tuple[dict[str, str], list[str], list[str]]:
    candidate = _candidate_by_id(writer_doc, candidate_id)
    route = _route_by_selector(opportunity_doc, route_selector)
    candidate_status, candidate_matched, candidate_blockers = _candidate_publication_status(
        writer_doc, candidate, candidate_id
    )
    route_status, route_matched, route_blockers = _route_publication_status(opportunity_doc, route, route_selector)
    approvals_ready, approval_matched, approval_blockers = _publication_approval_status(
        writer_doc,
        opportunity_doc,
        candidate_id,
        route_selector,
        approval_doc=approval_doc,
    )
    real_send_state, _, real_send_matched = _real_send_status(
        writer_doc,
        opportunity_doc,
        candidate_id,
        route_selector,
        approval_doc,
    )
    status = {
        "candidate": candidate_status,
        "route": route_status,
        "dry_run": "APPROVED_DRY_RUN" if approvals_ready else "LOCKED",
        "real_send": real_send_state,
    }
    return (
        status,
        candidate_matched + route_matched + approval_matched + real_send_matched,
        (candidate_blockers + route_blockers + approval_blockers),
    )


def _route_display_name(route: dict[str, Any] | None, fallback: str) -> str:
    if route is None:
        return fallback
    return str(route.get("venue") or route.get("platform") or route.get("id") or fallback)


def _public_writer_bio_rows(writer_doc: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for claim in _literary_writer_claims(writer_doc):
        rows.append(_claim_line(claim))
    return rows or ["- No public writer claims are renderable."]


def render_publication_stack_files(
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
    approval_doc: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build publication stack files; real sends execute through publication-send."""
    if approval_doc is not None:
        approval_label = str(approval_doc.get("id") or "approval-record")
        approval_violations = validate_doc(approval_doc, approval_label)
        if approval_violations:
            raise ValueError("approval record invalid: " + "; ".join(approval_violations[:6]))

    writer_subject = writer_doc.get("subject", {})
    if not isinstance(writer_subject, dict):
        writer_subject = {}
    writer_name = str(writer_subject.get("name") or writer_doc.get("name") or "Unnamed writer")
    candidate = _candidate_by_id(writer_doc, candidate_id)
    route = _route_by_selector(opportunity_doc, route_selector)
    route_name = _route_display_name(route, route_selector)
    candidate_title = str(candidate.get("title") if candidate else candidate_id)
    status, matched, blockers = _publication_stack_status_rows(
        writer_doc,
        opportunity_doc,
        candidate_id,
        route_selector,
        approval_doc,
    )
    has_dry_run_approval = status["dry_run"] == "APPROVED_DRY_RUN"
    readiness = render_publication_readiness(
        writer_doc,
        opportunity_doc,
        candidate_id=candidate_id,
        route_selector=route_selector,
        export=has_dry_run_approval,
        approval_doc=approval_doc,
    )
    public_presence = render_record(writer_doc, "public_presence_draft")
    matched_rows = [f"- {row}" for row in matched] or ["- none"]
    blocker_rows = [f"- {row}" for row in blockers] or ["- No readiness blockers remain for a dry-run review packet."]

    header = [
        f"# {writer_name} / {route_name} Review Packet",
        "",
        "Outward action: staged. These files are review drafts; real send uses publication-send.",
        f"Candidate metadata: {status['candidate']}.",
        f"Route metadata: {status['route']}.",
        f"Dry-run approval: {status['dry_run']}.",
        f"Real send: {status['real_send']}.",
        "No publication, submission, upload, contact, form action, or public export has happened.",
        "",
    ]

    readme = "\n".join(
        [
            *header,
            "## Files",
            "",
            "- fit-report.md",
            "- cover-letter-options.md",
            "- ai-disclosure-note.md",
            "- rights-checklist.md",
            "- submission-checklist.md",
            "- public-presence-copy-preview.md",
            "",
            "## Review Gates",
            "",
            "- Chris public export approval remains locked until explicit approval is supplied.",
            "- Chris submission approval remains locked until explicit approval is supplied.",
            "- Opportunity/route submission approval remains locked until explicit approval is supplied.",
            "- Real-send approval requires an approved real_send record before publication-send can execute.",
            "",
        ]
    )

    fit_report = "\n".join(
        [
            "# Fit Report",
            "",
            *header[2:],
            "## Matched",
            "",
            *matched_rows,
            "",
            "## Still Gated",
            "",
            *blocker_rows,
            "",
            "## Readiness Packet",
            "",
            readiness.rstrip(),
            "",
        ]
    )

    cover_letter = "\n".join(
        [
            "# Cover Letter Draft Options",
            "",
            *header[2:],
            "## Option A",
            "",
            "Dear Editors,",
            "",
            f"Please consider {candidate_title} for {route_name}. This draft is staged for Chris's voice review and has not been sent.",
            "",
            "## Option B",
            "",
            "Dear Editors,",
            "",
            f"I am sending a nonfiction essay for consideration by {route_name}. Final wording, biography, and any disclosure language remain locked pending Chris approval.",
            "",
            "## Public Bio Source Points",
            "",
            *_public_writer_bio_rows(writer_doc),
            "",
        ]
    )

    ai_note = "\n".join(
        [
            "# AI Disclosure Note",
            "",
            *header[2:],
            "## Draft Disclosure Surface",
            "",
            "- The route's AI policy/disclosure posture is sourced and resolved for review.",
            "- Final disclosure wording must be approved by Chris before any use.",
            "- This stack was generated as review scaffolding and does not assert that the candidate work contains AI-generated language.",
            "- Disclosure delivery has not occurred.",
            "",
        ]
    )

    rights_status = _display_value(candidate.get("rights_status")) if candidate else "missing"
    rights_checklist = "\n".join(
        [
            "# Rights Checklist",
            "",
            *header[2:],
            "## Rights Fields",
            "",
            f"- Candidate: {_display_value(candidate_title)}.",
            f"- Rights status: {rights_status}.",
            "- Content/source ref: recorded and withheld.",
            "- Manuscript text: not stored or rendered.",
            "- Chris must confirm final rights and prior-submission history before any send.",
            "",
        ]
    )

    submission_checklist = "\n".join(
        [
            "# Submission Checklist",
            "",
            *header[2:],
            "## Locks",
            "",
            "- Chris public export approval: LOCKED unless a matching dry-run approval record is supplied.",
            "- Chris submission approval: LOCKED unless a matching dry-run approval record is supplied.",
            "- Opportunity/route submission approval: LOCKED unless a matching dry-run approval record is supplied.",
            "- Real send: LOCKED unless a matching real_send approval record is supplied.",
            "",
            "## Before Publication Send",
            "",
            "- Chris reviews candidate, cover letter, disclosure, rights, and venue fit.",
            "- Public export, writer submission, route submission, and real_send approvals are recorded.",
            "- Run publication-send with the approval record and preserve its execution receipt.",
            "",
        ]
    )

    public_preview = "\n".join(
        [
            "# Public Presence Copy Preview",
            "",
            *header[2:],
            public_presence.rstrip(),
            "",
        ]
    )

    return {
        "README.md": readme,
        "fit-report.md": fit_report,
        "cover-letter-options.md": cover_letter,
        "ai-disclosure-note.md": ai_note,
        "rights-checklist.md": rights_checklist,
        "submission-checklist.md": submission_checklist,
        "public-presence-copy-preview.md": public_preview,
    }


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "publication-send"


def _runtime_value(
    *,
    send_config: dict[str, Any],
    approval: dict[str, Any],
    config_key: str,
    approval_key: str | None = None,
) -> str:
    configured = send_config.get(config_key)
    if not _missing(configured):
        return str(configured)
    return str(approval.get(approval_key or config_key) or "")


def _runtime_env_value(env_name: str, label: str, blockers: list[str]) -> str:
    if _missing(env_name):
        blockers.append(f"REAL_SEND_BLOCKED: {label} env var name is missing.")
        return ""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", env_name):
        blockers.append(f"REAL_SEND_BLOCKED: {label} env var name is invalid.")
        return ""
    value = os.environ.get(env_name)
    if _missing(value):
        blockers.append(f"REAL_SEND_BLOCKED: {label} env var {env_name} is not set.")
        return ""
    return str(value).strip()


def _runtime_email_from_env(env_name: str, label: str, blockers: list[str]) -> str:
    value = _runtime_env_value(env_name, label, blockers)
    if value and not EMAIL_RE.fullmatch(value):
        blockers.append(f"REAL_SEND_BLOCKED: {label} env var does not contain a valid email address.")
        return ""
    return value


def _runtime_text_from_env(env_name: str, label: str, blockers: list[str]) -> str:
    value = _runtime_env_value(env_name, label, blockers)
    if EMAIL_RE.search(value) or PHONE_RE.search(value):
        blockers.append(f"REAL_SEND_BLOCKED: {label} env var contains contact data.")
        return ""
    return value


def _direct_email_subject(
    *,
    approval: dict[str, Any],
    send_config: dict[str, Any],
    writer_name: str,
    candidate_id: str,
    route_name: str,
    blockers: list[str],
) -> str:
    subject_env = _runtime_value(
        send_config=send_config,
        approval=approval,
        config_key="message_subject_env",
    )
    if subject_env:
        subject = _runtime_text_from_env(subject_env, "message subject", blockers)
    else:
        subject = str(approval.get("message_subject") or f"Submission: {candidate_id} for {route_name}")
    subject = subject.strip()
    if not subject:
        blockers.append("REAL_SEND_BLOCKED: direct_email message subject is empty.")
    if "\n" in subject or "\r" in subject:
        blockers.append("REAL_SEND_BLOCKED: direct_email message subject must be one line.")
    if EMAIL_RE.search(subject) or PHONE_RE.search(subject):
        blockers.append("REAL_SEND_BLOCKED: direct_email message subject contains contact data.")
    if len(subject) > 180:
        blockers.append("REAL_SEND_BLOCKED: direct_email message subject is too long.")
    return subject or f"Submission from {writer_name}"


def _direct_email_body(
    *,
    approval: dict[str, Any],
    send_config: dict[str, Any],
    writer_name: str,
    candidate_id: str,
    route_name: str,
    blockers: list[str],
) -> str:
    body_env = _runtime_value(
        send_config=send_config,
        approval=approval,
        config_key="message_body_env",
    )
    if body_env:
        body = _runtime_text_from_env(body_env, "message body", blockers)
    else:
        body = str(
            approval.get("message_body")
            or (
                f"Please consider the referenced submission from {writer_name} for {route_name}.\n\n"
                f"Candidate: {candidate_id}\n"
                "Payload ref: recorded and withheld by the Representation substrate.\n"
            )
        )
    body = body.strip()
    if not body:
        blockers.append("REAL_SEND_BLOCKED: direct_email message body is empty.")
    return body


def _attach_payload_if_present(message: EmailMessage, payload_path: Path, blockers: list[str]) -> bool:
    if not payload_path.exists() or not payload_path.is_file():
        blockers.append("REAL_SEND_BLOCKED: direct_email payload path does not exist or is not a file.")
        return False
    content_type, _ = mimetypes.guess_type(str(payload_path))
    maintype, subtype = (content_type or "application/octet-stream").split("/", 1)
    try:
        data = payload_path.read_bytes()
    except OSError as exc:
        blockers.append(f"REAL_SEND_BLOCKED: direct_email payload could not be read: {exc}")
        return False
    message.add_attachment(data, maintype=maintype, subtype=subtype, filename=payload_path.name)
    return True


def _write_direct_email_outbox_copy(
    outbox_dir: Path, message: EmailMessage, candidate_id: str, route_selector: str
) -> Path:
    outbox_dir.mkdir(parents=True, exist_ok=True)
    path = outbox_dir / f"{_slug(candidate_id)}-{_slug(route_selector)}-direct-email.eml"
    path.write_text(message.as_string(), encoding="utf-8")
    return path


def _execute_direct_email(
    *,
    writer_name: str,
    candidate_id: str,
    route_selector: str,
    route_name: str,
    approval: dict[str, Any],
    send_config: dict[str, Any],
    outbox_dir: Path | None,
) -> tuple[str | None, list[str], list[str]]:
    blockers: list[str] = []
    rows: list[str] = []
    smtp_host = _runtime_value(send_config=send_config, approval=approval, config_key="smtp_host")
    smtp_port_raw = _runtime_value(send_config=send_config, approval=approval, config_key="smtp_port") or "25"
    smtp_timeout_raw = _runtime_value(send_config=send_config, approval=approval, config_key="smtp_timeout") or "15"
    if _missing(smtp_host):
        blockers.append("REAL_SEND_BLOCKED: direct_email delivery adapter requires --smtp-host.")
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        blockers.append("REAL_SEND_BLOCKED: direct_email smtp port must be an integer.")
        smtp_port = 25
    try:
        smtp_timeout = float(smtp_timeout_raw)
    except ValueError:
        blockers.append("REAL_SEND_BLOCKED: direct_email smtp timeout must be numeric.")
        smtp_timeout = 15.0

    recipient_env = _runtime_value(
        send_config=send_config,
        approval=approval,
        config_key="recipient_env",
        approval_key="recipient_address_env",
    )
    sender_env = _runtime_value(
        send_config=send_config,
        approval=approval,
        config_key="sender_env",
        approval_key="sender_address_env",
    )
    recipient = _runtime_email_from_env(recipient_env, "recipient address", blockers)
    sender = _runtime_email_from_env(sender_env, "sender address", blockers)
    subject = _direct_email_subject(
        approval=approval,
        send_config=send_config,
        writer_name=writer_name,
        candidate_id=candidate_id,
        route_name=route_name,
        blockers=blockers,
    )
    body = _direct_email_body(
        approval=approval,
        send_config=send_config,
        writer_name=writer_name,
        candidate_id=candidate_id,
        route_name=route_name,
        blockers=blockers,
    )

    message = EmailMessage()
    if sender:
        message["From"] = sender
    if recipient:
        message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    payload_env = _runtime_value(
        send_config=send_config,
        approval=approval,
        config_key="payload_path_env",
    )
    if payload_env:
        payload_value = _runtime_env_value(payload_env, "payload path", blockers)
        if payload_value:
            if _attach_payload_if_present(message, Path(payload_value), blockers):
                rows.append("Direct email payload attachment: attached from private runtime path.")

    if blockers:
        return None, rows, blockers

    if outbox_dir is not None:
        outbox_copy = _write_direct_email_outbox_copy(outbox_dir, message, candidate_id, route_selector)
        rows.append(f"Direct email outbox copy written: {outbox_copy}")

    use_ssl = bool(send_config.get("smtp_ssl")) or approval.get("smtp_ssl") is True
    use_starttls = bool(send_config.get("smtp_starttls")) or approval.get("smtp_starttls") is True
    user_env = _runtime_value(send_config=send_config, approval=approval, config_key="smtp_user_env")
    password_env = _runtime_value(send_config=send_config, approval=approval, config_key="smtp_password_env")
    username = _runtime_env_value(user_env, "smtp username", blockers) if user_env else ""
    password = _runtime_env_value(password_env, "smtp password", blockers) if password_env else ""
    if bool(username) != bool(password):
        blockers.append("REAL_SEND_BLOCKED: direct_email smtp username/password envs must be supplied together.")
    if blockers:
        return None, rows, blockers

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    try:
        with smtp_cls(smtp_host, smtp_port, timeout=smtp_timeout) as smtp:
            if use_starttls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
    except OSError as exc:
        blockers.append(f"REAL_SEND_BLOCKED: direct_email SMTP delivery failed: {exc}")
        return None, rows, blockers
    except smtplib.SMTPException as exc:
        blockers.append(f"REAL_SEND_BLOCKED: direct_email SMTP delivery failed: {exc}")
        return None, rows, blockers

    rows.append("Direct email SMTP delivery completed.")
    return "SENT_DIRECT_EMAIL", rows, blockers


def _write_local_outbox_receipt(
    outbox_dir: Path,
    *,
    writer_name: str,
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
    route_name: str,
    approval: dict[str, Any],
    timestamp: str,
) -> Path:
    outbox_dir.mkdir(parents=True, exist_ok=True)
    path = outbox_dir / f"{_slug(candidate_id)}-{_slug(route_selector)}-submission-envelope.md"
    path.write_text(
        "\n".join(
            [
                f"# Local Outbox Submission Envelope: {writer_name} / {route_name}",
                "",
                f"Created: {timestamp}",
                f"Writer record: {writer_doc.get('id', 'unknown-writer')}",
                f"Opportunity record: {opportunity_doc.get('id', 'unknown-opportunity')}",
                f"Candidate: {candidate_id}",
                f"Selected venue/route: {route_selector}",
                f"Real-send approval: {approval.get('id', 'approval-record')}",
                f"Delivery adapter: {approval.get('delivery_adapter')}",
                f"Recipient ref: {approval.get('recipient_ref')}",
                "Payload ref: recorded and withheld.",
                "",
                "Status: SENT_TO_LOCAL_OUTBOX",
                "External email, upload, form submission, publication, and editor contact were not performed by the local_outbox adapter.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def render_publication_send_receipt(
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any],
    candidate_id: str,
    route_selector: str,
    approval_doc: dict[str, Any] | None,
    *,
    execute: bool = False,
    outbox_dir: Path | None = None,
    send_config: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    """Render or execute a publication send receipt from explicit real-send approval."""
    if approval_doc is not None:
        approval_label = str(approval_doc.get("id") or "approval-record")
        approval_violations = validate_doc(approval_doc, approval_label)
        if approval_violations:
            raise ValueError("approval record invalid: " + "; ".join(approval_violations[:6]))

    writer_subject = writer_doc.get("subject", {})
    if not isinstance(writer_subject, dict):
        writer_subject = {}
    writer_name = str(writer_subject.get("name") or writer_doc.get("name") or "Unnamed writer")
    candidate = _candidate_by_id(writer_doc, candidate_id)
    route = _route_by_selector(opportunity_doc, route_selector)
    route_name = _route_display_name(route, route_selector)

    candidate_status, candidate_matched, candidate_blockers = _candidate_publication_status(
        writer_doc, candidate, candidate_id
    )
    route_status, route_matched, route_blockers = _route_publication_status(opportunity_doc, route, route_selector)
    approvals_ready, approval_matched, approval_blockers = _publication_approval_status(
        writer_doc,
        opportunity_doc,
        candidate_id,
        route_selector,
        approval_doc=approval_doc,
    )
    real_send_state, real_send_approval, real_send_matched = _real_send_status(
        writer_doc,
        opportunity_doc,
        candidate_id,
        route_selector,
        approval_doc,
    )

    blockers = candidate_blockers + route_blockers + approval_blockers
    matched = candidate_matched + route_matched + approval_matched + real_send_matched
    if approval_doc is None:
        blockers.append("Real send approval record is missing.")
    if real_send_approval is None:
        blockers.append("Real send approval is missing; publication-send requires an approved real_send record.")

    adapter = str(real_send_approval.get("delivery_adapter") or "missing") if real_send_approval else "missing"
    executed_path: Path | None = None
    executed_status: str | None = None
    execution_rows: list[str] = []
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    send_config = send_config or {}

    if execute and not blockers:
        if adapter == LOCAL_OUTBOX_ADAPTER:
            if outbox_dir is None:
                blockers.append("REAL_SEND_BLOCKED: local_outbox delivery adapter requires --outbox-dir.")
            else:
                executed_path = _write_local_outbox_receipt(
                    outbox_dir,
                    writer_name=writer_name,
                    writer_doc=writer_doc,
                    opportunity_doc=opportunity_doc,
                    candidate_id=candidate_id,
                    route_selector=route_selector,
                    route_name=route_name,
                    approval=real_send_approval,
                    timestamp=timestamp,
                )
                execution_rows.append(f"Local outbox receipt written: {executed_path}")
        elif adapter == DIRECT_EMAIL_ADAPTER:
            executed_status, direct_email_rows, direct_email_blockers = _execute_direct_email(
                writer_name=writer_name,
                candidate_id=candidate_id,
                route_selector=route_selector,
                route_name=route_name,
                approval=real_send_approval,
                send_config=send_config,
                outbox_dir=outbox_dir,
            )
            execution_rows.extend(direct_email_rows)
            blockers.extend(direct_email_blockers)
        elif adapter == SUBMISSION_FORM_ADAPTER:
            blockers.append(
                "REAL_SEND_BLOCKED: submission_form delivery adapter requires a form automation implementation "
                "for the selected route."
            )
        else:
            blockers.append(
                f"REAL_SEND_BLOCKED: delivery adapter {adapter} is unsupported; "
                f"supported adapters are {', '.join(sorted(REAL_SEND_DELIVERY_ADAPTERS))}."
            )

    if blockers:
        send_status = "BLOCKED"
        ok = False
    elif execute and executed_status:
        send_status = executed_status
        ok = True
    elif execute and executed_path is not None:
        send_status = "SENT_TO_LOCAL_OUTBOX"
        ok = True
    elif execute:
        send_status = "BLOCKED"
        ok = False
    else:
        send_status = "READY_TO_SEND"
        ok = True

    lines = [
        f"# Publication Send Receipt: {writer_name}",
        "",
        "Mode: publication_send",
        f"Generated: {timestamp}",
        f"Writer record: {writer_doc.get('id', 'unknown-writer')}",
        f"Opportunity record: {opportunity_doc.get('id', 'unknown-opportunity')}",
        f"Approval record: {approval_doc.get('id', 'not supplied') if approval_doc else 'not supplied'}",
        f"Candidate: {candidate_id}",
        f"Selected venue/route: {route_selector}",
        f"Candidate status: {candidate_status}",
        f"Route status: {route_status}",
        f"Dry-run approvals: {'APPROVED_DRY_RUN' if approvals_ready else 'LOCKED'}",
        f"Real send approval: {real_send_state}",
        f"Delivery adapter: {adapter}",
        f"Execution requested: {'true' if execute else 'false'}",
        f"Send status: {send_status}",
        "",
        "## Matched",
        "",
    ]
    lines.extend(f"- {row}" for row in matched) if matched else lines.append("- none")
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {row}" for row in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Execution", ""])
    if execution_rows:
        lines.extend(f"- {row}" for row in execution_rows)
    elif not execute:
        lines.append("- No execution requested; pass --execute to use the selected delivery adapter.")
    else:
        lines.append("- No execution completed.")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This command validates explicit real_send approval and attempts the selected delivery adapter.",
            "- Direct email uses runtime SMTP settings and sender/recipient env vars; receipts redact those values.",
            "- External credentials and recipient configuration stay outside tracked records.",
            "- This receipt does not claim acceptance, publication, editor interest, or public release.",
        ]
    )
    return "\n".join(lines) + "\n", ok


def _declared_output_modes(doc: dict[str, Any]) -> list[str]:
    outputs = doc.get("outputs", [])
    if not isinstance(outputs, list):
        return []
    modes: list[str] = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        mode = str(output.get("mode") or "")
        if mode in OUTPUT_MODES and mode not in modes:
            modes.append(mode)
    return modes


def _public_handoff_leaks(text: str) -> list[str]:
    leaks = [fragment for fragment in HANDOFF_PUBLIC_FORBIDDEN_FRAGMENTS if fragment in text]
    if EMAIL_RE.search(text):
        leaks.append("contact email")
    if PHONE_RE.search(text):
        leaks.append("phone-like contact data")
    return leaks


def _first_matching_line(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line
    return ""


def _append_handoff_row(rows: list[tuple[str, str, str]], status: str, name: str, detail: str) -> None:
    rows.append((status, name, _sentence(detail)))


def _build_handoff_audit(
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any] | None = None,
    candidate_id: str | None = None,
    route_selector: str | None = None,
) -> tuple[str, int]:
    rows: list[tuple[str, str, str]] = []
    writer_subject = writer_doc.get("subject", {})
    if not isinstance(writer_subject, dict):
        writer_subject = {}
    writer_name = str(writer_subject.get("name") or writer_doc.get("name") or "Unnamed writer")
    writer_label = str(writer_doc.get("id") or writer_name)

    writer_violations = validate_doc(writer_doc, writer_label)
    if writer_violations:
        _append_handoff_row(
            rows,
            "BROKEN",
            "Writer record validation",
            "; ".join(writer_violations[:5]),
        )
    else:
        _append_handoff_row(rows, "PROVEN", "Writer record validation", "record schema passes")

    if opportunity_doc is not None:
        opportunity_label = str(opportunity_doc.get("id") or "opportunity")
        opportunity_violations = validate_doc(opportunity_doc, opportunity_label)
        if opportunity_violations:
            _append_handoff_row(
                rows,
                "BROKEN",
                "Opportunity record validation",
                "; ".join(opportunity_violations[:5]),
            )
        else:
            _append_handoff_row(
                rows,
                "PROVEN",
                "Opportunity record validation",
                "market and route schema passes",
            )
    else:
        _append_handoff_row(
            rows,
            "GATE",
            "Opportunity record validation",
            "no opportunity record supplied, so scan/match route coverage is not audited",
        )

    for mode in _declared_output_modes(writer_doc):
        try:
            rendered = render_record(writer_doc, mode)
        except ValueError as exc:
            _append_handoff_row(rows, "BROKEN", f"{mode} renderer", str(exc))
            continue

        required_sections = ("## Subject Summary", "## Source Appendix Summary", "## No-Outward-Action Notice")
        missing_sections = [section for section in required_sections if section not in rendered]
        if missing_sections:
            _append_handoff_row(
                rows,
                "BROKEN",
                f"{mode} renderer",
                "missing required sections: " + ", ".join(missing_sections),
            )
        else:
            _append_handoff_row(
                rows, "PROVEN", f"{mode} renderer", "renders with evidence and no-outward-action sections"
            )

        if mode in PUBLIC_RENDER_MODES:
            leaks = _public_handoff_leaks(rendered)
            if leaks:
                _append_handoff_row(
                    rows,
                    "BROKEN",
                    f"{mode} public privacy",
                    "public renderer leaked " + ", ".join(sorted(set(leaks))),
                )
            else:
                _append_handoff_row(
                    rows,
                    "PROVEN",
                    f"{mode} public privacy",
                    "no local private refs, contact data, or raw-private markers found",
                )

    writer_modes = _output_modes(writer_doc)
    if AUTHORITY_MODES.issubset(writer_modes):
        try:
            authority_packet = render_authority_packet(writer_doc)
        except ValueError as exc:
            _append_handoff_row(rows, "BROKEN", "Authority packet", str(exc))
        else:
            if "## No-Outward-Action Gate" in authority_packet and "## Packet Blockers" in authority_packet:
                _append_handoff_row(
                    rows,
                    "PROVEN",
                    "Authority packet",
                    "combined dossier, public draft, scorecard, blockers, sources, and approvals render",
                )
            else:
                _append_handoff_row(
                    rows,
                    "BROKEN",
                    "Authority packet",
                    "packet rendered without required blocker or no-outward-action sections",
                )
    else:
        _append_handoff_row(
            rows,
            "GATE",
            "Authority packet",
            "record does not declare the complete authority mode set",
        )

    if opportunity_doc is not None and candidate_id and route_selector:
        try:
            literary_packet = render_literary_packet(
                writer_doc,
                opportunity_doc,
                candidate_id=candidate_id,
                route_selector=route_selector,
            )
        except ValueError as exc:
            _append_handoff_row(rows, "BROKEN", "Literary desk packet", str(exc))
        else:
            if "## Fit Check" in literary_packet and "## No-Send Notice" in literary_packet:
                desk_status = _first_matching_line(literary_packet, "Desk status: ") or "Desk status: unknown"
                _append_handoff_row(
                    rows,
                    "PROVEN",
                    "Literary desk packet",
                    f"scan-match-build packet renders; {desk_status}",
                )
                if "Desk status: BLOCKED" in literary_packet:
                    _append_handoff_row(
                        rows,
                        "GATE",
                        "Literary desk readiness",
                        "packet reports blockers instead of pretending submission is ready",
                    )
            else:
                _append_handoff_row(
                    rows,
                    "BROKEN",
                    "Literary desk packet",
                    "packet rendered without fit check or no-send notice",
                )
    elif opportunity_doc is not None:
        _append_handoff_row(
            rows,
            "GATE",
            "Literary desk packet",
            "candidate and route selectors are required to audit scan-match-build behavior",
        )

    for mode in _declared_output_modes(writer_doc):
        if mode not in EXPORT_APPROVAL_TYPES_BY_MODE:
            continue
        if _approved_export(writer_doc, mode):
            try:
                render_record(writer_doc, mode, export=True)
            except ValueError as exc:
                _append_handoff_row(rows, "BROKEN", f"{mode} export dry-run", str(exc))
            else:
                _append_handoff_row(rows, "PROVEN", f"{mode} export dry-run", "approved dry-run export renders")
        else:
            try:
                render_record(writer_doc, mode, export=True)
            except ValueError:
                _append_handoff_row(
                    rows,
                    "PROVEN",
                    f"{mode} export lock",
                    "export is locked until matching approval is recorded",
                )
            else:
                _append_handoff_row(
                    rows,
                    "BROKEN",
                    f"{mode} export lock",
                    "export rendered without matching approval",
                )

    if opportunity_doc is not None and candidate_id and route_selector:
        literary_approved = _approved_export(writer_doc, "writer_submission") and _approved_export(
            opportunity_doc, "writer_submission"
        )
        if literary_approved:
            try:
                render_literary_packet(
                    writer_doc,
                    opportunity_doc,
                    candidate_id=candidate_id,
                    route_selector=route_selector,
                    export=True,
                )
            except ValueError as exc:
                _append_handoff_row(rows, "BROKEN", "Literary export dry-run", str(exc))
            else:
                _append_handoff_row(rows, "PROVEN", "Literary export dry-run", "approved no-send dry run renders")
        else:
            try:
                render_literary_packet(
                    writer_doc,
                    opportunity_doc,
                    candidate_id=candidate_id,
                    route_selector=route_selector,
                    export=True,
                )
            except ValueError:
                _append_handoff_row(
                    rows,
                    "PROVEN",
                    "Literary export lock",
                    "literary export is locked until writer and opportunity submission approvals exist",
                )
            else:
                _append_handoff_row(
                    rows,
                    "BROKEN",
                    "Literary export lock",
                    "literary export rendered without both submission approvals",
                )

    try:
        sample_candidate = candidate_intake_row(
            candidate_id="handoff-audit-candidate",
            title="Handoff audit metadata-only candidate",
            content_ref="source://handoff-audit/metadata-only",
            source_ids=["handoff-audit-source"],
            claim_ids=["handoff-audit-claim"],
        )
    except ValueError as exc:
        _append_handoff_row(rows, "BROKEN", "Candidate intake", str(exc))
    else:
        serialized_candidate = yaml.safe_dump({"candidate_works": [sample_candidate]}, sort_keys=False)
        leaks = _public_handoff_leaks(serialized_candidate)
        if leaks:
            _append_handoff_row(rows, "BROKEN", "Candidate intake", "metadata row leaked " + ", ".join(leaks))
        else:
            _append_handoff_row(
                rows,
                "PROVEN",
                "Candidate intake",
                "metadata-only row emits without manuscript text or contact data",
            )

    mention_config = writer_doc.get("mention_index", {})
    if isinstance(mention_config, dict) and isinstance(mention_config.get("aliases"), list):
        sample_text = " ".join(str(alias) for alias in mention_config["aliases"][:2])
        mention_rows = index_mentions(sample_text, writer_doc)
        if mention_rows:
            _append_handoff_row(rows, "PROVEN", "Mention index", "aliases produce deterministic mention rows")
        else:
            _append_handoff_row(rows, "BROKEN", "Mention index", "aliases are declared but produced no mention rows")
    else:
        _append_handoff_row(rows, "GATE", "Mention index", "record has no mention_index aliases to audit")

    broken_count = sum(1 for status, _, _ in rows if status == "BROKEN")
    gate_count = sum(1 for status, _, _ in rows if status == "GATE")
    audit_status = "BROKEN" if broken_count else "PROVEN"

    lines = [
        f"# Representation Handoff Audit: {writer_name}",
        "",
        f"Audit status: {audit_status}",
        f"Broken features: {broken_count}",
        f"Open gates: {gate_count}",
        "Outward action: none; this audit only renders, validates, and proves locks.",
        "",
        "## Application Pipeline Loop Translation",
        "",
    ]
    for step, detail in HANDOFF_LOOP_STEPS:
        lines.append(f"- {step}: {detail}")

    lines.extend(["", "## Feature Checks", ""])
    lines.extend(f"- {status}: {name}. {detail}" for status, name, detail in rows)
    lines.extend(
        [
            "",
            "## Chris Handoff Rule",
            "",
            "A gate is acceptable only when it names the missing approval, source, candidate metadata, or route evidence. A broken feature is not acceptable for handoff.",
            "This audit does not submit, publish, upload, contact, scrape private messages, or represent AI-generated text as human work.",
        ]
    )
    return "\n".join(lines) + "\n", broken_count


def render_handoff_audit(
    writer_doc: dict[str, Any],
    opportunity_doc: dict[str, Any] | None = None,
    candidate_id: str | None = None,
    route_selector: str | None = None,
) -> str:
    """Render the no-outward-action feature audit for a representation handoff."""
    return _build_handoff_audit(writer_doc, opportunity_doc, candidate_id, route_selector)[0]


def _write_or_print(output: str, out: Path | None) -> None:
    if out:
        out.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


def _candidate_intake_command(args: argparse.Namespace) -> int:
    try:
        row = candidate_intake_row(
            candidate_id=args.id,
            title=args.title,
            content_ref=args.content_ref,
            source_ids=args.source_ids,
            claim_ids=args.claim_ids,
            genre=args.genre,
            form=args.form,
            length=args.length,
            status=args.status,
            rights_status=args.rights_status,
            note=args.note,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    output = yaml.safe_dump({"candidate_works": [row]}, sort_keys=False)
    _write_or_print(output, args.out)
    return 0


def _render_command(record: Path, mode: str, export: bool, out: Path | None, packet: bool) -> int:
    try:
        doc = _load_record(record)
        output = packet_record(doc, mode, export=export) if packet else render_record(doc, mode, export=export)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _write_or_print(output, out)
    return 0


def _literary_packet_command(
    writer: Path,
    opportunity: Path,
    candidate: str,
    route: str,
    export: bool,
    out: Path | None,
) -> int:
    try:
        writer_doc = _load_record(writer)
        opportunity_doc = _load_record(opportunity)
        output = render_literary_packet(
            writer_doc,
            opportunity_doc,
            candidate_id=candidate,
            route_selector=route,
            export=export,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _write_or_print(output, out)
    return 0


def _authority_packet_command(record: Path, out: Path | None) -> int:
    try:
        doc = _load_record(record)
        output = render_authority_packet(doc)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _write_or_print(output, out)
    return 0


def _handoff_audit_command(
    writer: Path,
    opportunity: Path | None,
    candidate: str | None,
    route: str | None,
    out: Path | None,
) -> int:
    try:
        writer_doc = _load_record(writer)
        opportunity_doc = _load_record(opportunity) if opportunity else None
        output, broken_count = _build_handoff_audit(
            writer_doc,
            opportunity_doc,
            candidate_id=candidate,
            route_selector=route,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _write_or_print(output, out)
    return 1 if broken_count else 0


def _publication_readiness_command(
    writer: Path,
    opportunity: Path,
    candidate: str,
    route: str,
    export: bool,
    approval_record: Path | None,
    out: Path | None,
) -> int:
    try:
        writer_doc = _load_record(writer)
        opportunity_doc = _load_record(opportunity)
        approval_doc = _load_record(approval_record) if approval_record else None
        output = render_publication_readiness(
            writer_doc,
            opportunity_doc,
            candidate_id=candidate,
            route_selector=route,
            export=export,
            approval_doc=approval_doc,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _write_or_print(output, out)
    return 0


def _publication_stack_command(
    writer: Path,
    opportunity: Path,
    candidate: str,
    route: str,
    out_dir: Path,
    approval_record: Path | None,
) -> int:
    try:
        writer_doc = _load_record(writer)
        opportunity_doc = _load_record(opportunity)
        approval_doc = _load_record(approval_record) if approval_record else None
        files = render_publication_stack_files(
            writer_doc,
            opportunity_doc,
            candidate_id=candidate,
            route_selector=route,
            approval_doc=approval_doc,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        if name not in PUBLICATION_STACK_FILENAMES:
            print(f"ERROR: unexpected publication stack file {name}", file=sys.stderr)
            return 1
        (out_dir / name).write_text(content, encoding="utf-8")
    print(f"Wrote publication stack: {out_dir}")
    for name in sorted(files):
        print(f"- {name}")
    return 0


def _publication_send_command(
    writer: Path,
    opportunity: Path,
    candidate: str,
    route: str,
    approval_record: Path | None,
    execute: bool,
    outbox_dir: Path | None,
    smtp_host: str | None,
    smtp_port: int,
    smtp_timeout: float,
    smtp_starttls: bool,
    smtp_ssl: bool,
    smtp_user_env: str | None,
    smtp_password_env: str | None,
    sender_env: str | None,
    recipient_env: str | None,
    message_subject_env: str | None,
    message_body_env: str | None,
    payload_path_env: str | None,
    out: Path | None,
) -> int:
    try:
        writer_doc = _load_record(writer)
        opportunity_doc = _load_record(opportunity)
        approval_doc = _load_record(approval_record) if approval_record else None
        output, ok = render_publication_send_receipt(
            writer_doc,
            opportunity_doc,
            candidate_id=candidate,
            route_selector=route,
            approval_doc=approval_doc,
            execute=execute,
            outbox_dir=outbox_dir,
            send_config={
                "smtp_host": smtp_host,
                "smtp_port": smtp_port,
                "smtp_timeout": smtp_timeout,
                "smtp_starttls": smtp_starttls,
                "smtp_ssl": smtp_ssl,
                "smtp_user_env": smtp_user_env,
                "smtp_password_env": smtp_password_env,
                "sender_env": sender_env,
                "recipient_env": recipient_env,
                "message_subject_env": message_subject_env,
                "message_body_env": message_body_env,
                "payload_path_env": payload_path_env,
            },
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    _write_or_print(output, out)
    return 0 if ok else 1


def _load_record(path: Path) -> dict[str, Any]:
    doc = _load_yaml(path)
    if isinstance(doc, list):
        raise ValueError("; ".join(doc))
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Representation Substrate source and privacy tools")
    sub = parser.add_subparsers(dest="cmd")

    validate = sub.add_parser("validate", help="validate representation records")
    validate.add_argument("paths", nargs="*", type=Path)
    validate.add_argument("--fleet", action="store_true")
    validate.add_argument("--quiet", action="store_true")

    render = sub.add_parser("render", help="render a representation mode")
    render.add_argument("record", type=Path)
    render.add_argument("--mode", required=True, choices=sorted(OUTPUT_MODES))
    render.add_argument("--export", action="store_true")
    render.add_argument("--out", type=Path)

    packet = sub.add_parser("packet", help="generate a reviewable representation packet")
    packet.add_argument("record", type=Path)
    packet.add_argument("--mode", required=True, choices=sorted(PACKET_MODES))
    packet.add_argument("--export", action="store_true")
    packet.add_argument("--out", type=Path)

    authority_packet = sub.add_parser(
        "authority-packet",
        help="generate a combined no-outward-action authority packet from one record",
    )
    authority_packet.add_argument("--record", required=True, type=Path)
    authority_packet.add_argument("--out", type=Path)

    literary_packet = sub.add_parser(
        "literary-packet",
        help="generate a no-send literary desk packet from writer, opportunity, candidate, and route",
    )
    literary_packet.add_argument("--writer", required=True, type=Path)
    literary_packet.add_argument("--opportunity", required=True, type=Path)
    literary_packet.add_argument("--candidate", required=True)
    literary_packet.add_argument("--route", required=True)
    literary_packet.add_argument("--export", action="store_true")
    literary_packet.add_argument("--out", type=Path)

    publication_readiness = sub.add_parser(
        "publication-readiness",
        help="generate a privacy-safe publication readiness packet for a writer, candidate, and route",
    )
    publication_readiness.add_argument("--writer", required=True, type=Path)
    publication_readiness.add_argument("--opportunity", required=True, type=Path)
    publication_readiness.add_argument("--candidate", required=True)
    publication_readiness.add_argument("--route", required=True)
    publication_readiness.add_argument("--export", action="store_true")
    publication_readiness.add_argument("--approval-record", type=Path)
    publication_readiness.add_argument("--out", type=Path)

    publication_stack = sub.add_parser(
        "publication-stack",
        help="write a review-only publication packet stack for a writer, candidate, and route",
    )
    publication_stack.add_argument("--writer", required=True, type=Path)
    publication_stack.add_argument("--opportunity", required=True, type=Path)
    publication_stack.add_argument("--candidate", required=True)
    publication_stack.add_argument("--route", required=True)
    publication_stack.add_argument("--out-dir", required=True, type=Path)
    publication_stack.add_argument("--approval-record", type=Path)

    publication_send = sub.add_parser(
        "publication-send",
        help="validate and execute an approved publication send adapter for a writer, candidate, and route",
    )
    publication_send.add_argument("--writer", required=True, type=Path)
    publication_send.add_argument("--opportunity", required=True, type=Path)
    publication_send.add_argument("--candidate", required=True)
    publication_send.add_argument("--route", required=True)
    publication_send.add_argument("--approval-record", type=Path)
    publication_send.add_argument("--execute", action="store_true")
    publication_send.add_argument("--outbox-dir", type=Path)
    publication_send.add_argument("--smtp-host")
    publication_send.add_argument("--smtp-port", type=int, default=25)
    publication_send.add_argument("--smtp-timeout", type=float, default=15.0)
    publication_send.add_argument("--smtp-starttls", action="store_true")
    publication_send.add_argument("--smtp-ssl", action="store_true")
    publication_send.add_argument("--smtp-user-env")
    publication_send.add_argument("--smtp-password-env")
    publication_send.add_argument("--sender-env")
    publication_send.add_argument("--recipient-env")
    publication_send.add_argument("--message-subject-env")
    publication_send.add_argument("--message-body-env")
    publication_send.add_argument("--payload-path-env")
    publication_send.add_argument("--out", type=Path)

    handoff_audit = sub.add_parser(
        "handoff-audit",
        help="audit a representation handoff without publishing, submitting, or contacting",
    )
    handoff_audit.add_argument("--writer", required=True, type=Path)
    handoff_audit.add_argument("--opportunity", type=Path)
    handoff_audit.add_argument("--candidate")
    handoff_audit.add_argument("--route")
    handoff_audit.add_argument("--out", type=Path)

    candidate_intake = sub.add_parser(
        "candidate-intake",
        help="emit a metadata-only candidate_works row from a manuscript/source ref",
    )
    candidate_intake.add_argument("--id", required=True)
    candidate_intake.add_argument("--title", required=True)
    candidate_intake.add_argument("--genre", default="")
    candidate_intake.add_argument("--form", default="")
    candidate_intake.add_argument("--length", default="")
    candidate_intake.add_argument("--status", default="metadata_only_source_ref_supplied")
    candidate_intake.add_argument("--rights-status", default="")
    candidate_intake.add_argument("--content-ref", required=True)
    candidate_intake.add_argument("--source-id", action="append", required=True, dest="source_ids")
    candidate_intake.add_argument("--claim-id", action="append", required=True, dest="claim_ids")
    candidate_intake.add_argument(
        "--note",
        default="Metadata-only candidate intake; no creative text stored.",
    )
    candidate_intake.add_argument("--out", type=Path)

    mention = sub.add_parser("index-mentions", help="index mentions from text files")
    mention.add_argument("record", type=Path)
    mention.add_argument("texts", nargs="+", type=Path)

    args = parser.parse_args(argv)
    base = Path(__file__).resolve().parent

    if args.cmd == "validate":
        paths = fleet_paths(base) if args.fleet else args.paths
        if not paths:
            parser.error("validate requires path(s) or --fleet")
        failures = 0
        for path in paths:
            violations = validate_path(path)
            if violations:
                failures += 1
                print(f"FAIL  {path}")
                for violation in violations:
                    print(f"  - {violation}")
            elif not args.quiet:
                print(f"PASS  {path}")
        if not args.quiet:
            print()
            print(f"{len(paths) - failures}/{len(paths)} passed")
        return 1 if failures else 0

    if args.cmd == "render":
        return _render_command(args.record, args.mode, args.export, args.out, packet=False)

    if args.cmd == "packet":
        return _render_command(args.record, args.mode, args.export, args.out, packet=True)

    if args.cmd == "authority-packet":
        return _authority_packet_command(args.record, args.out)

    if args.cmd == "literary-packet":
        return _literary_packet_command(
            args.writer,
            args.opportunity,
            args.candidate,
            args.route,
            args.export,
            args.out,
        )

    if args.cmd == "publication-readiness":
        return _publication_readiness_command(
            args.writer,
            args.opportunity,
            args.candidate,
            args.route,
            args.export,
            args.approval_record,
            args.out,
        )

    if args.cmd == "publication-stack":
        return _publication_stack_command(
            args.writer,
            args.opportunity,
            args.candidate,
            args.route,
            args.out_dir,
            args.approval_record,
        )

    if args.cmd == "publication-send":
        return _publication_send_command(
            args.writer,
            args.opportunity,
            args.candidate,
            args.route,
            args.approval_record,
            args.execute,
            args.outbox_dir,
            args.smtp_host,
            args.smtp_port,
            args.smtp_timeout,
            args.smtp_starttls,
            args.smtp_ssl,
            args.smtp_user_env,
            args.smtp_password_env,
            args.sender_env,
            args.recipient_env,
            args.message_subject_env,
            args.message_body_env,
            args.payload_path_env,
            args.out,
        )

    if args.cmd == "handoff-audit":
        return _handoff_audit_command(
            args.writer,
            args.opportunity,
            args.candidate,
            args.route,
            args.out,
        )

    if args.cmd == "candidate-intake":
        return _candidate_intake_command(args)

    if args.cmd == "index-mentions":
        try:
            profile = _load_record(args.record)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        rows: list[dict[str, Any]] = []
        for path in args.texts:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
                return 1
            for row in index_mentions(text, profile):
                rows.append({"path": str(path), **row})
        for row in rows:
            print(f"{row['path']}:{row['start']}: {row['match']} :: {row['context']}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
