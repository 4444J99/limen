"""Normalize attended Markdown exports and apply Studium source-verifier attestations."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import TypedDict, cast
from urllib.parse import urlparse

from .catalog import select_profile
from .contracts import (
    ResearchContractError,
    ResearchRequest,
    canonical_json,
    iso_datetime,
    mapping,
    now,
    stable_hash,
)
from .handoff import BlockedReceipt, ResearchReceipt, build_receipt
from .sanitization import (
    OutputSanitizationAttestation,
    assert_raw_export_custody_boundary,
    assert_receipt_sanitized,
    assert_tracked_output_machine_safe,
)
from .verification import SourceVerifierAttestation

_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_CITATION = re.compile(r"\[(S\d+|\d+)\](?!\()", re.IGNORECASE)
_SOURCE_LINE = re.compile(
    r"^\s*[-*]\s*\[(?P<id>S?\d+)\]\s*"
    r"\[(?P<title>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)(?P<meta>.*)$",
    re.IGNORECASE,
)
_NEGATIVE_SEARCH = re.compile(
    r"^\s*[-*]\s*Query:\s*(?P<query>.*?)\s*\|\s*Surface:\s*(?P<surface>.*?)\s*"
    r"\|\s*Searched:\s*(?P<searched>.*?)\s*\|\s*Result count:\s*(?P<count>\d+)\s*"
    r"\|\s*Disposition:\s*(?P<disposition>.+?)\s*$",
    re.IGNORECASE,
)


class _ReceiptSanitizationKwargs(TypedDict):
    tracked_output_safe: bool
    redactions_applied: Sequence[str]
    contains_credentials: bool
    contains_private_prompt_body: bool
    contains_sensitive_raw_material: bool


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _sections(markdown: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"preamble": []}
    current = "preamble"
    for line in markdown.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = _normalize_heading(heading.group(1))
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


def _metadata_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in text.split("|"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        fields[_normalize_heading(key)] = value.strip()
    return fields


def _source_id(raw: str) -> str:
    normalized = raw.lstrip("^").upper()
    if normalized.isdigit():
        normalized = f"S{normalized}"
    return f"SRC-{normalized}"


def _claim_id(raw: str) -> str:
    return f"CLM-C{raw}" if not raw.upper().startswith("C") else f"CLM-{raw.upper()}"


def _published_date(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw or raw.lower() in {"unknown", "none", "n/a", "not available"}:
        return None
    return raw


def _source_manifest(
    sections: Mapping[str, Sequence[str]],
) -> tuple[list[dict[str, object]], list[str]]:
    sources: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    for line in sections.get("source_manifest", ()):
        explicit = _SOURCE_LINE.match(line)
        if not explicit:
            if line.strip() and line.strip().lower() != "none":
                sources[f"INVALID-{len(sources) + 1}"] = {
                    "source_id": f"INVALID-{len(sources) + 1}",
                    "title": "",
                    "url": "",
                    "author_or_publisher": None,
                    "published_at": None,
                    "retrieved_at": None,
                    "source_type": "",
                    "primary_source": False,
                    "quality_tier": "",
                    "locator": None,
                }
            continue
        source_id = _source_id(explicit.group("id"))
        if source_id in sources:
            errors.append(f"duplicate_source_id:{source_id}")
            continue
        metadata = _metadata_fields(explicit.group("meta"))
        primary_label = (metadata.get("primary") or "").lower()
        primary = primary_label in {"true", "yes", "1"}
        sources[source_id] = {
            "source_id": source_id,
            "title": explicit.group("title").strip(),
            "url": explicit.group("url").rstrip(".,;"),
            "author_or_publisher": metadata.get("publisher") or metadata.get("author") or None,
            "published_at": _published_date(metadata.get("published") or metadata.get("publication_date")),
            "retrieved_at": iso_datetime(metadata.get("retrieved") or metadata.get("retrieval_date")),
            "source_type": metadata.get("source_type") or "",
            "primary_source": primary,
            "quality_tier": (metadata.get("quality_tier") or "").upper(),
            "locator": metadata.get("locator") or None,
        }
    return sorted(sources.values(), key=lambda item: str(item["source_id"])), errors


def _claim_lines(sections: Mapping[str, Sequence[str]]) -> list[str]:
    lines: list[str] = []
    for line in sections.get("material_claims", ()):
        stripped = line.strip()
        if not stripped or stripped.startswith(("<!--", "```")):
            continue
        if stripped.startswith(("-", "*")) or "[C" in stripped.upper():
            lines.append(stripped)
    return lines


def _claims(
    sections: Mapping[str, Sequence[str]], sources: Sequence[Mapping[str, object]]
) -> tuple[list[dict[str, object]], list[str], list[str]]:
    source_by_url = {str(item["url"]): str(item["source_id"]) for item in sources}
    aliases = {str(item["source_id"]).removeprefix("SRC-").upper(): str(item["source_id"]) for item in sources}
    claims: list[dict[str, object]] = []
    citation_occurrences: list[str] = []
    errors: list[str] = []
    seen_claim_ids: set[str] = set()
    for index, line in enumerate(_claim_lines(sections), start=1):
        match = re.search(r"\[C([^\]]+)\]", line, re.IGNORECASE)
        claim_id = _claim_id(match.group(1) if match else str(index))
        if claim_id in seen_claim_ids:
            errors.append(f"duplicate_claim_id:{claim_id}")
            continue
        seen_claim_ids.add(claim_id)
        lowered = line.lower()
        classification = (
            "unknown" if "[unknown]" in lowered else "inference" if "[inference]" in lowered else "evidence"
        )
        material = "[material]" in lowered or classification != "unknown"
        occurrences: list[str] = []
        for marker in _CITATION.findall(line):
            occurrences.append(aliases.get(marker.upper(), _source_id(marker)))
        for _, url in _MARKDOWN_LINK.findall(line):
            source_id = source_by_url.get(url.rstrip(".,;"))
            if source_id:
                occurrences.append(source_id)
            else:
                errors.append(f"unmapped_citation_url:{claim_id}")
        citation_occurrences.extend(occurrences)
        claims.append(
            {
                "claim_id": claim_id,
                "text": re.sub(r"^[-*|\s]+", "", line),
                "material": material,
                "classification": classification,
                "source_ids": sorted(set(occurrences)),
                "verification_status": "not_applicable" if classification == "unknown" else "unsupported",
            }
        )
    return claims, citation_occurrences, errors


def _section_items(sections: Mapping[str, Sequence[str]], name: str) -> list[str]:
    items = []
    for line in sections.get(name, ()):
        value = re.sub(r"^\s*[-*]\s*", "", line).strip()
        if value and value.lower() != "none":
            items.append(value)
    return items


def _negative_searches(
    sections: Mapping[str, Sequence[str]],
) -> tuple[list[dict[str, object]], list[str]]:
    searches: list[dict[str, object]] = []
    errors: list[str] = []
    for line in sections.get("negative_searches", ()):
        if not line.strip() or line.strip().lower() == "none":
            continue
        match = _NEGATIVE_SEARCH.match(line)
        if not match:
            errors.append("invalid_negative_search")
            continue
        searched_at = iso_datetime(match.group("searched"))
        if not searched_at:
            errors.append("invalid_negative_search_date")
            continue
        result_count = int(match.group("count"))
        if result_count != 0:
            errors.append(f"invalid_negative_search_result_count:{result_count}")
            continue
        searches.append(
            {
                "query": match.group("query").strip(),
                "surface": match.group("surface").strip(),
                "searched_at": searched_at,
                "result_count": result_count,
                "disposition": match.group("disposition").strip(),
            }
        )
    return searches, errors


def _safe_public_reference(url: str) -> bool:
    """Validate a citation reference without issuing a network request."""

    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        literal.is_private
        or literal.is_loopback
        or literal.is_link_local
        or literal.is_reserved
        or literal.is_unspecified
    )


def _domain_matches(host: str, candidate: str) -> bool:
    normalized = candidate.lower().strip().lstrip(".")
    return host == normalized or host.endswith("." + normalized)


def _source_constraint_errors(
    request: ResearchRequest,
    source: Mapping[str, object],
    verified_source: object,
) -> list[str]:
    errors: list[str] = []
    source_id = str(source["source_id"])
    parsed = urlparse(str(source.get("url") or ""))
    host = (parsed.hostname or "").lower()
    allow_domains = tuple(str(value) for value in request.domain_constraints.get("allow_domains") or ())
    deny_domains = tuple(str(value) for value in request.domain_constraints.get("deny_domains") or ())
    if allow_domains and not any(_domain_matches(host, value) for value in allow_domains):
        errors.append(f"domain_not_allowed:{source_id}:{host}")
    if any(_domain_matches(host, value) for value in deny_domains):
        errors.append(f"domain_denied:{source_id}:{host}")

    source_types = set(str(value) for value in request.domain_constraints.get("source_types") or ())
    if source_types and str(source.get("source_type")) not in source_types:
        errors.append(f"source_type_not_allowed:{source_id}:{source.get('source_type')}")

    published_at = source.get("published_at")
    published_after = request.freshness.get("published_after")
    published_before = request.freshness.get("published_before")
    if (published_after or published_before) and not published_at:
        errors.append(f"published_date_required:{source_id}")
    if published_at:
        try:
            published = date.fromisoformat(str(published_at))
        except ValueError:
            errors.append(f"source_metadata:{source_id}:published_at")
        else:
            if published_after and published < date.fromisoformat(str(published_after)):
                errors.append(f"published_before_window:{source_id}")
            if published_before and published > date.fromisoformat(str(published_before)):
                errors.append(f"published_after_window:{source_id}")
            max_age = request.freshness.get("max_source_age_days")
            retrieved_at = source.get("retrieved_at")
            if max_age is not None and retrieved_at:
                retrieved = datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00")).date()
                if (retrieved - published).days > int(max_age):
                    errors.append(f"source_too_old:{source_id}")

    retrieved_at = source.get("retrieved_at")
    if retrieved_at:
        retrieved = datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00"))
        retrieved_after = request.freshness.get("retrieved_after")
        if retrieved_after and retrieved.date() < date.fromisoformat(str(retrieved_after)):
            errors.append(f"retrieved_before_window:{source_id}")
        as_of = request.freshness.get("as_of")
        if as_of:
            as_of_time = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
            if retrieved < as_of_time:
                errors.append(f"retrieved_before_as_of:{source_id}")

    languages = set(str(value).lower() for value in request.domain_constraints.get("languages") or ())
    language = getattr(verified_source, "language", None)
    if languages and (not language or language.lower() not in languages):
        errors.append(f"language_not_verified:{source_id}")
    jurisdictions = set(str(value).lower() for value in request.domain_constraints.get("jurisdictions") or ())
    verified_jurisdictions = {str(value).lower() for value in getattr(verified_source, "jurisdictions", ())}
    if jurisdictions and not (jurisdictions & verified_jurisdictions):
        errors.append(f"jurisdiction_not_verified:{source_id}")
    return errors


def _validate_handoff(
    request: ResearchRequest,
    catalog: Mapping[str, object],
    handoff_receipt: Mapping[str, object],
) -> tuple[str, list[str]]:
    receipt = mapping(handoff_receipt, field_name="handoff receipt")
    selected_profile = str(receipt.get("selected_profile") or "").strip()
    errors: list[str] = []
    if receipt.get("request_id") != request.request_id:
        errors.append("handoff_request_id_mismatch")
    if receipt.get("request_hash") != stable_hash(request.canonical_contract()):
        errors.append("handoff_request_hash_mismatch")
    if receipt.get("catalog_hash") != stable_hash(catalog):
        errors.append("handoff_catalog_hash_mismatch")
    if receipt.get("outcome_type") != "ManualHandoff":
        errors.append("handoff_outcome_mismatch")
    verification = receipt.get("verification")
    if not isinstance(verification, Mapping) or verification.get("status") != "manual_pending":
        errors.append("handoff_status_mismatch")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", selected_profile):
        raise ResearchContractError("handoff selected_profile is invalid")
    assert_receipt_sanitized(receipt, private_question=request.question)
    selected, rejected = select_profile(request.with_profile(selected_profile), catalog)
    if selected is None or selected.profile_id != selected_profile:
        errors.append(
            "handoff_profile_unavailable:" + canonical_json(rejected.get(selected_profile) or ["profile_not_found"])
        )
    elif selected.execution_kind != "manual_handoff":
        errors.append("handoff_profile_not_manual")
    return selected_profile, errors


def ingest_markdown_export(
    markdown: str,
    request: ResearchRequest,
    catalog: Mapping[str, object],
    *,
    handoff_receipt: Mapping[str, object],
    verification_attestation: Mapping[str, object],
    sanitization_attestation: Mapping[str, object],
    observed_provider: str | None = None,
    observed_model: str | None = None,
    operator_handling_seconds: int = 0,
) -> tuple[dict[str, object] | BlockedReceipt, ResearchReceipt]:
    ingest_started_at = now()
    selected_profile, errors = _validate_handoff(request, catalog, handoff_receipt)
    sections = _sections(markdown)
    sources, source_errors = _source_manifest(sections)
    claims, _citation_occurrences, claim_errors = _claims(sections, sources)
    errors.extend(source_errors)
    errors.extend(claim_errors)
    source_by_id = {str(item["source_id"]): item for item in sources}
    claim_by_id = {str(item["claim_id"]): item for item in claims}
    resolvable_ids: set[str] = set()

    try:
        attestation = SourceVerifierAttestation.from_mapping(
            verification_attestation, expected_request_id=request.request_id
        )
    except ResearchContractError as exc:
        attestation = None
        errors.append(f"source_verifier_attestation:{exc}")
    try:
        assert_raw_export_custody_boundary(
            markdown,
            private_question=request.question,
            raw_export_ref=request.raw_export_ref,
        )
    except ResearchContractError as exc:
        errors.append(f"privacy_raw_export:{exc}")
    try:
        sanitization = OutputSanitizationAttestation.from_mapping(
            sanitization_attestation,
            expected_request_id=request.request_id,
            expected_export_hash=stable_hash(markdown),
            expected_preservation_tier=request.preservation_tier,
            expected_external_transmission=request.external_transmission,
        )
    except ResearchContractError as exc:
        sanitization = None
        errors.append(f"output_sanitization_attestation:{exc}")

    if not claims:
        errors.append("missing_material_claims")
    if not sources:
        errors.append("missing_source_manifest")
    for required in request.required_sections:
        if _normalize_heading(required) not in sections:
            errors.append(f"missing_owner_section:{_normalize_heading(required)}")
    for required in (
        "contradictions",
        "unknowns",
        "negative_searches",
        "novel_actionable_findings",
        "source_manifest",
    ):
        if required not in sections:
            errors.append(f"missing_section:{required}")

    if attestation is not None:
        if attestation.verdict != "accepted":
            errors.append("source_verifier_rejected")
        if set(attestation.claims) != set(claim_by_id):
            errors.append("source_verifier_claim_set_mismatch")
        if set(attestation.sources) != set(source_by_id):
            errors.append("source_verifier_source_set_mismatch")
        for source_id, source in source_by_id.items():
            verified_source = attestation.sources.get(source_id)
            if verified_source is None:
                continue
            if verified_source.url != source.get("url"):
                errors.append(f"source_verifier_url_mismatch:{source_id}")
            elif verified_source.resolvable:
                resolvable_ids.add(source_id)
            else:
                errors.append(f"broken_citation:{source_id}")
            source["source_type"] = verified_source.source_type
            source["primary_source"] = verified_source.primary_source
            source["quality_tier"] = verified_source.quality_tier
            errors.extend(_source_constraint_errors(request, source, verified_source))
        for claim_id, claim in claim_by_id.items():
            verified_claim = attestation.claims.get(claim_id)
            if verified_claim is None:
                continue
            if set(verified_claim.source_ids) != set(
                str(value) for value in cast(Sequence[object], claim["source_ids"])
            ):
                errors.append(f"source_verifier_claim_sources_mismatch:{claim_id}")
            claim["verification_status"] = verified_claim.verification_status

    for source in sources:
        source_id = str(source["source_id"])
        if not source_id.startswith("SRC-"):
            errors.append(f"invalid_source_line:{source_id}")
        for field_name in ("title", "url", "retrieved_at", "source_type", "quality_tier"):
            if not source.get(field_name):
                errors.append(f"source_metadata:{source_id}:{field_name}")
        published_at = source.get("published_at")
        if published_at:
            try:
                date.fromisoformat(str(published_at))
            except ValueError:
                errors.append(f"source_metadata:{source_id}:published_at")
        if source.get("quality_tier") not in {"A", "B", "C", "D"}:
            errors.append(f"source_metadata:{source_id}:quality_tier")
        if not _safe_public_reference(str(source.get("url") or "")):
            errors.append(f"unsafe_citation_url:{source_id}")
        if source_id not in resolvable_ids:
            errors.append(f"broken_citation:{source_id}")

    material_claims = 0
    supported_material_claims = 0
    for claim in claims:
        claim_id = str(claim["claim_id"])
        claim_sources = [str(item) for item in cast(Sequence[object], claim["source_ids"])]
        if claim["material"]:
            material_claims += 1
            if not claim_sources:
                errors.append(f"unsupported_claim:{claim_id}")
            elif claim["verification_status"] != "supported":
                errors.append(f"unsupported_claim:{claim_id}:{claim['verification_status']}")
            elif all(source_id in resolvable_ids for source_id in claim_sources):
                supported_material_claims += 1
        elif claim["classification"] == "unknown" and claim["verification_status"] != "not_applicable":
            errors.append(f"unknown_claim_status:{claim_id}")
        for source_id in claim_sources:
            if source_id not in source_by_id:
                errors.append(f"lost_source_metadata:{claim_id}:{source_id}")

    citation_edges = [
        str(source_id) for claim in claims for source_id in cast(Sequence[object], claim.get("source_ids") or ())
    ]
    primary_count = sum(
        1
        for source_id in citation_edges
        if source_id in source_by_id and bool(source_by_id[source_id].get("primary_source"))
    )
    total_citations = len(citation_edges)
    resolvable_citations = sum(1 for source_id in citation_edges if source_id in resolvable_ids)
    primary_ratio = primary_count / total_citations if total_citations else 0.0
    if primary_ratio + 1e-9 < request.primary_source_ratio:
        errors.append(f"primary_source_ratio:{primary_ratio:.3f}<{request.primary_source_ratio:.3f}")

    negative_searches, negative_errors = _negative_searches(sections)
    errors.extend(negative_errors)
    contradictions = _section_items(sections, "contradictions")
    unknowns = _section_items(sections, "unknowns")
    novel_findings = _section_items(sections, "novel_actionable_findings")
    if "novel_actionable_findings" in request.required_sections and not novel_findings:
        errors.append("missing_novel_actionable_finding")

    research_times: list[datetime] = []
    for source in sources:
        if source.get("retrieved_at"):
            research_times.append(datetime.fromisoformat(str(source["retrieved_at"]).replace("Z", "+00:00")))
    for search in negative_searches:
        research_times.append(datetime.fromisoformat(str(search["searched_at"]).replace("Z", "+00:00")))
    if research_times:
        retrieval_started_at = min(research_times).isoformat().replace("+00:00", "Z")
        retrieval_finished_at = max(research_times).isoformat().replace("+00:00", "Z")
    else:
        retrieval_started_at = ingest_started_at
        retrieval_finished_at = ingest_started_at
    if attestation is not None:
        requested = datetime.fromisoformat(request.requested_at.replace("Z", "+00:00"))
        retrieval_started = datetime.fromisoformat(retrieval_started_at.replace("Z", "+00:00"))
        retrieval_finished = datetime.fromisoformat(retrieval_finished_at.replace("Z", "+00:00"))
        verifier_finished_at = datetime.fromisoformat(attestation.verified_at.replace("Z", "+00:00"))
        if not requested <= retrieval_started <= retrieval_finished <= verifier_finished_at:
            errors.append("research_timestamps_out_of_order")
    if sanitization is not None:
        retrieval_finished = datetime.fromisoformat(retrieval_finished_at.replace("Z", "+00:00"))
        sanitized = datetime.fromisoformat(sanitization.attested_at.replace("Z", "+00:00"))
        if retrieval_finished > sanitized:
            errors.append("sanitization_timestamp_out_of_order")

    source_manifest_hash = stable_hash(sources)
    if attestation is not None:
        verifier = attestation.receipt_verifier
        verified_at = attestation.verified_at
    elif sanitization is not None:
        verifier = sanitization.receipt_verifier
        verified_at = sanitization.attested_at
    else:
        verifier = "limen.research"
        verified_at = now()
    packet: dict[str, object] = {
        "schema_version": "1.0",
        "outcome_type": "EvidencePacket",
        "request_id": request.request_id,
        "retrieved_at": retrieval_finished_at,
        "verification_status": "accepted",
        "source_manifest_hash": source_manifest_hash,
        "claims": claims,
        "sources": sources,
        "contradictions": contradictions,
        "unknowns": unknowns,
        "negative_searches": negative_searches,
        "novel_actionable_findings": novel_findings,
        "durable_output_ref": {
            "owner_repo": request.owner_repo,
            "report_path": request.report_ref,
            "receipt_path": request.receipt_ref,
            "raw_export_ref": request.raw_export_ref,
        },
    }
    try:
        assert_tracked_output_machine_safe(
            render_evidence_markdown(packet),
            private_question=request.question,
        )
    except ResearchContractError as exc:
        errors.append(f"tracked_output_sanitization:{exc}")
    tracked_output_safe = sanitization is not None and not errors
    receipt_sanitization: _ReceiptSanitizationKwargs = {
        "tracked_output_safe": tracked_output_safe,
        "redactions_applied": (sanitization.redactions_applied if sanitization is not None else ()),
        "contains_credentials": False,
        "contains_private_prompt_body": False,
        "contains_sensitive_raw_material": False,
    }
    if errors:
        privacy_failure = any(error.startswith("privacy_") for error in errors)
        structural = any(
            error.startswith(
                (
                    "missing_",
                    "invalid_",
                    "duplicate_",
                    "source_metadata",
                    "lost_source_metadata",
                    "unmapped_citation",
                    "handoff_",
                )
            )
            for error in errors
        )
        outcome = BlockedReceipt(
            request_id=request.request_id,
            blocker_code=(
                "privacy_mismatch" if privacy_failure else "invalid_export" if structural else "verification_failed"
            ),
            attempted_profiles=(selected_profile,),
            owner_surface=request.owner_repo,
            failed_predicate=";".join(sorted(set(errors))),
            next_action="Correct the export or source-verifier attestation; downstream agents must not consume it",
            reversible_work_completed=(
                "validated_handoff",
                "parsed_export",
                "checked_citations",
                "applied_source_verifier_attestation",
                "computed_citation_ratio",
            ),
        )
        receipt = build_receipt(
            request,
            catalog,
            selected_profile=selected_profile,
            outcome_type=outcome.outcome_type,
            verification_status="rejected",
            retrieval_started_at=retrieval_started_at,
            retrieval_finished_at=retrieval_finished_at,
            source_manifest_hash=source_manifest_hash,
            operator_handling_seconds=operator_handling_seconds,
            observed_provider=observed_provider,
            observed_model=observed_model,
            verifier=verifier,
            verified_at=verified_at,
            material_claims=material_claims,
            supported_material_claims=supported_material_claims,
            resolvable_citations=resolvable_citations,
            total_citations=total_citations,
            primary_source_citations=primary_count,
            primary_source_ratio=primary_ratio,
            rejection_reasons=errors,
            **receipt_sanitization,
        )
        return outcome, receipt

    receipt = build_receipt(
        request,
        catalog,
        selected_profile=selected_profile,
        outcome_type="EvidencePacket",
        verification_status="accepted",
        retrieval_started_at=retrieval_started_at,
        retrieval_finished_at=retrieval_finished_at,
        source_manifest_hash=source_manifest_hash,
        operator_handling_seconds=operator_handling_seconds,
        observed_provider=observed_provider,
        observed_model=observed_model,
        verifier=verifier,
        verified_at=verified_at,
        material_claims=material_claims,
        supported_material_claims=supported_material_claims,
        resolvable_citations=resolvable_citations,
        total_citations=total_citations,
        primary_source_citations=primary_count,
        primary_source_ratio=primary_ratio,
        **receipt_sanitization,
    )
    return packet, receipt


def render_evidence_markdown(packet: Mapping[str, object]) -> str:
    raw_claims = packet.get("claims")
    raw_sources = packet.get("sources")
    claims = cast(Sequence[object], raw_claims) if isinstance(raw_claims, Sequence) else []
    sources = cast(Sequence[object], raw_sources) if isinstance(raw_sources, Sequence) else []
    lines = [
        f"# Evidence Packet — {packet.get('request_id', '')}",
        "",
        f"- Retrieved: `{packet.get('retrieved_at', '')}`",
        f"- Verification: `{packet.get('verification_status', '')}`",
        f"- Source manifest: `{packet.get('source_manifest_hash', '')}`",
        "",
        "## Material Claims",
        "",
    ]
    for item in claims:
        claim = mapping(item, field_name="claim")
        source_ids = ", ".join(str(value) for value in cast(Sequence[object], claim.get("source_ids") or [])) or "none"
        lines.append(
            f"- **{claim.get('claim_id', '')}** [{claim.get('classification', '')}; "
            f"{claim.get('verification_status', '')}] {claim.get('text', '')} "
            f"(sources: {source_ids})"
        )
    lines.extend(["", "## Source Manifest", ""])
    for item in sources:
        source = mapping(item, field_name="source")
        lines.append(
            f"- **{source.get('source_id', '')}** [{source.get('title', '')}]({source.get('url', '')}) "
            f"— {source.get('author_or_publisher') or ''}; published "
            f"{source.get('published_at') or 'unknown'}; retrieved {source.get('retrieved_at', '')}; "
            f"type={source.get('source_type', '')}; primary="
            f"{str(bool(source.get('primary_source'))).lower()}; tier="
            f"{source.get('quality_tier', '')}; locator: {source.get('locator') or ''}"
        )
    for heading, key in (
        ("Contradictions", "contradictions"),
        ("Unknowns", "unknowns"),
        ("Negative Searches", "negative_searches"),
        ("Novel Actionable Findings", "novel_actionable_findings"),
    ):
        lines.extend(["", f"## {heading}", ""])
        values = packet.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)) and values:
            for value in values:
                if isinstance(value, Mapping):
                    lines.append(
                        "- "
                        + " | ".join(f"{str(field).replace('_', ' ').title()}: {item}" for field, item in value.items())
                    )
                else:
                    lines.append(f"- {value}")
        else:
            lines.append("None")
    return "\n".join(lines).rstrip() + "\n"
