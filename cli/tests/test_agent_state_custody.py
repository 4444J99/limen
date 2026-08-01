from __future__ import annotations

import json
import plistlib
from contextlib import nullcontext
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from limen.agent_state import custody
from limen.agent_state.crypto import encryption_profile_digest
from limen.agent_state.custody import (
    project_custody_receipt,
    run_custody_verification_campaign,
    verify_custody_restorations,
    write_custody_receipt,
)
from limen.agent_state.models import (
    AtomPack,
    CipherChunk,
    MetabolismReceipt,
    ReceiptError,
    RestoreProof,
    SourceProof,
)

LOGICAL_SHA256 = "d" * 64
PRIMARY_DEVICE = "githubRemoteDevice0001"
EXTERNAL_DEVICE = "t7RecoveryDevice0001"
RESTORED_AT = datetime(2026, 7, 29, 14, 30, tzinfo=UTC)
REMOTE_REFS = (
    "github:organvm/arca@" + "1" * 40,
    "github:organvm/arca@" + "2" * 40,
)


def metabolism_receipt(*, evidence: bool = True) -> MetabolismReceipt:
    chunk = CipherChunk(
        path="atoms-00000.jsonl.gz.enc.part-00000",
        bytes=128,
        sha256="c" * 64,
    )
    return MetabolismReceipt(
        schema="limen.agent_state_metabolism.v1",
        run_id="20260729T125700Z",
        source=SourceProof(
            path="/private/source/agent-state",
            kind="file-tree",
            bytes=64,
            sha256="a" * 64,
            stat_before=(1, 2, 3),
            stat_after=(1, 2, 3),
            inventory_before_sha256="b" * 64,
            inventory_after_sha256="b" * 64,
        ),
        atom_count=2,
        logical_sha256=LOGICAL_SHA256,
        encryption_profile_digest=encryption_profile_digest(),
        packs=[
            AtomPack(
                ordinal=0,
                atom_count=2,
                plaintext_bytes=64,
                plaintext_sha256="e" * 64,
                chunks=(chunk,),
            )
        ],
        git_remote="organvm/arca",
        git_commit="1" * 40,
        git_receipt_commit="2" * 40,
        external_chunks=[chunk],
        restorations=[
            RestoreProof(
                scope="git-sample",
                passed=True,
                atoms_verified=2,
            ),
            RestoreProof(
                scope="git-full-manifest",
                passed=True,
                atoms_verified=2,
                logical_sha256=LOGICAL_SHA256,
                device_id=PRIMARY_DEVICE if evidence else None,
                restored_at=RESTORED_AT.isoformat() if evidence else None,
                encryption_profile_digest=(encryption_profile_digest() if evidence else None),
                remote_refs=REMOTE_REFS if evidence else (),
            ),
            RestoreProof(
                scope="external-full",
                passed=True,
                atoms_verified=2,
                logical_sha256=LOGICAL_SHA256,
                device_id=EXTERNAL_DEVICE if evidence else None,
                restored_at=RESTORED_AT.isoformat() if evidence else None,
                encryption_profile_digest=(encryption_profile_digest() if evidence else None),
            ),
        ],
        retained_hot_bytes=0,
    )


def projected_receipt():
    return project_custody_receipt(metabolism_receipt())


def test_projection_is_path_free_and_binds_both_restorations() -> None:
    source = metabolism_receipt()
    projected = project_custody_receipt(source)
    payload = json.dumps(projected.model_dump(mode="json"), sort_keys=True)

    assert source.source.path not in payload
    assert projected.schema_version == "limen.custody_receipt.v1"
    assert projected.encryption_profile_digest == encryption_profile_digest()
    assert len(projected.chunk_manifest_digests) == len(source.packs) + 1
    assert projected.independent_device_ids == (
        PRIMARY_DEVICE,
        EXTERNAL_DEVICE,
    )
    assert projected.remote_refs == REMOTE_REFS
    assert {proof.custody_target_ref for proof in projected.restoration_proofs} == {
        "encrypted-git",
        "encrypted-external",
    }
    assert {proof.restored_output_digest for proof in projected.restoration_proofs} == {LOGICAL_SHA256}


def test_projection_rejects_non_independent_devices() -> None:
    receipt = metabolism_receipt()
    external = receipt.restorations[-1]
    receipt.restorations[-1] = RestoreProof(
        **{
            **asdict(external),
            "device_id": PRIMARY_DEVICE,
        }
    )

    with pytest.raises(
        ValueError,
        match="custody device identities must be independent",
    ):
        project_custody_receipt(receipt)


def test_projection_rejects_restore_digest_mismatch() -> None:
    receipt = metabolism_receipt()
    receipt.restorations[-1] = RestoreProof(
        scope="external-full",
        passed=True,
        atoms_verified=2,
        logical_sha256="f" * 64,
        device_id=EXTERNAL_DEVICE,
        restored_at=RESTORED_AT.isoformat(),
        encryption_profile_digest=encryption_profile_digest(),
    )

    with pytest.raises(
        ReceiptError,
        match="external-full restoration does not match",
    ):
        project_custody_receipt(receipt)


def test_projection_rejects_caller_only_device_assertions() -> None:
    with pytest.raises(ReceiptError, match="missing independent device evidence"):
        project_custody_receipt(metabolism_receipt(evidence=False))


def test_private_projection_write_is_idempotent_and_mode_600(
    tmp_path: Path,
) -> None:
    output = tmp_path / "private" / "custody.json"
    projected = projected_receipt()

    assert write_custody_receipt(output, projected) is True
    original = output.read_bytes()
    original_mtime = output.stat().st_mtime_ns
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.parent.stat().st_mode & 0o777 == 0o700

    assert write_custody_receipt(output, projected) is False
    assert output.read_bytes() == original
    assert output.stat().st_mtime_ns == original_mtime


def test_private_projection_rejects_conflicting_existing_receipt(
    tmp_path: Path,
) -> None:
    output = tmp_path / "private" / "custody.json"
    assert write_custody_receipt(output, projected_receipt()) is True
    conflicting_receipt = metabolism_receipt()
    external = conflicting_receipt.restorations[-1]
    conflicting_receipt.restorations[-1] = RestoreProof(
        **{
            **asdict(external),
            "device_id": "otherRecoveryDevice01",
        }
    )
    conflicting = project_custody_receipt(conflicting_receipt)

    with pytest.raises(ReceiptError, match="conflicts with verified custody"):
        write_custody_receipt(output, conflicting)


def test_projection_accepts_opencode_external_source_digest() -> None:
    receipt = metabolism_receipt()
    receipt.source = SourceProof(
        path=receipt.source.path,
        kind="opencode-sqlite",
        bytes=receipt.source.bytes,
        sha256=receipt.source.sha256,
        stat_before=receipt.source.stat_before,
        stat_after=receipt.source.stat_after,
    )
    opencode_profile = encryption_profile_digest("opencode-sqlite")
    receipt.encryption_profile_digest = opencode_profile
    external = receipt.restorations[-1]
    git = receipt.restorations[-2]
    receipt.restorations[-2] = RestoreProof(
        **{
            **asdict(git),
            "encryption_profile_digest": opencode_profile,
        }
    )
    receipt.restorations[-1] = RestoreProof(
        scope=external.scope,
        passed=True,
        source_sha256=receipt.source.sha256,
        device_id=external.device_id,
        restored_at=external.restored_at,
        encryption_profile_digest=opencode_profile,
    )

    projected = project_custody_receipt(receipt)

    assert {proof.restored_output_digest for proof in projected.restoration_proofs} == {
        LOGICAL_SHA256,
        receipt.source.sha256,
    }


def test_private_projection_removes_failed_temporary_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "private" / "custody.json"
    monkeypatch.setattr(
        custody.os,
        "fsync",
        lambda _descriptor: (_ for _ in ()).throw(OSError("storage failed")),
    )

    with pytest.raises(ReceiptError, match="cannot persist"):
        write_custody_receipt(output, projected_receipt())

    assert not output.exists()
    assert list(output.parent.glob(".custody.json.tmp-*")) == []


def test_independent_restore_binds_remote_refs_and_observed_devices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = metabolism_receipt(evidence=False)
    receipt.encryption_profile_digest = None
    vault_root = tmp_path / "fresh-clone"
    git_payload = vault_root / "agent-state" / "codex-sessions" / receipt.run_id
    external_root = tmp_path / "external"
    external_payload = external_root / "codex-sessions" / receipt.run_id
    git_payload.mkdir(parents=True)
    (git_payload / "atoms-00000.jsonl.gz.enc.part-00000").write_bytes(b"local-only")
    external_payload.mkdir(parents=True)
    remote = receipt.as_dict()
    remote["git_receipt_commit"] = None
    observed: list[str] = []

    class Vault:
        def __init__(self, root: Path, *, repository: str):
            assert repository == "organvm/arca"
            self.root = root

        def verify_identity(self) -> None:
            observed.append("identity")

        def require_exact_remote_head(self) -> str:
            raise AssertionError("historical custody must not require local HEAD")

        def completed_receipt_at_remote(
            self,
            relative: Path,
            message: str,
        ) -> tuple[str, str, str]:
            assert relative == Path(f"agent-state/codex-sessions/{receipt.run_id}")
            assert message == (f"agent-state: receipt codex-sessions {receipt.run_id}")
            observed.append("receipt")
            return "1" * 40, "2" * 40, json.dumps(remote)

        def materialize_remote_payload(
            self,
            relative: Path,
            payload_commit: str,
            expected_paths: list[Path],
            destination: Path,
        ) -> Path:
            assert relative == Path(f"agent-state/codex-sessions/{receipt.run_id}")
            assert payload_commit == "1" * 40
            assert expected_paths == [Path("atoms-00000.jsonl.gz.enc.part-00000")]
            observed.append("materialize")
            destination.mkdir(parents=True)
            return destination

    monkeypatch.setattr(custody, "GitVault", Vault)
    monkeypatch.setattr(custody, "keychain_key", lambda _service: "key")
    verified_roots: list[Path] = []

    def verify_packs(_packs, root: Path, *_args, **_kwargs):
        verified_roots.append(root)
        return RestoreProof(
            scope="git-full-manifest",
            passed=True,
            atoms_verified=2,
            logical_sha256=LOGICAL_SHA256,
        )

    monkeypatch.setattr(custody, "verify_atom_packs", verify_packs)
    monkeypatch.setattr(
        custody,
        "_device_identity",
        lambda path: PRIMARY_DEVICE if path == vault_root else EXTERNAL_DEVICE,
    )

    verified = verify_custody_restorations(
        receipt,
        name="codex-sessions",
        vault_root=vault_root,
        external_root=external_root,
        require_external_mount=False,
        restored_at=RESTORED_AT,
    )

    git_proof = next(proof for proof in verified.restorations if proof.scope == "git-full-manifest")
    external_proof = next(proof for proof in verified.restorations if proof.scope == "external-full")
    assert observed == ["identity", "receipt", "materialize"]
    assert verified_roots[0] != git_payload
    assert verified_roots[1] == external_payload
    assert verified.encryption_profile_digest == encryption_profile_digest()
    assert git_proof.device_id == PRIMARY_DEVICE
    assert git_proof.remote_refs == REMOTE_REFS
    assert external_proof.device_id == EXTERNAL_DEVICE
    assert external_proof.remote_refs == ()
    assert git_proof.restored_at == RESTORED_AT.isoformat()
    assert external_proof.restored_at == RESTORED_AT.isoformat()

    rerun = verify_custody_restorations(
        verified,
        name="codex-sessions",
        vault_root=vault_root,
        external_root=external_root,
        require_external_mount=False,
        restored_at=datetime(2026, 7, 30, 14, 30, tzinfo=UTC),
    )

    assert rerun.as_dict() == verified.as_dict()
    assert observed == [
        "identity",
        "receipt",
        "materialize",
        "identity",
        "receipt",
        "materialize",
    ]


def test_encryption_profile_digest_is_lowercase_sha256() -> None:
    digest = encryption_profile_digest()

    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_opencode_profile_records_raw_external_payload_form() -> None:
    assert encryption_profile_digest("opencode-sqlite") != encryption_profile_digest("file-tree")


def test_device_identity_collapses_apfs_volumes_to_physical_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    external = tmp_path / "external"
    for path in (first, second, external):
        path.mkdir()
    physical_stores = {
        str(first.resolve()): "disk0s2",
        str(second.resolve()): "disk0s5",
        str(external.resolve()): "disk4s1",
    }

    def diskutil(args, **_kwargs):
        if args[-1].startswith("/dev/"):
            return SimpleNamespace(
                returncode=0,
                stdout=plistlib.dumps(
                    {
                        "DeviceIdentifier": args[-1].removeprefix("/dev/"),
                        "ParentWholeDisk": args[-1].removeprefix("/dev/"),
                        "VirtualOrPhysical": "Physical",
                        "WholeDisk": True,
                        "BusProtocol": "PCI-Express",
                        "SystemImage": False,
                        "MediaUUID": (
                            "00000000-0000-0000-0000-000000000001"
                            if args[-1] == "/dev/disk0"
                            else "00000000-0000-0000-0000-000000000002"
                        ),
                    }
                ),
            )
        return SimpleNamespace(
            returncode=0,
            stdout=plistlib.dumps(
                {
                    "DeviceIdentifier": "disk9s1",
                    "APFSPhysicalStores": [
                        {
                            "APFSPhysicalStore": physical_stores[args[-1]],
                        }
                    ],
                }
            ),
        )

    monkeypatch.setattr(custody.subprocess, "run", diskutil)
    monkeypatch.setattr(custody, "_volume_mount", lambda path: path.resolve())

    assert custody._device_identity(first) == custody._device_identity(second)
    assert custody._device_identity(first) != custody._device_identity(external)


def test_device_identity_queries_containing_volume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    volume = tmp_path / "volume"
    target = volume / "nested" / "custody"
    target.mkdir(parents=True)
    observed: list[str] = []

    monkeypatch.setattr(custody.os.path, "ismount", lambda path: Path(path) == volume)

    def diskutil(args, **_kwargs):
        observed.append(args[-1])
        payload = (
            {
                "DeviceIdentifier": "disk4s1",
                "APFSPhysicalStores": [{"APFSPhysicalStore": "disk4s1"}],
            }
            if not args[-1].startswith("/dev/")
            else {
                "DeviceIdentifier": "disk4",
                "ParentWholeDisk": "disk4",
                "VirtualOrPhysical": "Physical",
                "WholeDisk": True,
                "BusProtocol": "USB",
                "SystemImage": False,
                "MediaUUID": "00000000-0000-0000-0000-000000000004",
            }
        )
        return SimpleNamespace(returncode=0, stdout=plistlib.dumps(payload))

    monkeypatch.setattr(custody.subprocess, "run", diskutil)

    custody._device_identity(target)

    assert observed == [str(volume), "/dev/disk4"]


def test_device_identity_rejects_virtual_disk_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mounted_image = tmp_path / "mounted-image"
    mounted_image.mkdir()

    def diskutil(args, **_kwargs):
        payload = (
            {
                "DeviceIdentifier": "disk8s1",
                "APFSPhysicalStores": [{"APFSPhysicalStore": "disk8s1"}],
            }
            if not args[-1].startswith("/dev/")
            else {
                "DeviceIdentifier": "disk8",
                "ParentWholeDisk": "disk8",
                "VirtualOrPhysical": "Virtual",
                "WholeDisk": True,
                "BusProtocol": "Disk Image",
                "SystemImage": False,
            }
        )
        return SimpleNamespace(returncode=0, stdout=plistlib.dumps(payload))

    monkeypatch.setattr(custody.subprocess, "run", diskutil)
    monkeypatch.setattr(custody, "_volume_mount", lambda path: path.resolve())

    with pytest.raises(ReceiptError, match="not backed by a physical"):
        custody._device_identity(mounted_image)


def test_device_identity_is_stable_across_bsd_renumbering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "external"
    target.mkdir()
    physical = "disk4"

    def diskutil(args, **_kwargs):
        if args[0] == "/usr/sbin/ioreg":
            return SimpleNamespace(
                returncode=0,
                stdout=f"""
+-o External <class IOUSBHostDevice, id 0x1>
  {{
    "USB Serial Number" = "stable-external-device"
    +-o Media <class IOMedia, id 0x2>
      {{
        "BSD Name" = "{physical}"
      }}
  }}
""".encode(),
            )
        payload = (
            {
                "DeviceIdentifier": f"{physical}s1",
                "APFSPhysicalStores": [{"APFSPhysicalStore": f"{physical}s1"}],
            }
            if not args[-1].startswith("/dev/")
            else {
                "DeviceIdentifier": physical,
                "ParentWholeDisk": physical,
                "VirtualOrPhysical": "Physical",
                "WholeDisk": True,
                "BusProtocol": "USB",
                "SystemImage": False,
            }
        )
        return SimpleNamespace(returncode=0, stdout=plistlib.dumps(payload))

    monkeypatch.setattr(custody.subprocess, "run", diskutil)
    monkeypatch.setattr(custody, "_volume_mount", lambda path: path.resolve())
    before = custody._device_identity(target)
    physical = "disk7"

    assert custody._device_identity(target) == before


def test_device_identity_collapses_usb_volumes_to_hardware_serial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    physical_stores = {
        str(first.resolve()): "disk4s1",
        str(second.resolve()): "disk7s1",
    }

    def diskutil(args, **_kwargs):
        if args[0] == "/usr/sbin/ioreg":
            return SimpleNamespace(
                returncode=0,
                stdout=b"""
+-o External <class IOUSBHostDevice, id 0x1>
  {
    "USB Serial Number" = "shared-physical-device"
    +-o Media <class IOMedia, id 0x2>
      {
        "BSD Name" = "disk4"
      }
    +-o Media <class IOMedia, id 0x3>
      {
        "BSD Name" = "disk7"
      }
  }
""",
            )
        if args[-1].startswith("/dev/"):
            physical = args[-1].removeprefix("/dev/")
            return SimpleNamespace(
                returncode=0,
                stdout=plistlib.dumps(
                    {
                        "DeviceIdentifier": physical,
                        "ParentWholeDisk": physical,
                        "VirtualOrPhysical": "Physical",
                        "WholeDisk": True,
                        "BusProtocol": "USB",
                        "SystemImage": False,
                    }
                ),
            )
        return SimpleNamespace(
            returncode=0,
            stdout=plistlib.dumps(
                {
                    "APFSPhysicalStores": [
                        {
                            "APFSPhysicalStore": physical_stores[args[-1]],
                        }
                    ],
                }
            ),
        )

    monkeypatch.setattr(custody.subprocess, "run", diskutil)
    monkeypatch.setattr(custody, "_volume_mount", lambda path: path.resolve())

    assert custody._device_identity(first) == custody._device_identity(second)


def test_device_identity_uses_usb_hardware_serial_when_disk_uuid_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "external"
    target.mkdir()

    def diskutil(args, **_kwargs):
        if args[0] == "/usr/sbin/ioreg":
            return SimpleNamespace(
                returncode=0,
                stdout=b"""
+-o External <class IOUSBHostDevice, id 0x1>
  {
    "USB Serial Number" = "external-device-serial"
    +-o Media <class IOMedia, id 0x2>
      {
        "BSD Name" = "disk4"
      }
  }
""",
            )
        payload = (
            {
                "APFSPhysicalStores": [{"APFSPhysicalStore": "disk4s1"}],
            }
            if not args[-1].startswith("/dev/")
            else {
                "DeviceIdentifier": "disk4",
                "ParentWholeDisk": "disk4",
                "VirtualOrPhysical": "Physical",
                "WholeDisk": True,
                "BusProtocol": "USB",
                "SystemImage": False,
            }
        )
        return SimpleNamespace(returncode=0, stdout=plistlib.dumps(payload))

    monkeypatch.setattr(custody.subprocess, "run", diskutil)
    monkeypatch.setattr(custody, "_volume_mount", lambda path: path.resolve())

    identity = custody._device_identity(target)

    assert identity.startswith("device_")
    assert len(identity) == len("device_") + 32


def test_device_identity_requires_stable_external_media_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "external"
    target.mkdir()

    def diskutil(args, **_kwargs):
        if args[0] == "/usr/sbin/ioreg":
            return SimpleNamespace(
                returncode=0,
                stdout=b"""
+-o External <class IOUSBHostDevice, id 0x1>
  {
    +-o Media <class IOMedia, id 0x2>
      {
        "BSD Name" = "disk4"
      }
  }
""",
            )
        payload = (
            {
                "DeviceIdentifier": "disk4s1",
                "APFSPhysicalStores": [{"APFSPhysicalStore": "disk4s1"}],
            }
            if not args[-1].startswith("/dev/")
            else {
                "DeviceIdentifier": "disk4",
                "ParentWholeDisk": "disk4",
                "VirtualOrPhysical": "Physical",
                "WholeDisk": True,
                "BusProtocol": "USB",
                "SystemImage": False,
            }
        )
        return SimpleNamespace(returncode=0, stdout=plistlib.dumps(payload))

    monkeypatch.setattr(custody.subprocess, "run", diskutil)
    monkeypatch.setattr(custody, "_volume_mount", lambda path: path.resolve())

    with pytest.raises(ReceiptError, match="stable media identity"):
        custody._device_identity(target)


def test_unsupported_source_kind_is_a_receipt_error(tmp_path: Path) -> None:
    receipt = metabolism_receipt(evidence=False)
    receipt.source = SourceProof(
        path=receipt.source.path,
        kind="unsupported",
        bytes=receipt.source.bytes,
        sha256=receipt.source.sha256,
        stat_before=receipt.source.stat_before,
        stat_after=receipt.source.stat_after,
        inventory_before_sha256=receipt.source.inventory_before_sha256,
        inventory_after_sha256=receipt.source.inventory_after_sha256,
    )

    with pytest.raises(ReceiptError, match="does not support this source kind"):
        verify_custody_restorations(
            receipt,
            name="codex-sessions",
            vault_root=tmp_path / "vault",
            external_root=tmp_path / "external",
            require_external_mount=False,
        )


def test_campaign_rejects_private_receipt_inside_source_tree(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    private_receipt = source / "metabolism.json"
    initial = metabolism_receipt(evidence=False)
    initial.source = SourceProof(
        path=str(source),
        kind=initial.source.kind,
        bytes=initial.source.bytes,
        sha256=initial.source.sha256,
        stat_before=initial.source.stat_before,
        stat_after=initial.source.stat_after,
        inventory_before_sha256=initial.source.inventory_before_sha256,
        inventory_after_sha256=initial.source.inventory_after_sha256,
    )
    initial.write(private_receipt)

    with pytest.raises(ReceiptError, match="private metabolism receipt"):
        run_custody_verification_campaign(
            "codex-sessions",
            private_receipt,
            tmp_path / "vault",
            tmp_path / "external",
            tmp_path / "custody.json",
            require_external_mount=False,
        )


@pytest.mark.parametrize("nested_target", ["git", "external"])
def test_campaign_rejects_custody_payload_inside_source_before_writes(
    tmp_path: Path,
    nested_target: str,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    private_receipt = tmp_path / "private" / "metabolism.json"
    initial = metabolism_receipt(evidence=False)
    initial.source = SourceProof(
        path=str(source),
        kind=initial.source.kind,
        bytes=initial.source.bytes,
        sha256=initial.source.sha256,
        stat_before=initial.source.stat_before,
        stat_after=initial.source.stat_after,
        inventory_before_sha256=initial.source.inventory_before_sha256,
        inventory_after_sha256=initial.source.inventory_after_sha256,
    )
    initial.write(private_receipt)
    vault_root = source / "vault" if nested_target == "git" else tmp_path / "vault"
    external_root = source / "external" if nested_target == "external" else tmp_path / "external"

    with pytest.raises(ReceiptError, match=f"{nested_target} custody payload".replace("git", "Git")):
        run_custody_verification_campaign(
            "codex-sessions",
            private_receipt,
            vault_root,
            external_root,
            tmp_path / "custody.json",
            require_external_mount=False,
        )

    assert not vault_root.exists()
    assert not external_root.exists()


def test_campaign_conflicting_projection_does_not_replace_private_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_receipt = tmp_path / "private" / "metabolism.json"
    output = tmp_path / "projection" / "custody.json"
    initial = metabolism_receipt(evidence=False)
    initial.write(private_receipt)
    original = private_receipt.read_bytes()
    verified = metabolism_receipt()
    conflicting = metabolism_receipt()
    external = conflicting.restorations[-1]
    conflicting.restorations[-1] = RestoreProof(
        **{
            **asdict(external),
            "device_id": "otherRecoveryDevice01",
        }
    )
    write_custody_receipt(output, project_custody_receipt(conflicting))
    monkeypatch.setattr(custody, "hold_lease", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(
        custody,
        "verify_custody_restorations",
        lambda *_args, **_kwargs: verified,
    )

    with pytest.raises(ReceiptError, match="conflicts with verified custody"):
        run_custody_verification_campaign(
            "codex-sessions",
            private_receipt,
            tmp_path / "vault",
            tmp_path / "external",
            output,
            require_external_mount=False,
        )

    assert private_receipt.read_bytes() == original


def test_campaign_projection_failure_does_not_replace_private_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_receipt = tmp_path / "private" / "metabolism.json"
    output = tmp_path / "projection" / "custody.json"
    initial = metabolism_receipt(evidence=False)
    initial.write(private_receipt)
    original = private_receipt.read_bytes()
    verified = metabolism_receipt()
    monkeypatch.setattr(custody, "hold_lease", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(
        custody,
        "verify_custody_restorations",
        lambda *_args, **_kwargs: verified,
    )
    monkeypatch.setattr(
        custody.os,
        "link",
        lambda *_args: (_ for _ in ()).throw(OSError("publication failed")),
    )

    with pytest.raises(ReceiptError, match="atomically persist"):
        run_custody_verification_campaign(
            "codex-sessions",
            private_receipt,
            tmp_path / "vault",
            tmp_path / "external",
            output,
            require_external_mount=False,
        )

    assert private_receipt.read_bytes() == original
    assert not output.exists()


def test_campaign_publication_recovers_after_crash_before_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_receipt = tmp_path / "private" / "metabolism.json"
    output = tmp_path / "projection" / "custody.json"
    initial = metabolism_receipt(evidence=False)
    initial.write(private_receipt)
    verified = metabolism_receipt()
    projected = project_custody_receipt(verified)
    original_fsync = custody._fsync_directory
    crashed = False

    def crash_after_private_receipt(path: Path) -> None:
        nonlocal crashed
        if path == private_receipt.parent and not crashed:
            crashed = True
            raise SystemExit("simulated termination")
        original_fsync(path)

    monkeypatch.setattr(custody, "_fsync_directory", crash_after_private_receipt)
    with pytest.raises(SystemExit, match="simulated termination"):
        custody._publish_campaign_receipts(
            metabolism_receipt=private_receipt,
            verified=verified,
            output=output,
            projected=projected,
        )

    assert MetabolismReceipt.read(private_receipt).as_dict() == verified.as_dict()
    assert not output.exists()

    monkeypatch.setattr(custody, "_fsync_directory", original_fsync)
    assert custody._publish_campaign_receipts(
        metabolism_receipt=private_receipt,
        verified=verified,
        output=output,
        projected=projected,
    ) == (False, True)
    assert write_custody_receipt(output, projected) is False


def test_campaign_repairs_existing_projection_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_receipt = tmp_path / "private" / "metabolism.json"
    output = tmp_path / "projection" / "custody.json"
    verified = metabolism_receipt()
    verified.write(private_receipt)
    write_custody_receipt(output, project_custody_receipt(verified))
    output.chmod(0o644)
    monkeypatch.setattr(custody, "hold_lease", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(
        custody,
        "verify_custody_restorations",
        lambda *_args, **_kwargs: verified,
    )

    _, _, metabolism_changed, custody_changed = run_custody_verification_campaign(
        "codex-sessions",
        private_receipt,
        tmp_path / "vault",
        tmp_path / "external",
        output,
        require_external_mount=False,
    )

    assert metabolism_changed is False
    assert custody_changed is False
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("device_id", 1),
        ("remote_refs", [1]),
    ],
)
def test_receipt_rejects_non_string_restoration_identifiers(
    field: str,
    value: object,
) -> None:
    payload = metabolism_receipt().as_dict()
    payload["restorations"][1][field] = value

    with pytest.raises(ReceiptError, match="failed consistency checks"):
        MetabolismReceipt.from_dict(payload)


def test_receipt_rejects_non_object_restoration_proof() -> None:
    payload = metabolism_receipt().as_dict()
    payload["restorations"] = [1]

    with pytest.raises(ReceiptError, match="invalid restoration evidence"):
        MetabolismReceipt.from_dict(payload)
