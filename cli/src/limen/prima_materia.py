"""Portable contracts for process-as-art provenance and encrypted custody."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

import rfc8785
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReplayClass = Literal["exact", "semantic", "observable_only"]
_Digest = str


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _validate_opaque_id(value: str) -> str:
    if not 16 <= len(value) <= 128 or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for character in value
    ):
        raise ValueError("opaque ID must be a bounded base64url-style identifier")
    return value


def _validate_registry_key(value: str) -> str:
    if not 1 <= len(value) <= 256 or "\x00" in value or value.strip() != value:
        raise ValueError("registry key must be a bounded nonblank string")
    return value


def _validate_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value


def _validate_optional_aware_datetime(value: datetime | None) -> datetime | None:
    return _validate_aware_datetime(value) if value is not None else None


class PrimaMateriaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EncryptedPayloadRefV1(PrimaMateriaModel):
    schema_version: Literal["limen.encrypted_payload_ref.v1"] = "limen.encrypted_payload_ref.v1"
    object_id: str
    ciphertext_sha256: _Digest
    encryption_profile_digest: _Digest
    chunk_manifest_digest: _Digest
    ciphertext_bytes: int = Field(ge=0)

    _object_id = field_validator("object_id")(_validate_opaque_id)
    _digests = field_validator(
        "ciphertext_sha256",
        "encryption_profile_digest",
        "chunk_manifest_digest",
    )(_validate_digest)


class PrivacyConsentPolicyV1(PrimaMateriaModel):
    schema_version: Literal["limen.privacy_consent_policy.v1"] = "limen.privacy_consent_policy.v1"
    policy_digest: _Digest
    purpose: str = Field(min_length=1, max_length=4096)
    access_scope: tuple[str, ...] = Field(min_length=1, max_length=256)
    publication_requires_receipt: bool = True
    consent_receipt_ref: str | None = None

    _digest = field_validator("policy_digest")(_validate_digest)
    _scopes = field_validator("access_scope")(lambda values: tuple(_validate_registry_key(value) for value in values))


class ResourceClaimV1(PrimaMateriaModel):
    schema_version: Literal["limen.resource_claim.v1"] = "limen.resource_claim.v1"
    claim_id: str
    hydrated_inputs_bytes: int = Field(ge=0)
    workspace_bytes: int = Field(ge=0)
    temporary_expansion_bytes: int = Field(ge=0)
    output_bytes: int = Field(ge=0)
    encryption_chunking_bytes: int = Field(ge=0)
    rollback_bytes: int = Field(ge=0)
    effective_from: datetime
    effective_until: datetime
    rollback_until: datetime

    _claim_id = field_validator("claim_id")(_validate_opaque_id)
    _times = field_validator(
        "effective_from",
        "effective_until",
        "rollback_until",
    )(_validate_aware_datetime)

    @model_validator(mode="after")
    def ordered_lifetime(self) -> ResourceClaimV1:
        if not self.effective_from < self.effective_until <= self.rollback_until:
            raise ValueError("claim lifetime must be effective_from < effective_until <= rollback_until")
        return self

    def active_bytes(self, observed_at: datetime) -> int:
        if self.effective_from <= observed_at < self.effective_until:
            return (
                self.hydrated_inputs_bytes + self.workspace_bytes + self.temporary_expansion_bytes + self.output_bytes
            )
        if self.effective_until <= observed_at < self.rollback_until:
            return self.output_bytes
        return 0


class PrimaMateriaEventV1(PrimaMateriaModel):
    schema_version: Literal["limen.prima_materia_event.v1"] = "limen.prima_materia_event.v1"
    event_id: str
    source_id: str
    adapter_digest: _Digest
    source_schema_digest: _Digest
    observed_at: datetime
    effective_at: datetime
    domain_tags: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    actor_id: str
    authority_ref: str
    causal_event_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=1024)
    intent_event_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=1024)
    encrypted_payloads: tuple[EncryptedPayloadRefV1, ...] = Field(default_factory=tuple, max_length=1024)
    input_digests: tuple[_Digest, ...] = Field(default_factory=tuple, max_length=1024)
    output_digests: tuple[_Digest, ...] = Field(default_factory=tuple, max_length=1024)
    privacy: PrivacyConsentPolicyV1
    replay_class: ReplayClass

    _opaque_ids = field_validator("event_id", "source_id")(_validate_opaque_id)
    _digests = field_validator("adapter_digest", "source_schema_digest")(_validate_digest)
    _times = field_validator("observed_at", "effective_at")(_validate_aware_datetime)
    _domain_tags = field_validator("domain_tags")(
        lambda values: tuple(_validate_registry_key(value) for value in values)
    )
    _lineage = field_validator("causal_event_ids", "intent_event_ids")(
        lambda values: tuple(_validate_opaque_id(value) for value in values)
    )
    _io_digests = field_validator("input_digests", "output_digests")(
        lambda values: tuple(_validate_digest(value) for value in values)
    )


class SourceAdapterV1(PrimaMateriaModel):
    schema_version: Literal["limen.source_adapter.v1"] = "limen.source_adapter.v1"
    adapter_id: str
    source_id: str
    owner_ref: str
    source_native_acquisition: str
    cursor_schema_digest: _Digest
    completeness_predicate: str
    privacy_transform_digest: _Digest
    resource_claim: ResourceClaimV1
    recipe_version: str
    custody_target_refs: tuple[str, ...] = Field(min_length=1, max_length=32)
    restoration_predicate: str

    _source_id = field_validator("source_id")(_validate_opaque_id)
    _registry = field_validator("adapter_id", "owner_ref", "recipe_version")(_validate_registry_key)
    _digests = field_validator("cursor_schema_digest", "privacy_transform_digest")(_validate_digest)


class TransformRecipeV1(PrimaMateriaModel):
    schema_version: Literal["limen.transform_recipe.v1"] = "limen.transform_recipe.v1"
    recipe_id: str
    version: str
    input_digests: tuple[_Digest, ...] = Field(min_length=1, max_length=4096)
    code_digest: _Digest
    tool_digests: tuple[_Digest, ...] = Field(default_factory=tuple, max_length=256)
    config_digest: _Digest
    environment_digest: _Digest
    parameters: dict[str, Any] = Field(default_factory=dict)
    randomness_declaration: str = Field(min_length=1, max_length=4096)
    time_declaration: str = Field(min_length=1, max_length=4096)
    output_digests: tuple[_Digest, ...] = Field(min_length=1, max_length=4096)
    replay_class: ReplayClass
    semantic_equivalence_predicate: str | None = None
    original_output_refs: tuple[EncryptedPayloadRefV1, ...] = Field(default_factory=tuple)

    _registry = field_validator("recipe_id", "version")(_validate_registry_key)
    _digests = field_validator(
        "input_digests",
        "tool_digests",
        "output_digests",
    )(lambda values: tuple(_validate_digest(value) for value in values))
    _single_digests = field_validator("code_digest", "config_digest", "environment_digest")(_validate_digest)

    @model_validator(mode="after")
    def replay_evidence_is_honest(self) -> TransformRecipeV1:
        if self.replay_class == "semantic" and (
            not self.semantic_equivalence_predicate or not self.original_output_refs
        ):
            raise ValueError("semantic replay requires an equivalence predicate and preserved original outputs")
        if self.replay_class == "exact" and self.semantic_equivalence_predicate is not None:
            raise ValueError("exact replay must not substitute semantic equivalence")
        if self.replay_class == "observable_only" and not self.original_output_refs:
            raise ValueError("observable-only replay requires preserved original outputs")
        return self


class ActionReceiptV1(PrimaMateriaModel):
    schema_version: Literal["limen.action_receipt.v1"] = "limen.action_receipt.v1"
    action_id: str
    authority_ref: str
    idempotency_key: str
    precondition_digest: _Digest
    provider_object_id: str
    provider_version: str
    provider_evidence_digest: _Digest
    postcondition_digest: _Digest
    reversibility: Literal["reversible", "compensating", "irreversible"]
    undo_evidence_digest: _Digest | None = None
    replay_class: Literal["observable_only"] = "observable_only"
    observed_at: datetime

    _action_id = field_validator("action_id")(_validate_opaque_id)
    _digests = field_validator(
        "precondition_digest",
        "provider_evidence_digest",
        "postcondition_digest",
    )(_validate_digest)
    _undo = field_validator("undo_evidence_digest")(lambda value: _validate_digest(value) if value else value)
    _observed_at = field_validator("observed_at")(_validate_aware_datetime)

    @model_validator(mode="after")
    def reversible_actions_have_undo_evidence(self) -> ActionReceiptV1:
        if self.reversibility != "irreversible" and self.undo_evidence_digest is None:
            raise ValueError("reversible actions require undo evidence")
        return self


class RestorationProofV1(PrimaMateriaModel):
    custody_target_ref: str
    device_id: str
    restored_at: datetime
    restored_output_digest: _Digest
    predicate_digest: _Digest
    passed: Literal[True] = True

    _device_id = field_validator("device_id")(_validate_opaque_id)
    _digests = field_validator("restored_output_digest", "predicate_digest")(_validate_digest)
    _restored_at = field_validator("restored_at")(_validate_aware_datetime)


class CustodyReceiptV1(PrimaMateriaModel):
    schema_version: Literal["limen.custody_receipt.v1"] = "limen.custody_receipt.v1"
    custody_id: str
    encryption_profile_digest: _Digest
    chunk_manifest_digests: tuple[_Digest, ...] = Field(min_length=1, max_length=4096)
    independent_device_ids: tuple[str, ...] = Field(min_length=2, max_length=32)
    remote_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    restoration_proofs: tuple[RestorationProofV1, ...] = Field(min_length=2, max_length=32)

    _custody_id = field_validator("custody_id")(_validate_opaque_id)
    _profile = field_validator("encryption_profile_digest")(_validate_digest)
    _manifests = field_validator("chunk_manifest_digests")(
        lambda values: tuple(_validate_digest(value) for value in values)
    )
    _devices = field_validator("independent_device_ids")(
        lambda values: tuple(_validate_opaque_id(value) for value in values)
    )

    @model_validator(mode="after")
    def copies_are_independent_and_restored(self) -> CustodyReceiptV1:
        device_ids = set(self.independent_device_ids)
        if len(device_ids) != len(self.independent_device_ids):
            raise ValueError("custody device identities must be independent")
        restored = {proof.custody_target_ref for proof in self.restoration_proofs}
        if len(restored) < 2:
            raise ValueError("at least two distinct custody targets must be restore-tested")
        restored_devices = {proof.device_id for proof in self.restoration_proofs}
        if not restored_devices.issubset(device_ids):
            raise ValueError("restoration proof device must belong to the custody receipt")
        if len(restored_devices) < 2:
            raise ValueError("at least two independent custody devices must be restore-tested")
        return self


class CompositionManifestV1(PrimaMateriaModel):
    schema_version: Literal["limen.composition_manifest.v1"] = "limen.composition_manifest.v1"
    composition_id: str
    selected_event_ids: tuple[str, ...] = Field(min_length=1, max_length=100_000)
    ordering: Literal["observed_time", "effective_time", "explicit"]
    explicit_order: tuple[str, ...] = Field(default_factory=tuple, max_length=100_000)
    omissions: tuple[str, ...] = Field(default_factory=tuple, max_length=100_000)
    decision_receipt_digests: tuple[_Digest, ...] = Field(
        default_factory=tuple,
        max_length=100_000,
    )
    redaction_receipt_digests: tuple[_Digest, ...] = Field(default_factory=tuple, max_length=100_000)
    failure_receipt_digests: tuple[_Digest, ...] = Field(
        default_factory=tuple,
        max_length=100_000,
    )
    custody_receipt_digests: tuple[_Digest, ...] = Field(
        default_factory=tuple,
        max_length=100_000,
    )
    transform_recipe_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100_000)
    output_digests: tuple[_Digest, ...] = Field(min_length=1, max_length=100_000)

    _composition_id = field_validator("composition_id")(_validate_opaque_id)
    _event_ids = field_validator("selected_event_ids", "explicit_order")(
        lambda values: tuple(_validate_opaque_id(value) for value in values)
    )
    _digests = field_validator(
        "decision_receipt_digests",
        "redaction_receipt_digests",
        "failure_receipt_digests",
        "custody_receipt_digests",
        "output_digests",
    )(lambda values: tuple(_validate_digest(value) for value in values))

    @model_validator(mode="after")
    def explicit_order_is_complete(self) -> CompositionManifestV1:
        selected = set(self.selected_event_ids)
        if len(selected) != len(self.selected_event_ids):
            raise ValueError("selected events must be unique")
        if self.ordering == "explicit" and (
            len(self.explicit_order) != len(self.selected_event_ids) or set(self.explicit_order) != selected
        ):
            raise ValueError("explicit ordering must enumerate selected events exactly")
        if self.ordering != "explicit" and self.explicit_order:
            raise ValueError("explicit_order is only valid with explicit ordering")
        return self


class DerivedCapabilityV1(PrimaMateriaModel):
    schema_version: Literal["limen.derived_capability.v1"] = "limen.derived_capability.v1"
    authority_id: str
    action: str
    plan_sha256: _Digest
    batch_id: str
    capability_digest: _Digest

    _authority_id = field_validator("authority_id")(_validate_opaque_id)
    _plan = field_validator("plan_sha256", "capability_digest")(_validate_digest)


class StandingAuthorityV1(PrimaMateriaModel):
    schema_version: Literal["limen.standing_authority.v1"] = "limen.standing_authority.v1"
    authority_id: str
    principal_ref: str
    migrated_signed_authority_digest: _Digest
    permitted_actions: frozenset[str] = Field(min_length=1, max_length=256)
    credential_references: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    issued_at: datetime
    revoked_at: datetime | None = None
    revocation_receipt_digest: _Digest | None = None

    _authority_id = field_validator("authority_id")(_validate_opaque_id)
    _migration = field_validator("migrated_signed_authority_digest")(_validate_digest)
    _issued_at = field_validator("issued_at")(_validate_aware_datetime)
    _revoked_at = field_validator("revoked_at")(_validate_optional_aware_datetime)
    _revocation = field_validator("revocation_receipt_digest")(
        lambda value: _validate_digest(value) if value else value
    )

    @model_validator(mode="after")
    def revocation_is_well_formed(self) -> StandingAuthorityV1:
        if (self.revoked_at is None) != (self.revocation_receipt_digest is None):
            raise ValueError("revocation time and receipt must appear together")
        return self

    def derive(self, *, action: str, plan_sha256: str, batch_id: str) -> DerivedCapabilityV1:
        if self.revoked_at is not None:
            raise ValueError("standing authority is revoked")
        if action not in self.permitted_actions:
            raise ValueError("action is outside standing authority")
        _validate_digest(plan_sha256)
        payload = {
            "schema_version": "limen.derived_capability.v1",
            "authority_id": self.authority_id,
            "action": action,
            "plan_sha256": plan_sha256,
            "batch_id": batch_id,
            "migrated_signed_authority_digest": self.migrated_signed_authority_digest,
        }
        return DerivedCapabilityV1(
            authority_id=self.authority_id,
            action=action,
            plan_sha256=plan_sha256,
            batch_id=batch_id,
            capability_digest=_canonical_digest(payload),
        )


class SourceCoverageV1(PrimaMateriaModel):
    schema_version: Literal["limen.source_coverage.v1"] = "limen.source_coverage.v1"
    registry_digest: _Digest
    observed_source_ids: tuple[str, ...]
    registered_source_ids: tuple[str, ...]
    missing_adapter_source_ids: tuple[str, ...]

    _digest = field_validator("registry_digest")(_validate_digest)
    _ids = field_validator(
        "observed_source_ids",
        "registered_source_ids",
        "missing_adapter_source_ids",
    )(lambda values: tuple(_validate_opaque_id(value) for value in values))

    @classmethod
    def reconcile(
        cls,
        *,
        registry_digest: str,
        observed_source_ids: tuple[str, ...],
        adapters: tuple[SourceAdapterV1, ...],
    ) -> SourceCoverageV1:
        registered = tuple(sorted({adapter.source_id for adapter in adapters}))
        observed = tuple(sorted(set(observed_source_ids)))
        missing = tuple(sorted(set(observed) - set(registered)))
        return cls(
            registry_digest=registry_digest,
            observed_source_ids=observed,
            registered_source_ids=registered,
            missing_adapter_source_ids=missing,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)
