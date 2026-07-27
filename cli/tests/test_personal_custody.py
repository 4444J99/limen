from __future__ import annotations

import json
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
    return lambda path: identities[path.resolve()]


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
