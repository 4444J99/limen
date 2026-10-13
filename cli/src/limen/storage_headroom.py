"""Hysteretic local-disk admission for new disposable worktrees."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import hashlib
import plistlib
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path


SCHEMA = "limen.storage_headroom.v1"
BLOCK_BELOW_BYTES = 50 * 1024**3
REENABLE_AT_BYTES = 200 * 1024**3


class StorageAdmissionError(RuntimeError):
    """New local worktree creation cannot be proven safe."""


def _state_root() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    root = Path(configured).expanduser() if configured else Path.home() / ".local" / "state"
    if not root.is_absolute() or ".." in root.parts:
        raise StorageAdmissionError("storage-admission-state-unavailable")
    return root / "limen"


def _existing_volume_path(target: Path) -> Path:
    try:
        path = target.expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        raise StorageAdmissionError("storage-volume-unavailable") from None
    if len(path.parts) >= 3 and path.parts[1] == "Volumes":
        mount = Path(*path.parts[:3])
        if not mount.is_mount():
            raise StorageAdmissionError("storage-mount-unavailable")
    while True:
        try:
            path.stat()
            return path
        except FileNotFoundError:
            pass
        except OSError:
            raise StorageAdmissionError("storage-volume-unavailable") from None
        parent = path.parent
        if parent == path:
            raise StorageAdmissionError("storage-volume-unavailable")
        path = parent


def storage_identity(path: Path) -> str:
    """Verified capacity pool identity; APFS siblings share a container UUID."""
    if sys.platform != "darwin":
        return f"device:{path.stat().st_dev}"
    try:
        result = subprocess.run(["df", "-P", str(path)], capture_output=True, check=True, timeout=5)
        device = result.stdout.decode().splitlines()[-1].split()[0]
        if not device.startswith("/dev/"):
            raise ValueError("unidentified device")

        def info(name):
            result = subprocess.run(["diskutil", "info", "-plist", name], capture_output=True, check=True, timeout=5)
            return plistlib.loads(result.stdout)

        volume = info(device)
        if volume.get("FilesystemType") == "apfs":
            container = info(volume["APFSContainerReference"])
            return "apfs:" + str(uuid.UUID(container["DiskUUID"]))
        return "volume:" + str(uuid.UUID(volume["VolumeUUID"]))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
        raise StorageAdmissionError("storage-identity-unavailable") from None


def _load_latch(path: Path) -> bool:
    if path.is_symlink():
        raise StorageAdmissionError("storage-admission-state-invalid")
    if not path.exists():
        return False
    if not path.is_file() or path.stat().st_uid != os.getuid():
        raise StorageAdmissionError("storage-admission-state-invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise StorageAdmissionError("storage-admission-state-invalid") from None
    if (
        not isinstance(value, dict)
        or value.get("schema") != SCHEMA
        or not isinstance(value.get("blocked"), bool)
        or type(value.get("observed_free_bytes")) is not int
        or value["observed_free_bytes"] < 0
    ):
        raise StorageAdmissionError("storage-admission-state-invalid")
    return value["blocked"]


def _store_latch(path: Path, *, blocked: bool, free_bytes: int) -> None:
    payload = {
        "schema": SCHEMA,
        "blocked": blocked,
        "observed_free_bytes": free_bytes,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    descriptor, temporary_name = tempfile.mkstemp(prefix="storage-headroom-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def require_storage_headroom(target: str | Path) -> None:
    """Deny new worktrees below 50 GiB, and keep the latch until 200 GiB."""
    volume_path = _existing_volume_path(Path(target))
    identity = storage_identity(volume_path)
    internal = identity == storage_identity(Path.home())
    try:
        volume_stats = os.statvfs(volume_path)
        free_bytes = volume_stats.f_bavail * volume_stats.f_frsize
    except OSError:
        raise StorageAdmissionError("storage-volume-unavailable") from None

    state_root = _state_root()
    try:
        state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        state_stat = state_root.stat()
        if state_root.is_symlink() or state_stat.st_uid != os.getuid() or state_stat.st_mode & 0o077:
            raise StorageAdmissionError("storage-admission-state-invalid")
        lock_path = state_root / "storage-headroom.lock"
        legacy_path = state_root / "storage-headroom.json"
        state_path = state_root / ("storage-headroom-" + hashlib.sha256(identity.encode()).hexdigest() + ".json")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            blocked = _load_latch(state_path)
            # External observations cannot clear the old internal restriction.
            if internal:
                blocked = _load_latch(legacy_path) or blocked
            if free_bytes < BLOCK_BELOW_BYTES:
                blocked = True
            elif free_bytes >= REENABLE_AT_BYTES:
                blocked = False
            _store_latch(state_path, blocked=blocked, free_bytes=free_bytes)
            if internal:
                _store_latch(legacy_path, blocked=blocked, free_bytes=free_bytes)
        finally:
            os.close(fd)
    except StorageAdmissionError:
        raise
    except OSError:
        raise StorageAdmissionError("storage-admission-state-unavailable") from None

    if blocked:
        raise StorageAdmissionError("storage-headroom-latched-until-200-gib-free")


__all__ = ["BLOCK_BELOW_BYTES", "REENABLE_AT_BYTES", "StorageAdmissionError", "require_storage_headroom"]
