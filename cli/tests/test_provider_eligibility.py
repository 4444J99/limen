"""Synthetic admission-seam diagnostics; not live provider-policy evidence."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from limen.execution_contract import execution_contract_hash, execution_contract_payload
from limen.provider_eligibility import (
    EVIDENCE_VERSION,
    POLICY_VERSION,
    EligibilityPolicyError,
    eligibility_dispatch_block_reason,
    policy_sha256,
    provider_eligibility_reason,
    validate_policy,
)
from limen.provider_selection import ExecutionProfile, ModelCapability, select_opencode_model


NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)


def policy():
    return {
        "schema_version": POLICY_VERSION,
        "repository": "example/fixture",
        "source_revision": "a" * 40,
        "data_classification": "synthetic",
        "max_retention_days": 0,
        "tools": ["read"],
        "destinations": ["https://example.test"],
    }


def evidence(model_id="fixture/renamed"):
    return {
        "schema_version": EVIDENCE_VERSION,
        "provider": "fixture-provider",
        "model_id": model_id,
        "policy_sha256": policy_sha256(policy()),
        "source_revision": "a" * 40,
        "data_classifications": ["synthetic"],
        "retention_days": 0,
        "allowed_tools": ["read"],
        "allowed_destinations": ["https://example.test"],
        "issued_at": "2026-09-07T11:00:00Z",
        "expires_at": "2026-09-07T13:00:00Z",
        "authority_reference": "fixture:independent-verifier",
    }


def check(statement=None, verifier=lambda _: True, **overrides):
    args = {
        "provider": "fixture-provider",
        "model_id": "fixture/renamed",
        "evidence": evidence() if statement is None else statement,
        "verifier": verifier,
        "now": NOW,
    }
    args.update(overrides)
    return provider_eligibility_reason(policy(), **args)


@pytest.mark.parametrize("value", [{}, False, "", [], 0])
def test_explicit_falsey_policy_is_not_policy_free(value):
    with pytest.raises(EligibilityPolicyError):
        validate_policy(value)
    assert eligibility_dispatch_block_reason({"provider_eligibility": value}) == "provider_eligibility_invalid"


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_retention_days", True),
        ("max_retention_days", 0.0),
        ("max_retention_days", -1),
        ("source_revision", "main"),
        ("repository", "*/*"),
        ("data_classification", "probably-public"),
        ("tools", ["*"]),
        ("tools", ["read", "read"]),
        ("destinations", ["https://*.example.test"]),
        ("destinations", ["https://user:secret@example.test"]),
        ("destinations", ["https://example.test/path"]),
        ("destinations", ["http://example.test"]),
        ("destinations", ["https://example.test:bad"]),
        ("destinations", ["https://["]),
    ],
)
def test_strict_policy_rejects_ambiguous_scope(field, value):
    request = policy()
    request[field] = value
    with pytest.raises(ValueError):
        validate_policy(request)


def test_type_valid_is_not_authenticated_and_production_stays_blocked():
    assert check() is None  # Deliberately synthetic verifier, not production evidence.
    assert check(verifier=None) == "provider_eligibility_adapter_unavailable"
    assert check(verifier=lambda _: False) == "provider_eligibility_evidence_untrusted"
    assert check(verifier=lambda _: 1) == "provider_eligibility_evidence_untrusted"
    assert (
        eligibility_dispatch_block_reason({"provider_eligibility": policy()})
        == "provider_eligibility_adapter_unavailable"
    )
    assert eligibility_dispatch_block_reason({}) is None
    assert eligibility_dispatch_block_reason({"provider_eligibility": None}) is None
    forged = evidence() | {"verified": True}
    assert check(forged) == "provider_eligibility_evidence_invalid"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("provider", "other", "identity_mismatch"),
        ("model_id", "fixture/other", "identity_mismatch"),
        ("source_revision", "b" * 40, "scope_mismatch"),
        ("policy_sha256", "b" * 64, "scope_mismatch"),
        ("expires_at", "2026-09-07T12:00:00Z", "evidence_expired"),
        ("issued_at", "2026-09-07T12:00:01Z", "evidence_expired"),
        ("issued_at", "2026-09-07T11:00:00", "evidence_invalid"),
        ("retention_days", 30, "data_denied"),
        ("retention_days", False, "evidence_invalid"),
        ("data_classifications", ["public"], "data_denied"),
        ("allowed_tools", [], "authority_denied"),
        ("allowed_destinations", ["https://other.test"], "authority_denied"),
    ],
)
def test_evidence_is_bound_to_exact_identity_revision_scope_and_expiry(field, value, reason):
    statement = evidence()
    statement[field] = value
    assert check(statement) == "provider_eligibility_" + reason


def test_verifier_exception_and_mutation_cannot_expand_scope():
    def failure(_):
        raise RuntimeError("do not echo private data")

    assert check(verifier=failure) == "provider_eligibility_evidence_invalid"
    statement = evidence() | {"allowed_tools": []}

    def mutation(value):
        value["allowed_tools"] = ["read"]
        return True

    assert check(statement, verifier=mutation) == "provider_eligibility_authority_denied"


def test_policy_is_hashed_and_legacy_hash_is_unchanged():
    task = {"id": "FIXTURE", "title": "Read receipts", "repo": "example/fixture", "target_agent": "fixture"}
    original = execution_contract_payload(task)
    assert original["schema_version"] == "limen-execution-contract.v4"
    assert execution_contract_hash(task) == execution_contract_hash(task | {"provider_eligibility": None})
    scoped = task | {"provider_eligibility": policy()}
    assert execution_contract_payload(scoped)["schema_version"] == "limen-execution-contract.v5"
    assert execution_contract_hash(scoped) != execution_contract_hash(task)
    changed = deepcopy(scoped)
    changed["provider_eligibility"]["max_retention_days"] = 30
    assert execution_contract_hash(changed) != execution_contract_hash(scoped)
    with pytest.raises(ValueError, match="provider_eligibility"):
        execution_contract_hash(scoped | {"repo": "example/other"})


def test_admission_filters_before_ranking_and_never_falls_back_to_unverified_model():
    profile = ExecutionProfile(None, 1.0, 0.0, 0.5, 8192, 2048, True, False, False, True, 1.0)
    allowed = ModelCapability("fixture/renamed", True, True, True, True, False, False, 32768, 8192, 1, 1, 0, 1)
    stronger = ModelCapability("fixture/stronger", True, True, True, True, True, False, 1048576, 65536, 0, 0, 8, 999999)
    statements = {allowed.model_id: evidence(), stronger.model_id: evidence(stronger.model_id) | {"retention_days": 30}}
    kwargs = dict(
        eligibility_policy=policy(), eligibility_provider="fixture-provider", eligibility_evidence=statements, now=NOW
    )
    assert select_opencode_model([allowed, stronger], profile, **kwargs) is None
    assert select_opencode_model([allowed, stronger], profile, eligibility_verifier=lambda _: True, **kwargs) == allowed
    assert select_opencode_model([stronger], profile, eligibility_verifier=lambda _: True, **kwargs) is None
    assert select_opencode_model([allowed, stronger], profile) == stronger  # Explicit legacy behavior.
