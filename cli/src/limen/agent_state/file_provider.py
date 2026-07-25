"""Private, resumable integration with the Domus File Provider adapter."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .atomize import canonical_bytes, sha256_file
from .models import MetabolismReceipt
from .pipeline import PipelineError
from .tree import NON_EVICTABLE_CLOUD_NAMES, RetentionPlan, is_materialized_cloud_path

MANIFEST_SCHEMA = "domus.file_provider_evict_manifest.v1"
RECEIPT_SCHEMA = "domus.file_provider_evict_receipt.v1"
AUTHORIZATION_SCHEMA = "domus.host_mutation_authorization.v2"
PROGRESS_SCHEMA = "limen.file_provider_evict_progress.v1"
AUTHORIZATION_ACTION = "file_provider_evict.apply"
ADAPTER_NAME = "domus-file-provider-evict"

MAX_BATCH_ITEMS = 1_000
BATCH_TIMEOUT_SECONDS = 15 * 60
ITEM_TIMEOUT_SECONDS = 60
MAX_ADAPTER_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_AUTHORIZATION_BYTES = 64 * 1024
MAX_SIGNATURE_BYTES = 32 * 1024
MAX_PROGRESS_BYTES = 64 * 1024 * 1024

HEX64 = re.compile(r"^[0-9a-f]{64}$")
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


def progress_path_for(private_receipt: Path) -> Path:
    return private_receipt.with_name(f"{private_receipt.stem}.file-provider-progress.json")


def collect_file_entry(records: list[dict[str, Any]], record: dict[str, Any]) -> None:
    if record.get("kind") == "file_entry":
        records.append(record)


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


def verify_materialized_content(items: tuple[FileProviderItem, ...]) -> None:
    for item in items:
        if not item.materialized:
            continue
        try:
            digest = sha256_file(item.path)
        except OSError as exc:
            raise PipelineError("captured File Provider item content is unreadable") from exc
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


def _run_adapter(executable: Path, manifest: dict[str, Any], *, plan: bool) -> tuple[int, bytes]:
    payload = canonical_bytes(manifest) + b"\n"
    arguments = [str(executable)]
    if plan:
        arguments.append("--plan")
    try:
        result = subprocess.run(
            arguments,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30 if plan else BATCH_TIMEOUT_SECONDS + 15,
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


def _authorization_envelope(
    receipt_path: Path,
    signature_path: Path,
    manifest: dict[str, Any],
) -> tuple[dict[str, str], str]:
    receipt_bytes = _secure_read(
        receipt_path,
        limit=MAX_AUTHORIZATION_BYTES,
        label="File Provider authorization receipt",
    )
    _validate_authorization(receipt_bytes, manifest)
    signature = _secure_read(
        signature_path,
        limit=MAX_SIGNATURE_BYTES,
        label="File Provider authorization signature",
    )
    return (
        {
            "receipt_b64": base64.b64encode(receipt_bytes).decode("ascii"),
            "signature_b64": base64.b64encode(signature).decode("ascii"),
        },
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
    parsed_items = [_validate_receipt_item(item, item_hash) for item, item_hash in zip(raw_items, expected_hashes)]
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
    identity = receipt.run_id
    if not TOKEN.fullmatch(identity) or len(identity) > 96:
        identity = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"limen-{identity}-{ordinal:06d}"


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
    authorization_principal: str | None = None,
    authorization_receipt: Path | None = None,
    authorization_signature: Path | None = None,
    adapter_name: str = ADAPTER_NAME,
    materialized_probe=is_materialized_cloud_path,
) -> FileProviderResult:
    """Prepare or execute one signed, finite File Provider batch."""

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
    applying = authorization_receipt is not None or authorization_signature is not None
    if planning and applying:
        raise PipelineError("File Provider authorization planning and apply are separate operations")
    if not planning and not applying:
        raise PipelineError("File Provider eviction requires a planned or signed authorization")
    if applying and (authorization_receipt is None or authorization_signature is None):
        raise PipelineError("File Provider eviction requires both authorization receipt and signature")
    executable = _discover_adapter(adapter_name)
    eligible = [item for item in items if not item.retained_metadata]
    completed_hashes = {entry["item_hash"] for entry in progress["completed_items"]}
    remaining = [item for item in eligible if item.item_hash not in completed_hashes]

    if planning:
        assert prepare_authorization is not None
        if not isinstance(authorization_principal, str) or not TOKEN.fullmatch(authorization_principal):
            raise PipelineError("File Provider authorization principal is missing or invalid")
        if prepare_authorization.expanduser().absolute() == progress_path.expanduser().absolute():
            raise PipelineError("File Provider authorization and progress paths must be distinct")
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

    pending = progress.get("pending_batch")
    if not isinstance(pending, dict):
        raise PipelineError("File Provider eviction has no pending authorization plan")
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
    assert authorization_receipt is not None and authorization_signature is not None
    authorization_envelope, authorization_sha256 = _authorization_envelope(
        authorization_receipt,
        authorization_signature,
        manifest,
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
