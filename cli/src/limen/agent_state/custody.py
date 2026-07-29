"""Path-free Prima Materia projections for verified agent-state custody."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from dataclasses import replace as dataclass_replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import rfc8785

from limen.host_admission import hold_lease
from limen.prima_materia import CustodyReceiptV1, RestorationProofV1

from .crypto import (
    encryption_profile_digest,
    keychain_key,
    verify_atom_packs,
    verify_encrypted_file,
)
from .models import MetabolismReceipt, ReceiptError, RestoreProof
from .pipeline import GitVault, require_mounted_external

GIT_TARGET_REF = "encrypted-git"
EXTERNAL_TARGET_REF = "encrypted-external"


def _digest(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _remote_refs(receipt: MetabolismReceipt) -> tuple[str, str]:
    if not receipt.git_remote or not receipt.git_commit or not receipt.git_receipt_commit:
        raise ReceiptError("verified custody is missing exact remote references")
    return (
        f"github:{receipt.git_remote}@{receipt.git_commit}",
        f"github:{receipt.git_remote}@{receipt.git_receipt_commit}",
    )


def _proof_output_digest(receipt: MetabolismReceipt, proof: RestoreProof) -> str | None:
    if proof.scope == "external-full" and receipt.source.kind == "opencode-sqlite":
        return proof.source_sha256
    return proof.logical_sha256


def _restoration(receipt: MetabolismReceipt, scope: str) -> tuple[RestoreProof, str]:
    matches = [proof for proof in receipt.restorations if proof.scope == scope and proof.passed]
    if len(matches) != 1:
        raise ReceiptError(f"verified custody requires one {scope} restoration")
    proof = matches[0]
    expected_digest = (
        receipt.source.sha256
        if scope == "external-full" and receipt.source.kind == "opencode-sqlite"
        else receipt.logical_sha256
    )
    if _proof_output_digest(receipt, proof) != expected_digest:
        raise ReceiptError(f"{scope} restoration does not match the logical manifest")
    if proof.device_id is None or proof.restored_at is None or proof.encryption_profile_digest is None:
        raise ReceiptError(f"{scope} restoration is missing independent device evidence")
    if proof.encryption_profile_digest != receipt.encryption_profile_digest:
        raise ReceiptError(f"{scope} restoration used a different encryption profile")
    if scope == "git-full-manifest" and proof.remote_refs != _remote_refs(receipt):
        raise ReceiptError("Git restoration is not bound to exact remote references")
    if scope == "external-full" and proof.remote_refs:
        raise ReceiptError("external restoration contains unexpected remote references")
    return proof, expected_digest


def _restored_at(value: str) -> datetime:
    try:
        restored_at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReceiptError("restoration evidence contains an invalid timestamp") from exc
    if restored_at.tzinfo is None or restored_at.utcoffset() is None:
        raise ReceiptError("restoration evidence timestamp must include a timezone")
    return restored_at


def project_custody_receipt(
    receipt: MetabolismReceipt,
) -> CustodyReceiptV1:
    """Project a verified metabolism receipt into the portable custody contract."""

    receipt.require_retirement_gate()
    if receipt.encryption_profile_digest is None:
        raise ReceiptError("capture-time encryption profile is missing")
    primary, primary_digest = _restoration(receipt, "git-full-manifest")
    external, external_digest = _restoration(receipt, "external-full")
    primary_device_id = primary.device_id
    external_device_id = external.device_id
    if primary_device_id is None or external_device_id is None:
        raise ReceiptError("restoration evidence is incomplete")

    chunk_manifest_digests = (
        *(_digest([asdict(chunk) for chunk in pack.chunks]) for pack in receipt.packs),
        _digest([asdict(chunk) for chunk in receipt.external_chunks]),
    )
    custody_id = (
        "custody_"
        + _digest(
            {
                "run_id": receipt.run_id,
                "logical_sha256": primary_digest,
                "external_sha256": external_digest,
                "encryption_profile_digest": receipt.encryption_profile_digest,
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
        output_digest: str,
    ) -> RestorationProofV1:
        if source.device_id is None or source.restored_at is None:
            raise ReceiptError("restoration evidence is incomplete")
        return RestorationProofV1(
            custody_target_ref=target_ref,
            device_id=source.device_id,
            restored_at=_restored_at(source.restored_at),
            restored_output_digest=output_digest,
            predicate_digest=_digest(asdict(source)),
        )

    return CustodyReceiptV1(
        custody_id=custody_id,
        encryption_profile_digest=receipt.encryption_profile_digest,
        chunk_manifest_digests=chunk_manifest_digests,
        independent_device_ids=(primary_device_id, external_device_id),
        remote_refs=_remote_refs(receipt),
        restoration_proofs=(
            proof(
                primary,
                target_ref=GIT_TARGET_REF,
                output_digest=primary_digest,
            ),
            proof(
                external,
                target_ref=EXTERNAL_TARGET_REF,
                output_digest=external_digest,
            ),
        ),
    )


def _device_identity(path: Path) -> str:
    try:
        device = path.stat().st_dev
    except OSError as exc:
        raise ReceiptError("custody restoration target is unavailable") from exc
    material = f"limen-custody-device-v1:{device}".encode()
    return "device_" + hashlib.sha256(material).hexdigest()[:32]


def _target_is_within_source(source_root: Path, target: Path) -> bool:
    source = source_root.expanduser().resolve(strict=False)
    resolved = target.expanduser().resolve(strict=False)
    try:
        resolved.relative_to(source)
        return True
    except ValueError:
        pass
    for ancestor in (resolved, *resolved.parents):
        if not ancestor.exists():
            continue
        try:
            if os.path.samefile(ancestor, source):
                return True
        except OSError:
            continue
    return False


def _capture_receipt_shape(receipt: MetabolismReceipt) -> dict[str, Any]:
    value = json.loads(json.dumps(receipt.as_dict(), sort_keys=True))
    value["git_receipt_commit"] = None
    value["source_retired"] = False
    value["retirement_proof"] = None
    for proof in value["restorations"]:
        for key in (
            "device_id",
            "restored_at",
            "encryption_profile_digest",
            "remote_refs",
        ):
            proof.pop(key, None)
    return value


def _require_remote_receipt(
    receipt: MetabolismReceipt,
    vault: GitVault,
    relative: Path,
    receipt_message: str,
) -> tuple[str, str]:
    vault.verify_identity()
    vault.require_exact_remote_head()
    payload_commit, receipt_commit, receipt_text = vault.completed_receipt_at_remote(
        relative,
        receipt_message,
    )
    if (payload_commit, receipt_commit) != (
        receipt.git_commit,
        receipt.git_receipt_commit,
    ):
        raise ReceiptError("private custody receipt is not exact on the remote")
    try:
        remote_value = json.loads(receipt_text)
    except json.JSONDecodeError as exc:
        raise ReceiptError("remote custody receipt is invalid") from exc
    if remote_value != _capture_receipt_shape(receipt):
        raise ReceiptError("remote custody receipt does not match private capture evidence")
    return payload_commit, receipt_commit


def _evidence_proof(
    receipt: MetabolismReceipt,
    proof: RestoreProof,
    *,
    device_id: str,
    restored_at: str,
    profile_digest: str,
    remote_refs: tuple[str, ...] = (),
) -> RestoreProof:
    output_digest = _proof_output_digest(receipt, proof)
    for existing in receipt.restorations:
        if (
            existing.scope == proof.scope
            and existing.passed
            and existing.device_id == device_id
            and existing.restored_at is not None
            and existing.encryption_profile_digest == profile_digest
            and existing.remote_refs == remote_refs
            and _proof_output_digest(receipt, existing) == output_digest
        ):
            restored_at = existing.restored_at
            break
    return dataclass_replace(
        proof,
        device_id=device_id,
        restored_at=restored_at,
        encryption_profile_digest=profile_digest,
        remote_refs=remote_refs,
    )


def verify_custody_restorations(
    receipt: MetabolismReceipt,
    *,
    name: str,
    vault_root: Path,
    external_root: Path,
    repository: str = "organvm/arca",
    key_service: str = "limen-arca-vault",
    require_external_mount: bool = True,
    restored_at: datetime | None = None,
) -> MetabolismReceipt:
    """Re-run both full restores and bind their real devices to remote evidence."""

    if not name or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in name):
        raise ValueError("custody name must be lowercase alphanumeric with hyphens")
    receipt.require_retirement_gate()
    if receipt.git_remote != repository:
        raise ReceiptError("private custody receipt names a different remote")
    profile_digest = receipt.encryption_profile_digest
    if profile_digest is None:
        raise ReceiptError("capture-time encryption profile is missing")
    if profile_digest != encryption_profile_digest():
        raise ReceiptError("capture-time encryption profile is unavailable to this restorer")

    relative = Path("agent-state") / name / receipt.run_id
    vault = GitVault(vault_root, repository=repository)
    receipt_message = (
        f"agent-state: receipt OpenCode {receipt.run_id}"
        if receipt.source.kind == "opencode-sqlite"
        else f"agent-state: receipt {name} {receipt.run_id}"
    )
    payload_commit, receipt_commit = _require_remote_receipt(
        receipt,
        vault,
        relative,
        receipt_message,
    )
    git_payload_root = vault.root / relative
    external_base = (
        require_mounted_external(external_root)
        if require_external_mount
        else external_root.expanduser().resolve(strict=False)
    )
    external_payload_root = external_base / name / receipt.run_id
    if not git_payload_root.is_dir() or not external_payload_root.is_dir():
        raise ReceiptError("both complete custody targets must be locally available")

    key = keychain_key(key_service)
    git_proof = verify_atom_packs(
        receipt.packs,
        git_payload_root,
        key,
        logical_sha256=receipt.logical_sha256,
    )
    if receipt.source.kind == "file-tree":
        expected_external = [chunk for pack in receipt.packs for chunk in pack.chunks]
        if receipt.external_chunks != expected_external:
            raise ReceiptError("external chunk manifest does not match the captured packs")
        external_proof = dataclass_replace(
            verify_atom_packs(
                receipt.packs,
                external_payload_root,
                key,
                logical_sha256=receipt.logical_sha256,
            ),
            scope="external-full",
        )
    elif receipt.source.kind == "opencode-sqlite":
        external_proof = verify_encrypted_file(
            receipt.external_chunks,
            external_payload_root,
            key,
            source_sha256=receipt.source.sha256,
        )
    else:
        raise ReceiptError("custody projection does not support this source kind")
    if not git_proof.passed or not external_proof.passed:
        raise ReceiptError("independent full restoration failed")

    git_device = _device_identity(git_payload_root)
    external_device = _device_identity(external_payload_root)
    if git_device == external_device:
        raise ReceiptError("custody restorations must use physically independent devices")
    recorded_at = (restored_at or datetime.now(UTC)).isoformat()
    refs = (
        f"github:{repository}@{payload_commit}",
        f"github:{repository}@{receipt_commit}",
    )
    verified = MetabolismReceipt.from_dict(receipt.as_dict())
    sample = next(
        (proof for proof in receipt.restorations if proof.scope == "git-sample" and proof.passed),
        None,
    )
    if sample is None:
        raise ReceiptError("Git sample restoration evidence is missing")
    verified.restorations = [
        sample,
        _evidence_proof(
            receipt,
            git_proof,
            device_id=git_device,
            restored_at=recorded_at,
            profile_digest=profile_digest,
            remote_refs=refs,
        ),
        _evidence_proof(
            receipt,
            external_proof,
            device_id=external_device,
            restored_at=recorded_at,
            profile_digest=profile_digest,
        ),
    ]
    return verified


def _create_private_parents(parent: Path) -> None:
    missing: list[Path] = []
    current = parent
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_synced_temp(path: Path, encoded: bytes) -> Path:
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=path.parent,
    )
    temporary = Path(raw_temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _validate_existing_custody(path: Path, receipt: CustodyReceiptV1) -> bool:
    try:
        existing = CustodyReceiptV1.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ReceiptError("canonical custody receipt is invalid") from exc
    if existing != receipt:
        raise ReceiptError("canonical custody receipt conflicts with verified custody")
    try:
        path.chmod(0o600)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise ReceiptError("cannot persist canonical custody receipt") from exc
    return False


def write_custody_receipt(path: Path, receipt: CustodyReceiptV1) -> bool:
    """Write once with private permissions; exact repeats are a no-op."""

    encoded = (json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.exists():
        return _validate_existing_custody(path, receipt)

    _create_private_parents(path.parent)
    temporary: Path | None = None
    try:
        temporary = _write_synced_temp(path, encoded)
        try:
            os.link(temporary, path)
        except FileExistsError:
            return _validate_existing_custody(path, receipt)
        path.chmod(0o600)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise ReceiptError("cannot persist canonical custody receipt") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def _write_verified_metabolism_receipt(
    path: Path,
    receipt: MetabolismReceipt,
) -> bool:
    if path.is_symlink():
        raise ReceiptError("private metabolism receipt cannot be a symlink")
    if path.exists():
        existing = MetabolismReceipt.read(path)
        if existing.as_dict() == receipt.as_dict():
            path.chmod(0o600)
            _fsync_directory(path.parent)
            return False
    _create_private_parents(path.parent)
    encoded = (json.dumps(receipt.as_dict(), indent=2, sort_keys=True) + "\n").encode()
    temporary: Path | None = None
    try:
        temporary = _write_synced_temp(path, encoded)
        os.replace(temporary, path)
        temporary = None
        path.chmod(0o600)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise ReceiptError("cannot persist verified metabolism receipt") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def run_custody_verification_campaign(
    name: str,
    metabolism_receipt: Path,
    vault_root: Path,
    external_root: Path,
    output: Path,
    *,
    repository: str = "organvm/arca",
    key_service: str = "limen-arca-vault",
    require_external_mount: bool = True,
) -> tuple[MetabolismReceipt, CustodyReceiptV1, bool, bool]:
    """Verify both copies under the heavy lease, then publish private and path-free receipts."""

    receipt = MetabolismReceipt.read(metabolism_receipt)
    if _target_is_within_source(Path(receipt.source.path), output):
        raise ReceiptError("canonical custody output must remain outside the source tree")
    owner = f"agent-state-custody-proof-{os.getpid()}"
    with hold_lease("heavy", owner=owner, surface=f"{name}-custody-proof"):
        verified = verify_custody_restorations(
            receipt,
            name=name,
            vault_root=vault_root,
            external_root=external_root,
            repository=repository,
            key_service=key_service,
            require_external_mount=require_external_mount,
        )
        projected = project_custody_receipt(verified)
        metabolism_changed = _write_verified_metabolism_receipt(
            metabolism_receipt,
            verified,
        )
        custody_changed = write_custody_receipt(output, projected)
    return verified, projected, metabolism_changed, custody_changed
