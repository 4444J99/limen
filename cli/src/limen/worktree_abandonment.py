"""Recoverable, crash-visible abandonment of local worktree material."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NoReturn

WORKTREE_ABANDONMENT_SCHEMA = "limen.worktree_abandonment.v1"
AbandonmentAction = Literal[
    "detach-worktree",
    "purge-proven-path",
    "quarantine",
    "remove-stable-lock",
]
AbandonmentState = Literal["planned", "verified", "applying", "completed", "crashed"]
OwnerProbe = Callable[[Path], int | None]
RootPrepare = Callable[[Path], None]
ContentProbe = Callable[[Path], None]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OBJECT_ID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


@dataclass(frozen=True)
class LockIdentity:
    path: str
    device: int
    inode: int
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class CustodyPathIdentity:
    path: str
    path_sha256: str
    device: int
    inode: int
    mtime_ns: int


class WorktreeAbandonmentError(RuntimeError):
    """An abandonment stopped fail-closed and left a typed receipt."""

    def __init__(self, message: str, *, receipt_path: Path, receipt: dict[str, Any]):
        self.receipt_path = receipt_path
        self.receipt = receipt
        super().__init__(message)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _run_git(repo: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(["git", "-C", str(repo), *args], 1, "", str(exc))


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _receipt_path(receipt_root: Path, action: AbandonmentAction, target: Path) -> Path:
    digest = hashlib.sha256(f"{action}\0{target}\0{secrets.token_hex(16)}".encode()).hexdigest()
    return receipt_root / f"{digest}.json"


def _new_receipt(
    *,
    receipt_root: Path,
    action: AbandonmentAction,
    target: Path,
    reason: str,
) -> tuple[Path, dict[str, Any]]:
    receipt_path = _receipt_path(receipt_root, action, target)
    receipt: dict[str, Any] = {
        "schema": WORKTREE_ABANDONMENT_SCHEMA,
        "action": action,
        "state": "planned",
        "phase": "preflight",
        "created_at": _now(),
        "updated_at": _now(),
        "target": str(target),
        "reason": reason,
        "result": None,
        "crash": None,
    }
    _atomic_json(receipt_path, receipt)
    return receipt_path, receipt


def _write_state(
    receipt_path: Path,
    receipt: dict[str, Any],
    *,
    state: AbandonmentState,
    phase: str,
    result: dict[str, Any] | None = None,
    crash_code: str | None = None,
    crash_detail: str | None = None,
) -> dict[str, Any]:
    updated = {
        **receipt,
        "state": state,
        "phase": phase,
        "updated_at": _now(),
        "result": result if result is not None else receipt.get("result"),
        "crash": (
            {"code": crash_code, "detail": crash_detail}
            if crash_code is not None and crash_detail is not None
            else None
        ),
    }
    _atomic_json(receipt_path, updated)
    return updated


def _raise_crash(
    receipt_path: Path,
    receipt: dict[str, Any],
    *,
    phase: str,
    code: str,
    detail: str,
) -> NoReturn:
    crashed = _write_state(
        receipt_path,
        receipt,
        state="crashed",
        phase=phase,
        crash_code=code,
        crash_detail=detail[:500],
    )
    raise WorktreeAbandonmentError(
        f"{code}: {detail}",
        receipt_path=receipt_path,
        receipt=crashed,
    )


def _registered_worktree_paths(superproject: Path) -> tuple[Path, ...]:
    listed = _run_git(superproject, "worktree", "list", "--porcelain")
    if listed.returncode != 0:
        raise RuntimeError((listed.stderr or listed.stdout or "worktree-list-unavailable").strip())
    paths: list[Path] = []
    for line in listed.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        try:
            paths.append(Path(line.removeprefix("worktree ")).resolve(strict=True))
        except OSError as exc:
            raise RuntimeError("registered-worktree-path-unavailable") from exc
    return tuple(paths)


def _default_cwd_owner_probe(target: Path) -> int | None:
    """Return an owning cwd PID, -1 when the unprivileged probe is unavailable."""

    try:
        result = subprocess.run(
            ["/usr/sbin/lsof", "-n", "-a", "-d", "cwd", "-Fpn"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return -1
    if result.returncode not in {0, 1}:
        return -1
    try:
        root = target.resolve(strict=True)
    except OSError:
        return -1
    pid: int | None = None
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            try:
                pid = int(line[1:])
            except ValueError:
                pid = None
        elif line.startswith("n/") and pid is not None:
            try:
                cwd = Path(line[1:]).resolve(strict=True)
            except OSError:
                continue
            if cwd == root or root in cwd.parents:
                return pid
    return None


def detach_registered_worktree(
    superproject: Path,
    target: Path,
    *,
    reason: str,
    receipt_root: Path,
    owner_probe: OwnerProbe | None = None,
) -> dict[str, Any]:
    """Detach one clean registered worktree using Git's non-forced native operation."""

    receipt_path, receipt = _new_receipt(
        receipt_root=receipt_root,
        action="detach-worktree",
        target=target,
        reason=reason,
    )
    phase = "preflight"
    try:
        superproject = superproject.resolve(strict=True)
        target = target.resolve(strict=True)
        if superproject == target:
            raise RuntimeError("target-is-superproject")
        gitfile = target / ".git"
        gitfile_stat = gitfile.lstat()
        if not stat.S_ISREG(gitfile_stat.st_mode) or gitfile.is_symlink():
            raise RuntimeError("target-is-not-linked-worktree")
        registered = _registered_worktree_paths(superproject)
        if target not in registered:
            raise RuntimeError("target-not-registered")
        owner = (owner_probe or _default_cwd_owner_probe)(target)
        if owner is not None:
            code = "owner-probe-unavailable" if owner == -1 else f"active-process-cwd:{owner}"
            raise RuntimeError(code)
        status = _run_git(target, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        if status.returncode != 0:
            raise RuntimeError("worktree-status-unavailable")
        if status.stdout:
            raise RuntimeError("worktree-not-clean")
        head = _run_git(target, "rev-parse", "HEAD")
        if head.returncode != 0 or not head.stdout.strip():
            raise RuntimeError("worktree-head-unavailable")
        receipt = _write_state(
            receipt_path,
            receipt,
            state="verified",
            phase="verify",
            result={"head": head.stdout.strip(), "registered": True, "clean": True},
        )
        phase = "detach"
        receipt = _write_state(receipt_path, receipt, state="applying", phase=phase)
        detached = _run_git(superproject, "worktree", "remove", str(target))
        if detached.returncode != 0:
            raise RuntimeError(
                f"git-worktree-remove-failed: {(detached.stderr or detached.stdout or 'unknown').strip()[:300]}"
            )
        if target.exists() or target.is_symlink():
            raise RuntimeError("target-remains-after-detach")
        if target in _registered_worktree_paths(superproject):
            raise RuntimeError("target-remains-registered")
        completed = _write_state(
            receipt_path,
            receipt,
            state="completed",
            phase="verify-final",
            result={**dict(receipt.get("result") or {}), "detached": True},
        )
        return {**completed, "receipt_path": str(receipt_path)}
    except WorktreeAbandonmentError:
        raise
    except Exception as exc:
        _raise_crash(
            receipt_path,
            receipt,
            phase=phase,
            code="detach-denied",
            detail=str(exc),
        )


def quarantine_path(
    source: Path,
    quarantine_root: Path,
    *,
    reason: str,
    receipt_root: Path,
    destination_name: str | None = None,
    owner_probe: OwnerProbe | None = None,
) -> dict[str, Any]:
    """Atomically move one path into same-filesystem recoverable quarantine."""

    receipt_path, receipt = _new_receipt(
        receipt_root=receipt_root,
        action="quarantine",
        target=source,
        reason=reason,
    )
    phase = "preflight"
    try:
        raw = source.lstat()
        if stat.S_ISLNK(raw.st_mode):
            raise RuntimeError("source-is-symlink")
        source = source.resolve(strict=True)
        owner = (owner_probe or _default_cwd_owner_probe)(source)
        if owner is not None:
            code = "owner-probe-unavailable" if owner == -1 else f"active-process-cwd:{owner}"
            raise RuntimeError(code)
        proposed_quarantine_root = quarantine_root.expanduser().resolve(strict=False)
        if (
            proposed_quarantine_root == source
            or source in proposed_quarantine_root.parents
            or proposed_quarantine_root in source.parents
        ):
            raise RuntimeError("quarantine-source-destination-nesting")
        proposed_quarantine_root.mkdir(parents=True, exist_ok=True)
        quarantine_root = proposed_quarantine_root.resolve(strict=True)
        if quarantine_root == source or source in quarantine_root.parents or quarantine_root in source.parents:
            raise RuntimeError("quarantine-source-destination-nesting")
        if not _same_filesystem(source, quarantine_root):
            raise RuntimeError("cross-filesystem-quarantine-denied")
        name = destination_name or source.name
        if not name or name in {".", ".."} or Path(name).name != name:
            raise RuntimeError("invalid-destination-name")
        destination = quarantine_root / name
        if destination.exists() or destination.is_symlink():
            raise RuntimeError("quarantine-destination-exists")
        receipt = _write_state(
            receipt_path,
            receipt,
            state="verified",
            phase="verify",
            result={
                "source_device": source.stat().st_dev,
                "destination": str(destination),
                "recoverable": True,
            },
        )
        phase = "move"
        receipt = _write_state(receipt_path, receipt, state="applying", phase=phase)
        os.rename(source, destination)
        if source.exists() or source.is_symlink() or not destination.exists():
            raise RuntimeError("atomic-move-postcondition-failed")
        completed = _write_state(
            receipt_path,
            receipt,
            state="completed",
            phase="verify-final",
            result={**dict(receipt.get("result") or {}), "moved": True},
        )
        return {**completed, "receipt_path": str(receipt_path)}
    except WorktreeAbandonmentError:
        raise
    except Exception as exc:
        _raise_crash(
            receipt_path,
            receipt,
            phase=phase,
            code="quarantine-denied",
            detail=str(exc),
        )


def _same_filesystem(source: Path, destination_root: Path) -> bool:
    return source.stat().st_dev == destination_root.stat().st_dev


def _custody_identity_matches(path: Path, expected: CustodyPathIdentity) -> bool:
    try:
        raw = path.lstat()
        actual_path = str(path.resolve(strict=True))
    except OSError:
        return False
    return (
        actual_path == expected.path
        and hashlib.sha256(actual_path.encode("utf-8", errors="surrogateescape")).hexdigest() == expected.path_sha256
        and not stat.S_ISLNK(raw.st_mode)
        and stat.S_ISDIR(raw.st_mode)
        and raw.st_dev == expected.device
        and raw.st_ino == expected.inode
        and raw.st_mtime_ns == expected.mtime_ns
    )


def _purge_directory_fd(directory_fd: int) -> None:
    """Unlink one already-isolated directory tree without following symlinks."""

    for name in os.listdir(directory_fd):
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(entry.st_mode):
            flags = os.O_RDONLY | os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            child_fd = os.open(name, flags, dir_fd=directory_fd)
            try:
                child = os.fstat(child_fd)
                if (child.st_dev, child.st_ino) != (entry.st_dev, entry.st_ino):
                    raise RuntimeError("purge-child-identity-changed")
                _purge_directory_fd(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


def _purge_proven_path(
    source: Path,
    expected: CustodyPathIdentity,
    *,
    reason: str,
    allowed_reasons: frozenset[str],
    proof: dict[str, Any],
    receipt_root: Path,
    owner_probe: OwnerProbe | None = None,
    root_prepare: RootPrepare | None = None,
    content_probe: ContentProbe | None = None,
    retain_empty_root: bool = False,
) -> dict[str, Any]:
    """Purge one exact directory after its typed owner proves replacement custody."""

    receipt_path, receipt = _new_receipt(
        receipt_root=receipt_root,
        action="purge-proven-path",
        target=source,
        reason=reason,
    )
    phase = "preflight"
    staging: Path | None = None
    try:
        if reason not in allowed_reasons:
            raise RuntimeError("proven-purge-reason-invalid")
        if not _custody_identity_matches(source, expected):
            raise RuntimeError("proven-path-identity-mismatch")
        if content_probe is not None:
            content_probe(source)
        owner = (owner_probe or _default_cwd_owner_probe)(source)
        if owner is not None:
            code = "owner-probe-unavailable" if owner == -1 else f"active-process-cwd:{owner}"
            raise RuntimeError(code)
        if not _custody_identity_matches(source, expected):
            raise RuntimeError("proven-path-identity-changed-after-owner-probe")
        if content_probe is not None:
            content_probe(source)
        if root_prepare is not None:
            root_prepare(source)
            if not _custody_identity_matches(source, expected):
                raise RuntimeError("proven-path-identity-changed-after-root-prepare")
            owner = (owner_probe or _default_cwd_owner_probe)(source)
            if owner is not None:
                code = "owner-probe-unavailable" if owner == -1 else f"active-process-cwd:{owner}"
                raise RuntimeError(code)
        if content_probe is not None:
            # This is the final content rehash before rename or fd-isolated
            # destruction. A plan-time or pre-owner hash is not deletion proof.
            content_probe(source)
        staging = source.parent / f".{source.name}.proven-purge-{receipt_path.stem[:16]}"
        if staging.exists() or staging.is_symlink():
            raise RuntimeError("proven-purge-staging-exists")
        receipt = _write_state(
            receipt_path,
            receipt,
            state="verified",
            phase="verify",
            result={
                "identity": asdict(expected),
                "proof": proof,
                "staging": None if retain_empty_root else str(staging),
                "owner": None,
                "retained_empty_root": retain_empty_root,
            },
        )
        if retain_empty_root:
            phase = "purge"
            receipt = _write_state(receipt_path, receipt, state="applying", phase=phase)
            flags = os.O_RDONLY | os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            source_fd = os.open(source, flags)
            try:
                isolated = os.fstat(source_fd)
                if (isolated.st_dev, isolated.st_ino) != (expected.device, expected.inode):
                    raise RuntimeError("proven-purge-root-identity-mismatch")
                _purge_directory_fd(source_fd)
            finally:
                os.close(source_fd)
            if not source.is_dir() or any(source.iterdir()):
                raise RuntimeError("proven-purge-root-not-empty")
            completed = _write_state(
                receipt_path,
                receipt,
                state="completed",
                phase="verify-final",
                result={
                    **dict(receipt.get("result") or {}),
                    "purged": True,
                    "retained_empty_root": True,
                },
            )
            return {**completed, "receipt_path": str(receipt_path)}
        phase = "isolate"
        receipt = _write_state(receipt_path, receipt, state="applying", phase=phase)
        os.rename(source, staging)
        if source.exists() or source.is_symlink():
            raise RuntimeError("proven-purge-source-remains")
        flags = os.O_RDONLY | os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        staging_fd = os.open(staging, flags)
        try:
            isolated = os.fstat(staging_fd)
            if (isolated.st_dev, isolated.st_ino) != (expected.device, expected.inode):
                raise RuntimeError("proven-purge-isolated-identity-mismatch")
            phase = "purge"
            receipt = _write_state(receipt_path, receipt, state="applying", phase=phase)
            _purge_directory_fd(staging_fd)
        finally:
            os.close(staging_fd)
        os.rmdir(staging)
        if staging.exists() or staging.is_symlink():
            raise RuntimeError("proven-purge-staging-remains")
        completed = _write_state(
            receipt_path,
            receipt,
            state="completed",
            phase="verify-final",
            result={**dict(receipt.get("result") or {}), "purged": True},
        )
        return {**completed, "receipt_path": str(receipt_path)}
    except WorktreeAbandonmentError:
        raise
    except Exception as exc:
        _raise_crash(
            receipt_path,
            receipt,
            phase=phase,
            code="proven-path-purge-denied",
            detail=str(exc),
        )


def purge_custody_proven_path(
    source: Path,
    expected: CustodyPathIdentity,
    *,
    reason: str,
    custody_plan_sha256: str,
    custody_content_sha256: str,
    receipt_root: Path,
    owner_probe: OwnerProbe | None = None,
    root_prepare: RootPrepare | None = None,
    content_probe: ContentProbe | None = None,
) -> dict[str, Any]:
    """Purge one exact directory only after full external restoration proof."""

    if not SHA256_RE.fullmatch(custody_plan_sha256) or not SHA256_RE.fullmatch(custody_content_sha256):
        raise ValueError("custody-purge-digest-invalid")
    return _purge_proven_path(
        source,
        expected,
        reason=reason,
        allowed_reasons=frozenset({"custody-restored+idle"}),
        proof={
            "kind": "external-restoration",
            "custody_plan_sha256": custody_plan_sha256,
            "custody_content_sha256": custody_content_sha256,
        },
        receipt_root=receipt_root,
        owner_probe=owner_probe,
        root_prepare=root_prepare,
        content_probe=content_probe,
    )


def purge_custody_proven_contents(
    source: Path,
    expected: CustodyPathIdentity,
    *,
    reason: str,
    custody_plan_sha256: str,
    custody_content_sha256: str,
    receipt_root: Path,
    owner_probe: OwnerProbe | None = None,
    content_probe: ContentProbe | None = None,
) -> dict[str, Any]:
    """Empty one exact directory after restoration proof while retaining its shell."""

    if not SHA256_RE.fullmatch(custody_plan_sha256) or not SHA256_RE.fullmatch(custody_content_sha256):
        raise ValueError("custody-purge-digest-invalid")
    return _purge_proven_path(
        source,
        expected,
        reason=reason,
        allowed_reasons=frozenset({"custody-restored+idle"}),
        proof={
            "kind": "external-restoration",
            "custody_plan_sha256": custody_plan_sha256,
            "custody_content_sha256": custody_content_sha256,
        },
        receipt_root=receipt_root,
        owner_probe=owner_probe,
        content_probe=content_probe,
        retain_empty_root=True,
    )


def purge_remote_proven_path(
    source: Path,
    expected: CustodyPathIdentity,
    *,
    reason: str,
    head: str,
    remote_refs: tuple[str, ...],
    local_ref_proof: tuple[dict[str, Any], ...],
    receipt_root: Path,
    owner_probe: OwnerProbe | None = None,
    content_probe: ContentProbe | None = None,
) -> dict[str, Any]:
    """Purge one clean clone whose exact HEAD is reachable from a remote ref."""

    if not OBJECT_ID_RE.fullmatch(head):
        raise ValueError("remote-purge-head-invalid")
    if not remote_refs or any(
        not value.startswith("refs/remotes/") or "\n" in value or "\r" in value for value in remote_refs
    ):
        raise ValueError("remote-purge-refs-invalid")
    if not local_ref_proof or any(
        not isinstance(value.get("local_ref"), str)
        or not isinstance(value.get("object"), str)
        or not isinstance(value.get("remote_refs"), list)
        or not value["remote_refs"]
        for value in local_ref_proof
    ):
        raise ValueError("remote-purge-local-ref-proof-invalid")
    return _purge_proven_path(
        source,
        expected,
        reason=reason,
        allowed_reasons=frozenset(
            {
                "clean+merged+idle",
                "clean+pushed+idle",
                "receipt-remote-merged+clean+idle",
            }
        ),
        proof={
            "kind": "remote-all-local-refs",
            "head": head,
            "remote_refs": list(remote_refs),
            "local_refs": list(local_ref_proof),
        },
        receipt_root=receipt_root,
        owner_probe=owner_probe,
        content_probe=content_probe,
    )


def capture_lock_identity(lock_path: Path) -> LockIdentity:
    """Capture the exact regular zero-byte lock identity for a later approved removal."""

    raw = lock_path.lstat()
    if stat.S_ISLNK(raw.st_mode) or not stat.S_ISREG(raw.st_mode):
        raise ValueError("lock-is-not-regular-file")
    if raw.st_size != 0:
        raise ValueError("lock-is-not-zero-byte")
    resolved_parent = lock_path.parent.resolve(strict=True)
    return LockIdentity(
        path=str(resolved_parent / lock_path.name),
        device=raw.st_dev,
        inode=raw.st_ino,
        size=raw.st_size,
        mtime_ns=raw.st_mtime_ns,
    )


def _exact_open_owner_probe(lock_path: Path) -> int | None:
    try:
        result = subprocess.run(
            ["lsof", "-n", "-Fpn", "--", str(lock_path)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return -1
    if result.returncode not in {0, 1}:
        return -1
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            try:
                return int(line[1:])
            except ValueError:
                return -1
    return None


def _identity_matches(lock_path: Path, expected: LockIdentity) -> bool:
    try:
        raw = lock_path.lstat()
        actual_path = str(lock_path.parent.resolve(strict=True) / lock_path.name)
    except OSError:
        return False
    return (
        actual_path == expected.path
        and not stat.S_ISLNK(raw.st_mode)
        and stat.S_ISREG(raw.st_mode)
        and raw.st_dev == expected.device
        and raw.st_ino == expected.inode
        and raw.st_size == expected.size == 0
        and raw.st_mtime_ns == expected.mtime_ns
    )


def remove_stable_zero_byte_lock(
    lock_path: Path,
    expected: LockIdentity,
    *,
    reason: str,
    receipt_root: Path,
    owner_probe: OwnerProbe | None = None,
) -> dict[str, Any]:
    """Remove only an exact, stable, unowned zero-byte lock file."""

    receipt_path, receipt = _new_receipt(
        receipt_root=receipt_root,
        action="remove-stable-lock",
        target=lock_path,
        reason=reason,
    )
    phase = "preflight"
    try:
        if not _identity_matches(lock_path, expected):
            raise RuntimeError("lock-identity-mismatch")
        first = lock_path.lstat()
        second = lock_path.lstat()
        if (
            first.st_dev,
            first.st_ino,
            first.st_size,
            first.st_mtime_ns,
        ) != (
            second.st_dev,
            second.st_ino,
            second.st_size,
            second.st_mtime_ns,
        ):
            raise RuntimeError("lock-identity-not-stable")
        owner = (owner_probe or _exact_open_owner_probe)(lock_path)
        if owner is not None:
            code = "owner-probe-unavailable" if owner == -1 else f"lock-open-by-process:{owner}"
            raise RuntimeError(code)
        if not _identity_matches(lock_path, expected):
            raise RuntimeError("lock-identity-changed-after-owner-probe")
        receipt = _write_state(
            receipt_path,
            receipt,
            state="verified",
            phase="verify",
            result={"identity": asdict(expected), "owner": None},
        )
        phase = "remove-exact-lock"
        receipt = _write_state(receipt_path, receipt, state="applying", phase=phase)
        os.unlink(lock_path)
        if lock_path.exists() or lock_path.is_symlink():
            raise RuntimeError("lock-remains-after-removal")
        completed = _write_state(
            receipt_path,
            receipt,
            state="completed",
            phase="verify-final",
            result={**dict(receipt.get("result") or {}), "removed": True},
        )
        return {**completed, "receipt_path": str(receipt_path)}
    except WorktreeAbandonmentError:
        raise
    except Exception as exc:
        _raise_crash(
            receipt_path,
            receipt,
            phase=phase,
            code="stable-lock-removal-denied",
            detail=str(exc),
        )


__all__ = [
    "WORKTREE_ABANDONMENT_SCHEMA",
    "CustodyPathIdentity",
    "LockIdentity",
    "WorktreeAbandonmentError",
    "capture_lock_identity",
    "detach_registered_worktree",
    "purge_custody_proven_contents",
    "purge_custody_proven_path",
    "purge_remote_proven_path",
    "quarantine_path",
    "remove_stable_zero_byte_lock",
]
