from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from limen.agent_state.crypto import encryption_profile_digest
from limen.agent_state.custody import (
    project_custody_receipt,
    write_custody_receipt,
)
from limen.agent_state.models import (
    AtomPack,
    CipherChunk,
    MetabolismReceipt,
    ReceiptError,
    RestoreProof,
    SourceProof,
)

LOGICAL_SHA256 = "d" * 64
PRIMARY_DEVICE = "githubRemoteDevice0001"
EXTERNAL_DEVICE = "t7RecoveryDevice0001"
RESTORED_AT = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)


def metabolism_receipt() -> MetabolismReceipt:
    chunk = CipherChunk(
        path="atoms-00000.jsonl.gz.enc.part-00000",
        bytes=128,
        sha256="c" * 64,
    )
    return MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="20260729T125700Z",
        source=SourceProof(
            path="/private/source/agent-state",
            kind="file-tree",
            bytes=64,
            sha256="a" * 64,
            stat_before=(1, 2, 3),
            stat_after=(1, 2, 3),
            inventory_before_sha256="b" * 64,
            inventory_after_sha256="b" * 64,
        ),
        atom_count=2,
        logical_sha256=LOGICAL_SHA256,
        packs=[
            AtomPack(
                ordinal=0,
                atom_count=2,
                plaintext_bytes=64,
                plaintext_sha256="e" * 64,
                chunks=(chunk,),
            )
        ],
        git_remote="organvm/arca",
        git_commit="1" * 40,
        git_receipt_commit="2" * 40,
        external_chunks=[chunk],
        restorations=[
            RestoreProof(
                scope="git-sample",
                passed=True,
                atoms_verified=2,
            ),
            RestoreProof(
                scope="git-full-manifest",
                passed=True,
                atoms_verified=2,
                logical_sha256=LOGICAL_SHA256,
            ),
            RestoreProof(
                scope="external-full",
                passed=True,
                atoms_verified=2,
                logical_sha256=LOGICAL_SHA256,
            ),
        ],
        retained_hot_bytes=0,
    )


def projected_receipt():
    return project_custody_receipt(
        metabolism_receipt(),
        primary_device_id=PRIMARY_DEVICE,
        external_device_id=EXTERNAL_DEVICE,
        restored_at=RESTORED_AT,
    )


def test_projection_is_path_free_and_binds_both_restorations() -> None:
    source = metabolism_receipt()
    projected = project_custody_receipt(
        source,
        primary_device_id=PRIMARY_DEVICE,
        external_device_id=EXTERNAL_DEVICE,
        restored_at=RESTORED_AT,
    )
    payload = json.dumps(projected.model_dump(mode="json"), sort_keys=True)

    assert source.source.path not in payload
    assert projected.schema_version == "limen.custody_receipt.v1"
    assert projected.encryption_profile_digest == encryption_profile_digest()
    assert len(projected.chunk_manifest_digests) == len(source.packs)
    assert projected.independent_device_ids == (
        PRIMARY_DEVICE,
        EXTERNAL_DEVICE,
    )
    assert projected.remote_refs == (
        "github:organvm/arca@" + "1" * 40,
        "github:organvm/arca@" + "2" * 40,
    )
    assert {proof.custody_target_ref for proof in projected.restoration_proofs} == {
        "encrypted-git",
        "encrypted-external",
    }
    assert {proof.restored_output_digest for proof in projected.restoration_proofs} == {LOGICAL_SHA256}


def test_projection_rejects_non_independent_devices() -> None:
    with pytest.raises(
        ValueError,
        match="custody device identities must be independent",
    ):
        project_custody_receipt(
            metabolism_receipt(),
            primary_device_id=PRIMARY_DEVICE,
            external_device_id=PRIMARY_DEVICE,
            restored_at=RESTORED_AT,
        )


def test_projection_rejects_restore_digest_mismatch() -> None:
    receipt = metabolism_receipt()
    receipt.restorations[-1] = RestoreProof(
        scope="external-full",
        passed=True,
        atoms_verified=2,
        logical_sha256="f" * 64,
    )

    with pytest.raises(
        ReceiptError,
        match="external-full restoration does not match",
    ):
        project_custody_receipt(
            receipt,
            primary_device_id=PRIMARY_DEVICE,
            external_device_id=EXTERNAL_DEVICE,
            restored_at=RESTORED_AT,
        )


def test_private_projection_write_is_idempotent_and_mode_600(
    tmp_path: Path,
) -> None:
    output = tmp_path / "private" / "custody.json"
    projected = projected_receipt()

    assert write_custody_receipt(output, projected) is True
    original = output.read_bytes()
    original_mtime = output.stat().st_mtime_ns
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.parent.stat().st_mode & 0o777 == 0o700

    assert write_custody_receipt(output, projected) is False
    assert output.read_bytes() == original
    assert output.stat().st_mtime_ns == original_mtime


def test_private_projection_rejects_conflicting_existing_receipt(
    tmp_path: Path,
) -> None:
    output = tmp_path / "private" / "custody.json"
    assert write_custody_receipt(output, projected_receipt()) is True
    conflicting = project_custody_receipt(
        metabolism_receipt(),
        primary_device_id=PRIMARY_DEVICE,
        external_device_id="otherRecoveryDevice01",
        restored_at=RESTORED_AT,
    )

    with pytest.raises(ReceiptError, match="conflicts with verified custody"):
        write_custody_receipt(output, conflicting)


def test_encryption_profile_digest_is_lowercase_sha256() -> None:
    digest = encryption_profile_digest()

    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
