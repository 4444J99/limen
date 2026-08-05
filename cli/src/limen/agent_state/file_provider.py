"""Private, resumable integration with the Domus File Provider adapter."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .atomize import canonical_bytes
from .crypto import verify_atom_packs
from .models import MetabolismReceipt
from .pipeline import PipelineError
from .tree import NON_EVICTABLE_CLOUD_NAMES, RetentionPlan, is_materialized_cloud_path

MANIFEST_SCHEMA = "domus.file_provider_evict_manifest.v1"
CAMPAIGN_PLAN_SCHEMA = "domus.file_provider_evict_campaign_plan.v1"
RECEIPT_SCHEMA = "domus.file_provider_evict_receipt.v1"
AUTHORIZATION_SCHEMA = "domus.host_mutation_authorization.v2"
CAMPAIGN_AUTHORIZATION_SCHEMA = "domus.host_mutation_authorization.v3"
STANDING_AUTHORIZATION_SCHEMA = "domus.host_mutation_standing_authority.v1"
DERIVED_CAPABILITY_SCHEMA = "domus.host_mutation_child_capability.v1"
PROGRESS_SCHEMA = "limen.file_provider_evict_progress.v1"
AUTHORIZATION_ACTION = "file_provider_evict.apply"
CAMPAIGN_AUTHORIZATION_ACTION = "file_provider_evict.apply_campaign"
ADAPTER_NAME = "domus-file-provider-evict"

MAX_BATCH_ITEMS = 1_000
MAX_CAMPAIGN_ITEMS = 100_000
BATCH_TIMEOUT_SECONDS = 15 * 60
ITEM_TIMEOUT_SECONDS = 60
MAX_ADAPTER_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_AUTHORIZATION_BYTES = 8 * 1024 * 1024
MAX_SIGNATURE_BYTES = 32 * 1024
MAX_PROGRESS_BYTES = 64 * 1024 * 1024
MAX_CONTENT_VERIFICATION_INPUT_BYTES = 32 * 1024 * 1024

_CONTENT_HASH_HELPER = r"""
import hashlib
import json
import os
import stat
import sys

paths = json.load(sys.stdin)
digests = []
for path in paths:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("not a regular file")
        digest = hashlib.sha256()
        while True:
            block = os.read(descriptor, 4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    current = os.lstat(path)
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if (
        any(getattr(before, key) != getattr(after, key) for key in identity)
        or any(getattr(after, key) != getattr(current, key) for key in identity)
        or stat.S_ISLNK(current.st_mode)
    ):
        raise OSError("file identity changed during verification")
    digests.append(digest.hexdigest())
json.dump(digests, sys.stdout, separators=(",", ":"))
"""

HEX64 = re.compile(r"^[0-9a-f]{64}$")
BASE64_TEXT = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$")  # allow-secret: syntax regex, not a credential
SUCCESS_STATUSES = frozenset({"evicted", "already_dataless"})
ITEM_STATUSES = frozenset({*SUCCESS_STATUSES, "retained", "failed"})


@dataclass(frozen=True)
class CapturedFile:
    relative: str
    bytes: int
    mtime_ns: int
    mode: int
    sha256: str
    record: dict[str, Any]


@dataclass(frozen=True)
class FileProviderItem:
    captured: CapturedFile
    path: Path
    url: str
    item_hash: str
    materialized: bool
    allocated_bytes: int
    retained_metadata: bool


@dataclass(frozen=True)
class FileProviderResult:
    selected_files: int
    evicted_files: int
    already_reclaimed_files: int
    retained_non_evictable_files: int
    retained_non_evictable_bytes: int
    allocated_after: int
    remaining_files: int
    complete: bool
    authorization_prepared: bool = False


@dataclass(frozen=True)
class RestoredFileResult:
    item_hash: str
    status: str
    bytes: int
    sha256: str
    selector_kind: str = "file_provider_item_hash"
    selector_hash: str | None = None


def progress_path_for(private_receipt: Path) -> Path:
    return private_receipt.with_name(f"{private_receipt.stem}.file-provider-progress.json")


def file_provider_item_hash(root: Path, relative: str) -> str:
    url = (root.expanduser().resolve() / relative).absolute().as_uri()
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def captured_path_selector_hash(relative: str) -> str:
    """Hash one immutable captured relative path without exposing it."""

    return hashlib.sha256(b"captured-path:v1\0" + relative.encode("utf-8")).hexdigest()


def captured_name_selector_hash(relative: str) -> str:
    """Hash a captured basename; restoration still requires one unique match."""

    name = PurePosixPath(relative).name
    return hashlib.sha256(b"captured-name:v1\0" + name.encode("utf-8")).hexdigest()


def collect_file_entry(records: list[dict[str, Any]], record: dict[str, Any]) -> None:
    if record.get("kind") == "file_entry":
        records.append(record)


def _collect_restore_metadata(
    records: list[dict[str, Any]],
    chunk_lengths: dict[str, int],
    record: dict[str, Any],
) -> None:
    kind = record.get("kind")
    if kind == "file_entry":
        records.append(record)
        return
    if kind != "file_chunk" or set(record) != {"kind", "chunk_sha256", "value_b64"}:
        raise PipelineError("captured restore atom has an invalid shape")
    digest = record.get("chunk_sha256")
    encoded = record.get("value_b64")
    if (
        not isinstance(digest, str)
        or not HEX64.fullmatch(digest)
        or not isinstance(encoded, str)
        or len(encoded) % 4
        or not BASE64_TEXT.fullmatch(encoded)
    ):
        raise PipelineError("captured restore chunk has invalid fields")
    padding = len(encoded) - len(encoded.rstrip("="))
    meaningful = len(encoded) - padding
    if meaningful % 4 != {0: 0, 1: 3, 2: 2}[padding]:
        raise PipelineError("captured restore chunk has invalid base64")
    decoded_length = (len(encoded) // 4) * 3 - padding
    if decoded_length <= 0 or digest in chunk_lengths:
        raise PipelineError("captured restore chunk is empty or duplicated")
    chunk_lengths[digest] = decoded_length


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


@contextmanager
def _open_restore_parent(root: Path, relative: PurePosixPath) -> Iterator[tuple[int, int, tuple[str, ...], str]]:
    """Anchor the root and every parent without following a captured-path symlink."""

    descriptors: list[int] = []
    try:
        descriptors.append(os.open(root, _directory_flags()))
        for component in relative.parts[:-1]:
            descriptor = os.open(component, _directory_flags(), dir_fd=descriptors[-1])
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise PipelineError("restore target parent changed type")
            descriptors.append(descriptor)
        yield descriptors[0], descriptors[-1], tuple(relative.parts[:-1]), relative.parts[-1]
    except FileNotFoundError:
        raise PipelineError("restore target parent is logically missing") from None
    except OSError:
        raise PipelineError("restore target parent is unavailable or changed type") from None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _restore_parent_is_current(
    root: Path,
    root_descriptor: int,
    parent_descriptor: int,
    components: tuple[str, ...],
) -> bool:
    """Re-walk the no-follow namespace before placement and compare anchored identities."""

    descriptors: list[int] = []
    try:
        descriptors.append(os.open(root, _directory_flags()))
        expected_root = os.fstat(root_descriptor)
        observed_root = os.fstat(descriptors[0])
        if (observed_root.st_dev, observed_root.st_ino) != (expected_root.st_dev, expected_root.st_ino):
            return False
        for component in components:
            descriptors.append(os.open(component, _directory_flags(), dir_fd=descriptors[-1]))
        expected_parent = os.fstat(parent_descriptor)
        observed_parent = os.fstat(descriptors[-1])
        return (observed_parent.st_dev, observed_parent.st_ino) == (
            expected_parent.st_dev,
            expected_parent.st_ino,
        )
    except OSError:
        return False
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while True:
        value = os.pread(descriptor, 1024 * 1024, offset)
        if not value:
            return digest.hexdigest()
        digest.update(value)
        offset += len(value)


def _pwrite_all(descriptor: int, value: bytes, offset: int) -> None:
    view = memoryview(value)
    written = 0
    while written < len(view):
        count = os.pwrite(descriptor, view[written:], offset + written)
        if count <= 0:
            raise OSError("short restore write")
        written += count


def _create_restore_temporary(parent_descriptor: int) -> tuple[int, str]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    for _attempt in range(128):
        name = f".limen-restore-{secrets.token_hex(16)}"
        try:
            return os.open(name, flags, 0o600, dir_fd=parent_descriptor), name
        except FileExistsError:
            continue
        except OSError:
            raise PipelineError("cannot create conflict-safe restore staging file") from None
    raise PipelineError("cannot allocate a unique restore staging file")


def _integer(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PipelineError(f"captured File Provider entry has invalid {field}")
    return value


def _captured_file(record: dict[str, Any]) -> CapturedFile:
    expected = {"kind", "path", "bytes", "mtime_ns", "mode", "sha256", "chunks"}
    if set(record) != expected or record.get("kind") != "file_entry":
        raise PipelineError("captured File Provider entry has an invalid shape")
    raw_path = record.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise PipelineError("captured File Provider entry has an invalid relative path")
    relative = PurePosixPath(raw_path)
    if (
        relative.is_absolute()
        or relative.as_posix() != raw_path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise PipelineError("captured File Provider entry has an unsafe relative path")
    size = _integer(record.get("bytes"), field="byte count")
    mtime_ns = _integer(record.get("mtime_ns"), field="mtime")
    mode = _integer(record.get("mode"), field="mode")
    digest = record.get("sha256")
    chunks = record.get("chunks")
    if mode > 0o777 or not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise PipelineError("captured File Provider entry has invalid metadata")
    if not isinstance(chunks, list) or not all(isinstance(value, str) and HEX64.fullmatch(value) for value in chunks):
        raise PipelineError("captured File Provider entry has an invalid chunk list")
    return CapturedFile(
        relative=raw_path,
        bytes=size,
        mtime_ns=mtime_ns,
        mode=mode,
        sha256=digest,
        record=record,
    )


def reconstruct_captured_files(
    receipt: MetabolismReceipt,
    root: Path,
    records: list[dict[str, Any]],
) -> tuple[CapturedFile, ...]:
    """Rebuild the original captured set from a fully verified atom stream."""

    root = root.expanduser().resolve()
    if receipt.source.kind != "file-tree" or Path(receipt.source.path).expanduser().resolve() != root:
        raise PipelineError("captured File Provider root does not match the resume request")
    captured = tuple(_captured_file(record) for record in records)
    relatives = [entry.relative for entry in captured]
    if not captured or relatives != sorted(relatives) or len(set(relatives)) != len(relatives):
        raise PipelineError("captured File Provider entries are empty, duplicated, or unordered")
    digest = hashlib.sha256()
    total = 0
    for entry in captured:
        digest.update(canonical_bytes(entry.record) + b"\n")
        total += entry.bytes
    if (
        len(captured) != receipt.source.stat_after[1]
        or total != receipt.source.bytes
        or digest.hexdigest() != receipt.source.sha256
    ):
        raise PipelineError("captured File Provider entries do not match immutable custody")
    return captured


def retention_plan_from_capture(
    receipt: MetabolismReceipt,
    root: Path,
    captured: tuple[CapturedFile, ...],
) -> RetentionPlan:
    return RetentionPlan(
        root=root.expanduser().resolve(),
        cold_paths=tuple(entry.relative for entry in captured),
        cold_bytes=sum(entry.bytes for entry in captured),
        hot_paths=(),
        hot_bytes=int(receipt.retained_hot_bytes or 0),
        cutoff_epoch=0.0,
        maximum_hot_bytes=0,
    )


def inspect_captured_files(
    root: Path,
    captured: tuple[CapturedFile, ...],
    *,
    materialized_probe=is_materialized_cloud_path,
) -> tuple[FileProviderItem, ...]:
    """Validate the logical namespace without hydrating dataless placeholders."""

    root = root.expanduser().resolve()
    inspected: list[FileProviderItem] = []
    for entry in captured:
        path = root / entry.relative
        try:
            value = path.lstat()
        except OSError as exc:
            raise PipelineError("captured File Provider item is logically missing") from exc
        if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
            raise PipelineError("captured File Provider item changed type")
        if value.st_size != entry.bytes or value.st_mtime_ns != entry.mtime_ns or value.st_mode & 0o777 != entry.mode:
            raise PipelineError("captured File Provider item metadata mutated")
        try:
            materialized = bool(materialized_probe(path))
        except OSError as exc:
            raise PipelineError("captured File Provider materialization state is unreadable") from exc
        url = path.absolute().as_uri()
        inspected.append(
            FileProviderItem(
                captured=entry,
                path=path,
                url=url,
                item_hash=hashlib.sha256(url.encode("utf-8")).hexdigest(),
                materialized=materialized,
                allocated_bytes=value.st_blocks * 512,
                retained_metadata=path.name in NON_EVICTABLE_CLOUD_NAMES,
            )
        )
    hashes = [item.item_hash for item in inspected]
    if len(set(hashes)) != len(hashes):
        raise PipelineError("captured File Provider item identity collided")
    return tuple(inspected)


def restore_captured_file(
    receipt: MetabolismReceipt,
    root: Path,
    payload_root: Path,
    key: str,
    item_hash: str | None = None,
    *,
    captured_path_hash: str | None = None,
    captured_name_hash: str | None = None,
    materialized_probe=is_materialized_cloud_path,
    before_mutation: Callable[[RestoredFileResult], None] | None = None,
) -> RestoredFileResult:
    """Restore one captured item without exposing or overwriting its path."""

    selectors = tuple(
        (kind, value)
        for kind, value in (
            ("file_provider_item_hash", item_hash),
            ("captured_path_hash", captured_path_hash),
            ("captured_name_hash", captured_name_hash),
        )
        if value is not None
    )
    if len(selectors) != 1:
        raise PipelineError("restore requires exactly one path-free selector")
    selector_kind, selector_hash = selectors[0]
    if not HEX64.fullmatch(selector_hash):
        raise PipelineError("restore selector must be lowercase sha256")
    receipt.require_retirement_gate()
    root = root.expanduser().resolve()
    records: list[dict[str, Any]] = []
    chunk_lengths: dict[str, int] = {}
    # Capture order places each file's chunks before its file_entry, so the selector cannot be
    # resolved until a full verified pass completes. Retain only metadata here; a second verified
    # pass writes only the selected chunks. A one-pass design would have to spill every captured
    # file, which is substantially less bounded than decrypting twice.
    proof = verify_atom_packs(
        receipt.packs,
        payload_root,
        key,
        logical_sha256=receipt.logical_sha256,
        record_consumer=lambda record: _collect_restore_metadata(records, chunk_lengths, record),
    )
    if not proof.passed:
        raise PipelineError("captured File Provider atoms failed full restoration")
    captured = reconstruct_captured_files(receipt, root, records)
    if selector_kind == "file_provider_item_hash":
        matches = [entry for entry in captured if file_provider_item_hash(root, entry.relative) == selector_hash]
    elif selector_kind == "captured_path_hash":
        matches = [entry for entry in captured if captured_path_selector_hash(entry.relative) == selector_hash]
    else:
        matches = [entry for entry in captured if captured_name_selector_hash(entry.relative) == selector_hash]
    if len(matches) != 1:
        raise PipelineError("restore selector does not identify exactly one captured file")
    entry = matches[0]
    canonical_item_hash = file_provider_item_hash(root, entry.relative)
    target = root / entry.relative
    relative = PurePosixPath(entry.relative)
    chunk_hashes = tuple(entry.record["chunks"])
    offsets: dict[str, list[int]] = {}
    offset = 0
    for digest in chunk_hashes:
        length = chunk_lengths.get(digest)
        if length is None:
            raise PipelineError("captured restore entry references a missing chunk")
        offsets.setdefault(digest, []).append(offset)
        offset += length
    if offset != entry.bytes:
        raise PipelineError("captured restore chunks do not match the file byte count")

    with _open_restore_parent(root, relative) as (
        root_descriptor,
        parent_descriptor,
        parent_components,
        target_name,
    ):
        try:
            existing = os.stat(target_name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        except OSError:
            raise PipelineError("restore target metadata is unreadable") from None
        if existing is not None:
            if (
                stat.S_ISLNK(existing.st_mode)
                or not stat.S_ISREG(existing.st_mode)
                or existing.st_size != entry.bytes
                or existing.st_mtime_ns != entry.mtime_ns
                or existing.st_mode & 0o777 != entry.mode
            ):
                raise PipelineError("restore target exists with conflicting metadata")
            try:
                materialized = bool(materialized_probe(target))
            except OSError:
                raise PipelineError("restore target materialization state is unreadable") from None
            if not _restore_parent_is_current(
                root,
                root_descriptor,
                parent_descriptor,
                parent_components,
            ):
                raise PipelineError("restore target parent changed during inspection")
            if not materialized:
                result = RestoredFileResult(
                    item_hash=canonical_item_hash,
                    status="already_dataless",
                    bytes=entry.bytes,
                    sha256=entry.sha256,
                    selector_kind=selector_kind,
                    selector_hash=selector_hash,
                )
                if before_mutation is not None:
                    before_mutation(result)
                return result
            try:
                descriptor = os.open(
                    target_name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=parent_descriptor,
                )
                try:
                    before = os.fstat(descriptor)
                    digest = _sha256_descriptor(descriptor)
                    after = os.fstat(descriptor)
                finally:
                    os.close(descriptor)
            except OSError:
                raise PipelineError("restore target content is unreadable") from None
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ) or digest != entry.sha256:
                raise PipelineError("restore target exists with conflicting content")
            result = RestoredFileResult(
                item_hash=canonical_item_hash,
                status="already_restored",
                bytes=entry.bytes,
                sha256=entry.sha256,
                selector_kind=selector_kind,
                selector_hash=selector_hash,
            )
            if before_mutation is not None:
                before_mutation(result)
            return result

        result = RestoredFileResult(
            item_hash=canonical_item_hash,
            status="restored",
            bytes=entry.bytes,
            sha256=entry.sha256,
            selector_kind=selector_kind,
            selector_hash=selector_hash,
        )
        if before_mutation is not None:
            before_mutation(result)

        temporary_descriptor, temporary_name = _create_restore_temporary(parent_descriptor)
        linked = False
        verified = False
        temporary_identity: tuple[int, int] | None = None
        seen: set[str] = set()

        def collect_chunk(record: dict[str, Any]) -> None:
            if record.get("kind") != "file_chunk" or record.get("chunk_sha256") not in offsets:
                return
            if set(record) != {"kind", "chunk_sha256", "value_b64"}:
                raise PipelineError("captured restore chunk has an invalid shape")
            digest = record["chunk_sha256"]
            encoded = record["value_b64"]
            if not isinstance(digest, str) or not isinstance(encoded, str):
                raise PipelineError("captured restore chunk has invalid fields")
            try:
                value = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                raise PipelineError("captured restore chunk has invalid base64") from None
            if len(value) != chunk_lengths[digest]:
                raise PipelineError("captured restore chunk has an invalid byte count")
            if hashlib.sha256(b"file-chunk:v1\0" + value).hexdigest() != digest:
                raise PipelineError("captured restore chunk failed content verification")
            if digest in seen:
                raise PipelineError("captured restore chunk is duplicated")
            for chunk_offset in offsets[digest]:
                _pwrite_all(temporary_descriptor, value, chunk_offset)
            seen.add(digest)

        try:
            try:
                os.fchmod(temporary_descriptor, 0o600)
                chunk_proof = verify_atom_packs(
                    receipt.packs,
                    payload_root,
                    key,
                    logical_sha256=receipt.logical_sha256,
                    record_consumer=collect_chunk,
                )
                if not chunk_proof.passed or seen != set(offsets):
                    raise PipelineError("captured restore chunks failed full restoration")
                os.fsync(temporary_descriptor)
                staged = os.fstat(temporary_descriptor)
                if staged.st_size != entry.bytes or _sha256_descriptor(temporary_descriptor) != entry.sha256:
                    raise PipelineError("reconstructed restore file failed content verification")
                os.fchmod(temporary_descriptor, entry.mode)
                os.utime(
                    temporary_name,
                    ns=(entry.mtime_ns, entry.mtime_ns),
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                os.fsync(temporary_descriptor)
                staged = os.fstat(temporary_descriptor)
                temporary_identity = staged.st_dev, staged.st_ino
                if not _restore_parent_is_current(
                    root,
                    root_descriptor,
                    parent_descriptor,
                    parent_components,
                ):
                    raise PipelineError("restore target parent changed during reconstruction")
                os.link(
                    temporary_name,
                    target_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                linked = True
                restored_descriptor = os.open(
                    target_name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=parent_descriptor,
                )
                try:
                    restored = os.fstat(restored_descriptor)
                    restored_digest = _sha256_descriptor(restored_descriptor)
                finally:
                    os.close(restored_descriptor)
                if (
                    (restored.st_dev, restored.st_ino) != temporary_identity
                    or not stat.S_ISREG(restored.st_mode)
                    or restored.st_size != entry.bytes
                    or restored.st_mtime_ns != entry.mtime_ns
                    or restored.st_mode & 0o777 != entry.mode
                    or restored_digest != entry.sha256
                ):
                    raise PipelineError("restored File Provider item failed postflight verification")
                if not _restore_parent_is_current(
                    root,
                    root_descriptor,
                    parent_descriptor,
                    parent_components,
                ):
                    raise PipelineError("restore target parent changed during placement")
                verified = True
            except FileExistsError:
                raise PipelineError("restore target appeared before conflict-safe placement") from None
            except OSError:
                raise PipelineError("restore placement failed") from None
        finally:
            if linked and not verified and temporary_identity is not None:
                try:
                    placed = os.stat(target_name, dir_fd=parent_descriptor, follow_symlinks=False)
                    if (placed.st_dev, placed.st_ino) == temporary_identity:
                        os.unlink(target_name, dir_fd=parent_descriptor)
                except OSError:
                    pass
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except OSError:
                pass
            try:
                os.close(temporary_descriptor)
            except OSError:
                pass
        return result


def verify_materialized_content(
    items: tuple[FileProviderItem, ...],
    *,
    timeout_seconds: int = BATCH_TIMEOUT_SECONDS,
) -> None:
    """Verify a bounded set without allowing one File Provider read to stall."""

    materialized = tuple(item for item in items if item.materialized)
    if not materialized:
        return
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds < 1
        or timeout_seconds > BATCH_TIMEOUT_SECONDS
    ):
        raise PipelineError("File Provider content verification deadline is invalid")
    payload = canonical_bytes([str(item.path) for item in materialized])
    if len(payload) > MAX_CONTENT_VERIFICATION_INPUT_BYTES:
        raise PipelineError("File Provider content verification input is too large")
    try:
        result = subprocess.run(
            [sys.executable, "-c", _CONTENT_HASH_HELPER],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError("File Provider content verification exceeded its bounded deadline") from exc
    except OSError as exc:
        raise PipelineError("captured File Provider item content is unreadable") from exc
    maximum_output = len(materialized) * 67 + 2
    if result.returncode != 0 or not result.stdout or len(result.stdout) > maximum_output:
        raise PipelineError("captured File Provider item content is unreadable")
    try:
        digests = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("File Provider content verification emitted an invalid response") from exc
    if (
        not isinstance(digests, list)
        or len(digests) != len(materialized)
        or any(not isinstance(value, str) or not HEX64.fullmatch(value) for value in digests)
    ):
        raise PipelineError("File Provider content verification emitted an invalid response")
    for item, digest in zip(materialized, digests):
        if digest != item.captured.sha256:
            raise PipelineError("captured File Provider item content mutated")


def _custody_sha256(receipt: MetabolismReceipt) -> str:
    value = receipt.as_dict()
    value["source_retired"] = False
    value["retirement_proof"] = None
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _item_set_sha256(items: tuple[FileProviderItem, ...]) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "eligible": [item.item_hash for item in items if not item.retained_metadata],
                "retained": [item.item_hash for item in items if item.retained_metadata],
            }
        )
    ).hexdigest()


def _new_progress(receipt: MetabolismReceipt, items: tuple[FileProviderItem, ...]) -> dict[str, Any]:
    eligible = [item for item in items if not item.retained_metadata]
    retained = [item for item in items if item.retained_metadata]
    return {
        "schema": PROGRESS_SCHEMA,
        "run_id": receipt.run_id,
        "custody_sha256": _custody_sha256(receipt),
        "item_set_sha256": _item_set_sha256(items),
        "eligible_item_count": len(eligible),
        "retained_items": [
            {
                "item_hash": item.item_hash,
                "status": "retained",
                "reason": "non_evictable_metadata",
            }
            for item in retained
        ],
        "completed_items": [],
        "pending_batch": None,
        "next_attempt": 0,
        "receipts": [],
    }


def _secure_read(path: Path, *, limit: int, label: str) -> bytes:
    try:
        value = path.lstat()
    except OSError as exc:
        raise PipelineError(f"{label} is missing or unreadable") from exc
    if (
        stat.S_ISLNK(value.st_mode)
        or not stat.S_ISREG(value.st_mode)
        or value.st_uid not in {0, os.getuid()}
        or value.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or value.st_size <= 0
        or value.st_size > limit
    ):
        raise PipelineError(f"{label} failed private-file checks")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise PipelineError(f"{label} is missing or unreadable") from exc
    if len(payload) != value.st_size:
        raise PipelineError(f"{label} changed while being read")
    return payload


def _atomic_private_write(path: Path, payload: bytes) -> None:
    path = path.expanduser().absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _hash_entry(value: object, *, status: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError("File Provider progress contains a malformed item")
    expected = {"item_hash", "status", "provider_item_hash", "domain_hash"}
    if set(value) != expected:
        raise PipelineError("File Provider progress contains a malformed item")
    item_hash = value.get("item_hash")
    item_status = value.get("status")
    if (
        not isinstance(item_hash, str)
        or not HEX64.fullmatch(item_hash)
        or item_status not in SUCCESS_STATUSES
        or not isinstance(value.get("provider_item_hash"), str)
        or not HEX64.fullmatch(value["provider_item_hash"])
        or not isinstance(value.get("domain_hash"), str)
        or not HEX64.fullmatch(value["domain_hash"])
    ):
        raise PipelineError("File Provider progress contains a malformed item")
    if status and item_status not in SUCCESS_STATUSES:
        raise PipelineError("File Provider progress contains an incomplete item")
    return dict(value)


def _load_progress(
    path: Path,
    receipt: MetabolismReceipt,
    items: tuple[FileProviderItem, ...],
) -> dict[str, Any]:
    if not path.exists():
        return _new_progress(receipt, items)
    payload = _secure_read(path, limit=MAX_PROGRESS_BYTES, label="File Provider progress receipt")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("File Provider progress receipt is invalid") from exc
    expected = {
        "schema",
        "run_id",
        "custody_sha256",
        "item_set_sha256",
        "eligible_item_count",
        "retained_items",
        "completed_items",
        "pending_batch",
        "next_attempt",
        "receipts",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise PipelineError("File Provider progress receipt has an invalid shape")
    eligible = [item.item_hash for item in items if not item.retained_metadata]
    retained = [item.item_hash for item in items if item.retained_metadata]
    if (
        value.get("schema") != PROGRESS_SCHEMA
        or value.get("run_id") != receipt.run_id
        or value.get("custody_sha256") != _custody_sha256(receipt)
        or value.get("item_set_sha256") != _item_set_sha256(items)
        or value.get("eligible_item_count") != len(eligible)
    ):
        raise PipelineError("File Provider progress receipt does not match immutable custody")
    retained_values = value.get("retained_items")
    expected_retained = [
        {"item_hash": item_hash, "status": "retained", "reason": "non_evictable_metadata"} for item_hash in retained
    ]
    if retained_values != expected_retained:
        raise PipelineError("File Provider retained metadata accounting is invalid")
    completed_values = value.get("completed_items")
    if not isinstance(completed_values, list):
        raise PipelineError("File Provider completed progress is invalid")
    completed = [_hash_entry(entry, status=True) for entry in completed_values]
    completed_hashes = [entry["item_hash"] for entry in completed]
    if len(set(completed_hashes)) != len(completed_hashes) or not set(completed_hashes) <= set(eligible):
        raise PipelineError("File Provider completed progress is inconsistent")
    next_attempt = value.get("next_attempt")
    if isinstance(next_attempt, bool) or not isinstance(next_attempt, int) or next_attempt < 0:
        raise PipelineError("File Provider progress attempt counter is invalid")
    pending = value.get("pending_batch")
    if pending is not None:
        pending_expected = {"attempt_id", "authorization_principal", "manifest_hash", "item_hashes"}
        if not isinstance(pending, dict) or set(pending) != pending_expected:
            raise PipelineError("File Provider pending authorization is invalid")
        hashes = pending.get("item_hashes")
        principal = pending.get("authorization_principal")
        attempt_id = pending.get("attempt_id")
        manifest_hash = pending.get("manifest_hash")
        incomplete = [item_hash for item_hash in eligible if item_hash not in set(completed_hashes)]
        if (
            not isinstance(hashes, list)
            or hashes != incomplete[:MAX_BATCH_ITEMS]
            or not isinstance(principal, str)
            or not TOKEN.fullmatch(principal)
            or not isinstance(attempt_id, str)
            or not TOKEN.fullmatch(attempt_id)
            or not isinstance(manifest_hash, str)
            or not HEX64.fullmatch(manifest_hash)
        ):
            raise PipelineError("File Provider pending authorization does not match remaining items")
    receipts = value.get("receipts")
    if not isinstance(receipts, list):
        raise PipelineError("File Provider progress receipt ledger is invalid")
    for entry in receipts:
        if not isinstance(entry, dict) or set(entry) != {"attempt_id", "manifest_hash", "receipt_sha256", "status"}:
            raise PipelineError("File Provider progress receipt ledger is invalid")
        if (
            not isinstance(entry.get("attempt_id"), str)
            or not TOKEN.fullmatch(entry["attempt_id"])
            or not isinstance(entry.get("manifest_hash"), str)
            or not HEX64.fullmatch(entry["manifest_hash"])
            or not isinstance(entry.get("receipt_sha256"), str)
            or not HEX64.fullmatch(entry["receipt_sha256"])
            or entry.get("status") not in {"succeeded", "partial_failure", "failed"}
        ):
            raise PipelineError("File Provider progress receipt ledger is invalid")
    value["completed_items"] = completed
    return value


def _write_progress(path: Path, value: dict[str, Any]) -> None:
    _atomic_private_write(path, canonical_bytes(value) + b"\n")


def _manifest(
    batch: tuple[FileProviderItem, ...],
    *,
    attempt_id: str,
    principal: str,
    authorization: dict[str, str] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "attempt_id": attempt_id,
        "timeout_seconds": BATCH_TIMEOUT_SECONDS,
        "per_item_timeout_seconds": ITEM_TIMEOUT_SECONDS,
        "authorization_principal": principal,
        "items": [{"item_hash": item.item_hash, "url": item.url} for item in batch],
    }
    if authorization is not None:
        value["authorization"] = authorization
    return value


def _manifest_hash(value: dict[str, Any]) -> str:
    binding = {
        "schema": value["schema"],
        "attempt_id": value["attempt_id"],
        "timeout_seconds": value["timeout_seconds"],
        "per_item_timeout_seconds": value["per_item_timeout_seconds"],
        "authorization_principal": value["authorization_principal"],
        "item_hashes": [item["item_hash"] for item in value["items"]],
    }
    return hashlib.sha256(canonical_bytes(binding)).hexdigest()


def _discover_adapter(name: str = ADAPTER_NAME) -> Path:
    candidate = shutil.which(name)
    if not candidate:
        raise PipelineError("Domus File Provider adapter is absent from PATH")
    path = Path(candidate).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise PipelineError("Domus File Provider adapter is not executable")
    return path


def _run_adapter(
    executable: Path,
    manifest: dict[str, Any],
    *,
    plan: bool,
    campaign: bool = False,
) -> tuple[int, bytes]:
    if plan and campaign:
        raise PipelineError("Domus File Provider adapter mode is ambiguous")
    payload = canonical_bytes(manifest) + b"\n"
    arguments = [str(executable)]
    if plan:
        arguments.append("--plan")
    elif campaign:
        arguments.append("--plan-campaign")
    try:
        result = subprocess.run(
            arguments,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30 if plan or campaign else BATCH_TIMEOUT_SECONDS + 15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PipelineError("Domus File Provider adapter did not complete") from exc
    if not result.stdout or len(result.stdout) > MAX_ADAPTER_OUTPUT_BYTES:
        raise PipelineError("Domus File Provider adapter emitted an invalid response")
    return result.returncode, result.stdout


def _json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"{label} has an invalid shape")
    return value


def _valid_time(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_authorization(payload: bytes, manifest: dict[str, Any]) -> dict[str, Any]:
    value = _json_object(payload, label="File Provider authorization receipt")
    expected = {
        "schema",
        "action",
        "attempt_id",
        "authorized_by",
        "issued_at",
        "expires_at",
        "manifest_hash",
        "item_count",
        "item_hashes",
    }
    hashes = [item["item_hash"] for item in manifest["items"]]
    if (
        set(value) != expected
        or canonical_bytes(value) + b"\n" != payload
        or value.get("schema") != AUTHORIZATION_SCHEMA
        or value.get("action") != AUTHORIZATION_ACTION
        or value.get("attempt_id") != manifest["attempt_id"]
        or value.get("authorized_by") != manifest["authorization_principal"]
        or value.get("manifest_hash") != _manifest_hash(manifest)
        or value.get("item_count") != len(hashes)
        or value.get("item_hashes") != hashes
        or not _valid_time(value.get("issued_at"))
        or not _valid_time(value.get("expires_at"))
    ):
        raise PipelineError("File Provider authorization does not bind the exact pending batch")
    return value


def _campaign_item_set_sha256(item_hashes: list[str]) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "schema": CAMPAIGN_PLAN_SCHEMA,
                "item_hashes": item_hashes,
            }
        )
    ).hexdigest()


def _campaign_identity(receipt: MetabolismReceipt) -> str:
    identity = receipt.run_id
    if not TOKEN.fullmatch(identity) or len(identity) > 96:
        identity = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return identity


def _attempt_prefix(receipt: MetabolismReceipt) -> str:
    return f"limen-{_campaign_identity(receipt)}-"


def _campaign_plan(
    receipt: MetabolismReceipt,
    eligible_hashes: list[str],
    *,
    principal: str,
) -> dict[str, Any]:
    return {
        "schema": CAMPAIGN_PLAN_SCHEMA,
        "campaign_id": _campaign_identity(receipt),
        "attempt_prefix": _attempt_prefix(receipt),
        "authorization_principal": principal,
        "timeout_seconds": BATCH_TIMEOUT_SECONDS,
        "per_item_timeout_seconds": ITEM_TIMEOUT_SECONDS,
        "item_hashes": eligible_hashes,
    }


def _standing_authority_id(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "action": CAMPAIGN_AUTHORIZATION_ACTION,
                "attempt_prefix": value["attempt_prefix"],
                "authorized_by": value["authorized_by"],
                "issued_at": value["issued_at"],
                "item_set_sha256": value["item_set_sha256"],
                "item_hashes": value["item_hashes"],
                "max_batch_items": value["max_batch_items"],
                "max_batch_timeout_seconds": value["max_batch_timeout_seconds"],
                "max_item_timeout_seconds": value["max_item_timeout_seconds"],
            }
        )
    ).hexdigest()


def _migrate_campaign_authorization(value: dict[str, Any], source_bytes: bytes) -> dict[str, Any]:
    return {
        "schema": STANDING_AUTHORIZATION_SCHEMA,
        "action": CAMPAIGN_AUTHORIZATION_ACTION,
        "authority_id": _standing_authority_id(value),
        "attempt_prefix": value["attempt_prefix"],
        "authorized_by": value["authorized_by"],
        "issued_at": value["issued_at"],
        "item_set_sha256": value["item_set_sha256"],
        "item_count": value["item_count"],
        "item_hashes": value["item_hashes"],
        "max_batch_items": value["max_batch_items"],
        "max_batch_timeout_seconds": value["max_batch_timeout_seconds"],
        "max_item_timeout_seconds": value["max_item_timeout_seconds"],
        "signature_subject_b64": base64.b64encode(source_bytes).decode("ascii"),
        "revoked_at": None,
    }


def _validate_standing_authorization(
    payload: bytes,
    receipt: MetabolismReceipt,
    eligible_hashes: list[str],
) -> dict[str, Any]:
    original = _json_object(payload, label="File Provider standing authorization receipt")
    legacy_expected = {
        "schema",
        "action",
        "campaign_id",
        "attempt_prefix",
        "authorized_by",
        "issued_at",
        "expires_at",
        "item_set_sha256",
        "item_count",
        "item_hashes",
        "max_batch_items",
        "max_batch_timeout_seconds",
        "max_item_timeout_seconds",
        "max_attempts",
    }
    standing_expected = {
        "schema",
        "action",
        "authority_id",
        "attempt_prefix",
        "authorized_by",
        "issued_at",
        "item_set_sha256",
        "item_count",
        "item_hashes",
        "max_batch_items",
        "max_batch_timeout_seconds",
        "max_item_timeout_seconds",
        "signature_subject_b64",
        "revoked_at",
    }
    if original.get("schema") == CAMPAIGN_AUTHORIZATION_SCHEMA:
        value = original
        if (
            set(value) != legacy_expected
            or canonical_bytes(value) + b"\n" != payload
            or not _valid_time(value.get("expires_at"))
            or isinstance(value.get("max_attempts"), bool)
            or not isinstance(value.get("max_attempts"), int)
            or value["max_attempts"] < 1
        ):
            raise PipelineError("File Provider standing authorization migration source is invalid")
        normalized = _migrate_campaign_authorization(value, payload)
    else:
        value = original
        normalized = value
    if (
        not 1 <= len(eligible_hashes) <= MAX_CAMPAIGN_ITEMS
        or set(normalized) != standing_expected
        or (value is normalized and canonical_bytes(value) + b"\n" != payload)
    ):
        raise PipelineError("File Provider standing authorization is not canonical")
    if (
        normalized.get("schema") != STANDING_AUTHORIZATION_SCHEMA
        or normalized.get("action") != CAMPAIGN_AUTHORIZATION_ACTION
        or normalized.get("attempt_prefix") != _attempt_prefix(receipt)
        or not isinstance(normalized.get("authorized_by"), str)
        or not TOKEN.fullmatch(normalized["authorized_by"])
        or normalized.get("item_set_sha256") != _campaign_item_set_sha256(eligible_hashes)
        or normalized.get("item_count") != len(eligible_hashes)
        or normalized.get("item_hashes") != eligible_hashes
        or normalized.get("max_batch_items") != MAX_BATCH_ITEMS
        or normalized.get("max_batch_timeout_seconds") != BATCH_TIMEOUT_SECONDS
        or normalized.get("max_item_timeout_seconds") != ITEM_TIMEOUT_SECONDS
        or not _valid_time(normalized.get("issued_at"))
        or normalized.get("authority_id") != _standing_authority_id(normalized)
        or normalized.get("revoked_at") is not None
        or (
            normalized.get("signature_subject_b64") is not None
            and not isinstance(normalized.get("signature_subject_b64"), str)
        )
    ):
        raise PipelineError("File Provider standing authorization does not bind immutable custody")
    return normalized


def _validate_standing_batch(
    authorization: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    prefix = authorization["attempt_prefix"]
    attempt_id = manifest["attempt_id"]
    suffix = attempt_id[len(prefix) :] if attempt_id.startswith(prefix) else ""
    authorized_hashes = set(authorization["item_hashes"])
    batch_hashes = [item["item_hash"] for item in manifest["items"]]
    if (
        manifest["authorization_principal"] != authorization["authorized_by"]
        or len(suffix) != 6
        or not suffix.isdigit()
        or len(batch_hashes) > authorization["max_batch_items"]
        or not set(batch_hashes) <= authorized_hashes
        or manifest["timeout_seconds"] > authorization["max_batch_timeout_seconds"]
        or manifest["per_item_timeout_seconds"] > authorization["max_item_timeout_seconds"]
    ):
        raise PipelineError("File Provider batch exceeds the standing authority")


def _derived_capability(
    authorization: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    core = {
        "schema": DERIVED_CAPABILITY_SCHEMA,
        "authority_id": authorization["authority_id"],
        "action": AUTHORIZATION_ACTION,
        "attempt_id": manifest["attempt_id"],
        "manifest_hash": _manifest_hash(manifest),
    }
    return {
        **core,
        "capability_sha256": hashlib.sha256(
            canonical_bytes(
                {
                    **core,
                    "standing_authority_sha256": hashlib.sha256(canonical_bytes(authorization) + b"\n").hexdigest(),
                }
            )
        ).hexdigest(),
    }


def _read_authorization_inputs(
    receipt_path: Path,
    signature_path: Path,
) -> tuple[bytes, bytes]:
    receipt_bytes = _secure_read(
        receipt_path,
        limit=MAX_AUTHORIZATION_BYTES,
        label="File Provider authorization receipt",
    )
    signature = _secure_read(
        signature_path,
        limit=MAX_SIGNATURE_BYTES,
        label="File Provider authorization signature",
    )
    return receipt_bytes, signature


def _authorization_envelope(
    receipt_bytes: bytes,
    signature: bytes,
    capability: dict[str, Any] | None = None,
) -> tuple[dict[str, str], str]:
    envelope = {
        "receipt_b64": base64.b64encode(receipt_bytes).decode("ascii"),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    if capability is not None:
        envelope["capability_b64"] = base64.b64encode(canonical_bytes(capability) + b"\n").decode("ascii")
    return (
        envelope,
        hashlib.sha256(receipt_bytes).hexdigest(),
    )


def _error_shape(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"category", "domain", "code"}
        and isinstance(value.get("category"), str)
        and TOKEN.fullmatch(value["category"]) is not None
        and isinstance(value.get("domain"), str)
        and TOKEN.fullmatch(value["domain"]) is not None
        and not isinstance(value.get("code"), bool)
        and isinstance(value.get("code"), int)
    )


def _validate_receipt_item(value: object, expected_hash: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.get("item_hash") != expected_hash
        or value.get("status") not in ITEM_STATUSES
    ):
        raise PipelineError("Domus File Provider receipt contains an invalid item")
    allowed = {"item_hash", "status", "provider_item_hash", "domain_hash", "error"}
    if not set(value) <= allowed:
        raise PipelineError("Domus File Provider receipt contains an invalid item")
    status_value = value["status"]
    provider_hash = value.get("provider_item_hash")
    domain_hash = value.get("domain_hash")
    if provider_hash is not None and (not isinstance(provider_hash, str) or not HEX64.fullmatch(provider_hash)):
        raise PipelineError("Domus File Provider receipt contains an invalid provider identity")
    if domain_hash is not None and (not isinstance(domain_hash, str) or not HEX64.fullmatch(domain_hash)):
        raise PipelineError("Domus File Provider receipt contains an invalid domain identity")
    if status_value in SUCCESS_STATUSES:
        if set(value) != {"item_hash", "status", "provider_item_hash", "domain_hash"}:
            raise PipelineError("Domus File Provider receipt contains an invalid success item")
    elif (
        "error" not in value
        or not _error_shape(value["error"])
        or status_value == "retained"
        and (provider_hash is None or domain_hash is None)
    ):
        raise PipelineError("Domus File Provider receipt contains an invalid failure item")
    return dict(value)


def _validate_receipt(
    payload: bytes,
    returncode: int,
    manifest: dict[str, Any],
    authorization_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    value = _json_object(payload, label="Domus File Provider receipt")
    expected = {
        "schema",
        "attempt_id",
        "manifest_hash",
        "authorization_sha256",
        "authorized_by",
        "started_at",
        "completed_at",
        "status",
        "item_count",
        "result_counts",
        "items",
    }
    expected_hashes = [item["item_hash"] for item in manifest["items"]]
    raw_items = value.get("items")
    if (
        set(value) != expected
        or value.get("schema") != RECEIPT_SCHEMA
        or value.get("attempt_id") != manifest["attempt_id"]
        or value.get("manifest_hash") != _manifest_hash(manifest)
        or value.get("authorization_sha256") != authorization_sha256
        or value.get("authorized_by") != manifest["authorization_principal"]
        or not _valid_time(value.get("started_at"))
        or not _valid_time(value.get("completed_at"))
        or value.get("status") not in {"succeeded", "partial_failure", "failed"}
        or value.get("item_count") != len(expected_hashes)
        or not isinstance(raw_items, list)
        or len(raw_items) != len(expected_hashes)
        or returncode not in {0, 2}
        or (returncode == 0) != (value.get("status") == "succeeded")
    ):
        raise PipelineError("Domus File Provider receipt does not match the exact request")
    parsed_items = [
        _validate_receipt_item(item, item_hash) for item, item_hash in zip(raw_items, expected_hashes, strict=True)
    ]
    counts = value.get("result_counts")
    if not isinstance(counts, dict) or set(counts) != ITEM_STATUSES:
        raise PipelineError("Domus File Provider receipt counts are invalid")
    actual = {status: sum(item["status"] == status for item in parsed_items) for status in ITEM_STATUSES}
    if any(isinstance(counts.get(status), bool) or counts.get(status) != actual[status] for status in ITEM_STATUSES):
        raise PipelineError("Domus File Provider receipt counts are invalid")
    if value["status"] == "succeeded" and any(item["status"] not in SUCCESS_STATUSES for item in parsed_items):
        raise PipelineError("Domus File Provider receipt success state is inconsistent")
    successes = [
        {
            "item_hash": item["item_hash"],
            "status": item["status"],
            "provider_item_hash": item["provider_item_hash"],
            "domain_hash": item["domain_hash"],
        }
        for item in parsed_items
        if item["status"] in SUCCESS_STATUSES
    ]
    return value, successes


def _attempt_id(receipt: MetabolismReceipt, ordinal: int) -> str:
    return f"{_attempt_prefix(receipt)}{ordinal:06d}"


def _stage_pending_batch(
    progress: dict[str, Any],
    receipt: MetabolismReceipt,
    remaining: list[FileProviderItem],
    *,
    principal: str,
) -> tuple[FileProviderItem, ...]:
    ordinal = int(progress["next_attempt"])
    batch = tuple(remaining[:MAX_BATCH_ITEMS])
    verify_materialized_content(batch)
    attempt_id = _attempt_id(receipt, ordinal)
    manifest = _manifest(batch, attempt_id=attempt_id, principal=principal)
    progress["pending_batch"] = {
        "attempt_id": attempt_id,
        "authorization_principal": principal,
        "manifest_hash": _manifest_hash(manifest),
        "item_hashes": [item.item_hash for item in batch],
    }
    progress["next_attempt"] = ordinal + 1
    return batch


def _result_from_progress(
    progress: dict[str, Any],
    items: tuple[FileProviderItem, ...],
    *,
    authorization_prepared: bool = False,
) -> FileProviderResult:
    eligible = [item for item in items if not item.retained_metadata]
    retained = [item for item in items if item.retained_metadata]
    completed = {entry["item_hash"]: entry for entry in progress["completed_items"]}
    by_hash = {item.item_hash: item for item in eligible}
    rematerialized = [item_hash for item_hash in completed if by_hash[item_hash].materialized]
    if rematerialized:
        raise PipelineError("a previously reclaimed File Provider item became materialized again")
    remaining = [item for item in eligible if item.item_hash not in completed]
    return FileProviderResult(
        selected_files=len(eligible),
        evicted_files=sum(entry["status"] == "evicted" for entry in completed.values()),
        already_reclaimed_files=sum(entry["status"] == "already_dataless" for entry in completed.values()),
        retained_non_evictable_files=len(retained),
        retained_non_evictable_bytes=sum(item.allocated_bytes for item in retained),
        allocated_after=sum(item.allocated_bytes for item in eligible if item.materialized),
        remaining_files=len(remaining),
        complete=not remaining,
        authorization_prepared=authorization_prepared,
    )


def process_file_provider_items(
    receipt: MetabolismReceipt,
    root: Path,
    captured: tuple[CapturedFile, ...],
    progress_path: Path,
    *,
    prepare_authorization: Path | None = None,
    prepare_campaign_authorization: Path | None = None,
    authorization_principal: str | None = None,
    authorization_receipt: Path | None = None,
    authorization_signature: Path | None = None,
    adapter_name: str = ADAPTER_NAME,
    materialized_probe=is_materialized_cloud_path,
) -> FileProviderResult:
    """Prepare or execute a signed batch or revocation-only standing authority."""

    receipt.require_retirement_gate()
    items = inspect_captured_files(root, captured, materialized_probe=materialized_probe)
    verify_materialized_content(tuple(item for item in items if item.retained_metadata))
    progress = _load_progress(progress_path, receipt, items)
    current = _result_from_progress(progress, items)
    if current.complete:
        progress["pending_batch"] = None
        _write_progress(progress_path, progress)
        return current
    planning = prepare_authorization is not None
    campaign_planning = prepare_campaign_authorization is not None
    applying = authorization_receipt is not None or authorization_signature is not None
    if planning and campaign_planning:
        raise PipelineError("choose one File Provider authorization planning mode")
    if (planning or campaign_planning) and applying:
        raise PipelineError("File Provider authorization planning and apply are separate operations")
    if not planning and not campaign_planning and not applying:
        raise PipelineError("File Provider eviction requires a planned or signed authorization")
    if applying and (authorization_receipt is None or authorization_signature is None):
        raise PipelineError("File Provider eviction requires both authorization receipt and signature")
    executable = _discover_adapter(adapter_name)
    eligible = [item for item in items if not item.retained_metadata]
    completed_hashes = {entry["item_hash"] for entry in progress["completed_items"]}
    remaining = [item for item in eligible if item.item_hash not in completed_hashes]

    if planning or campaign_planning:
        authorization_path = prepare_authorization or prepare_campaign_authorization
        assert authorization_path is not None
        if not isinstance(authorization_principal, str) or not TOKEN.fullmatch(authorization_principal):
            raise PipelineError("File Provider authorization principal is missing or invalid")
        if authorization_path.expanduser().absolute() == progress_path.expanduser().absolute():
            raise PipelineError("File Provider authorization and progress paths must be distinct")
    if campaign_planning:
        assert prepare_campaign_authorization is not None
        assert isinstance(authorization_principal, str)
        verify_materialized_content(tuple(eligible))
        eligible_hashes = [item.item_hash for item in eligible]
        campaign_plan = _campaign_plan(
            receipt,
            eligible_hashes,
            principal=authorization_principal,
        )
        returncode, authorization_request = _run_adapter(
            executable,
            campaign_plan,
            plan=False,
            campaign=True,
        )
        if returncode != 0:
            raise PipelineError("Domus File Provider adapter rejected the campaign plan")
        _validate_standing_authorization(
            authorization_request,
            receipt,
            eligible_hashes,
        )
        pending = progress.get("pending_batch")
        if pending is None:
            _stage_pending_batch(
                progress,
                receipt,
                remaining,
                principal=authorization_principal,
            )
        else:
            pending_attempt = pending["attempt_id"]
            pending_suffix = (
                pending_attempt[len(_attempt_prefix(receipt)) :]
                if pending_attempt.startswith(_attempt_prefix(receipt))
                else ""
            )
            if (
                pending["authorization_principal"] != authorization_principal
                or len(pending_suffix) != 6
                or not pending_suffix.isdigit()
            ):
                raise PipelineError("File Provider pending batch does not fit the standing authority")
        _atomic_private_write(prepare_campaign_authorization, authorization_request)
        _write_progress(progress_path, progress)
        return _result_from_progress(progress, items, authorization_prepared=True)
    if planning:
        assert prepare_authorization is not None
        assert isinstance(authorization_principal, str)
        batch = tuple(remaining[:MAX_BATCH_ITEMS])
        verify_materialized_content(batch)
        attempt_id = _attempt_id(receipt, int(progress["next_attempt"]))
        manifest = _manifest(batch, attempt_id=attempt_id, principal=authorization_principal)
        returncode, authorization_request = _run_adapter(executable, manifest, plan=True)
        if returncode != 0:
            raise PipelineError("Domus File Provider adapter rejected the authorization plan")
        _validate_authorization(authorization_request, manifest)
        progress["pending_batch"] = {
            "attempt_id": attempt_id,
            "authorization_principal": authorization_principal,
            "manifest_hash": _manifest_hash(manifest),
            "item_hashes": [item.item_hash for item in batch],
        }
        progress["next_attempt"] = int(progress["next_attempt"]) + 1
        _atomic_private_write(prepare_authorization, authorization_request)
        _write_progress(progress_path, progress)
        return _result_from_progress(progress, items, authorization_prepared=True)

    assert authorization_receipt is not None and authorization_signature is not None
    authorization_bytes, signature_bytes = _read_authorization_inputs(
        authorization_receipt,
        authorization_signature,
    )
    authorization_value = _json_object(
        authorization_bytes,
        label="File Provider authorization receipt",
    )
    standing_authorization: dict[str, Any] | None = None
    if authorization_value.get("schema") in {
        CAMPAIGN_AUTHORIZATION_SCHEMA,
        STANDING_AUTHORIZATION_SCHEMA,
    }:
        standing_authorization = _validate_standing_authorization(
            authorization_bytes,
            receipt,
            [item.item_hash for item in eligible],
        )
    pending = progress.get("pending_batch")
    if not isinstance(pending, dict):
        if standing_authorization is None:
            raise PipelineError("File Provider eviction has no pending authorization plan")
        _stage_pending_batch(
            progress,
            receipt,
            remaining,
            principal=standing_authorization["authorized_by"],
        )
        _write_progress(progress_path, progress)
        pending = progress["pending_batch"]
        assert isinstance(pending, dict)
    item_by_hash = {item.item_hash: item for item in remaining}
    try:
        batch = tuple(item_by_hash[item_hash] for item_hash in pending["item_hashes"])
    except KeyError as exc:
        raise PipelineError("File Provider pending batch no longer matches remaining items") from exc
    verify_materialized_content(batch)
    manifest = _manifest(
        batch,
        attempt_id=pending["attempt_id"],
        principal=pending["authorization_principal"],
    )
    if _manifest_hash(manifest) != pending["manifest_hash"]:
        raise PipelineError("File Provider pending manifest hash changed")
    if standing_authorization is None:
        _validate_authorization(authorization_bytes, manifest)
        effective_authorization_bytes = authorization_bytes
        capability = None
    else:
        _validate_standing_batch(standing_authorization, manifest)
        effective_authorization_bytes = canonical_bytes(standing_authorization) + b"\n"
        capability = _derived_capability(standing_authorization, manifest)
    authorization_envelope, authorization_sha256 = _authorization_envelope(
        effective_authorization_bytes,
        signature_bytes,
        capability,
    )
    apply_manifest = _manifest(
        batch,
        attempt_id=pending["attempt_id"],
        principal=pending["authorization_principal"],
        authorization=authorization_envelope,
    )
    returncode, adapter_payload = _run_adapter(executable, apply_manifest, plan=False)
    adapter_receipt, successes = _validate_receipt(
        adapter_payload,
        returncode,
        apply_manifest,
        authorization_sha256,
    )
    postflight_items = inspect_captured_files(root, captured, materialized_probe=materialized_probe)
    postflight_by_hash = {item.item_hash: item for item in postflight_items}
    if any(postflight_by_hash[entry["item_hash"]].materialized for entry in successes):
        raise PipelineError("Domus File Provider receipt failed the local dataless postcondition")
    completed = {entry["item_hash"]: entry for entry in progress["completed_items"]}
    completed.update({entry["item_hash"]: entry for entry in successes})
    eligible_hashes = [item.item_hash for item in postflight_items if not item.retained_metadata]
    progress["completed_items"] = [completed[item_hash] for item_hash in eligible_hashes if item_hash in completed]
    progress["pending_batch"] = None
    progress["receipts"].append(
        {
            "attempt_id": adapter_receipt["attempt_id"],
            "manifest_hash": adapter_receipt["manifest_hash"],
            "receipt_sha256": hashlib.sha256(adapter_payload).hexdigest(),
            "status": adapter_receipt["status"],
        }
    )
    _write_progress(progress_path, progress)
    result = _result_from_progress(progress, postflight_items)
    if returncode != 0:
        raise PipelineError("Domus File Provider adapter reported a partial or failed batch")
    return result
