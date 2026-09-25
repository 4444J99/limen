"""Recoverable, crash-visible abandonment of local worktree material."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import time
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
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
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
            # A stale, already-missing registration elsewhere in the repository
            # must not block retirement of this independently revalidated target.
            paths.append(Path(line.removeprefix("worktree ")).resolve(strict=False))
        except OSError as exc:
            raise RuntimeError("registered-worktree-path-unavailable") from exc
    return tuple(paths)


def _nested_payload_custody_reason(target: Path) -> str | None:
    """Retain populated Gitlinks and LFS payloads; empty Gitlinks hold no bytes.

    This check is for linked-checkout retirement: the common repository and its
    module object stores remain resident. An absent/empty uninitialized Gitlink
    has only its tracked pointer, already covered by the parent commit's custody.
    Never follow a symlink to decide that a nested checkout is empty.
    """
    tracked = _run_git(target, "ls-files", "--stage", "-z")
    if tracked.returncode != 0:
        return "tracked-file-inventory-unavailable"
    for entry in tracked.stdout.split("\x00"):
        if not entry.startswith("160000 "):
            continue
        fields = entry.split("\t", 1)
        if len(fields) != 2:
            return "submodule-custody-unproven"
        relative = Path(fields[1])
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            return "submodule-custody-unproven"
        nested = target
        try:
            for part in relative.parts:
                nested = nested / part
                if nested.is_symlink():
                    return "submodule-custody-unproven"
            if nested.exists() and (not nested.is_dir() or any(nested.iterdir())):
                return "submodule-custody-unproven"
        except OSError:
            return "submodule-custody-unproven"
    lfs = _run_git(target, "lfs", "ls-files", "--name-only")
    if lfs.returncode != 0:
        return "lfs-inventory-unavailable"
    if lfs.stdout.strip():
        return "lfs-custody-unproven"
    return None


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


def _admin_inventory(root: Path) -> dict[str, tuple[str, int, int]]:
    """Bounded byte/mode/time evidence; never follow links or silently omit entries."""
    inventory: dict[str, tuple[str, int, int]] = {}
    deadline = time.monotonic() + 30
    total = 0

    def visit(directory: Path) -> None:
        nonlocal total
        for path in sorted(directory.iterdir()):
            before = path.lstat()
            if len(inventory) >= 4096 or time.monotonic() >= deadline:
                raise RuntimeError("worktree-admin-inventory-limit")
            relative = str(path.relative_to(root))
            if relative in {
                "MERGE_HEAD",
                "MERGE_AUTOSTASH",
                "CHERRY_PICK_HEAD",
                "REVERT_HEAD",
                "REBASE_HEAD",
                "rebase-merge",
                "rebase-apply",
                "sequencer",
                "BISECT_LOG",
                "BISECT_START",
            }:
                raise RuntimeError("worktree-operation-in-progress")
            mode = stat.S_IMODE(before.st_mode)
            if stat.S_ISDIR(before.st_mode):
                inventory[relative] = ("directory", mode, before.st_mtime_ns)
                visit(path)
            elif stat.S_ISREG(before.st_mode):
                if path.name.endswith(".lock") or path.name == "locked":
                    raise RuntimeError("worktree-admin-locked")
                total += before.st_size
                if total > 256 * 1024 * 1024:
                    raise RuntimeError("worktree-admin-inventory-limit")
                with path.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha256").hexdigest()
                    after = os.fstat(handle.fileno())
                current = path.lstat()
                attributes = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode")
                identity = tuple(getattr(before, key) for key in attributes)
                if any(tuple(getattr(value, key) for key in attributes) != identity for value in (after, current)):
                    raise RuntimeError("worktree-admin-changed")
                inventory[relative] = (digest, mode, before.st_mtime_ns)
            else:
                raise RuntimeError("worktree-admin-unsupported-entry")

    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("worktree-admin-unavailable")
    visit(root)
    return inventory


def _anchor_admin_objects(superproject: Path, admin: Path, receipt_id: str) -> int:
    """Keep per-worktree refs and both sides of reflogs reachable after detach."""
    objects: set[str] = set()
    for relative in _admin_inventory(admin):
        path = admin / relative
        parts = Path(relative).parts
        if not path.is_file():
            continue
        is_log = parts[0] == "logs"
        is_ref = parts[0] == "refs" or path.name in {"HEAD", "ORIG_HEAD", "FETCH_HEAD", "AUTO_MERGE"}
        if not (is_log or is_ref):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            tokens = line.split()
            if not tokens or (is_ref and tokens[0] == "ref:"):
                continue
            ids = tokens[:2] if is_log else tokens[:1]
            if is_log and len(ids) != 2:
                raise RuntimeError("worktree-admin-invalid-reflog")
            for oid in ids:
                if not OBJECT_ID_RE.fullmatch(oid):
                    raise RuntimeError("worktree-admin-invalid-object")
                if set(oid) != {"0"}:
                    objects.add(oid)
    if objects:
        commands = (
            "start\n"
            + "".join(f"create refs/limen/retired-worktrees/{receipt_id}/{oid} {oid}\n" for oid in sorted(objects))
            + "prepare\ncommit\n"
        )
        result = subprocess.run(
            ["git", "-C", str(superproject), "update-ref", "--stdin"],
            input=commands,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("worktree-admin-object-anchor-failed")
    return len(objects)


def _preserve_worktree_admin(
    superproject: Path, target: Path, receipt_path: Path, receipt: dict[str, Any]
) -> dict[str, Any]:
    """Retain the ORIGINAL admin directory; Git removes only a verified replica.

    Rename on the same filesystem retains native ACLs, xattrs and inode metadata.
    This is local containment, not remote custody or permission to remove the store.
    The write-ahead receipt identifies both locations even across a process crash.
    """
    common_result = _run_git(superproject, "rev-parse", "--path-format=absolute", "--git-common-dir")
    admin_result = _run_git(target, "rev-parse", "--absolute-git-dir")
    if common_result.returncode or admin_result.returncode:
        raise RuntimeError("worktree-admin-location-unavailable")
    common = Path(common_result.stdout.strip()).resolve(strict=True)
    admin = Path(admin_result.stdout.strip())
    if admin.is_symlink() or admin.parent.is_symlink() or admin.parent != common / "worktrees":
        raise RuntimeError("worktree-admin-outside-common-store")
    before = _admin_inventory(admin)
    original_identity = admin.stat()
    archive_root = common / "retired-worktree-admin"
    if archive_root.is_symlink():
        raise RuntimeError("worktree-admin-archive-symlink")
    archive_root.mkdir(mode=0o700, exist_ok=True)
    archive = archive_root / receipt_path.stem
    archive.mkdir(mode=0o700)
    original = archive / "original"
    replica = archive / "replica"
    evidence = {
        "original_location": str(admin),
        "retained_original": str(original),
        "replica_location": str(replica),
        "inventory_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        "entries": len(before),
        "device": original_identity.st_dev,
        "inode": original_identity.st_ino,
        "custody": "local-original-retained-store-must-remain",
    }
    receipt = _write_state(
        receipt_path,
        receipt,
        state="verified",
        phase="preserve-admin-copy",
        result={**dict(receipt.get("result") or {}), "admin_preservation": evidence},
    )
    shutil.copytree(admin, replica, symlinks=True)
    if _admin_inventory(replica) != before or _admin_inventory(admin) != before:
        raise RuntimeError("worktree-admin-copy-mismatch")
    evidence["anchored_objects"] = _anchor_admin_objects(superproject, admin, receipt_path.stem)
    if _admin_inventory(admin) != before:
        raise RuntimeError("worktree-admin-changed-before-preservation")
    receipt = _write_state(receipt_path, receipt, state="applying", phase="preserve-admin-swap")
    admin.rename(original)
    try:
        replica.rename(admin)
    except BaseException:
        # Restore the original registration if the second rename fails. A hard
        # process crash instead leaves the write-ahead receipt and original intact.
        if not admin.exists() and not admin.is_symlink():
            original.rename(admin)
        raise
    if _admin_inventory(original) != before or _admin_inventory(admin) != before:
        raise RuntimeError("worktree-admin-changed-after-preservation")
    return _write_state(receipt_path, receipt, state="verified", phase="admin-preserved")


def recover_worktree_registration(
    superproject: Path, target: Path, receipt_root: Path, *, owner_probe: OwnerProbe | None = None
) -> None:
    """Repair only the recorded rename gap; absence alone grants no recovery action."""
    pointer = target / ".git"
    if pointer.is_symlink() or not pointer.is_file():
        raise RuntimeError("worktree-admin-pointer-unavailable")
    gitfile = pointer.read_text(encoding="utf-8").strip()
    if not gitfile.startswith("gitdir: "):
        raise RuntimeError("worktree-admin-pointer-invalid")
    admin = Path(gitfile.removeprefix("gitdir: "))
    if not admin.is_absolute():
        admin = target / admin
    if admin.exists() or admin.is_symlink():
        return
    if (owner_probe or _default_cwd_owner_probe)(target) is not None:
        raise RuntimeError("worktree-admin-recovery-owner-active-or-unavailable")
    common_result = _run_git(superproject, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common_result.returncode:
        raise RuntimeError("worktree-admin-common-store-unavailable")
    common = Path(common_result.stdout.strip()).resolve(strict=True)
    if admin.parent != common / "worktrees" or admin.parent.is_symlink():
        raise RuntimeError("worktree-admin-recovery-path-mismatch")
    candidates = []
    for number, path in enumerate(receipt_root.glob("*.json")):
        if number >= 512:
            raise RuntimeError("worktree-admin-recovery-receipt-limit")
        if path.is_symlink():
            continue
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            result = saved.get("result") or {}
            evidence = result.get("admin_preservation") or {}
            original = common / "retired-worktree-admin" / path.stem / "original"
            if (
                saved.get("schema") != WORKTREE_ABANDONMENT_SCHEMA
                or saved.get("action") != "detach-worktree"
                or saved.get("state") not in {"applying", "crashed"}
                or saved.get("target") != str(target)
                or result.get("superproject") != str(superproject)
                or evidence.get("original_location") != str(admin)
                or evidence.get("retained_original") != str(original)
            ):
                continue
            if any(part.is_symlink() for part in (original, original.parent, original.parent.parent)):
                raise RuntimeError("worktree-admin-recovery-symlink")
            observed = original.stat()
            inventory = _admin_inventory(original)
            if (observed.st_dev, observed.st_ino) != (evidence.get("device"), evidence.get("inode")) or hashlib.sha256(
                json.dumps(inventory, sort_keys=True).encode()
            ).hexdigest() != evidence.get("inventory_sha256"):
                raise RuntimeError("worktree-admin-recovery-evidence-mismatch")
            candidates.append((path, saved, original))
        except (OSError, ValueError, AttributeError):
            continue
    if len(candidates) != 1:
        raise RuntimeError("worktree-admin-recovery-unproven")
    path, saved, original = candidates[0]
    original.rename(admin)
    _write_state(
        path,
        saved,
        state="crashed",
        phase="preserved-original-restored",
        result={**saved["result"], "recovery": "registration-restored-original-retained"},
    )


def _require_clean_checkout(target: Path) -> None:
    status = _run_git(target, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status.returncode:
        raise RuntimeError("worktree-status-unavailable")
    if status.stdout:
        raise RuntimeError("worktree-not-clean")
    flags = _run_git(target, "ls-files", "-v", "-z")
    if flags.returncode or any(line[:1].islower() or line.startswith("S ") for line in flags.stdout.split("\x00")):
        raise RuntimeError("worktree-hidden-modifications")
    ignored = _run_git(target, "ls-files", "--others", "--ignored", "--exclude-standard", "-z")
    if ignored.returncode or ignored.stdout:
        raise RuntimeError("ignored-payload-custody-unproven")
    if nested_reason := _nested_payload_custody_reason(target):
        raise RuntimeError(nested_reason)


def completed_worktree_retirement(
    superproject: Path, target: Path, expected_head: str, receipt_root: Path
) -> dict[str, Any] | None:
    """Read back an exact completed attempt after a lease-checkpoint interruption."""
    if target.exists() or target.is_symlink() or target in _registered_worktree_paths(superproject):
        return None
    common_result = _run_git(superproject, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common_result.returncode:
        return None
    common = Path(common_result.stdout.strip()).resolve(strict=True)
    for number, path in enumerate(receipt_root.glob("*.json")):
        if number >= 512:
            return None
        if path.is_symlink():
            continue
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            result = saved.get("result") or {}
            evidence = result.get("admin_preservation") or {}
            original = common / "retired-worktree-admin" / path.stem / "original"
            if (
                saved.get("schema") != WORKTREE_ABANDONMENT_SCHEMA
                or saved.get("action") != "detach-worktree"
                or saved.get("state") != "completed"
                or saved.get("target") != str(target)
                or result.get("superproject") != str(superproject.resolve(strict=True))
                or result.get("head") != expected_head
                or result.get("detached") is not True
                or evidence.get("retained_original") != str(original)
                or any(part.is_symlink() for part in (original, original.parent, original.parent.parent))
            ):
                continue
            observed = original.stat()
            if (observed.st_dev, observed.st_ino) != (evidence.get("device"), evidence.get("inode")):
                continue
            inventory = _admin_inventory(original)
            if hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest() != evidence.get(
                "inventory_sha256"
            ):
                continue
            return {**saved, "receipt_path": str(path)}
        except (OSError, ValueError, AttributeError, RuntimeError):
            continue
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
        owner = (owner_probe or _default_cwd_owner_probe)(target)
        if owner is not None:
            code = "owner-probe-unavailable" if owner == -1 else f"active-process-cwd:{owner}"
            raise RuntimeError(code)
        recover_worktree_registration(superproject, target, receipt_root, owner_probe=owner_probe)
        registered = _registered_worktree_paths(superproject)
        if target not in registered:
            raise RuntimeError("target-not-registered")
        _require_clean_checkout(target)
        head = _run_git(target, "rev-parse", "HEAD")
        if head.returncode != 0 or not head.stdout.strip():
            raise RuntimeError("worktree-head-unavailable")
        receipt = _write_state(
            receipt_path,
            receipt,
            state="verified",
            phase="verify",
            result={"head": head.stdout.strip(), "registered": True, "clean": True, "superproject": str(superproject)},
        )
        phase = "detach"
        if nested_reason := _nested_payload_custody_reason(target):
            raise RuntimeError(nested_reason)
        receipt = _preserve_worktree_admin(superproject, target, receipt_path, receipt)
        owner = (owner_probe or _default_cwd_owner_probe)(target)
        if owner is not None:
            raise RuntimeError("owner-changed-before-detach")
        fresh_head = _run_git(target, "rev-parse", "HEAD")
        if fresh_head.returncode or fresh_head.stdout.strip() != head.stdout.strip():
            raise RuntimeError("head-changed-before-detach")
        _require_clean_checkout(target)
        evidence = receipt["result"]["admin_preservation"]
        if _admin_inventory(Path(evidence["original_location"])) != _admin_inventory(
            Path(evidence["retained_original"])
        ):
            raise RuntimeError("worktree-admin-changed-before-detach")
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
        # A helper may have advanced the write-ahead receipt before failing.
        # Do not overwrite its preservation locations with the older snapshot.
        try:
            saved = json.loads(receipt_path.read_text(encoding="utf-8"))
            if saved.get("schema") == receipt["schema"] and saved.get("target") == receipt["target"]:
                receipt = saved
        except (OSError, ValueError, AttributeError):
            pass
        _raise_crash(
            receipt_path,
            receipt,
            phase=phase,
            code="detach-denied",
            detail=str(exc),
        )


def retire_released_worktree(
    superproject: Path,
    target: Path,
    *,
    expected_head: str,
    remote_ref: str,
    receipt_root: Path,
    owner_probe: OwnerProbe | None = None,
) -> dict[str, Any]:
    """Retire a released disposable copy; preserve every ref and uncertain payload.

    The standing loss-free removal grant applies only after fresh remote proof.
    Repeating release after a crash is harmless: absence is an explicit result,
    and a surviving checkout is fully rechecked before the native detach.
    """
    if not target.exists() and not target.is_symlink():
        return {"state": "already-absent", "refs_deleted": 0}
    if not OBJECT_ID_RE.fullmatch(expected_head) or not remote_ref.startswith("refs/heads/"):
        return {"state": "retained", "reason": "invalid-release-proof"}

    def checked(*args: str) -> str:
        result = _run_git(target, *args)
        if result.returncode:
            raise RuntimeError("release-proof-unavailable")
        return result.stdout.strip()

    try:
        if checked("rev-parse", "HEAD") != expected_head:
            raise RuntimeError("head-advanced")
        if checked("status", "--porcelain=v1", "--untracked-files=all"):
            raise RuntimeError("dirty")
        if checked("ls-files", "--others", "--ignored", "--exclude-standard"):
            raise RuntimeError("ignored-payload")
        remote = checked("ls-remote", "--exit-code", "origin", remote_ref).split()
        if len(remote) != 2 or remote[1] != remote_ref or remote[0] != expected_head:
            raise RuntimeError("remote-tip-not-exact")
        # Recheck after the network operation, immediately before the lifecycle.
        if checked("rev-parse", "HEAD") != expected_head:
            raise RuntimeError("head-advanced")
        return detach_registered_worktree(
            superproject,
            target,
            reason="clean+pushed+idle: released disposable checkout; remote exact tip; refs retained",
            receipt_root=receipt_root,
            owner_probe=owner_probe,
        )
    except (RuntimeError, OSError) as exc:
        return {"state": "retained", "reason": str(exc), "refs_deleted": 0}


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

    def advertised_ref(value: object) -> bool:
        return (
            isinstance(value, str)
            and value.startswith(("refs/heads/", "refs/tags/", "refs/pull/"))
            and not any(char.isspace() or ord(char) < 32 for char in value)
            and not value.endswith("/")
        )

    if not remote_refs or not all(advertised_ref(value) for value in remote_refs):
        raise ValueError("remote-purge-refs-invalid")
    if not local_ref_proof or any(
        not isinstance(value.get("local_ref"), str)
        or not isinstance(value.get("object"), str)
        or not isinstance(value.get("remote_refs"), list)
        or not value["remote_refs"]
        or not all(advertised_ref(ref) for ref in value["remote_refs"])
        or not OBJECT_ID_RE.fullmatch(value["object"])
        for value in local_ref_proof
    ):
        raise ValueError("remote-purge-local-ref-proof-invalid")
    if content_probe is None:
        raise ValueError("remote-purge-fresh-content-probe-required")
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
    "completed_worktree_retirement",
    "detach_registered_worktree",
    "purge_custody_proven_contents",
    "purge_custody_proven_path",
    "purge_remote_proven_path",
    "quarantine_path",
    "recover_worktree_registration",
    "remove_stable_zero_byte_lock",
]
