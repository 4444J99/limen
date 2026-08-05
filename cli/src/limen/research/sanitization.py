"""Sanitization gates for tracked research outcomes and receipts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .contracts import (
    ATTESTATION_NAME_MAX_LENGTH,
    ResearchContractError,
    canonical_json,
    iso_datetime,
    mapping,
    stable_hash,
)


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SECRET = re.compile(
    r"(?i)(?:\bsk-[A-Za-z0-9_-]{8,}|\bpplx-[A-Za-z0-9_-]{20,}|"
    r"\bbearer\s+\S+|"
    r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|"
    r"\bAKIA[A-Z0-9]{16}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?:api[_-]?key|access[_-]?token|private[_-]?key|client[_-]?secret|password)"
    r"\s*[:=]\s*[\"']?[^,\s\"'}]{4,})"
)
_HASH = re.compile(r"^sha256:[a-f0-9]{64}$")
_PRESERVATION_TIERS = {
    "public_facing",
    "operational_internal",
    "client_private",
    "essence_private",
}
_TRANSMISSION_CLASSES = {"public_only", "sanitized_only", "forbidden"}


@dataclass(frozen=True)
class OutputSanitizationAttestation:
    """Studium-owned proof that the exact ingested export is track-safe."""

    request_id: str
    attested_at: str
    attestor: str
    export_hash: str
    preservation_tier: str
    external_transmission: str
    tracked_output_safe: bool
    contains_credentials: bool
    contains_private_prompt_body: bool
    contains_sensitive_raw_material: bool
    redactions_applied: tuple[str, ...]
    canonical_payload: Mapping[str, object]

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
        *,
        expected_request_id: str,
        expected_export_hash: str,
        expected_preservation_tier: str,
        expected_external_transmission: str,
    ) -> OutputSanitizationAttestation:
        data = mapping(payload, field_name="output sanitization attestation")
        exact = {
            "schema_version",
            "request_id",
            "attested_at",
            "attestor",
            "export_hash",
            "preservation_tier",
            "external_transmission",
            "tracked_output_safe",
            "contains_credentials",
            "contains_private_prompt_body",
            "contains_sensitive_raw_material",
            "redactions_applied",
        }
        if set(data) != exact:
            raise ResearchContractError("output sanitization attestation requires exact canonical fields")
        if data.get("schema_version") != "1.0":
            raise ResearchContractError("output sanitization attestation schema_version must be 1.0")
        request_id = str(data.get("request_id") or "").strip()
        if request_id != expected_request_id:
            raise ResearchContractError("output sanitization attestation request_id mismatch")
        attested_at = str(data.get("attested_at") or "").strip()
        if not iso_datetime(attested_at):
            raise ResearchContractError("output sanitization attestation requires attested_at")
        attestor = str(data.get("attestor") or "").strip()
        if not attestor or len(attestor) > ATTESTATION_NAME_MAX_LENGTH or _SECRET.search(attestor):
            raise ResearchContractError("output sanitization attestation requires a safe bounded attestor")
        export_hash = str(data.get("export_hash") or "").strip()
        if not _HASH.fullmatch(export_hash) or export_hash != expected_export_hash:
            raise ResearchContractError("output sanitization attestation export_hash mismatch")
        preservation_tier = str(data.get("preservation_tier") or "").strip()
        if preservation_tier not in _PRESERVATION_TIERS or preservation_tier != expected_preservation_tier:
            raise ResearchContractError("output sanitization attestation preservation_tier mismatch")
        external_transmission = str(data.get("external_transmission") or "").strip()
        if (
            external_transmission not in _TRANSMISSION_CLASSES
            or external_transmission != expected_external_transmission
        ):
            raise ResearchContractError("output sanitization attestation external_transmission mismatch")
        for field_name, expected in (
            ("tracked_output_safe", True),
            ("contains_credentials", False),
            ("contains_private_prompt_body", False),
            ("contains_sensitive_raw_material", False),
        ):
            if data.get(field_name) is not expected:
                raise ResearchContractError(f"output sanitization attestation {field_name} must be {expected}")
        raw_redactions = data.get("redactions_applied")
        if not isinstance(raw_redactions, Sequence) or isinstance(raw_redactions, (str, bytes)):
            raise ResearchContractError("output sanitization attestation redactions_applied must be an array")
        redactions = tuple(str(value).strip() for value in raw_redactions)
        if any(not value for value in redactions) or len(redactions) != len(set(redactions)):
            raise ResearchContractError("output sanitization attestation redactions must be unique non-empty strings")
        if external_transmission == "sanitized_only" and not redactions:
            raise ResearchContractError("sanitized_only output requires an applied redaction")
        return cls(
            request_id=request_id,
            attested_at=attested_at,
            attestor=attestor,
            export_hash=export_hash,
            preservation_tier=preservation_tier,
            external_transmission=external_transmission,
            tracked_output_safe=True,
            contains_credentials=False,
            contains_private_prompt_body=False,
            contains_sensitive_raw_material=False,
            redactions_applied=redactions,
            canonical_payload=data,
        )

    @property
    def receipt_verifier(self) -> str:
        return f"{self.attestor} attestation {stable_hash(self.canonical_payload)}"


def observed_identifier(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    identifier = value.strip()
    if not _IDENTIFIER.fullmatch(identifier) or _SECRET.search(identifier):
        raise ResearchContractError(f"{field_name} is not a safe observed identifier")
    return identifier


def assert_receipt_sanitized(payload: Mapping[str, object], *, private_question: str) -> None:
    serialized = canonical_json(payload)
    if private_question in serialized:
        raise ResearchContractError("receipt contains the private prompt body")
    if _SECRET.search(serialized):
        raise ResearchContractError("receipt contains credential-like material")


def assert_tracked_output_machine_safe(rendered_output: str, *, private_question: str) -> None:
    """Reject prompt or credential material before a tracked report is written."""

    if "\x00" in rendered_output:
        raise ResearchContractError("tracked output contains a NUL byte")
    question = private_question.strip()
    if question and question in rendered_output:
        raise ResearchContractError("tracked output contains the private request question")
    if _SECRET.search(rendered_output):
        raise ResearchContractError("tracked output contains credential-like material")


def assert_raw_export_custody_boundary(
    markdown: str,
    *,
    private_question: str,
    raw_export_ref: str | None,
) -> None:
    """Require private custody when the raw export retains prompt or secret text."""

    question = private_question.strip()
    contains_private_material = bool((question and question in markdown) or _SECRET.search(markdown))
    if contains_private_material and not (raw_export_ref and raw_export_ref.startswith("private-owner://")):
        raise ResearchContractError(
            "raw export containing prompt or credential material requires private-owner custody"
        )
