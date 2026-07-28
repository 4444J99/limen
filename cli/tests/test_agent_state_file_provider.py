from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from limen.agent_state import file_provider
from limen.agent_state.atomize import canonical_bytes
from limen.agent_state.crypto import EncryptedAtomPacker
from limen.agent_state.models import CipherChunk, MetabolismReceipt, RestoreProof
from limen.agent_state.pipeline import PipelineError
from limen.agent_state.tree import RetentionPlan, atomize_file_tree


def _captured(tmp_path: Path, names: tuple[str, ...]) -> tuple[MetabolismReceipt, tuple, Path]:
    root = tmp_path / "source"
    root.mkdir()
    for index, name in enumerate(names):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"private-{index:04d}".encode())
    relatives = tuple(sorted(names))
    plan = RetentionPlan(
        root=root,
        cold_paths=relatives,
        cold_bytes=sum((root / name).stat().st_size for name in relatives),
        hot_paths=(),
        hot_bytes=0,
        cutoff_epoch=0.0,
        maximum_hot_bytes=0,
    )
    records: list[dict[str, Any]] = []

    def sink(envelope: dict[str, Any], _line: bytes) -> None:
        file_provider.collect_file_entry(records, envelope["record"])

    result = atomize_file_tree(plan, sink, chunk_size=128)
    receipt = MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="run-0001",
        source=result.source,
        atom_count=result.atom_count,
        logical_sha256=result.logical_sha256,
        git_remote="organvm/arca",
        git_commit="a" * 40,
        git_receipt_commit="b" * 40,
        external_chunks=[CipherChunk(path="atoms.enc", bytes=1, sha256="c" * 64)],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=True),
        ],
    )
    captured = file_provider.reconstruct_captured_files(receipt, root, records)
    return receipt, captured, root


def _encrypted_capture(
    tmp_path: Path,
    names: tuple[str, ...],
) -> tuple[MetabolismReceipt, Path, Path]:
    root = tmp_path / "encrypted-source"
    root.mkdir()
    for index, name in enumerate(names):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((f"private-{index:04d}-" * 200).encode())
    relatives = tuple(sorted(names))
    plan = RetentionPlan(
        root=root,
        cold_paths=relatives,
        cold_bytes=sum((root / name).stat().st_size for name in relatives),
        hot_paths=(),
        hot_bytes=0,
        cutoff_epoch=0.0,
        maximum_hot_bytes=0,
    )
    payload = tmp_path / "encrypted-payload"
    packer = EncryptedAtomPacker(payload, "restore-test-key", pack_plaintext_limit=1024, chunk_limit=512)
    result = atomize_file_tree(plan, packer, chunk_size=256)
    packs = list(packer.close())
    receipt = MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="restore-run",
        source=result.source,
        atom_count=result.atom_count,
        logical_sha256=result.logical_sha256,
        packs=packs,
        git_remote="organvm/arca",
        git_commit="a" * 40,
        git_receipt_commit="b" * 40,
        external_chunks=[CipherChunk(path="external.enc", bytes=1, sha256="c" * 64)],
        restorations=[
            RestoreProof(scope="git-sample", passed=True),
            RestoreProof(scope="git-full-manifest", passed=True),
            RestoreProof(scope="external-full", passed=True),
        ],
    )
    return receipt, root, payload


def _authorization(manifest: dict[str, Any]) -> bytes:
    value = {
        "schema": file_provider.AUTHORIZATION_SCHEMA,
        "action": file_provider.AUTHORIZATION_ACTION,
        "attempt_id": manifest["attempt_id"],
        "authorized_by": manifest["authorization_principal"],
        "issued_at": "2026-07-25T05:00:00Z",
        "expires_at": "2026-07-25T05:15:00Z",
        "manifest_hash": file_provider._manifest_hash(manifest),
        "item_count": len(manifest["items"]),
        "item_hashes": [item["item_hash"] for item in manifest["items"]],
    }
    return canonical_bytes(value) + b"\n"


def _legacy_campaign_authorization(plan: dict[str, Any], *, max_attempts: int = 1) -> bytes:
    value = {
        "schema": file_provider.CAMPAIGN_AUTHORIZATION_SCHEMA,
        "action": file_provider.CAMPAIGN_AUTHORIZATION_ACTION,
        "campaign_id": plan["campaign_id"],
        "attempt_prefix": plan["attempt_prefix"],
        "authorized_by": plan["authorization_principal"],
        "issued_at": "2026-07-28T12:00:00Z",
        "expires_at": "2026-07-29T00:00:00Z",
        "item_set_sha256": file_provider._campaign_item_set_sha256(plan["item_hashes"]),
        "item_count": len(plan["item_hashes"]),
        "item_hashes": plan["item_hashes"],
        "max_batch_items": file_provider.MAX_BATCH_ITEMS,
        "max_batch_timeout_seconds": plan["timeout_seconds"],
        "max_item_timeout_seconds": plan["per_item_timeout_seconds"],
        "max_attempts": max_attempts,
    }
    return canonical_bytes(value) + b"\n"


def _standing_authorization(plan: dict[str, Any]) -> bytes:
    value = {
        "schema": file_provider.STANDING_AUTHORIZATION_SCHEMA,
        "action": file_provider.CAMPAIGN_AUTHORIZATION_ACTION,
        "attempt_prefix": plan["attempt_prefix"],
        "authorized_by": plan["authorization_principal"],
        "issued_at": "2026-07-28T12:00:00Z",
        "item_set_sha256": file_provider._campaign_item_set_sha256(plan["item_hashes"]),
        "item_count": len(plan["item_hashes"]),
        "item_hashes": plan["item_hashes"],
        "max_batch_items": file_provider.MAX_BATCH_ITEMS,
        "max_batch_timeout_seconds": plan["timeout_seconds"],
        "max_item_timeout_seconds": plan["per_item_timeout_seconds"],
        "signature_subject_b64": None,
        "revoked_at": None,
    }
    value["authority_id"] = file_provider._standing_authority_id(value)
    return canonical_bytes(value) + b"\n"


def _success_receipt(manifest: dict[str, Any], statuses: list[str]) -> bytes:
    authorization = base64.b64decode(manifest["authorization"]["receipt_b64"])
    items = [
        {
            "item_hash": request["item_hash"],
            "status": status,
            "provider_item_hash": "d" * 64,
            "domain_hash": "e" * 64,
        }
        for request, status in zip(manifest["items"], statuses)
    ]
    counts = {status: sum(item["status"] == status for item in items) for status in file_provider.ITEM_STATUSES}
    value = {
        "schema": file_provider.RECEIPT_SCHEMA,
        "attempt_id": manifest["attempt_id"],
        "manifest_hash": file_provider._manifest_hash(manifest),
        "authorization_sha256": hashlib.sha256(authorization).hexdigest(),
        "authorized_by": manifest["authorization_principal"],
        "started_at": "2026-07-25T05:01:00Z",
        "completed_at": "2026-07-25T05:02:00Z",
        "status": "succeeded",
        "item_count": len(items),
        "result_counts": counts,
        "items": items,
    }
    return canonical_bytes(value) + b"\n"


def _plan(
    monkeypatch: pytest.MonkeyPatch,
    receipt: MetabolismReceipt,
    captured: tuple,
    root: Path,
    progress: Path,
    authorization: Path,
    probe,
) -> dict[str, Any]:
    planned: dict[str, Any] = {}

    def run(_executable: Path, manifest: dict[str, Any], *, plan: bool):
        assert plan
        planned.update(manifest)
        return 0, _authorization(manifest)

    monkeypatch.setattr(file_provider, "_discover_adapter", lambda _name: Path("/bin/true"))
    monkeypatch.setattr(file_provider, "_run_adapter", run)
    result = file_provider.process_file_provider_items(
        receipt,
        root,
        captured,
        progress,
        prepare_authorization=authorization,
        authorization_principal="test-authorizer",
        materialized_probe=probe,
    )
    assert result.authorization_prepared
    return planned


def test_signed_batch_is_private_resumable_and_accounts_for_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, captured, root = _captured(tmp_path, (".DS_Store", "one.txt", "two.mov"))
    progress = tmp_path / "progress.json"
    authorization = tmp_path / "authorization.json"
    signature = tmp_path / "authorization.json.sig"
    dataless: set[str] = set()

    def probe(path: Path) -> bool:
        return hashlib.sha256(path.absolute().as_uri().encode()).hexdigest() not in dataless

    planned = _plan(monkeypatch, receipt, captured, root, progress, authorization, probe)
    assert len(planned["items"]) == 2
    assert all(item["url"].startswith("file://") for item in planned["items"])
    assert str(root).encode() not in authorization.read_bytes()
    assert str(root).encode() not in progress.read_bytes()
    signature.write_bytes(b"fake-openssh-signature")
    signature.chmod(0o600)

    def apply(_executable: Path, manifest: dict[str, Any], *, plan: bool):
        assert not plan
        dataless.update(item["item_hash"] for item in manifest["items"])
        return 0, _success_receipt(manifest, ["evicted"] * len(manifest["items"]))

    monkeypatch.setattr(file_provider, "_run_adapter", apply)
    result = file_provider.process_file_provider_items(
        receipt,
        root,
        captured,
        progress,
        authorization_receipt=authorization,
        authorization_signature=signature,
        materialized_probe=probe,
    )

    assert result.complete
    assert result.evicted_files == 2
    assert result.retained_non_evictable_files == 1
    assert result.remaining_files == 0
    assert str(root).encode() not in progress.read_bytes()


def test_missing_adapter_fails_closed_before_writing_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, captured, root = _captured(tmp_path, ("one.txt",))
    progress = tmp_path / "progress.json"
    authorization = tmp_path / "authorization.json"
    monkeypatch.setattr(file_provider.shutil, "which", lambda _name: None)

    with pytest.raises(PipelineError, match="absent from PATH"):
        file_provider.process_file_provider_items(
            receipt,
            root,
            captured,
            progress,
            prepare_authorization=authorization,
            authorization_principal="test-authorizer",
            materialized_probe=lambda _path: True,
        )

    assert not progress.exists()
    assert not authorization.exists()


def test_restore_missing_item_from_fully_verified_atoms(tmp_path: Path) -> None:
    receipt, root, payload = _encrypted_capture(tmp_path, ("missing.json", "other.txt"))
    target = root / "missing.json"
    expected = target.read_bytes()
    before = target.stat()
    item_hash = file_provider.file_provider_item_hash(root, "missing.json")
    target.unlink()

    restored = file_provider.restore_captured_file(
        receipt,
        root,
        payload,
        "restore-test-key",
        item_hash,
    )

    assert restored.status == "restored"
    assert target.read_bytes() == expected
    assert target.stat().st_mtime_ns == before.st_mtime_ns
    assert target.stat().st_mode & 0o777 == before.st_mode & 0o777
    repeated = file_provider.restore_captured_file(
        receipt,
        root,
        payload,
        "restore-test-key",
        item_hash,
    )
    assert repeated.status == "already_restored"


def test_restore_missing_item_by_captured_path_hash_is_path_free(tmp_path: Path) -> None:
    relative = "private/missing.json"
    receipt, root, payload = _encrypted_capture(tmp_path, (relative, "other.txt"))
    target = root / relative
    expected = target.read_bytes()
    selector_hash = file_provider.captured_path_selector_hash(relative)
    target.unlink()

    restored = file_provider.restore_captured_file(
        receipt,
        root,
        payload,
        "restore-test-key",
        captured_path_hash=selector_hash,
    )

    assert restored.status == "restored"
    assert restored.selector_kind == "captured_path_hash"
    assert restored.selector_hash == selector_hash
    assert restored.item_hash == file_provider.file_provider_item_hash(root, relative)
    assert target.read_bytes() == expected
    assert relative not in repr(restored)


def test_restore_missing_item_by_unique_captured_name_hash(tmp_path: Path) -> None:
    relative = "private/nested/missing.json"
    receipt, root, payload = _encrypted_capture(tmp_path, (relative, "other.txt"))
    target = root / relative
    expected = target.read_bytes()
    selector_hash = file_provider.captured_name_selector_hash(relative)
    target.unlink()

    restored = file_provider.restore_captured_file(
        receipt,
        root,
        payload,
        "restore-test-key",
        captured_name_hash=selector_hash,
    )

    assert restored.status == "restored"
    assert restored.selector_kind == "captured_name_hash"
    assert restored.selector_hash == selector_hash
    assert target.read_bytes() == expected
    assert relative not in repr(restored)


def test_restore_name_hash_rejects_duplicate_basenames(tmp_path: Path) -> None:
    first = "one/duplicate.json"
    second = "two/duplicate.json"
    receipt, root, payload = _encrypted_capture(tmp_path, (first, second))
    (root / first).unlink()
    (root / second).unlink()

    with pytest.raises(PipelineError, match="selector does not identify"):
        file_provider.restore_captured_file(
            receipt,
            root,
            payload,
            "restore-test-key",
            captured_name_hash=file_provider.captured_name_selector_hash(first),
        )

    assert not (root / first).exists()
    assert not (root / second).exists()


def test_restore_selector_mismatch_stops_before_chunk_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = "missing.json"
    receipt, root, payload = _encrypted_capture(tmp_path, (relative,))
    target = root / relative
    target.unlink()
    verification_calls = 0
    real_verify = file_provider.verify_atom_packs

    def verify(*args, **kwargs):
        nonlocal verification_calls
        verification_calls += 1
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(file_provider, "verify_atom_packs", verify)

    with pytest.raises(PipelineError, match="selector does not identify"):
        file_provider.restore_captured_file(
            receipt,
            root,
            payload,
            "restore-test-key",
            captured_path_hash="f" * 64,
        )

    assert verification_calls == 1
    assert not target.exists()


def test_restore_receipt_preflight_can_stop_before_target_mutation(tmp_path: Path) -> None:
    relative = "private/missing.json"
    receipt, root, payload = _encrypted_capture(tmp_path, (relative,))
    target = root / relative
    target.unlink()

    def reject(_result: file_provider.RestoredFileResult) -> None:
        raise PipelineError("restore receipt conflicts")

    with pytest.raises(PipelineError, match="receipt conflicts"):
        file_provider.restore_captured_file(
            receipt,
            root,
            payload,
            "restore-test-key",
            captured_path_hash=file_provider.captured_path_selector_hash(relative),
            before_mutation=reject,
        )

    assert not target.exists()


def test_restore_parent_replacement_cannot_redirect_placement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = "private/missing.json"
    receipt, root, payload = _encrypted_capture(tmp_path, (relative,))
    target = root / relative
    target.unlink()
    outside = tmp_path / "outside"
    outside.mkdir()
    displaced = root / "displaced"
    verification_calls = 0
    real_verify = file_provider.verify_atom_packs

    def verify(*args, **kwargs):
        nonlocal verification_calls
        verification_calls += 1
        if verification_calls == 2:
            target.parent.rename(displaced)
            target.parent.symlink_to(outside, target_is_directory=True)
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(file_provider, "verify_atom_packs", verify)

    with pytest.raises(PipelineError, match="parent changed during reconstruction"):
        file_provider.restore_captured_file(
            receipt,
            root,
            payload,
            "restore-test-key",
            captured_path_hash=file_provider.captured_path_selector_hash(relative),
        )

    assert not (outside / target.name).exists()
    assert not (displaced / target.name).exists()


def test_restore_operational_failure_is_path_free_pipeline_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = "private/missing.json"
    receipt, root, payload = _encrypted_capture(tmp_path, (relative,))
    target = root / relative
    target.unlink()

    def deny_link(*_args, **_kwargs):
        raise PermissionError(1, "denied", str(target))

    monkeypatch.setattr(file_provider.os, "link", deny_link)
    with pytest.raises(PipelineError, match="restore placement failed") as raised:
        file_provider.restore_captured_file(
            receipt,
            root,
            payload,
            "restore-test-key",
            captured_path_hash=file_provider.captured_path_selector_hash(relative),
        )

    assert str(target) not in str(raised.value)
    assert not target.exists()


def test_restore_rejects_existing_conflicting_content(tmp_path: Path) -> None:
    receipt, root, payload = _encrypted_capture(tmp_path, ("captured.json",))
    target = root / "captured.json"
    before = target.stat()
    original = target.read_bytes()
    target.write_bytes(b"x" * len(original))
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))

    with pytest.raises(PipelineError, match="conflicting content"):
        file_provider.restore_captured_file(
            receipt,
            root,
            payload,
            "restore-test-key",
            file_provider.file_provider_item_hash(root, "captured.json"),
        )

    assert target.read_bytes() == b"x" * len(original)


def test_restore_recognizes_exact_dataless_item_without_opening_content(tmp_path: Path) -> None:
    receipt, root, payload = _encrypted_capture(tmp_path, ("placeholder.json",))

    restored = file_provider.restore_captured_file(
        receipt,
        root,
        payload,
        "restore-test-key",
        file_provider.file_provider_item_hash(root, "placeholder.json"),
        materialized_probe=lambda _path: False,
    )

    assert restored.status == "already_dataless"


def test_adapter_process_arguments_never_contain_item_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "file:///private/disposable-item.txt"
    manifest = {
        "schema": file_provider.MANIFEST_SCHEMA,
        "attempt_id": "attempt-1",
        "timeout_seconds": file_provider.BATCH_TIMEOUT_SECONDS,
        "per_item_timeout_seconds": file_provider.ITEM_TIMEOUT_SECONDS,
        "authorization_principal": "test-authorizer",
        "items": [{"item_hash": hashlib.sha256(url.encode()).hexdigest(), "url": url}],
    }
    observed: dict[str, Any] = {}

    class Result:
        returncode = 0
        stdout = b"{}\n"

    def run(arguments, **kwargs):
        observed["arguments"] = arguments
        observed["input"] = kwargs["input"]
        return Result()

    monkeypatch.setattr(file_provider.subprocess, "run", run)
    file_provider._run_adapter(Path("/bin/true"), manifest, plan=True)

    assert url not in " ".join(observed["arguments"])
    assert url.encode() in observed["input"]


def test_dataless_placeholder_is_verified_by_adapter_as_already_reclaimed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, captured, root = _captured(tmp_path, ("placeholder.txt",))
    progress = tmp_path / "progress.json"
    authorization = tmp_path / "authorization.json"
    signature = tmp_path / "authorization.json.sig"
    planned = _plan(
        monkeypatch,
        receipt,
        captured,
        root,
        progress,
        authorization,
        lambda _path: False,
    )
    assert len(planned["items"]) == 1
    signature.write_bytes(b"fake-openssh-signature")
    signature.chmod(0o600)

    def apply(_executable: Path, manifest: dict[str, Any], *, plan: bool):
        assert not plan
        return 0, _success_receipt(manifest, ["already_dataless"])

    monkeypatch.setattr(file_provider, "_run_adapter", apply)
    result = file_provider.process_file_provider_items(
        receipt,
        root,
        captured,
        progress,
        authorization_receipt=authorization,
        authorization_signature=signature,
        materialized_probe=lambda _path: False,
    )

    assert result.complete
    assert result.already_reclaimed_files == 1


def test_only_retained_metadata_reaches_terminal_state_without_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, captured, root = _captured(tmp_path, (".DS_Store",))
    monkeypatch.setattr(
        file_provider,
        "_discover_adapter",
        lambda _name: (_ for _ in ()).throw(AssertionError("adapter must not be discovered")),
    )

    result = file_provider.process_file_provider_items(
        receipt,
        root,
        captured,
        tmp_path / "progress.json",
        materialized_probe=lambda _path: True,
    )

    assert result.complete
    assert result.selected_files == 0
    assert result.retained_non_evictable_files == 1


@pytest.mark.parametrize("mutation", ["missing", "content"])
def test_missing_or_mutated_source_fails_before_adapter(
    mutation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, captured, root = _captured(tmp_path, ("one.txt",))
    source = root / "one.txt"
    if mutation == "missing":
        source.unlink()
    else:
        before = source.stat()
        source.write_bytes(b"changed-0000")
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("adapter must not run")

    monkeypatch.setattr(file_provider, "_discover_adapter", lambda _name: Path("/bin/true"))
    monkeypatch.setattr(file_provider, "_run_adapter", unexpected)
    match = "logically missing" if mutation == "missing" else "content mutated"
    with pytest.raises(PipelineError, match=match):
        file_provider.process_file_provider_items(
            receipt,
            root,
            captured,
            tmp_path / "progress.json",
            prepare_authorization=tmp_path / "authorization.json",
            authorization_principal="test-authorizer",
            materialized_probe=lambda _path: True,
        )
    assert not called


def test_partial_receipt_persists_success_and_next_plan_skips_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, captured, root = _captured(tmp_path, ("one.txt", "three.txt", "two.txt"))
    progress = tmp_path / "progress.json"
    authorization = tmp_path / "authorization.json"
    signature = tmp_path / "authorization.json.sig"
    dataless: set[str] = set()

    def probe(path: Path) -> bool:
        return hashlib.sha256(path.absolute().as_uri().encode()).hexdigest() not in dataless

    first_plan = _plan(monkeypatch, receipt, captured, root, progress, authorization, probe)
    first_hash = first_plan["items"][0]["item_hash"]
    signature.write_bytes(b"fake-openssh-signature")
    signature.chmod(0o600)

    def partial(_executable: Path, manifest: dict[str, Any], *, plan: bool):
        assert not plan
        dataless.add(manifest["items"][0]["item_hash"])
        items = [
            {
                "item_hash": manifest["items"][0]["item_hash"],
                "status": "evicted",
                "provider_item_hash": "d" * 64,
                "domain_hash": "e" * 64,
            },
            {
                "item_hash": manifest["items"][1]["item_hash"],
                "status": "retained",
                "provider_item_hash": "d" * 64,
                "domain_hash": "e" * 64,
                "error": {"category": "nonevictable", "domain": "NSFileProviderErrorDomain", "code": -2008},
            },
            {
                "item_hash": manifest["items"][2]["item_hash"],
                "status": "failed",
                "error": {"category": "not_attempted_after_failure", "domain": "domus", "code": 1},
            },
        ]
        authorization_bytes = base64.b64decode(manifest["authorization"]["receipt_b64"])
        counts = {status: sum(item["status"] == status for item in items) for status in file_provider.ITEM_STATUSES}
        value = {
            "schema": file_provider.RECEIPT_SCHEMA,
            "attempt_id": manifest["attempt_id"],
            "manifest_hash": file_provider._manifest_hash(manifest),
            "authorization_sha256": hashlib.sha256(authorization_bytes).hexdigest(),
            "authorized_by": manifest["authorization_principal"],
            "started_at": "2026-07-25T05:01:00Z",
            "completed_at": "2026-07-25T05:02:00Z",
            "status": "partial_failure",
            "item_count": 3,
            "result_counts": counts,
            "items": items,
        }
        return 2, canonical_bytes(value) + b"\n"

    monkeypatch.setattr(file_provider, "_run_adapter", partial)
    with pytest.raises(PipelineError, match="partial or failed"):
        file_provider.process_file_provider_items(
            receipt,
            root,
            captured,
            progress,
            authorization_receipt=authorization,
            authorization_signature=signature,
            materialized_probe=probe,
        )

    second_authorization = tmp_path / "authorization-2.json"
    second_plan = _plan(monkeypatch, receipt, captured, root, progress, second_authorization, probe)
    assert first_hash not in [item["item_hash"] for item in second_plan["items"]]


def test_authorization_plan_is_capped_at_one_thousand_items(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = tuple(f"item-{index:04d}.txt" for index in range(1_001))
    receipt, captured, root = _captured(tmp_path, names)
    planned = _plan(
        monkeypatch,
        receipt,
        captured,
        root,
        tmp_path / "progress.json",
        tmp_path / "authorization.json",
        lambda _path: True,
    )

    assert len(planned["items"]) == file_provider.MAX_BATCH_ITEMS


def test_content_verification_has_a_process_deadline_without_path_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _receipt, captured, root = _captured(tmp_path, ("one.txt",))
    items = file_provider.inspect_captured_files(
        root,
        captured,
        materialized_probe=lambda _path: True,
    )
    observed: dict[str, object] = {}

    def stalled(args, **kwargs):
        observed["args"] = args
        observed["timeout"] = kwargs["timeout"]
        observed["input"] = kwargs["input"]
        raise file_provider.subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(file_provider.subprocess, "run", stalled)

    with pytest.raises(
        PipelineError,
        match="exceeded its bounded deadline",
    ):
        file_provider.verify_materialized_content(
            items,
            timeout_seconds=7,
        )

    assert observed["timeout"] == 7
    assert str(root) not in " ".join(observed["args"])
    assert str(root).encode() in observed["input"]


def test_one_campaign_authorization_advances_multiple_batches_without_replanning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_provider, "MAX_BATCH_ITEMS", 2)
    receipt, captured, root = _captured(
        tmp_path,
        ("one.txt", "three.txt", "two.txt"),
    )
    progress = tmp_path / "progress.json"
    authorization = tmp_path / "campaign-authorization.json"
    signature = tmp_path / "campaign-authorization.json.sig"
    dataless: set[str] = set()
    planned: dict[str, Any] = {}

    def probe(path: Path) -> bool:
        return hashlib.sha256(path.absolute().as_uri().encode()).hexdigest() not in dataless

    def plan_campaign(
        _executable: Path,
        manifest: dict[str, Any],
        *,
        plan: bool,
        campaign: bool = False,
    ):
        assert not plan and campaign
        planned.update(manifest)
        return 0, _standing_authorization(manifest)

    monkeypatch.setattr(file_provider, "_discover_adapter", lambda _name: Path("/bin/true"))
    monkeypatch.setattr(file_provider, "_run_adapter", plan_campaign)
    result = file_provider.process_file_provider_items(
        receipt,
        root,
        captured,
        progress,
        prepare_campaign_authorization=authorization,
        authorization_principal="test-authorizer",
        materialized_probe=probe,
    )

    assert result.authorization_prepared
    assert planned["item_hashes"] == [
        file_provider.file_provider_item_hash(root, name) for name in ("one.txt", "three.txt", "two.txt")
    ]
    assert str(root).encode() not in authorization.read_bytes()
    assert str(root).encode() not in progress.read_bytes()
    signature.write_bytes(b"fake-openssh-signature")
    signature.chmod(0o600)
    attempts: list[str] = []
    authorization_hashes: list[str] = []

    def apply(
        _executable: Path,
        manifest: dict[str, Any],
        *,
        plan: bool,
        campaign: bool = False,
    ):
        assert not plan and not campaign
        attempts.append(manifest["attempt_id"])
        authorization_bytes = base64.b64decode(manifest["authorization"]["receipt_b64"])
        authorization_hashes.append(hashlib.sha256(authorization_bytes).hexdigest())
        dataless.update(item["item_hash"] for item in manifest["items"])
        return 0, _success_receipt(manifest, ["evicted"] * len(manifest["items"]))

    monkeypatch.setattr(file_provider, "_run_adapter", apply)
    first = file_provider.process_file_provider_items(
        receipt,
        root,
        captured,
        progress,
        authorization_receipt=authorization,
        authorization_signature=signature,
        materialized_probe=probe,
    )
    second = file_provider.process_file_provider_items(
        receipt,
        root,
        captured,
        progress,
        authorization_receipt=authorization,
        authorization_signature=signature,
        materialized_probe=probe,
    )

    assert first.remaining_files == 1
    assert second.complete
    assert attempts == ["limen-run-0001-000000", "limen-run-0001-000001"]
    assert len(set(authorization_hashes)) == 1
    progress_value = json.loads(progress.read_bytes())
    assert progress_value["pending_batch"] is None
    assert progress_value["next_attempt"] == 2
    assert len(progress_value["receipts"]) == 2


def test_campaign_authorization_rejects_hash_outside_immutable_custody(
    tmp_path: Path,
) -> None:
    receipt, captured, root = _captured(tmp_path, ("one.txt", "two.txt"))
    items = file_provider.inspect_captured_files(
        root,
        captured,
        materialized_probe=lambda _path: True,
    )
    eligible_hashes = [item.item_hash for item in items]
    plan = file_provider._campaign_plan(receipt, eligible_hashes, principal="test-authorizer")
    authorization = json.loads(_standing_authorization(plan))
    authorization["item_hashes"][0] = "f" * 64
    authorization["item_set_sha256"] = file_provider._campaign_item_set_sha256(authorization["item_hashes"])

    with pytest.raises(PipelineError, match="does not bind immutable custody"):
        file_provider._validate_standing_authorization(
            canonical_bytes(authorization) + b"\n",
            receipt,
            eligible_hashes,
        )


def test_campaign_batch_may_narrow_but_not_widen_signed_timeout_caps(
    tmp_path: Path,
) -> None:
    receipt, captured, root = _captured(tmp_path, ("one.txt",))
    items = file_provider.inspect_captured_files(
        root,
        captured,
        materialized_probe=lambda _path: True,
    )
    plan = file_provider._campaign_plan(
        receipt,
        [item.item_hash for item in items],
        principal="test-authorizer",
    )
    authorization = json.loads(_standing_authorization(plan))
    manifest = file_provider._manifest(
        items,
        attempt_id="limen-run-0001-000000",
        principal="test-authorizer",
    )
    manifest["timeout_seconds"] -= 1
    manifest["per_item_timeout_seconds"] -= 1

    file_provider._validate_standing_batch(authorization, manifest)
    manifest["timeout_seconds"] = authorization["max_batch_timeout_seconds"] + 1
    with pytest.raises(PipelineError, match="exceeds the standing authority"):
        file_provider._validate_standing_batch(authorization, manifest)


def test_standing_authority_has_no_attempt_bound_and_legacy_receipt_migrates(
    tmp_path: Path,
) -> None:
    receipt, captured, root = _captured(tmp_path, ("one.txt",))
    items = file_provider.inspect_captured_files(root, captured, materialized_probe=lambda _path: True)
    plan = file_provider._campaign_plan(
        receipt,
        [item.item_hash for item in items],
        principal="test-authorizer",
    )
    legacy = _legacy_campaign_authorization(plan, max_attempts=1)
    authority = file_provider._validate_standing_authorization(
        legacy,
        receipt,
        plan["item_hashes"],
    )

    assert "expires_at" not in authority
    assert "max_attempts" not in authority
    assert authority["signature_subject_b64"] is not None
    for ordinal in range(300):
        manifest = file_provider._manifest(
            items,
            attempt_id=f"{authority['attempt_prefix']}{ordinal:06d}",
            principal=authority["authorized_by"],
        )
        file_provider._validate_standing_batch(authority, manifest)
