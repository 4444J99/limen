from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from limen import personal_custody as custody


def _volume(path: Path, *, device: str, physical: str, uuid: str) -> custody.VolumeIdentity:
    return custody.VolumeIdentity(
        mount=str(path.resolve()),
        device=device,
        physical_device=physical,
        volume_uuid=uuid,
    )


def _fixture(
    tmp_path: Path,
) -> tuple[
    Path,
    Path,
    Path,
    Path,
    dict[Path, custody.VolumeIdentity],
]:
    source = tmp_path / "home" / "Desktop"
    source.mkdir(parents=True)
    (source / "document.txt").write_text("unique document\n", encoding="utf-8")
    nested = source / "nested"
    nested.mkdir()
    (nested / "photo.bin").write_bytes(b"\0private\1" * 1024)
    (source / "link").symlink_to("document.txt")
    archive = tmp_path / "Archive4T"
    recovery = tmp_path / "T7Recovery"
    archive.mkdir()
    recovery.mkdir()
    archive_identity = _volume(
        archive,
        device="/dev/disk5s1",
        physical="/dev/disk4",
        uuid="ARCHIVE-UUID",
    )
    recovery_identity = _volume(
        recovery,
        device="/dev/disk7s1",
        physical="/dev/disk6",
        uuid="RECOVERY-UUID",
    )
    inventory = {
        "schema": "limen.storage_evacuation_inventory.v1",
        "inventory_id": "fixture-inventory",
        "frozen_at": "2026-07-27T00:00:00Z",
        "custody_devices": [
            {
                "name": "Archive4T",
                "device": archive_identity.device,
                "physical_device": archive_identity.physical_device,
                "volume_uuid": archive_identity.volume_uuid,
            },
            {
                "name": "T7Recovery",
                "device": recovery_identity.device,
                "physical_device": recovery_identity.physical_device,
                "volume_uuid": recovery_identity.volume_uuid,
            },
        ],
        "roots": [
            {
                "root": str(source),
                "size_bytes": 8192,
                "owner": "personal-bulk-custody",
                "gate": "two_independent_copies_and_restore",
            }
        ],
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    return (
        source,
        archive,
        recovery,
        inventory_path,
        {
            archive.resolve(): archive_identity,
            recovery.resolve(): recovery_identity,
        },
    )


def _probe(
    identities: dict[Path, custody.VolumeIdentity],
) -> custody.VolumeProbe:
    def probe(path: Path) -> custody.VolumeIdentity:
        resolved = path.resolve()
        for mount, identity in identities.items():
            if resolved == mount or mount in resolved.parents:
                return identity
        raise KeyError(resolved)

    return probe


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True, copy_function=shutil.copy2)


def _plan(
    tmp_path: Path,
) -> tuple[
    dict[str, object],
    Path,
    Path,
    Path,
    Path,
    dict[Path, custody.VolumeIdentity],
]:
    source, archive, recovery, inventory, identities = _fixture(tmp_path)
    result = custody.create_plan(
        inventory_path=inventory,
        label="desktop",
        source=source,
        archive_root=archive,
        recovery_root=recovery,
        private_root=Path("evacuation"),
        require_volume=False,
        volume_probe=_probe(identities),
    )
    return result, source, archive, recovery, inventory, identities


def test_two_drive_plan_apply_restore_and_exact_reclaim(tmp_path: Path) -> None:
    plan_result, source, archive, recovery, _inventory, identities = _plan(tmp_path)
    plan_sha256 = str(plan_result["plan_sha256"])
    plan_path = Path(str(plan_result["archive_plan"]))
    public_receipts = tmp_path / "public.jsonl"

    applied = custody.apply_plan(
        plan_path=plan_path,
        expected_plan_sha256=plan_sha256,
        public_receipt_path=public_receipts,
        require_volume=False,
        volume_probe=_probe(identities),
        copy_tree=_copy_tree,
    )

    assert applied["copy_count"] == 2
    assert applied["independent_physical_devices"] is True
    assert applied["restoration_passed"] is True
    assert source.exists()
    content_sha256 = str(applied["content_sha256"])
    assert (archive / "evacuation" / "objects" / "desktop" / content_sha256).is_dir()
    assert (recovery / "evacuation" / "objects" / "desktop" / content_sha256).is_dir()

    reclaimed = custody.reclaim_plan(
        plan_path=plan_path,
        expected_plan_sha256=plan_sha256,
        public_receipt_path=public_receipts,
        require_volume=False,
        volume_probe=_probe(identities),
        owner_probe=lambda _path: None,
    )

    assert reclaimed["reclaimed"] is True
    assert not source.exists()
    events = [json.loads(line)["event"] for line in public_receipts.read_text().splitlines()]
    assert events == ["custody_restored", "internal_copy_reclaimed"]


def test_stale_plan_hash_and_source_drift_fail_closed(tmp_path: Path) -> None:
    plan_result, source, _archive, _recovery, _inventory, identities = _plan(tmp_path)
    plan_path = Path(str(plan_result["archive_plan"]))
    plan_sha256 = str(plan_result["plan_sha256"])

    with pytest.raises(custody.PersonalCustodyError, match="custody-plan-sha-mismatch"):
        custody.apply_plan(
            plan_path=plan_path,
            expected_plan_sha256="0" * 64,
            require_volume=False,
            volume_probe=_probe(identities),
            copy_tree=_copy_tree,
        )

    (source / "document.txt").write_text("changed after plan\n", encoding="utf-8")
    with pytest.raises(custody.PersonalCustodyError, match="custody-content-drift"):
        custody.apply_plan(
            plan_path=plan_path,
            expected_plan_sha256=plan_sha256,
            require_volume=False,
            volume_probe=_probe(identities),
            copy_tree=_copy_tree,
        )
    assert source.exists()


def test_same_physical_device_is_not_a_second_copy(tmp_path: Path) -> None:
    source, archive, recovery, inventory_path, identities = _fixture(tmp_path)
    recovery_identity = identities[recovery.resolve()]
    identities[recovery.resolve()] = custody.VolumeIdentity(
        mount=recovery_identity.mount,
        device=recovery_identity.device,
        physical_device=identities[archive.resolve()].physical_device,
        volume_uuid=recovery_identity.volume_uuid,
    )
    inventory = json.loads(inventory_path.read_text())
    inventory["custody_devices"][1]["physical_device"] = identities[recovery.resolve()].physical_device
    inventory_path.write_text(json.dumps(inventory))

    with pytest.raises(
        custody.PersonalCustodyError,
        match="custody-volumes-share-physical-device",
    ):
        custody.create_plan(
            inventory_path=inventory_path,
            label="desktop",
            source=source,
            archive_root=archive,
            recovery_root=recovery,
            private_root=Path("evacuation"),
            require_volume=False,
            volume_probe=_probe(identities),
        )


def test_symlinked_content_addressed_destination_fails_closed(
    tmp_path: Path,
) -> None:
    plan_result, source, archive, _recovery, _inventory, identities = _plan(tmp_path)
    destination = archive / "evacuation" / "objects" / "desktop" / str(plan_result["content_sha256"])
    destination.parent.mkdir(parents=True)
    destination.symlink_to(source, target_is_directory=True)

    with pytest.raises(
        custody.PersonalCustodyError,
        match="custody-object-path-symlink",
    ):
        custody.apply_plan(
            plan_path=Path(str(plan_result["archive_plan"])),
            expected_plan_sha256=str(plan_result["plan_sha256"]),
            require_volume=False,
            volume_probe=_probe(identities),
            copy_tree=_copy_tree,
        )
    assert source.exists()


def test_materialized_object_must_remain_on_planned_volume(
    tmp_path: Path,
) -> None:
    plan_result, source, archive, recovery, _inventory, identities = _plan(tmp_path)
    ordinary_probe = _probe(identities)

    def drifting_probe(path: Path) -> custody.VolumeIdentity:
        resolved = path.resolve()
        if archive.resolve() in resolved.parents:
            return identities[recovery.resolve()]
        return ordinary_probe(path)

    with pytest.raises(
        custody.PersonalCustodyError,
        match="custody-object-volume-identity-drift",
    ):
        custody.apply_plan(
            plan_path=Path(str(plan_result["archive_plan"])),
            expected_plan_sha256=str(plan_result["plan_sha256"]),
            require_volume=False,
            volume_probe=drifting_probe,
            copy_tree=_copy_tree,
        )
    assert source.exists()


def test_active_owner_blocks_reclaim_after_valid_restoration(tmp_path: Path) -> None:
    plan_result, source, _archive, _recovery, _inventory, identities = _plan(tmp_path)
    plan_path = Path(str(plan_result["archive_plan"]))
    plan_sha256 = str(plan_result["plan_sha256"])
    custody.apply_plan(
        plan_path=plan_path,
        expected_plan_sha256=plan_sha256,
        require_volume=False,
        volume_probe=_probe(identities),
        copy_tree=_copy_tree,
    )

    with pytest.raises(custody.PersonalCustodyError, match="custody-reclaim-denied"):
        custody.reclaim_plan(
            plan_path=plan_path,
            expected_plan_sha256=plan_sha256,
            require_volume=False,
            volume_probe=_probe(identities),
            owner_probe=lambda _path: 4242,
        )
    assert source.exists()


def test_contents_reclaim_retains_empty_standard_folder(tmp_path: Path) -> None:
    source, archive, recovery, inventory, identities = _fixture(tmp_path)
    plan_result = custody.create_plan(
        inventory_path=inventory,
        label="downloads",
        source=source,
        archive_root=archive,
        recovery_root=recovery,
        private_root=Path("evacuation"),
        reclaim_mode="contents",
        require_volume=False,
        volume_probe=_probe(identities),
    )
    plan_path = Path(str(plan_result["archive_plan"]))
    plan_sha256 = str(plan_result["plan_sha256"])
    custody.apply_plan(
        plan_path=plan_path,
        expected_plan_sha256=plan_sha256,
        require_volume=False,
        volume_probe=_probe(identities),
        copy_tree=_copy_tree,
    )

    receipt = custody.reclaim_plan(
        plan_path=plan_path,
        expected_plan_sha256=plan_sha256,
        require_volume=False,
        volume_probe=_probe(identities),
        owner_probe=lambda _path: None,
    )

    assert receipt["reclaim_mode"] == "contents"
    assert source.is_dir()
    assert list(source.iterdir()) == []
    repeated = custody.reclaim_plan(
        plan_path=plan_path,
        expected_plan_sha256=plan_sha256,
        require_volume=False,
        volume_probe=_probe(identities),
        owner_probe=lambda _path: None,
    )
    assert repeated["receipt_sha256"] == receipt["receipt_sha256"]


@pytest.mark.parametrize("completed_writes", [0, 1])
def test_post_purge_receipt_write_crash_recovers_without_repurging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    completed_writes: int,
) -> None:
    plan_result, source, _archive, _recovery, _inventory, identities = _plan(tmp_path)
    plan_path = Path(str(plan_result["archive_plan"]))
    plan_sha256 = str(plan_result["plan_sha256"])
    custody.apply_plan(
        plan_path=plan_path,
        expected_plan_sha256=plan_sha256,
        require_volume=False,
        volume_probe=_probe(identities),
        copy_tree=_copy_tree,
    )
    real_write_pair = custody._write_receipt_pair

    def interrupt_completed(
        archive_path: Path,
        recovery_path: Path,
        payload: dict[str, object],
    ) -> None:
        if payload.get("status") != "reclaimed":
            real_write_pair(archive_path, recovery_path, payload)
            return
        if completed_writes:
            custody._atomic_json(archive_path, payload)
        raise custody.PersonalCustodyError("simulated-post-purge-crash")

    monkeypatch.setattr(custody, "_write_receipt_pair", interrupt_completed)
    with pytest.raises(custody.PersonalCustodyError, match="simulated-post-purge-crash"):
        custody.reclaim_plan(
            plan_path=plan_path,
            expected_plan_sha256=plan_sha256,
            require_volume=False,
            volume_probe=_probe(identities),
            owner_probe=lambda _path: None,
        )
    assert not source.exists()

    monkeypatch.setattr(custody, "_write_receipt_pair", real_write_pair)
    recovered = custody.reclaim_plan(
        plan_path=plan_path,
        expected_plan_sha256=plan_sha256,
        require_volume=False,
        volume_probe=_probe(identities),
        owner_probe=lambda _path: (_ for _ in ()).throw(AssertionError("recovery must not attempt a second purge")),
    )

    assert recovered["reclaimed"] is True
    assert not source.exists()


def test_special_file_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    fifo = source / "pipe"
    fifo.parent.mkdir(exist_ok=True)
    try:
        fifo.touch()
        fifo.unlink()
        fifo_path = str(fifo)
        import os

        os.mkfifo(fifo_path)
        with pytest.raises(custody.PersonalCustodyError, match="source-special-file"):
            custody.content_records(source)
    finally:
        fifo.unlink(missing_ok=True)


@pytest.mark.parametrize("private_root", [Path("/absolute"), Path("../escape"), Path(".")])
def test_private_root_must_be_safe_and_relative(tmp_path: Path, private_root: Path) -> None:
    source, archive, recovery, inventory, identities = _fixture(tmp_path)
    with pytest.raises(custody.PersonalCustodyError, match="private-root-"):
        custody.create_plan(
            inventory_path=inventory,
            label="desktop",
            source=source,
            archive_root=archive,
            recovery_root=recovery,
            private_root=private_root,
            require_volume=False,
            volume_probe=_probe(identities),
        )


def test_apply_validates_both_canonical_plan_copies(tmp_path: Path) -> None:
    plan_result, _source, _archive, recovery, _inventory, identities = _plan(tmp_path)
    plan_sha256 = str(plan_result["plan_sha256"])
    recovery_plan = Path(str(plan_result["recovery_plan"]))
    payload = json.loads(recovery_plan.read_text())
    payload["label"] = "tampered"
    recovery_plan.write_text(json.dumps(payload))

    with pytest.raises(custody.PersonalCustodyError, match="custody-plan-sha-mismatch"):
        custody.apply_plan(
            plan_path=Path(str(plan_result["archive_plan"])),
            expected_plan_sha256=plan_sha256,
            require_volume=False,
            volume_probe=_probe(identities),
            copy_tree=_copy_tree,
        )
    assert recovery.exists()


def test_public_receipt_cannot_be_reclaimed_with_source(tmp_path: Path) -> None:
    plan_result, source, _archive, _recovery, _inventory, identities = _plan(tmp_path)
    with pytest.raises(custody.PersonalCustodyError, match="public-receipt-inside-reclaimed-source"):
        custody.apply_plan(
            plan_path=Path(str(plan_result["archive_plan"])),
            expected_plan_sha256=str(plan_result["plan_sha256"]),
            public_receipt_path=source / "receipt.jsonl",
            require_volume=False,
            volume_probe=_probe(identities),
            copy_tree=_copy_tree,
        )


def test_content_manifest_includes_metadata_digests(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    document = source / "document"
    document.write_text("metadata\n")
    if hasattr(os, "setxattr"):
        try:
            os.setxattr(document, "user.limen-test", b"retained")
        except OSError:
            pass
    records = custody.content_records(source)
    assert all(record.xattrs_sha256 for record in records)
    assert all(record.acl_sha256 for record in records)
