#!/usr/bin/env python3
"""Representation Substrate source, privacy, mention, and mode gates."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
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
}
APPROVAL_STATUSES = {"not_requested", "pending", "approved", "denied"}
OUTPUT_MODES = {
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
    "private_dossier",
    "public_page_draft",
    "writer_submission",
    "market_fit",
    "collaboration_packet",
    "project_page",
}
PUBLIC_RENDER_MODES = {
    "creator_presence_preview",
    "public_page_draft",
    "project_page",
    "co_branded_page",
}
PRIVATE_RENDER_MODES = {
    "private_dossier",
    "writer_submission",
    "market_fit",
    "collaboration_packet",
}
PUBLIC_APPROVAL_TYPES = {"public_export", "public_claim", "co_branded_page", "project_page"}
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
}


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
    return {
        str(source.get("source_type"))
        for source in _sources(doc)
        if source.get("source_type")
    }


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
    return (
        str(source.get("source_type")) == "web"
        and str(source.get("privacy_level")) == "public"
    )


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
                    violations.append(
                        f"{prefix} references unknown claim_ids: {', '.join(unknown)}"
                    )
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
                            violations.append(
                                f"{prefix} acceptance gate contains placeholder text {placeholder!r}"
                            )

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
                    str(approval_id)
                    for approval_id in approval_refs
                    if str(approval_id) not in approval_ids
                ]
                if unknown_approvals:
                    violations.append(
                        f"{prefix} references unknown approval_ids: {', '.join(unknown_approvals)}"
                    )
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
        violations.append(
            f"{report_label}: private relational/persona claims require messages source evidence"
        )

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
            else:
                unknown = [str(claim_id) for claim_id in refs if str(claim_id) not in claim_ids]
                if unknown:
                    violations.append(
                        f"{prefix} references unknown claim_ids: {', '.join(unknown)}"
                    )

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
                unknown_claims = [
                    str(claim_id) for claim_id in claim_refs if str(claim_id) not in claim_ids
                ]
                if unknown_claims:
                    violations.append(
                        f"{prefix} references unknown claim_ids: {', '.join(unknown_claims)}"
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
                    str(source_id)
                    for source_id in guideline_refs
                    if str(source_id) not in source_ids
                ]
                if unknown_guideline_refs:
                    violations.append(
                        f"{prefix} references unknown guidelines_source_ids: "
                        f"{', '.join(unknown_guideline_refs)}"
                    )

        if _route_is_venue_specific(route):
            if not isinstance(guideline_refs, list) or not guideline_refs:
                violations.append(
                    f"{prefix} guidelines_source_ids must list public web sources "
                    "for venue-specific routes"
                )
            else:
                non_public_web = [
                    str(source_id)
                    for source_id in guideline_refs
                    if str(source_id) in sources_by_id
                    and not _source_is_public_web(sources_by_id[str(source_id)])
                ]
                if non_public_web:
                    violations.append(
                        f"{prefix} guidelines_source_ids must reference public web sources: "
                        f"{', '.join(non_public_web)}"
                    )
                guidelines_url = str(route.get("guidelines_url") or "").strip()
                if guidelines_url:
                    source_urls = {
                        str(sources_by_id[str(source_id)].get("source_ref"))
                        for source_id in guideline_refs
                        if str(source_id) in sources_by_id
                    }
                    if guidelines_url not in source_urls:
                        violations.append(
                            f"{prefix} guidelines_url must match a guidelines_source_ids source_ref"
                        )

        ai_refs = route.get("ai_policy_source_ids", [])
        if ai_refs is not None:
            if not isinstance(ai_refs, list):
                violations.append(f"{prefix} ai_policy_source_ids must be a list when present")
            else:
                unknown_ai_refs = [
                    str(source_id) for source_id in ai_refs if str(source_id) not in source_ids
                ]
                if unknown_ai_refs:
                    violations.append(
                        f"{prefix} references unknown ai_policy_source_ids: {', '.join(unknown_ai_refs)}"
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
                    violations.append(
                        f"{report_label}: message source {idx} appears to expose private text"
                    )

    return violations


def validate_doc(doc: dict[str, Any], label: str = "<doc>") -> list[str]:
    """Return validation violations for one Representation Substrate record."""
    violations: list[str] = []
    violations.extend(_validate_core_schema(doc, label))
    violations.extend(_validate_claims(doc, label))
    violations.extend(_validate_sources(doc, label))
    violations.extend(_validate_approvals(doc, label))
    violations.extend(_validate_literary_metadata(doc, label))
    violations.extend(_validate_privacy(doc, label))
    return violations


def validate_path(path: Path) -> list[str]:
    doc = _load_yaml(path)
    if isinstance(doc, list):
        return doc
    return validate_doc(doc, str(path))


def fleet_paths(base: Path) -> list[Path]:
    roots = [base / "records", base / "opportunities"]
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


def public_claims(doc: dict[str, Any]) -> list[dict[str, Any]]:
    sources = _source_by_id(doc)
    approved_claim_ids = _approved_public_claim_ids(doc)
    out: list[dict[str, Any]] = []

    for claim in _claims(doc):
        if claim.get("public_ok") is not True:
            continue
        source_ids = [str(source_id) for source_id in claim.get("source_ids", [])]
        if not source_ids or any(source_id not in sources for source_id in source_ids):
            continue
        privacies = _claim_source_privacies(claim, sources)
        source_types = _claim_source_types(claim, sources)
        all_public = bool(privacies) and all(privacy == "public" for privacy in privacies)
        public_approved = _claim_has_public_approval(claim, approved_claim_ids)
        if "messages" in source_types and not public_approved:
            continue
        if all_public or public_approved:
            out.append(claim)

    return out


def _output_modes(doc: dict[str, Any]) -> set[str]:
    outputs = doc.get("outputs", [])
    if not isinstance(outputs, list):
        return set()
    return {
        str(output.get("mode"))
        for output in outputs
        if isinstance(output, dict) and output.get("mode")
    }


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
        _safe_metadata_text(source_id, "source-id", max_len=120)
        for source_id in source_ids
        if str(source_id).strip()
    ]
    cleaned_claim_ids = [
        _safe_metadata_text(claim_id, "claim-id", max_len=120)
        for claim_id in claim_ids
        if str(claim_id).strip()
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


def _source_rows(
    doc: dict[str, Any], rendered_claim_ids: set[str], mode: str
) -> list[str]:
    rows: list[str] = []
    public_mode = mode in PUBLIC_RENDER_MODES
    for source in _sources(doc):
        refs = source.get("claim_ids", [])
        if isinstance(refs, list) and rendered_claim_ids.intersection(str(ref) for ref in refs):
            rows.append(_source_line(source, public_mode))
    return rows


def _submission_readiness_rows(
    doc: dict[str, Any], claims: list[dict[str, Any]]
) -> list[str]:
    sources = _source_by_id(doc)
    public_profile_claims: list[dict[str, Any]] = []
    for claim in claims:
        source_ids = [str(source_id) for source_id in claim.get("source_ids", [])]
        if source_ids and all(
            sources.get(source_id, {}).get("privacy_level") == "public"
            for source_id in source_ids
        ):
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

    proof_points = "; ".join(
        str(claim.get("summary", claim.get("label", "claim"))).rstrip(".!?")
        for claim in claims
    )
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
    claims = [
        claim
        for claim in visible_claims
        if not output_claim_ids or str(claim.get("id")) in output_claim_ids
    ]
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
    mandate_description = (
        str(mandate.get("description", "")) if isinstance(mandate, dict) else str(mandate or "")
    )
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


def _literary_writer_claims(writer_doc: dict[str, Any]) -> list[dict[str, Any]]:
    output_claim_ids = _output_claim_ids(writer_doc, "writer_submission")
    return [
        claim
        for claim in public_claims(writer_doc)
        if not output_claim_ids or str(claim.get("id")) in output_claim_ids
    ]


def _literary_opportunity_claims(opportunity_doc: dict[str, Any]) -> list[dict[str, Any]]:
    output_claim_ids = _output_claim_ids(opportunity_doc, "market_fit") or _output_claim_ids(
        opportunity_doc, "writer_submission"
    )
    return [
        claim
        for claim in _claims(opportunity_doc)
        if not output_claim_ids or str(claim.get("id")) in output_claim_ids
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


def _literary_approval_rows(
    writer_doc: dict[str, Any], opportunity_doc: dict[str, Any]
) -> list[str]:
    rows: list[str] = []
    for label, doc in (("Writer", writer_doc), ("Opportunity", opportunity_doc)):
        submission_approvals = [
            approval
            for approval in _approvals(doc)
            if str(approval.get("approval_type")) == "submission"
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
    ai_policy_status_unresolved = _ai_policy_status_unresolved(
        route.get("ai_policy_disclosure_status")
    )
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

    if args.cmd == "literary-packet":
        return _literary_packet_command(
            args.writer,
            args.opportunity,
            args.candidate,
            args.route,
            args.export,
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
