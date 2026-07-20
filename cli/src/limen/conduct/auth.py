"""Credential-wall principal registry for authenticated conduct requests."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from limen.conduct.models import ConductPrincipalV1


class ConductAuthenticationError(ValueError):
    pass


def parse_principal_registry(raw: str) -> tuple[tuple[ConductPrincipalV1, str], ...]:
    """Parse the secret JSON registry without ever returning bearer values in metadata."""

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConductAuthenticationError("conduct principal registry is invalid JSON") from exc
    if not isinstance(document, dict) or document.get("schema_version") != "limen.conduct_principal_registry.v1":
        raise ConductAuthenticationError("conduct principal registry has an unsupported schema")
    entries = document.get("principals")
    if not isinstance(entries, list) or not entries:
        raise ConductAuthenticationError("conduct principal registry must contain principals")
    parsed: list[tuple[ConductPrincipalV1, str]] = []
    seen_principals: set[str] = set()
    seen_hashes: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ConductAuthenticationError("conduct principal registry entries must be objects")
        bearer = entry.get("bearer")
        if not isinstance(bearer, str) or len(bearer) < 24 or len(bearer) > 4096:
            raise ConductAuthenticationError("conduct principal bearer must be a bounded secret")
        metadata: dict[str, Any] = {key: value for key, value in entry.items() if key != "bearer"}
        try:
            principal = ConductPrincipalV1.model_validate(metadata)
        except ValueError as exc:
            raise ConductAuthenticationError("conduct principal metadata is invalid") from exc
        bearer_hash = hashlib.sha256(bearer.encode("utf-8")).hexdigest()
        if principal.principal_id in seen_principals or bearer_hash in seen_hashes:
            raise ConductAuthenticationError("conduct principal registry contains a duplicate")
        seen_principals.add(principal.principal_id)
        seen_hashes.add(bearer_hash)
        parsed.append((principal, bearer))
    return tuple(parsed)


def authenticate_principal(raw_registry: str, bearer: str) -> ConductPrincipalV1:
    if not bearer:
        raise ConductAuthenticationError("missing conduct bearer")
    for principal, candidate in parse_principal_registry(raw_registry):
        if hmac.compare_digest(candidate, bearer):
            return principal
    raise ConductAuthenticationError("invalid conduct bearer")
