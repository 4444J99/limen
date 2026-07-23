"""Owner-verifier attestation required before an EvidencePacket can be accepted."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

from .contracts import (
    ATTESTATION_NAME_MAX_LENGTH,
    ResearchContractError,
    canonical_json,
    iso_datetime,
    mapping,
    stable_hash,
)

_CLAIM_ID = re.compile(r"^CLM-[A-Z0-9-]+$")
_SOURCE_ID = re.compile(r"^SRC-[A-Z0-9-]+$")
_STATUSES = {
    "supported",
    "partially_supported",
    "contradicted",
    "unsupported",
    "not_applicable",
}
_QUALITY_TIERS = {"A", "B", "C", "D"}


@dataclass(frozen=True)
class VerifiedClaim:
    claim_id: str
    verification_status: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class VerifiedSource:
    source_id: str
    url: str
    resolvable: bool
    source_type: str
    primary_source: bool
    quality_tier: str
    language: str | None
    jurisdictions: tuple[str, ...]


@dataclass(frozen=True)
class SourceVerifierAttestation:
    request_id: str
    verified_at: str
    verifier: str
    verdict: str
    claims: Mapping[str, VerifiedClaim]
    sources: Mapping[str, VerifiedSource]
    canonical_payload: Mapping[str, object]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object], *, expected_request_id: str) -> SourceVerifierAttestation:
        data = mapping(payload, field_name="source verifier attestation")
        allowed = {
            "schema_version",
            "request_id",
            "verified_at",
            "verifier",
            "verdict",
            "private_connected_sources_used",
            "claims",
            "sources",
        }
        extras = sorted(set(data) - allowed)
        if extras:
            raise ResearchContractError("source verifier attestation contains unknown fields: " + ",".join(extras))
        if data.get("schema_version") != "1.0":
            raise ResearchContractError("source verifier attestation schema_version must be 1.0")
        request_id = str(data.get("request_id") or "").strip()
        if request_id != expected_request_id:
            raise ResearchContractError("source verifier attestation request_id mismatch")
        verified_at = str(data.get("verified_at") or "").strip()
        if not iso_datetime(verified_at):
            raise ResearchContractError("source verifier attestation requires verified_at")
        verifier = str(data.get("verifier") or "").strip()
        if not verifier or len(verifier) > ATTESTATION_NAME_MAX_LENGTH:
            raise ResearchContractError("source verifier attestation requires a bounded verifier")
        verdict = str(data.get("verdict") or "").strip()
        if verdict not in {"accepted", "rejected"}:
            raise ResearchContractError("source verifier attestation verdict is invalid")
        if data.get("private_connected_sources_used") is not False:
            raise ResearchContractError("private connected sources are forbidden")

        claims: dict[str, VerifiedClaim] = {}
        raw_claims = data.get("claims")
        if not isinstance(raw_claims, Sequence) or isinstance(raw_claims, (str, bytes)):
            raise ResearchContractError("source verifier attestation claims must be a list")
        for item in raw_claims:
            claim = mapping(item, field_name="verified claim")
            if set(claim) != {"claim_id", "verification_status", "source_ids"}:
                raise ResearchContractError("verified claims require exact canonical fields")
            claim_id = str(claim.get("claim_id") or "").strip()
            status = str(claim.get("verification_status") or "").strip()
            raw_source_ids = claim.get("source_ids")
            if not _CLAIM_ID.fullmatch(claim_id) or status not in _STATUSES:
                raise ResearchContractError("verified claim identifier or status is invalid")
            if not isinstance(raw_source_ids, Sequence) or isinstance(raw_source_ids, (str, bytes)):
                raise ResearchContractError("verified claim source_ids must be a list")
            source_ids = tuple(str(value).strip() for value in raw_source_ids)
            if len(set(source_ids)) != len(source_ids) or any(not _SOURCE_ID.fullmatch(value) for value in source_ids):
                raise ResearchContractError("verified claim source_ids are invalid")
            if claim_id in claims:
                raise ResearchContractError("verified claim identifiers must be unique")
            claims[claim_id] = VerifiedClaim(claim_id, status, source_ids)

        sources: dict[str, VerifiedSource] = {}
        raw_sources = data.get("sources")
        if not isinstance(raw_sources, Sequence) or isinstance(raw_sources, (str, bytes)):
            raise ResearchContractError("source verifier attestation sources must be a list")
        for item in raw_sources:
            source = mapping(item, field_name="verified source")
            allowed_source = {
                "source_id",
                "url",
                "resolvable",
                "source_type",
                "primary_source",
                "quality_tier",
                "metadata_confirmed",
                "language",
                "jurisdictions",
            }
            if set(source) - allowed_source:
                raise ResearchContractError("verified source contains unknown fields")
            required_source = {
                "source_id",
                "url",
                "resolvable",
                "source_type",
                "primary_source",
                "quality_tier",
                "metadata_confirmed",
            }
            if not required_source.issubset(source):
                raise ResearchContractError("verified source is missing canonical fields")
            source_id = str(source.get("source_id") or "").strip()
            url = str(source.get("url") or "").strip()
            parsed_url = urlparse(url)
            resolvable = source.get("resolvable")
            source_type = str(source.get("source_type") or "").strip()
            quality_tier = str(source.get("quality_tier") or "").strip().upper()
            primary = source.get("primary_source")
            if (
                not _SOURCE_ID.fullmatch(source_id)
                or not re.fullmatch(r"https?://[^\s]+", url)
                or parsed_url.username is not None
                or parsed_url.password is not None
                or not parsed_url.hostname
                or not isinstance(resolvable, bool)
                or not source_type
                or not isinstance(primary, bool)
                or quality_tier not in _QUALITY_TIERS
                or source.get("metadata_confirmed") is not True
            ):
                raise ResearchContractError("verified source grading is invalid")
            language = str(source.get("language") or "").strip() or None
            raw_jurisdictions = source.get("jurisdictions") or ()
            if not isinstance(raw_jurisdictions, Sequence) or isinstance(raw_jurisdictions, (str, bytes)):
                raise ResearchContractError("verified source jurisdictions must be a list")
            jurisdictions = tuple(str(value).strip() for value in raw_jurisdictions)
            if source_id in sources:
                raise ResearchContractError("verified source identifiers must be unique")
            sources[source_id] = VerifiedSource(
                source_id,
                url,
                resolvable,
                source_type,
                primary,
                quality_tier,
                language,
                jurisdictions,
            )

        return cls(
            request_id=request_id,
            verified_at=verified_at,
            verifier=verifier,
            verdict=verdict,
            claims=claims,
            sources=sources,
            canonical_payload=data,
        )

    @property
    def receipt_verifier(self) -> str:
        return f"{self.verifier} attestation {stable_hash(self.canonical_payload)}"

    def canonical_json(self) -> str:
        return canonical_json(self.canonical_payload)
