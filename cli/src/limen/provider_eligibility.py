"""Fail-closed provider policy admission; no provider discovery or invocation.

The verifier is a trusted caller dependency, never a field in an agent task.
Type-valid provider statements are not authenticated evidence. Production
dispatch intentionally blocks policy-bearing tasks until such an adapter is
installed through the existing authority boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


POLICY_VERSION = "limen.provider_eligibility.v1"
EVIDENCE_VERSION = "limen.provider_eligibility_evidence.v1"
_CLASSES = {"synthetic", "public", "internal", "confidential", "restricted"}
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_POLICY_KEYS = {
    "schema_version",
    "repository",
    "source_revision",
    "data_classification",
    "max_retention_days",
    "tools",
    "destinations",
}
_EVIDENCE_KEYS = {
    "schema_version",
    "provider",
    "model_id",
    "policy_sha256",
    "source_revision",
    "data_classifications",
    "retention_days",
    "allowed_tools",
    "allowed_destinations",
    "issued_at",
    "expires_at",
    "authority_reference",
}
EvidenceVerifier = Callable[[Mapping[str, Any]], bool]


class EligibilityPolicyError(ValueError):
    """An explicit admission policy cannot be represented without coercion."""


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise EligibilityPolicyError("invalid identifier")
    return value


def _days(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 36_500:
        raise EligibilityPolicyError("retention must be integer days")
    return value


def _strings(value: object, *, origins: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise EligibilityPolicyError("scope must be a string list")
    if len(value) != len(set(value)):
        raise EligibilityPolicyError("duplicate scope entry")
    for item in value:
        if not origins:
            _identifier(item)
            continue
        parsed = urlsplit(item)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in item
            or any(char.isspace() for char in item)
            or item != "https://" + parsed.netloc
        ):
            raise EligibilityPolicyError("destination must be an exact HTTPS origin")
        try:
            parsed.port
        except ValueError as exc:
            raise EligibilityPolicyError("invalid destination port") from exc
    return sorted(value)


def validate_policy(value: object) -> dict[str, Any]:
    """Normalize one explicit policy, rejecting extras, falsey values and globs."""
    if not isinstance(value, Mapping) or set(value) != _POLICY_KEYS:
        raise EligibilityPolicyError("provider eligibility policy fields are invalid")
    if value.get("schema_version") != POLICY_VERSION:
        raise EligibilityPolicyError("unknown provider eligibility schema")
    repository = value.get("repository")
    if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
        raise EligibilityPolicyError("repository must be an exact owner/name")
    revision = value.get("source_revision")
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
        raise EligibilityPolicyError("source revision must be an immutable commit")
    classification = value.get("data_classification")
    if not isinstance(classification, str) or classification not in _CLASSES:
        raise EligibilityPolicyError("unknown data classification")
    return {
        "schema_version": POLICY_VERSION,
        "repository": repository.lower(),
        "source_revision": revision,
        "data_classification": classification,
        "max_retention_days": _days(value.get("max_retention_days")),
        "tools": _strings(value.get("tools")),
        "destinations": _strings(value.get("destinations"), origins=True),
    }


def policy_sha256(policy: object) -> str:
    encoded = json.dumps(validate_policy(policy), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise EligibilityPolicyError("timestamp must be timezone aware")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EligibilityPolicyError("invalid timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise EligibilityPolicyError("timestamp must be timezone aware")
    return result


def provider_eligibility_reason(
    policy: object,
    *,
    provider: str,
    model_id: str,
    evidence: object = None,
    verifier: EvidenceVerifier | None = None,
    now: datetime | None = None,
) -> str | None:
    """Return a redacted rejection code, or None after authenticated admission.

    ``verifier`` must independently authenticate the entire statement against a
    trusted policy authority. It must not trust a payload's ``verified`` flag,
    model-generated prose, or artifact digest alone. No production implementation
    is installed by this module; fake verifiers belong only in synthetic tests.
    """
    try:
        request = validate_policy(policy)
        _identifier(provider)
        _identifier(model_id)
    except (EligibilityPolicyError, ValueError):
        return "provider_eligibility_invalid"
    if verifier is None:
        return "provider_eligibility_adapter_unavailable"
    if not isinstance(evidence, Mapping) or set(evidence) != _EVIDENCE_KEYS:
        return "provider_eligibility_evidence_invalid"
    # Snapshot before verification and evaluate the same bytes afterwards;
    # mutable caller-owned mappings never become post-verification authority.
    try:
        snapshot = json.loads(json.dumps(dict(evidence), allow_nan=False))
        if snapshot["schema_version"] != EVIDENCE_VERSION:
            return "provider_eligibility_evidence_invalid"
        if snapshot["provider"] != provider or snapshot["model_id"] != model_id:
            return "provider_eligibility_identity_mismatch"
        digest = snapshot["policy_sha256"]
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            return "provider_eligibility_evidence_invalid"
        if digest != policy_sha256(request) or snapshot["source_revision"] != request["source_revision"]:
            return "provider_eligibility_scope_mismatch"
        _identifier(snapshot["authority_reference"])
        classes = _strings(snapshot["data_classifications"])
        if not set(classes) <= _CLASSES:
            return "provider_eligibility_evidence_invalid"
        retained = _days(snapshot["retention_days"])
        tools = _strings(snapshot["allowed_tools"])
        destinations = _strings(snapshot["allowed_destinations"], origins=True)
        issued, expires = _timestamp(snapshot["issued_at"]), _timestamp(snapshot["expires_at"])
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or not issued <= current < expires:
            return "provider_eligibility_evidence_expired"
        # Give the verifier a separate copy so even it cannot mutate the
        # statement that is subsequently used for scope checks.
        if verifier(json.loads(json.dumps(snapshot))) is not True:
            return "provider_eligibility_evidence_untrusted"
    except Exception:
        # Parsing and verifier failures deny admission without echoing private
        # statement contents, URLs, or exception payloads.
        return "provider_eligibility_evidence_invalid"
    if request["data_classification"] not in classes or retained > request["max_retention_days"]:
        return "provider_eligibility_data_denied"
    if not set(request["tools"]) <= set(tools) or not set(request["destinations"]) <= set(destinations):
        return "provider_eligibility_authority_denied"
    return None


def eligibility_dispatch_block_reason(task: object) -> str | None:
    """Legacy compatibility is not policy verification; explicit policy blocks.

    Production dispatch has no independently authenticated provider-policy adapter
    yet. Neither a task extra nor a well-formed synthetic fixture can enable it.
    """
    policy = (
        task.get("provider_eligibility") if isinstance(task, Mapping) else getattr(task, "provider_eligibility", None)
    )
    if policy is None:
        return None
    try:
        validate_policy(policy)
    except (EligibilityPolicyError, ValueError):
        return "provider_eligibility_invalid"
    return "provider_eligibility_adapter_unavailable"
