from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

import limen.research as research_runtime
from limen.cli import main
from limen.research import (
    BlockedReceipt,
    ManualHandoff,
    OutputSanitizationAttestation,
    ResearchContractError,
    ResearchRequest,
    SourceVerifierAttestation,
    ingest_markdown_export,
    load_document,
    owner_path,
    prepare_research,
    select_profile,
    stable_hash,
    verify_owner_root,
    verify_raw_export_custody,
)
from limen.research.handoff import build_receipt


REQUEST_ID = "SGO-REQ-2026-TEST-001"
CAPABILITIES = [
    "current_web_retrieval",
    "cited_synthesis",
    "claim_verification",
    "markdown_export",
]
REQUIRED_SECTIONS = [
    "material_claims",
    "contradictions",
    "unknowns",
    "negative_searches",
    "novel_actionable_findings",
    "source_manifest",
]


def request_payload(**overrides):
    payload = {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "commission_id": "INQ-2026-001",
        "requested_at": "2026-07-17T12:00:00Z",
        "question": "What changed, and what primary evidence supports it?",
        "context_refs": [{"owner_repo": "organvm/limen", "path": "docs/research-backend.md"}],
        "required_capabilities": CAPABILITIES,
        "freshness": {"as_of": "2026-07-17T12:00:00Z"},
        "domain_constraints": {
            "allow_domains": ["example.com", "standards.example"],
            "source_types": ["official_documentation"],
            "languages": ["en"],
        },
        "verification_strength": "primary_source",
        "preservation_tier": "operational_internal",
        "external_transmission": "public_only",
        "latency_ceiling_seconds": 1800,
        "spend_ceiling": {"currency": "USD", "variable_cost": 0},
        "output_contract": {
            "format": "markdown",
            "owner_repo": "organvm/limen",
            "report_path": "docs/research/test-result.md",
            "receipt_path": "docs/research/test-result.receipt.json",
            "raw_export_ref": "private-owner://limen/perplexity-exports/test-result.md",
            "required_sections": REQUIRED_SECTIONS,
        },
    }
    payload.update(overrides)
    return payload


def profile(
    *,
    state="enabled",
    kind="manual_handoff",
    outcome="ManualHandoff",
    capabilities=None,
    preservation_tiers=None,
    external_transmission=None,
    verification_strength="systematic",
    variable_cost_usd=0,
    execution_timeout_seconds=900,
    health=None,
    provider_ref=None,
    priority=0,
):
    return {
        "state": state,
        "activation": "on_demand",
        "execution_kind": kind,
        "outcome_type": outcome,
        "capabilities": capabilities or CAPABILITIES,
        "preservation_tiers": preservation_tiers or ["public_facing", "operational_internal"],
        "external_transmission": external_transmission or ["public_only", "sanitized_only"],
        "verification_strength": verification_strength,
        "variable_cost_usd": variable_cost_usd,
        "execution_timeout_seconds": execution_timeout_seconds,
        "provider_surface": "arbitrary_research_surface",
        "provider_ref": provider_ref,
        "priority": priority,
        "guardrails": {
            "project_name": "Limen Research",
            "required_export_format": "markdown",
            "standing_instructions_ref": "owner://standing-instructions.md",
            "launch_url": "https://www.perplexity.ai/",
            "private_connected_sources_allowed": False,
            "variable_spend_ceiling": variable_cost_usd,
        },
        "health": health
        or {
            "machine": {
                "required_profile_state": state,
                "request_compatibility_required": True,
                "owner_output_paths_required": True,
                "required_export_format": "markdown",
                "maximum_variable_cost_usd": variable_cost_usd,
                "enforce_execution_timeout": True,
            },
            "attended": {
                "disposition": "defer_to_manual_handoff",
                "live_authentication_asserted": False,
                "checks_deferred": ["authenticated_session_available"],
            },
            "failure_outcome": "ManualHandoff",
        },
    }


def api_profile(*, state="enabled", variable_cost_usd=0):
    return profile(
        state=state,
        kind="automated_adapter",
        outcome="EvidencePacket",
        variable_cost_usd=variable_cost_usd,
        health={
            "machine": {
                "required_profile_state": "enabled",
                "credential_presence_required": True,
                "api_credit_state_required": "funded",
                "automatic_top_up_state_required": "off",
                "live_pricing_required": True,
                "projected_cost_required": True,
                "projected_cost_within_request_ceiling_required": True,
            },
            "attended": {
                "disposition": "not_applicable",
                "live_authentication_asserted": False,
                "checks_deferred": [],
            },
            "failure_outcome": "BlockedReceipt",
        },
    )


def catalog(profiles=None, adapters=None):
    result = {
        "schema_version": "1.0",
        "registry_id": "fixture-research-backends",
        "profiles": profiles or {"pro_research": profile()},
    }
    if adapters is not None:
        result["adapters"] = adapters
    return result


def valid_export(*, retrieved=True, broken_source=False, lost_source=False):
    first_retrieval = "2026-07-17T12:20:00Z" if retrieved else ""
    third_claim = (
        "- [C3][material][evidence][supported] The missing record supports this claim. [S3]"
        if lost_source
        else "- [C3][unknown] No additional supported claim was established."
    )
    primary_url = "https://broken.example/missing" if broken_source else "https://example.com/primary"
    return f"""# Research result

## Material Claims

- [C1][material][evidence][supported] The primary source records the change. [S1]
- [C2][material][evidence][supported] A second primary source corroborates it. [S2]
{third_claim}

## Contradictions

None

## Unknowns

- The implementation timing remains unknown.

## Negative Searches

- Query: official rollback notice | Surface: first-party docs | Searched: 2026-07-17T12:22:00Z | Result count: 0 | Disposition: no official rollback notice found

## Novel Actionable Findings

- Add a live standards-change check before future dispatch.

## Source Manifest

- [S1] [Primary record]({primary_url}) | Publisher: Example Authority | Published: 2026-07-16 | Retrieved: {first_retrieval} | Source Type: provisional | Primary: provisional | Quality Tier: provisional | Locator: section 2
- [S2] [Primary standard](https://standards.example/spec) | Publisher: Standards Body | Published: 2026-07-15 | Retrieved: 2026-07-17T12:21:00Z | Source Type: provisional | Primary: provisional | Quality Tier: provisional | Locator: change log
"""


def valid_attestation(
    *,
    first_status="supported",
    second_primary=True,
    first_url="https://example.com/primary",
    first_resolvable=True,
):
    return {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "verified_at": "2026-07-17T12:30:00Z",
        "verifier": "Studium Source Verifier",
        "verdict": "accepted" if first_status == "supported" else "rejected",
        "private_connected_sources_used": False,
        "claims": [
            {
                "claim_id": "CLM-C1",
                "verification_status": first_status,
                "source_ids": ["SRC-S1"],
            },
            {
                "claim_id": "CLM-C2",
                "verification_status": "supported",
                "source_ids": ["SRC-S2"],
            },
            {
                "claim_id": "CLM-C3",
                "verification_status": "not_applicable",
                "source_ids": [],
            },
        ],
        "sources": [
            {
                "source_id": "SRC-S1",
                "url": first_url,
                "resolvable": first_resolvable,
                "source_type": "official_documentation",
                "primary_source": True,
                "quality_tier": "A",
                "metadata_confirmed": True,
                "language": "en",
                "jurisdictions": [],
            },
            {
                "source_id": "SRC-S2",
                "url": "https://standards.example/spec",
                "resolvable": True,
                "source_type": "official_documentation",
                "primary_source": second_primary,
                "quality_tier": "A" if second_primary else "B",
                "metadata_confirmed": True,
                "language": "en",
                "jurisdictions": [],
            },
        ],
    }


def valid_sanitization(markdown=None, **overrides):
    payload = {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "attested_at": "2026-07-17T12:31:00Z",
        "attestor": "Studium Output Sanitizer",
        "export_hash": stable_hash(markdown if markdown is not None else valid_export()),
        "preservation_tier": "operational_internal",
        "external_transmission": "public_only",
        "tracked_output_safe": True,
        "contains_credentials": False,
        "contains_private_prompt_body": False,
        "contains_sensitive_raw_material": False,
        "redactions_applied": [],
    }
    payload.update(overrides)
    return payload


def handoff_for(request, registry):
    outcome, receipt = prepare_research(request, registry, prompt_ref=f"{REQUEST_ID}.prompt.md")
    assert isinstance(outcome, ManualHandoff)
    return outcome, receipt.public_dict()


def ingest_valid(request=None, registry=None, markdown=None, **kwargs):
    request = request or ResearchRequest.from_mapping(request_payload())
    registry = registry or catalog()
    markdown = markdown if markdown is not None else valid_export()
    _, handoff = handoff_for(request, registry)
    return ingest_markdown_export(
        markdown,
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(),
        sanitization_attestation=valid_sanitization(
            markdown,
            preservation_tier=request.preservation_tier,
            external_transmission=request.external_transmission,
        ),
        **kwargs,
    )


def test_request_uses_canonical_owner_names_and_hashes_exact_source_payload():
    payload = request_payload()
    request = ResearchRequest.from_mapping(payload)
    public = request.public_contract()

    assert request.preservation_tier == "operational_internal"
    assert request.canonical_contract() == payload
    assert stable_hash(request.canonical_contract()) == stable_hash(payload)
    assert request.question not in json.dumps(public)
    assert public["question_hash"].startswith("sha256:")


def test_request_rejects_owner_schema_type_and_semantic_drift():
    invalid_payloads = []

    scalar_capabilities = request_payload()
    scalar_capabilities["required_capabilities"] = "current_web_retrieval"
    invalid_payloads.append(scalar_capabilities)

    scalar_sections = request_payload()
    scalar_sections["output_contract"]["required_sections"] = "source_manifest"
    invalid_payloads.append(scalar_sections)

    numeric_question = request_payload()
    numeric_question["question"] = 1234567890
    invalid_payloads.append(numeric_question)

    numeric_latency = request_payload()
    numeric_latency["latency_ceiling_seconds"] = "1800"
    invalid_payloads.append(numeric_latency)

    numeric_spend = request_payload()
    numeric_spend["spend_ceiling"]["variable_cost"] = "0"
    invalid_payloads.append(numeric_spend)

    numeric_owner = request_payload()
    numeric_owner["output_contract"]["owner_repo"] = 123
    invalid_payloads.append(numeric_owner)

    empty_freshness = request_payload()
    empty_freshness["freshness"] = {}
    invalid_payloads.append(empty_freshness)

    reverse_freshness = request_payload()
    reverse_freshness["freshness"] = {
        "published_after": "2026-07-17",
        "published_before": "2024-01-01",
    }
    invalid_payloads.append(reverse_freshness)

    scalar_domains = request_payload()
    scalar_domains["domain_constraints"]["allow_domains"] = "example.com"
    invalid_payloads.append(scalar_domains)

    invalid_language = request_payload()
    invalid_language["domain_constraints"]["languages"] = ["english"]
    invalid_payloads.append(invalid_language)

    tilde_path = request_payload()
    tilde_path["output_contract"]["report_path"] = "~private/report.md"
    invalid_payloads.append(tilde_path)

    for payload in invalid_payloads:
        with pytest.raises(ResearchContractError):
            ResearchRequest.from_mapping(payload)


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://example.com/catalog.yaml",
        "https://user:password@example.com/catalog.yaml",
        "https://localhost/catalog.yaml",
        "https://127.0.0.1/catalog.yaml",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_load_document_rejects_non_https_userinfo_and_private_hosts(monkeypatch, unsafe_url):
    def unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("unsafe remote document must be rejected before fetch")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_fetch)
    with pytest.raises(ResearchContractError, match="public|HTTPS"):
        load_document(unsafe_url)


def test_load_document_requires_public_dns_and_strict_mapping(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def read():
            return b"registry_id: fixture\n"

    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())

    assert load_document("https://example.com/catalog.yaml") == {"registry_id": "fixture"}
    with pytest.raises(ResearchContractError, match="JSON object"):
        load_document({1: "coerced keys are forbidden"})

    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("10.0.0.4", 443))],
    )
    with pytest.raises(ResearchContractError, match="public addresses"):
        load_document("https://internal.example/catalog.yaml")


def test_legacy_privacy_name_and_private_transmission_are_rejected():
    legacy = request_payload()
    legacy["privacy_class"] = "tracked_internal"
    with pytest.raises(ResearchContractError, match="unknown ResearchRequest"):
        ResearchRequest.from_mapping(legacy)

    with pytest.raises(ResearchContractError, match="forbid external transmission"):
        ResearchRequest.from_mapping(
            request_payload(
                preservation_tier="client_private",
                external_transmission="public_only",
            )
        )

    private = request_payload(
        preservation_tier="client_private",
        external_transmission="forbidden",
    )
    private["output_contract"] = {
        **private["output_contract"],
        "raw_export_ref": "local/export.md",
    }
    with pytest.raises(ResearchContractError, match="private-owner"):
        ResearchRequest.from_mapping(private)

    private["output_contract"]["raw_export_ref"] = None
    assert ResearchRequest.from_mapping(private).preservation_tier == "client_private"


def test_profile_selection_is_order_independent_and_capability_based():
    request = ResearchRequest.from_mapping(request_payload())
    alpha = profile(verification_strength="primary_source", execution_timeout_seconds=600)
    renamed = profile(verification_strength="systematic", execution_timeout_seconds=300)

    first, _ = select_profile(request, catalog({"alpha_adapter": alpha, "renamed_x": renamed}))
    second, _ = select_profile(request, catalog({"renamed_x": renamed, "alpha_adapter": alpha}))

    assert first and second
    assert first.profile_id == second.profile_id == "renamed_x"


def test_catalog_add_remove_and_provider_auto_need_no_code_change():
    request = ResearchRequest.from_mapping(request_payload())
    base, _ = select_profile(request, catalog({"alpha_adapter": profile()}))
    expanded, _ = select_profile(
        request,
        catalog(
            {
                "alpha_adapter": profile(verification_strength="primary_source"),
                "beta_adapter": profile(verification_strength="systematic"),
            }
        ),
    )
    auto_request = request.with_profile("provider_auto")
    selector = profile(
        kind="capability_discovery",
        outcome="selected_adapter",
        variable_cost_usd=None,
    )
    adapters = {
        "vendor_zeta": profile(provider_ref="vendor_zeta", verification_strength="primary_source"),
        "renamed_provider": profile(
            provider_ref="renamed_provider",
            verification_strength="systematic",
        ),
    }
    auto, rejected = select_profile(
        auto_request,
        catalog({"provider_auto": selector}, adapters),
    )

    assert base and base.profile_id == "alpha_adapter"
    assert expanded and expanded.profile_id == "beta_adapter"
    assert not rejected
    assert auto and auto.profile_id == "renamed_provider"


def test_catalog_fails_closed_on_missing_privacy_or_fixed_model_fields():
    request = ResearchRequest.from_mapping(request_payload())
    missing = profile()
    missing.pop("preservation_tiers")
    with pytest.raises(ResearchContractError, match="must declare"):
        select_profile(request, catalog({"bad_profile": missing}))

    pinned = profile()
    pinned["model_id"] = "fixed-model"
    with pytest.raises(ResearchContractError, match="unknown fields|fixed-model"):
        select_profile(request, catalog({"bad_profile": pinned}))


def test_nested_computer_health_requires_live_credit_refill_and_value_case():
    request = ResearchRequest.from_mapping(request_payload())
    computer = profile(
        health={
            "machine": {
                "required_profile_state": "enabled",
                "live_computer_credit_balance_required": True,
                "automatic_refill_state_required": "off",
                "separate_value_case_required": True,
            },
            "attended": {
                "disposition": "defer_to_manual_handoff",
                "live_authentication_asserted": False,
                "checks_deferred": ["computer_surface_reachable"],
            },
            "failure_outcome": "BlockedReceipt",
        }
    )
    blocked, rejected = select_profile(request, catalog({"pro_computer": computer}))
    selected, _ = select_profile(
        request,
        catalog({"pro_computer": computer}),
        runtime_health={
            "pro_computer": {
                "live_computer_credit_balance": 5,
                "automatic_refill_state": "off",
                "separate_value_case_confirmed": True,
            }
        },
    )

    assert blocked is None
    assert "health:computer_credits_unverified" in rejected["pro_computer"]
    assert selected and selected.profile_id == "pro_computer"


def test_missing_api_health_attestation_does_not_disable_attended_pro():
    request = ResearchRequest.from_mapping(request_payload())
    registry = catalog({"pro_research": profile(), "api_search": api_profile()})
    outcome, receipt = prepare_research(request, registry, prompt_ref="prompt.md")

    assert isinstance(outcome, ManualHandoff)
    assert receipt.selected_profile == "pro_research"


def test_api_is_credential_gated_and_execution_remains_unimplemented():
    request = ResearchRequest.from_mapping(request_payload()).with_profile("api_search")
    registry = catalog({"api_search": api_profile()})
    missing, _ = prepare_research(request, registry, prompt_ref="prompt.md")
    assert isinstance(missing, BlockedReceipt)
    assert missing.blocker_code == "missing_credential"

    health = {
        "api_search": {
            "credential_present": True,
            "api_credit_state": "funded",
            "automatic_top_up_state": "off",
            "live_pricing_confirmed": True,
            "projected_cost_usd": 0,
            "adapter_enabled": True,
        }
    }
    blocked, receipt = prepare_research(
        request,
        registry,
        prompt_ref="prompt.md",
        runtime_health=health,
    )
    assert isinstance(blocked, BlockedReceipt)
    assert "deliberately unimplemented" in blocked.failed_predicate
    assert "credential_present" not in json.dumps(receipt.public_dict())


def test_renamed_api_adapter_uses_injected_health_not_vendor_environment(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "sk-proj-012345678901234567890123456789")
    request = ResearchRequest.from_mapping(request_payload()).with_profile("renamed_adapter")
    registry = catalog({"renamed_adapter": api_profile()})

    missing, _ = prepare_research(request, registry, prompt_ref="prompt.md")
    selected, _ = select_profile(
        request,
        registry,
        runtime_health={
            "renamed_adapter": {
                "credential_present": True,
                "api_credit_state": "funded",
                "automatic_top_up_state": "off",
                "live_pricing_confirmed": True,
                "projected_cost_usd": 0,
                "adapter_enabled": True,
            }
        },
    )

    assert isinstance(missing, BlockedReceipt)
    assert missing.blocker_code == "missing_credential"
    assert selected and selected.profile_id == "renamed_adapter"


def test_manual_handoff_and_receipt_match_owner_contract_surface():
    request = ResearchRequest.from_mapping(request_payload())
    outcome, receipt = prepare_research(request, catalog(), prompt_ref="prompt.md")

    assert isinstance(outcome, ManualHandoff)
    assert set(outcome.public_dict()) == {
        "schema_version",
        "outcome_type",
        "request_id",
        "selected_profile",
        "preservation_tier",
        "external_transmission",
        "status",
        "project_name",
        "launch_url",
        "prompt_ref",
        "standing_instructions_ref",
        "required_export_format",
        "execution_timeout_seconds",
        "ingest_destination",
        "operator_actions",
        "resume_predicate",
    }
    assert request.question in outcome.rendered_prompt
    assert request.question not in json.dumps(outcome.public_dict())
    assert receipt.privacy["preservation_tier"] == "operational_internal"
    assert receipt.privacy["external_transmission"] == "public_only"
    assert receipt.privacy["private_connected_sources_used"] is False
    assert receipt.privacy["tracked_output_safe"] is False
    assert receipt.catalog_hash == stable_hash(catalog())


def test_missing_capability_returns_blocked_receipt():
    request = ResearchRequest.from_mapping(
        request_payload(required_capabilities=[*CAPABILITIES, "unavailable_capability"])
    )
    outcome, receipt = prepare_research(request, catalog(), prompt_ref="prompt.md")

    assert isinstance(outcome, BlockedReceipt)
    assert outcome.blocker_code == "missing_capability"
    assert receipt.verification["status"] == "rejected"
    assert receipt.privacy["tracked_output_safe"] is False


def test_valid_export_requires_and_uses_independent_source_verifier_attestation():
    outcome, receipt = ingest_valid(observed_provider="perplexity")

    assert isinstance(outcome, dict)
    assert outcome["outcome_type"] == "EvidencePacket"
    assert outcome["claims"][0]["verification_status"] == "supported"
    assert outcome["sources"][0]["source_type"] == "official_documentation"
    assert outcome["sources"][0]["primary_source"] is True
    assert "Studium Source Verifier attestation sha256:" in receipt.verification["verifier"]
    assert receipt.verification["primary_source_ratio"] == 1.0
    assert receipt.privacy["tracked_output_safe"] is True


def test_schema_valid_attestation_names_fit_receipt_verifier_bound():
    request = ResearchRequest.from_mapping(request_payload())
    registry = catalog()
    markdown = valid_export()
    _, handoff = handoff_for(request, registry)
    long_name = "V" * 120
    verification = valid_attestation()
    verification["verifier"] = long_name
    accepted, accepted_receipt = ingest_markdown_export(
        markdown,
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=verification,
        sanitization_attestation=valid_sanitization(markdown),
    )
    rejected, rejected_receipt = ingest_markdown_export(
        markdown,
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation={},
        sanitization_attestation=valid_sanitization(markdown, attestor=long_name),
    )

    assert isinstance(accepted, dict)
    assert accepted_receipt.verification["verifier"].startswith(long_name)
    assert isinstance(rejected, BlockedReceipt)
    assert rejected_receipt.verification["verifier"].startswith(long_name)


def test_provider_self_support_label_cannot_override_verifier_rejection():
    request = ResearchRequest.from_mapping(request_payload())
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    markdown = valid_export().replace("The primary source records the change.", "The Moon is made of cheese.")
    outcome, _ = ingest_markdown_export(
        markdown,
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(first_status="unsupported"),
        sanitization_attestation=valid_sanitization(markdown),
    )

    assert isinstance(outcome, BlockedReceipt)
    assert "source_verifier_rejected" in outcome.failed_predicate
    assert "unsupported_claim:CLM-C1:unsupported" in outcome.failed_predicate


def test_missing_or_mismatched_verifier_attestation_is_rejected():
    request = ResearchRequest.from_mapping(request_payload())
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    missing, _ = ingest_markdown_export(
        valid_export(),
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation={},
        sanitization_attestation=valid_sanitization(),
    )
    mismatched = valid_attestation()
    mismatched["claims"][0]["source_ids"] = ["SRC-S2"]
    wrong, _ = ingest_markdown_export(
        valid_export(),
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=mismatched,
        sanitization_attestation=valid_sanitization(),
    )

    assert isinstance(missing, BlockedReceipt)
    assert "source_verifier_attestation" in missing.failed_predicate
    assert isinstance(wrong, BlockedReceipt)
    assert "source_verifier_claim_sources_mismatch:CLM-C1" in wrong.failed_predicate


def test_url_reachability_comes_only_from_bound_verifier_attestation(monkeypatch):
    request = ResearchRequest.from_mapping(request_payload())
    registry = catalog()
    _, handoff = handoff_for(request, registry)

    def unexpected_network(*_args, **_kwargs):
        raise AssertionError("ingest must not perform network I/O")

    monkeypatch.setattr("socket.getaddrinfo", unexpected_network)
    monkeypatch.setattr("urllib.request.urlopen", unexpected_network)
    accepted, _ = ingest_markdown_export(
        valid_export(),
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(),
        sanitization_attestation=valid_sanitization(),
    )
    rejected, _ = ingest_markdown_export(
        valid_export(),
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(first_resolvable=False),
        sanitization_attestation=valid_sanitization(),
    )

    assert isinstance(accepted, dict)
    assert isinstance(rejected, BlockedReceipt)
    assert "broken_citation:SRC-S1" in rejected.failed_predicate


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "https://user:password@example.com/primary",
        "http://127.0.0.1/internal",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_unsafe_citation_references_are_rejected_without_fetching(unsafe_url):
    request = ResearchRequest.from_mapping(request_payload())
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    markdown = valid_export().replace("https://example.com/primary", unsafe_url)
    outcome, _ = ingest_markdown_export(
        markdown,
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(first_url=unsafe_url),
        sanitization_attestation=valid_sanitization(markdown),
    )

    assert isinstance(outcome, BlockedReceipt)
    assert "unsafe_citation_url:SRC-S1" in outcome.failed_predicate


def test_output_sanitization_attestation_is_bound_and_machine_checked():
    request = ResearchRequest.from_mapping(request_payload())
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    markdown = valid_export().replace(
        "The primary source records the change.",
        "api_key = supersecretvalue",
    )
    outcome, receipt = ingest_markdown_export(
        markdown,
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(),
        sanitization_attestation=valid_sanitization(markdown),
    )
    mismatched, _ = ingest_markdown_export(
        valid_export(),
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(),
        sanitization_attestation=valid_sanitization(valid_export(), export_hash=stable_hash("different")),
    )
    missing, missing_receipt = ingest_markdown_export(
        valid_export(),
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(),
        sanitization_attestation={},
    )

    assert isinstance(outcome, BlockedReceipt)
    assert "credential-like material" in outcome.failed_predicate
    assert receipt.privacy["tracked_output_safe"] is False
    assert "supersecretvalue" not in json.dumps(receipt.public_dict())
    assert isinstance(mismatched, BlockedReceipt)
    assert "export_hash mismatch" in mismatched.failed_predicate
    assert isinstance(missing, BlockedReceipt)
    assert missing_receipt.privacy["tracked_output_safe"] is False


def test_private_raw_export_may_echo_question_when_tracked_packet_does_not():
    request = ResearchRequest.from_mapping(request_payload())
    markdown = f"{request.question}\n\n{valid_export()}"
    outcome, receipt = ingest_valid(request=request, markdown=markdown)

    assert isinstance(outcome, dict)
    assert request.question not in json.dumps(outcome)
    assert request.question not in json.dumps(receipt.public_dict())


def test_raw_prompt_echo_requires_private_owner_custody():
    payload = request_payload()
    payload["output_contract"]["raw_export_ref"] = "raw/session.md"
    request = ResearchRequest.from_mapping(payload)
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    markdown = f"{request.question}\n\n{valid_export()}"
    outcome, receipt = ingest_markdown_export(
        markdown,
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(),
        sanitization_attestation=valid_sanitization(markdown),
    )

    assert isinstance(outcome, BlockedReceipt)
    assert outcome.blocker_code == "privacy_mismatch"
    assert "requires private-owner custody" in outcome.failed_predicate
    assert receipt.privacy["tracked_output_safe"] is False


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        (valid_export(retrieved=False), "source_metadata:SRC-S1:retrieved_at"),
        (valid_export(broken_source=True), "broken_citation:SRC-S1"),
        (valid_export(lost_source=True), "lost_source_metadata:CLM-C3:SRC-S3"),
    ],
)
def test_invalid_exports_are_rejected(markdown, expected):
    request = ResearchRequest.from_mapping(request_payload())
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    attestation = valid_attestation()
    if "broken.example" in markdown:
        attestation["sources"][0]["url"] = "https://broken.example/missing"
        attestation["sources"][0]["resolvable"] = False
    if "S3" in markdown:
        attestation["claims"][2] = {
            "claim_id": "CLM-C3",
            "verification_status": "supported",
            "source_ids": ["SRC-S3"],
        }
    outcome, receipt = ingest_markdown_export(
        markdown,
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=attestation,
        sanitization_attestation=valid_sanitization(markdown),
    )

    assert isinstance(outcome, BlockedReceipt)
    assert expected in outcome.failed_predicate
    assert receipt.verification["status"] == "rejected"


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        (
            valid_export().replace(
                "- [C2][material][evidence][supported]",
                "- [C1][material][evidence][supported]",
            ),
            "duplicate_claim_id:CLM-C1",
        ),
        (
            valid_export().replace(
                "- [S2] [Primary standard]",
                "- [S1] [Primary standard]",
            ),
            "duplicate_source_id:SRC-S1",
        ),
        (
            valid_export().replace("Result count: 0", "Result count: 3"),
            "invalid_negative_search_result_count:3",
        ),
    ],
)
def test_ambiguous_or_nonnegative_evidence_rows_are_rejected(markdown, expected):
    outcome, receipt = ingest_valid(markdown=markdown)

    assert isinstance(outcome, BlockedReceipt)
    assert expected in outcome.failed_predicate
    assert receipt.verification["status"] == "rejected"


def test_historical_iso_publication_dates_are_accepted():
    markdown = valid_export().replace("Published: 2026-07-16", "Published: 1999-12-31")
    outcome, receipt = ingest_valid(markdown=markdown)

    assert isinstance(outcome, dict)
    assert outcome["sources"][0]["published_at"] == "1999-12-31"
    assert receipt.verification["status"] == "accepted"


def test_domain_source_type_and_publication_constraints_are_enforced():
    payload = request_payload()
    payload["freshness"] = {
        "published_after": "2026-07-17",
        "published_before": "2026-07-17",
    }
    payload["domain_constraints"] = {
        "allow_domains": ["allowed.example"],
        "source_types": ["peer_reviewed_primary_research"],
        "languages": ["en"],
    }
    request = ResearchRequest.from_mapping(payload)
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    outcome, _ = ingest_markdown_export(
        valid_export(),
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(),
        sanitization_attestation=valid_sanitization(),
    )

    assert isinstance(outcome, BlockedReceipt)
    assert "domain_not_allowed:SRC-S1:example.com" in outcome.failed_predicate
    assert "source_type_not_allowed:SRC-S1:official_documentation" in outcome.failed_predicate
    assert "published_before_window:SRC-S1" in outcome.failed_predicate


def test_primary_ratio_counts_claim_source_edges_not_unique_sources():
    request = ResearchRequest.from_mapping(request_payload())
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    claims = [
        "- [C1][material][evidence][supported] Primary edge. [S1]",
        *[f"- [C{index}][material][evidence][supported] Secondary edge {index}. [S2]" for index in range(2, 12)],
    ]
    markdown = valid_export().replace(
        "- [C1][material][evidence][supported] The primary source records the change. [S1]\n"
        "- [C2][material][evidence][supported] A second primary source corroborates it. [S2]\n"
        "- [C3][unknown] No additional supported claim was established.",
        "\n".join(claims),
    )
    attestation = valid_attestation(second_primary=False)
    attestation["claims"] = [
        {
            "claim_id": "CLM-C1",
            "verification_status": "supported",
            "source_ids": ["SRC-S1"],
        },
        *[
            {
                "claim_id": f"CLM-C{index}",
                "verification_status": "supported",
                "source_ids": ["SRC-S2"],
            }
            for index in range(2, 12)
        ],
    ]
    outcome, receipt = ingest_markdown_export(
        markdown,
        request,
        registry,
        handoff_receipt=handoff,
        verification_attestation=attestation,
        sanitization_attestation=valid_sanitization(markdown),
    )

    assert isinstance(outcome, BlockedReceipt)
    assert "primary_source_ratio:0.091<0.800" in outcome.failed_predicate
    assert receipt.verification["total_citations"] == 11


def test_stale_or_removed_handoff_profile_is_rejected():
    request = ResearchRequest.from_mapping(request_payload())
    original = catalog()
    _, handoff = handoff_for(request, original)
    replacement = catalog({"replacement": profile()})
    stale, _ = ingest_markdown_export(
        valid_export(),
        request,
        replacement,
        handoff_receipt=handoff,
        verification_attestation=valid_attestation(),
        sanitization_attestation=valid_sanitization(),
    )
    forged = deepcopy(handoff)
    forged["catalog_hash"] = stable_hash(replacement)
    removed, _ = ingest_markdown_export(
        valid_export(),
        request,
        replacement,
        handoff_receipt=forged,
        verification_attestation=valid_attestation(),
        sanitization_attestation=valid_sanitization(),
    )

    assert isinstance(stale, BlockedReceipt)
    assert "handoff_catalog_hash_mismatch" in stale.failed_predicate
    assert isinstance(removed, BlockedReceipt)
    assert "handoff_profile_unavailable" in removed.failed_predicate


def test_observed_provider_and_model_reject_secret_shaped_values():
    with pytest.raises(ResearchContractError, match="safe observed identifier"):
        ingest_valid(observed_model="sk-proj-012345678901234567890123456789")


@pytest.mark.parametrize(
    "overrides",
    [
        {"variable_cost_usd": 1},
        {"material_claims": 1, "supported_material_claims": 2},
        {"total_citations": 1, "resolvable_citations": 2},
        {"total_citations": 1, "primary_source_citations": 1, "primary_source_ratio": 0},
        {
            "retrieval_started_at": "2026-07-17T12:30:00Z",
            "retrieval_finished_at": "2026-07-17T12:00:00Z",
        },
    ],
)
def test_receipt_builder_rejects_impossible_semantics(overrides):
    request = ResearchRequest.from_mapping(request_payload())
    arguments = {
        "selected_profile": "pro_research",
        "outcome_type": "BlockedReceipt",
        "verification_status": "rejected",
        "retrieval_started_at": "2026-07-17T12:00:00Z",
        "retrieval_finished_at": "2026-07-17T12:30:00Z",
    }
    arguments.update(overrides)
    with pytest.raises(ResearchContractError):
        build_receipt(request, catalog(), **arguments)


def init_owner_repo(path: Path, slug="organvm/limen"):
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", f"https://github.com/{slug}.git"],
        check=True,
    )


def test_owner_root_and_private_raw_export_custody_are_proven(tmp_path):
    request = ResearchRequest.from_mapping(request_payload())
    owner = tmp_path / "owner"
    init_owner_repo(owner)
    verified = verify_owner_root(owner, request)
    private_root = tmp_path / "private-owner"
    private_export = private_root / "perplexity-exports" / "test-result.md"
    private_export.parent.mkdir(parents=True)
    private_export.write_text("export")
    wrong_export = private_root / "wrong.md"
    wrong_export.write_text("export")

    verify_raw_export_custody(
        private_export,
        verified,
        request,
        raw_owner_root=private_root,
    )
    with pytest.raises(ResearchContractError, match="designated raw-owner-root"):
        verify_raw_export_custody(private_export, verified, request)
    with pytest.raises(ResearchContractError, match="designated owner reference"):
        verify_raw_export_custody(
            wrong_export,
            verified,
            request,
            raw_owner_root=private_root,
        )

    tracked_payload = request_payload()
    tracked_payload["output_contract"]["raw_export_ref"] = "raw/export.md"
    tracked_request = ResearchRequest.from_mapping(tracked_payload)
    tracked_export = owner / "raw" / "export.md"
    tracked_export.parent.mkdir()
    tracked_export.write_text("export")
    verify_raw_export_custody(tracked_export, verified, tracked_request)
    with pytest.raises(ResearchContractError, match="does not match"):
        verify_raw_export_custody(wrong_export, verified, tracked_request)

    wrong = tmp_path / "wrong"
    init_owner_repo(wrong, "organvm/not-limen")
    with pytest.raises(ResearchContractError, match="does not match"):
        verify_owner_root(wrong, request)


def test_owner_path_rejects_escape(tmp_path):
    with pytest.raises(ResearchContractError, match="escapes owner root"):
        owner_path(tmp_path, "../outside.json")


def test_cli_prepare_writes_prompt_and_schema_shaped_handoff(tmp_path):
    request_path = tmp_path / "request.yaml"
    catalog_path = tmp_path / "catalog.yaml"
    work_dir = tmp_path / "handoff"
    payload = request_payload()
    request_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    catalog_path.write_text(yaml.safe_dump(catalog(), sort_keys=False))

    result = CliRunner().invoke(
        main,
        [
            "research",
            "prepare",
            str(request_path),
            "--catalog",
            str(catalog_path),
            "--work-dir",
            str(work_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    prompt = (work_dir / f"{REQUEST_ID}.prompt.md").read_text()
    outcome = json.loads((work_dir / f"{REQUEST_ID}.outcome.json").read_text())
    receipt = (work_dir / f"{REQUEST_ID}.receipt.json").read_text()
    assert payload["question"] in prompt
    assert payload["question"] not in receipt
    assert outcome["launch_url"] == "https://www.perplexity.ai/"
    assert outcome["execution_timeout_seconds"] == 900


@pytest.mark.parametrize(
    "report_path",
    [
        "docs/research/test-result.md",
        "docs/research/test-result.json",
    ],
)
def test_cli_ingest_uses_contract_format_before_terminal_receipt(tmp_path, report_path):
    owner = tmp_path / "owner"
    init_owner_repo(owner)
    payload = request_payload()
    payload["output_contract"]["report_path"] = report_path
    request = ResearchRequest.from_mapping(payload)
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    request_path = tmp_path / "request.yaml"
    catalog_path = tmp_path / "catalog.yaml"
    handoff_path = tmp_path / "handoff.json"
    verification_path = tmp_path / "verification.json"
    sanitization_path = tmp_path / "sanitization.json"
    private_root = tmp_path / "private-owner"
    export_path = private_root / "perplexity-exports" / "test-result.md"
    export_path.parent.mkdir(parents=True)
    request_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    catalog_path.write_text(yaml.safe_dump(registry, sort_keys=False))
    handoff_path.write_text(json.dumps(handoff))
    verification_path.write_text(json.dumps(valid_attestation()))
    export_path.write_text(valid_export())
    sanitization_path.write_text(json.dumps(valid_sanitization()))
    result = CliRunner().invoke(
        main,
        [
            "research",
            "ingest",
            str(export_path),
            str(request_path),
            "--catalog",
            str(catalog_path),
            "--owner-root",
            str(owner),
            "--handoff-receipt",
            str(handoff_path),
            "--verification-file",
            str(verification_path),
            "--sanitization-file",
            str(sanitization_path),
            "--raw-owner-root",
            str(private_root),
            "--operator-handling-seconds",
            "600",
        ],
    )

    report = owner / payload["output_contract"]["report_path"]
    receipt = owner / payload["output_contract"]["receipt_path"]
    assert result.exit_code == 0, result.output
    assert report.is_file()
    assert report.read_text().startswith("# Evidence Packet")
    assert receipt.is_file()
    assert json.loads(receipt.read_text())["verification"]["status"] == "accepted"


def test_cli_blocked_outcome_is_written_before_terminal_receipt(tmp_path, monkeypatch):
    owner = tmp_path / "owner"
    init_owner_repo(owner)
    payload = request_payload()
    request = ResearchRequest.from_mapping(payload)
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    request_path = tmp_path / "request.yaml"
    catalog_path = tmp_path / "catalog.yaml"
    handoff_path = tmp_path / "handoff.json"
    verification_path = tmp_path / "verification.json"
    sanitization_path = tmp_path / "sanitization.json"
    private_root = tmp_path / "private-owner"
    export_path = private_root / "perplexity-exports" / "test-result.md"
    export_path.parent.mkdir(parents=True)
    request_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    catalog_path.write_text(yaml.safe_dump(registry, sort_keys=False))
    handoff_path.write_text(json.dumps(handoff))
    verification_path.write_text(json.dumps(valid_attestation(first_resolvable=False)))
    export_path.write_text(valid_export())
    sanitization_path.write_text(json.dumps(valid_sanitization()))

    writes = []
    real_write_json = research_runtime.write_json

    def observed_write(path, value):
        writes.append(path)
        real_write_json(path, value)

    monkeypatch.setattr(research_runtime, "write_json", observed_write)
    result = CliRunner().invoke(
        main,
        [
            "research",
            "ingest",
            str(export_path),
            str(request_path),
            "--catalog",
            str(catalog_path),
            "--owner-root",
            str(owner),
            "--handoff-receipt",
            str(handoff_path),
            "--verification-file",
            str(verification_path),
            "--sanitization-file",
            str(sanitization_path),
            "--raw-owner-root",
            str(private_root),
            "--operator-handling-seconds",
            "600",
        ],
    )

    receipt = owner / payload["output_contract"]["receipt_path"]
    assert result.exit_code == 1
    assert writes[-2].name.endswith(".blocked.json")
    assert writes[-1] == receipt
    assert json.loads(receipt.read_text())["verification"]["status"] == "rejected"


def test_cli_report_write_failure_leaves_no_terminal_receipt(tmp_path):
    owner = tmp_path / "owner"
    init_owner_repo(owner)
    payload = request_payload()
    payload["output_contract"] = {
        **payload["output_contract"],
        "report_path": "blocked/report.md",
        "receipt_path": "receipts/result.json",
    }
    request = ResearchRequest.from_mapping(payload)
    registry = catalog()
    _, handoff = handoff_for(request, registry)
    request_path = tmp_path / "request.yaml"
    catalog_path = tmp_path / "catalog.yaml"
    handoff_path = tmp_path / "handoff.json"
    verification_path = tmp_path / "verification.json"
    sanitization_path = tmp_path / "sanitization.json"
    private_root = tmp_path / "private-owner"
    export_path = private_root / "perplexity-exports" / "test-result.md"
    export_path.parent.mkdir(parents=True)
    request_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    catalog_path.write_text(yaml.safe_dump(registry, sort_keys=False))
    handoff_path.write_text(json.dumps(handoff))
    verification_path.write_text(json.dumps(valid_attestation()))
    export_path.write_text(valid_export())
    sanitization_path.write_text(json.dumps(valid_sanitization()))
    (owner / "blocked").write_text("not a directory")
    result = CliRunner().invoke(
        main,
        [
            "research",
            "ingest",
            str(export_path),
            str(request_path),
            "--catalog",
            str(catalog_path),
            "--owner-root",
            str(owner),
            "--handoff-receipt",
            str(handoff_path),
            "--verification-file",
            str(verification_path),
            "--sanitization-file",
            str(sanitization_path),
            "--raw-owner-root",
            str(private_root),
            "--operator-handling-seconds",
            "600",
        ],
    )

    receipt = owner / payload["output_contract"]["receipt_path"]
    assert result.exit_code != 0
    assert not receipt.exists()


@pytest.mark.skipif(
    not os.environ.get("PRAXIS_PERPETUA_ROOT"),
    reason="set PRAXIS_PERPETUA_ROOT for owner-contract integration",
)
def test_real_praxis_requests_registry_and_schemas_are_consumable():
    jsonschema = pytest.importorskip("jsonschema")
    root = Path(os.environ["PRAXIS_PERPETUA_ROOT"])
    registry = yaml.safe_load((root / "governance/research-backend-profiles.yaml").read_text())
    request_schema = json.loads((root / "schemas/research-request.schema.json").read_text())
    outcome_schema = json.loads((root / "schemas/research-outcome.schema.json").read_text())
    receipt_schema = json.loads((root / "schemas/research-receipt.schema.json").read_text())
    verifier_schema = json.loads((root / "schemas/source-verifier-attestation.schema.json").read_text())
    sanitization_schema = json.loads((root / "schemas/output-sanitization-attestation.schema.json").read_text())
    checker = jsonschema.FormatChecker()
    fixture_root = root / "tests/research-backend/fixtures"
    verifier_fixture = json.loads((fixture_root / "valid-source-verifier-attestation.json").read_text())
    sanitization_fixture = json.loads((fixture_root / "valid-output-sanitization-attestation.json").read_text())
    raw_export = (fixture_root / "valid-export.md").read_text()
    jsonschema.validate(verifier_fixture, verifier_schema, format_checker=checker)
    jsonschema.validate(sanitization_fixture, sanitization_schema, format_checker=checker)
    SourceVerifierAttestation.from_mapping(
        verifier_fixture,
        expected_request_id=verifier_fixture["request_id"],
    )
    OutputSanitizationAttestation.from_mapping(
        sanitization_fixture,
        expected_request_id=sanitization_fixture["request_id"],
        expected_export_hash=stable_hash(raw_export),
        expected_preservation_tier=sanitization_fixture["preservation_tier"],
        expected_external_transmission=sanitization_fixture["external_transmission"],
    )

    for path in sorted((root / "commissions/2026-07-17-perplexity-research-pilot/requests").glob("*.yaml")):
        raw_request = yaml.safe_load(path.read_text())
        jsonschema.validate(raw_request, request_schema, format_checker=checker)
        request = ResearchRequest.from_mapping(raw_request)
        outcome, receipt = prepare_research(request, registry, prompt_ref=f"{request.request_id}.md")
        assert isinstance(outcome, ManualHandoff)
        jsonschema.validate(outcome.public_dict(), outcome_schema, format_checker=checker)
        jsonschema.validate(receipt.public_dict(), receipt_schema, format_checker=checker)
