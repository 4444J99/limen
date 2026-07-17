"""Cryptographic owner-attestation contracts for recovery completion gates.

The ledger's structural validator may accept an unprovisioned campaign so the
historical denominator remains inspectable.  A release gate must additionally
call :func:`owner_gate_attestation_errors`; missing requirements, missing keys,
or an invalid signature are then explicit fail-closed blockers.

This module deliberately uses only the Python standard library.  Public keys
are represented as an RSA modulus encoded with unpadded base64url plus a public
exponent.  Signatures use RSASSA-PKCS1-v1_5 with SHA-256.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from limen.reacceptance_contract import (
    COMPLETION_GATE_KEYS,
    SHA256_DIGEST,
    _strict_json_dumps,
)


OWNER_ATTESTATION_REQUIREMENTS_SCHEMA = "limen.reacceptance.owner_attestation_requirements.v1"
OWNER_ATTESTATION_SCHEMA = "limen.reacceptance.owner_attestation.v1"
OWNER_ATTESTATION_PAYLOAD_SCHEMA = "limen.reacceptance.owner_attestation_payload.v1"
EFFECT_OWNER_ATTESTATION_SCHEMA = "limen.reacceptance.effect_owner_attestation.v1"
EFFECT_OWNER_ATTESTATION_PAYLOAD_SCHEMA = "limen.reacceptance.effect_owner_attestation_payload.v1"
CUTOFF_EVENT_OFFSET_ANCHOR_SCHEMA = "limen.prompt_corpus_cutoff_event_offsets.v1"
PRIVACY_FROZEN_MANIFEST_SCHEMA = "limen.reacceptance.privacy_frozen_manifest.v1"
EFFECT_OUTCOME_SCHEMA = "limen.reacceptance.effect_owner_outcome.v1"
RSA_SHA256_PKCS1_V1_5 = "rsa-sha256-pkcs1-v1_5"

MIN_RSA_BITS = 2048
MAX_RSA_BITS = 8192
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
_TERMINAL_EFFECT_OUTCOMES = {
    "contained",
    "reversed",
    "custody_preserved",
    "owner_authorized_retained",
    "owner_adjudicated_no_change",
}


def _canonical_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON, rejecting non-finite or unsupported values."""

    return _strict_json_dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _canonical_json_value(value: Any, *, label: str) -> Any:
    """Return a detached canonical JSON value or raise for non-JSON input."""

    try:
        encoded = _canonical_bytes(value)
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be canonical JSON") from exc


def owner_binding_digest(value: Any) -> str:
    """Return the exact canonical binding digest used by ledger owner gates."""

    encoded = _canonical_bytes(value)
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _valid_https_url(value: Any) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    parsed = urlsplit(value)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )


def receipt_identity(receipt: Any) -> dict[str, str] | None:
    """Normalize every durable identity carried by a receipt.

    If a receipt has both an HTTPS URL and an owner-bound digest, both are
    included.  This prevents a signature over one identity from silently
    leaving the other mutable.
    """

    if not isinstance(receipt, Mapping):
        return None
    identity: dict[str, str] = {}
    url = receipt.get("url")
    if _valid_https_url(url):
        identity["url"] = str(url)
    digest = receipt.get("digest")
    owner = receipt.get("owner")
    if (
        isinstance(digest, str)
        and SHA256_DIGEST.fullmatch(digest)
        and isinstance(owner, str)
        and owner
        and owner == owner.strip()
    ):
        identity["owner"] = owner
        identity["digest"] = digest
    if not identity:
        return None
    if "url" in identity and "digest" in identity:
        identity["kind"] = "https_url_and_owner_digest"
    elif "url" in identity:
        identity["kind"] = "https_url"
    else:
        identity["kind"] = "owner_digest"
    return identity


def owner_attestation_payload(
    *,
    gate_key: str,
    owner: str,
    binding_digest: str,
    predicate: Any,
    receipt: Any,
) -> dict[str, Any]:
    """Build the complete payload an owner key must sign.

    Raises ``ValueError`` for an incomplete binding so callers cannot sign a
    partially specified authority claim.
    """

    if gate_key not in COMPLETION_GATE_KEYS:
        raise ValueError(f"unknown owner gate: {gate_key}")
    if not isinstance(owner, str) or not owner or owner != owner.strip():
        raise ValueError("owner must be a non-empty canonical string")
    if not isinstance(binding_digest, str) or not SHA256_DIGEST.fullmatch(binding_digest):
        raise ValueError("binding_digest must be a SHA-256 digest")
    canonical_predicate = _canonical_json_value(predicate, label="owner predicate")
    if not isinstance(canonical_predicate, dict):
        raise ValueError("owner predicate must be an object")
    predicate_command = canonical_predicate.get("command")
    if (
        not isinstance(predicate_command, str)
        or not predicate_command
        or predicate_command != predicate_command.strip()
        or "\x00" in predicate_command
    ):
        raise ValueError("predicate_command must be a non-empty canonical string")
    identity = receipt_identity(receipt)
    if identity is None:
        raise ValueError("receipt needs a durable HTTPS URL or owner-bound SHA-256 digest")
    canonical_receipt = _canonical_json_value(receipt, label="owner receipt")
    if not isinstance(canonical_receipt, dict):
        raise ValueError("owner receipt must be an object")
    return {
        "schema": OWNER_ATTESTATION_PAYLOAD_SCHEMA,
        "gate_key": gate_key,
        "owner": owner,
        "owner_binding_digest": binding_digest,
        "predicate_command": predicate_command,
        "predicate": canonical_predicate,
        "receipt_identity": identity,
        "receipt": canonical_receipt,
    }


def canonical_owner_attestation_payload(payload: Mapping[str, Any]) -> bytes:
    """Serialize a fully formed owner-attestation payload for signing."""

    required = {
        "schema",
        "gate_key",
        "owner",
        "owner_binding_digest",
        "predicate_command",
        "predicate",
        "receipt_identity",
        "receipt",
    }
    if set(payload) != required or payload.get("schema") != OWNER_ATTESTATION_PAYLOAD_SCHEMA:
        raise ValueError("owner attestation payload has an invalid shape")
    identity = payload.get("receipt_identity")
    normalized_identity = receipt_identity(identity)
    if normalized_identity is None or not isinstance(identity, Mapping) or dict(identity) != normalized_identity:
        raise ValueError("owner attestation receipt identity is not canonical")
    rebuilt = owner_attestation_payload(
        gate_key=str(payload.get("gate_key") or ""),
        owner=str(payload.get("owner") or ""),
        binding_digest=str(payload.get("owner_binding_digest") or ""),
        predicate=payload.get("predicate"),
        receipt=payload.get("receipt"),
    )
    if rebuilt != dict(payload):
        raise ValueError("owner attestation payload is not canonical")
    return _canonical_bytes(rebuilt)


def effect_owner_attestation_payload(
    *,
    subject_id: str,
    historical_row_ids: Any,
    effect: str,
    owner_surface: str,
    status: str,
    outcome: str,
    predicate: Any,
    receipt: Any,
) -> dict[str, Any]:
    """Build the exact effect-owner payload that a custody owner must sign."""

    canonical_strings = {
        "subject_id": subject_id,
        "effect": effect,
        "owner_surface": owner_surface,
        "status": status,
        "outcome": outcome,
    }
    for field, value in canonical_strings.items():
        if not isinstance(value, str) or not value or value != value.strip() or "\x00" in value:
            raise ValueError(f"{field} must be a non-empty canonical string")
    if (
        not isinstance(historical_row_ids, list)
        or not historical_row_ids
        or any(
            not isinstance(row_id, str) or not row_id or row_id != row_id.strip() or "\x00" in row_id
            for row_id in historical_row_ids
        )
        or len(historical_row_ids) != len(set(historical_row_ids))
    ):
        raise ValueError("historical_row_ids must be unique non-empty canonical strings")
    canonical_predicate = _canonical_json_value(predicate, label="effect owner predicate")
    if not isinstance(canonical_predicate, dict):
        raise ValueError("effect owner predicate must be an object")
    identity = receipt_identity(receipt)
    if identity is None:
        raise ValueError("effect owner receipt needs a durable identity")
    return {
        "schema": EFFECT_OWNER_ATTESTATION_PAYLOAD_SCHEMA,
        "subject_id": subject_id,
        "historical_row_ids": sorted(historical_row_ids),
        "effect": effect,
        "owner_surface": owner_surface,
        "status": status,
        "outcome": outcome,
        "predicate": canonical_predicate,
        "receipt_identity": identity,
    }


def canonical_effect_owner_attestation_payload(payload: Mapping[str, Any]) -> bytes:
    """Serialize an exact effect-owner payload for signing and verification."""

    required = {
        "schema",
        "subject_id",
        "historical_row_ids",
        "effect",
        "owner_surface",
        "status",
        "outcome",
        "predicate",
        "receipt_identity",
    }
    if set(payload) != required or payload.get("schema") != EFFECT_OWNER_ATTESTATION_PAYLOAD_SCHEMA:
        raise ValueError("effect owner attestation payload has an invalid shape")
    identity = payload.get("receipt_identity")
    normalized_identity = receipt_identity(identity)
    if normalized_identity is None or not isinstance(identity, Mapping) or dict(identity) != normalized_identity:
        raise ValueError("effect owner receipt identity is not canonical")
    rebuilt = effect_owner_attestation_payload(
        subject_id=str(payload.get("subject_id") or ""),
        historical_row_ids=payload.get("historical_row_ids"),
        effect=str(payload.get("effect") or ""),
        owner_surface=str(payload.get("owner_surface") or ""),
        status=str(payload.get("status") or ""),
        outcome=str(payload.get("outcome") or ""),
        predicate=payload.get("predicate"),
        receipt=identity,
    )
    if rebuilt != dict(payload):
        raise ValueError("effect owner attestation payload is not canonical")
    return _canonical_bytes(rebuilt)


def _base64url_decode(value: Any) -> bytes | None:
    if not isinstance(value, str) or not value or "=" in value:
        return None
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        return None
    if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != value:
        return None
    return decoded


def _public_key_errors(public_key: Any, *, label: str) -> list[str]:
    if not isinstance(public_key, Mapping):
        return [f"{label} must be an object"]
    errors: list[str] = []
    key_id = public_key.get("key_id")
    if not isinstance(key_id, str) or not key_id or key_id != key_id.strip() or len(key_id) > 128 or "\x00" in key_id:
        errors.append(f"{label} key_id is invalid")
    if public_key.get("algorithm") != RSA_SHA256_PKCS1_V1_5:
        errors.append(f"{label} algorithm must be {RSA_SHA256_PKCS1_V1_5}")
    modulus_bytes = _base64url_decode(public_key.get("modulus"))
    if modulus_bytes is None:
        errors.append(f"{label} modulus must be canonical unpadded base64url")
    else:
        modulus = int.from_bytes(modulus_bytes, "big")
        bits = modulus.bit_length()
        if bits < MIN_RSA_BITS or bits > MAX_RSA_BITS or modulus % 2 == 0:
            errors.append(f"{label} modulus must be an odd {MIN_RSA_BITS}-{MAX_RSA_BITS} bit integer")
        if modulus_bytes[0] == 0:
            errors.append(f"{label} modulus must not have leading zero bytes")
    exponent = public_key.get("exponent")
    if (
        not isinstance(exponent, int)
        or isinstance(exponent, bool)
        or exponent < 3
        or exponent > 0xFFFFFFFF
        or exponent % 2 == 0
    ):
        errors.append(f"{label} exponent must be an odd integer between 3 and 2^32-1")
    return errors


def verify_rsa_sha256_pkcs1_v1_5(public_key: Mapping[str, Any], message: bytes, signature: str) -> bool:
    """Verify an unpadded-base64url RSA-SHA256 PKCS#1 v1.5 signature."""

    if _public_key_errors(public_key, label="public key"):
        return False
    signature_bytes = _base64url_decode(signature)
    modulus_bytes = _base64url_decode(public_key.get("modulus"))
    if signature_bytes is None or modulus_bytes is None:
        return False
    modulus = int.from_bytes(modulus_bytes, "big")
    exponent = int(public_key["exponent"])
    width = (modulus.bit_length() + 7) // 8
    if len(signature_bytes) != width:
        return False
    signature_integer = int.from_bytes(signature_bytes, "big")
    if signature_integer >= modulus:
        return False
    decoded = pow(signature_integer, exponent, modulus).to_bytes(width, "big")
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(message).digest()
    padding_length = width - len(digest_info) - 3
    if padding_length < 8:
        return False
    expected = b"\x00\x01" + b"\xff" * padding_length + b"\x00" + digest_info
    return hmac.compare_digest(decoded, expected)


def _key_list_errors(keys: Any, *, label: str) -> list[str]:
    if not isinstance(keys, list):
        return [f"{label} must be a list"]
    errors: list[str] = []
    key_ids: list[str] = []
    for index, public_key in enumerate(keys):
        key_label = f"{label}[{index}]"
        if isinstance(public_key, Mapping) and set(public_key) != {
            "key_id",
            "algorithm",
            "modulus",
            "exponent",
        }:
            errors.append(f"{key_label} must contain exactly key_id, algorithm, modulus, and exponent")
        errors.extend(_public_key_errors(public_key, label=key_label))
        if isinstance(public_key, Mapping) and isinstance(public_key.get("key_id"), str):
            key_ids.append(str(public_key["key_id"]))
    if len(key_ids) != len(set(key_ids)):
        errors.append(f"{label} key_id values must be unique")
    return errors


def _known_effect_owner_names(scope: Mapping[str, Any]) -> tuple[set[str], list[str]]:
    mappings = scope.get("known_side_effect_owners")
    if not isinstance(mappings, Mapping):
        return set(), ["known_side_effect_owners must be an object when owner keys are provisioned"]
    owners: set[str] = set()
    errors: list[str] = []
    for row_id, effect_owners in mappings.items():
        if not isinstance(row_id, str) or not row_id or not isinstance(effect_owners, Mapping):
            errors.append("known_side_effect_owners must map row IDs to effect-owner objects")
            continue
        for effect, owner in effect_owners.items():
            if (
                not isinstance(effect, str)
                or not effect
                or not isinstance(owner, str)
                or not owner
                or owner != owner.strip()
            ):
                errors.append(f"known_side_effect_owners[{row_id}] has an invalid effect owner")
                continue
            owners.add(owner)
    return owners, errors


def _key_principal_reuse_errors(
    gates: Mapping[str, Any],
    effect_owners: Mapping[str, Any],
) -> list[str]:
    assignments: dict[tuple[str, int], str] = {}
    errors: list[str] = []

    def register(principal: Any, keys: Any) -> None:
        if not isinstance(principal, str) or not isinstance(keys, list):
            return
        for public_key in keys:
            if not isinstance(public_key, Mapping) or _public_key_errors(public_key, label="public key"):
                continue
            identity = (str(public_key["modulus"]), int(public_key["exponent"]))
            previous = assignments.setdefault(identity, principal)
            if previous != principal:
                errors.append(
                    f"one public key cannot authenticate distinct owner principals {previous!r} and {principal!r}"
                )

    for requirement in gates.values():
        if isinstance(requirement, Mapping):
            register(requirement.get("owner"), requirement.get("keys"))
    for principal, requirement in effect_owners.items():
        if isinstance(requirement, Mapping):
            register(principal, requirement.get("keys"))
    return sorted(set(errors))


def owner_attestation_scope_errors(scope: Any) -> list[str]:
    """Validate the optional owner-key requirements embedded in a scope.

    ``None`` is structurally valid for an in-progress campaign.  Use
    :func:`owner_attestation_provisioning_blockers` for release readiness.
    """

    if not isinstance(scope, Mapping):
        return ["scope must be an object"]
    requirements = scope.get("owner_attestation_requirements")
    if requirements is None:
        return []
    if not isinstance(requirements, Mapping):
        return ["owner_attestation_requirements must be an object or null"]
    errors: list[str] = []
    if set(requirements) != {"schema", "gates", "effect_owners"}:
        errors.append("owner_attestation_requirements must contain exactly schema, gates, and effect_owners")
    if requirements.get("schema") != OWNER_ATTESTATION_REQUIREMENTS_SCHEMA:
        errors.append(f"owner_attestation_requirements schema must be {OWNER_ATTESTATION_REQUIREMENTS_SCHEMA}")
    gates = requirements.get("gates")
    if not isinstance(gates, Mapping):
        return errors + ["owner_attestation_requirements.gates must be an object"]
    if set(gates) != COMPLETION_GATE_KEYS:
        errors.append("owner_attestation_requirements.gates must contain exactly the five completion gates")
    for gate_key in sorted(COMPLETION_GATE_KEYS & set(gates)):
        requirement = gates[gate_key]
        label = f"owner_attestation_requirements.gates.{gate_key}"
        if not isinstance(requirement, Mapping):
            errors.append(f"{label} must be an object")
            continue
        if set(requirement) != {"owner", "predicate_command", "keys"}:
            errors.append(f"{label} must contain exactly owner, predicate_command, and keys")
        owner = requirement.get("owner")
        if not isinstance(owner, str) or not owner or owner != owner.strip():
            errors.append(f"{label}.owner must be a non-empty canonical string")
        command = requirement.get("predicate_command")
        if not isinstance(command, str) or not command or command != command.strip() or "\x00" in command:
            errors.append(f"{label}.predicate_command must be a non-empty canonical string")
        errors.extend(_key_list_errors(requirement.get("keys"), label=f"{label}.keys"))

    expected_effect_owners, effect_owner_scope_errors = _known_effect_owner_names(scope)
    errors.extend(effect_owner_scope_errors)
    effect_owners = requirements.get("effect_owners")
    if not isinstance(effect_owners, Mapping):
        return errors + ["owner_attestation_requirements.effect_owners must be an object"]
    if set(effect_owners) != expected_effect_owners:
        errors.append("owner_attestation_requirements.effect_owners must contain exactly the frozen effect owners")
    for owner_surface in sorted(expected_effect_owners & set(effect_owners)):
        requirement = effect_owners[owner_surface]
        label = f"owner_attestation_requirements.effect_owners.{owner_surface}"
        if not isinstance(requirement, Mapping):
            errors.append(f"{label} must be an object")
            continue
        if set(requirement) != {"keys"}:
            errors.append(f"{label} must contain exactly keys")
        errors.extend(_key_list_errors(requirement.get("keys"), label=f"{label}.keys"))
    errors.extend(_key_principal_reuse_errors(gates, effect_owners))
    return errors


def owner_attestation_requirements_digest(scope: Any) -> str | None:
    """Return the digest a document scope should freeze for owner key requirements."""

    if owner_attestation_scope_errors(scope):
        return None
    requirements = scope.get("owner_attestation_requirements")
    if requirements is None:
        return None
    return owner_binding_digest(requirements)


def owner_attestation_provisioning_blockers(scope: Any) -> list[str]:
    """Return release blockers for missing or unusable gate key requirements."""

    structural = owner_attestation_scope_errors(scope)
    if structural:
        return [f"owner_attestation_requirements_invalid:{error}" for error in structural]
    requirements = scope.get("owner_attestation_requirements")
    if requirements is None:
        return ["owner_attestation_requirements_unprovisioned"]
    blockers: list[str] = []
    gates = requirements["gates"]
    for gate_key in sorted(COMPLETION_GATE_KEYS):
        if not gates[gate_key]["keys"]:
            blockers.append(f"{gate_key}:owner_public_key_unprovisioned")
    for owner_surface, requirement in sorted(requirements["effect_owners"].items()):
        if not requirement["keys"]:
            blockers.append(f"effect_owner:{owner_surface}:public_key_unprovisioned")
    return blockers


def owner_gate_attestation_errors(
    *,
    scope: Mapping[str, Any],
    gate_key: str,
    owner_evidence: Any,
    binding_value: Any,
) -> list[str]:
    """Authenticate one owner gate against its scope-pinned key requirement."""

    if gate_key not in COMPLETION_GATE_KEYS:
        return [f"unknown owner gate: {gate_key}"]
    structural = owner_attestation_scope_errors(scope)
    if structural:
        return [f"owner attestation scope invalid: {error}" for error in structural]
    requirements = scope.get("owner_attestation_requirements")
    if requirements is None:
        return ["owner attestation requirements are unprovisioned"]
    requirement = requirements["gates"][gate_key]
    keys = requirement["keys"]
    if not keys:
        return [f"{gate_key} owner public key is unprovisioned"]
    if not isinstance(owner_evidence, Mapping):
        return [f"{gate_key} owner evidence must be an object"]

    errors: list[str] = []
    owner = owner_evidence.get("owner")
    expected_owner = requirement["owner"]
    if owner != expected_owner:
        errors.append(f"{gate_key} owner does not match the scope requirement")
    predicate = owner_evidence.get("predicate")
    command = predicate.get("command") if isinstance(predicate, Mapping) else None
    expected_command = requirement["predicate_command"]
    if command != expected_command:
        errors.append(f"{gate_key} predicate command does not match the scope requirement")
    identity = receipt_identity(owner_evidence.get("receipt"))
    if identity is None:
        errors.append(f"{gate_key} receipt identity is invalid")
    try:
        binding_digest = owner_binding_digest(binding_value)
    except (TypeError, ValueError):
        return errors + [f"{gate_key} owner binding contains non-canonical values"]
    try:
        expected_payload = owner_attestation_payload(
            gate_key=gate_key,
            owner=str(owner or ""),
            binding_digest=binding_digest,
            predicate=predicate,
            receipt=owner_evidence.get("receipt"),
        )
    except ValueError as exc:
        errors.append(f"{gate_key} signed payload cannot be derived: {exc}")
        expected_payload = None

    attestation = owner_evidence.get("attestation")
    if not isinstance(attestation, Mapping):
        return errors + [f"{gate_key} owner attestation is missing"]
    if set(attestation) != {"schema", "algorithm", "key_id", "payload", "signature"}:
        errors.append(f"{gate_key} owner attestation has an invalid shape")
    if attestation.get("schema") != OWNER_ATTESTATION_SCHEMA:
        errors.append(f"{gate_key} owner attestation schema is invalid")
    if attestation.get("algorithm") != RSA_SHA256_PKCS1_V1_5:
        errors.append(f"{gate_key} owner attestation algorithm is invalid")
    key_id = attestation.get("key_id")
    public_key = next(
        (key for key in keys if isinstance(key, Mapping) and key.get("key_id") == key_id),
        None,
    )
    if public_key is None:
        errors.append(f"{gate_key} owner attestation key is not scope-pinned")
    payload = attestation.get("payload")
    if expected_payload is None or payload != expected_payload:
        errors.append(f"{gate_key} owner attestation payload does not match current evidence")
    if public_key is not None and payload == expected_payload:
        try:
            message = canonical_owner_attestation_payload(expected_payload)
        except ValueError as exc:
            errors.append(f"{gate_key} owner attestation payload is invalid: {exc}")
        else:
            if not verify_rsa_sha256_pkcs1_v1_5(
                public_key,
                message,
                str(attestation.get("signature") or ""),
            ):
                errors.append(f"{gate_key} owner attestation signature is invalid")
    return errors


def effect_owner_attestation_errors(
    *,
    scope: Mapping[str, Any],
    subject_id: str,
    outcome: Any,
) -> list[str]:
    """Authenticate one side-effect outcome with its frozen owner's key."""

    structural = owner_attestation_scope_errors(scope)
    if structural:
        return [f"owner attestation scope invalid: {error}" for error in structural]
    requirements = scope.get("owner_attestation_requirements")
    if requirements is None:
        return ["effect owner attestation requirements are unprovisioned"]
    if not isinstance(outcome, Mapping):
        return ["effect owner outcome must be an object"]
    owner_surface = outcome.get("owner_surface")
    effect_requirements = requirements["effect_owners"]
    requirement = effect_requirements.get(owner_surface) if isinstance(owner_surface, str) else None
    if not isinstance(requirement, Mapping):
        return ["effect owner is not scope-pinned"]
    keys = requirement["keys"]
    if not keys:
        return [f"effect owner {owner_surface} public key is unprovisioned"]

    errors: list[str] = []
    try:
        expected_payload = effect_owner_attestation_payload(
            subject_id=subject_id,
            historical_row_ids=outcome.get("historical_row_ids"),
            effect=str(outcome.get("effect") or ""),
            owner_surface=str(owner_surface or ""),
            status=str(outcome.get("status") or ""),
            outcome=str(outcome.get("outcome") or ""),
            predicate=outcome.get("predicate"),
            receipt=outcome.get("receipt"),
        )
    except ValueError as exc:
        errors.append(f"effect owner signed payload cannot be derived: {exc}")
        expected_payload = None

    attestation = outcome.get("owner_attestation")
    if not isinstance(attestation, Mapping):
        return errors + ["effect owner attestation is missing"]
    if set(attestation) != {"schema", "algorithm", "key_id", "payload", "signature"}:
        errors.append("effect owner attestation has an invalid shape")
    if attestation.get("schema") != EFFECT_OWNER_ATTESTATION_SCHEMA:
        errors.append("effect owner attestation schema is invalid")
    if attestation.get("algorithm") != RSA_SHA256_PKCS1_V1_5:
        errors.append("effect owner attestation algorithm is invalid")
    key_id = attestation.get("key_id")
    public_key = next(
        (key for key in keys if isinstance(key, Mapping) and key.get("key_id") == key_id),
        None,
    )
    if public_key is None:
        errors.append("effect owner attestation key is not scope-pinned for this owner")
    payload = attestation.get("payload")
    if expected_payload is None or payload != expected_payload:
        errors.append("effect owner attestation payload does not match current outcome")
    if public_key is not None and payload == expected_payload:
        try:
            message = canonical_effect_owner_attestation_payload(expected_payload)
        except ValueError as exc:
            errors.append(f"effect owner attestation payload is invalid: {exc}")
        else:
            if not verify_rsa_sha256_pkcs1_v1_5(
                public_key,
                message,
                str(attestation.get("signature") or ""),
            ):
                errors.append("effect owner attestation signature is invalid")
    return errors


def cutoff_event_offset_digest(event_offsets: Any) -> str:
    """Hash an ordered, unique immutable event-offset sequence with domain separation."""

    if (
        not isinstance(event_offsets, list)
        or not event_offsets
        or any(not isinstance(offset, str) or not offset or offset != offset.strip() for offset in event_offsets)
        or len(event_offsets) != len(set(event_offsets))
    ):
        raise ValueError("event_offsets must be an ordered list of unique non-empty strings")
    payload = {
        "schema": CUTOFF_EVENT_OFFSET_ANCHOR_SCHEMA,
        "event_offsets": event_offsets,
    }
    return "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def cutoff_event_offset_anchor_errors(cutoff: Any) -> list[str]:
    """Validate a verified cutoff's explicit event-offset digest anchor."""

    if not isinstance(cutoff, Mapping):
        return ["cutoff receipt must be an object"]
    errors: list[str] = []
    if cutoff.get("schema") != CUTOFF_EVENT_OFFSET_ANCHOR_SCHEMA:
        errors.append(f"cutoff receipt schema must be {CUTOFF_EVENT_OFFSET_ANCHOR_SCHEMA}")
    try:
        expected = cutoff_event_offset_digest(cutoff.get("event_offsets"))
    except ValueError as exc:
        return errors + [str(exc)]
    if cutoff.get("status") != "verified":
        errors.append("cutoff receipt must be verified")
    if cutoff.get("event_offset_digest") != expected:
        errors.append("cutoff event_offset_digest does not match the immutable offsets")
    return errors


def privacy_frozen_manifest(scope: Mapping[str, Any]) -> dict[str, Any]:
    """Build the exact privacy row/effect denominator that an owner must bind."""

    affected = scope.get("privacy_affected_row_ids")
    known_effects = scope.get("known_side_effects")
    source_digest = scope.get("source_reference_manifest_digest")
    if (
        not isinstance(affected, list)
        or not affected
        or len(affected) != len(set(affected))
        or any(not isinstance(row_id, str) or not row_id for row_id in affected)
    ):
        raise ValueError("privacy_affected_row_ids must contain unique non-empty row IDs")
    if not isinstance(known_effects, Mapping):
        raise ValueError("known_side_effects must be an object")
    if not isinstance(source_digest, str) or not SHA256_DIGEST.fullmatch(source_digest):
        raise ValueError("source_reference_manifest_digest must be a SHA-256 digest")
    effects_by_row: dict[str, list[str]] = {}
    for row_id in sorted(affected):
        effects = known_effects.get(row_id)
        if (
            not isinstance(effects, list)
            or not effects
            or len(effects) != len(set(effects))
            or any(not isinstance(effect, str) or not effect for effect in effects)
        ):
            raise ValueError(f"privacy row {row_id} must have unique frozen effects")
        effects_by_row[row_id] = sorted(effects)
    return {
        "schema": PRIVACY_FROZEN_MANIFEST_SCHEMA,
        "affected_row_ids": sorted(affected),
        "effects_by_row": effects_by_row,
        "source_reference_manifest_digest": source_digest,
    }


def privacy_frozen_manifest_digest(scope: Mapping[str, Any]) -> str:
    """Digest the exact frozen privacy denominator."""

    return owner_binding_digest(privacy_frozen_manifest(scope))


def privacy_manifest_binding_errors(owner_evidence: Any, scope: Mapping[str, Any]) -> list[str]:
    """Check that privacy owner evidence binds the frozen scope manifest."""

    if not isinstance(owner_evidence, Mapping):
        return ["privacy owner evidence must be an object"]
    try:
        expected = privacy_frozen_manifest_digest(scope)
    except ValueError as exc:
        return [f"privacy frozen manifest is invalid: {exc}"]
    if owner_evidence.get("frozen_manifest_digest") != expected:
        return ["privacy frozen_manifest_digest does not match the scope"]
    return []


def frozen_effect_atoms(
    scope: Mapping[str, Any],
    *,
    row_ids: Iterable[str] | None = None,
) -> list[tuple[str, str]]:
    """Enumerate a stable row/effect denominator from the frozen scope."""

    known_effects = scope.get("known_side_effects")
    if not isinstance(known_effects, Mapping):
        raise ValueError("known_side_effects must be an object")
    selected = sorted(set(row_ids)) if row_ids is not None else sorted(known_effects)
    atoms: list[tuple[str, str]] = []
    for row_id in selected:
        effects = known_effects.get(row_id)
        if not isinstance(effects, list) or len(effects) != len(set(effects)):
            raise ValueError(f"known_side_effects[{row_id}] must be a unique list")
        for effect in sorted(effects):
            if not isinstance(effect, str) or not effect:
                raise ValueError(f"known_side_effects[{row_id}] contains an invalid effect")
            atoms.append((row_id, effect))
    return atoms


def effect_owner_outcome_errors(
    scope: Mapping[str, Any],
    outcomes: Any,
    *,
    row_ids: Iterable[str] | None = None,
) -> list[str]:
    """Validate one terminal owner outcome and receipt per frozen effect atom."""

    try:
        expected = frozen_effect_atoms(scope, row_ids=row_ids)
    except ValueError as exc:
        return [str(exc)]
    if not isinstance(outcomes, list):
        return ["effect owner outcomes must be a list"]
    errors: list[str] = []
    observed: list[tuple[str, str]] = []
    for index, outcome in enumerate(outcomes):
        label = f"effect owner outcome[{index}]"
        if not isinstance(outcome, Mapping):
            errors.append(f"{label} must be an object")
            continue
        if outcome.get("schema") != EFFECT_OUTCOME_SCHEMA:
            errors.append(f"{label} schema must be {EFFECT_OUTCOME_SCHEMA}")
        row_id = outcome.get("row_id")
        effect = outcome.get("effect")
        if isinstance(row_id, str) and isinstance(effect, str):
            observed.append((row_id, effect))
        else:
            errors.append(f"{label} row_id and effect are required")
        if outcome.get("status") != "verified":
            errors.append(f"{label} status must be verified")
        if outcome.get("outcome") not in _TERMINAL_EFFECT_OUTCOMES:
            errors.append(f"{label} outcome is not terminal")
        owner = outcome.get("owner")
        if not isinstance(owner, str) or not owner or owner != owner.strip():
            errors.append(f"{label} owner is invalid")
        if outcome.get("replay_authorized") is not False:
            errors.append(f"{label} must explicitly deny replay")
        if receipt_identity(outcome.get("receipt")) is None:
            errors.append(f"{label} receipt identity is invalid")
    if len(observed) != len(set(observed)):
        errors.append("effect owner outcomes contain duplicate row/effect atoms")
    if sorted(observed) != expected:
        errors.append("effect owner outcomes do not match the frozen row/effect denominator")
    return errors


def effect_owner_outcomes_digest(outcomes: Any) -> str:
    """Return a semantic digest for an already validated effect-outcome registry."""

    return owner_binding_digest(outcomes)
