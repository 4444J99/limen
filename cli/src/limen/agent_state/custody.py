"""Path-free Prima Materia projections for verified agent-state custody."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import subprocess
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


def _diskutil_info(target: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["/usr/sbin/diskutil", "info", "-plist", target],
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReceiptError("custody physical-device probe failed") from exc
    if result.returncode:
        raise ReceiptError("custody physical-device probe failed")
    try:
        payload = plistlib.loads(result.stdout)
    except plistlib.InvalidFileException as exc:
        raise ReceiptError("custody physical-device evidence is invalid") from exc
    if not isinstance(payload, dict):
        raise ReceiptError("custody physical-device evidence is invalid")
    return payload


def _volume_mount(path: Path) -> Path:
    """Return the mounted volume that contains one restoration target."""

    try:
        candidate = path.resolve(strict=True)
    except OSError as exc:
        raise ReceiptError("custody restoration target is unavailable") from exc
    while not os.path.ismount(candidate):
        parent = candidate.parent
        if parent == candidate:
            raise ReceiptError("custody restoration volume is unavailable")
        candidate = parent
    return candidate


def _ioreg_string(value: str) -> str | None:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, str):
        return None
    decoded = decoded.strip()
    return decoded or None


def _usb_hardware_serial(physical: str) -> str | None:
    """Return the USB-device serial whose storage subtree owns a whole disk."""

    try:
        result = subprocess.run(
            [
                "/usr/sbin/ioreg",
                "-r",
                "-l",
                "-w",
                "0",
                "-c",
                "IOUSBHostDevice",
            ],
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReceiptError("custody physical-device probe failed") from exc
    if result.returncode:
        raise ReceiptError("custody physical-device probe failed")
    try:
        output = result.stdout.decode("utf-8") if isinstance(result.stdout, bytes) else str(result.stdout)
    except UnicodeError as exc:
        raise ReceiptError("custody physical-device evidence is invalid") from exc

    entry_pattern = re.compile(r"^(.*?)\+-o\s+.+?\s+<class\s+([^,>]+)")
    property_pattern = re.compile(r'^.*?"([^"]+)"\s*=\s*(.*)$')
    stack: list[dict[str, Any]] = []
    candidates: set[str] = set()
    for line in output.splitlines():
        entry_match = entry_pattern.match(line)
        if entry_match:
            position = line.index("+-o")
            while stack and int(stack[-1]["position"]) >= position:
                stack.pop()
            stack.append(
                {
                    "position": position,
                    "class": entry_match.group(2),
                    "properties": {},
                }
            )
            continue
        if not stack:
            continue
        property_match = property_pattern.match(line)
        if not property_match:
            continue
        key, raw_value = property_match.groups()
        properties = stack[-1]["properties"]
        if not isinstance(properties, dict):
            raise ReceiptError("custody physical-device evidence is invalid")
        properties[key] = raw_value.strip()
        if key != "BSD Name" or _ioreg_string(raw_value) != physical:
            continue
        usb_device = next(
            (node for node in reversed(stack) if node["class"] == "IOUSBHostDevice"),
            None,
        )
        if usb_device is None:
            continue
        usb_properties = usb_device["properties"]
        if not isinstance(usb_properties, dict):
            raise ReceiptError("custody physical-device evidence is invalid")
        serial = next(
            (
                value
                for serial_key in ("USB Serial Number", "kUSBSerialNumberString")
                if (value := _ioreg_string(str(usb_properties.get(serial_key, "")))) is not None
            ),
            None,
        )
        if serial is not None:
            candidates.add(serial)
    if len(candidates) > 1:
        raise ReceiptError("custody physical-device evidence is ambiguous")
    return next(iter(candidates), None)


def _device_identity(path: Path) -> str:
    payload = _diskutil_info(str(_volume_mount(path)))
    try:
        stores = payload.get("APFSPhysicalStores")
        if isinstance(stores, list) and len(stores) == 1 and isinstance(stores[0], dict):
            store = str(stores[0]["APFSPhysicalStore"])
            match = re.fullmatch(r"(disk[0-9]+)s[0-9]+", store)
            physical = match.group(1) if match else store
        else:
            physical = str(payload["ParentWholeDisk"])
    except (KeyError, TypeError) as exc:
        raise ReceiptError("custody physical-device evidence is invalid") from exc
    if not re.fullmatch(r"disk[0-9]+", physical):
        raise ReceiptError("custody physical-device evidence is invalid")
    physical_info = _diskutil_info(f"/dev/{physical}")
    if (
        physical_info.get("DeviceIdentifier") != physical
        or physical_info.get("ParentWholeDisk") != physical
        or physical_info.get("WholeDisk") is not True
        or physical_info.get("VirtualOrPhysical") == "Virtual"
        or physical_info.get("BusProtocol") == "Disk Image"
        or physical_info.get("MediaType") == "Disk Image"
        or physical_info.get("SystemImage") is True
    ):
        raise ReceiptError("custody target is not backed by a physical whole disk")
    stable_media_id = next(
        (value for key in ("MediaUUID", "DiskUUID") if isinstance((value := physical_info.get(key)), str) and value),
        None,
    )
    if stable_media_id is None:
        device_tree_path = physical_info.get("DeviceTreePath")
        if (
            physical_info.get("Internal") is True
            and physical_info.get("BusProtocol") == "Apple Fabric"
            and isinstance(device_tree_path, str)
            and device_tree_path
        ):
            # Apple Fabric storage is integrated with the machine rather than detachable
            # media. Its device-tree path is stable across BSD disk re-enumeration.
            stable_media_id = f"apple-integrated:{device_tree_path}"
        elif physical_info.get("BusProtocol") == "USB":
            usb_serial = _usb_hardware_serial(physical)
            if usb_serial is not None:
                stable_media_id = f"usb-device:{usb_serial}"
    if stable_media_id is None:
        raise ReceiptError("custody physical device lacks a stable media identity")
    material = f"limen-custody-physical-device-v4:{stable_media_id}".encode()
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
    expected_profile_digest: str,
) -> tuple[str, str]:
    vault.verify_identity()
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
    expected = _capture_receipt_shape(receipt)
    legacy_expected = dict(expected)
    recorded_profile = legacy_expected.pop("encryption_profile_digest", None)
    legacy_profile_match = (
        recorded_profile == expected_profile_digest
        and "encryption_profile_digest" not in remote_value
        and remote_value == legacy_expected
    )
    if remote_value != expected and not legacy_profile_match:
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
    try:
        expected_profile = encryption_profile_digest(receipt.source.kind)
    except ValueError as exc:
        raise ReceiptError("custody projection does not support this source kind") from exc
    profile_digest = receipt.encryption_profile_digest or expected_profile
    if profile_digest != expected_profile:
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
        profile_digest,
    )
    external_base = (
        require_mounted_external(external_root)
        if require_external_mount
        else external_root.expanduser().resolve(strict=False)
    )
    external_payload_root = external_base / name / receipt.run_id
    if not vault.root.is_dir() or not external_payload_root.is_dir():
        raise ReceiptError("both complete custody targets must be locally available")

    key = keychain_key(key_service)
    git_chunks = [Path(chunk.path) for pack in receipt.packs for chunk in pack.chunks]
    with tempfile.TemporaryDirectory(
        prefix=".limen-arca-restore-",
        dir=vault.root.parent,
    ) as temporary:
        git_payload_root = vault.materialize_remote_payload(
            relative,
            payload_commit,
            git_chunks,
            Path(temporary) / "payload",
        )
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

    git_device = _device_identity(vault.root)
    external_device = _device_identity(external_payload_root)
    if git_device == external_device:
        raise ReceiptError("custody restorations must use physically independent devices")
    recorded_at = (restored_at or datetime.now(UTC)).isoformat()
    refs = (
        f"github:{repository}@{payload_commit}",
        f"github:{repository}@{receipt_commit}",
    )
    verified = MetabolismReceipt.from_dict(receipt.as_dict())
    verified.encryption_profile_digest = profile_digest
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


def _validate_existing_custody(
    path: Path,
    receipt: CustodyReceiptV1,
    *,
    persist_permissions: bool = True,
) -> bool:
    if path.is_symlink():
        raise ReceiptError("canonical custody receipt cannot be a symlink")
    try:
        existing = CustodyReceiptV1.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ReceiptError("canonical custody receipt is invalid") from exc
    if existing != receipt:
        raise ReceiptError("canonical custody receipt conflicts with verified custody")
    if not persist_permissions:
        return False
    try:
        path.chmod(0o600)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise ReceiptError("cannot persist canonical custody receipt") from exc
    return False


def write_custody_receipt(path: Path, receipt: CustodyReceiptV1) -> bool:
    """Write once with private permissions; exact repeats are a no-op."""

    encoded = (json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path.is_symlink():
        raise ReceiptError("canonical custody receipt cannot be a symlink")
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


def _metabolism_write_required(
    path: Path,
    receipt: MetabolismReceipt,
) -> bool:
    if path.is_symlink():
        raise ReceiptError("private metabolism receipt cannot be a symlink")
    if path.exists():
        existing = MetabolismReceipt.read(path)
        if existing.as_dict() == receipt.as_dict():
            return False
    return True


def _rollback_campaign_publication(
    *,
    metabolism_receipt: Path,
    metabolism_backup: Path | None,
    metabolism_replaced: bool,
    output: Path,
    custody_temporary: Path | None,
    custody_created: bool,
) -> None:
    failures: list[OSError] = []
    if metabolism_replaced and metabolism_backup is not None:
        try:
            os.replace(metabolism_backup, metabolism_receipt)
            _fsync_directory(metabolism_receipt.parent)
        except OSError as exc:
            failures.append(exc)
    if custody_created and custody_temporary is not None:
        try:
            if output.exists() and os.path.samefile(output, custody_temporary):
                output.unlink()
                _fsync_directory(output.parent)
        except OSError as exc:
            failures.append(exc)
    if failures:
        raise ReceiptError("custody receipt publication rollback was incomplete") from failures[0]


def _publish_campaign_receipts(
    *,
    metabolism_receipt: Path,
    verified: MetabolismReceipt,
    output: Path,
    projected: CustodyReceiptV1,
) -> tuple[bool, bool]:
    """Stage both receipts, persist owner evidence, then expose its projection."""

    if output.is_symlink():
        raise ReceiptError("canonical custody receipt cannot be a symlink")
    custody_changed = not output.exists()
    if not custody_changed:
        _validate_existing_custody(
            output,
            projected,
            persist_permissions=True,
        )
    metabolism_changed = _metabolism_write_required(metabolism_receipt, verified)
    _create_private_parents(output.parent)
    _create_private_parents(metabolism_receipt.parent)
    custody_encoded = (json.dumps(projected.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode("utf-8")
    metabolism_encoded = (json.dumps(verified.as_dict(), indent=2, sort_keys=True) + "\n").encode()
    custody_temporary: Path | None = None
    metabolism_temporary: Path | None = None
    metabolism_backup: Path | None = None
    custody_created = False
    metabolism_replaced = False
    try:
        if custody_changed:
            custody_temporary = _write_synced_temp(output, custody_encoded)
        if metabolism_changed:
            metabolism_temporary = _write_synced_temp(
                metabolism_receipt,
                metabolism_encoded,
            )
            metabolism_backup = _write_synced_temp(
                metabolism_receipt,
                metabolism_receipt.read_bytes(),
            )

        if metabolism_temporary is not None:
            os.replace(metabolism_temporary, metabolism_receipt)
            metabolism_temporary = None
            metabolism_replaced = True
            _fsync_directory(metabolism_receipt.parent)

        if custody_temporary is not None:
            try:
                os.link(custody_temporary, output)
                custody_created = True
            except FileExistsError:
                _validate_existing_custody(
                    output,
                    projected,
                    persist_permissions=False,
                )
                custody_changed = False
            if custody_created:
                _fsync_directory(output.parent)
    except (OSError, ReceiptError) as exc:
        try:
            _rollback_campaign_publication(
                metabolism_receipt=metabolism_receipt,
                metabolism_backup=metabolism_backup,
                metabolism_replaced=metabolism_replaced,
                output=output,
                custody_temporary=custody_temporary,
                custody_created=custody_created,
            )
        except ReceiptError as rollback_error:
            raise rollback_error from exc
        if isinstance(exc, ReceiptError):
            raise
        raise ReceiptError("cannot atomically persist verified custody receipts") from exc
    finally:
        for temporary in (
            custody_temporary,
            metabolism_temporary,
            metabolism_backup,
        ):
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return metabolism_changed, custody_changed


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

    if output.expanduser().resolve(strict=False) == metabolism_receipt.expanduser().resolve(strict=False):
        raise ReceiptError("canonical and private custody receipts require distinct paths")
    receipt = MetabolismReceipt.read(metabolism_receipt)
    source_root = Path(receipt.source.path)
    git_payload_root = vault_root / "agent-state" / name / receipt.run_id
    external_payload_root = external_root / name / receipt.run_id
    if _target_is_within_source(source_root, metabolism_receipt):
        raise ReceiptError("private metabolism receipt must remain outside the source tree")
    if _target_is_within_source(source_root, output):
        raise ReceiptError("canonical custody output must remain outside the source tree")
    if _target_is_within_source(source_root, git_payload_root):
        raise ReceiptError("Git custody payload must remain outside the source tree")
    if _target_is_within_source(source_root, external_payload_root):
        raise ReceiptError("external custody payload must remain outside the source tree")
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
        metabolism_changed, custody_changed = _publish_campaign_receipts(
            metabolism_receipt=metabolism_receipt,
            verified=verified,
            output=output,
            projected=projected,
        )
    return verified, projected, metabolism_changed, custody_changed
