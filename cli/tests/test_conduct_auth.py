from __future__ import annotations

import json

import pytest
from limen.conduct.auth import (
    ConductAuthenticationError,
    authenticate_principal,
    parse_principal_registry,
)


def registry(*entries: dict) -> str:
    return json.dumps(
        {
            "schema_version": "limen.conduct_principal_registry.v1",
            "principals": list(entries),
        }
    )


def entry(principal_id: str, bearer: str) -> dict:
    return {
        "principal_id": principal_id,
        "agent": "codex",
        "surface": "cloud",
        "roles": ["observer", "conductor"],
        "bearer": bearer,
    }


def test_registry_derives_principal_without_exposing_bearer() -> None:
    raw = registry(entry("codex-cloud", "principal-secret-at-least-24-characters"))
    principal = authenticate_principal(raw, "principal-secret-at-least-24-characters")
    assert principal.principal_id == "codex-cloud"
    assert "bearer" not in principal.model_dump()


def test_registry_rejects_short_duplicate_and_unknown_bearers() -> None:
    with pytest.raises(ConductAuthenticationError, match="bounded secret"):
        parse_principal_registry(registry(entry("short", "too-short")))
    duplicate = registry(
        entry("first", "duplicate-secret-at-least-24-characters"),
        entry("second", "duplicate-secret-at-least-24-characters"),
    )
    with pytest.raises(ConductAuthenticationError, match="duplicate"):
        parse_principal_registry(duplicate)
    with pytest.raises(ConductAuthenticationError, match="invalid conduct bearer"):
        authenticate_principal(
            registry(entry("codex-cloud", "principal-secret-at-least-24-characters")),
            "wrong-secret-at-least-24-characters",
        )
