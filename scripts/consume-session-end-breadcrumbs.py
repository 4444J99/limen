#!/usr/bin/env python3
"""Idempotently drain constant-time SessionEnd breadcrumbs on heartbeat.

Each real SessionEnd occurrence owns one bounded receipt. Global and project
deliveries converge on that occurrence, while a later resumed end gets fresh
consumer state. Slow consumers have finite timeouts, at most three attempts,
output digests instead of logs, and a partitioned on-disk active queue so
terminal receipts are never rescanned on every heartbeat.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import fcntl
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

BREADCRUMB_SCHEMA = "limen.session_end_breadcrumb.v1"
CURSOR_SCHEMA = "limen.session_end_cursor.v1"
RECEIPT_SCHEMA = "limen.session_end_consumer_receipt.v1"
ACTIVE_INDEX_SCHEMA = "limen.session_end_active_index.v1"
MODEL_WARNING_SCHEMA = "limen.model_tier_audit_warning.v1"
APPEND_TRANSACTION_SCHEMA = "limen.append_once_transaction.v1"
PAIR_STATE_SCHEMA = "limen.session_end_pair_state.v1"
ACTIVE_INDEX_NAME = ".active-index-v1"
LOCK_NAME = ".drain.lock"
ACTIVE_RECEIPT_DIR = "active"
TERMINAL_RECEIPT_DIR = "terminal"
PAIR_STATE_DIR = "pairs"
MAX_BATCH_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 4096
MAX_MODEL_EVIDENCE_BYTES = 64 * 1024
MAX_ATTEMPTS = 3
MAX_MIGRATION_RECEIPTS = 128
PAIR_WINDOW_SECONDS = 30.0
TERMINAL_STATUSES = {"complete", "failed", "not_applicable"}
ISOLATION_MARKERS = (
    "/.claude/worktrees/",
    "/.worktrees/",
    "/.limen-worktrees/",
    "/limen-worktrees/",
)


@dataclass(frozen=True)
class CommandResult:
    """Bounded subprocess outcome retained without unbounded command output."""

    exit_code: int
    output: bytes
    duration_ms: int
    timed_out: bool = False
    evidence_tail: bytes = b""
    output_total_bytes: int = 0


@dataclass(frozen=True)
class ConsumerSpec:
    """One independently retried slow consumer and its bounded environment."""

    name: str
    timeout_seconds: int
    command: Callable[[Path, Mapping[str, Any]], Sequence[str]]
    environment: Mapping[str, str] | None = None


Runner = Callable[[Sequence[str], int, Path, Mapping[str, str] | None], CommandResult]


def default_source(environ: Mapping[str, str] | None = None) -> Path:
    """Return the version-independent queue shared by global and project hooks."""

    environ = os.environ if environ is None else environ
    configured = environ.get("LIMEN_SESSION_END_BREADCRUMBS")
    if configured:
        return Path(configured).expanduser()
    state_home = environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home).expanduser() / "limen" / "session-end-breadcrumbs.jsonl"
    home = Path(environ.get("HOME") or Path.home()).expanduser()
    return home / ".local" / "state" / "limen" / "session-end-breadcrumbs.jsonl"


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    """Encode a mapping as deterministic, newline-terminated JSON."""

    return (json.dumps(dict(payload), indent=2, sort_keys=True) + "\n").encode()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> bool:
    """Atomically write stable JSON, preserving inode and mtime when bytes match."""

    encoded = _json_bytes(payload)
    try:
        if path.read_bytes() == encoded:
            return False
    except OSError:
        pass
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        temp.replace(path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass
    return True


def _load_json(path: Path, default: Mapping[str, Any]) -> dict[str, Any]:
    """Load a JSON object, returning a defensive default on any invalid input."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return value if isinstance(value, dict) else dict(default)


def _load_json_strict(path: Path) -> tuple[bool, dict[str, Any]]:
    """Distinguish an absent JSON object from a corrupt one."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return True, {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False, {}
    return (True, value) if isinstance(value, dict) else (False, {})


def _finite_float(value: object, default: float = 0.0) -> float:
    """Coerce a finite float or return the supplied default."""

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _nonnegative_int(value: object, default: int = 0) -> int:
    """Coerce a nonnegative integer or return the supplied default."""

    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number >= 0 else default


def _session_key(session_id: str) -> str:
    """Return the redacted stable key for one provider session."""

    return hashlib.sha256(session_id.encode()).hexdigest()


def _occurrence_key(event: Mapping[str, Any]) -> str:
    """Return the stable key for one exact SessionEnd occurrence."""

    identity = event.get("occurrence_id") or event.get("event_id", "")
    material = f"{event.get('session_id', '')}\0{identity}"
    return hashlib.sha256(material.encode()).hexdigest()


def _malformed_event(line: bytes) -> dict[str, Any]:
    """Convert an invalid queue line into a redacted terminal event."""

    digest = hashlib.sha256(line).hexdigest()
    return {
        "schema": BREADCRUMB_SCHEMA,
        "event_id": digest,
        "delivery_id": digest,
        "occurrence_basis": "exact",
        "provider": "unknown",
        "session_id": f"invalid-{digest[:24]}",
        "source": "malformed-line",
        "ended_epoch": 0.0,
        "cwd": "",
        "payload_valid": False,
        "payload_sha256": digest,
    }


def _normalized_event(line: bytes) -> dict[str, Any]:
    """Validate and bound one raw breadcrumb queue line."""

    try:
        event = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _malformed_event(line)
    valid = bool(
        isinstance(event, dict)
        and event.get("schema") == BREADCRUMB_SCHEMA
        and isinstance(event.get("session_id"), str)
        and event.get("session_id")
        and isinstance(event.get("event_id"), str)
        and event.get("event_id")
    )
    if not valid:
        return _malformed_event(line)
    try:
        ended_epoch = float(event.get("ended_epoch", 0))
    except (TypeError, ValueError, OverflowError):
        return _malformed_event(line)
    if not math.isfinite(ended_epoch) or ended_epoch < 0:
        return _malformed_event(line)
    digest = hashlib.sha256(line).hexdigest()
    return {
        "schema": BREADCRUMB_SCHEMA,
        "event_id": str(event["event_id"])[:128],
        "delivery_id": str(event.get("delivery_id") or event["event_id"])[:128],
        "occurrence_basis": (
            str(event.get("occurrence_basis"))
            if event.get("occurrence_basis") in {"transcript", "fallback"}
            else "exact"
        ),
        "provider": str(event.get("provider") or "unknown")[:32],
        "session_id": str(event["session_id"])[:256],
        "source": str(event.get("source") or "unknown")[:32],
        "ended_epoch": ended_epoch,
        "cwd": str(event.get("cwd") or "")[:4096],
        "payload_valid": event.get("payload_valid") is True,
        "payload_sha256": str(event.get("payload_sha256") or digest)[:64],
    }


def _is_isolation_worktree(cwd: object) -> bool:
    """Return whether a cwd belongs to a sanctioned isolation-root shape."""

    normalized = str(cwd or "").replace("\\", "/")
    return any(marker in normalized for marker in ISOLATION_MARKERS)


def _initial_consumer_state(payload_valid: bool, cwd: object) -> dict[str, dict[str, Any]]:
    """Build initial consumer states for one normalized occurrence."""

    names = ["compatibility_closeout", *(spec.name for spec in default_consumer_specs())]
    if not payload_valid:
        return {name: {"status": "not_applicable", "attempts": 0} for name in names}
    states = {name: {"status": "pending", "attempts": 0} for name in names}
    if not _is_isolation_worktree(cwd):
        states["compatibility_closeout"] = {"status": "not_applicable", "attempts": 0}
    return states


def _receipt_for(event: Mapping[str, Any], existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Create or safely upgrade the receipt for an exact occurrence."""

    if existing and existing.get("schema") == RECEIPT_SCHEMA:
        receipt = dict(existing)
        sources = {str(value) for value in receipt.get("sources") or []}
        sources.add(str(event["source"]))
        receipt["sources"] = sorted(sources)
        event_ids = {str(value) for value in receipt.get("event_ids") or []}
        if receipt.get("event_id"):
            event_ids.add(str(receipt["event_id"]))
        event_ids.add(str(event["event_id"]))
        receipt["event_ids"] = sorted(event_ids)
        delivery_ids = {str(value) for value in receipt.get("delivery_ids") or []}
        delivery_ids.add(str(event.get("delivery_id") or event["event_id"]))
        receipt["delivery_ids"] = sorted(delivery_ids)
        receipt["last_seen_epoch"] = max(
            _finite_float(receipt.get("last_seen_epoch")),
            _finite_float(event.get("ended_epoch")),
        )
        if event.get("payload_valid") is True and receipt.get("payload_valid") is not True:
            receipt.update(
                {
                    "event_id": event["event_id"],
                    "provider": event["provider"],
                    "first_seen_epoch": _finite_float(event.get("ended_epoch")),
                    "cwd": event.get("cwd") or "",
                    "payload_valid": True,
                    "payload_sha256": event.get("payload_sha256"),
                    "consumers": _initial_consumer_state(True, event.get("cwd")),
                }
            )
        return receipt
    event_id = str(event["event_id"])
    delivery_id = str(event.get("delivery_id") or event_id)
    return {
        "schema": RECEIPT_SCHEMA,
        "event_id": event_id,
        "event_ids": [event_id],
        "delivery_ids": [delivery_id],
        "occurrence_id": str(event.get("occurrence_id") or event_id),
        "occurrence_basis": str(event.get("occurrence_basis") or "exact"),
        "session_id": event["session_id"],
        "session_key": _session_key(str(event["session_id"])),
        "provider": event["provider"],
        "sources": [event["source"]],
        "first_seen_epoch": _finite_float(event.get("ended_epoch")),
        "last_seen_epoch": _finite_float(event.get("ended_epoch")),
        "cwd": event.get("cwd") or "",
        "payload_valid": event.get("payload_valid") is True,
        "payload_sha256": event.get("payload_sha256"),
        "consumers": _initial_consumer_state(event.get("payload_valid") is True, event.get("cwd")),
    }


def _receipt_active(receipt: Mapping[str, Any]) -> bool:
    """Return whether any consumer still owns runnable work."""

    consumers = receipt.get("consumers") or {}
    return any(state.get("status") in {"pending", "retry"} for state in consumers.values() if isinstance(state, dict))


def _safe_receipt_name(value: object) -> str | None:
    """Accept only a plain JSON basename suitable for the receipt root."""

    name = str(value or "")
    if not name.endswith(".json") or name != Path(name).name or name.startswith("."):
        return None
    return name


def _receipt_name(event: Mapping[str, Any]) -> str:
    """Derive the deterministic filename for an exact occurrence."""

    return f"{_session_key(str(event['session_id']))[:16]}-{_occurrence_key(event)[:32]}.json"


def _pair_state_path(receipt_root: Path, event: Mapping[str, Any]) -> Path:
    """Return the O(1) fallback-pair state path for one payload identity."""

    event_key = hashlib.sha256(str(event.get("event_id") or "").encode()).hexdigest()[:32]
    return receipt_root / PAIR_STATE_DIR / f"{_session_key(str(event['session_id']))[:16]}-{event_key}.json"


def _select_receipt_path(event: dict[str, Any], receipt_root: Path) -> Path | None:
    """Select an exact receipt, pairing only opposite-source fallback deliveries."""

    if event.get("occurrence_basis") != "fallback":
        event["occurrence_id"] = event["event_id"]
        return _find_exact_receipt(receipt_root, _receipt_name(event))

    state_valid, state = _load_json_strict(_pair_state_path(receipt_root, event))
    if state_valid and state.get("schema") == PAIR_STATE_SCHEMA:
        source = str(event.get("source") or "unknown")
        sources = {str(value) for value in state.get("sources") or []}
        last_seen = _finite_float(state.get("last_seen_epoch"), -PAIR_WINDOW_SECONDS - 1)
        name = _safe_receipt_name(state.get("receipt"))
        if (
            name
            and source not in sources
            and abs(_finite_float(event.get("ended_epoch")) - last_seen) <= PAIR_WINDOW_SECONDS
        ):
            path = _find_exact_receipt(receipt_root, name)
            receipt = _load_json(path, {}) if path else {}
            if (
                receipt.get("schema") == RECEIPT_SCHEMA
                and receipt.get("event_id") == event.get("event_id")
                and source not in {str(value) for value in receipt.get("sources") or []}
            ):
                event["occurrence_id"] = str(receipt.get("occurrence_id") or receipt["event_id"])
                return path

    event["occurrence_id"] = str(event.get("delivery_id") or event["event_id"])
    return _find_exact_receipt(receipt_root, _receipt_name(event))


def _write_pair_state(
    receipt_root: Path,
    event: Mapping[str, Any],
    receipt_path: Path,
    receipt: Mapping[str, Any],
) -> None:
    """Point the fallback payload identity at its latest occurrence receipt."""

    if event.get("occurrence_basis") != "fallback":
        return
    _atomic_json(
        _pair_state_path(receipt_root, event),
        {
            "schema": PAIR_STATE_SCHEMA,
            "receipt": receipt_path.name,
            "sources": sorted(str(value) for value in receipt.get("sources") or []),
            "last_seen_epoch": _finite_float(receipt.get("last_seen_epoch")),
        },
    )


def _receipt_destination(receipt_root: Path, name: str, receipt: Mapping[str, Any]) -> Path:
    """Choose the active or terminal partition for a receipt."""

    directory = ACTIVE_RECEIPT_DIR if _receipt_active(receipt) else TERMINAL_RECEIPT_DIR
    return receipt_root / directory / name


def _find_exact_receipt(receipt_root: Path, name: str) -> Path | None:
    """Find one exact occurrence without proximity- or source-based conflation."""

    for path in (
        receipt_root / ACTIVE_RECEIPT_DIR / name,
        receipt_root / TERMINAL_RECEIPT_DIR / name,
        receipt_root / name,
    ):
        if path.is_file():
            return path
    return None


def _place_receipt(path: Path, receipt_root: Path, receipt: Mapping[str, Any]) -> Path:
    """Atomically place a receipt in the active queue or terminal history."""

    target = _receipt_destination(receipt_root, path.name, receipt)
    if path == target:
        return path
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.exists():
        if path.read_bytes() != target.read_bytes():
            raise RuntimeError(f"conflicting session-end receipt destinations for {path.name}")
        path.unlink()
        return target
    path.replace(target)
    return target


def _legacy_receipt_batch(receipt_root: Path, limit: int) -> tuple[list[Path], bool]:
    """Select at most one bounded migration batch from the legacy flat directory."""

    selected: list[Path] = []
    try:
        with os.scandir(receipt_root) as entries:
            for entry in entries:
                if not entry.is_file(follow_symlinks=False) or not _safe_receipt_name(entry.name):
                    continue
                selected.append(receipt_root / entry.name)
                if len(selected) > limit:
                    break
    except FileNotFoundError:
        return [], False
    return selected[:limit], len(selected) > limit


def _write_layout_state(receipt_root: Path, *, migration_pending: bool) -> None:
    """Persist the partition layout and legacy-migration state."""

    _atomic_json(
        receipt_root / ACTIVE_INDEX_NAME,
        {
            "schema": ACTIVE_INDEX_SCHEMA,
            "layout": "partitioned-active-terminal-v1",
            "migration_pending": migration_pending,
        },
    )


def _migrate_legacy_receipts(
    receipt_root: Path,
    *,
    limit: int = MAX_MIGRATION_RECEIPTS,
) -> tuple[list[Path], bool]:
    """Move a finite legacy batch so recovery advances without rescanning history."""

    paths, pending = _legacy_receipt_batch(receipt_root, max(1, limit))
    active: list[Path] = []
    for path in paths:
        receipt = _load_json(path, {})
        placed = _place_receipt(path, receipt_root, receipt)
        if _receipt_active(receipt):
            active.append(placed)
    _write_layout_state(receipt_root, migration_pending=pending)
    return active, pending


def _bounded_active_paths(receipt_root: Path, limit: int | None) -> list[Path]:
    """Read a bounded prefix, or the full active queue for explicit integrity checks."""

    paths: list[Path] = []
    directory = receipt_root / ACTIVE_RECEIPT_DIR
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_file(follow_symlinks=False) and _safe_receipt_name(entry.name):
                    paths.append(directory / entry.name)
                    if limit is not None and len(paths) >= max(1, limit):
                        break
    except FileNotFoundError:
        pass
    return paths


def ingest(
    source: Path,
    *,
    cursor_path: Path,
    receipt_root: Path,
    max_bytes: int = MAX_BATCH_BYTES,
) -> tuple[list[Path], int]:
    """Ingest one bounded queue suffix into exact active or terminal receipts."""

    cursor = _load_json(cursor_path, {"schema": CURSOR_SCHEMA, "offset": 0, "device": None, "inode": None})
    try:
        stat_result = source.stat()
    except OSError:
        return [], 0
    offset = _nonnegative_int(cursor.get("offset"), 0)
    cursor_device = cursor.get("device")
    cursor_inode = cursor.get("inode")
    if cursor_device is not None and not isinstance(cursor_device, int):
        cursor_device = None
        offset = 0
    if cursor_inode is not None and not isinstance(cursor_inode, int):
        cursor_inode = None
        offset = 0
    if (
        offset < 0
        or offset > stat_result.st_size
        or cursor_device not in {None, stat_result.st_dev}
        or cursor_inode not in {None, stat_result.st_ino}
    ):
        offset = 0
    with source.open("rb") as handle:
        handle.seek(offset)
        chunk = handle.read(max(1, min(max_bytes, MAX_BATCH_BYTES)))
    complete = chunk.rfind(b"\n") + 1
    if complete <= 0:
        return [], 0
    receipt_names: list[str] = []
    for line in chunk[:complete].splitlines():
        if not line:
            continue
        event = _normalized_event(line)
        receipt_path = _select_receipt_path(event, receipt_root)
        if receipt_path is None:
            receipt_path = receipt_root / ACTIVE_RECEIPT_DIR / _receipt_name(event)
        existing = _load_json(receipt_path, {}) if receipt_path.exists() else None
        receipt = _receipt_for(event, existing)
        _atomic_json(receipt_path, receipt)
        receipt_path = _place_receipt(receipt_path, receipt_root, receipt)
        _write_pair_state(receipt_root, event, receipt_path, receipt)
        receipt_names.append(receipt_path.name)
    _atomic_json(
        cursor_path,
        {
            "schema": CURSOR_SCHEMA,
            "offset": offset + complete,
            "device": stat_result.st_dev,
            "inode": stat_result.st_ino,
        },
    )
    paths = [path for name in dict.fromkeys(receipt_names) if (path := _find_exact_receipt(receipt_root, name))]
    return paths, len(receipt_names)


def default_consumer_specs() -> tuple[ConsumerSpec, ...]:
    """Return the bounded slow-consumer registry for one occurrence."""

    debt_timeout = _nonnegative_int(os.environ.get("LIMEN_SESSION_WORKTREE_DEBT_TIMEOUT"), 30)
    if debt_timeout <= 0:
        debt_timeout = 30
    return (
        ConsumerSpec(
            "handoff",
            20,
            lambda root, _event: (sys.executable, str(root / "scripts" / "handoff-relay.py")),
        ),
        ConsumerSpec(
            "orphan_watchers",
            10,
            lambda root, event: (
                sys.executable,
                str(root / "scripts" / "orphan-watchers.py"),
                "--session-end",
                "--sid",
                str(event["session_id"]),
            ),
        ),
        ConsumerSpec(
            "claim_capture",
            15,
            lambda root, event: (
                sys.executable,
                str(root / "scripts" / "capture-session-claim.py"),
                "--sid",
                str(event["session_id"]),
            ),
        ),
        ConsumerSpec(
            "model_audit",
            30,
            lambda root, event: (
                sys.executable,
                str(root / "scripts" / "claude-workflow-guard.py"),
                "audit-transcript",
                str(event["session_id"]),
                "--max-billable-tokens",
                "999999999",
                "--max-opus-billable-tokens",
                "999999999",
                "--max-agent-calls",
                "999999",
                "--max-opus-agents",
                "1",
            ),
        ),
        ConsumerSpec(
            "lifecycle_pressure",
            60,
            lambda root, _event: (
                sys.executable,
                str(root / "scripts" / "session-lifecycle-pressure.py"),
                "--write",
            ),
            {"LIMEN_WORKTREE_DEBT_TIMEOUT": str(debt_timeout)},
        ),
    )


@contextlib.contextmanager
def _consumer_lock(receipt_root: Path) -> Iterator[bool]:
    """Hold the one nonblocking cross-entrypoint drain lock for this receipt root."""

    try:
        receipt_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = receipt_root / LOCK_NAME
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.fchmod(descriptor, 0o600)
    except OSError:
        yield False
        return
    acquired = False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
        yield acquired
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def run_bounded(
    command: Sequence[str],
    timeout_seconds: int,
    cwd: Path,
    extra_env: Mapping[str, str] | None = None,
) -> CommandResult:
    """Run one consumer in a process group and convert spawn/time failures to finite results."""

    started = time.monotonic()
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(
                list(command),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={**os.environ, "LIMEN_ROOT": str(cwd), **dict(extra_env or {})},
            )
        except OSError as exc:
            duration_ms = round((time.monotonic() - started) * 1000)
            return CommandResult(
                exit_code=127,
                output=f"spawn-oserror:{exc.errno or 'unknown'}".encode(),
                duration_ms=duration_ms,
            )
        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                exit_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                exit_code = process.wait()
        output.seek(0, os.SEEK_END)
        output_total_bytes = output.tell()
        output.seek(0)
        captured = output.read(MAX_OUTPUT_BYTES)
        output.seek(max(0, output_total_bytes - MAX_MODEL_EVIDENCE_BYTES))
        evidence_tail = output.read(MAX_MODEL_EVIDENCE_BYTES)
    duration_ms = round((time.monotonic() - started) * 1000)
    return CommandResult(
        exit_code=124 if timed_out else exit_code,
        output=captured[:MAX_OUTPUT_BYTES],
        duration_ms=duration_ms,
        timed_out=timed_out,
        evidence_tail=evidence_tail,
        output_total_bytes=output_total_bytes,
    )


def _write_all(descriptor: int, payload: bytes) -> bool:
    """Write every payload byte to an open descriptor."""

    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            return False
        view = view[written:]
    return True


def _commit_append_marker(marker_path: Path, state: Mapping[str, Any]) -> bool:
    """Commit and verify an append-once transaction marker."""

    committed = {**dict(state), "status": "committed"}
    _atomic_json(marker_path, committed)
    valid, observed = _load_json_strict(marker_path)
    return valid and observed == committed


def _append_state_bytes(state: Mapping[str, Any]) -> tuple[int, bytes] | None:
    """Validate an append transaction and return its offset and encoded line."""

    stored_text = state.get("line")
    offset = state.get("offset")
    if (
        state.get("schema") != APPEND_TRANSACTION_SCHEMA
        or not isinstance(stored_text, str)
        or not isinstance(offset, int)
        or offset < 0
    ):
        return None
    stored = stored_text.encode()
    if state.get("line_sha256") != hashlib.sha256(stored).hexdigest():
        return None
    return offset, stored


def _finish_prepared_append(descriptor: int, marker_path: Path, state: Mapping[str, Any]) -> bool:
    """Finish one prepared append only when the ledger tail is still attributable."""

    parsed = _append_state_bytes(state)
    if parsed is None:
        return False
    offset, stored = parsed
    observed = os.pread(descriptor, len(stored), offset)
    if observed != stored:
        size = os.fstat(descriptor).st_size
        if size != offset + len(observed) or not stored.startswith(observed):
            return False
        if not _write_all(descriptor, stored[len(observed) :]):
            return False
        os.fsync(descriptor)
    return _commit_append_marker(marker_path, state)


def _append_json_line_once(
    path: Path,
    payload: Mapping[str, Any],
    *,
    marker_path: Path,
    identity: str,
) -> bool:
    """Append once with one ledger-global prepared transaction under flock."""

    encoded = (json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        marker_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        flags = os.O_APPEND | os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            pending_path = marker_path.parent / ".pending"
            pending_valid, pending = _load_json_strict(pending_path)
            if not pending_valid:
                return False
            if pending:
                pending_marker_name = _safe_receipt_name(pending.get("marker"))
                if not pending_marker_name:
                    return False
                pending_marker = marker_path.parent / pending_marker_name
                if not _finish_prepared_append(descriptor, pending_marker, pending):
                    return False
                _atomic_json(pending_path, {})

            valid, state = _load_json_strict(marker_path)
            if not valid:
                return False
            if state:
                if state.get("schema") != APPEND_TRANSACTION_SCHEMA or state.get("identity") != identity:
                    return False
                parsed = _append_state_bytes(state)
                if parsed is None:
                    return False
                offset, stored = parsed
                observed = os.pread(descriptor, len(stored), offset)
                if state.get("status") == "committed":
                    return observed == stored
                if state.get("status") != "prepared":
                    return False
                return _finish_prepared_append(descriptor, marker_path, state)

            prepared = {
                "schema": APPEND_TRANSACTION_SCHEMA,
                "identity": identity,
                "status": "prepared",
                "offset": os.fstat(descriptor).st_size,
                "line_sha256": hashlib.sha256(encoded).hexdigest(),
                "line": encoded.decode("utf-8"),
                "marker": marker_path.name,
            }
            _atomic_json(marker_path, prepared)
            marker_valid, observed_marker = _load_json_strict(marker_path)
            if not marker_valid or observed_marker != prepared:
                return False
            _atomic_json(pending_path, prepared)
            pending_valid, observed_pending = _load_json_strict(pending_path)
            if not pending_valid or observed_pending != prepared:
                return False
            if not _write_all(descriptor, encoded):
                return False
            os.fsync(descriptor)
            if not _commit_append_marker(marker_path, prepared):
                return False
            _atomic_json(pending_path, {})
            return True
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
    except OSError:
        return False


def _append_compatibility(root: Path, receipt: Mapping[str, Any]) -> CommandResult:
    """Append the legacy worktree closeout record exactly once."""

    started = time.monotonic()
    if not _is_isolation_worktree(receipt.get("cwd")):
        return CommandResult(0, b"not-applicable", round((time.monotonic() - started) * 1000))
    record = {
        "ts": int(_finite_float(receipt.get("last_seen_epoch"))),
        "sid": receipt["session_id"],
        "cwd": receipt.get("cwd") or "",
        "branch": "unknown",
        "event_id": str(receipt.get("event_id") or ""),
    }
    path = root / "logs" / "session-closeout.jsonl"
    occurrence = _occurrence_key(receipt)
    marker = root / "logs" / "session-closeout-events" / f"{occurrence}.json"
    exit_code = 0 if _append_json_line_once(path, record, marker_path=marker, identity=occurrence) else 1
    return CommandResult(exit_code, b"", round((time.monotonic() - started) * 1000))


def _model_report(result: CommandResult) -> dict[str, Any]:
    """Recover a bounded model report, including violations beyond the 4 KiB digest prefix."""

    candidates = [result.evidence_tail, result.output]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            report = json.loads(candidate.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        if isinstance(report, dict):
            return report
    tail = (result.evidence_tail or result.output).decode("utf-8", errors="replace")
    marker = '"violations"'
    marker_at = tail.rfind(marker)
    if marker_at >= 0:
        colon = tail.find(":", marker_at + len(marker))
        if colon >= 0:
            try:
                violations, _ = json.JSONDecoder().raw_decode(tail[colon + 1 :].lstrip())
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(violations, list):
                    return {"violations": violations}
    return {}


def _model_warning_payload(receipt: Mapping[str, Any], result: CommandResult) -> dict[str, Any]:
    """Build bounded durable evidence for a model-audit policy warning."""

    report = _model_report(result)
    violations = report.get("violations") if isinstance(report, dict) else []
    if not isinstance(violations, list):
        violations = []
    payload: dict[str, Any] = {
        "schema": MODEL_WARNING_SCHEMA,
        "event_id": str(receipt.get("event_id") or ""),
        "occurrence_id": _occurrence_key(receipt),
        "session_id": str(receipt.get("session_id") or ""),
        "ended_epoch": _finite_float(receipt.get("last_seen_epoch")),
        "violations": [str(value)[:1024] for value in violations[:20]],
        "output_sha256": hashlib.sha256(result.output).hexdigest(),
        "evidence_tail_sha256": hashlib.sha256(result.evidence_tail).hexdigest(),
        "output_total_bytes": result.output_total_bytes or len(result.output),
        "output_truncated": (result.output_total_bytes or len(result.output)) > len(result.output),
    }
    if isinstance(report, dict):
        for key in (
            "agentCalls",
            "billableTokens",
            "expensiveSubagents",
            "opusBillableTokens",
        ):
            if isinstance(report.get(key), (int, float)):
                payload[key] = report[key]
    return payload


def _record_model_warning(root: Path, receipt: Mapping[str, Any], result: CommandResult) -> tuple[bool, str]:
    """Persist both warning receipt and append-only ledger transaction."""

    payload = _model_warning_payload(receipt, result)
    occurrence = _occurrence_key(receipt)
    warning_path = root / "logs" / "model-tier-audit-warnings" / f"{occurrence}.json"
    try:
        _atomic_json(warning_path, payload)
    except OSError:
        return False, ""
    valid, observed = _load_json_strict(warning_path)
    if not valid or observed != payload:
        return False, ""
    ledger_path = root / "logs" / "model-tier-audit.jsonl"
    marker_path = warning_path.parent / ".ledger" / f"{occurrence}.json"
    if not _append_json_line_once(
        ledger_path,
        payload,
        marker_path=marker_path,
        identity=occurrence,
    ):
        return False, ""
    try:
        relative = str(warning_path.relative_to(root))
    except ValueError:
        relative = str(warning_path)
    return warning_path.is_file(), relative


def _result_state(prior: Mapping[str, Any], result: CommandResult) -> dict[str, Any]:
    """Reduce one bounded attempt into the next durable consumer state."""

    attempts = int(prior.get("attempts") or 0) + 1
    succeeded = result.exit_code == 0
    status = "complete" if succeeded else ("failed" if attempts >= MAX_ATTEMPTS else "retry")
    return {
        "status": status,
        "attempts": attempts,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_ms": result.duration_ms,
        "output_sha256": hashlib.sha256(result.output).hexdigest(),
        "output_truncated": (result.output_total_bytes or len(result.output)) > len(result.output),
    }


def process_receipt(
    path: Path,
    *,
    root: Path,
    runner: Runner = run_bounded,
    specs: Sequence[ConsumerSpec] | None = None,
    deadline: float | None = None,
) -> tuple[int, int]:
    """Advance each unfinished consumer once and persist every result independently."""

    receipt = _load_json(path, {})
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("payload_valid") is not True:
        return 0, 0
    specs = tuple(specs or default_consumer_specs())
    consumers = dict(receipt.get("consumers") or {})
    attempted = 0
    completed = 0
    ordered: list[tuple[str, Callable[[], CommandResult]]] = [
        ("compatibility_closeout", lambda: _append_compatibility(root, receipt))
    ]
    ordered.extend(
        (
            spec.name,
            lambda spec=spec: runner(spec.command(root, receipt), spec.timeout_seconds, root, spec.environment),
        )
        for spec in specs
    )
    for name, invoke in ordered:
        state = dict(consumers.get(name) or {"status": "pending", "attempts": 0})
        if name == "compatibility_closeout" and not _is_isolation_worktree(receipt.get("cwd")):
            state = {"status": "not_applicable", "attempts": int(state.get("attempts") or 0)}
            consumers[name] = state
            receipt["consumers"] = consumers
            _atomic_json(path, receipt)
            continue
        if state.get("status") in TERMINAL_STATUSES:
            continue
        if int(state.get("attempts") or 0) >= MAX_ATTEMPTS:
            state["status"] = "failed"
            consumers[name] = state
            continue
        if deadline is not None and time.monotonic() >= deadline:
            break
        result = invoke()
        attempted += 1
        warning_receipt = ""
        audit_exit_code: int | None = None
        if name == "model_audit" and result.exit_code == 2:
            recorded, warning_receipt = _record_model_warning(root, receipt, result)
            audit_exit_code = result.exit_code
            if recorded:
                result = CommandResult(
                    0,
                    result.output,
                    result.duration_ms,
                    result.timed_out,
                    evidence_tail=result.evidence_tail,
                    output_total_bytes=result.output_total_bytes,
                )
        state = _result_state(state, result)
        if audit_exit_code is not None and state["status"] == "complete":
            state["warning"] = True
            state["audit_exit_code"] = audit_exit_code
            state["warning_receipt"] = warning_receipt
        completed += state["status"] == "complete"
        consumers[name] = state
        receipt["consumers"] = consumers
        receipt["updated_epoch"] = time.time()
        _atomic_json(path, receipt)
    return attempted, completed


def consume(
    *,
    root: Path,
    source: Path,
    cursor_path: Path,
    receipt_root: Path,
    runner: Runner = run_bounded,
    specs: Sequence[ConsumerSpec] | None = None,
    max_sessions: int = 8,
    runway_seconds: int = 60,
) -> dict[str, int]:
    """Drain one bounded batch under the shared nonblocking consumer lock."""

    empty = {"ingested": 0, "processed": 0, "attempted": 0, "completed": 0}
    with _consumer_lock(receipt_root) as acquired:
        if not acquired:
            return empty
        migrated_active, _migration_pending = _migrate_legacy_receipts(receipt_root)
        ingested_paths, ingested = ingest(source, cursor_path=cursor_path, receipt_root=receipt_root)
        active_paths = _bounded_active_paths(receipt_root, max(1, max_sessions))
        candidates = list(dict.fromkeys([*ingested_paths, *migrated_active, *active_paths]))[: max(1, max_sessions)]
        deadline = time.monotonic() + max(1, runway_seconds)
        attempted = completed = processed = 0
        for path in candidates:
            if time.monotonic() >= deadline:
                break
            count, successes = process_receipt(
                path,
                root=root,
                runner=runner,
                specs=specs,
                deadline=deadline,
            )
            attempted += count
            completed += successes
            processed += 1
            receipt = _load_json(path, {})
            if receipt.get("schema") == RECEIPT_SCHEMA:
                _place_receipt(path, receipt_root, receipt)
        return {
            "ingested": ingested,
            "processed": processed,
            "attempted": attempted,
            "completed": completed,
        }


def check(cursor_path: Path, receipt_root: Path) -> int:
    """Validate the cursor and partition metadata without scanning terminal receipts."""

    cursor_loaded, cursor = _load_json_strict(cursor_path)
    cursor_valid = cursor_loaded and (
        not cursor
        or (
            cursor.get("schema") == CURSOR_SCHEMA
            and isinstance(cursor.get("offset"), int)
            and not isinstance(cursor.get("offset"), bool)
            and cursor["offset"] >= 0
            and (cursor.get("device") is None or isinstance(cursor.get("device"), int))
            and (cursor.get("inode") is None or isinstance(cursor.get("inode"), int))
        )
    )
    if not cursor_valid:
        print("session-end-consumer --check: FAIL — invalid cursor")
        return 1
    index_path = receipt_root / ACTIVE_INDEX_NAME
    index_loaded, index = _load_json_strict(index_path)
    if not index_loaded:
        print("session-end-consumer --check: FAIL — corrupt active index")
        return 1
    if index and (
        index.get("schema") != ACTIVE_INDEX_SCHEMA
        or index.get("layout") != "partitioned-active-terminal-v1"
        or not isinstance(index.get("migration_pending"), bool)
    ):
        print("session-end-consumer --check: FAIL — invalid active index")
        return 1
    # This explicit predicate may inspect the complete pending queue; the heartbeat
    # hot path remains bounded and terminal history is never scanned here.
    for path in _bounded_active_paths(receipt_root, None):
        receipt_loaded, receipt = _load_json_strict(path)
        if not receipt_loaded or receipt.get("schema") != RECEIPT_SCHEMA or not _receipt_active(receipt):
            print(f"session-end-consumer --check: FAIL — invalid active receipt {path.name}")
            return 1
    print("session-end-consumer --check: OK")
    return 0


def main() -> int:
    """Run the bounded heartbeat consumer or its read-only integrity check."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--cursor", type=Path)
    parser.add_argument("--receipt-root", type=Path)
    parser.add_argument("--max-sessions", type=int, default=8)
    parser.add_argument("--runway-seconds", type=int, default=60)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = (args.root or Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))).resolve()
    source = args.source.expanduser() if args.source else default_source()
    cursor = args.cursor.expanduser() if args.cursor else root / "logs" / "session-end-breadcrumbs.cursor.json"
    receipt_root = (
        args.receipt_root.expanduser() if args.receipt_root else root / "logs" / "session-end-consumer-receipts"
    )
    if args.check:
        return check(cursor, receipt_root)
    result = consume(
        root=root,
        source=source,
        cursor_path=cursor,
        receipt_root=receipt_root,
        max_sessions=args.max_sessions,
        runway_seconds=args.runway_seconds,
    )
    print(
        "session-end-consumer: "
        f"ingested={result['ingested']} processed={result['processed']} "
        f"attempted={result['attempted']} complete={result['completed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
