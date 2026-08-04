"""Local common-Git reservation boundary for institutional campaign succession."""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import rfc8785

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.conduct.models import CampaignRelayReceiptV1, canonical_hash
from limen.workstream_contract import (
    RECEIPT_SCHEMA,
    ContractError,
    validate_contract,
)

_RECEIPT_CEILING = 65_536
_PREDECESSOR_RECEIPT_CEILING = 262_144
_GIT_CONTROL_OUTPUT_CEILING = 4096
_GIT_TIMEOUT_SECONDS = 10.0
_GIT_OBJECT_LENGTHS = frozenset({40, 64})
_LOCK_ACQUIRE_TIMEOUT_SECONDS = 2.0
_CONTROL_LINE_CEILING = 4096
_CONTROL_TOTAL_CEILING = 16_384
_STARTUP_OUTPUT_CEILING = 65_536
_STARTUP_TIMEOUT_SECONDS = 300.0
_EXEC_HANDOFF_BUDGET_SECONDS = 10.0
_REGISTRATION_OUTPUT_CEILING = 4096
_REGISTRATION_TIMEOUT_SECONDS = 20.0
_RELAY_CONTROL_SCHEMA = "limen.campaign_relay_control.v1"
_RELAY_ATTEMPT_SCHEMA = "limen.campaign_relay_attempt.v1"
_RELAY_READY_SCHEMA = "limen.campaign_relay_ready.v1"
_TERMINAL_STATES = frozenset({"failed", "indeterminate"})
_IMMUTABLE_FIELDS = (
    "relay_id",
    "workstream",
    "predecessor_receipt_blob",
    "predecessor_contract_digest",
    "predecessor_deadline_epoch",
    "exact_remote_main",
    "successor_slug",
    "successor_branch",
    "successor_session_id",
)
_LINEAGE_FIELDS = tuple(field for field in _IMMUTABLE_FIELDS if field != "exact_remote_main")


class CampaignRelayError(RuntimeError):
    """One fail-closed relay error with a stable, path-free public projection."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)

    @property
    def public_reason(self) -> str:
        return f"{self.code}: {self.public_message}"


def _deadline_timeout(
    deadline_monotonic: float | None,
    ceiling_seconds: float,
) -> float:
    """Return one phase's budget without ever extending the relay deadline."""

    if deadline_monotonic is None:
        return ceiling_seconds
    remaining = deadline_monotonic - time.monotonic()
    if remaining <= 0:
        raise CampaignRelayError(
            "relay_startup_timeout",
            "campaign relay startup exceeded its absolute deadline",
        )
    return min(ceiling_seconds, remaining)


@dataclass(frozen=True)
class RelayReservation:
    receipt: CampaignRelayReceiptV1
    created: bool


@dataclass(frozen=True)
class RelayLaunch:
    receipt: CampaignRelayReceiptV1
    launched: bool


@dataclass(frozen=True)
class ReadyRelayCapsule:
    receipt: CampaignRelayReceiptV1
    capsule_path: str
    payload: dict[str, Any]
    remaining_seconds: int


@dataclass(frozen=True)
class RelayStore:
    path: Path
    descriptor: int


def _git_bytes(
    root: Path,
    *args: str,
    output_ceiling: int = _GIT_CONTROL_OUTPUT_CEILING,
    deadline_monotonic: float | None = None,
) -> bytes:
    try:
        result = run_bounded_subprocess(
            ["git", *args],
            cwd=root,
            timeout_seconds=_deadline_timeout(deadline_monotonic, _GIT_TIMEOUT_SECONDS),
            stdout_ceiling=output_ceiling,
            stderr_ceiling=_GIT_CONTROL_OUTPUT_CEILING,
        )
    except BoundedSubprocessError as exc:
        if exc.kind == "output":
            raise CampaignRelayError(
                "relay_git_output_oversized",
                "campaign relay Git probe exceeded its output ceiling",
            ) from exc
        if exc.kind == "timeout":
            raise CampaignRelayError(
                "relay_git_timeout",
                "campaign relay Git probe exceeded its bounded deadline",
            ) from exc
        raise CampaignRelayError(
            "relay_git_unavailable",
            "campaign relay Git probe is unavailable",
        ) from exc
    if result.returncode != 0:
        raise CampaignRelayError(
            "relay_git_failed",
            "campaign relay Git probe failed",
        )
    return result.stdout


def _git(
    root: Path,
    *args: str,
    deadline_monotonic: float | None = None,
) -> str:
    raw = _git_bytes(
        root,
        *args,
        deadline_monotonic=deadline_monotonic,
    )
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise CampaignRelayError(
            "relay_git_output_invalid",
            "campaign relay Git probe returned invalid text",
        ) from exc


def _git_succeeds(
    root: Path,
    *args: str,
    deadline_monotonic: float | None = None,
) -> bool:
    try:
        result = run_bounded_subprocess(
            ["git", *args],
            cwd=root,
            timeout_seconds=_deadline_timeout(deadline_monotonic, _GIT_TIMEOUT_SECONDS),
            stdout_ceiling=_GIT_CONTROL_OUTPUT_CEILING,
            stderr_ceiling=_GIT_CONTROL_OUTPUT_CEILING,
        )
    except BoundedSubprocessError as exc:
        if exc.kind == "timeout":
            raise CampaignRelayError(
                "relay_git_timeout",
                "campaign relay Git probe exceeded its bounded deadline",
            ) from exc
        if exc.kind == "output":
            raise CampaignRelayError(
                "relay_git_output_oversized",
                "campaign relay Git probe exceeded its output ceiling",
            ) from exc
        raise CampaignRelayError(
            "relay_git_unavailable",
            "campaign relay Git probe is unavailable",
        ) from exc
    return result.returncode == 0


def _capsule_remote_ref(commit: str) -> str:
    if len(commit) not in _GIT_OBJECT_LENGTHS or any(character not in "0123456789abcdef" for character in commit):
        raise CampaignRelayError(
            "relay_publication_invalid",
            "campaign relay publication commit is invalid",
        )
    return f"refs/heads/limen-relay/capsule/{commit}"


def _ready_remote_ref(relay_id: str) -> str:
    _relay_names(relay_id)
    return f"refs/heads/limen-relay/ready/{relay_id}"


def _attempt_remote_ref(relay_id: str) -> str:
    _relay_names(relay_id)
    return f"refs/heads/limen-relay/attempt/{relay_id}"


def _latest_remote_ref(workstream: str) -> str:
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", workstream):
        raise CampaignRelayError(
            "relay_workstream_invalid",
            "campaign relay workstream identity is invalid",
        )
    return f"refs/heads/limen-relay/latest/{workstream}"


def _remote_ref_head(
    root: Path,
    ref: str,
    *,
    deadline_monotonic: float | None = None,
) -> str:
    rows = _git(
        root,
        "ls-remote",
        "origin",
        ref,
        deadline_monotonic=deadline_monotonic,
    ).splitlines()
    if len(rows) != 1:
        raise CampaignRelayError(
            "relay_publication_unreachable",
            "campaign relay remote ref is missing or ambiguous",
        )
    fields = rows[0].split("\t")
    if len(fields) != 2 or fields[1] != ref:
        raise CampaignRelayError(
            "relay_publication_unreachable",
            "campaign relay remote ref is malformed",
        )
    head = fields[0]
    if len(head) not in _GIT_OBJECT_LENGTHS or any(character not in "0123456789abcdef" for character in head):
        raise CampaignRelayError(
            "relay_publication_unreachable",
            "campaign relay remote ref identity is malformed",
        )
    return head


def _ensure_remote_branch_contains(
    root: Path,
    *,
    branch: str,
    commit: str,
    deadline_monotonic: float | None = None,
) -> None:
    remote_ref = f"refs/heads/{branch}"
    remote_head = _remote_ref_head(
        root,
        remote_ref,
        deadline_monotonic=deadline_monotonic,
    )
    if remote_head != commit:
        if not _git_succeeds(
            root,
            "fetch",
            "--no-tags",
            "--quiet",
            "--no-write-fetch-head",
            "origin",
            remote_head,
            deadline_monotonic=deadline_monotonic,
        ):
            raise CampaignRelayError(
                "relay_publication_unreachable",
                "campaign relay topic head could not be loaded without checkout mutation",
            )
        if not _git_succeeds(
            root,
            "merge-base",
            "--is-ancestor",
            commit,
            remote_head,
            deadline_monotonic=deadline_monotonic,
        ):
            raise CampaignRelayError(
                "relay_publication_unreachable",
                "campaign relay publication is not reachable from its topic branch",
            )


def _git_common_dir(
    root: Path,
    *,
    deadline_monotonic: float | None = None,
) -> Path:
    raw = _git(
        root,
        "rev-parse",
        "--path-format=absolute",
        "--git-common-dir",
        deadline_monotonic=deadline_monotonic,
    )
    path = Path(raw)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CampaignRelayError(
            "relay_store_unavailable",
            "campaign relay Git common directory is unavailable",
        ) from exc
    if path.is_symlink() or not resolved.is_dir():
        raise CampaignRelayError(
            "relay_store_invalid",
            "campaign relay Git common directory must be a real directory",
        )
    return resolved


def _primary_checkout(
    root: Path,
    *,
    deadline_monotonic: float | None = None,
) -> Path:
    """Derive and verify the primary non-bare checkout from the shared Git directory."""

    common = _git_common_dir(root, deadline_monotonic=deadline_monotonic)
    if common.name != ".git":
        raise CampaignRelayError(
            "relay_primary_checkout_invalid",
            "campaign relay requires a primary non-bare Git checkout",
        )
    primary = common.parent
    try:
        top_level = Path(
            _git(
                primary,
                "rev-parse",
                "--path-format=absolute",
                "--show-toplevel",
                deadline_monotonic=deadline_monotonic,
            )
        ).resolve(strict=True)
        primary_common = _git_common_dir(
            primary,
            deadline_monotonic=deadline_monotonic,
        )
    except OSError as exc:
        raise CampaignRelayError(
            "relay_primary_checkout_invalid",
            "campaign relay primary checkout is unavailable",
        ) from exc
    if primary.is_symlink() or not primary.is_dir() or top_level != primary or primary_common != common:
        raise CampaignRelayError(
            "relay_primary_checkout_invalid",
            "campaign relay primary checkout does not match its Git common directory",
        )
    return primary


def _relay_worktree(
    root: Path,
    successor_slug: str,
    *,
    deadline_monotonic: float | None = None,
) -> Path:
    """Resolve the generated successor worktree and bind it to the same repository."""

    primary = _primary_checkout(
        root,
        deadline_monotonic=deadline_monotonic,
    )
    candidate = primary / ".worktrees" / successor_slug
    try:
        resolved = candidate.resolve(strict=True)
        top_level = Path(
            _git(
                resolved,
                "rev-parse",
                "--path-format=absolute",
                "--show-toplevel",
                deadline_monotonic=deadline_monotonic,
            )
        ).resolve(strict=True)
        worktree_common = _git_common_dir(
            resolved,
            deadline_monotonic=deadline_monotonic,
        )
        primary_common = _git_common_dir(
            primary,
            deadline_monotonic=deadline_monotonic,
        )
    except OSError as exc:
        raise CampaignRelayError(
            "relay_worktree_invalid",
            "campaign relay successor worktree is unavailable",
        ) from exc
    if candidate.is_symlink() or not resolved.is_dir() or top_level != resolved or worktree_common != primary_common:
        raise CampaignRelayError(
            "relay_worktree_invalid",
            "campaign relay successor worktree does not match the primary checkout",
        )
    return resolved


def _verify_store_identity(store: RelayStore) -> None:
    try:
        path_metadata = os.stat(store.path, follow_symlinks=False)
        opened_metadata = os.fstat(store.descriptor)
    except OSError as exc:
        raise CampaignRelayError(
            "relay_store_changed",
            "campaign relay store identity changed during reservation",
        ) from exc
    if (
        not stat.S_ISDIR(path_metadata.st_mode)
        or not stat.S_ISDIR(opened_metadata.st_mode)
        or (path_metadata.st_dev, path_metadata.st_ino) != (opened_metadata.st_dev, opened_metadata.st_ino)
    ):
        raise CampaignRelayError(
            "relay_store_changed",
            "campaign relay store identity changed during reservation",
        )


@contextmanager
def _open_store(
    root: Path,
    *,
    deadline_monotonic: float | None = None,
) -> Iterator[RelayStore]:
    common = _git_common_dir(
        root,
        deadline_monotonic=deadline_monotonic,
    )
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise CampaignRelayError(
            "relay_store_unsupported",
            "campaign relay store requires no-follow directory operations",
        )
    store_path = common / "limen" / "campaign-relays"
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        parent = os.open(common, flags)
        descriptors.append(parent)
        for name in ("limen", "campaign-relays"):
            created = False
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent)
                created = True
            except FileExistsError:
                pass
            if created:
                os.fsync(parent)
            child = os.open(name, flags, dir_fd=parent)
            descriptors.append(child)
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                raise CampaignRelayError(
                    "relay_store_invalid",
                    "campaign relay store must contain only real directories",
                )
            os.fchmod(child, 0o700)
            os.fsync(child)
            parent = child
        store = RelayStore(path=store_path, descriptor=parent)
        _verify_store_identity(store)
        yield store
        _verify_store_identity(store)
    except CampaignRelayError:
        raise
    except OSError as exc:
        raise CampaignRelayError(
            "relay_store_unavailable",
            "campaign relay store is unavailable",
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _relay_names(relay_id: str) -> tuple[str, str]:
    if len(relay_id) != 64 or any(character not in "0123456789abcdef" for character in relay_id):
        raise CampaignRelayError(
            "relay_identity_invalid",
            "relay identity must be a lowercase SHA-256 digest",
        )
    return f"{relay_id}.json", f"{relay_id}.lock"


@contextmanager
def campaign_relay_lock(
    root: Path,
    relay_id: str,
    *,
    timeout_seconds: float = _LOCK_ACQUIRE_TIMEOUT_SECONDS,
    deadline_monotonic: float | None = None,
) -> Iterator[RelayStore]:
    """Hold the cross-beat relay lock for one bounded reservation phase."""

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not 0 < timeout_seconds <= 30
    ):
        raise CampaignRelayError(
            "relay_lock_timeout_invalid",
            "campaign relay lock timeout must be between 0 and 30 seconds",
        )
    _receipt_name, lock_name = _relay_names(relay_id)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with _open_store(root, deadline_monotonic=deadline_monotonic) as store:
        for attempt in range(2):
            try:
                descriptor = os.open(lock_name, flags, 0o600, dir_fd=store.descriptor)
                break
            except FileNotFoundError as exc:
                if attempt == 0:
                    _verify_store_identity(store)
                    continue
                raise CampaignRelayError(
                    "relay_lock_unavailable",
                    "campaign relay lock is unavailable",
                ) from exc
            except OSError as exc:
                raise CampaignRelayError(
                    "relay_lock_unavailable",
                    "campaign relay lock is unavailable",
                ) from exc
        locked = False
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise CampaignRelayError(
                    "relay_lock_invalid",
                    "campaign relay lock must be a regular file",
                )
            os.fchmod(descriptor, 0o600)
            deadline = time.monotonic() + _deadline_timeout(
                deadline_monotonic,
                timeout_seconds,
            )
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise CampaignRelayError(
                            "relay_lock_busy",
                            "campaign relay lock remained busy past its bounded acquire deadline",
                        ) from None
                    time.sleep(min(0.01, remaining))
            yield store
        finally:
            try:
                if locked:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _read_receipt(store: RelayStore, receipt_name: str) -> CampaignRelayReceiptV1 | None:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(receipt_name, flags, dir_fd=store.descriptor)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CampaignRelayError(
            "relay_receipt_unavailable",
            "campaign relay receipt is unavailable",
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise CampaignRelayError(
                "relay_receipt_invalid",
                "campaign relay receipt must be a private regular file",
            )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(_RECEIPT_CEILING + 1)
    except OSError as exc:
        raise CampaignRelayError(
            "relay_receipt_unreadable",
            "campaign relay receipt is unreadable",
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > _RECEIPT_CEILING:
        raise CampaignRelayError(
            "relay_receipt_oversized",
            "campaign relay receipt exceeds its bounded size",
        )
    try:
        return CampaignRelayReceiptV1.model_validate_json(raw)
    except ValueError as exc:
        raise CampaignRelayError(
            "relay_receipt_invalid",
            "campaign relay receipt is invalid",
        ) from exc


def _write_receipt(
    store: RelayStore,
    receipt_name: str,
    receipt: CampaignRelayReceiptV1,
) -> None:
    payload = (
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True, separators=(",", ": ")) + "\n"
    ).encode("utf-8")
    if len(payload) > _RECEIPT_CEILING:
        raise CampaignRelayError(
            "relay_receipt_oversized",
            "campaign relay receipt exceeds its bounded size",
        )
    temporary = f".{receipt_name}.tmp.{os.getpid()}.{threading.get_ident()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600, dir_fd=store.descriptor)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary,
            receipt_name,
            src_dir_fd=store.descriptor,
            dst_dir_fd=store.descriptor,
        )
        os.fsync(store.descriptor)
    except OSError as exc:
        raise CampaignRelayError(
            "relay_receipt_write_failed",
            "campaign relay receipt could not be recorded",
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=store.descriptor)
        except FileNotFoundError:
            pass


def _tracked_predecessor(
    root: Path,
    receipt_path: Path,
    *,
    exact_remote_main: str,
    predecessor_commit: str | None = None,
) -> tuple[str, dict[str, Any]]:
    if len(exact_remote_main) not in _GIT_OBJECT_LENGTHS or any(
        character not in "0123456789abcdef" for character in exact_remote_main
    ):
        raise CampaignRelayError(
            "relay_remote_main_invalid",
            "exact remote main must be a lowercase Git object id",
        )
    root = root.resolve()
    source_commit = exact_remote_main
    if predecessor_commit is None:
        try:
            resolved = receipt_path.resolve(strict=True)
            relative = resolved.relative_to(root).as_posix()
        except (OSError, ValueError) as exc:
            raise CampaignRelayError(
                "relay_predecessor_invalid",
                "predecessor receipt must be a real file inside the checkout",
            ) from exc
        if receipt_path.is_symlink() or not resolved.is_file():
            raise CampaignRelayError(
                "relay_predecessor_invalid",
                "predecessor receipt must be a real file",
            )
    else:
        if len(predecessor_commit) not in _GIT_OBJECT_LENGTHS or any(
            character not in "0123456789abcdef" for character in predecessor_commit
        ):
            raise CampaignRelayError(
                "relay_predecessor_invalid",
                "predecessor commit must be an exact lowercase Git object id",
            )
        relative_path = PurePosixPath(receipt_path.as_posix())
        if (
            len(relative_path.parts) != 4
            or relative_path.parts[:2] != ("docs", "continuations")
            or relative_path.name != "workstream.json"
            or any(part in {"", ".", ".."} for part in relative_path.parts)
        ):
            raise CampaignRelayError(
                "relay_predecessor_invalid",
                "predecessor receipt path is not canonical",
            )
        resolved_commit = _git(root, "rev-parse", f"{predecessor_commit}^{{commit}}")
        if resolved_commit != predecessor_commit:
            raise CampaignRelayError(
                "relay_predecessor_invalid",
                "predecessor commit is not one exact immutable commit",
            )
        source_commit = predecessor_commit
        relative = relative_path.as_posix()
    blob = _git(root, "rev-parse", f"{source_commit}:{relative}")
    if len(blob) not in _GIT_OBJECT_LENGTHS or any(character not in "0123456789abcdef" for character in blob):
        raise CampaignRelayError(
            "relay_predecessor_invalid",
            "predecessor receipt did not resolve to one Git blob",
        )
    try:
        blob_size = int(_git(root, "cat-file", "-s", blob))
    except ValueError as exc:
        raise CampaignRelayError(
            "relay_predecessor_invalid",
            "predecessor receipt Git blob size is invalid",
        ) from exc
    if not 0 < blob_size <= _PREDECESSOR_RECEIPT_CEILING:
        raise CampaignRelayError(
            "relay_predecessor_oversized",
            "predecessor receipt exceeds its bounded size",
        )
    raw = _git_bytes(
        root,
        "cat-file",
        "blob",
        blob,
        output_ceiling=_PREDECESSOR_RECEIPT_CEILING,
    )
    if len(raw) != blob_size:
        raise CampaignRelayError(
            "relay_predecessor_invalid",
            "predecessor receipt Git blob size changed during capture",
        )
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignRelayError(
            "relay_predecessor_invalid",
            "committed predecessor receipt is invalid JSON",
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema") != RECEIPT_SCHEMA:
        raise CampaignRelayError(
            "relay_predecessor_invalid",
            "predecessor receipt schema is unsupported",
        )
    try:
        contract = validate_contract(payload.get("contract"))
    except ContractError as exc:
        raise CampaignRelayError(
            "relay_predecessor_invalid",
            "predecessor contract is invalid",
        ) from exc
    if payload.get("workstream") != "institutional-omega":
        raise CampaignRelayError(
            "relay_predecessor_invalid",
            "automatic succession is limited to institutional-omega",
        )
    return blob, contract


def _relay_identity_digest(
    *,
    workstream: str,
    predecessor_receipt_blob: str,
    predecessor_contract_digest: str,
    predecessor_deadline_epoch: int,
) -> str:
    return canonical_hash(
        {
            "workstream": workstream,
            "predecessor_receipt_blob": predecessor_receipt_blob,
            "predecessor_contract_digest": predecessor_contract_digest,
            "predecessor_deadline_epoch": predecessor_deadline_epoch,
        }
    )


def relay_identity(
    root: Path,
    predecessor: Path,
    *,
    exact_remote_main: str,
    predecessor_commit: str | None = None,
) -> CampaignRelayReceiptV1:
    """Derive one stable successor identity without writing or launching anything."""

    blob, contract = _tracked_predecessor(
        root,
        predecessor,
        exact_remote_main=exact_remote_main,
        predecessor_commit=predecessor_commit,
    )
    deadline = contract["runway"].get("deadline_epoch")
    if isinstance(deadline, bool) or not isinstance(deadline, int) or deadline <= 0:
        raise CampaignRelayError(
            "relay_predecessor_unadmitted",
            "predecessor campaign has not been admitted",
        )
    try:
        contract_digest = canonical_hash(contract)
    except rfc8785.CanonicalizationError as exc:
        raise CampaignRelayError(
            "relay_predecessor_invalid",
            "committed predecessor contract cannot be canonicalized",
        ) from exc
    relay_id = _relay_identity_digest(
        workstream="institutional-omega",
        predecessor_receipt_blob=blob,
        predecessor_contract_digest=contract_digest,
        predecessor_deadline_epoch=deadline,
    )
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
    predecessor_commit: str | None = None,
) -> RelayReservation:
    """Persist the reservation before any worktree creation or provider spawn."""

    expected = relay_identity(
        root,
        predecessor,
        exact_remote_main=exact_remote_main,
        predecessor_commit=predecessor_commit,
    )
    receipt_name, _lock_name = _relay_names(expected.relay_id)
    with campaign_relay_lock(root, expected.relay_id) as store:
        existing = _read_receipt(store, receipt_name)
        if existing is not None:
            if (
                _relay_identity_digest(
                    workstream=existing.workstream,
                    predecessor_receipt_blob=existing.predecessor_receipt_blob,
                    predecessor_contract_digest=existing.predecessor_contract_digest,
                    predecessor_deadline_epoch=existing.predecessor_deadline_epoch,
                )
                != existing.relay_id
                or existing.relay_id != expected.relay_id
                or any(
                    getattr(existing, field) != getattr(expected, field)
                    for field in (
                        "workstream",
                        "predecessor_receipt_blob",
                        "predecessor_contract_digest",
                        "predecessor_deadline_epoch",
                        "successor_slug",
                        "successor_branch",
                        "successor_session_id",
                    )
                )
            ):
                raise CampaignRelayError(
                    "relay_receipt_conflict",
                    "stored relay identity conflicts with the predecessor",
                )
            if existing.state == "reserved" and existing.exact_remote_main != expected.exact_remote_main:
                existing = CampaignRelayReceiptV1.model_validate(
                    {
                        **existing.model_dump(mode="json"),
                        "exact_remote_main": expected.exact_remote_main,
                    }
                )
                _write_receipt(store, receipt_name, existing)
            return RelayReservation(receipt=existing, created=False)
        _write_receipt(store, receipt_name, expected)
        return RelayReservation(receipt=expected, created=True)


def launch_reserved_relay(*args: Any, **kwargs: Any) -> RelayLaunch:
    from limen.conduct.campaign_relay_protocol import launch_reserved_relay as implementation

    return implementation(*args, **kwargs)


def discover_ready_relay(*args: Any, **kwargs: Any) -> ReadyRelayCapsule:
    from limen.conduct.campaign_relay_protocol import discover_ready_relay as implementation

    return implementation(*args, **kwargs)


def relay_boundary_projection(receipt: CampaignRelayReceiptV1) -> dict[str, Any]:
    from limen.conduct.campaign_relay_protocol import relay_boundary_projection as implementation

    return implementation(receipt)
