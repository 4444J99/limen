"""Dual encrypted custody and bounded retirement for session file trees."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, replace
from pathlib import Path

from limen.host_admission import hold_lease

from .crypto import EncryptedAtomPacker, keychain_key, verify_atom_packs
from .models import AtomPack, CipherChunk, MetabolismReceipt, RestoreProof, SourceProof
from .pipeline import GitVault, PipelineError, require_mounted_external, run_id_now
from .tree import RetentionPlan, atomize_file_tree, require_plan_matches_source, retire_cold_files


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
) -> MetabolismReceipt:
    if not name or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in name):
        raise ValueError("tree custody name must be lowercase alphanumeric with hyphens")
    if not plan.cold_paths:
        raise PipelineError(f"no cold files selected for {name}")
    external_base = require_mounted_external(external_root) if require_external_mount else external_root.resolve()
    external_base.mkdir(parents=True, exist_ok=True)
    run_id = run_id or run_id_now()
    vault = GitVault(vault_root, repository=repository)
    vault.verify()
    relative = Path("agent-state") / name / run_id
    payload_root = vault.root / relative
    exact_root = external_base / name / run_id
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
        full = verify_atom_packs(packs, payload_root, key, logical_sha256=result.logical_sha256)
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
    plan: RetentionPlan,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    *,
    run_id: str,
    repository: str = "organvm/arca",
    key_service: str = "limen-arca-vault",
    require_external_mount: bool = True,
) -> MetabolismReceipt:
    """Resume after encrypted atoms reached Git but final custody did not close."""

    external_base = require_mounted_external(external_root) if require_external_mount else external_root.resolve()
    external_base.mkdir(parents=True, exist_ok=True)
    vault = GitVault(vault_root, repository=repository)
    vault.verify()
    relative = Path("agent-state") / name / run_id
    payload_root = vault.root / relative
    if not payload_root.is_dir():
        raise PipelineError(f"interrupted custody payload is missing: {run_id}")
    receipt = load_tree_manifest(payload_root)
    if receipt.run_id != run_id:
        raise PipelineError("tree capture run identity does not match resume request")
    if receipt.source.bytes != plan.cold_bytes:
        raise PipelineError("current cold total does not match interrupted capture")
    require_plan_matches_source(plan, receipt.source)
    receipt.retained_hot_bytes = plan.hot_bytes
    key = keychain_key(key_service)
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
    )
    if not sample.passed or not full.passed:
        raise PipelineError(f"{name} resumed Git restoration failed")
    exact_root = external_base / name / run_id
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
    receipt.external_chunks = [chunk for pack in external_packs for chunk in pack.chunks]
    receipt.restorations = [sample, full, external]
    receipt.git_remote = repository
    receipt.git_commit = vault.require_exact_remote_head()
    receipt.write(payload_root / "receipt.json")
    receipt.git_receipt_commit = vault.commit_and_push(
        relative,
        f"agent-state: receipt {name} {run_id}",
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
        if retire:
            deleted = retire_cold_files(receipt, plan)
            receipt.source_retired = True
            receipt.retirement_proof = (
                f"deleted-files:{deleted};deleted-bytes:{plan.cold_bytes};retained-hot-bytes:{plan.hot_bytes}"
            )
            receipt.write(private_receipt)
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
        if retire:
            deleted = retire_cold_files(receipt, plan)
            receipt.source_retired = True
            receipt.retirement_proof = (
                f"deleted-files:{deleted};deleted-bytes:{plan.cold_bytes};retained-hot-bytes:{plan.hot_bytes}"
            )
            receipt.write(private_receipt)
        return receipt
