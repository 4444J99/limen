"""Dual encrypted custody and bounded retirement for session file trees."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, replace
from pathlib import Path

from limen.host_admission import hold_lease

from .crypto import EncryptedAtomPacker, keychain_key, verify_atom_packs
from .models import AtomPack, MetabolismReceipt
from .pipeline import GitVault, PipelineError, require_mounted_external, run_id_now
from .tree import RetentionPlan, atomize_file_tree, retire_cold_files


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
        shutil.rmtree(payload_root, ignore_errors=True)
        shutil.rmtree(exact_root, ignore_errors=True)
        raise


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
