"""Dual encrypted custody and bounded retirement for session file trees."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.host_admission import hold_lease

from .crypto import (
    EncryptedAtomPacker,
    encryption_profile_digest,
    keychain_key,
    verify_atom_packs,
)
from .file_provider import (
    CapturedFile,
    FileProviderResult,
    RestoredFileResult,
    collect_file_entry,
    process_file_provider_items,
    progress_path_for,
    reconstruct_captured_files,
    restore_captured_file,
    retention_plan_from_capture,
)
from .models import AtomPack, CipherChunk, MetabolismReceipt, ReceiptError, RestoreProof, SourceProof
from .pipeline import (
    ARCA_REMOTE_EXACT_ERROR,
    RETIREMENT_AUTHORIZATION_REQUIRED,
    GitVault,
    PipelineError,
    require_mounted_external,
    run_id_now,
)
from .tree import (
    RetentionPlan,
    atomize_file_tree,
    require_plan_matches_source,
)


def _copy_packs(packs: list[AtomPack], source: Path, destination: Path) -> list[AtomPack]:
    copied: list[AtomPack] = []
    for pack in packs:
        chunks = []
        for chunk in pack.chunks:
            source_path = source / chunk.path
            destination_path = destination / chunk.path
            shutil.copyfile(source_path, destination_path)
            os.chmod(destination_path, 0o600)
            chunks.append(chunk)
        copied.append(replace(pack, chunks=tuple(chunks)))
    return copied


def _manifest_chunk(value: dict[str, object]) -> CipherChunk:
    relative = Path(str(value["path"]))
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != str(value["path"]):
        raise PipelineError("tree manifest contains an unsafe ciphertext path")
    return CipherChunk(
        path=relative.name,
        bytes=int(str(value["bytes"])),
        sha256=str(value["sha256"]),
    )


def _manifest_stat(value: object) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3:
        raise PipelineError("tree manifest contains an invalid source identity")
    return (int(value[0]), int(value[1]), int(value[2]))


def _require_custody_targets_outside_source(
    source_root: Path,
    targets: Mapping[str, Path],
) -> None:
    """Fail before writes when a custody target could capture itself."""

    source = source_root.expanduser().resolve(strict=False)
    nested: list[str] = []
    for label, target in targets.items():
        resolved = target.expanduser().resolve(strict=False)
        try:
            resolved.relative_to(source)
        except ValueError:
            for ancestor in (resolved, *resolved.parents):
                if not ancestor.exists():
                    continue
                try:
                    if os.path.samefile(ancestor, source):
                        nested.append(label)
                        break
                except OSError:
                    continue
        else:
            nested.append(label)
    if nested:
        raise PipelineError("custody targets must remain outside the source tree: " + ", ".join(nested))


def load_tree_manifest(payload_root: Path) -> MetabolismReceipt:
    """Load and validate the immutable portion of an interrupted tree capture."""

    try:
        manifest = json.loads((payload_root / "manifest.json").read_text(encoding="utf-8"))
        source_value = manifest["source"]
        source = SourceProof(
            path=str(source_value["path"]),
            kind=str(source_value["kind"]),
            bytes=int(source_value["bytes"]),
            sha256=str(source_value["sha256"]),
            stat_before=_manifest_stat(source_value["stat_before"]),
            stat_after=_manifest_stat(source_value["stat_after"]),
            inventory_before_sha256=source_value.get("inventory_before_sha256"),
            inventory_after_sha256=source_value.get("inventory_after_sha256"),
        )
        packs = [
            AtomPack(
                ordinal=int(value["ordinal"]),
                atom_count=int(value["atom_count"]),
                plaintext_bytes=int(value["plaintext_bytes"]),
                plaintext_sha256=str(value["plaintext_sha256"]),
                chunks=tuple(_manifest_chunk(chunk) for chunk in value["chunks"]),
            )
            for value in manifest["packs"]
        ]
        historical_restorations = [
            RestoreProof(
                scope=str(value["scope"]),
                passed=bool(value["passed"]),
                atoms_verified=int(value.get("atoms_verified", 0)),
                logical_sha256=value.get("logical_sha256"),
                source_sha256=value.get("source_sha256"),
                detail=str(value.get("detail", "")),
                device_id=value.get("device_id"),
                restored_at=value.get("restored_at"),
                encryption_profile_digest=value.get("encryption_profile_digest"),
                remote_refs=tuple(value.get("remote_refs", ())),
            )
            for value in manifest.get("restorations", [])
        ]
        logical_sha256 = manifest.get("logical_sha256")
        if not logical_sha256:
            logical_sha256 = next(
                (
                    proof.logical_sha256
                    for proof in historical_restorations
                    if proof.scope == "git-full-manifest" and proof.passed and proof.logical_sha256
                ),
                None,
            )
        receipt = MetabolismReceipt(
            schema=str(manifest["schema"]),
            run_id=str(manifest["run_id"]),
            source=source,
            atom_count=int(manifest["atom_count"]),
            logical_sha256=str(logical_sha256 or ""),
            encryption_profile_digest=manifest.get("encryption_profile_digest"),
            packs=packs,
            duplicate_payloads=int(manifest.get("duplicate_chunks", 0)),
            restorations=historical_restorations,
            retained_hot_bytes=int(manifest["retained_hot_bytes"]),
        )
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise PipelineError("tree capture manifest is missing or invalid") from exc
    if (
        receipt.schema != "limen.agent_state_metabolism.v1"
        or not receipt.source.stable
        or len(receipt.logical_sha256) != 64
        or [pack.ordinal for pack in packs] != list(range(len(packs)))
        or not packs
        or any(not pack.chunks for pack in packs)
        or sum(pack.atom_count for pack in packs) != receipt.atom_count
    ):
        raise PipelineError("tree capture manifest failed consistency checks")
    return receipt


def _require_private_retirement_receipt(
    receipt: MetabolismReceipt,
    private_receipt: Path,
) -> None:
    receipt.require_retirement_gate()
    try:
        durable = json.loads(private_receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError("private retirement receipt is missing or invalid") from exc
    expected = json.loads(json.dumps(receipt.as_dict(), sort_keys=True))
    if not isinstance(durable, dict) or set(durable) != set(expected):
        raise PipelineError("private retirement receipt does not match verified custody")
    for value in (durable, expected):
        value["source_retired"] = False
        value["retirement_proof"] = None
    if durable == expected:
        return

    try:
        enriched = MetabolismReceipt.from_dict(durable)
        from .custody import project_custody_receipt

        project_custody_receipt(enriched)
    except (ReceiptError, ValueError) as exc:
        raise PipelineError("private retirement receipt does not match verified custody") from exc
    for value in (durable, expected):
        for proof in value["restorations"]:
            for key in (
                "device_id",
                "restored_at",
                "encryption_profile_digest",
                "remote_refs",
            ):
                proof.pop(key, None)
    if durable != expected:
        raise PipelineError("private retirement receipt does not match verified custody")


def capture_cold_tree(
    name: str,
    plan: RetentionPlan,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    *,
    run_id: str | None = None,
    repository: str = "organvm/arca",
    key_service: str = "limen-arca-vault",
    require_external_mount: bool = True,
    pack_plaintext_limit: int = 32 * 1024 * 1024,
    chunk_limit: int = 90 * 1024 * 1024,
    record_consumer: Callable[[dict[str, Any]], None] | None = None,
) -> MetabolismReceipt:
    if not name or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in name):
        raise ValueError("tree custody name must be lowercase alphanumeric with hyphens")
    if not plan.cold_paths:
        raise PipelineError(f"no cold files selected for {name}")
    run_id = run_id or run_id_now()
    vault = GitVault(vault_root, repository=repository)
    relative = Path("agent-state") / name / run_id
    payload_root = vault.root / relative
    unresolved_external = external_root.expanduser().resolve(strict=False)
    exact_root = unresolved_external / name / run_id
    _require_custody_targets_outside_source(
        plan.root,
        {
            "vault-root": vault.root,
            "external-root": unresolved_external,
            "private-receipt": private_receipt,
            "encrypted-git-output": payload_root,
            "encrypted-external-output": exact_root,
        },
    )
    vault.verify()
    external_base = require_mounted_external(external_root) if require_external_mount else unresolved_external
    exact_root = external_base / name / run_id
    _require_custody_targets_outside_source(
        plan.root,
        {
            "external-root": external_base,
            "encrypted-external-output": exact_root,
        },
    )
    external_base.mkdir(parents=True, exist_ok=True)
    if payload_root.exists() or exact_root.exists():
        raise PipelineError(f"custody run already exists: {run_id}")
    payload_root.mkdir(parents=True, mode=0o700)
    exact_root.mkdir(parents=True, mode=0o700)
    key = keychain_key(key_service)
    packer = EncryptedAtomPacker(
        payload_root,
        key,
        pack_plaintext_limit=pack_plaintext_limit,
        chunk_limit=chunk_limit,
    )
    try:
        result = atomize_file_tree(plan, packer)
        packs = list(packer.close())
        if not result.source.stable:
            raise PipelineError(f"{name} file tree mutated during capture")
        sample = verify_atom_packs(packs, payload_root, key, logical_sha256=result.logical_sha256, sample=True)
        full = verify_atom_packs(
            packs,
            payload_root,
            key,
            logical_sha256=result.logical_sha256,
            record_consumer=record_consumer,
        )
        if not sample.passed or not full.passed:
            raise PipelineError(f"{name} encrypted Git restoration failed")
        external_packs = _copy_packs(packs, payload_root, exact_root)
        external = replace(
            verify_atom_packs(
                external_packs,
                exact_root,
                key,
                logical_sha256=result.logical_sha256,
            ),
            scope="external-full",
        )
        if not external.passed:
            raise PipelineError(f"{name} encrypted external restoration failed")
        external_chunks = [chunk for pack in external_packs for chunk in pack.chunks]
        receipt = MetabolismReceipt(
            schema="limen.agent_state_metabolism.v1",
            run_id=run_id,
            source=result.source,
            atom_count=result.atom_count,
            logical_sha256=result.logical_sha256,
            encryption_profile_digest=encryption_profile_digest("file-tree"),
            packs=packs,
            duplicate_payloads=result.duplicate_chunks,
            external_chunks=external_chunks,
            restorations=[sample, full, external],
            retained_hot_bytes=plan.hot_bytes,
        )
        manifest = {
            "schema": receipt.schema,
            "run_id": run_id,
            "source": asdict(receipt.source),
            "file_count": result.file_count,
            "atom_count": result.atom_count,
            "logical_sha256": result.logical_sha256,
            "encryption_profile_digest": receipt.encryption_profile_digest,
            "duplicate_chunks": result.duplicate_chunks,
            "cold_bytes": plan.cold_bytes,
            "retained_hot_bytes": plan.hot_bytes,
            "packs": [asdict(pack) for pack in packs],
            "restorations": [asdict(proof) for proof in receipt.restorations],
        }
        (payload_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        receipt.git_commit = vault.commit_and_push(relative, f"agent-state: seal {name} {run_id}")
        receipt.git_remote = repository
        (payload_root / "receipt.json").write_text(
            json.dumps(receipt.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        receipt.git_receipt_commit = vault.commit_and_push(relative, f"agent-state: receipt {name} {run_id}")
        receipt.write(private_receipt)
        receipt.require_retirement_gate()
        return receipt
    except BaseException:
        packer.abort()
        raise


def resume_cold_tree_capture(
    name: str,
    plan: RetentionPlan | None,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    *,
    run_id: str,
    repository: str = "organvm/arca",
    key_service: str = "limen-arca-vault",
    require_external_mount: bool = True,
    reconstruct_root: Path | None = None,
    captured_files: list[CapturedFile] | None = None,
) -> MetabolismReceipt:
    """Resume after encrypted atoms reached Git but final custody did not close."""

    vault = GitVault(vault_root, repository=repository)
    vault.verify_identity()
    relative = Path("agent-state") / name / run_id
    payload_root = vault.root / relative
    if not payload_root.is_dir():
        raise PipelineError(f"interrupted custody payload is missing: {run_id}")
    receipt = load_tree_manifest(payload_root)
    if receipt.run_id != run_id:
        raise PipelineError("tree capture run identity does not match resume request")
    if reconstruct_root is not None:
        source_root = reconstruct_root
    elif plan is not None:
        source_root = plan.root
    else:
        source_root = Path(receipt.source.path)
    unresolved_external = external_root.expanduser().resolve(strict=False)
    exact_root = unresolved_external / name / run_id
    _require_custody_targets_outside_source(
        source_root,
        {
            "vault-root": vault.root,
            "external-root": unresolved_external,
            "private-receipt": private_receipt,
            "encrypted-git-output": payload_root,
            "encrypted-external-output": exact_root,
        },
    )
    external_base = require_mounted_external(external_root) if require_external_mount else unresolved_external
    exact_root = external_base / name / run_id
    _require_custody_targets_outside_source(
        source_root,
        {
            "external-root": external_base,
            "encrypted-external-output": exact_root,
        },
    )
    external_base.mkdir(parents=True, exist_ok=True)
    key = keychain_key(key_service)
    available_profile = encryption_profile_digest("file-tree")
    if receipt.encryption_profile_digest is not None and receipt.encryption_profile_digest != available_profile:
        raise PipelineError("tree capture encryption profile does not match the available restorer")
    records: list[dict[str, Any]] = []
    sample = verify_atom_packs(
        receipt.packs,
        payload_root,
        key,
        logical_sha256=receipt.logical_sha256,
        sample=True,
    )
    full = verify_atom_packs(
        receipt.packs,
        payload_root,
        key,
        logical_sha256=receipt.logical_sha256,
        record_consumer=(lambda record: collect_file_entry(records, record)) if reconstruct_root is not None else None,
    )
    if not sample.passed or not full.passed:
        raise PipelineError(f"{name} resumed Git restoration failed")
    if reconstruct_root is not None:
        reconstructed = reconstruct_captured_files(receipt, reconstruct_root, records)
        plan = retention_plan_from_capture(receipt, reconstruct_root, reconstructed)
        if captured_files is not None:
            captured_files.extend(reconstructed)
    elif plan is None:
        raise PipelineError("resume requires either a retention plan or captured File Provider root")
    else:
        if receipt.source.bytes != plan.cold_bytes:
            raise PipelineError("current cold total does not match interrupted capture")
        require_plan_matches_source(plan, receipt.source)
    receipt.retained_hot_bytes = plan.hot_bytes
    exact_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    external_packs = _copy_packs(receipt.packs, payload_root, exact_root)
    external = replace(
        verify_atom_packs(
            external_packs,
            exact_root,
            key,
            logical_sha256=receipt.logical_sha256,
        ),
        scope="external-full",
    )
    if not external.passed:
        raise PipelineError(f"{name} resumed external restoration failed")
    if receipt.encryption_profile_digest is None:
        receipt.encryption_profile_digest = available_profile
    receipt.external_chunks = [chunk for pack in external_packs for chunk in pack.chunks]
    receipt.restorations = [sample, full, external]
    receipt.git_remote = repository
    receipt_message = f"agent-state: receipt {name} {run_id}"
    remote_completed: tuple[str, str, str] | None = None
    try:
        completed = vault.completed_receipt_commits(relative, receipt_message)
    except PipelineError as exc:
        if str(exc) != ARCA_REMOTE_EXACT_ERROR:
            raise
        remote_completed = vault.completed_receipt_at_remote(relative, receipt_message)
        completed = (remote_completed[0], remote_completed[1])
    if completed is not None:
        payload_commit, receipt_commit = completed
        receipt.git_commit = payload_commit
        try:
            durable = json.loads(
                remote_completed[2]
                if remote_completed is not None
                else (payload_root / "receipt.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError("completed ARCA receipt is missing or invalid") from exc
        expected = json.loads(json.dumps(receipt.as_dict(), sort_keys=True))
        if durable != expected:
            raise PipelineError("completed ARCA receipt does not match verified custody")
        receipt.git_receipt_commit = receipt_commit
        if not private_receipt.exists():
            receipt.write(private_receipt)
        _require_private_retirement_receipt(receipt, private_receipt)
        return receipt
    expected_paths = [relative / chunk.path for pack in receipt.packs for chunk in pack.chunks]
    expected_paths.append(relative / "manifest.json")
    receipt.git_commit = vault.resume_and_push_payload(
        relative,
        expected_paths,
        f"agent-state: seal {name} {run_id}",
    )
    receipt.write(payload_root / "receipt.json")
    receipt.git_receipt_commit = vault.commit_and_push(
        relative,
        receipt_message,
    )
    receipt.write(private_receipt)
    receipt.require_retirement_gate()
    return receipt


def run_cold_tree_campaign(
    name: str,
    plan: RetentionPlan,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    *,
    retire: bool = False,
    run_id: str | None = None,
) -> MetabolismReceipt:
    if retire:
        raise PipelineError(RETIREMENT_AUTHORIZATION_REQUIRED)
    owner = f"agent-state-metabolism-{os.getpid()}"
    with hold_lease("heavy", owner=owner, surface=f"{name}-agent-state-custody"):
        receipt = capture_cold_tree(
            name,
            plan,
            vault_root,
            external_root,
            private_receipt,
            run_id=run_id,
        )
        return receipt


def run_resume_cold_tree_campaign(
    name: str,
    plan: RetentionPlan,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    *,
    run_id: str,
    retire: bool = False,
) -> MetabolismReceipt:
    if retire:
        raise PipelineError(RETIREMENT_AUTHORIZATION_REQUIRED)
    owner = f"agent-state-metabolism-{os.getpid()}"
    with hold_lease("heavy", owner=owner, surface=f"{name}-agent-state-custody-resume"):
        receipt = resume_cold_tree_capture(
            name,
            plan,
            vault_root,
            external_root,
            private_receipt,
            run_id=run_id,
        )
        return receipt


def _write_restore_receipt(
    path: Path,
    result: RestoredFileResult,
    *,
    run_id: str,
    git_receipt_commit: str,
) -> dict[str, object]:
    stable: dict[str, object] = {
        "schema": "limen.file_provider_restore_receipt.v1",
        "run_id": run_id,
        "item_hash": result.item_hash,
        "selector_kind": result.selector_kind,
        "selector_hash": result.selector_hash or result.item_hash,
        "bytes": result.bytes,
        "sha256": result.sha256,
        "git_receipt_commit": git_receipt_commit,
    }
    existing = _preflight_restore_receipt(path, stable)
    if existing is not None:
        return existing
    payload = {
        **stable,
        "status": result.status,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        raise PipelineError("cannot prepare private File Provider restore receipt") from None
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = _preflight_restore_receipt(path, stable)
        if existing is None:
            raise PipelineError("private File Provider restore receipt appeared without content")
        return existing
    except OSError:
        raise PipelineError("cannot create private File Provider restore receipt") from None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass
        raise PipelineError("cannot persist private File Provider restore receipt") from None
    return payload


def _valid_restore_receipt(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    expected = {
        "schema",
        "run_id",
        "item_hash",
        "selector_kind",
        "selector_hash",
        "bytes",
        "sha256",
        "git_receipt_commit",
        "status",
        "recorded_at",
    }
    hashes = (
        payload.get("item_hash"),
        payload.get("selector_hash"),
        payload.get("sha256"),
    )
    return (
        set(payload) == expected
        and payload.get("schema") == "limen.file_provider_restore_receipt.v1"
        and isinstance(payload.get("run_id"), str)
        and bool(payload.get("run_id"))
        and payload.get("selector_kind") in {"file_provider_item_hash", "captured_path_hash", "captured_name_hash"}
        and all(
            isinstance(digest, str)
            and len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest)
            for digest in hashes
        )
        and isinstance(payload.get("bytes"), int)
        and not isinstance(payload.get("bytes"), bool)
        and payload["bytes"] >= 0
        and isinstance(payload.get("git_receipt_commit"), str)
        and len(payload["git_receipt_commit"]) == 40
        and all(character in "0123456789abcdef" for character in payload["git_receipt_commit"])
        and payload.get("status") in {"restored", "already_restored", "already_dataless"}
        and isinstance(payload.get("recorded_at"), str)
        and bool(payload.get("recorded_at"))
    )


def _preflight_restore_receipt(path: Path, expected: Mapping[str, object]) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise PipelineError("private File Provider restore receipt is invalid") from None
    if not _valid_restore_receipt(payload) or any(payload.get(key) != value for key, value in expected.items()):
        raise PipelineError("private File Provider restore receipt conflicts with this restoration")
    return payload


def run_restore_cloudkit_item_campaign(
    name: str,
    root: Path,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    restore_receipt: Path,
    *,
    run_id: str,
    item_hash: str | None = None,
    captured_path_hash: str | None = None,
    captured_name_hash: str | None = None,
    repository: str = "organvm/arca",
    key_service: str = "limen-arca-vault",
) -> dict[str, object]:
    """Restore one conflict-free captured item and write a path-free receipt."""

    owner = f"agent-state-metabolism-{os.getpid()}"
    with hold_lease("heavy", owner=owner, surface=f"{name}-cloudkit-item-restore"):
        vault = GitVault(vault_root, repository=repository)
        vault.verify_identity()
        relative = Path("agent-state") / name / run_id
        try:
            payload_commit, receipt_commit, receipt_text = vault.completed_receipt_at_remote(
                relative,
                f"agent-state: receipt {name} {run_id}",
            )
            value = json.loads(receipt_text)
            if not isinstance(value, dict):
                raise ReceiptError("completed File Provider receipt must be a JSON object")
            tracked = MetabolismReceipt.from_dict(value)
        except (ReceiptError, json.JSONDecodeError) as exc:
            raise PipelineError("completed File Provider custody receipt is invalid") from exc
        if tracked.git_commit != payload_commit or tracked.git_receipt_commit is not None:
            raise PipelineError("completed File Provider custody is not exact on its remote")
        tracked.git_receipt_commit = receipt_commit
        if tracked.run_id != run_id:
            raise PipelineError("completed File Provider custody run does not match the restore request")
        _require_private_retirement_receipt(tracked, private_receipt)
        if tracked.git_receipt_commit is None:
            raise PipelineError("completed File Provider receipt commit is unavailable")
        selectors = [
            (kind, value)
            for kind, value in (
                ("file_provider_item_hash", item_hash),
                ("captured_path_hash", captured_path_hash),
                ("captured_name_hash", captured_name_hash),
            )
            if value is not None
        ]
        if len(selectors) != 1:
            raise PipelineError("restore requires exactly one path-free selector")
        selector_kind, selector_hash = selectors[0]
        request = {
            "schema": "limen.file_provider_restore_receipt.v1",
            "run_id": run_id,
            "selector_kind": selector_kind,
            "selector_hash": selector_hash,
            "git_receipt_commit": tracked.git_receipt_commit,
        }
        _preflight_restore_receipt(restore_receipt, request)
        payload_root = require_mounted_external(external_root) / name / run_id

        def preflight(result: RestoredFileResult) -> None:
            _preflight_restore_receipt(
                restore_receipt,
                {
                    **request,
                    "item_hash": result.item_hash,
                    "bytes": result.bytes,
                    "sha256": result.sha256,
                },
            )

        result = restore_captured_file(
            tracked,
            root,
            payload_root,
            keychain_key(key_service),
            item_hash,
            captured_path_hash=captured_path_hash,
            captured_name_hash=captured_name_hash,
            before_mutation=preflight,
        )
        return _write_restore_receipt(
            restore_receipt,
            result,
            run_id=run_id,
            git_receipt_commit=tracked.git_receipt_commit,
        )


def _record_file_provider_result(
    receipt: MetabolismReceipt,
    private_receipt: Path,
    result: FileProviderResult,
) -> None:
    receipt.source_retired = result.complete
    receipt.retirement_proof = (
        "file-provider-progress:"
        f"selected-files={result.selected_files};"
        f"evicted-files={result.evicted_files};"
        f"already-reclaimed-files={result.already_reclaimed_files};"
        f"retained-non-evictable-files={result.retained_non_evictable_files};"
        f"retained-non-evictable-bytes={result.retained_non_evictable_bytes};"
        f"allocated-after={result.allocated_after};"
        f"remaining-files={result.remaining_files};"
        f"authorization-prepared={str(result.authorization_prepared).lower()}"
    )
    receipt.write(private_receipt)


def _run_file_provider_action(
    receipt: MetabolismReceipt,
    root: Path,
    captured: tuple[CapturedFile, ...],
    private_receipt: Path,
    *,
    progress_path: Path | None,
    prepare_authorization: Path | None,
    prepare_campaign_authorization: Path | None,
    authorization_principal: str | None,
    authorization_receipt: Path | None,
    authorization_signature: Path | None,
) -> None:
    _require_private_retirement_receipt(receipt, private_receipt)
    result = process_file_provider_items(
        receipt,
        root,
        captured,
        progress_path or progress_path_for(private_receipt),
        prepare_authorization=prepare_authorization,
        prepare_campaign_authorization=prepare_campaign_authorization,
        authorization_principal=authorization_principal,
        authorization_receipt=authorization_receipt,
        authorization_signature=authorization_signature,
    )
    _record_file_provider_result(receipt, private_receipt, result)


def run_cloudkit_materialization_campaign(
    name: str,
    plan: RetentionPlan,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    *,
    evict: bool = False,
    run_id: str | None = None,
    progress_path: Path | None = None,
    prepare_authorization: Path | None = None,
    prepare_campaign_authorization: Path | None = None,
    authorization_principal: str | None = None,
    authorization_receipt: Path | None = None,
    authorization_signature: Path | None = None,
) -> MetabolismReceipt:
    """Preserve materialized iCloud files, then reclaim via File Provider."""

    owner = f"agent-state-metabolism-{os.getpid()}"
    with hold_lease("heavy", owner=owner, surface=f"{name}-cloudkit-custody"):
        records: list[dict[str, Any]] = []
        receipt = capture_cold_tree(
            name,
            plan,
            vault_root,
            external_root,
            private_receipt,
            run_id=run_id,
            record_consumer=lambda record: collect_file_entry(records, record),
        )
        captured = reconstruct_captured_files(receipt, plan.root, records)
        if evict or prepare_authorization is not None or prepare_campaign_authorization is not None:
            _run_file_provider_action(
                receipt,
                plan.root,
                captured,
                private_receipt,
                progress_path=progress_path,
                prepare_authorization=prepare_authorization,
                prepare_campaign_authorization=prepare_campaign_authorization,
                authorization_principal=authorization_principal,
                authorization_receipt=authorization_receipt,
                authorization_signature=authorization_signature,
            )
        return receipt


def run_resume_cloudkit_materialization_campaign(
    name: str,
    root: Path,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    *,
    run_id: str,
    evict: bool = False,
    progress_path: Path | None = None,
    prepare_authorization: Path | None = None,
    prepare_campaign_authorization: Path | None = None,
    authorization_principal: str | None = None,
    authorization_receipt: Path | None = None,
    authorization_signature: Path | None = None,
) -> MetabolismReceipt:
    """Resume preserved iCloud ciphertext, then optionally reclaim materializations."""

    owner = f"agent-state-metabolism-{os.getpid()}"
    with hold_lease("heavy", owner=owner, surface=f"{name}-cloudkit-custody-resume"):
        captured_files: list[CapturedFile] = []
        receipt = resume_cold_tree_capture(
            name,
            None,
            vault_root,
            external_root,
            private_receipt,
            run_id=run_id,
            reconstruct_root=root,
            captured_files=captured_files,
        )
        if evict or prepare_authorization is not None or prepare_campaign_authorization is not None:
            _run_file_provider_action(
                receipt,
                root,
                tuple(captured_files),
                private_receipt,
                progress_path=progress_path,
                prepare_authorization=prepare_authorization,
                prepare_campaign_authorization=prepare_campaign_authorization,
                authorization_principal=authorization_principal,
                authorization_receipt=authorization_receipt,
                authorization_signature=authorization_signature,
            )
        return receipt
