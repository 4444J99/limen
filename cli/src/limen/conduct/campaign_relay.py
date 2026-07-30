"""Durable reservation boundary for institutional campaign succession."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from limen.conduct.models import CampaignRelayReceiptV1, canonical_hash
from limen.workstream_contract import (
    RECEIPT_SCHEMA,
    ContractError,
    validate_contract,
)

_RECEIPT_CEILING = 65_536
_GIT_OBJECT_LENGTHS = frozenset({40, 64})
_LOCK_ACQUIRE_TIMEOUT_SECONDS = 2.0


class CampaignRelayError(RuntimeError):
    """One fail-closed relay error safe to record in the campaign owner."""


@dataclass(frozen=True)
class RelayReservation:
    receipt: CampaignRelayReceiptV1
    created: bool


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise CampaignRelayError(f"git {' '.join(args)} failed: {detail or result.returncode}")
    return result.stdout.strip()


def _git_common_dir(root: Path) -> Path:
    raw = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    path = Path(raw)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CampaignRelayError(f"Git common directory is unavailable: {exc}") from exc
    if path.is_symlink() or not resolved.is_dir():
        raise CampaignRelayError("Git common directory must be a real directory")
    return resolved


def _store_dir(root: Path) -> Path:
    common = _git_common_dir(root)
    store = common / "limen" / "campaign-relays"
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise CampaignRelayError("campaign relay store requires no-follow directory operations")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        parent = os.open(common, flags)
        descriptors.append(parent)
        for name in ("limen", "campaign-relays"):
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent)
            except FileExistsError:
                pass
            child = os.open(name, flags, dir_fd=parent)
            descriptors.append(child)
            os.fchmod(child, 0o700)
            parent = child
        resolved = store.resolve(strict=True)
    except OSError as exc:
        raise CampaignRelayError(f"campaign relay store is unavailable: {exc}") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    if store.is_symlink() or not resolved.is_relative_to(common) or not resolved.is_dir():
        raise CampaignRelayError("campaign relay store must remain inside the Git common directory")
    return resolved


def _paths(root: Path, relay_id: str) -> tuple[Path, Path]:
    if len(relay_id) != 64 or any(character not in "0123456789abcdef" for character in relay_id):
        raise CampaignRelayError("relay identity must be a lowercase SHA-256 digest")
    store = _store_dir(root)
    return store / f"{relay_id}.json", store / f"{relay_id}.lock"


@contextmanager
def campaign_relay_lock(
    root: Path,
    relay_id: str,
    *,
    timeout_seconds: float = _LOCK_ACQUIRE_TIMEOUT_SECONDS,
) -> Iterator[None]:
    """Hold the cross-beat relay lock for one bounded reservation phase."""

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not 0 < timeout_seconds <= 30
    ):
        raise CampaignRelayError("campaign relay lock timeout must be between 0 and 30 seconds")
    _receipt_path, lock_path = _paths(root, relay_id)
    if lock_path.is_symlink():
        raise CampaignRelayError("campaign relay lock must not be a symlink")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise CampaignRelayError(f"campaign relay lock is unavailable: {exc}") from exc
    locked = False
    try:
        os.fchmod(descriptor, 0o600)
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CampaignRelayError(
                        "campaign relay lock remained busy past its bounded acquire deadline"
                    ) from None
                time.sleep(min(0.01, remaining))
        yield
    finally:
        try:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _read_receipt(path: Path) -> CampaignRelayReceiptV1 | None:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CampaignRelayError(f"campaign relay receipt is unavailable: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise CampaignRelayError("campaign relay receipt must be a private regular file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(_RECEIPT_CEILING + 1)
    except OSError as exc:
        raise CampaignRelayError(f"campaign relay receipt is unreadable: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > _RECEIPT_CEILING:
        raise CampaignRelayError("campaign relay receipt exceeds its bounded size")
    try:
        return CampaignRelayReceiptV1.model_validate_json(raw)
    except ValueError as exc:
        raise CampaignRelayError(f"campaign relay receipt is invalid: {exc}") from exc


def _write_receipt(path: Path, receipt: CampaignRelayReceiptV1) -> None:
    payload = (
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True, separators=(",", ": ")) + "\n"
    ).encode("utf-8")
    if len(payload) > _RECEIPT_CEILING:
        raise CampaignRelayError("campaign relay receipt exceeds its bounded size")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        raise CampaignRelayError(f"campaign relay receipt could not be persisted: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _tracked_predecessor(
    root: Path,
    receipt_path: Path,
    *,
    exact_remote_main: str,
) -> tuple[str, dict[str, Any]]:
    if len(exact_remote_main) not in _GIT_OBJECT_LENGTHS or any(
        character not in "0123456789abcdef" for character in exact_remote_main
    ):
        raise CampaignRelayError("exact remote main must be a lowercase Git object id")
    root = root.resolve()
    try:
        resolved = receipt_path.resolve(strict=True)
        relative = resolved.relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise CampaignRelayError("predecessor receipt must be a real file inside the checkout") from exc
    if receipt_path.is_symlink() or not resolved.is_file():
        raise CampaignRelayError("predecessor receipt must be a real file")
    blob = _git(root, "rev-parse", f"{exact_remote_main}:{relative}")
    try:
        payload = json.loads(_git(root, "show", f"{exact_remote_main}:{relative}"))
    except json.JSONDecodeError as exc:
        raise CampaignRelayError(f"committed predecessor receipt is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != RECEIPT_SCHEMA:
        raise CampaignRelayError("predecessor receipt schema is unsupported")
    try:
        contract = validate_contract(payload.get("contract"))
    except ContractError as exc:
        raise CampaignRelayError(f"predecessor contract is invalid: {exc}") from exc
    if payload.get("workstream") != "institutional-omega":
        raise CampaignRelayError("automatic succession is limited to institutional-omega")
    return blob, contract


def relay_identity(
    root: Path,
    predecessor: Path,
    *,
    exact_remote_main: str,
) -> CampaignRelayReceiptV1:
    """Derive one stable successor identity without writing or launching anything."""

    blob, contract = _tracked_predecessor(
        root,
        predecessor,
        exact_remote_main=exact_remote_main,
    )
    deadline = contract["runway"].get("deadline_epoch")
    if isinstance(deadline, bool) or not isinstance(deadline, int) or deadline <= 0:
        raise CampaignRelayError("predecessor campaign has not been admitted")
    contract_digest = canonical_hash(contract)
    identity = {
        "workstream": "institutional-omega",
        "predecessor_receipt_blob": blob,
        "predecessor_contract_digest": contract_digest,
        "predecessor_deadline_epoch": deadline,
        "exact_remote_main": exact_remote_main,
    }
    relay_id = canonical_hash(identity)
    slug = f"institutional-omega-{relay_id[:16]}"
    return CampaignRelayReceiptV1(
        relay_id=relay_id,
        workstream="institutional-omega",
        predecessor_receipt_blob=blob,
        predecessor_contract_digest=contract_digest,
        predecessor_deadline_epoch=deadline,
        exact_remote_main=exact_remote_main,
        successor_slug=slug,
        successor_branch=f"work/{slug}",
        successor_session_id=f"relay-{relay_id[:32]}",
        state="reserved",
    )


def reserve_relay(
    root: Path,
    predecessor: Path,
    *,
    exact_remote_main: str,
) -> RelayReservation:
    """Persist the reservation before any worktree creation or provider spawn."""

    expected = relay_identity(root, predecessor, exact_remote_main=exact_remote_main)
    receipt_path, _lock_path = _paths(root, expected.relay_id)
    with campaign_relay_lock(root, expected.relay_id):
        existing = _read_receipt(receipt_path)
        if existing is not None:
            if existing.relay_id != expected.relay_id or any(
                getattr(existing, field) != getattr(expected, field)
                for field in (
                    "workstream",
                    "predecessor_receipt_blob",
                    "predecessor_contract_digest",
                    "predecessor_deadline_epoch",
                    "exact_remote_main",
                    "successor_slug",
                    "successor_branch",
                    "successor_session_id",
                )
            ):
                raise CampaignRelayError("stored relay identity conflicts with the predecessor")
            return RelayReservation(receipt=existing, created=False)
        _write_receipt(receipt_path, expected)
        return RelayReservation(receipt=expected, created=True)


def relay_boundary_projection(receipt: CampaignRelayReceiptV1) -> dict[str, Any]:
    """Return the path-free lifecycle atom safe for heartbeat and owner receipts."""

    return {
        "schema": "limen.campaign_relay_boundary.v1",
        "relay_id": receipt.relay_id,
        "state": receipt.state,
        "attempts": receipt.attempts,
        "successor_session_id": receipt.successor_session_id,
        "workstream": receipt.workstream,
        "next_lifecycle_predicate": (
            "the separately reviewed launch effector proves broker registration, exact remote "
            "receipt publication, and provider exec continuity without a duplicate spawn"
        ),
    }
