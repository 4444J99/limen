from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from limen.prima_materia import (
    CollaboratorProjectRelationshipV1,
    CollaboratorRepositoryAccessV1,
    CollaboratorUniverseEntryV1,
    CollaboratorUniverseManifestV1,
    CompositionManifestV1,
    CustodyReceiptV1,
    EncryptedPayloadRefV1,
    PrimaMateriaEventV1,
    PrivacyConsentPolicyV1,
    ProjectUniverseEntryV1,
    ProjectUniverseManifestV1,
    ResourceClaimV1,
    RestorationProofV1,
    SourceAdapterV1,
    SourceCoverageV1,
    StandingAuthorityV1,
    TransformRecipeV1,
    UniverseSourceAdapterV1,
    UniverseSourceRegistryV1,
)

DIGEST = "a" * 64
OPAQUE_SOURCE = "opaqueSource000001"


def _claim(identifier: str = "claimIdentifier01") -> ResourceClaimV1:
    start = datetime(2026, 7, 28, tzinfo=UTC)
    return ResourceClaimV1(
        claim_id=identifier,
        source_instance_id="sourceInstance001",
        operation_id="operationInstance01",
        hydrated_inputs_bytes=1,
        workspace_bytes=2,
        temporary_expansion_bytes=3,
        output_bytes=4,
        encryption_chunking_bytes=5,
        rollback_bytes=6,
        memory_bytes=7,
        file_count=8,
        network_bytes=9,
        wall_time_seconds=10,
        effective_from=start,
        effective_until=start + timedelta(hours=1),
        rollback_until=start + timedelta(hours=2),
    )


def _adapter(adapter_id: str, source_id: str) -> SourceAdapterV1:
    return SourceAdapterV1(
        adapter_id=adapter_id,
        source_id=source_id,
        owner_ref=f"owner-{adapter_id}",
        source_native_acquisition="source-owned cursor stream",
        cursor_schema_digest=DIGEST,
        completeness_predicate="source cursor is exhausted",
        privacy_transform_digest=DIGEST,
        claim_recipe=f"claim-recipe-{source_id}",
        recipe_version="recipe-v1",
        custody_target_refs=("encrypted-primary", "encrypted-recovery"),
        restoration_predicate="both targets restore",
    )


def _universe_source(adapter_id: str, source_kind: str) -> UniverseSourceAdapterV1:
    return UniverseSourceAdapterV1(
        adapter_id=adapter_id,
        source_kind=source_kind,
        owner_ref=f"owner-{source_kind}",
        census_enumerator_ref=f"{source_kind}-census-v1",
        project_enumerator_ref=f"{source_kind}-projects-v1",
        collaborator_enumerator_ref=f"{source_kind}-collaborators-v1",
        completeness_predicate=f"all {source_kind} source instances have terminal dispositions",
        privacy_projection_ref=f"{source_kind}-privacy-projection-v1",
    )


def test_universe_source_registry_is_dynamic_order_independent_and_fail_closed() -> None:
    source_a = _universe_source("adapter-a", "source-a")
    source_b = _universe_source("adapter-b", "source-b")
    source_c = _universe_source("adapter-c", "source-c")

    first = UniverseSourceRegistryV1(
        registry_id="universeSources001",
        adapters=(source_b, source_a),
    )
    reordered = UniverseSourceRegistryV1(
        registry_id="universeSources001",
        adapters=(source_a, source_b),
    )
    added = UniverseSourceRegistryV1(
        registry_id="universeSources001",
        adapters=(source_a, source_b, source_c),
    )
    removed = UniverseSourceRegistryV1(
        registry_id="universeSources001",
        adapters=(source_a,),
    )

    assert first.source_kinds == ("source-a", "source-b")
    assert first.canonical_digest == reordered.canonical_digest
    assert added.canonical_digest != first.canonical_digest
    assert removed.canonical_digest != first.canonical_digest

    with pytest.raises(ValueError, match="adapter identities"):
        UniverseSourceRegistryV1(
            registry_id="universeSources001",
            adapters=(source_a, source_a.model_copy(update={"source_kind": "source-z"})),
        )
    with pytest.raises(ValueError, match="source kinds"):
        UniverseSourceRegistryV1(
            registry_id="universeSources001",
            adapters=(source_a, source_b.model_copy(update={"source_kind": "source-a"})),
        )


def test_tracked_universe_source_registry_binds_both_manifests_without_a_code_denominator() -> None:
    root = Path(__file__).resolve().parents[2]
    registry_path = root / "institutio" / "governance" / "prima-materia-universe-sources.json"
    registry = UniverseSourceRegistryV1.model_validate_json(registry_path.read_text())
    reordered = UniverseSourceRegistryV1(
        registry_id=registry.registry_id,
        adapters=tuple(reversed(registry.adapters)),
    )

    assert registry.source_kinds == tuple(sorted(registry.source_kinds))
    assert registry.canonical_digest == reordered.canonical_digest
    assert all(adapter.project_enumerator_ref for adapter in registry.adapters)
    assert all(adapter.collaborator_enumerator_ref for adapter in registry.adapters)
    assert all(adapter.privacy_projection_ref for adapter in registry.adapters)


def test_arbitrary_adapter_order_and_unknown_source_debt() -> None:
    source_a = "sourceIdentifierA1"
    source_b = "sourceIdentifierB2"
    missing = "sourceIdentifierC3"
    adapters = (_adapter("z-adapter", source_b), _adapter("a-adapter", source_a))

    first = SourceCoverageV1.reconcile(
        registry_digest=DIGEST,
        observed_source_ids=(missing, source_a, source_b),
        adapters=adapters,
    )
    reordered = SourceCoverageV1.reconcile(
        registry_digest=DIGEST,
        observed_source_ids=(source_b, missing, source_a),
        adapters=tuple(reversed(adapters)),
    )
    removed = SourceCoverageV1.reconcile(
        registry_digest=DIGEST,
        observed_source_ids=(source_a, source_b),
        adapters=(adapters[0],),
    )

    assert first == reordered
    assert first.missing_adapter_source_ids == (missing,)
    assert removed.missing_adapter_source_ids == (source_a,)


def test_event_accepts_registry_domain_tags_without_taxonomy_code() -> None:
    event = PrimaMateriaEventV1(
        event_id="opaqueEvent0000001",
        source_id=OPAQUE_SOURCE,
        adapter_digest=DIGEST,
        source_schema_digest=DIGEST,
        observed_at=datetime.now(UTC),
        effective_at=datetime.now(UTC),
        domain_tags=("future.domain/new-kind", "anything the registry owns"),
        actor_id="private actor reference",
        authority_ref="authority receipt",
        encrypted_payloads=(
            EncryptedPayloadRefV1(
                object_id="opaquePayload00001",
                ciphertext_sha256=DIGEST,
                encryption_profile_digest=DIGEST,
                chunk_manifest_digest=DIGEST,
                ciphertext_bytes=10,
            ),
        ),
        privacy=PrivacyConsentPolicyV1(
            policy_digest=DIGEST,
            purpose="bounded test",
            access_scope=("private",),
        ),
        replay_class="exact",
    )
    assert event.domain_tags[0] == "future.domain/new-kind"


def test_contract_times_require_explicit_utc_offsets() -> None:
    with pytest.raises(ValueError, match="explicit UTC offset"):
        ResourceClaimV1(
            claim_id="claimIdentifier01",
            source_instance_id="sourceInstance001",
            operation_id="operationInstance01",
            hydrated_inputs_bytes=1,
            workspace_bytes=2,
            temporary_expansion_bytes=3,
            output_bytes=4,
            encryption_chunking_bytes=5,
            rollback_bytes=6,
            memory_bytes=7,
            file_count=8,
            network_bytes=9,
            wall_time_seconds=10,
            effective_from=datetime(2026, 7, 28, tzinfo=UTC).replace(tzinfo=None),
            effective_until=datetime(2026, 7, 28, 1, tzinfo=UTC).replace(tzinfo=None),
            rollback_until=datetime(2026, 7, 28, 2, tzinfo=UTC).replace(tzinfo=None),
        )


def test_semantic_recipe_requires_original_output_and_equivalence() -> None:
    with pytest.raises(ValueError, match="semantic replay"):
        TransformRecipeV1(
            recipe_id="model-work",
            version="v1",
            input_digests=(DIGEST,),
            code_digest=DIGEST,
            config_digest=DIGEST,
            environment_digest=DIGEST,
            randomness_declaration="provider controlled",
            time_declaration="recorded",
            output_digests=(DIGEST,),
            replay_class="semantic",
        )


def test_observable_only_recipe_requires_preserved_original_output() -> None:
    with pytest.raises(ValueError, match="observable-only replay"):
        TransformRecipeV1(
            recipe_id="external-action",
            version="v1",
            input_digests=(DIGEST,),
            code_digest=DIGEST,
            config_digest=DIGEST,
            environment_digest=DIGEST,
            randomness_declaration="provider controlled",
            time_declaration="provider observed",
            output_digests=(DIGEST,),
            replay_class="observable_only",
        )


def test_explicit_composition_order_accepts_a_complete_permutation() -> None:
    manifest = CompositionManifestV1(
        composition_id="compositionId0001",
        selected_event_ids=("eventIdentifierA1", "eventIdentifierB2"),
        ordering="explicit",
        explicit_order=("eventIdentifierB2", "eventIdentifierA1"),
        decision_receipt_digests=(DIGEST,),
        redaction_receipt_digests=(DIGEST,),
        failure_receipt_digests=(DIGEST,),
        custody_receipt_digests=(DIGEST,),
        output_digests=(DIGEST,),
    )

    assert manifest.explicit_order == (
        "eventIdentifierB2",
        "eventIdentifierA1",
    )
    assert manifest.decision_receipt_digests == (DIGEST,)
    assert manifest.failure_receipt_digests == (DIGEST,)
    assert manifest.custody_receipt_digests == (DIGEST,)

    with pytest.raises(ValueError, match="enumerate selected events exactly"):
        CompositionManifestV1(
            **{
                **manifest.model_dump(),
                "explicit_order": ("eventIdentifierA1",),
            },
        )


def test_custody_restoration_proofs_cover_independent_devices() -> None:
    restored_at = datetime(2026, 7, 28, tzinfo=UTC)
    proofs = (
        RestorationProofV1(
            custody_target_ref="encrypted-primary",
            device_id="deviceIdentifierA1",
            restored_at=restored_at,
            restored_output_digest=DIGEST,
            predicate_digest=DIGEST,
        ),
        RestorationProofV1(
            custody_target_ref="encrypted-recovery",
            device_id="deviceIdentifierB2",
            restored_at=restored_at,
            restored_output_digest=DIGEST,
            predicate_digest=DIGEST,
        ),
    )
    receipt = CustodyReceiptV1(
        custody_id="custodyReceipt0001",
        encryption_profile_digest=DIGEST,
        chunk_manifest_digests=(DIGEST,),
        independent_device_ids=(
            "deviceIdentifierA1",
            "deviceIdentifierB2",
        ),
        restoration_proofs=proofs,
    )

    assert {proof.device_id for proof in receipt.restoration_proofs} == {
        "deviceIdentifierA1",
        "deviceIdentifierB2",
    }

    with pytest.raises(
        ValueError,
        match="independent custody devices must be restore-tested",
    ):
        CustodyReceiptV1(
            custody_id="custodyReceipt0002",
            encryption_profile_digest=DIGEST,
            chunk_manifest_digests=(DIGEST,),
            independent_device_ids=(
                "deviceIdentifierA1",
                "deviceIdentifierB2",
            ),
            restoration_proofs=(
                proofs[0],
                proofs[1].model_copy(
                    update={"device_id": "deviceIdentifierA1"},
                ),
            ),
        )


def test_standing_authority_has_no_time_or_attempt_cap_and_revocation_fails_closed() -> None:
    authority = StandingAuthorityV1(
        authority_id="standingAuthority01",
        principal_ref="vault-principal-reference",
        migrated_signed_authority_digest=DIGEST,
        permitted_actions=frozenset({"file-provider-custody"}),
        credential_references=("op://vault/item/field",),
        issued_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    capabilities = {
        authority.derive(
            action="file-provider-custody",
            plan_sha256=f"{ordinal:064x}",
            batch_id=f"batch-{ordinal}",
        ).capability_digest
        for ordinal in range(300)
    }
    assert len(capabilities) == 300
    assert "expires_at" not in authority.model_dump()
    assert "max_attempts" not in authority.model_dump()

    revoked = authority.model_copy(
        update={
            "revoked_at": datetime.now(UTC),
            "revocation_receipt_digest": "b" * 64,
        }
    )
    with pytest.raises(ValueError, match="revoked"):
        revoked.derive(
            action="file-provider-custody",
            plan_sha256=DIGEST,
            batch_id="next",
        )


def _project(
    project_id: str,
    *,
    repository_ids: tuple[str, ...] = (),
    child_task_ids: tuple[str, ...] = (),
) -> ProjectUniverseEntryV1:
    return ProjectUniverseEntryV1(
        project_id=project_id,
        source_lineage_ids=(f"lineage-{project_id}",),
        repository_ids=repository_ids,
        child_task_ids=child_task_ids,
        artifact_refs=(f"artifact-{project_id}",),
        collaborator_ids=(),
        lifecycle_stage="verified",
        predicate_refs=(f"predicate-{project_id}",),
        receipt_refs=(f"receipt-{project_id}",),
        coverage_disposition="complete",
        build_status="passed",
    )


def test_project_universe_supports_zero_and_multiple_repositories_without_task_conflation() -> None:
    multi_repository = _project(
        "projectIdentifierA1",
        repository_ids=("repository-a", "repository-b"),
        child_task_ids=("task-a",),
    )
    zero_repository = _project(
        "projectIdentifierB2",
        child_task_ids=("task-b",),
    )
    manifest = ProjectUniverseManifestV1(
        manifest_id="projectManifest001",
        frozen_at=datetime(2026, 7, 28, tzinfo=UTC),
        frozen_wave_digest=DIGEST,
        source_registry_digest=DIGEST,
        enumeration_complete=True,
        required_source_instance_ids=("source-a", "source-b"),
        observed_source_instance_ids=("source-a", "source-b"),
        missing_source_instance_ids=(),
        unexpected_source_instance_ids=(),
        required_project_ids=("projectIdentifierA1", "projectIdentifierB2"),
        missing_project_ids=(),
        unexpected_project_ids=(),
        projects=(multi_repository, zero_repository),
    )

    assert manifest.source_coverage_complete
    assert manifest.all_canonical_projects_built
    assert len(manifest.projects[0].repository_ids) == 2
    assert manifest.projects[1].repository_ids == ()

    with pytest.raises(ValueError, match="project identities and child task identities"):
        ProjectUniverseManifestV1(
            **{
                **manifest.model_dump(),
                "projects": (
                    multi_repository.model_copy(update={"child_task_ids": ("projectIdentifierB2",)}),
                    zero_repository,
                ),
            }
        )


def test_project_universe_rejects_false_source_and_build_completion() -> None:
    with pytest.raises(ValueError, match="missing source instances"):
        ProjectUniverseManifestV1(
            manifest_id="projectManifest002",
            frozen_at=datetime(2026, 7, 28, tzinfo=UTC),
            frozen_wave_digest=DIGEST,
            source_registry_digest=DIGEST,
            enumeration_complete=True,
            required_source_instance_ids=("source-a", "source-b"),
            observed_source_instance_ids=("source-a",),
            missing_source_instance_ids=(),
            unexpected_source_instance_ids=(),
            required_project_ids=("projectIdentifierA1",),
            missing_project_ids=("projectIdentifierA1",),
            unexpected_project_ids=(),
            projects=(),
        )

    with pytest.raises(ValueError, match="missing project identities"):
        ProjectUniverseManifestV1(
            manifest_id="projectManifest003",
            frozen_at=datetime(2026, 7, 28, tzinfo=UTC),
            frozen_wave_digest=DIGEST,
            source_registry_digest=DIGEST,
            enumeration_complete=True,
            required_source_instance_ids=("source-a",),
            observed_source_instance_ids=("source-a",),
            missing_source_instance_ids=(),
            unexpected_source_instance_ids=(),
            required_project_ids=("projectIdentifierA1", "projectIdentifierB2"),
            missing_project_ids=(),
            unexpected_project_ids=(),
            projects=(_project("projectIdentifierA1"),),
        )

    with pytest.raises(ValueError, match="usable artifact"):
        ProjectUniverseEntryV1.model_validate(
            {
                **_project("projectIdentifierC3").model_dump(),
                "artifact_refs": (),
            }
        )


def _collaborator(
    collaborator_id: str,
    *,
    roles: tuple[str, ...],
    project_access_level: str,
    project_access_status: str,
    repository_accesses: tuple[CollaboratorRepositoryAccessV1, ...] = (),
    coverage_disposition: str = "reconciled",
) -> CollaboratorUniverseEntryV1:
    needs_identity = project_access_status in {"pending", "active"} or any(
        access.status in {"pending", "active"} for access in repository_accesses
    )
    access_receipts = () if project_access_status == "not_granted" else (f"project-access-{collaborator_id}",)
    return CollaboratorUniverseEntryV1(
        collaborator_id=collaborator_id,
        source_lineage_ids=(f"lineage-{collaborator_id}",),
        github_login_sha256=DIGEST if needs_identity else None,
        github_identity_receipt_ref=f"github-proof-{collaborator_id}" if needs_identity else None,
        relationships=(
            CollaboratorProjectRelationshipV1(
                project_id="project-a",
                roles=roles,
                project_access_level=project_access_level,
                project_access_status=project_access_status,
                project_authority_ref=f"authority-{collaborator_id}" if project_access_status == "active" else None,
                project_access_receipt_refs=access_receipts,
                repository_accesses=repository_accesses,
            ),
        ),
        coverage_disposition=coverage_disposition,
        disposition_receipt_refs=(f"disposition-{collaborator_id}",),
    )


def test_collaborator_universe_is_not_capped_by_three_live_grants() -> None:
    def active_repository_access(*suffixes: str) -> tuple[CollaboratorRepositoryAccessV1, ...]:
        return tuple(
            CollaboratorRepositoryAccessV1(
                repository_id=f"repository-{suffix}",
                access_level="write",
                status="active",
                authority_ref=f"repository-authority-{suffix}",
                receipt_refs=(f"repository-receipt-{suffix}",),
            )
            for suffix in suffixes
        )

    collaborators = (
        _collaborator(
            "collaboratorIdA01",
            roles=("co_builder",),
            project_access_level="admin",
            project_access_status="active",
            repository_accesses=active_repository_access("a", "b"),
        ),
        _collaborator(
            "collaboratorIdB02",
            roles=("contributor",),
            project_access_level="write",
            project_access_status="active",
            repository_accesses=active_repository_access("c"),
        ),
        _collaborator(
            "collaboratorIdC03",
            roles=("advisor",),
            project_access_level="read",
            project_access_status="active",
        ),
        _collaborator(
            "collaboratorIdD04",
            roles=("advisor",),
            project_access_level="none",
            project_access_status="declined",
            coverage_disposition="declined",
        ),
    )
    manifest = CollaboratorUniverseManifestV1(
        manifest_id="collaboratorManifest01",
        frozen_at=datetime(2026, 7, 28, tzinfo=UTC),
        frozen_wave_digest=DIGEST,
        source_registry_digest=DIGEST,
        project_universe_manifest_digest=DIGEST,
        enumeration_complete=True,
        required_source_instance_ids=("source-a", "source-b"),
        observed_source_instance_ids=("source-a", "source-b"),
        missing_source_instance_ids=(),
        unexpected_source_instance_ids=(),
        project_ids=("project-a",),
        required_collaborator_ids=tuple(collaborator.collaborator_id for collaborator in collaborators),
        missing_collaborator_ids=(),
        unexpected_collaborator_ids=(),
        collaborators=collaborators,
    )

    assert sum(len(item.relationships[0].repository_accesses) for item in collaborators) == 3
    assert len(manifest.collaborators) == 4
    assert manifest.reconciled
    assert collaborators[2].relationships[0].project_access_level == "read"
    assert collaborators[2].relationships[0].repository_accesses == ()

    with pytest.raises(ValueError, match="missing collaborator identities"):
        CollaboratorUniverseManifestV1(
            **{
                **manifest.model_dump(),
                "required_collaborator_ids": (*manifest.required_collaborator_ids, "collaboratorIdE05"),
                "missing_collaborator_ids": (),
            }
        )


def test_collaborator_roles_and_access_fail_closed() -> None:
    with pytest.raises(ValueError, match="reference-only identities"):
        _collaborator(
            "referenceIdentity01",
            roles=("reference", "research"),
            project_access_level="none",
            project_access_status="not_granted",
        )

    with pytest.raises(ValueError, match="exceeds the source-classified"):
        _collaborator(
            "overgrantIdentity01",
            roles=("contributor",),
            project_access_level="admin",
            project_access_status="active",
        )

    client = _collaborator(
        "clientIdentity001",
        roles=("client",),
        project_access_level="none",
        project_access_status="not_granted",
        coverage_disposition="identity_unresolved",
    )
    prospect = _collaborator(
        "prospectIdentity01",
        roles=("prospect",),
        project_access_level="none",
        project_access_status="not_granted",
        coverage_disposition="identity_unresolved",
    )
    assert client.relationships[0].project_access_level == "none"
    assert prospect.relationships[0].project_access_level == "none"
    with pytest.raises(ValueError, match="exceeds the source-classified"):
        _collaborator(
            "clientOvergrant01",
            roles=("client",),
            project_access_level="read",
            project_access_status="active",
        )

    relationship = CollaboratorProjectRelationshipV1(
        project_id="project-a",
        roles=("advisor",),
        project_access_level="read",
        project_access_status="active",
        project_authority_ref="project-authority",
        project_access_receipt_refs=("project-access-receipt",),
    )
    with pytest.raises(ValueError, match="proven GitHub identity"):
        CollaboratorUniverseEntryV1(
            collaborator_id="unprovenIdentity01",
            source_lineage_ids=("lineage-unproven",),
            relationships=(relationship,),
            coverage_disposition="reconciled",
            disposition_receipt_refs=("disposition-unproven",),
        )


def test_generated_schemas_match_models(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, str(root / "scripts" / "generate-prima-materia-schemas.py")],
        check=True,
        cwd=root,
    )
    schemas = root / "spec" / "contracts" / "prima-materia"
    expected = {
        "action-receipt-v1.schema.json",
        "collaborator-universe-manifest-v1.schema.json",
        "composition-manifest-v1.schema.json",
        "custody-receipt-v1.schema.json",
        "frozen-wave-manifest-v1.schema.json",
        "prima-materia-event-v1.schema.json",
        "project-universe-manifest-v1.schema.json",
        "resource-claim-v1.schema.json",
        "source-adapter-v1.schema.json",
        "source-coverage-v1.schema.json",
        "standing-authority-v1.schema.json",
        "transform-recipe-v1.schema.json",
        "universe-enumerator-registry-v1.schema.json",
        "universe-source-registry-v1.schema.json",
    }
    assert {path.name for path in schemas.glob("*.json")} == expected
    assert all(json.loads(path.read_text())["$schema"].endswith("2020-12/schema") for path in schemas.glob("*.json"))
