from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from limen.prima_materia import (
    CompositionManifestV1,
    CustodyReceiptV1,
    EncryptedPayloadRefV1,
    PrimaMateriaEventV1,
    PrivacyConsentPolicyV1,
    ResourceClaimV1,
    RestorationProofV1,
    SourceAdapterV1,
    SourceCoverageV1,
    StandingAuthorityV1,
    TransformRecipeV1,
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
        "composition-manifest-v1.schema.json",
        "custody-receipt-v1.schema.json",
        "frozen-wave-manifest-v1.schema.json",
        "prima-materia-event-v1.schema.json",
        "resource-claim-v1.schema.json",
        "source-adapter-v1.schema.json",
        "source-coverage-v1.schema.json",
        "standing-authority-v1.schema.json",
        "transform-recipe-v1.schema.json",
    }
    assert {path.name for path in schemas.glob("*.json")} == expected
    assert all(json.loads(path.read_text())["$schema"].endswith("2020-12/schema") for path in schemas.glob("*.json"))
