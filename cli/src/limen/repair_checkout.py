"""One retained bounded repair checkout, admitted by the existing execution owner."""

from datetime import UTC, datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import re

from limen.storage_headroom import StorageAdmissionError, _existing_volume_path, _state_root, storage_identity

MAX_BYTES = 256 * 1024**2
FLOOR_BYTES = 10 * 1024**3


def allocated_bytes(path: Path) -> int:
    total = path.lstat().st_blocks * 512
    if path.is_dir() and not path.is_symlink():
        for directory, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                total += (Path(directory) / name).lstat().st_blocks * 512
    return total


def create_repair_checkout(
    client, work_key: str, repository: Path, destination: Path, revision: str, budget: int = MAX_BYTES
) -> dict:
    """No clone/install/hydration; ambiguous effects keep their reservation."""
    now = datetime.now(UTC)
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise StorageAdmissionError("repair-exact-revision-required")
    admission = client.execution_info(work_key)
    deadline = datetime.fromisoformat(admission["attempt_deadline"].replace("Z", "+00:00"))
    remaining = (deadline - now).total_seconds()
    if (
        admission.get("storage_repair") is not True
        or not 0 < remaining <= 1800
        or admission.get("verification_seconds", 601) > 600
    ):
        raise StorageAdmissionError("repair-execution-admission-required")
    if type(budget) is not int or not 0 < budget <= MAX_BYTES:
        raise StorageAdmissionError("repair-allocation-invalid")
    destination = destination.absolute()
    if destination.exists() or any(p.is_symlink() for p in (destination, *destination.parents)):
        raise StorageAdmissionError("repair-destination-invalid")
    volume = _existing_volume_path(destination)
    identity = storage_identity(volume)
    stats = os.statvfs(volume)
    if stats.f_bavail * stats.f_frsize <= budget + FLOOR_BYTES:
        raise StorageAdmissionError("repair-storage-floor")
    listing = subprocess.run(
        ["git", "-C", str(repository), "ls-tree", "-rl", revision],
        capture_output=True,
        text=True,
        timeout=min(5, remaining),
        check=True,
    )
    estimate = sum(
        ((int(line.split()[3]) + 4095) // 4096) * 4096
        for line in listing.stdout.splitlines()
        if line.split()[3].isdigit()
    )
    if estimate > budget:
        raise StorageAdmissionError("repair-checkout-estimate-exceeds-budget")
    root = _state_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise StorageAdmissionError("storage-admission-state-invalid")
    fd = os.open(root / "repair-checkout.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = root / "repair-checkout.json"
        if state.exists() or state.is_symlink():
            raise StorageAdmissionError("repair-checkout-retention-unresolved")
        receipt = {
            "schema": "limen.repair_checkout.v1",
            "run_id": admission["run_id"],
            "outcome_id": admission["outcome_id"],
            "deadline": deadline.isoformat(),
            "target": str(destination),
            "storage_identity": identity,
            "budget_bytes": budget,
            "status": "reserved",
            "disposition": "retained-owner-custody-required",
        }
        # Exclusive creation survives interruption and never renews an allowance.
        with state.open("x") as handle:
            os.chmod(state, 0o600)
            json.dump(receipt, handle)
            handle.flush()
            os.fsync(handle.fileno())
        import hashlib

        client.reserve_growth(work_key, "worktree", hashlib.sha256(str(destination).encode()).hexdigest())
        remaining = (deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise StorageAdmissionError("repair-attempt-exhausted-retained")
        subprocess.run(
            ["git", "-C", str(repository), "worktree", "add", "--detach", "--", str(destination), revision],
            capture_output=True,
            timeout=remaining,
            check=True,
        )
        stats = os.statvfs(destination)
        actual = allocated_bytes(destination)
        if (
            storage_identity(destination) != identity
            or actual > budget
            or stats.f_bavail * stats.f_frsize <= FLOOR_BYTES
        ):
            raise StorageAdmissionError("repair-checkout-allocation-exceeded-retained")
        if datetime.now(UTC) >= deadline:
            raise StorageAdmissionError("repair-attempt-exhausted-retained")
        receipt.update(status="admitted", allocated_bytes=actual)
        state.write_text(json.dumps(receipt))
        return receipt
    except BlockingIOError:
        raise StorageAdmissionError("repair-writer-occupied") from None
    finally:
        os.close(fd)
