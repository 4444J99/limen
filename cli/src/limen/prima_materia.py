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


def _validate_git_sha(value: str) -> str:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("Git SHA must be a full lowercase SHA-1")
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
    schema_version: Literal["limen.prima_materia_resource_claim.v1"] = "limen.prima_materia_resource_claim.v1"
    claim_id: str
    source_instance_id: str
    operation_id: str
    hydrated_inputs_bytes: int = Field(ge=0)
    workspace_bytes: int = Field(ge=0)
    temporary_expansion_bytes: int = Field(ge=0)
    output_bytes: int = Field(ge=0)
    encryption_chunking_bytes: int = Field(ge=0)
    rollback_bytes: int = Field(ge=0)
    memory_bytes: int = Field(ge=0)
    file_count: int = Field(ge=0)
    network_bytes: int = Field(ge=0)
    wall_time_seconds: int = Field(ge=1, le=2_592_000)
    effective_from: datetime
    effective_until: datetime
    rollback_until: datetime

    _opaque_ids = field_validator(
        "claim_id",
        "source_instance_id",
        "operation_id",
    )(_validate_opaque_id)
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
    claim_recipe: str
    recipe_version: str
    custody_target_refs: tuple[str, ...] = Field(min_length=1, max_length=32)
    restoration_predicate: str

    _source_id = field_validator("source_id")(_validate_opaque_id)
    _registry = field_validator(
        "adapter_id",
        "owner_ref",
        "claim_recipe",
        "recipe_version",
    )(_validate_registry_key)
    _digests = field_validator("cursor_schema_digest", "privacy_transform_digest")(_validate_digest)


class FrozenRepositoryV1(PrimaMateriaModel):
    repository_id: str
    path_sha256: _Digest

    _repository_id = field_validator("repository_id")(_validate_opaque_id)
    _path = field_validator("path_sha256")(_validate_digest)


class FrozenStorageRootV1(PrimaMateriaModel):
    root_id: str
    path_sha256: _Digest

    _root_id = field_validator("root_id")(_validate_opaque_id)
    _path = field_validator("path_sha256")(_validate_digest)


class FrozenSourceInstanceV1(PrimaMateriaModel):
    instance_id: str
    source_id: str

    _ids = field_validator("instance_id", "source_id")(_validate_opaque_id)


class FrozenDeviceRoleV1(PrimaMateriaModel):
    role_id: str
    physical_device_sha256: _Digest

    _role = field_validator("role_id")(_validate_registry_key)
    _device = field_validator("physical_device_sha256")(_validate_digest)


class FrozenWaveManifestV1(PrimaMateriaModel):
    """One immutable denominator for a pair of independent λ audits."""

    schema_version: Literal["limen.frozen_wave_manifest.v1"] = "limen.frozen_wave_manifest.v1"
    wave_id: str
    frozen_at: datetime
    enumeration_complete: bool
    repositories: tuple[FrozenRepositoryV1, ...] = Field(max_length=4096)
    storage_roots: tuple[FrozenStorageRootV1, ...] = Field(max_length=4096)
    source_instances: tuple[FrozenSourceInstanceV1, ...] = Field(min_length=1, max_length=8192)
    device_roles: tuple[FrozenDeviceRoleV1, ...] = Field(max_length=64)
    protected_exclusion_ids: tuple[str, ...] = Field(max_length=256)
    protected_registry_digest: _Digest
    source_registry_digest: _Digest
    source_inventory_producer_digest: _Digest
    lambda_rung_registry_digest: _Digest
    remote_main_sha: str
    installed_runtime_sha: str
    control_plane_runtime_path_sha256: _Digest
    control_plane_repository: str
    control_plane_default_branch: str

    _wave_id = field_validator("wave_id")(_validate_opaque_id)
    _frozen_at = field_validator("frozen_at")(_validate_aware_datetime)
    _protected = field_validator("protected_exclusion_ids")(
        lambda values: tuple(_validate_registry_key(value) for value in values)
    )
    _registry_digests = field_validator(
        "protected_registry_digest",
        "source_registry_digest",
        "source_inventory_producer_digest",
        "lambda_rung_registry_digest",
        "control_plane_runtime_path_sha256",
    )(_validate_digest)
    _control_shas = field_validator(
        "remote_main_sha",
        "installed_runtime_sha",
    )(_validate_git_sha)
    _control_registry = field_validator(
        "control_plane_repository",
        "control_plane_default_branch",
    )(_validate_registry_key)

    @model_validator(mode="after")
    def denominator_is_unique_and_ordered(self) -> FrozenWaveManifestV1:
        collections = (
            ("repositories", tuple(item.repository_id for item in self.repositories)),
            ("storage_roots", tuple(item.root_id for item in self.storage_roots)),
            ("source_instances", tuple(item.instance_id for item in self.source_instances)),
            ("device_roles", tuple(item.role_id for item in self.device_roles)),
            ("protected_exclusions", self.protected_exclusion_ids),
        )
        for label, values in collections:
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must contain unique identities")
            if tuple(sorted(values)) != values:
                raise ValueError(f"{label} must be sorted")
        return self


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


ProjectCoverageDisposition = Literal["complete", "partial", "unknown", "blocked", "superseded"]
ProjectBuildStatus = Literal["not_started", "passed", "failed", "blocked", "unknown"]
RelationshipRole = Literal[
    "reference",
    "research",
    "audience",
    "prospect",
    "client",
    "advisor",
    "contributor",
    "co_builder",
]
ProjectAccessLevel = Literal["none", "read", "write", "admin"]
RepositoryAccessLevel = Literal["none", "read", "triage", "write", "maintain", "admin"]
AccessStatus = Literal["not_granted", "pending", "active", "declined", "identity_unresolved"]
CollaboratorCoverageDisposition = Literal["reconciled", "pending", "declined", "identity_unresolved", "unknown"]


def _validate_sorted_unique_registry_values(values: tuple[str, ...], label: str) -> None:
    validated = tuple(_validate_registry_key(value) for value in values)
    if len(validated) != len(set(validated)):
        raise ValueError(f"{label} must contain unique identities")
    if tuple(sorted(validated)) != validated:
        raise ValueError(f"{label} must be sorted")


def _validate_universe_source_coverage(
    *,
    required: tuple[str, ...],
    observed: tuple[str, ...],
    missing: tuple[str, ...],
    unexpected: tuple[str, ...],
) -> None:
    for label, values in (
        ("required_source_instance_ids", required),
        ("observed_source_instance_ids", observed),
        ("missing_source_instance_ids", missing),
        ("unexpected_source_instance_ids", unexpected),
    ):
        _validate_sorted_unique_registry_values(values, label)
    expected_missing = tuple(sorted(set(required) - set(observed)))
    expected_unexpected = tuple(sorted(set(observed) - set(required)))
    if missing != expected_missing:
        raise ValueError("missing source instances must equal required minus observed")
    if unexpected != expected_unexpected:
        raise ValueError("unexpected source instances must equal observed minus required")


def _validate_universe_identity_coverage(
    *,
    required: tuple[str, ...],
    observed: tuple[str, ...],
    missing: tuple[str, ...],
    unexpected: tuple[str, ...],
    label: str,
) -> None:
    for field_label, values in (
        (f"required_{label}_ids", required),
        (f"observed_{label}_ids", observed),
        (f"missing_{label}_ids", missing),
        (f"unexpected_{label}_ids", unexpected),
    ):
        _validate_sorted_unique_registry_values(values, field_label)
    expected_missing = tuple(sorted(set(required) - set(observed)))
    expected_unexpected = tuple(sorted(set(observed) - set(required)))
    if missing != expected_missing:
        raise ValueError(f"missing {label} identities must equal required minus observed")
    if unexpected != expected_unexpected:
        raise ValueError(f"unexpected {label} identities must equal observed minus required")


class UniverseSourceAdapterV1(PrimaMateriaModel):
    """One dynamically configured source class for both universe manifests."""

    schema_version: Literal["limen.universe_source_adapter.v1"] = "limen.universe_source_adapter.v1"
    adapter_id: str
    source_kind: str
    owner_ref: str
    census_enumerator_ref: str
    project_enumerator_ref: str
    collaborator_enumerator_ref: str
    completeness_predicate: str = Field(min_length=1, max_length=4096)
    privacy_projection_ref: str

    _registry = field_validator(
        "adapter_id",
        "source_kind",
        "owner_ref",
        "census_enumerator_ref",
        "project_enumerator_ref",
        "collaborator_enumerator_ref",
        "privacy_projection_ref",
    )(_validate_registry_key)


class UniverseSourceRegistryV1(PrimaMateriaModel):
    """Order-independent registry whose members define the live source denominator."""

    schema_version: Literal["limen.universe_source_registry.v1"] = "limen.universe_source_registry.v1"
    registry_id: str
    adapters: tuple[UniverseSourceAdapterV1, ...] = Field(min_length=1, max_length=4096)

    _registry_id = field_validator("registry_id")(_validate_opaque_id)

    @model_validator(mode="after")
    def source_classes_are_unique(self) -> UniverseSourceRegistryV1:
        adapter_ids = tuple(adapter.adapter_id for adapter in self.adapters)
        source_kinds = tuple(adapter.source_kind for adapter in self.adapters)
        if len(adapter_ids) != len(set(adapter_ids)):
            raise ValueError("universe source adapter identities must be unique")
        if len(source_kinds) != len(set(source_kinds)):
            raise ValueError("universe source kinds must be unique")
        return self

    @property
    def source_kinds(self) -> tuple[str, ...]:
        return tuple(sorted(adapter.source_kind for adapter in self.adapters))

    @property
    def canonical_digest(self) -> str:
        payload = self.model_dump(mode="json")
        payload["adapters"] = sorted(
            payload["adapters"],
            key=lambda adapter: (adapter["source_kind"], adapter["adapter_id"]),
        )
        return _canonical_digest(payload)


class ProjectUniverseEntryV1(PrimaMateriaModel):
    project_id: str
    alias_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    source_lineage_ids: tuple[str, ...] = Field(min_length=1, max_length=4096)
    repository_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=1024)
    child_task_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100_000)
    artifact_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    collaborator_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    lifecycle_stage: str
    predicate_refs: tuple[str, ...] = Field(min_length=1, max_length=4096)
    receipt_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    coverage_disposition: ProjectCoverageDisposition
    build_status: ProjectBuildStatus

    _project_id = field_validator("project_id")(_validate_opaque_id)
    _lifecycle_stage = field_validator("lifecycle_stage")(_validate_registry_key)

    @model_validator(mode="after")
    def evidence_is_canonical_and_build_is_proven(self) -> ProjectUniverseEntryV1:
        for label, values in (
            ("alias_ids", self.alias_ids),
            ("source_lineage_ids", self.source_lineage_ids),
            ("repository_ids", self.repository_ids),
            ("child_task_ids", self.child_task_ids),
            ("artifact_refs", self.artifact_refs),
            ("collaborator_ids", self.collaborator_ids),
            ("predicate_refs", self.predicate_refs),
            ("receipt_refs", self.receipt_refs),
        ):
            _validate_sorted_unique_registry_values(values, label)
        if self.project_id in self.alias_ids:
            raise ValueError("project aliases must not repeat the canonical project identity")
        if self.coverage_disposition == "complete" and not self.receipt_refs:
            raise ValueError("complete project coverage requires a durable receipt")
        if self.build_status == "passed" and (not self.artifact_refs or not self.receipt_refs):
            raise ValueError("passed project builds require a usable artifact and durable receipt")
        return self


class ProjectUniverseManifestV1(PrimaMateriaModel):
    schema_version: Literal["limen.project_universe_manifest.v1"] = "limen.project_universe_manifest.v1"
    manifest_id: str
    frozen_at: datetime
    frozen_wave_digest: _Digest
    source_registry_digest: _Digest
    enumeration_complete: bool
    required_source_instance_ids: tuple[str, ...] = Field(min_length=1, max_length=100_000)
    observed_source_instance_ids: tuple[str, ...] = Field(max_length=100_000)
    missing_source_instance_ids: tuple[str, ...] = Field(max_length=100_000)
    unexpected_source_instance_ids: tuple[str, ...] = Field(max_length=100_000)
    required_project_ids: tuple[str, ...] = Field(min_length=1, max_length=100_000)
    missing_project_ids: tuple[str, ...] = Field(max_length=100_000)
    unexpected_project_ids: tuple[str, ...] = Field(max_length=100_000)
    projects: tuple[ProjectUniverseEntryV1, ...] = Field(max_length=100_000)

    _manifest_id = field_validator("manifest_id")(_validate_opaque_id)
    _frozen_at = field_validator("frozen_at")(_validate_aware_datetime)
    _digests = field_validator("frozen_wave_digest", "source_registry_digest")(_validate_digest)

    @model_validator(mode="after")
    def denominator_is_source_derived_and_projects_are_distinct(self) -> ProjectUniverseManifestV1:
        _validate_universe_source_coverage(
            required=self.required_source_instance_ids,
            observed=self.observed_source_instance_ids,
            missing=self.missing_source_instance_ids,
            unexpected=self.unexpected_source_instance_ids,
        )
        project_ids = tuple(project.project_id for project in self.projects)
        _validate_universe_identity_coverage(
            required=self.required_project_ids,
            observed=project_ids,
            missing=self.missing_project_ids,
            unexpected=self.unexpected_project_ids,
            label="project",
        )
        child_task_ids = {task_id for project in self.projects for task_id in project.child_task_ids}
        conflated = sorted(set(project_ids) & child_task_ids)
        if conflated:
            raise ValueError("project identities and child task identities must remain distinct")
        return self

    @property
    def source_coverage_complete(self) -> bool:
        return (
            self.enumeration_complete
            and not self.missing_source_instance_ids
            and not self.unexpected_source_instance_ids
        )

    @property
    def canonical_project_coverage_complete(self) -> bool:
        return (
            not self.missing_project_ids
            and not self.unexpected_project_ids
            and all(project.coverage_disposition == "complete" for project in self.projects)
        )

    @property
    def all_canonical_projects_built(self) -> bool:
        return (
            self.source_coverage_complete
            and self.canonical_project_coverage_complete
            and bool(self.projects)
            and all(project.build_status == "passed" for project in self.projects)
        )


class CollaboratorRepositoryAccessV1(PrimaMateriaModel):
    repository_id: str
    access_level: RepositoryAccessLevel
    status: AccessStatus
    authority_ref: str | None = None
    receipt_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)

    _repository_id = field_validator("repository_id")(_validate_registry_key)
    _authority_ref = field_validator("authority_ref")(
        lambda value: _validate_registry_key(value) if value is not None else None
    )

    @model_validator(mode="after")
    def access_has_independent_evidence(self) -> CollaboratorRepositoryAccessV1:
        _validate_sorted_unique_registry_values(self.receipt_refs, "repository access receipts")
        if self.status in {"not_granted", "declined", "identity_unresolved"} and self.access_level != "none":
            raise ValueError("inactive repository access must use the none level")
        if self.status in {"pending", "active"} and self.access_level == "none":
            raise ValueError("pending or active repository access requires an explicit level")
        if self.status != "not_granted" and not self.receipt_refs:
            raise ValueError("repository access disposition requires a source-owned receipt")
        if self.status == "active" and self.authority_ref is None:
            raise ValueError("active repository access requires explicit authority")
        return self


class CollaboratorProjectRelationshipV1(PrimaMateriaModel):
    project_id: str
    roles: tuple[RelationshipRole, ...] = Field(min_length=1, max_length=6)
    project_access_level: ProjectAccessLevel = "none"
    project_access_status: AccessStatus = "not_granted"
    project_authority_ref: str | None = None
    project_access_receipt_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    repository_accesses: tuple[CollaboratorRepositoryAccessV1, ...] = Field(default_factory=tuple, max_length=1024)

    _project_id = field_validator("project_id")(_validate_registry_key)
    _authority_ref = field_validator("project_authority_ref")(
        lambda value: _validate_registry_key(value) if value is not None else None
    )

    @model_validator(mode="after")
    def project_access_is_role_bounded_and_separate(self) -> CollaboratorProjectRelationshipV1:
        if len(self.roles) != len(set(self.roles)) or tuple(sorted(self.roles)) != self.roles:
            raise ValueError("relationship roles must be unique and sorted")
        _validate_sorted_unique_registry_values(
            self.project_access_receipt_refs,
            "project access receipts",
        )
        repository_ids = tuple(access.repository_id for access in self.repository_accesses)
        _validate_sorted_unique_registry_values(repository_ids, "repository accesses")
        if self.project_access_status in {"not_granted", "declined", "identity_unresolved"}:
            if self.project_access_level != "none":
                raise ValueError("inactive Project access must use the none level")
        elif self.project_access_level == "none":
            raise ValueError("pending or active Project access requires an explicit level")
        if self.project_access_status != "not_granted" and not self.project_access_receipt_refs:
            raise ValueError("Project access disposition requires a source-owned receipt")
        if self.project_access_status == "active" and self.project_authority_ref is None:
            raise ValueError("active Project access requires explicit authority")
        allowed_levels: set[ProjectAccessLevel] = {"none"}
        if "advisor" in self.roles:
            allowed_levels.add("read")
        if "contributor" in self.roles:
            allowed_levels.update({"read", "write"})
        if "co_builder" in self.roles:
            allowed_levels.update({"read", "write", "admin"})
        if self.project_access_level not in allowed_levels:
            raise ValueError("Project access exceeds the source-classified relationship role")
        return self


class CollaboratorUniverseEntryV1(PrimaMateriaModel):
    collaborator_id: str
    alias_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    source_lineage_ids: tuple[str, ...] = Field(min_length=1, max_length=4096)
    github_login_sha256: _Digest | None = None
    github_identity_receipt_ref: str | None = None
    relationships: tuple[CollaboratorProjectRelationshipV1, ...] = Field(min_length=1, max_length=4096)
    coverage_disposition: CollaboratorCoverageDisposition
    disposition_receipt_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)

    _collaborator_id = field_validator("collaborator_id")(_validate_opaque_id)
    _github_digest = field_validator("github_login_sha256")(
        lambda value: _validate_digest(value) if value is not None else None
    )
    _github_receipt = field_validator("github_identity_receipt_ref")(
        lambda value: _validate_registry_key(value) if value is not None else None
    )

    @model_validator(mode="after")
    def identity_is_private_proven_and_actually_collaborative(self) -> CollaboratorUniverseEntryV1:
        _validate_sorted_unique_registry_values(self.alias_ids, "collaborator aliases")
        _validate_sorted_unique_registry_values(self.source_lineage_ids, "collaborator source lineages")
        _validate_sorted_unique_registry_values(self.disposition_receipt_refs, "collaborator disposition receipts")
        if self.collaborator_id in self.alias_ids:
            raise ValueError("collaborator aliases must not repeat the canonical collaborator identity")
        project_ids = tuple(relationship.project_id for relationship in self.relationships)
        _validate_sorted_unique_registry_values(project_ids, "collaborator project relationships")
        if (self.github_login_sha256 is None) != (self.github_identity_receipt_ref is None):
            raise ValueError("GitHub identity digest and proof receipt must appear together")
        collaborator_roles = {"prospect", "client", "advisor", "contributor", "co_builder"}
        if not any(collaborator_roles.intersection(relationship.roles) for relationship in self.relationships):
            raise ValueError("reference-only identities stay outside the collaborator universe")
        access_needs_identity = any(
            relationship.project_access_status in {"pending", "active"}
            or any(access.status in {"pending", "active"} for access in relationship.repository_accesses)
            for relationship in self.relationships
        )
        if access_needs_identity and self.github_login_sha256 is None:
            raise ValueError("pending or active access requires a proven GitHub identity")
        if self.coverage_disposition != "unknown" and not self.disposition_receipt_refs:
            raise ValueError("collaborator disposition requires a source-owned receipt")
        return self


class CollaboratorUniverseManifestV1(PrimaMateriaModel):
    schema_version: Literal["limen.collaborator_universe_manifest.v1"] = "limen.collaborator_universe_manifest.v1"
    manifest_id: str
    frozen_at: datetime
    frozen_wave_digest: _Digest
    source_registry_digest: _Digest
    project_universe_manifest_digest: _Digest
    enumeration_complete: bool
    required_source_instance_ids: tuple[str, ...] = Field(min_length=1, max_length=100_000)
    observed_source_instance_ids: tuple[str, ...] = Field(max_length=100_000)
    missing_source_instance_ids: tuple[str, ...] = Field(max_length=100_000)
    unexpected_source_instance_ids: tuple[str, ...] = Field(max_length=100_000)
    project_ids: tuple[str, ...] = Field(min_length=1, max_length=100_000)
    required_collaborator_ids: tuple[str, ...] = Field(min_length=1, max_length=100_000)
    missing_collaborator_ids: tuple[str, ...] = Field(max_length=100_000)
    unexpected_collaborator_ids: tuple[str, ...] = Field(max_length=100_000)
    collaborators: tuple[CollaboratorUniverseEntryV1, ...] = Field(max_length=100_000)

    _manifest_id = field_validator("manifest_id")(_validate_opaque_id)
    _frozen_at = field_validator("frozen_at")(_validate_aware_datetime)
    _digests = field_validator(
        "frozen_wave_digest",
        "source_registry_digest",
        "project_universe_manifest_digest",
    )(_validate_digest)

    @model_validator(mode="after")
    def denominator_is_source_derived_and_identities_are_distinct(self) -> CollaboratorUniverseManifestV1:
        _validate_universe_source_coverage(
            required=self.required_source_instance_ids,
            observed=self.observed_source_instance_ids,
            missing=self.missing_source_instance_ids,
            unexpected=self.unexpected_source_instance_ids,
        )
        _validate_sorted_unique_registry_values(self.project_ids, "project_ids")
        collaborator_ids = tuple(collaborator.collaborator_id for collaborator in self.collaborators)
        _validate_universe_identity_coverage(
            required=self.required_collaborator_ids,
            observed=collaborator_ids,
            missing=self.missing_collaborator_ids,
            unexpected=self.unexpected_collaborator_ids,
            label="collaborator",
        )
        unknown_projects = sorted(
            {
                relationship.project_id
                for collaborator in self.collaborators
                for relationship in collaborator.relationships
            }
            - set(self.project_ids)
        )
        if unknown_projects:
            raise ValueError("collaborator relationships must reference the bound project universe")
        return self

    @property
    def source_coverage_complete(self) -> bool:
        return (
            self.enumeration_complete
            and not self.missing_source_instance_ids
            and not self.unexpected_source_instance_ids
        )

    @property
    def collaborator_coverage_complete(self) -> bool:
        return (
            not self.missing_collaborator_ids
            and not self.unexpected_collaborator_ids
            and all(collaborator.coverage_disposition != "unknown" for collaborator in self.collaborators)
        )

    @property
    def reconciled(self) -> bool:
        return self.source_coverage_complete and self.collaborator_coverage_complete and bool(self.collaborators)


def utc_now() -> datetime:
    return datetime.now(UTC)
