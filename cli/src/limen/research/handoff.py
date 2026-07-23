"""Typed attended handoffs, blocked outcomes, and sanitized receipts."""

from __future__ import annotations

import re
import webbrowser
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from .catalog import blocker_code, select_profile
from .contracts import (
    RECEIPT_VERIFIER_MAX_LENGTH,
    STANDING_INSTRUCTIONS_REF,
    ResearchContractError,
    ResearchRequest,
    canonical_json,
    mapping,
    now,
    stable_hash,
)
from .sanitization import assert_receipt_sanitized, observed_identifier


@dataclass(frozen=True)
class ManualHandoff:
    request_id: str
    selected_profile: str
    preservation_tier: str
    external_transmission: str
    project_name: str
    launch_url: str
    prompt_ref: str
    standing_instructions_ref: str
    required_export_format: str
    execution_timeout_seconds: int
    ingest_destination: str
    operator_actions: tuple[str, ...]
    resume_predicate: str
    status: str = "ready"
    schema_version: str = "1.0"
    outcome_type: str = "ManualHandoff"
    rendered_prompt: str = field(default="", repr=False, compare=False)

    def public_dict(self) -> dict[str, object]:
        result = asdict(self)
        result.pop("rendered_prompt", None)
        result["operator_actions"] = list(self.operator_actions)
        return result


@dataclass(frozen=True)
class BlockedReceipt:
    request_id: str
    blocker_code: str
    attempted_profiles: tuple[str, ...]
    owner_surface: str
    failed_predicate: str
    next_action: str
    reversible_work_completed: tuple[str, ...] = ()
    blocked_at: str = field(default_factory=now)
    schema_version: str = "1.0"
    outcome_type: str = "BlockedReceipt"

    def public_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["attempted_profiles"] = list(self.attempted_profiles)
        result["reversible_work_completed"] = list(self.reversible_work_completed)
        return result


@dataclass(frozen=True)
class ResearchReceipt:
    receipt_id: str
    request_id: str
    request_hash: str
    catalog_hash: str
    selected_profile: str
    observed_provider: str | None
    observed_model: str | None
    retrieval_started_at: str
    retrieval_finished_at: str
    source_manifest_hash: str
    outcome_type: str
    usage: Mapping[str, object]
    verification: Mapping[str, object]
    durable_output: Mapping[str, object]
    privacy: Mapping[str, object]
    sanitization: Mapping[str, bool]
    schema_version: str = "1.0"

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


def _receipt_id(request_id: str) -> str:
    return request_id.replace("SGO-REQ-", "SGO-RCT-", 1)


def _raw_export_disposition(request: ResearchRequest) -> str:
    if not request.raw_export_ref:
        return "not_retained"
    if request.raw_export_ref.startswith("private-owner://"):
        return "private_owner"
    return "tracked_owner_repo"


def build_receipt(
    request: ResearchRequest,
    catalog: Mapping[str, Any],
    *,
    selected_profile: str,
    outcome_type: str,
    verification_status: str,
    retrieval_started_at: str,
    retrieval_finished_at: str,
    source_manifest_hash: str | None = None,
    variable_cost_usd: float = 0.0,
    requests: int | None = None,
    computer_credits: float | None = None,
    operator_handling_seconds: int = 0,
    observed_provider: str | None = None,
    observed_model: str | None = None,
    verifier: str = "limen.research",
    verified_at: str | None = None,
    material_claims: int = 0,
    supported_material_claims: int = 0,
    resolvable_citations: int = 0,
    total_citations: int = 0,
    primary_source_citations: int = 0,
    primary_source_ratio: float = 0.0,
    rejection_reasons: Sequence[str] = (),
    tracked_output_safe: bool | None = None,
    redactions_applied: Sequence[str] | None = None,
    contains_credentials: bool = False,
    contains_private_prompt_body: bool = False,
    contains_sensitive_raw_material: bool = False,
) -> ResearchReceipt:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", selected_profile):
        raise ResearchContractError("selected_profile must match the owner profile identifier contract")
    observed_provider = observed_identifier(observed_provider, field_name="observed_provider")
    observed_model = observed_identifier(observed_model, field_name="observed_model")
    if not verifier.strip() or len(verifier) > RECEIPT_VERIFIER_MAX_LENGTH:
        raise ResearchContractError("verifier must be a bounded non-empty identifier")
    started = datetime.fromisoformat(retrieval_started_at.replace("Z", "+00:00"))
    finished = datetime.fromisoformat(retrieval_finished_at.replace("Z", "+00:00"))
    if finished < started:
        raise ResearchContractError("retrieval_finished_at cannot precede retrieval_started_at")
    if variable_cost_usd < 0 or variable_cost_usd > request.spend_ceiling_usd:
        raise ResearchContractError("receipt variable cost exceeds the request spend ceiling")
    if operator_handling_seconds < 0 or operator_handling_seconds > request.latency_ceiling_seconds:
        raise ResearchContractError("operator handling exceeds the request latency ceiling")
    if not 0 <= supported_material_claims <= material_claims:
        raise ResearchContractError("supported material claims must be bounded by material claims")
    if not 0 <= resolvable_citations <= total_citations:
        raise ResearchContractError("resolvable citations must be bounded by total citations")
    if not 0 <= primary_source_citations <= total_citations:
        raise ResearchContractError("primary-source citations must be bounded by total citations")
    expected_ratio = primary_source_citations / total_citations if total_citations else 0.0
    if abs(primary_source_ratio - expected_ratio) > 1e-9:
        raise ResearchContractError("primary-source ratio does not match citation counts")
    if verification_status == "accepted" and (
        supported_material_claims != material_claims
        or resolvable_citations != total_citations
        or primary_source_ratio + 1e-9 < request.primary_source_ratio
    ):
        raise ResearchContractError("accepted receipt does not satisfy the request verification gate")
    if tracked_output_safe is not None and not isinstance(tracked_output_safe, bool):
        raise ResearchContractError("tracked_output_safe must be boolean")
    for field_name, value in (
        ("contains_credentials", contains_credentials),
        ("contains_private_prompt_body", contains_private_prompt_body),
        ("contains_sensitive_raw_material", contains_sensitive_raw_material),
    ):
        if not isinstance(value, bool):
            raise ResearchContractError(f"{field_name} must be boolean")
    redactions = tuple(
        str(value).strip()
        for value in (
            redactions_applied
            if redactions_applied is not None
            else (
                "credentials_omitted",
                "private_prompt_body_omitted",
                "sensitive_raw_material_omitted",
            )
        )
    )
    if any(not value for value in redactions) or len(redactions) != len(set(redactions)):
        raise ResearchContractError("redactions_applied must be unique non-empty strings")

    verification: dict[str, object] = {
        "status": verification_status,
        "verified_at": verified_at or retrieval_finished_at,
        "verifier": verifier.strip(),
        "material_claims": material_claims,
        "supported_material_claims": supported_material_claims,
        "resolvable_citations": resolvable_citations,
        "total_citations": total_citations,
        "primary_source_citations": primary_source_citations,
        "primary_source_ratio": primary_source_ratio,
    }
    if rejection_reasons:
        verification["rejection_reasons"] = sorted(set(rejection_reasons))
    durable_output: dict[str, object] = {
        "owner_repo": request.owner_repo,
        "report_path": request.report_ref,
        "receipt_path": request.receipt_ref,
        "raw_export_ref": request.raw_export_ref,
    }
    if tracked_output_safe is None:
        tracked_output_safe = False
    receipt = ResearchReceipt(
        receipt_id=_receipt_id(request.request_id),
        request_id=request.request_id,
        request_hash=stable_hash(request.canonical_contract()),
        catalog_hash=stable_hash(catalog),
        selected_profile=selected_profile,
        observed_provider=observed_provider,
        observed_model=observed_model,
        retrieval_started_at=retrieval_started_at,
        retrieval_finished_at=retrieval_finished_at,
        source_manifest_hash=source_manifest_hash or stable_hash([]),
        outcome_type=outcome_type,
        usage={
            "currency": "USD",
            "variable_cost": variable_cost_usd,
            "requests": requests,
            "computer_credits": computer_credits,
            "operator_handling_seconds": operator_handling_seconds,
            "usage_source": "not_exposed",
        },
        verification=verification,
        durable_output=durable_output,
        privacy={
            "preservation_tier": request.preservation_tier,
            "external_transmission": request.external_transmission,
            "tracked_output_safe": tracked_output_safe,
            "raw_export_disposition": _raw_export_disposition(request),
            "private_connected_sources_used": False,
            "redactions_applied": list(redactions),
        },
        sanitization={
            "contains_credentials": contains_credentials,
            "contains_private_prompt_body": contains_private_prompt_body,
            "contains_sensitive_raw_material": contains_sensitive_raw_material,
        },
    )
    assert_receipt_sanitized(receipt.public_dict(), private_question=request.question)
    return receipt


def render_research_prompt(request: ResearchRequest) -> str:
    freshness = canonical_json(request.freshness) if request.freshness else "current at execution time"
    domains = canonical_json(request.domain_constraints) if request.domain_constraints else "none"
    capabilities = ", ".join(request.required_capabilities)
    required_sections = ", ".join(request.required_sections) or "the normalization appendix below"
    owner_heading_lines = "\n".join(
        f"- `## {' '.join(word.capitalize() for word in section.split('_'))}` (normalized key: `{section}`)"
        for section in request.required_sections
    )
    if not owner_heading_lines:
        owner_heading_lines = "- None beyond the normalization appendix."
    return f"""# Limen Research commission: {request.request_id}

## Question

{request.question}

## Request constraints

- Required capabilities: {capabilities}
- Freshness: {freshness}
- Domain constraints: {domains}
- Preservation tier: {request.preservation_tier}
- External transmission: {request.external_transmission}
- Verification strength: {request.verification_level}
- Variable spend ceiling: USD {request.spend_ceiling_usd:.2f}
- Minimum primary-source citation ratio: {request.primary_source_ratio:.0%}
- Owner-required sections: {required_sections}

## Standing instructions

1. Prefer primary sources for material claims and use secondary sources only to interpret or triangulate.
2. Cite every material claim with a direct, resolvable source.
3. Separate sourced evidence, inference, and unknowns explicitly.
4. Name contradictions between credible sources without forcing false consensus.
5. Include negative searches and state when a requested fact could not be verified.
6. Preserve source title, URL, author or publisher, publication date, retrieval date, source type, quality tier, and locator.
7. Do not use connected private sources. Submit and retrieve only material allowed by the request's `{request.external_transmission}` declaration.
8. Do not schedule tasks, send messages, make purchases, connect services, or perform an external write.
9. Research mode must select its own models; do not claim or request a specific model.

## Owner-required answer headings

Include every heading below as an exact second-level Markdown heading. A heading may contain `None`,
but it may not be omitted.

{owner_heading_lines}

## Required normalization appendix

End with these exact second-level headings, even when content is `None`:

- `## Material Claims` — one bullet per claim:
  `[C1][material][evidence|inference][supported|partially_supported|contradicted|unsupported] ... [S1]`.
- `## Contradictions`
- `## Unknowns`
- `## Negative Searches` — one bullet per search:
  `- Query: ... | Surface: ... | Searched: YYYY-MM-DDTHH:MM:SSZ | Result count: 0 | Disposition: ...`.
- `## Novel Actionable Findings`
- `## Source Manifest` — one source per line:
  `- [S1] [Title](URL) | Publisher: ... | Published: YYYY-MM-DD or Unknown | Retrieved: YYYY-MM-DDTHH:MM:SSZ | Source Type: ... | Primary: provisional | Quality Tier: provisional | Locator: ...`.

The `Primary` and `Quality Tier` labels are provisional until Studium's Source Verifier independently
grades them. Return the completed answer as a Markdown Session export. Do not perform any
recommendation in the world.
"""


def _blocked(
    request: ResearchRequest,
    catalog: Mapping[str, Any],
    *,
    code: str,
    attempted_profiles: Sequence[str],
    failed_predicate: str,
    next_action: str,
    started_at: str,
    selected_profile: str,
) -> tuple[BlockedReceipt, ResearchReceipt]:
    finished_at = now()
    outcome = BlockedReceipt(
        request_id=request.request_id,
        blocker_code=code,
        attempted_profiles=tuple(sorted(set(attempted_profiles))),
        owner_surface=request.owner_repo,
        failed_predicate=failed_predicate,
        next_action=next_action,
        reversible_work_completed=("validated_request", "evaluated_profile_catalog"),
    )
    receipt = build_receipt(
        request,
        catalog,
        selected_profile=selected_profile,
        outcome_type=outcome.outcome_type,
        verification_status="rejected",
        retrieval_started_at=started_at,
        retrieval_finished_at=finished_at,
        rejection_reasons=(failed_predicate,),
    )
    return outcome, receipt


def prepare_research(
    request: ResearchRequest,
    catalog: Mapping[str, Any],
    *,
    prompt_ref: str,
    runtime_health: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[ManualHandoff | BlockedReceipt, ResearchReceipt]:
    started_at = now()
    profile, rejected = select_profile(request, catalog, runtime_health=runtime_health)
    if profile is None:
        attempted = tuple(rejected) or (request.preferred_profile or "provider_auto",)
        predicate = (
            "; ".join(f"{profile_id}={','.join(reasons)}" for profile_id, reasons in sorted(rejected.items()))
            or "no qualifying profile or reachable adapter"
        )
        return _blocked(
            request,
            catalog,
            code=blocker_code(rejected),
            attempted_profiles=attempted,
            failed_predicate=predicate,
            next_action="Refresh the owner catalog or satisfy its recorded health gate; do not substitute silently",
            started_at=started_at,
            selected_profile=request.preferred_profile or "provider_auto",
        )

    if profile.execution_kind != "manual_handoff" or profile.outcome_type != "ManualHandoff":
        return _blocked(
            request,
            catalog,
            code="provider_unreachable",
            attempted_profiles=(profile.profile_id,),
            failed_predicate=f"{profile.profile_id} live automation is deliberately unimplemented",
            next_action="Use an attended profile or implement and explicitly enable the owner-approved adapter",
            started_at=started_at,
            selected_profile=profile.profile_id,
        )

    if profile.variable_cost_usd is None:
        return _blocked(
            request,
            catalog,
            code="spend_ceiling",
            attempted_profiles=(profile.profile_id,),
            failed_predicate=f"{profile.profile_id} variable cost is unknown",
            next_action="Refresh the live cost observation before creating a handoff",
            started_at=started_at,
            selected_profile=profile.profile_id,
        )

    export_format = str(profile.guardrails.get("required_export_format") or "")
    project_name = str(profile.guardrails.get("project_name") or "").strip()
    launch_url = str(profile.guardrails.get("launch_url") or "").strip()
    standing_ref = str(profile.guardrails.get("standing_instructions_ref") or STANDING_INSTRUCTIONS_REF).strip()
    launch = urlparse(launch_url)
    if (
        export_format != "markdown"
        or not project_name
        or launch.scheme != "https"
        or not launch.netloc
        or not standing_ref
        or profile.execution_timeout_seconds is None
        or profile.guardrails.get("private_connected_sources_allowed") is not False
    ):
        return _blocked(
            request,
            catalog,
            code="missing_capability",
            attempted_profiles=(profile.profile_id,),
            failed_predicate=f"{profile.profile_id} lacks a safe attended-handoff contract",
            next_action="Repair the owner profile metadata; do not infer an attended surface",
            started_at=started_at,
            selected_profile=profile.profile_id,
        )

    attended = mapping(
        profile.health.get("attended") or {},
        field_name=f"profile {profile.profile_id}.health.attended",
    )
    deferred = tuple(str(item) for item in attended.get("checks_deferred") or ())
    operator_actions = (
        f"Open the attended {project_name} Project or Space",
        *(f"Confirm attended preflight: {item}" for item in deferred),
        "Select Research mode and submit the rendered prompt",
        "Export the completed Session answer as Markdown",
        "Place the export at the declared ingest destination",
    )
    prompt = render_research_prompt(request)
    outcome = ManualHandoff(
        request_id=request.request_id,
        selected_profile=profile.profile_id,
        preservation_tier=request.preservation_tier,
        external_transmission=request.external_transmission,
        project_name=project_name,
        launch_url=launch_url,
        prompt_ref=prompt_ref,
        standing_instructions_ref=standing_ref,
        required_export_format=export_format,
        execution_timeout_seconds=profile.execution_timeout_seconds,
        ingest_destination=request.raw_export_ref or request.report_ref,
        operator_actions=operator_actions,
        resume_predicate="The Markdown export exists at the declared ingest destination",
        rendered_prompt=prompt,
    )
    finished_at = now()
    receipt = build_receipt(
        request,
        catalog,
        selected_profile=profile.profile_id,
        outcome_type=outcome.outcome_type,
        verification_status="manual_pending",
        retrieval_started_at=started_at,
        retrieval_finished_at=finished_at,
        variable_cost_usd=profile.variable_cost_usd,
    )
    return outcome, receipt


def launch_attended_research(outcome: ManualHandoff) -> bool:
    """Open the attended surface only; never submit, schedule, or automate it."""

    return bool(webbrowser.open(outcome.launch_url, new=2))
