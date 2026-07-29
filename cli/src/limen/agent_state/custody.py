"""Path-free Prima Materia projections for verified agent-state custody."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import rfc8785

from limen.prima_materia import CustodyReceiptV1, RestorationProofV1

from .crypto import encryption_profile_digest
from .models import MetabolismReceipt, ReceiptError, RestoreProof


def _digest(value: object) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _restoration(receipt: MetabolismReceipt, scope: str) -> RestoreProof:
    matches = [proof for proof in receipt.restorations if proof.scope == scope and proof.passed]
    if len(matches) != 1:
        raise ReceiptError(f"verified custody requires one {scope} restoration")
    proof = matches[0]
    if proof.logical_sha256 != receipt.logical_sha256:
        raise ReceiptError(f"{scope} restoration does not match the logical manifest")
    return proof


def project_custody_receipt(
    receipt: MetabolismReceipt,
    *,
    primary_device_id: str,
    external_device_id: str,
    restored_at: datetime,
    primary_target_ref: str = "encrypted-git",
    external_target_ref: str = "encrypted-external",
) -> CustodyReceiptV1:
    """Project a verified metabolism receipt into the portable custody contract."""

    receipt.require_retirement_gate()
    primary = _restoration(receipt, "git-full-manifest")
    external = _restoration(receipt, "external-full")
    if not receipt.git_remote or not receipt.git_commit or not receipt.git_receipt_commit:
        raise ReceiptError("verified custody is missing exact remote references")

    chunk_manifest_digests = tuple(_digest([asdict(chunk) for chunk in pack.chunks]) for pack in receipt.packs)
    custody_id = (
        "custody_"
        + _digest(
            {
                "run_id": receipt.run_id,
                "logical_sha256": receipt.logical_sha256,
                "chunk_manifest_digests": list(chunk_manifest_digests),
                "git_remote": receipt.git_remote,
                "git_commit": receipt.git_commit,
                "git_receipt_commit": receipt.git_receipt_commit,
            }
        )[:32]
    )

    def proof(
        source: RestoreProof,
        *,
        target_ref: str,
        device_id: str,
    ) -> RestorationProofV1:
        return RestorationProofV1(
            custody_target_ref=target_ref,
            device_id=device_id,
            restored_at=restored_at,
            restored_output_digest=receipt.logical_sha256,
            predicate_digest=_digest(asdict(source)),
        )

    return CustodyReceiptV1(
        custody_id=custody_id,
        encryption_profile_digest=encryption_profile_digest(),
        chunk_manifest_digests=chunk_manifest_digests,
        independent_device_ids=(primary_device_id, external_device_id),
        remote_refs=(
            f"github:{receipt.git_remote}@{receipt.git_commit}",
            f"github:{receipt.git_remote}@{receipt.git_receipt_commit}",
        ),
        restoration_proofs=(
            proof(
                primary,
                target_ref=primary_target_ref,
                device_id=primary_device_id,
            ),
            proof(
                external,
                target_ref=external_target_ref,
                device_id=external_device_id,
            ),
        ),
    )


def _create_private_parents(parent: Path) -> None:
    missing: list[Path] = []
    current = parent
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)


def write_custody_receipt(path: Path, receipt: CustodyReceiptV1) -> bool:
    """Write once with private permissions; exact repeats are a no-op."""

    encoded = (json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.exists():
        try:
            existing = CustodyReceiptV1.model_validate_json(path.read_bytes())
        except (OSError, ValueError) as exc:
            raise ReceiptError("canonical custody receipt is invalid") from exc
        if existing != receipt:
            raise ReceiptError("canonical custody receipt conflicts with verified custody")
        path.chmod(0o600)
        return False

    _create_private_parents(path.parent)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        return write_custody_receipt(path, receipt)
    except OSError as exc:
        raise ReceiptError("cannot create canonical custody receipt") from exc
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return True
