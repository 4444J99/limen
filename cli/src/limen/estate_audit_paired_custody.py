"""Two-device orchestration for generated estate-audit custody.

This module deliberately composes :mod:`limen.estate_audit_custody` through its
public executable.  The single-rail implementation remains the only writer of
repository and failed-checkout payload custody; this layer proves that the same
fresh, dynamically discovered plan is restored on two registered physical
devices while one sanctioned heavy lease is held.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from limen.agent_state.custody import _device_identity
from limen.agent_state.models import ReceiptError
from limen.estate_audit_custody import (
    MAX_ROOTS,
    MAX_SECONDS,
    CustodyPlan,
    EstateAuditCustodyError,
    discover_plan,
)
from limen.host_admission import AdmissionDenied, hold_lease

REGISTRY_SCHEMA = "limen.estate_audit_paired_custody_targets.v1"
PRIVATE_RECEIPT_SCHEMA = "limen.estate_audit_paired_custody_prepared.v1"
PROJECTION_SCHEMA = "limen.estate_audit_paired_custody_projection.v1"
SINGLE_RAIL_RESULT_SCHEMA = "limen.estate_audit_custody_result.v1"
SINGLE_RAIL_RECEIPT_SCHEMA = "limen.estate_audit_custody_receipt.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PHYSICAL_IDENTITY_RE = re.compile(r"^device_[0-9a-f]{32}$")
ERROR_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,95}$")
MAX_REGISTRY_BYTES = 1024 * 1024
MAX_CHILD_STDOUT_BYTES = 1024 * 1024
MAX_CHILD_STDERR_BYTES = 256 * 1024
MAX_PREPARED_RECORD_BYTES = 4 * 1024 * 1024
PROCESS_GROUP_TERM_SECONDS = 0.25
PROCESS_GROUP_KILL_SECONDS = 2.0
TARGET_REFS = ("archive4t", "t7recovery")
TARGET_NAMES = {
    "archive4t": "Archive4T",
    "t7recovery": "T7Recovery",
}
TARGET_RELATIVE = Path("limen-private/estate-audit-git-custody")
PAIR_RECEIPT_RELATIVE = Path("paired-receipts")
TARGET_OUTPUT_DIRECTORIES = (
    "paired-receipts",
    "payloads",
    "receipts",
    "repositories",
)


class PairedCustodyError(RuntimeError):
    """A paired-custody predicate failed closed with path-free evidence."""

    def __init__(self, code: str, *, reasons: tuple[str, ...] = ()) -> None:
        self.code = code if ERROR_CODE_RE.fullmatch(code) else "invalid-error-code"
        self.reasons = tuple(reason for reason in reasons if ERROR_CODE_RE.fullmatch(reason))[:8]
        super().__init__(self.code)


@dataclass(frozen=True)
class VolumeIdentity:
    mount: str
    device: str
    physical_device: str
    volume_uuid: str
    physical_identity: str


@dataclass(frozen=True)
class RegisteredTarget:
    ref: str
    name: str
    custody_root: Path
    identity: VolumeIdentity

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(
            {
                "name": self.name,
                "mount": self.identity.mount,
                "volume_uuid": self.identity.volume_uuid,
                "physical_identity": self.identity.physical_identity,
            }
        )


@dataclass(frozen=True)
class TargetRegistry:
    inventory_id: str
    inventory_sha256: str
    targets: tuple[RegisteredTarget, ...]


@dataclass(frozen=True)
class RailRequest:
    mode: str
    limen_root: Path
    max_roots: int
    max_seconds: int
    expected_plan_sha256: str | None = None
    custody_root: Path | None = None
    expected_volume_uuid: str | None = None
    expected_physical_identity: str | None = None
    deadline: float | None = None


class RailRunner(Protocol):
    def __call__(self, request: RailRequest) -> dict[str, Any]: ...


VolumeProbe = Callable[[Path], VolumeIdentity]
PlanDiscoverer = Callable[[Path, int, float], CustodyPlan]
LeaseFactory = Callable[..., AbstractContextManager[dict[str, Any]]]
PreparedWriteHook = Callable[[RegisteredTarget, int], None]


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _regular_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise PairedCustodyError("registry-not-regular")
        if info.st_size > MAX_REGISTRY_BYTES:
            raise PairedCustodyError("registry-size-limit")
        with path.open("rb") as handle:
            encoded = handle.read(MAX_REGISTRY_BYTES + 1)
        if len(encoded) > MAX_REGISTRY_BYTES:
            raise PairedCustodyError("registry-size-limit")
        payload = json.loads(encoded)
    except PairedCustodyError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PairedCustodyError("registry-unavailable") from exc
    if not isinstance(payload, dict):
        raise PairedCustodyError("registry-invalid")
    return encoded, payload


def _absolute_without_links(path: str) -> Path:
    candidate = Path(os.path.abspath(os.path.expanduser(path)))
    if not candidate.is_absolute() or ".." in Path(path).parts:
        raise PairedCustodyError("target-path-invalid")
    return candidate


def load_target_registry(path: Path, *, repository_root: Path) -> TargetRegistry:
    """Load the exact target registration and bind it to the frozen inventory."""

    _registry_bytes, payload = _regular_json(path)
    if payload.get("schema") != REGISTRY_SCHEMA:
        raise PairedCustodyError("registry-schema-mismatch")
    if payload.get("proof_status") != "registered_not_live_verified":
        raise PairedCustodyError("registry-proof-status-invalid")
    inventory_relative = Path(str(payload.get("inventory") or ""))
    if (
        inventory_relative.is_absolute()
        or inventory_relative in {Path(), Path(".")}
        or ".." in inventory_relative.parts
    ):
        raise PairedCustodyError("registry-inventory-path-invalid")
    inventory_path = repository_root / inventory_relative
    inventory_bytes, inventory = _regular_json(inventory_path)
    inventory_sha256 = hashlib.sha256(inventory_bytes).hexdigest()
    inventory_id = inventory.get("inventory_id")
    registered_inventory_id = payload.get("inventory_id")
    if (
        inventory.get("schema") != "limen.storage_evacuation_inventory.v1"
        or not isinstance(inventory_id, str)
        or not inventory_id
        or not isinstance(registered_inventory_id, str)
        or not registered_inventory_id
        or inventory_id != registered_inventory_id
        or inventory_sha256 != payload.get("inventory_sha256")
    ):
        raise PairedCustodyError("registry-inventory-binding-mismatch")

    devices: dict[str, VolumeIdentity] = {}
    for candidate in inventory.get("custody_devices") or []:
        if not isinstance(candidate, dict):
            raise PairedCustodyError("inventory-device-invalid")
        name = str(candidate.get("name") or "")
        if name in devices:
            raise PairedCustodyError("inventory-device-duplicate")
        try:
            devices[name] = VolumeIdentity(
                mount=str(candidate["mount"]),
                device=str(candidate["device"]),
                physical_device=str(candidate["physical_device"]),
                volume_uuid=str(candidate["volume_uuid"]).upper(),
                physical_identity="",
            )
        except (KeyError, TypeError) as exc:
            raise PairedCustodyError("inventory-device-invalid") from exc

    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or len(raw_targets) != 2:
        raise PairedCustodyError("registry-target-count-invalid")
    targets: list[RegisteredTarget] = []
    for candidate in raw_targets:
        if not isinstance(candidate, dict):
            raise PairedCustodyError("registry-target-invalid")
        ref = str(candidate.get("ref") or "")
        name = str(candidate.get("inventory_name") or "")
        if ref not in TARGET_REFS or name != TARGET_NAMES[ref] or name not in devices:
            raise PairedCustodyError("registry-target-invalid")
        custody_root = _absolute_without_links(str(candidate.get("custody_root") or ""))
        identity = devices[name]
        physical_identity = candidate.get("stable_physical_identity")
        if not isinstance(physical_identity, str) or not PHYSICAL_IDENTITY_RE.fullmatch(physical_identity):
            raise PairedCustodyError("registry-stable-physical-identity-missing")
        identity = VolumeIdentity(
            mount=identity.mount,
            device=identity.device,
            physical_device=identity.physical_device,
            volume_uuid=identity.volume_uuid,
            physical_identity=physical_identity,
        )
        mount = _absolute_without_links(identity.mount)
        try:
            relative = custody_root.relative_to(mount)
        except ValueError as exc:
            raise PairedCustodyError("registry-target-outside-mount") from exc
        if relative != TARGET_RELATIVE:
            raise PairedCustodyError("registry-target-path-invalid")
        targets.append(
            RegisteredTarget(
                ref=ref,
                name=name,
                custody_root=custody_root,
                identity=identity,
            )
        )
    if tuple(target.ref for target in targets) != TARGET_REFS:
        raise PairedCustodyError("registry-target-order-invalid")
    if len({target.name for target in targets}) != 2:
        raise PairedCustodyError("registry-target-name-duplicate")
    return TargetRegistry(
        inventory_id=inventory_id,
        inventory_sha256=inventory_sha256,
        targets=tuple(targets),
    )


def diskutil_volume_identity(mount: Path) -> VolumeIdentity:
    """Read the mounted APFS volume identity without mutating host state."""

    try:
        result = subprocess.run(
            ["/usr/sbin/diskutil", "info", "-plist", str(mount)],
            capture_output=True,
            check=False,
            timeout=20,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PairedCustodyError("volume-identity-probe-failed") from exc
    if result.returncode:
        raise PairedCustodyError("volume-identity-probe-failed")
    try:
        value = plistlib.loads(result.stdout)
        device = str(value["DeviceIdentifier"])
        stores = value.get("APFSPhysicalStores")
        if isinstance(stores, list) and len(stores) == 1 and isinstance(stores[0], dict):
            store = str(stores[0]["APFSPhysicalStore"])
            match = re.fullmatch(r"(disk[0-9]+)s[0-9]+", store)
            physical = match.group(1) if match else store
        else:
            physical = str(value["ParentWholeDisk"])
        observed_mount = str(Path(value["MountPoint"]).resolve(strict=True))
        volume_uuid = str(value["VolumeUUID"]).upper()
        physical_identity = _device_identity(mount)
    except (KeyError, OSError, ReceiptError, TypeError, plistlib.InvalidFileException) as exc:
        raise PairedCustodyError("volume-identity-invalid") from exc
    return VolumeIdentity(
        mount=observed_mount,
        device=f"/dev/{device}",
        physical_device=f"/dev/{physical}",
        volume_uuid=volume_uuid,
        physical_identity=physical_identity,
    )


def _assert_no_path_indirection(target: RegisteredTarget, *, require_mount: bool) -> None:
    mount = _absolute_without_links(target.identity.mount)
    try:
        info = mount.lstat()
    except OSError as exc:
        raise PairedCustodyError("target-mount-unavailable") from exc
    if mount.is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise PairedCustodyError("target-mount-invalid")
    if require_mount and (not mount.is_mount() or not os.access(mount, os.W_OK)):
        raise PairedCustodyError("target-mount-unavailable")
    try:
        relative = target.custody_root.relative_to(mount)
    except ValueError as exc:
        raise PairedCustodyError("target-outside-mounted-volume") from exc
    current = mount
    for part in relative.parts:
        current /= part
        try:
            current_info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise PairedCustodyError("target-path-unavailable") from exc
        if stat.S_ISLNK(current_info.st_mode):
            raise PairedCustodyError("target-path-symlink")
        if current != target.custody_root and not stat.S_ISDIR(current_info.st_mode):
            raise PairedCustodyError("target-parent-not-directory")
        if current == target.custody_root and not stat.S_ISDIR(current_info.st_mode):
            raise PairedCustodyError("target-not-directory")


def _assert_target_outputs_safe(target: RegisteredTarget) -> None:
    try:
        target_info = target.custody_root.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise PairedCustodyError("target-path-unavailable") from exc
    if target.custody_root.is_symlink() or not stat.S_ISDIR(target_info.st_mode):
        raise PairedCustodyError("target-not-directory")
    for name in TARGET_OUTPUT_DIRECTORIES:
        output = target.custody_root / name
        try:
            info = output.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise PairedCustodyError("target-output-unavailable") from exc
        if output.is_symlink() or not stat.S_ISDIR(info.st_mode):
            raise PairedCustodyError("target-output-invalid")


def _assert_pair_receipt_path_safe(
    target: RegisteredTarget,
    plan_sha256: str,
    record_sha256: str | None = None,
) -> None:
    filenames = [_paired_receipt_filename(plan_sha256)]
    if record_sha256 is not None:
        filenames.append(_paired_receipt_filename(plan_sha256, record_sha256))
    directory = target.custody_root / PAIR_RECEIPT_RELATIVE
    try:
        info = directory.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise PairedCustodyError("paired-receipt-root-unavailable") from exc
    if directory.is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise PairedCustodyError("paired-receipt-root-invalid")

    for filename in filenames:
        receipt = directory / filename
        try:
            info = receipt.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise PairedCustodyError("paired-receipt-unavailable") from exc
        if receipt.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise PairedCustodyError("paired-receipt-not-regular")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise PairedCustodyError("paired-receipt-mode-invalid")
        if info.st_size > MAX_PREPARED_RECORD_BYTES:
            raise PairedCustodyError("paired-receipt-size-limit")


def _assert_live_target(
    target: RegisteredTarget,
    *,
    volume_probe: VolumeProbe,
    require_mount: bool,
) -> VolumeIdentity:
    _assert_no_path_indirection(target, require_mount=require_mount)
    _assert_target_outputs_safe(target)
    actual = volume_probe(_absolute_without_links(target.identity.mount))
    expected = (
        str(_absolute_without_links(target.identity.mount)),
        target.identity.volume_uuid,
        target.identity.physical_identity,
    )
    observed = (
        actual.mount,
        actual.volume_uuid,
        actual.physical_identity,
    )
    if observed != expected:
        raise PairedCustodyError(f"{target.ref}-identity-mismatch")
    return actual


def validate_live_targets(
    registry: TargetRegistry,
    *,
    volume_probe: VolumeProbe = diskutil_volume_identity,
    require_mount: bool = True,
) -> None:
    """Validate both exact mounted target identities without creating anything."""

    observed: list[VolumeIdentity] = []
    for target in registry.targets:
        observed.append(
            _assert_live_target(
                target,
                volume_probe=volume_probe,
                require_mount=require_mount,
            )
        )
    if observed[0].physical_identity == observed[1].physical_identity:
        raise PairedCustodyError("targets-share-physical-device")
    if observed[0].volume_uuid == observed[1].volume_uuid:
        raise PairedCustodyError("targets-share-volume-uuid")


def _overlap(first: Path, second: Path) -> bool:
    left = first.expanduser().resolve(strict=False)
    right = second.expanduser().resolve(strict=False)
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def _assert_targets_outside_sources(
    registry: TargetRegistry,
    plan: CustodyPlan,
) -> None:
    for target in registry.targets:
        for root in plan.roots:
            if _overlap(target.custody_root, Path(root.path)):
                raise PairedCustodyError("target-source-overlap")


def _assert_targets_outside_control_paths(
    registry: TargetRegistry,
    *,
    repository_root: Path,
    limen_root: Path,
    registry_path: Path,
    single_rail_script: Path,
) -> None:
    protected = (
        repository_root,
        limen_root,
        registry_path,
        single_rail_script,
    )
    for target in registry.targets:
        if any(_overlap(target.custody_root, path) for path in protected):
            raise PairedCustodyError("target-control-path-overlap")


def _validated_public(
    payload: dict[str, Any],
    *,
    expected_plan_sha256: str | None,
    require_changed: bool,
) -> dict[str, Any]:
    if payload.get("result_schema") != SINGLE_RAIL_RESULT_SCHEMA:
        raise PairedCustodyError("single-rail-result-invalid")
    if require_changed:
        if payload.get("schema") != SINGLE_RAIL_RECEIPT_SCHEMA or payload.get("status") != "restored":
            raise PairedCustodyError("single-rail-result-invalid")
    elif (
        payload.get("schema") != "limen.estate_audit_custody_plan.v1"
        or payload.get("status") != "ready"
        or payload.get("content_preflight_ok") is not True
    ):
        raise PairedCustodyError("single-rail-result-invalid")
    plan_sha256 = str(payload.get("plan_sha256") or "")
    if not SHA256_RE.fullmatch(plan_sha256):
        raise PairedCustodyError("single-rail-plan-invalid")
    if expected_plan_sha256 is not None and plan_sha256 != expected_plan_sha256:
        raise PairedCustodyError("single-rail-plan-mismatch")
    count_fields = (
        "root_count",
        "repository_count",
        "head_count",
        "empty_index_root_count",
        "indexed_root_count",
    )
    for field in count_fields:
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PairedCustodyError("single-rail-count-invalid")
    if require_changed and not isinstance(payload.get("changed"), bool):
        raise PairedCustodyError("single-rail-changed-invalid")
    if payload.get("schema") == SINGLE_RAIL_RECEIPT_SCHEMA and (
        not SHA256_RE.fullmatch(str(payload.get("content_sha256") or ""))
        or payload.get("restoration_passed") is not True
        or not SHA256_RE.fullmatch(str(payload.get("working_payload_manifest_sha256") or ""))
    ):
        raise PairedCustodyError("single-rail-restoration-invalid")
    return payload


def _assert_check_matches_plan(check: dict[str, Any], plan: CustodyPlan) -> None:
    expected = plan.public_payload()
    for field in (
        "plan_sha256",
        "root_count",
        "repository_count",
        "head_count",
        "empty_index_root_count",
        "indexed_root_count",
    ):
        if check.get(field) != expected.get(field):
            raise PairedCustodyError("fresh-check-plan-mismatch")


def _assert_same_logical_inventory(
    check: dict[str, Any],
    rail: dict[str, Any],
) -> None:
    for field in (
        "plan_sha256",
        "root_count",
        "repository_count",
        "head_count",
        "empty_index_root_count",
        "indexed_root_count",
    ):
        if rail.get(field) != check.get(field):
            raise PairedCustodyError("rail-logical-inventory-mismatch")


def _remaining_seconds(deadline: float) -> int:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PairedCustodyError("paired-custody-time-limit-exceeded")
    return max(1, min(MAX_SECONDS, int(remaining)))


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_process_group_exit(
    process: subprocess.Popen[bytes],
    process_group: int,
    *,
    deadline: float,
) -> bool:
    while time.monotonic() < deadline:
        process.poll()
        if not _process_group_exists(process_group):
            return True
        time.sleep(0.01)
    process.poll()
    return not _process_group_exists(process_group)


def _terminate_process_group(process: subprocess.Popen[bytes], *, mode: str) -> None:
    process_group = process.pid
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError as exc:
        raise PairedCustodyError(f"single-rail-{mode}-termination-failed") from exc

    if not _wait_for_process_group_exit(
        process,
        process_group,
        deadline=time.monotonic() + PROCESS_GROUP_TERM_SECONDS,
    ):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as exc:
            raise PairedCustodyError(f"single-rail-{mode}-termination-failed") from exc

    try:
        process.wait(timeout=PROCESS_GROUP_KILL_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise PairedCustodyError(f"single-rail-{mode}-termination-failed") from exc
    if not _wait_for_process_group_exit(
        process,
        process_group,
        deadline=time.monotonic() + PROCESS_GROUP_KILL_SECONDS,
    ):
        raise PairedCustodyError(f"single-rail-{mode}-termination-failed")


def invoke_single_rail(script: Path, request: RailRequest) -> dict[str, Any]:
    """Invoke only the existing public single-rail executable."""

    child_seconds = request.max_seconds
    if request.deadline is not None:
        child_seconds = min(child_seconds, _remaining_seconds(request.deadline))
    arguments = [
        sys.executable,
        str(script),
        f"--{request.mode}",
        "--json",
        "--max-roots",
        str(request.max_roots),
        "--max-seconds",
        str(child_seconds),
    ]
    if request.mode in {"check", "apply"}:
        arguments.extend(["--limen-root", str(request.limen_root)])
    if request.custody_root is not None:
        arguments.extend(["--custody-root", str(request.custody_root)])
    if request.expected_plan_sha256 is not None:
        arguments.extend(["--expected-plan-sha", request.expected_plan_sha256])
    if request.expected_volume_uuid is not None:
        arguments.extend(["--expected-volume-uuid", request.expected_volume_uuid])
    if request.expected_physical_identity is not None:
        arguments.extend(["--expected-physical-identity", request.expected_physical_identity])
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    stdout = None
    stderr = None
    try:
        try:
            process = subprocess.Popen(
                arguments,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            stdout = process.stdout
            stderr = process.stderr
            if stdout is None or stderr is None:
                raise PairedCustodyError(f"single-rail-{request.mode}-unavailable")
            selector = selectors.DefaultSelector()
            selector.register(stdout, selectors.EVENT_READ, ("stdout", MAX_CHILD_STDOUT_BYTES))
            selector.register(stderr, selectors.EVENT_READ, ("stderr", MAX_CHILD_STDERR_BYTES))
            output = {"stdout": bytearray(), "stderr": bytearray()}
            deadline = request.deadline or time.monotonic() + child_seconds + 30
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(arguments, child_seconds)
                events = selector.select(remaining)
                if not events:
                    raise subprocess.TimeoutExpired(arguments, child_seconds)
                for key, _mask in events:
                    stream, limit = key.data
                    chunk = os.read(key.fd, min(64 * 1024, limit + 1 - len(output[stream])))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output[stream].extend(chunk)
                    if len(output[stream]) > limit:
                        raise PairedCustodyError(f"single-rail-{request.mode}-{stream}-limit")
            returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
            payload = json.loads(bytes(output["stdout"]))
            if not isinstance(payload, dict):
                raise PairedCustodyError(f"single-rail-{request.mode}-invalid")
            if returncode:
                error = str(payload.get("error") or "")
                reasons = (error,) if ERROR_CODE_RE.fullmatch(error) else ()
                raise PairedCustodyError(
                    f"single-rail-{request.mode}-blocked",
                    reasons=reasons,
                )
        except BaseException:
            if process is not None:
                _terminate_process_group(process, mode=request.mode)
            raise
        finally:
            if selector is not None:
                selector.close()
            if stdout is not None:
                stdout.close()
            if stderr is not None:
                stderr.close()
    except PairedCustodyError:
        raise
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise PairedCustodyError(f"single-rail-{request.mode}-unavailable") from exc
    return payload


def _open_receipt_directory(custody_root: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        root = os.open(custody_root, flags)
    except OSError as exc:
        raise PairedCustodyError("paired-receipt-root-unavailable") from exc
    directory: int | None = None
    try:
        try:
            os.mkdir(PAIR_RECEIPT_RELATIVE.name, 0o700, dir_fd=root)
        except FileExistsError:
            pass
        directory = os.open(PAIR_RECEIPT_RELATIVE.name, flags, dir_fd=root)
        os.fchmod(directory, 0o700)
        os.fsync(root)
        return directory
    except OSError as exc:
        if directory is not None:
            os.close(directory)
        raise PairedCustodyError("paired-receipt-root-invalid") from exc
    finally:
        os.close(root)


def _read_optional_receipt_bytes(custody_root: Path, filename: str) -> bytes | None:
    directory = _open_receipt_directory(custody_root)
    try:
        try:
            descriptor = os.open(
                filename,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory,
            )
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise PairedCustodyError("paired-receipt-not-regular")
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise PairedCustodyError("paired-receipt-mode-invalid")
            encoded = handle.read(MAX_PREPARED_RECORD_BYTES + 1)
        if len(encoded) > MAX_PREPARED_RECORD_BYTES:
            raise PairedCustodyError("paired-receipt-size-limit")
        return encoded
    except PairedCustodyError:
        raise
    except OSError as exc:
        raise PairedCustodyError("paired-receipt-unavailable") from exc
    finally:
        os.close(directory)


def _read_receipt_bytes(custody_root: Path, filename: str) -> bytes:
    encoded = _read_optional_receipt_bytes(custody_root, filename)
    if encoded is None:
        raise PairedCustodyError("paired-receipt-unavailable")
    return encoded


def _private_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _write_exact_private_json(
    custody_root: Path,
    filename: str,
    payload: dict[str, Any],
) -> bool:
    encoded = _private_json_bytes(payload)
    if len(encoded) > MAX_PREPARED_RECORD_BYTES:
        raise PairedCustodyError("paired-receipt-size-limit")
    directory = _open_receipt_directory(custody_root)
    temporary: str | None = None
    try:
        try:
            info = os.stat(filename, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise PairedCustodyError("paired-receipt-not-regular")
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise PairedCustodyError("paired-receipt-mode-invalid")
            descriptor = os.open(
                filename,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory,
            )
            with os.fdopen(descriptor, "rb") as handle:
                existing = handle.read(MAX_PREPARED_RECORD_BYTES + 1)
            if len(existing) > MAX_PREPARED_RECORD_BYTES:
                raise PairedCustodyError("paired-receipt-size-limit")
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != encoded:
                raise PairedCustodyError("paired-receipt-conflict")
            return False

        temporary = f".{filename}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary,
            filename,
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
        temporary = None
        committed = os.open(
            filename,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory,
        )
        try:
            os.fchmod(committed, 0o600)
            os.fsync(committed)
        finally:
            os.close(committed)
        os.fsync(directory)
        return True
    except PairedCustodyError:
        raise
    except OSError as exc:
        raise PairedCustodyError("paired-receipt-write-failed") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        os.close(directory)


def _prepared_record(
    registry: TargetRegistry,
    check: dict[str, Any],
    rail_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    content: dict[str, Any] = {
        "schema": PRIVATE_RECEIPT_SCHEMA,
        "status": "prepared",
        "requires_peer_match": True,
        "inventory": {
            "id": registry.inventory_id,
            "sha256": registry.inventory_sha256,
        },
        "plan_sha256": check["plan_sha256"],
        "denominator": {
            field: check[field]
            for field in (
                "root_count",
                "repository_count",
                "head_count",
                "empty_index_root_count",
                "indexed_root_count",
            )
        },
        "targets": {
            target.ref: {
                "name": target.name,
                "custody_root": str(target.custody_root),
                "identity": {
                    "mount": target.identity.mount,
                    "volume_uuid": target.identity.volume_uuid,
                    "physical_identity": target.identity.physical_identity,
                },
                "identity_sha256": target.identity_sha256,
                "single_rail_content_sha256": rail_results[target.ref]["content_sha256"],
                "rail_restoration_passed": True,
            }
            for target in registry.targets
        },
        "working_payload_manifest_sha256": rail_results[TARGET_REFS[0]]["working_payload_manifest_sha256"],
        "independent_physical_devices": True,
        "source_retired": False,
        "reclaim_performed": False,
    }
    return {**content, "record_sha256": _canonical_sha256(content)}


def _paired_receipt_filename(
    plan_sha256: str,
    record_sha256: str | None = None,
) -> str:
    if not SHA256_RE.fullmatch(plan_sha256):
        raise PairedCustodyError("paired-receipt-name-invalid")
    if record_sha256 is None:
        return f"{plan_sha256}.json"
    if not SHA256_RE.fullmatch(record_sha256):
        raise PairedCustodyError("paired-receipt-name-invalid")
    return f"{plan_sha256}.{record_sha256}.json"


def _validated_prepared_record(encoded: bytes, expected: dict[str, Any]) -> dict[str, Any]:
    expected_bytes = _private_json_bytes(expected)
    if encoded != expected_bytes:
        raise PairedCustodyError("paired-receipts-diverged")
    try:
        payload = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PairedCustodyError("paired-receipt-invalid") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != PRIVATE_RECEIPT_SCHEMA
        or payload.get("status") != "prepared"
        or payload.get("requires_peer_match") is not True
        or "copy_count" in payload
        or "restoration_passed" in payload
    ):
        raise PairedCustodyError("paired-receipt-invalid")
    content = {key: value for key, value in payload.items() if key != "record_sha256"}
    if payload.get("record_sha256") != _canonical_sha256(content):
        raise PairedCustodyError("paired-receipt-content-mismatch")
    return payload


def _select_prepared_filename(
    registry: TargetRegistry,
    record: dict[str, Any],
    *,
    volume_probe: VolumeProbe,
    require_mount: bool,
) -> str:
    legacy = _paired_receipt_filename(str(record["plan_sha256"]))
    expected = _private_json_bytes(record)
    existing: list[bytes | None] = []
    for target in registry.targets:
        _assert_live_target(target, volume_probe=volume_probe, require_mount=require_mount)
        existing.append(_read_optional_receipt_bytes(target.custody_root, legacy))
        _assert_live_target(target, volume_probe=volume_probe, require_mount=require_mount)
    if all(value is None or value == expected for value in existing):
        return legacy
    return _paired_receipt_filename(
        str(record["plan_sha256"]),
        str(record["record_sha256"]),
    )


def _write_prepared_pair(
    registry: TargetRegistry,
    record: dict[str, Any],
    *,
    volume_probe: VolumeProbe,
    require_mount: bool,
    write_hook: PreparedWriteHook | None,
) -> tuple[bool, dict[str, Any]]:
    filename = _select_prepared_filename(
        registry,
        record,
        volume_probe=volume_probe,
        require_mount=require_mount,
    )
    changed = False
    for index, target in enumerate(registry.targets):
        _assert_live_target(target, volume_probe=volume_probe, require_mount=require_mount)
        changed = _write_exact_private_json(target.custody_root, filename, record) or changed
        _assert_live_target(target, volume_probe=volume_probe, require_mount=require_mount)
        if write_hook is not None:
            write_hook(target, index)
    reopened: list[bytes] = []
    for target in registry.targets:
        _assert_live_target(target, volume_probe=volume_probe, require_mount=require_mount)
        reopened.append(_read_receipt_bytes(target.custody_root, filename))
        _assert_live_target(target, volume_probe=volume_probe, require_mount=require_mount)
    first, second = reopened
    if first != second:
        raise PairedCustodyError("paired-receipts-diverged")
    return changed, _validated_prepared_record(first, record)


def _projection(
    registry: TargetRegistry,
    check: dict[str, Any],
    rail_results: dict[str, dict[str, Any]],
    record: dict[str, Any],
    *,
    changed: bool,
) -> dict[str, Any]:
    return {
        "schema": PROJECTION_SCHEMA,
        "status": "restored",
        "changed": changed,
        "inventory_sha256": registry.inventory_sha256,
        "plan_sha256": check["plan_sha256"],
        **{
            field: check[field]
            for field in (
                "root_count",
                "repository_count",
                "head_count",
                "empty_index_root_count",
                "indexed_root_count",
            )
        },
        "target_refs": list(TARGET_REFS),
        "target_identity_sha256": {target.ref: target.identity_sha256 for target in registry.targets},
        "single_rail_content_sha256": {ref: rail_results[ref]["content_sha256"] for ref in TARGET_REFS},
        "working_payload_manifest_sha256": record["working_payload_manifest_sha256"],
        "paired_receipt_sha256": record["record_sha256"],
        "copy_count": 2,
        "independent_physical_devices": True,
        "restoration_passed": True,
        "source_retired": False,
        "reclaim_performed": False,
    }


def _default_discoverer(
    limen_root: Path,
    max_roots: int,
    deadline: float,
) -> CustodyPlan:
    return discover_plan(
        limen_root,
        max_roots=max_roots,
        deadline=deadline,
    )


def run_paired_custody(
    *,
    repository_root: Path,
    limen_root: Path,
    registry_path: Path,
    single_rail_script: Path,
    max_roots: int = MAX_ROOTS,
    max_seconds: int = MAX_SECONDS,
    runner: RailRunner | None = None,
    volume_probe: VolumeProbe = diskutil_volume_identity,
    plan_discoverer: PlanDiscoverer = _default_discoverer,
    lease_factory: LeaseFactory = hold_lease,
    require_mount: bool = True,
    prepared_write_hook: PreparedWriteHook | None = None,
) -> dict[str, Any]:
    """Run one admission-guarded, two-rail custody proof."""

    if max_roots <= 0 or max_roots > MAX_ROOTS:
        raise PairedCustodyError("invalid-root-limit")
    if max_seconds <= 0 or max_seconds > MAX_SECONDS:
        raise PairedCustodyError("invalid-time-limit")
    invoke = runner or (lambda request: invoke_single_rail(single_rail_script, request))
    owner = f"estate-audit-paired-custody-{os.getpid()}"
    try:
        lease = lease_factory(
            "heavy",
            owner=owner,
            surface="estate-audit-paired-custody",
        )
        with lease:
            deadline = time.monotonic() + max_seconds
            registry = load_target_registry(
                registry_path,
                repository_root=repository_root,
            )
            validate_live_targets(
                registry,
                volume_probe=volume_probe,
                require_mount=require_mount,
            )
            _assert_targets_outside_control_paths(
                registry,
                repository_root=repository_root,
                limen_root=limen_root,
                registry_path=registry_path,
                single_rail_script=single_rail_script,
            )
            check = _validated_public(
                invoke(
                    RailRequest(
                        mode="check",
                        limen_root=limen_root,
                        max_roots=max_roots,
                        max_seconds=max_seconds,
                        deadline=deadline,
                    )
                ),
                expected_plan_sha256=None,
                require_changed=False,
            )
            plan = plan_discoverer(limen_root, max_roots, deadline)
            _remaining_seconds(deadline)
            _assert_check_matches_plan(check, plan)
            _assert_targets_outside_sources(registry, plan)
            for target in registry.targets:
                _assert_pair_receipt_path_safe(target, check["plan_sha256"])

            rail_results: dict[str, dict[str, Any]] = {}
            apply_changed = False
            for target in registry.targets:
                _assert_live_target(
                    target,
                    volume_probe=volume_probe,
                    require_mount=require_mount,
                )
                applied = _validated_public(
                    invoke(
                        RailRequest(
                            mode="apply",
                            limen_root=limen_root,
                            max_roots=max_roots,
                            max_seconds=max_seconds,
                            expected_plan_sha256=check["plan_sha256"],
                            custody_root=target.custody_root,
                            expected_volume_uuid=target.identity.volume_uuid,
                            expected_physical_identity=target.identity.physical_identity,
                            deadline=deadline,
                        )
                    ),
                    expected_plan_sha256=check["plan_sha256"],
                    require_changed=True,
                )
                _assert_live_target(
                    target,
                    volume_probe=volume_probe,
                    require_mount=require_mount,
                )
                _assert_same_logical_inventory(check, applied)
                apply_changed = bool(applied["changed"]) or apply_changed
                rail_results[target.ref] = applied

            if len({rail_results[ref]["working_payload_manifest_sha256"] for ref in TARGET_REFS}) != 1:
                raise PairedCustodyError("rail-working-payload-mismatch")

            # Revalidate both exact devices and path topology immediately before
            # the only paired-layer writes.
            _remaining_seconds(deadline)
            validate_live_targets(
                registry,
                volume_probe=volume_probe,
                require_mount=require_mount,
            )
            _assert_targets_outside_control_paths(
                registry,
                repository_root=repository_root,
                limen_root=limen_root,
                registry_path=registry_path,
                single_rail_script=single_rail_script,
            )
            _assert_targets_outside_sources(registry, plan)
            record = _prepared_record(registry, check, rail_results)
            for target in registry.targets:
                _assert_pair_receipt_path_safe(
                    target,
                    check["plan_sha256"],
                    record["record_sha256"],
                )
            receipt_changed, reopened_record = _write_prepared_pair(
                registry,
                record,
                volume_probe=volume_probe,
                require_mount=require_mount,
                write_hook=prepared_write_hook,
            )
            return _projection(
                registry,
                check,
                rail_results,
                reopened_record,
                changed=apply_changed or receipt_changed,
            )
    except AdmissionDenied as exc:
        reasons = tuple(
            str(reason) for reason in (exc.decision.get("reasons") or ()) if ERROR_CODE_RE.fullmatch(str(reason))
        )
        raise PairedCustodyError(
            "host-admission-denied",
            reasons=reasons,
        ) from exc
    except EstateAuditCustodyError as exc:
        raise PairedCustodyError(
            "fresh-plan-discovery-blocked",
            reasons=(exc.code,),
        ) from exc


def blocked_projection(exc: PairedCustodyError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": PROJECTION_SCHEMA,
        "status": "blocked",
        "error": exc.code,
    }
    if exc.reasons:
        payload["reasons"] = list(exc.reasons)
    return payload


__all__ = [
    "PRIVATE_RECEIPT_SCHEMA",
    "PROJECTION_SCHEMA",
    "REGISTRY_SCHEMA",
    "PairedCustodyError",
    "RailRequest",
    "RegisteredTarget",
    "TargetRegistry",
    "VolumeIdentity",
    "blocked_projection",
    "diskutil_volume_identity",
    "invoke_single_rail",
    "load_target_registry",
    "run_paired_custody",
    "validate_live_targets",
]
