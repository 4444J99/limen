from __future__ import annotations

import json
import time
from contextlib import nullcontext
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from limen.agent_state import tree_pipeline
from limen.agent_state.crypto import EncryptedAtomPacker, encryption_profile_digest
from limen.agent_state.models import MetabolismReceipt, ReceiptError
from limen.agent_state.pipeline import ARCA_REMOTE_EXACT_ERROR, PipelineError
from limen.agent_state.tree import RetentionPlan, atomize_file_tree, plan_retention

KEY = "tree-resume-test-key"


class _Vault:
    root: Path
    resumed = False

    def __init__(self, root: Path, *, repository: str = "organvm/arca"):
        self.root = root
        self.repository = repository

    def verify_identity(self) -> None:
        return None

    def resume_and_push_payload(
        self,
        relative: Path,
        expected_paths: list[Path],
        message: str,
    ) -> str:
        assert relative == Path("agent-state/icloud-drive/run")
        assert expected_paths[-1] == relative / "manifest.json"
        assert message == "agent-state: seal icloud-drive run"
        type(self).resumed = True
        return "a" * 40

    def commit_and_push(self, relative: Path, message: str) -> str:
        assert relative == Path("agent-state/icloud-drive/run")
        assert message == "agent-state: receipt icloud-drive run"
        return "b" * 40

    def completed_receipt_commits(
        self,
        relative: Path,
        message: str,
    ) -> tuple[str, str] | None:
        assert relative == Path("agent-state/icloud-drive/run")
        assert message == "agent-state: receipt icloud-drive run"
        return None


class _CompletedVault(_Vault):
    def completed_receipt_at_remote(
        self,
        relative: Path,
        message: str,
    ) -> tuple[str, str, str]:
        assert relative == Path("agent-state/icloud-drive/run")
        assert message == "agent-state: receipt icloud-drive run"
        return (
            "a" * 40,
            "b" * 40,
            (self.root / relative / "receipt.json").read_text(encoding="utf-8"),
        )

    def completed_receipt_commits(
        self,
        relative: Path,
        message: str,
    ) -> tuple[str, str] | None:
        assert relative == Path("agent-state/icloud-drive/run")
        assert message == "agent-state: receipt icloud-drive run"
        return "a" * 40, "b" * 40

    def resume_and_push_payload(self, *_args, **_kwargs) -> str:
        raise AssertionError("completed custody must not push payload batches")

    def commit_and_push(self, *_args, **_kwargs) -> str:
        raise AssertionError("completed custody must not create another receipt")


class _AdvancedRemoteVault(_CompletedVault):
    def completed_receipt_commits(
        self,
        relative: Path,
        message: str,
    ) -> tuple[str, str] | None:
        raise PipelineError(ARCA_REMOTE_EXACT_ERROR)


def _interrupted_tree(tmp_path: Path) -> tuple[Path, Path, Path, RetentionPlan]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "materialized.mov").write_bytes(b"private cloud bytes" * 100)
    plan = plan_retention(source, now=time.time() + 1, hot_days=0)
    vault = tmp_path / "vault"
    payload = vault / "agent-state" / "icloud-drive" / "run"
    payload.mkdir(parents=True)
    packer = EncryptedAtomPacker(payload, KEY, pack_plaintext_limit=512, chunk_limit=256)
    result = atomize_file_tree(plan, packer)
    packs = list(packer.close())
    manifest = {
        "schema": "limen.agent_state_metabolism.v1",
        "run_id": "run",
        "source": asdict(result.source),
        "file_count": result.file_count,
        "atom_count": result.atom_count,
        "logical_sha256": result.logical_sha256,
        "duplicate_chunks": result.duplicate_chunks,
        "cold_bytes": plan.cold_bytes,
        "retained_hot_bytes": plan.hot_bytes,
        "packs": [asdict(pack) for pack in packs],
        "restorations": [],
    }
    (payload / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return source, vault, payload, plan


def _resume(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    plan: RetentionPlan,
    vault: Path,
):
    monkeypatch.setattr(tree_pipeline, "GitVault", _Vault)
    monkeypatch.setattr(tree_pipeline, "keychain_key", lambda _service: KEY)
    return tree_pipeline.resume_cold_tree_capture(
        "icloud-drive",
        plan,
        vault,
        tmp_path / "external",
        tmp_path / "private-receipt.json",
        run_id="run",
        require_external_mount=False,
    )


def _enriched_custody_receipt(receipt: MetabolismReceipt) -> MetabolismReceipt:
    enriched = MetabolismReceipt.from_dict(receipt.as_dict())
    restored_at = datetime(2026, 7, 30, 12, tzinfo=UTC).isoformat()
    remote_refs = (
        f"github:{receipt.git_remote}@{receipt.git_commit}",
        f"github:{receipt.git_remote}@{receipt.git_receipt_commit}",
    )
    enriched.restorations = [
        (
            replace(
                proof,
                device_id="gitRestoreDevice0001",
                restored_at=restored_at,
                encryption_profile_digest=receipt.encryption_profile_digest,
                remote_refs=remote_refs,
            )
            if proof.scope == "git-full-manifest"
            else replace(
                proof,
                device_id="externalRestoreDevice0001",
                restored_at=restored_at,
                encryption_profile_digest=receipt.encryption_profile_digest,
            )
            if proof.scope == "external-full"
            else proof
        )
        for proof in enriched.restorations
    ]
    return enriched


@pytest.mark.parametrize(
    "nested_target",
    [
        "vault-root",
        "external-root",
        "private-receipt",
        "encrypted-git-output",
        "encrypted-external-output",
    ],
)
def test_capture_rejects_custody_targets_inside_source_before_writes(
    tmp_path: Path,
    nested_target: str,
) -> None:
    source = tmp_path / "source"
    vault = tmp_path / "vault"
    external = tmp_path / "external"
    private_receipt = tmp_path / "private" / "receipt.json"
    if nested_target == "vault-root":
        vault = source / "vault"
    elif nested_target == "external-root":
        external = source / "external"
    elif nested_target == "private-receipt":
        private_receipt = source / "receipts" / "receipt.json"
    elif nested_target == "encrypted-git-output":
        source = vault / "agent-state"
    elif nested_target == "encrypted-external-output":
        source = external / "icloud-drive"
    source.mkdir(parents=True)
    (source / "history.json").write_text("protected")
    plan = plan_retention(source, now=time.time() + 1, hot_days=0)

    with pytest.raises(PipelineError, match=nested_target):
        tree_pipeline.capture_cold_tree(
            "icloud-drive",
            plan,
            vault,
            external,
            private_receipt,
            run_id="run",
            require_external_mount=False,
        )

    assert not private_receipt.exists()
    assert not (vault / "agent-state" / "icloud-drive" / "run").exists()
    assert not (external / "icloud-drive" / "run").exists()


def test_custody_guard_uses_filesystem_identity_for_case_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "Data"
    alias = tmp_path / "data"
    source.mkdir()
    if not alias.exists():
        alias.mkdir()
    real_samefile = tree_pipeline.os.path.samefile

    def samefile(first, second):
        if {Path(first), Path(second)} == {source, alias}:
            return True
        return real_samefile(first, second)

    monkeypatch.setattr(tree_pipeline.os.path, "samefile", samefile)

    with pytest.raises(PipelineError, match="vault-root"):
        tree_pipeline._require_custody_targets_outside_source(
            source,
            {"vault-root": alias / "vault"},
        )


def test_resume_rejects_private_receipt_inside_source_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, vault, _payload, plan = _interrupted_tree(tmp_path)
    external = tmp_path / "external"
    private_receipt = source / "receipt.json"
    monkeypatch.setattr(tree_pipeline, "GitVault", _Vault)

    with pytest.raises(PipelineError, match="private-receipt"):
        tree_pipeline.resume_cold_tree_capture(
            "icloud-drive",
            plan,
            vault,
            external,
            private_receipt,
            run_id="run",
            require_external_mount=False,
        )

    assert not private_receipt.exists()
    assert not external.exists()


def test_resume_verifies_then_pushes_existing_ciphertext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, _payload, plan = _interrupted_tree(tmp_path)
    _Vault.resumed = False

    receipt = _resume(monkeypatch, tmp_path, plan, vault)

    assert _Vault.resumed
    assert receipt.git_commit == "a" * 40
    assert receipt.git_receipt_commit == "b" * 40
    assert receipt.encryption_profile_digest == encryption_profile_digest()
    assert (tmp_path / "private-receipt.json").is_file()
    receipt.require_retirement_gate()


def test_private_receipt_matches_json_normalized_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, _payload, plan = _interrupted_tree(tmp_path)
    receipt = _resume(monkeypatch, tmp_path, plan, vault)

    tree_pipeline._require_private_retirement_receipt(
        receipt,
        tmp_path / "private-receipt.json",
    )


def test_metabolism_receipt_round_trips_only_canonical_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, _payload, plan = _interrupted_tree(tmp_path)
    receipt = _resume(monkeypatch, tmp_path, plan, vault)
    path = tmp_path / "private-receipt.json"

    assert MetabolismReceipt.read(path).as_dict() == receipt.as_dict()
    canonical = json.loads(path.read_text())
    malformed = json.loads(json.dumps(canonical))
    malformed["unexpected"] = True
    path.write_text(json.dumps(malformed))
    with pytest.raises(ReceiptError, match="non-canonical"):
        MetabolismReceipt.read(path)
    malformed = json.loads(json.dumps(canonical))
    malformed["source"]["stat_before"] = [1, 2]
    path.write_text(json.dumps(malformed))
    with pytest.raises(ReceiptError, match="invalid source identity"):
        MetabolismReceipt.read(path)
    malformed = json.loads(json.dumps(canonical))
    malformed["packs"][0]["atom_count"] = "1"
    path.write_text(json.dumps(malformed))
    with pytest.raises(ReceiptError, match="consistency checks"):
        MetabolismReceipt.read(path)
    malformed = json.loads(json.dumps(canonical))
    malformed["restorations"][0]["passed"] = "false"
    path.write_text(json.dumps(malformed))
    with pytest.raises(ReceiptError, match="consistency checks"):
        MetabolismReceipt.read(path)


def test_private_custody_match_ignores_only_mutable_retirement_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, _payload, plan = _interrupted_tree(tmp_path)
    receipt = _resume(monkeypatch, tmp_path, plan, vault)
    receipt.retirement_proof = "file-provider-progress:remaining-files=1"
    receipt.write(tmp_path / "private-receipt.json")
    receipt.retirement_proof = None

    tree_pipeline._require_private_retirement_receipt(receipt, tmp_path / "private-receipt.json")
    durable = json.loads((tmp_path / "private-receipt.json").read_text())
    durable["git_commit"] = "f" * 40
    (tmp_path / "private-receipt.json").write_text(json.dumps(durable))
    with pytest.raises(PipelineError, match="does not match verified custody"):
        tree_pipeline._require_private_retirement_receipt(receipt, tmp_path / "private-receipt.json")


def test_resume_accepts_completed_exact_receipt_without_another_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, _payload, plan = _interrupted_tree(tmp_path)
    first = _resume(monkeypatch, tmp_path, plan, vault)
    monkeypatch.setattr(tree_pipeline, "GitVault", _CompletedVault)
    monkeypatch.setattr(tree_pipeline, "keychain_key", lambda _service: KEY)

    resumed = tree_pipeline.resume_cold_tree_capture(
        "icloud-drive",
        plan,
        vault,
        tmp_path / "external",
        tmp_path / "private-receipt.json",
        run_id="run",
        require_external_mount=False,
    )

    assert resumed.as_dict() == first.as_dict()


def test_resume_accepts_completed_receipt_with_valid_custody_enrichment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, _payload, plan = _interrupted_tree(tmp_path)
    first = _resume(monkeypatch, tmp_path, plan, vault)
    private_receipt = tmp_path / "private-receipt.json"
    enriched = _enriched_custody_receipt(first)
    enriched.write(private_receipt)
    original = private_receipt.read_bytes()
    monkeypatch.setattr(tree_pipeline, "GitVault", _CompletedVault)
    monkeypatch.setattr(tree_pipeline, "keychain_key", lambda _service: KEY)

    resumed = tree_pipeline.resume_cold_tree_capture(
        "icloud-drive",
        plan,
        vault,
        tmp_path / "external",
        private_receipt,
        run_id="run",
        require_external_mount=False,
    )

    assert resumed.as_dict() == first.as_dict()
    assert private_receipt.read_bytes() == original


def test_resume_rejects_invalid_custody_enrichment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, _payload, plan = _interrupted_tree(tmp_path)
    first = _resume(monkeypatch, tmp_path, plan, vault)
    private_receipt = tmp_path / "private-receipt.json"
    enriched = _enriched_custody_receipt(first)
    git_device = next(proof.device_id for proof in enriched.restorations if proof.scope == "git-full-manifest")
    enriched.restorations = [
        (replace(proof, device_id=git_device) if proof.scope == "external-full" else proof)
        for proof in enriched.restorations
    ]
    enriched.write(private_receipt)

    with pytest.raises(PipelineError, match="does not match verified custody"):
        tree_pipeline._require_private_retirement_receipt(first, private_receipt)


def test_resume_rematerializes_missing_private_receipt_from_exact_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, _payload, plan = _interrupted_tree(tmp_path)
    first = _resume(monkeypatch, tmp_path, plan, vault)
    private_receipt = tmp_path / "private-receipt.json"
    private_receipt.unlink()
    monkeypatch.setattr(tree_pipeline, "GitVault", _CompletedVault)
    monkeypatch.setattr(tree_pipeline, "keychain_key", lambda _service: KEY)

    resumed = tree_pipeline.resume_cold_tree_capture(
        "icloud-drive",
        plan,
        vault,
        tmp_path / "external",
        private_receipt,
        run_id="run",
        require_external_mount=False,
    )

    assert resumed.as_dict() == first.as_dict()
    assert MetabolismReceipt.read(private_receipt).as_dict() == first.as_dict()
    assert private_receipt.stat().st_mode & 0o777 == 0o600


def test_resume_accepts_completed_receipt_reachable_behind_remote_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, _payload, plan = _interrupted_tree(tmp_path)
    first = _resume(monkeypatch, tmp_path, plan, vault)
    monkeypatch.setattr(tree_pipeline, "GitVault", _AdvancedRemoteVault)
    monkeypatch.setattr(tree_pipeline, "keychain_key", lambda _service: KEY)

    resumed = tree_pipeline.resume_cold_tree_capture(
        "icloud-drive",
        plan,
        vault,
        tmp_path / "external",
        tmp_path / "private-receipt.json",
        run_id="run",
        require_external_mount=False,
    )

    assert resumed.as_dict() == first.as_dict()


def test_single_item_restore_writes_path_free_private_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, vault, _payload, plan = _interrupted_tree(tmp_path)
    _resume(monkeypatch, tmp_path, plan, vault)
    monkeypatch.setattr(tree_pipeline, "GitVault", _CompletedVault)
    monkeypatch.setattr(tree_pipeline, "keychain_key", lambda _service: KEY)
    monkeypatch.setattr(tree_pipeline, "hold_lease", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(tree_pipeline, "require_mounted_external", lambda path: path.resolve())
    monkeypatch.setattr(
        tree_pipeline,
        "restore_captured_file",
        lambda *_args, **_kwargs: tree_pipeline.RestoredFileResult(
            item_hash="d" * 64,
            status="restored",
            bytes=42,
            sha256="e" * 64,
            selector_kind="captured_name_hash",
            selector_hash="c" * 64,
        ),
    )
    restore_receipt = tmp_path / "restore.json"

    result = tree_pipeline.run_restore_cloudkit_item_campaign(
        "icloud-drive",
        source,
        vault,
        tmp_path / "external",
        tmp_path / "private-receipt.json",
        restore_receipt,
        run_id="run",
        captured_name_hash="c" * 64,
    )

    assert result["status"] == "restored"
    assert result["item_hash"] == "d" * 64
    assert result["selector_kind"] == "captured_name_hash"
    assert result["selector_hash"] == "c" * 64
    assert str(source) not in restore_receipt.read_text()
    original = restore_receipt.read_bytes()
    repeated = tree_pipeline.run_restore_cloudkit_item_campaign(
        "icloud-drive",
        source,
        vault,
        tmp_path / "external",
        tmp_path / "private-receipt.json",
        restore_receipt,
        run_id="run",
        captured_name_hash="c" * 64,
    )
    assert repeated == result
    assert restore_receipt.read_bytes() == original


def test_cloud_resume_reconstructs_original_set_from_verified_atoms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, vault, _payload, plan = _interrupted_tree(tmp_path)
    _resume(monkeypatch, tmp_path, plan, vault)
    monkeypatch.setattr(tree_pipeline, "GitVault", _CompletedVault)
    monkeypatch.setattr(tree_pipeline, "keychain_key", lambda _service: KEY)
    monkeypatch.setattr(tree_pipeline, "require_mounted_external", lambda path: path.resolve())
    monkeypatch.setattr(tree_pipeline, "hold_lease", lambda *_args, **_kwargs: nullcontext())
    observed: list[str] = []

    def process(_receipt, root, captured, *_args, **_kwargs):
        assert root == source
        observed.extend(entry.relative for entry in captured)
        return tree_pipeline.FileProviderResult(
            selected_files=1,
            evicted_files=0,
            already_reclaimed_files=0,
            retained_non_evictable_files=0,
            retained_non_evictable_bytes=0,
            allocated_after=plan.cold_bytes,
            remaining_files=1,
            complete=False,
            authorization_prepared=True,
        )

    monkeypatch.setattr(tree_pipeline, "process_file_provider_items", process)
    resumed = tree_pipeline.run_resume_cloudkit_materialization_campaign(
        "icloud-drive",
        source,
        vault,
        tmp_path / "external",
        tmp_path / "private-receipt.json",
        run_id="run",
        prepare_authorization=tmp_path / "authorization.json",
        authorization_principal="test-authorizer",
    )

    assert observed == ["materialized.mov"]
    assert not resumed.source_retired
    assert "remaining-files=1" in str(resumed.retirement_proof)


def test_resume_rejects_corrupt_ciphertext_before_remote_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, vault, payload, plan = _interrupted_tree(tmp_path)
    ciphertext = next(payload.glob("atoms-*.enc.part-*"))
    damaged = bytearray(ciphertext.read_bytes())
    damaged[-1] ^= 1
    ciphertext.write_bytes(damaged)
    _Vault.resumed = False

    with pytest.raises(PipelineError, match="resumed Git restoration failed"):
        _resume(monkeypatch, tmp_path, plan, vault)

    assert not _Vault.resumed


def test_resume_rejects_source_inventory_drift_before_remote_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, vault, _payload, _plan = _interrupted_tree(tmp_path)
    (source / "materialized.mov").write_bytes(b"changed after capture")
    changed_plan = plan_retention(source, now=time.time() + 1, hot_days=0)
    _Vault.resumed = False

    with pytest.raises(PipelineError, match="current cold total"):
        _resume(monkeypatch, tmp_path, changed_plan, vault)

    assert not _Vault.resumed


def test_cloud_eviction_requires_matching_private_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, vault, _payload, plan = _interrupted_tree(tmp_path)
    receipt = _resume(monkeypatch, tmp_path, plan, vault)
    (tmp_path / "private-receipt.json").unlink()
    evicted = False

    def unexpected_eviction(*_args, **_kwargs):
        nonlocal evicted
        evicted = True
        raise AssertionError("eviction must not run")

    monkeypatch.setattr(tree_pipeline, "hold_lease", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(tree_pipeline, "resume_cold_tree_capture", lambda *_args, **_kwargs: receipt)
    monkeypatch.setattr(tree_pipeline, "process_file_provider_items", unexpected_eviction)

    with pytest.raises(PipelineError, match="private retirement receipt"):
        tree_pipeline.run_resume_cloudkit_materialization_campaign(
            "icloud-drive",
            source,
            vault,
            tmp_path / "external",
            tmp_path / "private-receipt.json",
            run_id="run",
            evict=True,
        )

    assert not evicted
