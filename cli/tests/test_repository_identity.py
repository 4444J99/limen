from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from limen.repository_identity import (
    LIMEN_REPOSITORY_IDENTITY,
    LIMEN_TRANSFER_FALLBACK_COORDINATE,
    RepositoryIdentityV1,
)


ROOT = Path(__file__).resolve().parents[2]


def test_limen_identity_is_stable_across_owner_coordinate() -> None:
    identity = LIMEN_REPOSITORY_IDENTITY

    assert identity.repository_id == 1_255_213_941
    assert identity.accepts("4444J99/limen")
    assert identity.accepts("organvm/limen")
    assert identity.accepts("ORGANVM/LIMEN")
    assert identity.canonicalize("organvm/limen") == "4444J99/limen"
    assert identity.stable_key("refs/heads/main@" + "a" * 40) == (
        "github-repository:1255213941/refs/heads/main@" + "a" * 40
    )


def test_coordinate_collisions_are_case_insensitive() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        RepositoryIdentityV1(
            repository_id=1,
            canonical_coordinate="Owner/Repo",
            historical_aliases=("owner/repo",),
        )


def test_unregistered_coordinate_is_rejected_without_mutating_identity() -> None:
    identity = LIMEN_REPOSITORY_IDENTITY

    with pytest.raises(ValueError, match="does not belong"):
        identity.canonicalize("someone-else/limen")

    assert identity.canonical_coordinate == "4444J99/limen"


def test_registry_matches_runtime_contract() -> None:
    registry = json.loads((ROOT / "institutio/github/repository-identity.json").read_text())
    identity = RepositoryIdentityV1.model_validate(registry["repositories"][0])

    assert identity == LIMEN_REPOSITORY_IDENTITY
    assert registry["transfer_fallback_coordinate"] == LIMEN_TRANSFER_FALLBACK_COORDINATE
    assert not identity.accepts(LIMEN_TRANSFER_FALLBACK_COORDINATE)


def test_wire_schema_declares_required_case_insensitive_semantic_validation() -> None:
    schema = json.loads((ROOT / "spec/contracts/repository-identity-v1.schema.json").read_text())

    assert "MUST also run the RepositoryIdentityV1 semantic validator" in schema["description"]
    assert schema["properties"]["historical_aliases"]["x-limen-case-insensitive-unique"] is True
