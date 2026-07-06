"""Shared proof-field checks for local removal acceptance ledgers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


REQUIRED_ACCEPTANCE_PROOF_FIELDS = ("accepted_at", "archive_proof", "redaction_proof")


def missing_required_acceptance_proof_fields(
    event: Mapping[str, Any],
    required_fields: tuple[str, ...] = REQUIRED_ACCEPTANCE_PROOF_FIELDS,
) -> tuple[str, ...]:
    return tuple(field for field in required_fields if not str(event.get(field) or "").strip())


def has_required_acceptance_proof(
    event: Mapping[str, Any],
    required_fields: tuple[str, ...] = REQUIRED_ACCEPTANCE_PROOF_FIELDS,
) -> bool:
    return not missing_required_acceptance_proof_fields(event, required_fields)
