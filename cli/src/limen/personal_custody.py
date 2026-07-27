"""Two-independent-drive custody and exact-plan reclaim for personal roots.

Private plans contain source paths and relative names, so they live only on the
two external custody devices. Public JSONL receipts contain aggregate evidence
and exact plan/content digests but no source or child paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import secrets
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.agent_state.pipeline import PipelineError, require_mounted_external
from limen.worktree_abandonment import (
    CustodyPathIdentity,
    WorktreeAbandonmentError,
    purge_custody_proven_contents,
    purge_custody_proven_path,
)

PLAN_SCHEMA = "limen.personal_custody_plan.v1"
RECEIPT_SCHEMA = "limen.personal_custody_receipt.v1"
PUBLIC_RECEIPT_SCHEMA = "limen.personal_custody_public_receipt.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CHUNK_BYTES = 4 * 1024 * 1024
DEFAULT_ARCHIVE_ROOT = Path("/Volumes/Archive4T")
DEFAULT_RECOVERY_ROOT = Path("/Volumes/T7Recovery")
DEFAULT_PRIVATE_ROOT = Path("laptop-evacuation/20260727")
CopyTree = Callable[[Path, Path], None]
VolumeProbe = Callable[[Path], "VolumeIdentity"]


class PersonalCustodyError(RuntimeError):
    """A bounded custody or reclaim predicate failed closed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class VolumeIdentity:
    mount: str
    device: str
    physical_device: str
    volume_uuid: str


@dataclass(frozen=True)
class SourceIdentity:
    path: str
    path_sha256: str
    device: int
    inode: int
    mtime_ns: int


@dataclass(frozen=True)
class ContentRecord:
    relative: str
    kind: str
    mode: int
    size_bytes: int
    physical_bytes: int
    sha256: str | None
    link_target: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or path.is_symlink():
            raise PersonalCustodyError("source-file-not-regular")
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK_BYTES):
                digest.update(chunk)
        after = path.lstat()
    except OSError as exc:
        raise PersonalCustodyError("source-file-unavailable", type(exc).__name__) from exc
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if tuple(getattr(before, key) for key in identity) != tuple(getattr(after, key) for key in identity):
        raise PersonalCustodyError("source-file-changed-during-hash")
    return digest.hexdigest()


def _record(path: Path, source: Path) -> ContentRecord:
    try:
        info = path.lstat()
    except OSError as exc:
        raise PersonalCustodyError("source-entry-unavailable", type(exc).__name__) from exc
    relative = "." if path == source else path.relative_to(source).as_posix()
    mode = stat.S_IMODE(info.st_mode)
    physical = int(getattr(info, "st_blocks", 0) * 512)
    if stat.S_ISDIR(info.st_mode):
        return ContentRecord(relative, "directory", mode, 0, physical, None, None)
    if stat.S_ISREG(info.st_mode):
        return ContentRecord(
            relative,
            "file",
            mode,
            int(info.st_size),
            physical,
            _file_sha256(path),
            None,
        )
    if stat.S_ISLNK(info.st_mode):
        try:
            target = os.readlink(path)
        except OSError as exc:
            raise PersonalCustodyError("source-symlink-unavailable", type(exc).__name__) from exc
        encoded = target.encode("utf-8", errors="surrogateescape")
        return ContentRecord(
            relative,
            "symlink",
            mode,
            len(encoded),
            physical,
            hashlib.sha256(encoded).hexdigest(),
            target,
        )
    raise PersonalCustodyError("source-special-file", relative)


def content_records(source: Path) -> tuple[ContentRecord, ...]:
    """Hash one directory without following symlinks or accepting special files."""

    try:
        source = source.expanduser().resolve(strict=True)
        root_before = source.lstat()
    except OSError as exc:
        raise PersonalCustodyError("source-root-unavailable", type(exc).__name__) from exc
    if source.is_symlink() or not stat.S_ISDIR(root_before.st_mode):
        raise PersonalCustodyError("source-root-not-directory")
    records = [_record(source, source)]
    for current, directories, files in os.walk(source, followlinks=False):
        current_path = Path(current)
        directories.sort()
        files.sort()
        for name in directories:
            records.append(_record(current_path / name, source))
        for name in files:
            records.append(_record(current_path / name, source))
    try:
        root_after = source.lstat()
    except OSError as exc:
        raise PersonalCustodyError("source-root-changed", type(exc).__name__) from exc
    if (
        root_before.st_dev,
        root_before.st_ino,
        root_before.st_mtime_ns,
    ) != (
        root_after.st_dev,
        root_after.st_ino,
        root_after.st_mtime_ns,
    ):
        raise PersonalCustodyError("source-root-changed-during-hash")
    return tuple(sorted(records, key=lambda value: value.relative))


def _source_identity(source: Path) -> SourceIdentity:
    resolved = source.expanduser().resolve(strict=True)
    info = resolved.lstat()
    if resolved.is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise PersonalCustodyError("source-root-not-directory")
    encoded = str(resolved).encode("utf-8", errors="surrogateescape")
    return SourceIdentity(
        path=str(resolved),
        path_sha256=hashlib.sha256(encoded).hexdigest(),
        device=int(info.st_dev),
        inode=int(info.st_ino),
        mtime_ns=int(info.st_mtime_ns),
    )


def _diskutil_volume_identity(mount: Path) -> VolumeIdentity:
    try:
        result = subprocess.run(
            ["/usr/sbin/diskutil", "info", "-plist", str(mount)],
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PersonalCustodyError("volume-identity-probe-failed") from exc
    if result.returncode:
        raise PersonalCustodyError("volume-identity-probe-failed")
    try:
        payload = plistlib.loads(result.stdout)
        device = str(payload["DeviceIdentifier"])
        stores = payload.get("APFSPhysicalStores")
        if isinstance(stores, list) and len(stores) == 1 and isinstance(stores[0], dict):
            store = str(stores[0]["APFSPhysicalStore"])
            match = re.fullmatch(r"(disk[0-9]+)s[0-9]+", store)
            physical = match.group(1) if match else store
        else:
            physical = str(payload["ParentWholeDisk"])
        volume_uuid = str(payload["VolumeUUID"]).upper()
        mounted = str(Path(payload["MountPoint"]).resolve(strict=True))
    except (KeyError, OSError, plistlib.InvalidFileException, TypeError) as exc:
        raise PersonalCustodyError("volume-identity-invalid") from exc
    return VolumeIdentity(
        mount=mounted,
        device=f"/dev/{device}",
        physical_device=f"/dev/{physical}",
        volume_uuid=volume_uuid,
    )


def _inventory_root(inventory: dict[str, Any], source: Path) -> dict[str, Any]:
    resolved = source.expanduser().resolve(strict=True)
    for candidate in inventory.get("roots", []):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("root"), str):
            continue
        try:
            path = Path(candidate["root"]).expanduser().resolve(strict=True)
        except OSError:
            continue
        if path == resolved:
            return candidate
    raise PersonalCustodyError("source-not-in-frozen-inventory")


def _inventory_volume(inventory: dict[str, Any], name: str, actual: VolumeIdentity) -> None:
    for candidate in inventory.get("custody_devices", []):
        if isinstance(candidate, dict) and candidate.get("name") == name:
            expected = (
                candidate.get("device"),
                candidate.get("physical_device"),
                str(candidate.get("volume_uuid", "")).upper(),
            )
            observed = (
                actual.device,
                actual.physical_device,
                actual.volume_uuid,
            )
            if expected != observed:
                raise PersonalCustodyError(f"{name.lower()}-inventory-device-drift")
            return
    raise PersonalCustodyError(f"{name.lower()}-missing-from-inventory")


def _prepare_external_root(path: Path, *, require_volume: bool) -> Path:
    if require_volume:
        try:
            return require_mounted_external(path)
        except PipelineError as exc:
            raise PersonalCustodyError("external-custody-unavailable") from exc
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _private_plan_relative(label: str, plan_sha256: str) -> Path:
    return Path("_MANIFESTS") / label / f"{plan_sha256}.plan.json"


def _receipt_relative(label: str, plan_sha256: str) -> Path:
    return Path("_MANIFESTS") / label / f"{plan_sha256}.receipt.json"


def _object_relative(label: str, content_sha256: str) -> Path:
    return Path("objects") / label / content_sha256


def _atomic_json(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)


def _load_json(path: Path, *, schema: str) -> dict[str, Any]:
    try:
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise PersonalCustodyError("private-receipt-not-regular")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PersonalCustodyError("private-receipt-unavailable") from exc
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise PersonalCustodyError("private-receipt-schema-mismatch")
    return payload


def _plan_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "plan_sha256"}


def _validated_plan(path: Path, expected_sha256: str) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(expected_sha256):
        raise PersonalCustodyError("invalid-expected-plan-sha")
    plan = _load_json(path, schema=PLAN_SCHEMA)
    observed = _canonical_sha256(_plan_payload(plan))
    if observed != expected_sha256 or plan.get("plan_sha256") != expected_sha256:
        raise PersonalCustodyError("custody-plan-sha-mismatch")
    return plan


def _expected_records(plan: dict[str, Any]) -> tuple[ContentRecord, ...]:
    try:
        records = tuple(ContentRecord(**value) for value in plan["records"])
    except (KeyError, TypeError) as exc:
        raise PersonalCustodyError("custody-plan-records-invalid") from exc
    if _canonical_sha256([asdict(value) for value in records]) != plan.get("content_sha256"):
        raise PersonalCustodyError("custody-plan-content-mismatch")
    return records


def _assert_content(path: Path, expected: tuple[ContentRecord, ...]) -> None:
    current = content_records(path)

    def logical(record: ContentRecord) -> tuple[str, str, int, int, str | None, str | None]:
        return (
            record.relative,
            record.kind,
            record.mode,
            record.size_bytes,
            record.sha256,
            record.link_target,
        )

    if tuple(map(logical, current)) != tuple(map(logical, expected)):
        raise PersonalCustodyError("custody-content-drift")


def _copy_with_ditto(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "/usr/bin/ditto",
            "--rsrc",
            "--extattr",
            "--acl",
            "--noqtn",
            str(source),
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[:300]
        raise PersonalCustodyError("custody-copy-failed", detail)


def _restore_probe(
    copy: Path,
    records: tuple[ContentRecord, ...],
    *,
    copy_file: Callable[[Path, Path], None] | None = None,
) -> dict[str, Any]:
    regular = [record for record in records if record.kind == "file"]
    if not regular:
        return {"kind": "empty-tree-manifest", "passed": True}
    selected = max(regular, key=lambda value: (value.size_bytes, value.relative))
    source = copy / selected.relative
    probe_root = copy.parent / f".restore-probe-{os.getpid()}-{secrets.token_hex(6)}"
    probe = probe_root / "restored"
    probe_root.mkdir(mode=0o700)
    try:
        if copy_file is None:
            if Path("/usr/bin/ditto").is_file():
                result = subprocess.run(
                    [
                        "/usr/bin/ditto",
                        "--rsrc",
                        "--extattr",
                        "--acl",
                        str(source),
                        str(probe),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode:
                    raise PersonalCustodyError("restore-probe-copy-failed")
            else:
                shutil.copy2(source, probe)
        else:
            copy_file(source, probe)
        if _file_sha256(probe) != selected.sha256:
            raise PersonalCustodyError("restore-probe-hash-mismatch")
        return {
            "kind": "materialized-file",
            "relative_sha256": hashlib.sha256(selected.relative.encode("utf-8", errors="surrogateescape")).hexdigest(),
            "size_bytes": selected.size_bytes,
            "passed": True,
        }
    finally:
        if probe.exists() or probe.is_symlink():
            probe.unlink()
        if probe_root.exists():
            probe_root.rmdir()


def create_plan(
    *,
    inventory_path: Path,
    label: str,
    source: Path,
    archive_root: Path,
    recovery_root: Path,
    private_root: Path,
    reclaim_mode: str = "root",
    require_volume: bool = True,
    volume_probe: VolumeProbe = _diskutil_volume_identity,
) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", label):
        raise PersonalCustodyError("invalid-custody-label")
    if reclaim_mode not in {"root", "contents"}:
        raise PersonalCustodyError("invalid-reclaim-mode")
    try:
        inventory_bytes = inventory_path.read_bytes()
        inventory = json.loads(inventory_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise PersonalCustodyError("inventory-unavailable") from exc
    if not isinstance(inventory, dict) or inventory.get("schema") != ("limen.storage_evacuation_inventory.v1"):
        raise PersonalCustodyError("inventory-schema-mismatch")
    selected = _inventory_root(inventory, source)
    archive = _prepare_external_root(archive_root / private_root, require_volume=require_volume)
    recovery = _prepare_external_root(recovery_root / private_root, require_volume=require_volume)
    archive_identity = volume_probe(archive_root.resolve(strict=True))
    recovery_identity = volume_probe(recovery_root.resolve(strict=True))
    _inventory_volume(inventory, "Archive4T", archive_identity)
    _inventory_volume(inventory, "T7Recovery", recovery_identity)
    if archive_identity.physical_device == recovery_identity.physical_device:
        raise PersonalCustodyError("custody-volumes-share-physical-device")
    source_identity = _source_identity(source)
    records = content_records(source)
    record_payload = [asdict(record) for record in records]
    content_sha256 = _canonical_sha256(record_payload)
    payload = {
        "schema": PLAN_SCHEMA,
        "created_at": _now(),
        "inventory": {
            "id": inventory.get("inventory_id"),
            "sha256": hashlib.sha256(inventory_bytes).hexdigest(),
            "frozen_at": inventory.get("frozen_at"),
            "selected_root": selected.get("root"),
            "selected_size_bytes": selected.get("size_bytes"),
            "owner": selected.get("owner"),
            "gate": selected.get("gate"),
        },
        "label": label,
        "reclaim_mode": reclaim_mode,
        "source": asdict(source_identity),
        "volumes": {
            "archive": asdict(archive_identity),
            "recovery": asdict(recovery_identity),
        },
        "private_root": private_root.as_posix(),
        "content_sha256": content_sha256,
        "file_count": sum(record.kind == "file" for record in records),
        "directory_count": sum(record.kind == "directory" for record in records),
        "symlink_count": sum(record.kind == "symlink" for record in records),
        "size_bytes": sum(record.size_bytes for record in records),
        "physical_bytes": sum(record.physical_bytes for record in records),
        "records": record_payload,
    }
    plan_sha256 = _canonical_sha256(payload)
    plan = {**payload, "plan_sha256": plan_sha256}
    relative = _private_plan_relative(label, plan_sha256)
    _atomic_json(archive / relative, plan)
    _atomic_json(recovery / relative, plan)
    return {
        "schema": PUBLIC_RECEIPT_SCHEMA,
        "event": "planned",
        "label": label,
        "reclaim_mode": reclaim_mode,
        "inventory_sha256": payload["inventory"]["sha256"],
        "plan_sha256": plan_sha256,
        "content_sha256": content_sha256,
        "file_count": payload["file_count"],
        "size_bytes": payload["size_bytes"],
        "physical_bytes": payload["physical_bytes"],
        "archive_plan": str(archive / relative),
        "recovery_plan": str(recovery / relative),
        "independent_physical_devices": True,
    }


def _live_volume_roots(
    plan: dict[str, Any],
    *,
    require_volume: bool,
    volume_probe: VolumeProbe,
) -> tuple[Path, Path]:
    volumes = plan["volumes"]
    archive_mount = Path(volumes["archive"]["mount"])
    recovery_mount = Path(volumes["recovery"]["mount"])
    archive_live = volume_probe(archive_mount.resolve(strict=True))
    recovery_live = volume_probe(recovery_mount.resolve(strict=True))
    if asdict(archive_live) != volumes["archive"]:
        raise PersonalCustodyError("archive-volume-identity-drift")
    if asdict(recovery_live) != volumes["recovery"]:
        raise PersonalCustodyError("recovery-volume-identity-drift")
    if archive_live.physical_device == recovery_live.physical_device:
        raise PersonalCustodyError("custody-volumes-share-physical-device")
    private_root = Path(plan["private_root"])
    archive = _prepare_external_root(archive_mount / private_root, require_volume=require_volume)
    recovery = _prepare_external_root(recovery_mount / private_root, require_volume=require_volume)
    return archive, recovery


def _materialize_copy(
    source: Path,
    destination: Path,
    expected: tuple[ContentRecord, ...],
    *,
    copy_tree: CopyTree,
) -> dict[str, Any]:
    if destination.exists():
        try:
            _assert_content(destination, expected)
        except PersonalCustodyError:
            # A prior bounded copy may have stopped mid-file. The destination is
            # content-addressed by this exact plan, so ditto may resume into it.
            copy_tree(source, destination)
            _assert_content(destination, expected)
        return _restore_probe(destination, expected)
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy_tree(source, destination)
    _assert_content(destination, expected)
    return _restore_probe(destination, expected)


def apply_plan(
    *,
    plan_path: Path,
    expected_plan_sha256: str,
    public_receipt_path: Path | None = None,
    require_volume: bool = True,
    volume_probe: VolumeProbe = _diskutil_volume_identity,
    copy_tree: CopyTree = _copy_with_ditto,
) -> dict[str, Any]:
    plan = _validated_plan(plan_path, expected_plan_sha256)
    expected = _expected_records(plan)
    archive, recovery = _live_volume_roots(plan, require_volume=require_volume, volume_probe=volume_probe)
    relative_plan = _private_plan_relative(plan["label"], expected_plan_sha256)
    peer_plan = recovery / relative_plan
    if _validated_plan(peer_plan, expected_plan_sha256) != plan:
        raise PersonalCustodyError("recovery-plan-content-mismatch")
    source = Path(plan["source"]["path"])
    if asdict(_source_identity(source)) != plan["source"]:
        raise PersonalCustodyError("source-identity-drift")
    _assert_content(source, expected)
    object_relative = _object_relative(plan["label"], plan["content_sha256"])
    archive_copy = archive / object_relative
    recovery_copy = recovery / object_relative
    archive_restore = _materialize_copy(source, archive_copy, expected, copy_tree=copy_tree)
    recovery_restore = _materialize_copy(source, recovery_copy, expected, copy_tree=copy_tree)
    _assert_content(source, expected)
    receipt_payload = {
        "schema": RECEIPT_SCHEMA,
        "status": "restored",
        "created_at": _now(),
        "label": plan["label"],
        "reclaim_mode": plan.get("reclaim_mode", "root"),
        "plan_sha256": expected_plan_sha256,
        "content_sha256": plan["content_sha256"],
        "inventory_sha256": plan["inventory"]["sha256"],
        "source": plan["source"],
        "file_count": plan["file_count"],
        "size_bytes": plan["size_bytes"],
        "physical_bytes": plan["physical_bytes"],
        "copies": {
            "archive": {
                "volume": plan["volumes"]["archive"],
                "relative": object_relative.as_posix(),
                "restore": archive_restore,
            },
            "recovery": {
                "volume": plan["volumes"]["recovery"],
                "relative": object_relative.as_posix(),
                "restore": recovery_restore,
            },
        },
        "independent_physical_devices": True,
        "restoration_passed": True,
        "reclaimed": False,
    }
    receipt_payload["receipt_sha256"] = _canonical_sha256(receipt_payload)
    relative_receipt = _receipt_relative(plan["label"], expected_plan_sha256)
    _atomic_json(archive / relative_receipt, receipt_payload)
    _atomic_json(recovery / relative_receipt, receipt_payload)
    public = {
        "schema": PUBLIC_RECEIPT_SCHEMA,
        "event": "custody_restored",
        "recorded_at": _now(),
        "label": plan["label"],
        "reclaim_mode": plan.get("reclaim_mode", "root"),
        "inventory_sha256": plan["inventory"]["sha256"],
        "plan_sha256": expected_plan_sha256,
        "content_sha256": plan["content_sha256"],
        "receipt_sha256": receipt_payload["receipt_sha256"],
        "file_count": plan["file_count"],
        "size_bytes": plan["size_bytes"],
        "physical_bytes": plan["physical_bytes"],
        "copy_count": 2,
        "independent_physical_devices": True,
        "restoration_passed": True,
        "reclaimed": False,
    }
    if public_receipt_path is not None:
        _append_public_receipt(public_receipt_path, public)
    return public


def _validated_receipt(path: Path, plan: dict[str, Any], expected_plan_sha256: str) -> dict[str, Any]:
    receipt = _load_json(path, schema=RECEIPT_SCHEMA)
    content = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt.get("receipt_sha256") != _canonical_sha256(content):
        raise PersonalCustodyError("custody-receipt-sha-mismatch")
    if (
        receipt.get("plan_sha256") != expected_plan_sha256
        or receipt.get("content_sha256") != plan.get("content_sha256")
        or receipt.get("restoration_passed") is not True
        or receipt.get("independent_physical_devices") is not True
    ):
        raise PersonalCustodyError("custody-receipt-proof-mismatch")
    return receipt


def _open_owner_probe(path: Path, *, ignore_root: bool) -> int | None:
    try:
        result = subprocess.run(
            ["lsof", "-n", "-Fpn", "+D", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return -1
    if result.returncode not in {0, 1}:
        return -1
    root = path.resolve(strict=True)
    pid: int | None = None
    for line in result.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n/") and pid is not None:
            candidate = Path(line[1:]).resolve(strict=False)
            if ignore_root and candidate == root:
                continue
            if candidate == root or root in candidate.parents:
                return pid
    return None


def _open_file_owner_probe(path: Path) -> int | None:
    return _open_owner_probe(path, ignore_root=False)


def _open_descendant_owner_probe(path: Path) -> int | None:
    return _open_owner_probe(path, ignore_root=True)


def _remove_root_delete_acl(path: Path) -> None:
    """Remove only the source root ACL after custody and owner checks pass."""

    if sys.platform != "darwin":
        return
    result = subprocess.run(
        ["/bin/chmod", "-N", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("source-root-delete-acl-removal-failed")


def reclaim_plan(
    *,
    plan_path: Path,
    expected_plan_sha256: str,
    public_receipt_path: Path | None = None,
    require_volume: bool = True,
    volume_probe: VolumeProbe = _diskutil_volume_identity,
    owner_probe: Callable[[Path], int | None] = _open_file_owner_probe,
) -> dict[str, Any]:
    plan = _validated_plan(plan_path, expected_plan_sha256)
    expected = _expected_records(plan)
    archive, recovery = _live_volume_roots(plan, require_volume=require_volume, volume_probe=volume_probe)
    relative_receipt = _receipt_relative(plan["label"], expected_plan_sha256)
    archive_receipt = _validated_receipt(archive / relative_receipt, plan, expected_plan_sha256)
    recovery_receipt = _validated_receipt(recovery / relative_receipt, plan, expected_plan_sha256)
    if archive_receipt != recovery_receipt:
        raise PersonalCustodyError("custody-receipts-diverged")
    object_relative = _object_relative(plan["label"], plan["content_sha256"])
    archive_copy = archive / object_relative
    recovery_copy = recovery / object_relative
    _assert_content(archive_copy, expected)
    archive_restore = _restore_probe(archive_copy, expected)
    _assert_content(recovery_copy, expected)
    recovery_restore = _restore_probe(recovery_copy, expected)
    source = Path(plan["source"]["path"])
    if asdict(_source_identity(source)) != plan["source"]:
        raise PersonalCustodyError("source-identity-drift")
    _assert_content(source, expected)
    expected_identity = SourceIdentity(**plan["source"])
    purge_identity = CustodyPathIdentity(
        path=expected_identity.path,
        path_sha256=expected_identity.path_sha256,
        device=expected_identity.device,
        inode=expected_identity.inode,
        mtime_ns=expected_identity.mtime_ns,
    )
    reclaim_mode = plan.get("reclaim_mode", "root")
    effective_owner_probe = (
        _open_descendant_owner_probe
        if reclaim_mode == "contents" and owner_probe is _open_file_owner_probe
        else owner_probe
    )
    try:
        arguments = {
            "source": source,
            "expected": purge_identity,
            "reason": "custody-restored+idle",
            "custody_plan_sha256": expected_plan_sha256,
            "custody_content_sha256": plan["content_sha256"],
            "receipt_root": archive / "_PURGE_RECEIPTS",
            "owner_probe": effective_owner_probe,
        }
        if reclaim_mode == "contents":
            purge = purge_custody_proven_contents(**arguments)
        else:
            purge = purge_custody_proven_path(
                **arguments,
                root_prepare=_remove_root_delete_acl,
            )
    except WorktreeAbandonmentError as exc:
        raise PersonalCustodyError("custody-reclaim-denied", str(exc).splitlines()[0]) from exc
    completed = {
        **archive_receipt,
        "status": "reclaimed",
        "updated_at": _now(),
        "copies": {
            **archive_receipt["copies"],
            "archive": {
                **archive_receipt["copies"]["archive"],
                "restore": archive_restore,
            },
            "recovery": {
                **archive_receipt["copies"]["recovery"],
                "restore": recovery_restore,
            },
        },
        "reclaimed": True,
        "purge_receipt_sha256": _canonical_sha256(purge),
    }
    completed.pop("receipt_sha256", None)
    completed["receipt_sha256"] = _canonical_sha256(completed)
    _atomic_json(archive / relative_receipt, completed)
    _atomic_json(recovery / relative_receipt, completed)
    public = {
        "schema": PUBLIC_RECEIPT_SCHEMA,
        "event": "internal_copy_reclaimed",
        "recorded_at": _now(),
        "label": plan["label"],
        "reclaim_mode": reclaim_mode,
        "inventory_sha256": plan["inventory"]["sha256"],
        "plan_sha256": expected_plan_sha256,
        "content_sha256": plan["content_sha256"],
        "receipt_sha256": completed["receipt_sha256"],
        "file_count": plan["file_count"],
        "size_bytes": plan["size_bytes"],
        "physical_bytes": plan["physical_bytes"],
        "copy_count": 2,
        "independent_physical_devices": True,
        "restoration_passed": True,
        "reclaimed": True,
    }
    if public_receipt_path is not None:
        _append_public_receipt(public_receipt_path, public)
    return public


def _append_public_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event_key = (
        payload.get("event"),
        payload.get("label"),
        payload.get("plan_sha256"),
    )
    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            existing = [
                value
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and isinstance((value := json.loads(line)), dict)
            ]
        except (OSError, json.JSONDecodeError) as exc:
            raise PersonalCustodyError("public-receipt-ledger-invalid") from exc
    if any((value.get("event"), value.get("label"), value.get("plan_sha256")) == event_key for value in existing):
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            for value in [*existing, payload]:
                handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--inventory", type=Path, required=True)
    plan.add_argument("--label", required=True)
    plan.add_argument("--source", type=Path, required=True)
    plan.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    plan.add_argument("--recovery-root", type=Path, default=DEFAULT_RECOVERY_ROOT)
    plan.add_argument("--private-root", type=Path, default=DEFAULT_PRIVATE_ROOT)
    plan.add_argument("--reclaim-mode", choices=("root", "contents"), default="root")
    for name in ("apply", "reclaim"):
        command = subparsers.add_parser(name)
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument("--expected-plan-sha256", required=True)
        command.add_argument("--public-receipt", type=Path)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.command == "plan":
            result = create_plan(
                inventory_path=args.inventory,
                label=args.label,
                source=args.source,
                archive_root=args.archive_root,
                recovery_root=args.recovery_root,
                private_root=args.private_root,
                reclaim_mode=args.reclaim_mode,
            )
        elif args.command == "apply":
            result = apply_plan(
                plan_path=args.plan,
                expected_plan_sha256=args.expected_plan_sha256,
                public_receipt_path=args.public_receipt,
            )
        else:
            result = reclaim_plan(
                plan_path=args.plan,
                expected_plan_sha256=args.expected_plan_sha256,
                public_receipt_path=args.public_receipt,
            )
    except PersonalCustodyError as exc:
        print(json.dumps({"schema": PUBLIC_RECEIPT_SCHEMA, "status": "blocked", "code": exc.code}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
