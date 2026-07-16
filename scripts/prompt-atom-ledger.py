#!/usr/bin/env python3
"""Incrementally atomize the private prompt corpus and publish a redacted control view."""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shlex
import signal
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REPO = Path(__file__).resolve().parents[1]
CLI_SRC = REPO / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.prompt_corpus import (  # noqa: E402
    _json_bytes,
    _path_signature,
    LedgerPaths,
    atomic_write_bytes,
    attest_source_scan,
    build_snapshot,
    check_ledger,
    cursor_digest,
    current_source_scanner_code_digest,
    digest,
    load_event_journal,
    load_json_strict,
    load_jsonl,
    load_jsonl_strict,
    load_policy,
    occurrence_from_event,
    private_marker,
    prompt_authority_seal,
    public_projection,
    read_raw_object,
    render_markdown,
    structural_segments,
    update_ledger,
    validate_cursor_shape,
    validate_raw_references,
    validate_source_adapter_cursor,
)
from limen.prompt_sources import (  # noqa: E402
    AGY_CONVERSATION_UNIT_SIGNATURE_FIELDS,
    AGY_HISTORY_KEYSETS,
    CLAUDE_PROJECT_MEMORY_ALIAS_ID,
    CLAUDE_SUBAGENT_SESSION_ALIAS_ID,
    CLAUDE_DERIVED_TOOL_RESULT_INTEGER_FIELDS,
    CLAUDE_DERIVED_TOOL_RESULT_JOB_KEYS,
    CLAUDE_DERIVED_TOOL_RESULT_PROMPT_KEYSETS,
    CLAUDE_DERIVED_TOOL_RESULT_TEXT_FIELDS,
    CLAUDE_EXIT_PLAN_ALLOWED_PROMPT_INPUT_KEYS,
    CLAUDE_EXIT_PLAN_ALLOWED_PROMPT_KEYS,
    CODEX_COMPACTED_MESSAGE_KEYSETS,
    CODEX_COMPACTED_PAYLOAD_KEYSETS,
    CODEX_COMPACTION_ITEM_KEYSETS,
    CODEX_HISTORY_KEYSETS,
    CODEX_BYTE_RANGE_KEYS,
    CODEX_EVENT_USER_PAYLOAD_KEYSETS,
    CODEX_RESPONSE_USER_PAYLOAD_KEYSETS,
    CODEX_TEXT_ELEMENT_KEYS,
    CODEX_USER_CONTENT_BLOCK_KEYSETS,
    CODEX_USER_RECORD_KEYS,
    CLAUDE_ASSISTANT_CONTENT_BLOCK_TYPES,
    CLAUDE_ASSISTANT_PROMPT_FIELDS,
    CLAUDE_ATTACHMENT_PROMPT_FIELDS,
    CLAUDE_ATTACHMENT_TYPES,
    CLAUDE_GOAL_STATUS_KEYS,
    CLAUDE_PROJECT_JSONL_TYPES,
    CLAUDE_QUEUE_OPERATIONS,
    CLAUDE_SUBAGENT_METADATA_KEYS,
    CLAUDE_TASK_KEYSETS,
    CLAUDE_USER_CONTENT_BLOCK_TYPES,
    CLAUDE_USER_CONTENT_BLOCK_KEYSETS,
    CLAUDE_UNEXPECTED_PROMPT_FIELDS,
    CLAUDE_WORKFLOW_PHASE_KEYS,
    CLAUDE_WORKFLOW_PROGRESS_KEYS,
    CLAUDE_WORKFLOW_METADATA_KEYS,
    GEMINI_CONTENT_BLOCK_KEYSETS,
    GEMINI_NONUSER_RECORD_KEYSETS,
    GEMINI_SET_KEYSETS,
    GEMINI_USER_RECORD_KEYSETS,
    OPENCODE_ASSISTANT_MESSAGE_KEYSETS,
    OPENCODE_TASK_TOOL_INPUT_KEYSETS,
    OPENCODE_TASK_TOOL_METADATA_KEYSETS,
    OPENCODE_TASK_TOOL_PART_KEYS,
    OPENCODE_TASK_TOOL_STATE_KEYSETS,
    OPENCODE_TASK_TOOL_TIME_KEYSETS,
    OPENCODE_USER_MESSAGE_KEYS,
    OPENCODE_USER_PART_KEYSETS,
    OPENCODE_USER_SUMMARY_DIFF_KEYS,
    OPENCODE_USER_SUMMARY_KEYS,
    OPENCODE_USER_SUMMARY_MAX_BYTES,
    OPENCODE_UNIT_SIGNATURE_FIELDS,
    PROMPT_SOURCE_SCANNER_VERSION,
    SOURCE_ADAPTER_CONTRACT_VERSION,
    SOURCE_ADAPTER_RULES,
    SOURCE_ALIAS_BLOCKER_REASONS,
    SOURCE_FILE_SIGNATURE_FIELDS,
    SOURCE_MISSING_EXCLUSION_ID,
    SOURCE_RECORD_SCHEMAS,
    SourcePathCustody,
    agy_conversation_root_error,
    agy_conversation_storage_error,
    inspect_source_path_custody,
    source_adapter_contract,
    source_contract_receipt_applies,
)


SCANNER_VERSION = PROMPT_SOURCE_SCANNER_VERSION
DEFAULT_CLASSIFIER_TIMEOUT_SECONDS = 30.0
MAX_CLASSIFIER_TIMEOUT_SECONDS = 300.0
DEFAULT_RECLASSIFICATION_LIMIT = 100
MAX_RECLASSIFICATION_LIMIT = 10_000
DEFAULT_MAX_SOURCE_BYTES_PER_UNIT = 32 * 1024 * 1024
HARD_MAX_SOURCE_BYTES_PER_UNIT = 512 * 1024 * 1024
DEFAULT_MAX_EVENTS_PER_UNIT = 10_000
HARD_MAX_EVENTS_PER_UNIT = 100_000
DEFAULT_MAX_DISCOVERY_UNITS = 100_000
HARD_MAX_DISCOVERY_UNITS = 1_000_000
DEFAULT_MAX_CLASSIFIER_INPUT_BYTES = 16 * 1024 * 1024
HARD_MAX_CLASSIFIER_INPUT_BYTES = 64 * 1024 * 1024
MAX_CLASSIFIER_OUTPUT_BYTES = 8 * 1024 * 1024
HARD_MAX_CLASSIFIER_OUTPUT_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_CLASSIFIER_STDERR_BYTES = 1024 * 1024
HARD_MAX_CLASSIFIER_STDERR_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_CLASSIFIER_OCCURRENCES = 10_000
HARD_MAX_CLASSIFIER_OCCURRENCES = 100_000
DEFAULT_MAX_WORK_UNITS = 80
SOURCE_HOME_OVERRIDE: Path | None = None


@dataclass(frozen=True)
class ClassifierRun:
    """Result of one opaque runtime-classifier invocation."""

    events: list[dict[str, Any]]
    attempted: bool
    classified_occurrences: int
    error: str | None = None


@dataclass(frozen=True)
class ResourceLimits:
    """Hard ceilings for one bounded scanner invocation.

    Work-unit limits bound how many source containers are attempted. These
    limits bound the size of each container, its event cardinality, discovery,
    and the optional classifier protocol so one nominal unit cannot be
    arbitrarily expensive.
    """

    max_source_bytes_per_unit: int
    max_events_per_unit: int
    max_discovery_units: int
    max_classifier_input_bytes: int
    max_classifier_output_bytes: int
    max_classifier_stderr_bytes: int
    max_classifier_occurrences: int


class DiscoveredRows(list[dict[str, Any]]):
    """List-compatible discovery result carrying fail-closed truncation data."""

    def __init__(self) -> None:
        super().__init__()
        self.discovery_errors: list[tuple[str, str]] = []
        self.source_alias_blocker_counts: Counter[str] = Counter()
        self.truncated_source: str | None = None
        self.discovered_count = 0


def policy_number(
    policy: dict[str, Any],
    dotted_key: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    """Read a nested runtime-policy number without coupling to its full schema."""

    value: Any = policy
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            value = default
            break
        value = value[part]
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(maximum, max(minimum, number))


def classifier_timeout_seconds(policy: dict[str, Any]) -> float:
    return policy_number(
        policy,
        "confidence_thresholds.command_timeout_seconds",
        DEFAULT_CLASSIFIER_TIMEOUT_SECONDS,
        minimum=0.05,
        maximum=MAX_CLASSIFIER_TIMEOUT_SECONDS,
    )


def reclassification_limit(policy: dict[str, Any]) -> int:
    return int(
        policy_number(
            policy,
            "reclassification.max_occurrences_per_run",
            DEFAULT_RECLASSIFICATION_LIMIT,
            minimum=1,
            maximum=MAX_RECLASSIFICATION_LIMIT,
        )
    )


def runtime_limits(policy: dict[str, Any]) -> ResourceLimits:
    """Load bounded, provider-neutral resource ceilings from runtime policy."""

    def integer(name: str, default: int, hard_maximum: int) -> int:
        return int(
            policy_number(
                policy,
                f"resource_limits.{name}",
                default,
                minimum=1,
                maximum=hard_maximum,
            )
        )

    return ResourceLimits(
        max_source_bytes_per_unit=integer(
            "max_source_bytes_per_unit",
            DEFAULT_MAX_SOURCE_BYTES_PER_UNIT,
            HARD_MAX_SOURCE_BYTES_PER_UNIT,
        ),
        max_events_per_unit=integer(
            "max_events_per_unit",
            DEFAULT_MAX_EVENTS_PER_UNIT,
            HARD_MAX_EVENTS_PER_UNIT,
        ),
        max_discovery_units=integer(
            "max_discovery_units",
            DEFAULT_MAX_DISCOVERY_UNITS,
            HARD_MAX_DISCOVERY_UNITS,
        ),
        max_classifier_input_bytes=integer(
            "max_classifier_input_bytes",
            DEFAULT_MAX_CLASSIFIER_INPUT_BYTES,
            HARD_MAX_CLASSIFIER_INPUT_BYTES,
        ),
        max_classifier_output_bytes=integer(
            "max_classifier_output_bytes",
            MAX_CLASSIFIER_OUTPUT_BYTES,
            HARD_MAX_CLASSIFIER_OUTPUT_BYTES,
        ),
        max_classifier_stderr_bytes=integer(
            "max_classifier_stderr_bytes",
            DEFAULT_MAX_CLASSIFIER_STDERR_BYTES,
            HARD_MAX_CLASSIFIER_STDERR_BYTES,
        ),
        max_classifier_occurrences=integer(
            "max_classifier_occurrences",
            DEFAULT_MAX_CLASSIFIER_OCCURRENCES,
            HARD_MAX_CLASSIFIER_OCCURRENCES,
        ),
    )


def _classification_text(event: dict[str, Any]) -> str:
    task_body = str(event.get("task_body") or "")
    return task_body if task_body.strip() else str(event.get("text") or "")


def _classifier_requests(
    events: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], str | None]:
    requests: list[dict[str, Any]] = []
    by_occurrence: dict[str, dict[str, Any]] = {}
    for event in events:
        reserved = str(event.get("existing_occurrence_id") or "")
        occurrence = occurrence_from_event(event)
        occurrence_id = reserved or str(occurrence["occurrence_id"])
        if occurrence_id in by_occurrence:
            return [], {}, f"duplicate input occurrence id: {occurrence_id}"
        text = _classification_text(event)
        segments = structural_segments(text)
        requests.append(
            {
                "schema_version": 1,
                "occurrence_id": occurrence_id,
                "source": str(event.get("source") or "unknown"),
                "body_kind": str(event.get("body_kind") or "direct"),
                "provenance": str(occurrence.get("provenance") or "unknown_user_input"),
                "authority": str(occurrence.get("authority") or "unknown"),
                "text": text,
                "segments": [{"index": index, "text": segment} for index, segment in enumerate(segments)],
            }
        )
        by_occurrence[occurrence_id] = event
    return requests, by_occurrence, None


def _bounded_jsonl_payload(rows: Sequence[dict[str, Any]], limit: int) -> bytes | None:
    """Serialize JSONL incrementally and stop before crossing the byte ceiling."""

    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True)
    payload = bytearray()
    for row in rows:
        for piece in encoder.iterencode(row):
            encoded = piece.encode("utf-8")
            if len(payload) + len(encoded) + 1 > limit:
                return None
            payload.extend(encoded)
        payload.extend(b"\n")
    return bytes(payload)


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except ProcessLookupError:
            pass


def _bounded_classifier_io(
    process: subprocess.Popen[bytes],
    payload: bytes,
    *,
    timeout: float,
    stdout_limit: int,
    stderr_limit: int,
) -> tuple[bytes, bytes, str | None]:
    """Feed and drain a classifier without ever accumulating unbounded output."""

    stdout = bytearray()
    stderr = bytearray()
    overflow: list[str] = []
    overflow_lock = threading.Lock()

    def mark_overflow(label: str) -> None:
        with overflow_lock:
            if not overflow:
                overflow.append(label)
                _terminate_process_group(process)

    def reader(stream: Any, target: bytearray, limit: int, label: str) -> None:
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                if len(target) + len(chunk) > limit:
                    mark_overflow(label)
                    return
                target.extend(chunk)
        except (OSError, ValueError):
            return
        finally:
            with contextlib.suppress(OSError):
                stream.close()

    def writer() -> None:
        if process.stdin is None:
            return
        try:
            view = memoryview(payload)
            for offset in range(0, len(view), 64 * 1024):
                process.stdin.write(view[offset : offset + 64 * 1024])
            process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            with contextlib.suppress(OSError):
                process.stdin.close()

    if process.stdout is None or process.stderr is None:
        _terminate_process_group(process)
        return b"", b"", "classifier pipes are unavailable"
    threads = [
        threading.Thread(
            target=reader,
            args=(process.stdout, stdout, stdout_limit, "stdout"),
            daemon=True,
        ),
        threading.Thread(
            target=reader,
            args=(process.stderr, stderr, stderr_limit, "stderr"),
            daemon=True,
        ),
        threading.Thread(target=writer, daemon=True),
    ]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout
    timed_out = False
    while process.poll() is None:
        if overflow:
            _terminate_process_group(process)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            _terminate_process_group(process)
            break
        try:
            process.wait(timeout=min(0.05, remaining))
        except subprocess.TimeoutExpired:
            continue
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=1.0)
    for thread in threads:
        thread.join(timeout=1.0)
    if timed_out:
        return bytes(stdout), bytes(stderr), "timeout"
    if overflow:
        return bytes(stdout), bytes(stderr), f"{overflow[0]}_limit"
    return bytes(stdout), bytes(stderr), None


def classify_events(
    events: Sequence[dict[str, Any]],
    *,
    command: str | None,
    policy: dict[str, Any],
) -> ClassifierRun:
    """Enrich events through an opaque JSONL command or retain structural fallback.

    The command receives one request per line and must return exactly one object
    per requested occurrence: ``{"occurrence_id": "...", "atoms": [...]}``.
    Any process or protocol failure leaves every input event unchanged, so the
    core structural atomizer retains complete source coverage.
    """

    fallback = [dict(event) for event in events]
    if not command or not command.strip() or not fallback:
        return ClassifierRun(events=fallback, attempted=False, classified_occurrences=0)
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error=f"classifier command cannot be parsed: {exc}",
        )
    if not argv:
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error="classifier command is empty",
        )

    limits = runtime_limits(policy)
    if len(fallback) > limits.max_classifier_occurrences:
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error="classifier input exceeds the bounded occurrence limit",
        )
    text_characters = 0
    for event in fallback:
        text_characters += len(_classification_text(event))
        if text_characters > limits.max_classifier_input_bytes:
            return ClassifierRun(
                events=fallback,
                attempted=True,
                classified_occurrences=0,
                error="classifier input exceeds the bounded byte limit",
            )
    requests, by_occurrence, request_error = _classifier_requests(fallback)
    if request_error:
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error=request_error,
        )
    payload = _bounded_jsonl_payload(requests, limits.max_classifier_input_bytes)
    if payload is None:
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error="classifier input exceeds the bounded byte limit",
        )
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            shell=False,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error=f"classifier command could not start: {exc}",
        )
    timeout = classifier_timeout_seconds(policy)
    stdout_bytes, _stderr_bytes, process_error = _bounded_classifier_io(
        process,
        payload,
        timeout=timeout,
        stdout_limit=limits.max_classifier_output_bytes,
        stderr_limit=limits.max_classifier_stderr_bytes,
    )
    if process_error == "timeout":
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error=f"classifier command exceeded {timeout:g}s timeout",
        )
    if process_error == "stdout_limit":
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error="classifier output exceeds the bounded response limit",
        )
    if process_error == "stderr_limit":
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error="classifier stderr exceeds the bounded diagnostic limit",
        )
    if process_error:
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error=process_error,
        )
    if process.returncode != 0:
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error=f"classifier command exited with status {process.returncode}",
        )
    try:
        stdout = stdout_bytes.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error=f"classifier output is not UTF-8: {exc}",
        )

    responses: dict[str, list[dict[str, Any]]] = {}
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (TypeError, ValueError) as exc:
            return ClassifierRun(
                events=fallback,
                attempted=True,
                classified_occurrences=0,
                error=f"classifier output line {line_number} is malformed JSON: {exc}",
            )
        if not isinstance(row, dict):
            return ClassifierRun(
                events=fallback,
                attempted=True,
                classified_occurrences=0,
                error=f"classifier output line {line_number} is not an object",
            )
        occurrence_id = str(row.get("occurrence_id") or "")
        if occurrence_id not in by_occurrence:
            return ClassifierRun(
                events=fallback,
                attempted=True,
                classified_occurrences=0,
                error=f"classifier returned an unexpected occurrence id: {occurrence_id or '<missing>'}",
            )
        if occurrence_id in responses:
            return ClassifierRun(
                events=fallback,
                attempted=True,
                classified_occurrences=0,
                error=f"classifier returned a duplicate occurrence id: {occurrence_id}",
            )
        atoms = row.get("atoms")
        if not isinstance(atoms, list) or not all(isinstance(atom, dict) for atom in atoms):
            return ClassifierRun(
                events=fallback,
                attempted=True,
                classified_occurrences=0,
                error=f"classifier atoms for {occurrence_id} are not an object list",
            )
        responses[occurrence_id] = [dict(atom) for atom in atoms]
    expected_ids = set(by_occurrence)
    if set(responses) != expected_ids:
        missing = ", ".join(sorted(expected_ids - set(responses)))
        return ClassifierRun(
            events=fallback,
            attempted=True,
            classified_occurrences=0,
            error=f"classifier response is missing occurrence ids: {missing}",
        )

    enriched: list[dict[str, Any]] = []
    for event in fallback:
        occurrence_id = str(event.get("existing_occurrence_id") or occurrence_from_event(event)["occurrence_id"])
        row = dict(event)
        row["atoms"] = [
            {**candidate, "classifier_provenance": "runtime_command"} for candidate in responses[occurrence_id]
        ]
        enriched.append(row)
    return ClassifierRun(
        events=enriched,
        attempted=True,
        classified_occurrences=len(enriched),
    )


def existing_reclassification_events(
    paths: LedgerPaths,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Rehydrate a bounded, deterministic set of canonical existing occurrences."""

    occurrences, atoms, errors = load_event_journal(paths.event_journal)
    if errors:
        raise ValueError("; ".join(errors))
    atoms_by_occurrence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in atoms:
        atoms_by_occurrence[str(atom.get("occurrence_id") or "")].append(atom)

    eligible = [
        occurrence
        for occurrence in occurrences
        if occurrence.get("occurrence_id") and occurrence.get("raw_object") and not occurrence.get("excluded_reason")
    ]
    eligible.sort(
        key=lambda occurrence: (
            0
            if any(
                atom.get("atomization_mode") == "structural_fallback"
                for atom in atoms_by_occurrence.get(str(occurrence.get("occurrence_id")), [])
            )
            else 1,
            int(occurrence.get("classification_revision") or 0),
            str(occurrence.get("timestamp") or ""),
            str(occurrence.get("occurrence_id") or ""),
        )
    )
    events: list[dict[str, Any]] = []
    for occurrence in eligible[: reclassification_limit(policy)]:
        raw = read_raw_object(paths, str(occurrence["raw_object"]))
        events.append(
            {
                # The writer must reserve this canonical identity. Session/event
                # references are intentionally hash-only in the private journal.
                "existing_occurrence_id": str(occurrence["occurrence_id"]),
                "source": str(occurrence.get("source") or "unknown"),
                "session_ref": str(occurrence.get("session_ref_hash") or "unknown"),
                "event_ref": str(occurrence.get("event_ref_hash") or "unknown"),
                "event_index": int(occurrence.get("event_index") or 0),
                "text_index": int(occurrence.get("text_index") or 0),
                "source_locator": occurrence.get("source_locator"),
                "timestamp": occurrence.get("timestamp"),
                "text": raw,
                "body_kind": str(occurrence.get("body_kind") or "direct"),
                "provenance": str(occurrence.get("provenance") or "unknown_user_input"),
                "authority": str(occurrence.get("authority") or "unknown"),
            }
        )
    return events


@dataclass
class ScanBudget:
    """One work-unit ceiling within the fleet-wide hard cap."""

    limit: int | None
    used: int = 0

    @classmethod
    def from_cli(cls, max_files: int, *, unbounded: bool = False) -> "ScanBudget":
        if max_files < 0:
            raise ValueError("max-files cannot be negative")
        if unbounded:
            return cls(None)
        if max_files <= 0:
            raise ValueError("max-files must be positive unless --unbounded is explicit")
        return cls(max_files)

    def claim(self) -> bool:
        if self.limit is not None and self.used >= self.limit:
            return False
        self.used += 1
        return True


def empty_coverage() -> dict[str, int]:
    return {
        "discovered": 0,
        "converged": 0,
        "adapted": 0,
        "excluded": 0,
        "scanned": 0,
        "pending": 0,
        "errors": 0,
        "unsupported": 0,
    }


def coverage_row(coverage: dict[str, dict[str, int]], source: str) -> dict[str, int]:
    return coverage.setdefault(source, empty_coverage())


def merge_coverage(*groups: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    merged: dict[str, dict[str, int]] = {}
    for group in groups:
        for source, counts in group.items():
            target = coverage_row(merged, source)
            for key in target:
                target[key] += int(counts.get(key) or 0)
    return dict(sorted(merged.items()))


def fair_scan_budgets(
    max_files: int,
    *,
    rotation: int,
    active_lanes: Sequence[str] | None = None,
    unbounded: bool = False,
) -> dict[str, ScanBudget]:
    """Reserve a rotating share for each agent lane within one hard cap."""

    families = ("codex", "claude", "gemini", "opencode", "agy")
    if max_files < 0:
        raise ValueError("max-files cannot be negative")
    if unbounded:
        return {family: ScanBudget(limit=None) for family in families}
    if max_files <= 0:
        raise ValueError("max-files must be positive unless --unbounded is explicit")
    allocations = {family: 0 for family in families}
    active = [family for family in families if active_lanes is None or family in active_lanes]
    if not active:
        return {family: ScanBudget(limit=0) for family in families}
    for offset in range(max_files):
        family = active[(rotation + offset) % len(active)]
        allocations[family] += 1
    return {family: ScanBudget(limit=allocations[family]) for family in families}


def regular_lane(source: str) -> str:
    if source == "gemini-tmp-agy":
        return "agy"
    for lane in ("codex", "claude", "gemini", "agy"):
        if source == lane or source.startswith(f"{lane}-"):
            return lane
    return ("codex", "claude", "gemini", "agy")[int(digest(source)[:2], 16) % 4]


def active_scan_lanes(lifecycle: Any, rows: Sequence[dict[str, Any]]) -> set[str]:
    lanes = {regular_lane(str(row.get("source") or "unknown")) for row in rows}
    opencode_path = getattr(lifecycle, "OPENCODE_DB", None)
    if opencode_path is not None and Path(opencode_path).is_file():
        lanes.add("opencode")
    agy_root = getattr(lifecycle, "AGY_CLI_CONVERSATIONS", None)
    if agy_root is not None and Path(agy_root).is_dir():
        home = getattr(lifecycle, "HOME", None)
        root_error = (
            agy_conversation_root_error(Path(home), Path(agy_root))
            if home is not None
            else "configured HOME is unavailable"
        )
        if root_error:
            lanes.add("agy")
            return lanes
        try:
            if next(Path(agy_root).rglob("*.db"), None) is not None:
                lanes.add("agy")
        except OSError:
            lanes.add("agy")
    return lanes


def source_scan_budget(
    budget: ScanBudget | dict[str, ScanBudget],
    source: str,
) -> ScanBudget:
    if isinstance(budget, ScanBudget):
        return budget
    return budget[regular_lane(source)]


def _redacted_policy_text(value: Any, fallback: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return fallback
    local_markers = ("/Users/", "/Volumes/", "/private/", "/tmp/", "~/", "file://")
    return fallback if any(marker in candidate for marker in local_markers) else candidate


def build_adapter_gap_routes(
    adapter_gaps: Sequence[str],
    policy: dict[str, Any],
) -> list[dict[str, str]]:
    """Owner-route unsupported sources without exposing private source locators."""

    routing = policy.get("owner_routing")
    routing = routing if isinstance(routing, dict) else {}
    default_owner = _redacted_policy_text(routing.get("default_owner"), "organvm/limen")
    default_route = _redacted_policy_text(
        routing.get("default_route"),
        "TABVLARIVS/prompt-atom-intake",
    )
    default_next = _redacted_policy_text(
        routing.get("default_next_command"),
        "python3 scripts/prompt-atom-ledger.py --scan --all --write",
    )
    per_source: dict[str, Any] = {}
    for key in ("sources", "adapters", "by_source"):
        candidate = routing.get(key)
        if isinstance(candidate, dict):
            per_source.update(candidate)

    routes: list[dict[str, str]] = []
    for raw_source in sorted(set(str(value) for value in adapter_gaps if str(value))):
        source = raw_source if re.fullmatch(r"[A-Za-z0-9_.:-]+", raw_source) else f"source-{digest(raw_source)[:12]}"
        override = per_source.get(raw_source)
        if not isinstance(override, dict) and isinstance(routing.get(raw_source), dict):
            override = routing[raw_source]
        override = override if isinstance(override, dict) else {}
        routes.append(
            {
                "source": source,
                "owner": _redacted_policy_text(override.get("owner"), default_owner),
                "route": _redacted_policy_text(override.get("route"), default_route),
                "failed_predicate": _redacted_policy_text(
                    override.get("failed_predicate"),
                    f"prompt-source-adapter:{source}:complete",
                ),
                "next_command": _redacted_policy_text(
                    override.get("next_command"),
                    default_next,
                ),
            }
        )
    return routes


def cursor_unit_key(source: str, locator: Any) -> str:
    return f"scan-v{SCANNER_VERSION}:{source}:{locator}"


def load_lifecycle_module() -> Any:
    path = REPO / "scripts" / "prompt-lifecycle-ledger.py"
    spec = importlib.util.spec_from_file_location("prompt_lifecycle_for_atoms", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if SOURCE_HOME_OVERRIDE is not None:
        original_home = Path(module.HOME)
        source_home = SOURCE_HOME_OVERRIDE.resolve()

        def rebase(path: Any) -> Path:
            candidate = Path(path)
            try:
                return source_home / candidate.relative_to(original_home)
            except ValueError:
                return candidate

        module.HOME = source_home
        for attribute in (
            "OPENCODE_DB",
            "AGY_CLI_ROOT",
            "AGY_CLI_HISTORY",
            "AGY_CLI_CONVERSATIONS",
        ):
            if hasattr(module, attribute):
                setattr(module, attribute, rebase(getattr(module, attribute)))
        module.LOCAL_SOURCES = [(source, rebase(root), patterns) for source, root, patterns in module.LOCAL_SOURCES]
    return module


def file_signature(path: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    values = {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "inode": stat.st_ino,
        "device": stat.st_dev,
    }
    return {field: values[field] for field in SOURCE_FILE_SIGNATURE_FIELDS}


def canonical_source_root(lifecycle: Any, source: str) -> Path | None:
    for item in getattr(lifecycle, "LOCAL_SOURCES", ()):
        if isinstance(item, (tuple, list)) and len(item) >= 2 and str(item[0]) == source:
            return Path(item[1])
    if source == "gemini-tmp" and getattr(lifecycle, "HOME", None) is not None:
        return Path(lifecycle.HOME) / ".gemini" / "tmp"
    return None


def containing_source_root(lifecycle: Any, source: str, path: Path) -> Path | None:
    """Select the most specific declared root that lexically contains this unit."""

    lexical_path = path.expanduser().absolute()
    candidates: list[Path] = []
    for item in getattr(lifecycle, "LOCAL_SOURCES", ()):
        if not isinstance(item, (tuple, list)) or len(item) < 2 or str(item[0]) != source:
            continue
        root = Path(item[1])
        lexical_root = root.expanduser().absolute()
        try:
            lexical_path.relative_to(lexical_root) if lexical_path != lexical_root else None
        except ValueError:
            continue
        candidates.append(root)
    if candidates:
        return max(candidates, key=lambda candidate: len(candidate.expanduser().absolute().parts))
    return canonical_source_root(lifecycle, source)


def source_path_custody(
    lifecycle: Any,
    source: str,
    path: Path,
    *,
    containment_root: Path | None = None,
) -> SourcePathCustody:
    root = containment_root or containing_source_root(lifecycle, source, path) or path.parent
    return inspect_source_path_custody(
        source,
        path,
        root,
        isolated_home=SOURCE_HOME_OVERRIDE,
    )


def source_relative_path(lifecycle: Any, source: str, path: Path) -> Path | None:
    """Return a source-relative role after typed direct-or-alias custody succeeds."""

    root_path = canonical_source_root(lifecycle, source)
    if root_path is None:
        return None
    custody = source_path_custody(lifecycle, source, path, containment_root=root_path)
    return custody.relative if custody.error is None else None


def source_unit_signature(
    lifecycle: Any,
    source: str,
    path: Path,
    *,
    containment_root: Path | None = None,
) -> dict[str, int] | None:
    custody = source_path_custody(
        lifecycle,
        source,
        path,
        containment_root=containment_root,
    )
    if custody.error is not None:
        return None
    if custody.alias_contract_id in {
        CLAUDE_PROJECT_MEMORY_ALIAS_ID,
        CLAUDE_SUBAGENT_SESSION_ALIAS_ID,
    }:
        return custody.unit_signature
    return file_signature(path)


def _bounded_file_bytes(path: Path, signature: dict[str, Any], *, maximum: int) -> bytes | None:
    if int(signature.get("size") or 0) > maximum:
        return None
    try:
        with path.open("rb") as handle:
            payload = handle.read(maximum + 1)
    except OSError:
        return None
    return payload if len(payload) <= maximum else None


def _bounded_ascii_decimal(path: Path, signature: dict[str, Any]) -> bool:
    payload = _bounded_file_bytes(path, signature, maximum=128)
    if payload is None:
        return False
    try:
        value = payload.decode("ascii", errors="strict")
    except UnicodeError:
        return False
    return re.fullmatch(r"[0-9]+(?:\r?\n)?", value) is not None


def source_exclusion_candidate_id(
    lifecycle: Any,
    source: str,
    path: Path,
    signature: dict[str, Any],
) -> str | None:
    """Return a path/metadata-only exclusion candidate without reading content."""

    custody = source_path_custody(lifecycle, source, path)
    relative = custody.relative
    if custody.error is not None or relative is None:
        return None
    if custody.alias_contract_id == CLAUDE_PROJECT_MEMORY_ALIAS_ID:
        return custody.alias_contract_id
    if custody.alias_contract_id == CLAUDE_SUBAGENT_SESSION_ALIAS_ID:
        return custody.alias_contract_id if path.is_file() else None
    parts = relative.parts
    suffix = path.suffix.lower()

    if source == "claude-file-history":
        if len(parts) >= 1 and re.fullmatch(r"[0-9a-fA-F]+@v[0-9]+", path.name):
            return "claude-file-history-snapshot-v1"
        return None
    if source == "claude-plans":
        return "claude-generated-plan-v1"
    if source == "claude-tasks" and len(parts) >= 2:
        if len(parts) == 2 and path.name == ".lock" and int(signature.get("size") or 0) == 0:
            return "claude-task-lock-v1"
        if len(parts) == 2 and path.name == ".highwatermark":
            return "claude-task-watermark-v1"
        if suffix not in (".json", ".jsonl", ".md"):
            return "claude-task-artifact-v1"
        return None
    if source != "claude-projects" or len(parts) < 2:
        return None

    if len(parts) >= 4 and parts[2] == "tool-results":
        return "claude-project-tool-result-v1"
    if len(parts) >= 5 and parts[2:4] == ("workflows", "scripts") and suffix == ".js":
        return "claude-workflow-script-v1"
    if len(parts) == 3 and parts[1] == "memory" and suffix == ".md":
        return "claude-project-memory-v1"
    if len(parts) == 2 and suffix == ".md":
        sibling = path.parent / "memory" / path.name
        sibling_relative = source_relative_path(lifecycle, source, sibling)
        if sibling_relative is not None and sibling_relative.parts == (parts[0], "memory", path.name):
            return "claude-project-memory-mirror-v1"
        return None
    if len(parts) >= 4 and suffix not in (".json", ".jsonl", ".md"):
        return "claude-project-media-v1"
    return None


def _memory_mirror_signature(
    lifecycle: Any,
    source: str,
    path: Path,
) -> dict[str, Any] | None:
    sibling = path.parent / "memory" / path.name
    if source_relative_path(lifecycle, source, sibling) is None:
        return None
    return file_signature(sibling)


def confirm_source_exclusion(
    lifecycle: Any,
    source: str,
    path: Path,
    signature: dict[str, Any],
    candidate_id: str,
) -> tuple[str, dict[str, dict[str, Any]], dict[str, dict[str, str]]] | None:
    """Confirm a candidate after its work unit has been claimed."""

    if candidate_id == "claude-task-watermark-v1" and not _bounded_ascii_decimal(path, signature):
        return None
    related: dict[str, dict[str, Any]] = {}
    related_evidence: dict[str, dict[str, str]] = {}
    if candidate_id in {
        CLAUDE_PROJECT_MEMORY_ALIAS_ID,
        CLAUDE_SUBAGENT_SESSION_ALIAS_ID,
    }:
        custody = source_path_custody(lifecycle, source, path)
        if (
            custody.error is not None
            or custody.alias_contract_id != candidate_id
            or custody.unit_signature != signature
            or custody.related_signatures is None
            or custody.related_evidence is None
        ):
            return None
        related = dict(custody.related_signatures)
        related_evidence = dict(custody.related_evidence)
    elif candidate_id == "claude-project-memory-mirror-v1":
        sibling = path.parent / "memory" / path.name
        sibling_signature = _memory_mirror_signature(lifecycle, source, path)
        if sibling_signature is None or sibling_signature.get("size") != signature.get("size"):
            return None
        maximum = 16 * 1024 * 1024
        payload = _bounded_file_bytes(path, signature, maximum=maximum)
        sibling_payload = _bounded_file_bytes(sibling, sibling_signature, maximum=maximum)
        if payload is None or sibling_payload is None:
            return None
        primary_sha = hashlib.sha256(payload).hexdigest()
        related_sha = hashlib.sha256(sibling_payload).hexdigest()
        if primary_sha != related_sha:
            return None
        if file_signature(sibling) != sibling_signature:
            return None
        related["memory_sibling"] = sibling_signature
        related_evidence["memory_sibling"] = {
            "locator_sha256": hashlib.sha256(str(sibling).encode("utf-8", errors="replace")).hexdigest(),
            "primary_content_sha256": primary_sha,
            "related_content_sha256": related_sha,
        }
    return candidate_id, related, related_evidence


def current_exclusion_related_signatures(
    lifecycle: Any,
    source: str,
    path: Path,
    candidate_id: str,
) -> dict[str, dict[str, Any]] | None:
    if candidate_id in {
        CLAUDE_PROJECT_MEMORY_ALIAS_ID,
        CLAUDE_SUBAGENT_SESSION_ALIAS_ID,
    }:
        custody = source_path_custody(lifecycle, source, path)
        if custody.error is not None or custody.alias_contract_id != candidate_id:
            return None
        return dict(custody.related_signatures or {})
    if candidate_id != "claude-project-memory-mirror-v1":
        return {}
    signature = _memory_mirror_signature(lifecycle, source, path)
    return {"memory_sibling": signature} if signature is not None else None


def current_exclusion_related_evidence(
    lifecycle: Any,
    source: str,
    path: Path,
    candidate_id: str,
) -> dict[str, dict[str, Any]] | None:
    if candidate_id in {
        CLAUDE_PROJECT_MEMORY_ALIAS_ID,
        CLAUDE_SUBAGENT_SESSION_ALIAS_ID,
    }:
        custody = source_path_custody(lifecycle, source, path)
        if custody.error is not None or custody.alias_contract_id != candidate_id:
            return None
        return dict(custody.related_evidence or {})
    return None


def source_unit_receipt_matches(
    receipt: Any,
    *,
    disposition: str,
    contract_id: str,
    contract_digest: str,
    source: str,
    locator: str,
    signature: dict[str, Any],
    related_signatures: dict[str, dict[str, Any]] | None = None,
    expected_related_evidence: dict[str, dict[str, Any]] | None = None,
) -> bool:
    related_evidence = receipt.get("related_evidence", {}) if isinstance(receipt, dict) else {}
    return bool(
        isinstance(receipt, dict)
        and receipt.get("version") == SOURCE_ADAPTER_CONTRACT_VERSION
        and receipt.get("disposition") == disposition
        and receipt.get("contract_id") == contract_id
        and receipt.get("contract_digest") == contract_digest
        and receipt.get("signature") == signature
        and receipt.get("related_signatures", {}) == (related_signatures or {})
        and (expected_related_evidence is None or related_evidence == expected_related_evidence)
        and source_contract_receipt_applies(
            contract_id,
            source,
            locator,
            signature=signature,
            related_signatures=related_signatures,
            related_evidence=related_evidence,
        )
    )


def native_source_adapter_candidate_id(
    lifecycle: Any,
    source: str,
    path: Path,
) -> str | None:
    relative = source_relative_path(lifecycle, source, path)
    if relative is None:
        return None
    if source == "codex-attachments":
        if len(relative.parts) == 2 and re.fullmatch(r"pasted-text-[1-9][0-9]*\.txt", path.name):
            return "codex-pasted-text-attachment-v1"
        return None
    if source == "codex-sessions":
        parts = relative.parts
        if (
            len(parts) == 4
            and re.fullmatch(r"20[0-9]{2}", parts[0])
            and re.fullmatch(r"(?:0[1-9]|1[0-2])", parts[1])
            and re.fullmatch(r"(?:0[1-9]|[12][0-9]|3[01])", parts[2])
            and re.fullmatch(r"rollout-.+\.jsonl", parts[3])
        ):
            return "codex-session-jsonl-v2"
        return None
    if source != "claude-projects" or path.suffix.lower() != ".json":
        return None
    if len(relative.parts) == 4 and relative.parts[2] == "remote-agents":
        return "claude-remote-task-command-v1"
    role_parts = set(relative.parts[2:])
    if "subagents" in role_parts:
        return "claude-subagent-metadata-v1"
    if "workflows" in role_parts:
        return "claude-workflow-metadata-v1"
    return None


def claude_project_path_authority(lifecycle: Any, source: str, path: Path) -> str | None:
    if source != "claude-projects":
        return None
    relative = source_relative_path(lifecycle, source, path)
    if relative is None:
        return "unknown"
    if any(part in {"subagents", "workflows"} for part in relative.parts[2:]):
        return "derived"
    if path.suffix.lower() == ".jsonl":
        return "operator" if len(relative.parts) == 2 else "unknown"
    return None


def bounded_sqlite_lengths(
    connection: sqlite3.Connection,
    query: str,
    params: tuple[Any, ...],
    *,
    max_rows: int,
    max_bytes: int,
) -> tuple[int, int, str | None]:
    """Read only bounded SQLite length metadata before materializing payload rows."""

    count = 0
    total = 0
    for row in connection.execute(query, (*params, max_rows + 1)):
        count += 1
        if count > max_rows:
            return count, total, "rows"
        total += int(row[0] or 0)
        if total > max_bytes:
            return count, total, "bytes"
    return count, total, None


def event_timestamp(obj: dict[str, Any]) -> Any:
    payload = obj.get("payload")
    return obj.get("timestamp") or obj.get("ts") or (payload.get("timestamp") if isinstance(payload, dict) else None)


def canonical_file_session_id(source: str, path: Path, records: list[dict[str, Any]]) -> str | None:
    """Resolve a file-level session id before visiting prompt rows.

    Codex user-message rows do not themselves carry the session id.  The
    ``session_meta`` row does, so falling back per event to the file path makes
    the same turn disagree with ``codex-history`` and defeats echo deduplication.
    """

    if source != "codex-sessions":
        return None
    candidates: list[str] = []
    for obj in records:
        if obj.get("type") != "session_meta":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        for key in ("id", "session_id"):
            if payload.get(key):
                value = str(payload[key])
                if value not in candidates:
                    candidates.append(value)
    if not candidates:
        return None
    path_matches = [value for value in candidates if value in path.name]
    if len(path_matches) == 1:
        return path_matches[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def codex_session_identity_error(path: Path, records: list[dict[str, Any]]) -> str | None:
    """Require one canonical file identity while permitting exact resume metadata."""

    candidates: list[str] = []
    for obj in records:
        if obj.get("type") != "session_meta":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            return "Codex session metadata is malformed"
        identity_count = 0
        for key in ("id", "session_id"):
            if key not in payload:
                continue
            value = payload.get(key)
            if not isinstance(value, str) or not value:
                return "Codex session identity is malformed"
            identity_count += 1
            if value not in candidates:
                candidates.append(value)
        if identity_count == 0:
            return "Codex session identity is malformed"
    if not candidates:
        return "Codex session has no canonical identity"
    if len(candidates) == 1:
        return None
    path_matches = [value for value in candidates if value in path.name]
    if len(path_matches) != 1:
        return "Codex session identity is ambiguous"
    return None


def codex_file_is_forked(source: str, records: list[dict[str, Any]]) -> bool:
    if source != "codex-sessions":
        return False
    for obj in records:
        if obj.get("type") != "session_meta":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("forked_from_id") or payload.get("parent_thread_id"):
            return True
        if payload.get("thread_source") == "subagent":
            return True
    return False


def session_reference(
    source: str,
    path: Path,
    obj: dict[str, Any],
    *,
    file_session_id: str | None = None,
) -> str:
    payload = obj.get("payload")
    values = (
        obj.get("sessionId"),
        obj.get("session_id"),
        payload.get("session_id") if isinstance(payload, dict) else None,
    )
    session_id = next((str(value) for value in values if value), file_session_id)
    family = source.split("-", 1)[0]
    if session_id:
        return f"{family}:{session_id}"
    return f"{source}:{path}"


def provenance_for(source: str, obj: dict[str, Any], body_kind: str) -> tuple[str, str]:
    if source == "claude-projects" and bool(obj.get("isCompactSummary")):
        return "continuation_summary", "derived"
    if source == "claude-projects" and (bool(obj.get("isMeta")) or bool(obj.get("sourceToolAssistantUUID"))):
        return "delegated_task_frame", "derived"
    if body_kind == "session_context":
        return "continuation_summary", "derived"
    if body_kind in {"flame_scaffold", "flame_with_task_body"}:
        return "delegated_task_frame", "derived"
    if bool(obj.get("isSidechain")):
        return "delegated_task_frame", "derived"
    if source == "claude-projects" and obj.get("type") == "assistant":
        return "delegated_task_frame", "derived"
    if source == "claude-projects" and obj.get("type") == "queue-operation":
        return "unknown_user_input", "unknown"
    if source == "claude-projects" and obj.get("type") == "last-prompt":
        return "unknown_user_input", "unknown"
    attachment = obj.get("attachment")
    if (
        source == "claude-projects"
        and obj.get("type") == "attachment"
        and isinstance(attachment, dict)
        and attachment.get("type") in {"goal_status", "queued_command"}
    ):
        return "unknown_user_input", "unknown"
    if (
        source == "claude-projects"
        and obj.get("type") == "attachment"
        and isinstance(attachment, dict)
        and attachment.get("type") == "hook_additional_context"
    ):
        return "delegated_task_frame", "derived"
    payload = obj.get("payload")
    if source == "codex-sessions" and isinstance(payload, dict):
        if obj.get("type") == "event_msg" and payload.get("type") == "user_message":
            return "transport_echo", "derived"
        if payload.get("type") == "message" and payload.get("role") == "user":
            return "operator_typed", "operator"
    if source == "codex-history":
        return "transport_echo", "derived"
    if source == "agy-cli-history":
        return "operator_typed", "operator"
    if source == "claude-tasks":
        return "delegated_task_frame", "derived"
    if source.startswith("claude") and not bool(obj.get("isSidechain")):
        return "operator_typed", "operator"
    return "unknown_user_input", "unknown"


def claude_assistant_prompt_fields(name: str) -> tuple[str, ...]:
    """Apply global prompt fields to every named tool, then add tool-specific fields."""

    return tuple(dict.fromkeys((*CLAUDE_ASSISTANT_PROMPT_FIELDS["*"], *CLAUDE_ASSISTANT_PROMPT_FIELDS.get(name, ()))))


def claude_exit_plan_allowed_prompts(tool_input: Any) -> list[str] | None:
    """Return only the exact, provider-emitted ExitPlanMode permission prompts."""

    if not isinstance(tool_input, dict) or tuple(sorted(tool_input)) != tuple(
        sorted(CLAUDE_EXIT_PLAN_ALLOWED_PROMPT_INPUT_KEYS)
    ):
        return None
    if not isinstance(tool_input.get("plan"), str) or not isinstance(tool_input.get("planFilePath"), str):
        return None
    allowed = tool_input.get("allowedPrompts")
    if not isinstance(allowed, list):
        return None
    prompts: list[str] = []
    for item in allowed:
        if (
            not isinstance(item, dict)
            or tuple(sorted(item)) != tuple(sorted(CLAUDE_EXIT_PLAN_ALLOWED_PROMPT_KEYS))
            or not isinstance(item.get("prompt"), str)
            or not item["prompt"].strip()
            or not isinstance(item.get("tool"), str)
            or not item["tool"].strip()
        ):
            return None
        prompts.append(str(item["prompt"]))
    return prompts


def claude_derived_tool_result_prompt(obj: dict[str, Any]) -> str | None:
    """Extract the exact delegated prompt echoed by a Claude subagent result."""

    marker = obj.get("sourceToolAssistantUUID")
    result = obj.get("toolUseResult")
    allowed_keysets = {tuple(sorted(keyset)) for keyset in CLAUDE_DERIVED_TOOL_RESULT_PROMPT_KEYSETS}
    if (
        not isinstance(marker, str)
        or not marker
        or not isinstance(result, dict)
        or tuple(sorted(result)) not in allowed_keysets
    ):
        return None
    for field in CLAUDE_DERIVED_TOOL_RESULT_TEXT_FIELDS:
        if field in result and not isinstance(result.get(field), str):
            return None
    for field in CLAUDE_DERIVED_TOOL_RESULT_INTEGER_FIELDS:
        if field in result and (isinstance(result.get(field), bool) or not isinstance(result.get(field), int)):
            return None
    for field in ("canReadOutputFile", "isAsync"):
        if field in result and not isinstance(result.get(field), bool):
            return None
    if "content" in result and not isinstance(result.get("content"), list):
        return None
    for field in ("toolStats", "usage"):
        if field in result and not isinstance(result.get(field), dict):
            return None
    prompt = result.get("prompt")
    return prompt if isinstance(prompt, str) and prompt.strip() else None


def claude_derived_tool_result_job_prompts(obj: dict[str, Any]) -> list[str] | None:
    """Extract prompts from the exact provider-emitted durable-job result envelope."""

    marker = obj.get("sourceToolAssistantUUID")
    result = obj.get("toolUseResult")
    if (
        not isinstance(marker, str)
        or not marker
        or not isinstance(result, dict)
        or set(result) != {"jobs"}
        or not isinstance(result.get("jobs"), list)
    ):
        return None
    prompts: list[str] = []
    for job in result["jobs"]:
        if (
            not isinstance(job, dict)
            or tuple(sorted(job)) != tuple(sorted(CLAUDE_DERIVED_TOOL_RESULT_JOB_KEYS))
            or any(not isinstance(job.get(field), str) for field in ("cron", "humanSchedule", "id", "prompt"))
            or any(not isinstance(job.get(field), bool) for field in ("durable", "recurring"))
            or not job["id"].strip()
            or not job["prompt"].strip()
        ):
            return None
        prompts.append(str(job["prompt"]))
    return prompts


def claude_attachment_prompt_texts(attachment: dict[str, Any]) -> list[str] | None:
    """Parse exact textual attachment envelopes; media remains an explicit gap."""

    attachment_type = attachment.get("type")
    if attachment_type == "goal_status":
        condition = attachment.get("condition")
        return [condition] if isinstance(condition, str) and condition.strip() else None
    if attachment_type not in {"hook_additional_context", "queued_command"}:
        return []
    field = "content" if attachment_type == "hook_additional_context" else "prompt"
    value = attachment.get(field)
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return None
    if attachment_type == "hook_additional_context":
        return (
            [item for item in value if isinstance(item, str) and item.strip()]
            if all(isinstance(item, str) for item in value)
            else None
        )
    texts: list[str] = []
    for block in value:
        if (
            not isinstance(block, dict)
            or set(block) != {"text", "type"}
            or block.get("type") != "text"
            or not isinstance(block.get("text"), str)
        ):
            return None
        if block["text"].strip():
            texts.append(str(block["text"]))
    return texts


def claude_assistant_prompt_texts(obj: dict[str, Any]) -> list[str]:
    message = obj.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    texts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = str(block.get("name") or "")
        tool_input = block.get("input")
        if not isinstance(tool_input, dict):
            continue
        fields = claude_assistant_prompt_fields(name)
        for field in fields:
            value = tool_input.get(field)
            if isinstance(value, str) and value.strip():
                texts.append(value)
        if name == "ExitPlanMode":
            nested = claude_exit_plan_allowed_prompts(tool_input)
            if nested is not None:
                texts.extend(nested)
    return texts


def claude_transport_candidate(obj: dict[str, Any]) -> bool:
    if obj.get("type") in {"last-prompt", "queue-operation"}:
        return True
    attachment = obj.get("attachment")
    return bool(
        obj.get("type") == "attachment"
        and isinstance(attachment, dict)
        and attachment.get("type") in {"goal_status", "queued_command"}
    )


def normalize_claude_file_events(source: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if source != "claude-projects":
        return events
    primary_hashes = {
        (str(event.get("session_ref") or ""), digest(str(event.get("text") or "")))
        for event in events
        if event.get("provenance") == "operator_typed" and not event.get("claude_transport_candidate")
    }
    for event in events:
        if not event.pop("claude_transport_candidate", False):
            continue
        candidate_key = (
            str(event.get("session_ref") or ""),
            digest(str(event.get("text") or "")),
        )
        if candidate_key in primary_hashes:
            event["provenance"] = "transport_echo"
            event["authority"] = "derived"
        elif event.get("provenance") != "delegated_task_frame":
            event["provenance"] = "unknown_user_input"
            event["authority"] = "unknown"
    return events


def prompt_texts_for(lifecycle: Any, source: str, obj: dict[str, Any]) -> list[str]:
    """Extract prompt surfaces without turning transport/tool output into people."""

    if source == "claude-projects" and obj.get("type") == "claude-remote-task-command":
        return lifecycle.text_from_content(obj.get("content"))
    if source == "claude-projects" and obj.get("type") == "attachment":
        attachment = obj.get("attachment")
        if isinstance(attachment, dict):
            texts = claude_attachment_prompt_texts(attachment)
            return texts or []
        return []
    if source == "claude-projects" and obj.get("type") == "assistant":
        return claude_assistant_prompt_texts(obj)
    if source == "claude-projects" and "type" not in obj:
        texts: list[str] = []

        def append_text(value: Any) -> None:
            if isinstance(value, str) and value.strip():
                texts.append(value)

        if "description" in obj and ("agentType" in obj or "toolUseId" in obj):
            append_text(obj.get("description"))
            return texts
        if any(field in obj for field in ("runId", "workflowName", "args", "phases", "workflowProgress")):
            append_text(obj.get("args"))
            phases = obj.get("phases")
            if isinstance(phases, list):
                for phase in phases:
                    if isinstance(phase, dict):
                        append_text(phase.get("title"))
                for phase in phases:
                    if isinstance(phase, dict):
                        append_text(phase.get("detail"))
            progress = obj.get("workflowProgress")
            if isinstance(progress, list):
                for item in progress:
                    if isinstance(item, dict):
                        append_text(item.get("promptPreview"))
            return texts
    if source.startswith("claude"):
        if source == "claude-tasks":
            return lifecycle.prompt_texts(source, obj)
        typ = obj.get("type")
        if typ == "last-prompt":
            return lifecycle.text_from_content(obj.get("lastPrompt"))
        if typ == "queue-operation":
            return lifecycle.text_from_content(obj.get("content")) + lifecycle.text_from_content(obj.get("prompt"))
        if typ == "user":
            message = obj.get("message")
            if not isinstance(message, dict) or message.get("role") not in (None, "user"):
                return []
            content = message.get("content")
            texts: list[str] = []
            if isinstance(content, str):
                if content.strip():
                    texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "text":
                        continue
                    texts.extend(lifecycle.text_from_content(block.get("text")))
            derived_prompt = claude_derived_tool_result_prompt(obj)
            if derived_prompt is not None:
                texts.append(derived_prompt)
            derived_job_prompts = claude_derived_tool_result_job_prompts(obj)
            if derived_job_prompts is not None:
                texts.extend(derived_job_prompts)
            return texts
    parser_source = "gemini-tmp-agy" if source == "gemini-tmp" else source
    return lifecycle.prompt_texts(parser_source, obj)


def strict_json_records(
    path: Path,
    *,
    limits: ResourceLimits | None = None,
    max_source_bytes: int | None = None,
    max_records: int | None = None,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Read one supported JSON source atomically or return a closed error.

    The lifecycle compatibility reader intentionally skips malformed rows.  A
    source cursor cannot: skipping a torn line and recording the file signature
    would permanently certify missing operator input.
    """

    active_limits = limits or runtime_limits({})
    byte_ceiling = max_source_bytes or active_limits.max_source_bytes_per_unit
    record_ceiling = max_records or active_limits.max_events_per_unit
    is_jsonl = path.suffix == ".jsonl" or path.name == "history.jsonl"
    if not is_jsonl and path.suffix != ".json":
        return [], None, False
    try:
        size = path.stat().st_size
        if size > byte_ceiling:
            return (
                [],
                f"{path}: source is {size} bytes; bounded ceiling is {byte_ceiling}",
                True,
            )
        if is_jsonl:
            rows: list[dict[str, Any]] = []
            with path.open(encoding="utf-8", errors="strict") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    if len(rows) >= record_ceiling:
                        return (
                            [],
                            f"{path}: record count exceeds bounded ceiling {record_ceiling}",
                            True,
                        )
                    try:
                        value = json.loads(line)
                    except (TypeError, ValueError) as exc:
                        return [], f"{path}:{line_number}: malformed JSON: {exc}", True
                    if not isinstance(value, dict):
                        return [], f"{path}:{line_number}: JSONL row is not an object", True
                    rows.append(value)
            return rows, None, True
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as exc:
        return [], f"{path}: unreadable JSON source: {exc}", True
    if isinstance(value, dict):
        return [value], None, True
    if isinstance(value, list) and all(isinstance(row, dict) for row in value):
        if len(value) > record_ceiling:
            return (
                [],
                f"{path}: record count exceeds bounded ceiling {record_ceiling}",
                True,
            )
        return list(value), None, True
    return [], f"{path}: JSON source is not an object or object array", True


def strict_codex_session_records(
    lifecycle: Any,
    path: Path,
    signature: dict[str, Any],
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Stream one canonical Codex rollout under its provider-specific ceilings.

    Non-prompt rows become empty positional sentinels after validation. This
    preserves exact event indexes without retaining large assistant/tool bodies
    in memory, while every user-bearing row is schema-checked before custody can
    advance.
    """

    rule = SOURCE_ADAPTER_RULES["codex-session-jsonl-v2"]
    max_probe_bytes = int(rule["max_probe_bytes"])
    max_record_bytes = int(rule["max_record_bytes"])
    max_records = int(rule["max_records"])
    expected_size = int(signature.get("size") or 0)
    if expected_size > max_probe_bytes:
        return [], f"{path}: Codex session exceeds bounded byte ceiling {max_probe_bytes}", True

    records: list[dict[str, Any]] = []
    bytes_read = 0
    try:
        with path.open("rb") as handle:
            while True:
                raw = handle.readline(max_record_bytes + 1)
                if not raw:
                    break
                bytes_read += len(raw)
                if len(raw) > max_record_bytes:
                    return [], f"{path}: Codex record exceeds bounded byte ceiling {max_record_bytes}", True
                if not raw.strip():
                    continue
                if len(records) >= max_records:
                    return [], f"{path}: Codex record count exceeds bounded ceiling {max_records}", True
                record_number = len(records) + 1
                try:
                    obj = json.loads(raw.decode("utf-8", errors="strict"))
                except (UnicodeError, ValueError, RecursionError) as exc:
                    return [], f"{path}:{record_number}: malformed JSON: {exc}", True
                if not isinstance(obj, dict):
                    return [], f"{path}:{record_number}: JSONL row is not an object", True
                schema_error = native_record_schema_error(
                    lifecycle,
                    "codex-sessions",
                    path,
                    [obj],
                    adapter_id="codex-session-jsonl-v2",
                    file_complete=False,
                )
                if schema_error:
                    detail = schema_error.split(":1: ", 1)[-1]
                    return [], f"{path}:{record_number}: {detail}", True
                keep = bool(obj.get("type") in {"compacted", "session_meta"} or contains_codex_user_marker(obj))
                records.append(obj if keep else {})
    except OSError as exc:
        return [], f"{path}: unreadable Codex session: {exc}", True

    if bytes_read != expected_size or file_signature(path) != signature:
        return [], f"{path}: Codex session changed during bounded read", True
    identity_error = codex_session_identity_error(path, records)
    if identity_error:
        return [], f"{path}: {identity_error}", True
    return records, None, True


def strict_native_records(
    lifecycle: Any,
    source: str,
    path: Path,
    signature: dict[str, Any],
    *,
    limits: ResourceLimits | None = None,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Read one native source through its exact, bounded adapter contract."""

    # Detached attachment bytes have no authority without a canonical parent
    # event.  Do not let a JSON-looking filename fall through to the generic
    # record parser and accidentally become prompt truth.
    if source == "codex-attachments":
        return [], None, False

    active_limits = limits or runtime_limits({})
    adapter_id = native_source_adapter_candidate_id(lifecycle, source, path)
    if adapter_id == "codex-session-jsonl-v2":
        return strict_codex_session_records(lifecycle, path, signature)
    if adapter_id == "claude-remote-task-command-v1":
        adapter_limit = int(SOURCE_ADAPTER_RULES[adapter_id]["max_probe_bytes"])
        try:
            size = path.stat().st_size
        except OSError as exc:
            return [], f"{path}: unreadable JSON source: {exc}", True
        if size > adapter_limit:
            return [], f"{path}: remote task metadata exceeds adapter ceiling {adapter_limit}", True
    source_schema = SOURCE_RECORD_SCHEMAS.get("claude-project-jsonl-v1", {})
    source_specific_limits = bool(source == "claude-projects" and path.suffix.lower() == ".jsonl")
    records, error, supported = strict_json_records(
        path,
        limits=active_limits,
        max_source_bytes=(int(source_schema["max_probe_bytes"]) if source_specific_limits else None),
        max_records=(int(source_schema["max_records"]) if source_specific_limits else None),
    )
    if error or not supported:
        return records, error, supported
    if adapter_id != "claude-remote-task-command-v1":
        return records, None, True
    rule = SOURCE_ADAPTER_RULES["claude-remote-task-command-v1"]
    expected_keys = set(rule["object_keys"])
    if len(records) != 1 or set(records[0]) != expected_keys:
        return [], f"{path}: remote task metadata does not match the bounded adapter schema", True
    record = records[0]
    for field, field_type in rule["field_types"].items():
        value = record.get(field)
        if field_type == "nonempty-string" and (not isinstance(value, str) or not value.strip()):
            return [], f"{path}: remote task {field} must be non-empty text", True
        if field_type == "nonnegative-integer" and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            return [], f"{path}: remote task {field} must be a non-negative integer", True
    command = record[rule["text_field"]]
    return (
        [
            {
                "type": rule["event_type"],
                "id": next(record[field] for field in rule["event_id_fields"] if record.get(field)),
                "sessionId": record[rule["session_field"]],
                "timestamp": record[rule["timestamp_field"]],
                "content": command,
                "isSidechain": True,
            }
        ],
        None,
        True,
    )


def contains_codex_user_marker(value: Any) -> bool:
    """Conservatively detect user-bearing shapes outside the two exact adapters."""

    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            marker_type = current.get("type")
            if current.get("role") == "user" or (
                isinstance(marker_type, str) and marker_type.startswith("user_message")
            ):
                return True
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return False


def unhandled_prompt_field(
    value: Any,
    *,
    handled: set[tuple[int, str]],
    opaque_subtrees: set[int] | None = None,
) -> str | None:
    """Find a prompt-named field outside an explicitly extracted schema path."""

    opaque = opaque_subtrees or set()
    pending = [value]
    while pending:
        current = pending.pop()
        if id(current) in opaque:
            continue
        if isinstance(current, dict):
            for key, item in current.items():
                if key in CLAUDE_UNEXPECTED_PROMPT_FIELDS and (id(current), key) not in handled:
                    return str(key)
                pending.append(item)
        elif isinstance(current, list):
            pending.extend(current)
    return None


def _codex_turn_metadata_valid(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"turn_id"}
        and isinstance(value.get("turn_id"), str)
        and value.get("turn_id")
    )


def codex_image_block_schema_error(block: dict[str, Any]) -> str | None:
    if tuple(sorted(block)) != CODEX_USER_CONTENT_BLOCK_KEYSETS["input_image"]:
        return "unknown Codex input-image schema"
    if block.get("detail") != "high":
        return "unknown Codex input-image detail schema"
    image_url = block.get("image_url")
    prefix = "data:image/png;base64,"
    if not isinstance(image_url, str) or not image_url.startswith(prefix) or len(image_url) == len(prefix):
        return "unknown Codex input-image data schema"
    max_media_bytes = int(SOURCE_ADAPTER_RULES["codex-session-jsonl-v2"]["max_media_bytes"])
    max_encoded_bytes = ((max_media_bytes + 2) // 3) * 4
    if len(image_url) - len(prefix) > max_encoded_bytes:
        return f"Codex input image exceeds bounded byte ceiling {max_media_bytes}"
    return None


def codex_event_text_elements_error(payload: dict[str, Any]) -> str | None:
    message = payload.get("message")
    elements = payload.get("text_elements")
    if not isinstance(message, str) or not isinstance(elements, list):
        return "unknown Codex event text-element schema"
    message_bytes = message.encode("utf-8")
    previous_end = 0
    for element in elements:
        byte_range = element.get("byte_range") if isinstance(element, dict) else None
        if (
            not isinstance(element, dict)
            or tuple(sorted(element)) != CODEX_TEXT_ELEMENT_KEYS
            or not isinstance(element.get("placeholder"), str)
            or not isinstance(byte_range, dict)
            or tuple(sorted(byte_range)) != CODEX_BYTE_RANGE_KEYS
            or any(
                isinstance(byte_range.get(field), bool) or not isinstance(byte_range.get(field), int)
                for field in CODEX_BYTE_RANGE_KEYS
            )
        ):
            return "unknown Codex event text-element schema"
        start = int(byte_range["start"])
        end = int(byte_range["end"])
        if start < previous_end or end < start or end > len(message_bytes):
            return "invalid Codex event text-element range"
        try:
            exact_placeholder = message_bytes[start:end].decode("utf-8", errors="strict")
        except UnicodeError:
            return "invalid Codex event text-element range"
        if exact_placeholder != element["placeholder"]:
            return "Codex event text-element does not match message bytes"
        previous_end = end
    return None


def codex_compacted_schema_error(record: dict[str, Any]) -> str | None:
    payload = record.get("payload")
    if not isinstance(payload, dict) or tuple(sorted(payload)) not in CODEX_COMPACTED_PAYLOAD_KEYSETS:
        return "unknown Codex compacted payload schema"
    if payload.get("message") != "":
        return "Codex compacted message must be the exact empty transport field"

    payload_keys = tuple(sorted(payload))
    if len(payload_keys) == 6:
        uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        if any(
            not isinstance(payload.get(field), str) or re.fullmatch(uuid_pattern, str(payload[field])) is None
            for field in ("first_window_id", "previous_window_id", "window_id")
        ):
            return "unknown Codex compacted window identity schema"
        window_number = payload.get("window_number")
        if isinstance(window_number, bool) or not isinstance(window_number, int) or window_number < 0:
            return "unknown Codex compacted window number schema"
    elif "window_id" in payload:
        window_id = payload.get("window_id")
        if isinstance(window_id, bool) or not isinstance(window_id, int) or window_id < 0:
            return "unknown Codex compacted legacy window schema"

    history = payload.get("replacement_history")
    maximum = int(SOURCE_ADAPTER_RULES["codex-session-jsonl-v2"]["max_compacted_history_items"])
    if not isinstance(history, list) or not history or len(history) > maximum:
        return f"Codex compacted history exceeds bounded item ceiling {maximum}"
    compaction_items = 0
    allowed_messages = set(CODEX_COMPACTED_MESSAGE_KEYSETS)
    allowed_compactions = set(CODEX_COMPACTION_ITEM_KEYSETS)
    for item in history:
        if not isinstance(item, dict):
            return "unknown Codex compacted history item schema"
        item_type = item.get("type")
        if item_type == "message":
            if tuple(sorted(item)) not in allowed_messages or item.get("role") not in {"user", "developer"}:
                return "unknown Codex compacted message schema"
            metadata = item.get("internal_chat_message_metadata_passthrough")
            if metadata is not None and not _codex_turn_metadata_valid(metadata):
                return "unknown Codex compacted message metadata schema"
            content = item.get("content")
            if not isinstance(content, list):
                return "unknown Codex compacted message content schema"
            for block in content:
                if not isinstance(block, dict):
                    return "unknown Codex compacted content block schema"
                block_type = block.get("type")
                expected_keys = CODEX_USER_CONTENT_BLOCK_KEYSETS.get(str(block_type))
                if expected_keys is None or tuple(sorted(block)) != expected_keys:
                    return "Codex compacted content requires an explicit adapter"
                if block_type == "input_text":
                    if not isinstance(block.get("text"), str):
                        return "unknown Codex compacted input-text schema"
                    continue
                if item.get("role") != "user":
                    return "Codex compacted developer media requires an explicit adapter"
                image_error = codex_image_block_schema_error(block)
                if image_error:
                    return image_error
            continue
        if item_type == "compaction":
            compaction_items += 1
            if tuple(sorted(item)) not in allowed_compactions:
                return "unknown Codex compaction item schema"
            if not isinstance(item.get("encrypted_content"), str) or not item.get("encrypted_content"):
                return "unknown Codex encrypted compaction schema"
            if "id" in item and (not isinstance(item.get("id"), str) or not item.get("id")):
                return "unknown Codex compaction identity schema"
            for field in ("metadata", "internal_chat_message_metadata_passthrough"):
                if field in item and not _codex_turn_metadata_valid(item.get(field)):
                    return "unknown Codex compaction metadata schema"
            continue
        return "unknown Codex compacted history item type"
    if compaction_items != 1:
        return "Codex compacted history must contain exactly one compaction item"
    return None


def codex_media_pairing_error(records: list[dict[str, Any]]) -> str | None:
    """Bind local-image transport references to one nearby canonical data image turn."""

    primaries: list[tuple[int, tuple[str, ...], int]] = []
    for index, record in enumerate(records):
        payload = record.get("payload")
        if not (
            record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "message"
            and payload.get("role") == "user"
        ):
            continue
        content = payload.get("content")
        if not isinstance(content, list):
            continue
        texts = tuple(
            str(block["text"])
            for block in content
            if isinstance(block, dict) and block.get("type") == "input_text" and isinstance(block.get("text"), str)
        )
        media_count = sum(1 for block in content if isinstance(block, dict) and block.get("type") == "input_image")
        if media_count:
            primaries.append((index, texts, media_count))

    paired: Counter[int] = Counter()
    for index, record in enumerate(records):
        payload = record.get("payload")
        if not (
            record.get("type") == "event_msg" and isinstance(payload, dict) and payload.get("type") == "user_message"
        ):
            continue
        local_images = payload.get("local_images")
        if not isinstance(local_images, list) or not local_images:
            continue
        for locator in local_images:
            if not isinstance(locator, str) or not locator or "\x00" in locator:
                return "Codex user-media transport locator is malformed"
            candidate = Path(locator)
            if (
                not candidate.is_absolute()
                or ".." in candidate.parts
                or str(candidate.expanduser().absolute()) != locator
            ):
                return "Codex user-media transport locator is not canonical"
        elements = payload.get("text_elements")
        if not isinstance(elements, list):
            return "Codex user-media transport has malformed text elements"
        image_placeholders = [
            element
            for element in elements
            if isinstance(element, dict)
            and re.fullmatch(r"\[Image #[1-9][0-9]*\]", str(element.get("placeholder") or ""))
        ]
        if len(image_placeholders) != len(local_images):
            return "Codex user-media transport cardinality does not match image placeholders"
        message = payload.get("message")
        candidates = [
            primary
            for primary in primaries
            if primary[0] < index
            and index - primary[0] <= 2
            and isinstance(message, str)
            and message in primary[1]
            and primary[2] == len(local_images)
        ]
        if not candidates:
            return "Codex user media has no exact canonical primary binding"
        primary = max(candidates, key=lambda item: item[0])
        paired[primary[0]] += 1
    if any(paired[index] != 1 for index, _texts, _count in primaries):
        return "Codex primary user media does not have exactly one transport binding"
    return None


def native_record_schema_error(
    lifecycle: Any,
    source: str,
    path: Path,
    records: list[dict[str, Any]],
    *,
    adapter_id: str | None,
    file_complete: bool = True,
) -> str | None:
    """Reject structurally unknown Claude containers before advancing a cursor."""

    if adapter_id == "claude-remote-task-command-v1":
        return None
    relative = source_relative_path(lifecycle, source, path)
    if source == "codex-sessions":
        for index, record in enumerate(records):
            payload = record.get("payload")
            is_response_user = bool(
                record.get("type") == "response_item"
                and isinstance(payload, dict)
                and payload.get("type") == "message"
                and payload.get("role") == "user"
            )
            is_event_user = bool(
                record.get("type") == "event_msg"
                and isinstance(payload, dict)
                and payload.get("type") == "user_message"
            )
            is_compacted = record.get("type") == "compacted"
            if contains_codex_user_marker(record) and not (is_response_user or is_event_user or is_compacted):
                return f"{path}:{index + 1}: unknown Codex user-bearing record schema"
            if is_compacted:
                if tuple(sorted(record)) != CODEX_USER_RECORD_KEYS or not isinstance(record.get("timestamp"), str):
                    return f"{path}:{index + 1}: unknown Codex compacted record envelope"
                compacted_error = codex_compacted_schema_error(record)
                if compacted_error:
                    return f"{path}:{index + 1}: {compacted_error}"
                continue
            if not isinstance(payload, dict):
                continue
            has_user_role = payload.get("role") == "user"
            has_user_message_type = payload.get("type") == "user_message"
            if has_user_role or has_user_message_type:
                if tuple(sorted(record)) != CODEX_USER_RECORD_KEYS or not isinstance(record.get("timestamp"), str):
                    return f"{path}:{index + 1}: unknown Codex user record envelope"
                if has_user_role and record.get("type") != "response_item":
                    return f"{path}:{index + 1}: unknown Codex response user record type"
                if has_user_message_type and record.get("type") != "event_msg":
                    return f"{path}:{index + 1}: unknown Codex event user record type"
            if is_response_user:
                if (
                    payload.get("type") != "message"
                    or tuple(sorted(payload)) not in CODEX_RESPONSE_USER_PAYLOAD_KEYSETS
                ):
                    return f"{path}:{index + 1}: unknown Codex response user-message schema"
                metadata = payload.get("internal_chat_message_metadata_passthrough")
                if metadata is not None and (
                    not isinstance(metadata, dict)
                    or set(metadata) != {"turn_id"}
                    or not isinstance(metadata.get("turn_id"), str)
                ):
                    return f"{path}:{index + 1}: unknown Codex response user-message metadata schema"
                content = payload.get("content")
                if not isinstance(content, list):
                    return f"{path}:{index + 1}: unknown Codex response user-content schema"
                for block in content:
                    if not isinstance(block, dict):
                        return f"{path}:{index + 1}: unknown Codex response user-content schema"
                    block_type = block.get("type")
                    expected_keys = CODEX_USER_CONTENT_BLOCK_KEYSETS.get(str(block_type))
                    if expected_keys is None or tuple(sorted(block)) != expected_keys:
                        return f"{path}:{index + 1}: Codex user content requires an explicit content adapter"
                    if block_type == "input_image":
                        image_error = codex_image_block_schema_error(block)
                        if image_error:
                            return f"{path}:{index + 1}: {image_error}"
                        continue
                    if not isinstance(block.get("text"), str):
                        return f"{path}:{index + 1}: unknown Codex input-text schema"
                continue
            if is_event_user:
                if tuple(sorted(payload)) not in CODEX_EVENT_USER_PAYLOAD_KEYSETS:
                    return f"{path}:{index + 1}: unknown Codex event user-message schema"
                if not isinstance(payload.get("message"), str):
                    return f"{path}:{index + 1}: unknown Codex event user-message text schema"
                for media_field in ("images", "local_images"):
                    media = payload.get(media_field, [])
                    if media is not None and not isinstance(media, list):
                        return f"{path}:{index + 1}: unknown Codex event user-media schema"
                    if media_field == "images" and media:
                        return f"{path}:{index + 1}: Codex user media requires an explicit content adapter"
                    if (
                        media_field == "local_images"
                        and media
                        and not all(isinstance(value, str) and value for value in media)
                    ):
                        return f"{path}:{index + 1}: unknown Codex event local-image schema"
                elements_error = codex_event_text_elements_error(payload)
                if elements_error:
                    return f"{path}:{index + 1}: {elements_error}"
        pairing_error = codex_media_pairing_error(records) if file_complete else None
        return f"{path}: {pairing_error}" if pairing_error else None
    if source == "codex-history":
        allowed = set(CODEX_HISTORY_KEYSETS)
        for index, record in enumerate(records):
            if tuple(sorted(record)) not in allowed or not isinstance(record.get("text"), str):
                return f"{path}:{index + 1}: unknown Codex history schema"
        return None
    if source == "agy-cli-history":
        allowed = set(AGY_HISTORY_KEYSETS)
        for index, record in enumerate(records):
            if tuple(sorted(record)) not in allowed or not isinstance(record.get("display"), str):
                return f"{path}:{index + 1}: unknown Agy history schema"
        return None
    if source in {"gemini-tmp", "gemini-tmp-agy"}:
        user_keysets = set(GEMINI_USER_RECORD_KEYSETS)
        content_keysets = set(GEMINI_CONTENT_BLOCK_KEYSETS)
        set_keysets = set(GEMINI_SET_KEYSETS)
        nonuser_keysets = set(GEMINI_NONUSER_RECORD_KEYSETS)

        def gemini_user_valid(value: Any) -> bool:
            if not isinstance(value, dict) or tuple(sorted(value)) not in user_keysets or value.get("type") != "user":
                return False
            content = value.get("content")
            if not isinstance(content, list):
                return False
            for block in content:
                if not isinstance(block, dict) or tuple(sorted(block)) not in content_keysets:
                    return False
                if "text" in block and not isinstance(block.get("text"), str):
                    return False
                if "functionResponse" in block and not isinstance(block.get("functionResponse"), dict):
                    return False
            return True

        for index, record in enumerate(records):
            if record.get("type") == "user":
                if not gemini_user_valid(record):
                    return f"{path}:{index + 1}: unknown Gemini user-message schema"
                continue
            set_obj = record.get("$set")
            if set_obj is not None:
                if (
                    set(record) != {"$set"}
                    or not isinstance(set_obj, dict)
                    or tuple(sorted(set_obj)) not in set_keysets
                ):
                    return f"{path}:{index + 1}: unknown Gemini update schema"
                messages = set_obj.get("messages")
                if messages is not None and (
                    not isinstance(messages, list) or not all(gemini_user_valid(message) for message in messages)
                ):
                    return f"{path}:{index + 1}: unknown Gemini update message schema"
                continue
            if tuple(sorted(record)) not in nonuser_keysets:
                return f"{path}:{index + 1}: unknown Gemini chat record schema"
            if "type" in record and record.get("type") != "gemini":
                return f"{path}:{index + 1}: unknown Gemini non-user role"
        return None
    if source == "claude-projects":
        if relative is None:
            return f"{path}: source is outside the canonical Claude projects root"
        if path.suffix.lower() == ".jsonl":
            allowed_types = set(CLAUDE_PROJECT_JSONL_TYPES)

            def content_valid(content: Any) -> bool:
                if isinstance(content, str):
                    return True
                if not isinstance(content, list):
                    return False
                for block in content:
                    if not isinstance(block, dict) or block.get("type") not in CLAUDE_USER_CONTENT_BLOCK_TYPES:
                        return False
                    block_type = str(block.get("type") or "")
                    expected_keysets = CLAUDE_USER_CONTENT_BLOCK_KEYSETS.get(block_type, ())
                    if tuple(sorted(block)) not in expected_keysets:
                        return False
                    if block_type in {"document", "image"}:
                        return False
                    if block_type == "text" and not isinstance(block.get("text"), str):
                        return False
                    if block_type == "tool_result" and (
                        not isinstance(block.get("tool_use_id"), str)
                        or ("is_error" in block and not isinstance(block.get("is_error"), bool))
                    ):
                        return False
                return True

            for index, record in enumerate(records):
                handled_prompt_fields: set[tuple[int, str]] = set()
                opaque_prompt_subtrees: set[int] = set()
                record_type = record.get("type")
                if record_type not in allowed_types:
                    return f"{path}:{index + 1}: unknown Claude project JSONL record schema"
                if record_type == "user":
                    message = record.get("message")
                    message_content = message.get("content") if isinstance(message, dict) else None
                    if isinstance(message_content, list) and any(
                        isinstance(block, dict) and block.get("type") in {"document", "image"}
                        for block in message_content
                    ):
                        return f"{path}:{index + 1}: Claude user media requires an explicit content adapter"
                    if (
                        not isinstance(message, dict)
                        or set(message) != {"content", "role"}
                        or message.get("role") != "user"
                        or not content_valid(message.get("content"))
                    ):
                        return f"{path}:{index + 1}: unknown Claude user-message schema"
                    content = message.get("content")
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_result":
                                opaque_prompt_subtrees.add(id(block.get("content")))
                    tool_result = record.get("toolUseResult")
                    if isinstance(tool_result, dict) and "prompt" in tool_result:
                        if claude_derived_tool_result_prompt(record) is None:
                            return f"{path}:{index + 1}: unknown Claude derived tool-result prompt schema"
                        handled_prompt_fields.add((id(tool_result), "prompt"))
                        for field in ("content", "toolStats", "usage"):
                            if field in tool_result:
                                opaque_prompt_subtrees.add(id(tool_result.get(field)))
                    if isinstance(tool_result, dict) and "jobs" in tool_result:
                        if claude_derived_tool_result_job_prompts(record) is None:
                            return f"{path}:{index + 1}: unknown Claude derived tool-result jobs schema"
                        for job in tool_result["jobs"]:
                            handled_prompt_fields.add((id(job), "prompt"))
                if record_type == "assistant":
                    message = record.get("message")
                    content = message.get("content") if isinstance(message, dict) else None
                    if (
                        not isinstance(message, dict)
                        or message.get("role") != "assistant"
                        or not isinstance(content, list)
                    ):
                        return f"{path}:{index + 1}: unknown Claude assistant-message schema"
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") not in CLAUDE_ASSISTANT_CONTENT_BLOCK_TYPES:
                            return f"{path}:{index + 1}: unknown Claude assistant-content schema"
                        if block.get("type") != "tool_use":
                            continue
                        name = block.get("name")
                        tool_input = block.get("input")
                        if not isinstance(name, str) or not isinstance(tool_input, dict):
                            return f"{path}:{index + 1}: unknown Claude assistant tool-use schema"
                        fields = claude_assistant_prompt_fields(name)
                        if any(field in tool_input and not isinstance(tool_input.get(field), str) for field in fields):
                            return f"{path}:{index + 1}: unknown Claude assistant prompt-field schema"
                        handled_prompt_fields.update((id(tool_input), field) for field in fields if field in tool_input)
                        if "allowedPrompts" in tool_input:
                            allowed_prompts = claude_exit_plan_allowed_prompts(tool_input)
                            if name != "ExitPlanMode" or allowed_prompts is None:
                                return f"{path}:{index + 1}: unknown Claude allowed-prompts schema"
                            for item in tool_input["allowedPrompts"]:
                                handled_prompt_fields.add((id(item), "prompt"))
                if record_type == "attachment":
                    attachment = record.get("attachment")
                    if not isinstance(attachment, dict) or attachment.get("type") not in CLAUDE_ATTACHMENT_TYPES:
                        return f"{path}:{index + 1}: unknown Claude attachment schema"
                    attachment_type = str(attachment.get("type") or "")
                    prompt_fields = CLAUDE_ATTACHMENT_PROMPT_FIELDS.get(attachment_type, ())
                    handled_prompt_fields.update(
                        (id(attachment), field) for field in prompt_fields if field in attachment
                    )
                    if any(
                        field in attachment and field not in prompt_fields for field in CLAUDE_UNEXPECTED_PROMPT_FIELDS
                    ):
                        return f"{path}:{index + 1}: unknown Claude attachment prompt-carrier schema"
                    if prompt_fields and claude_attachment_prompt_texts(attachment) is None:
                        if attachment_type == "queued_command" and isinstance(attachment.get("prompt"), list):
                            return (
                                f"{path}:{index + 1}: Claude queued-command media requires an explicit content adapter"
                            )
                        return f"{path}:{index + 1}: unknown Claude attachment prompt-field schema"
                    if attachment.get("type") == "goal_status" and (
                        set(attachment) - set(CLAUDE_GOAL_STATUS_KEYS)
                        or not isinstance(attachment.get("condition"), str)
                    ):
                        return f"{path}:{index + 1}: unknown Claude goal-status schema"
                if record_type == "queue-operation":
                    if record.get("operation") not in CLAUDE_QUEUE_OPERATIONS:
                        return f"{path}:{index + 1}: unknown Claude queue-operation schema"
                    if any(
                        field in record and not isinstance(record.get(field), str) for field in ("content", "prompt")
                    ):
                        return f"{path}:{index + 1}: unknown Claude queued prompt schema"
                    if "prompt" in record:
                        handled_prompt_fields.add((id(record), "prompt"))
                if record_type == "last-prompt":
                    allowed_keysets = {
                        frozenset(("lastPrompt", "leafUuid", "sessionId", "type")),
                        frozenset(("leafUuid", "sessionId", "type")),
                    }
                    if frozenset(record) not in allowed_keysets or (
                        "lastPrompt" in record and not isinstance(record.get("lastPrompt"), str)
                    ):
                        return f"{path}:{index + 1}: unknown Claude last-prompt schema"
                hidden_prompt = unhandled_prompt_field(
                    record,
                    handled=handled_prompt_fields,
                    opaque_subtrees=opaque_prompt_subtrees,
                )
                if hidden_prompt:
                    return f"{path}:{index + 1}: unknown Claude nested prompt carrier {hidden_prompt}"
            return None
        if path.suffix.lower() != ".json":
            return None
        role_parts = set(relative.parts[2:])
        if "subagents" in role_parts:
            allowed_keys = set(CLAUDE_SUBAGENT_METADATA_KEYS)
            required_any = {"agentType", "toolUseId"}
            schema_name = "Claude subagent metadata"
        elif "workflows" in role_parts:
            allowed_keys = set(CLAUDE_WORKFLOW_METADATA_KEYS)
            required_any = {"agentType", "runId"}
            schema_name = "Claude workflow metadata"
        else:
            return f"{path}: unknown Claude project JSON container schema"
        for index, record in enumerate(records):
            keys = set(record)
            if not keys <= allowed_keys or not keys & required_any:
                return f"{path}:{index + 1}: unknown {schema_name} schema"
            if "description" in record and not isinstance(record.get("description"), str):
                return f"{path}:{index + 1}: unknown {schema_name} description schema"
            if "args" in record and not isinstance(record.get("args"), str):
                return f"{path}:{index + 1}: unknown {schema_name} arguments schema"
            for field, prompt_fields, nested_keys in (
                ("phases", ("title", "detail"), set(CLAUDE_WORKFLOW_PHASE_KEYS)),
                (
                    "workflowProgress",
                    ("promptPreview",),
                    set(CLAUDE_WORKFLOW_PROGRESS_KEYS),
                ),
            ):
                value = record.get(field)
                if value is None:
                    continue
                if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                    return f"{path}:{index + 1}: unknown {schema_name} {field} schema"
                if any(set(item) - nested_keys for item in value):
                    return f"{path}:{index + 1}: unknown {schema_name} {field} keys"
                if any(
                    prompt_field in item and not isinstance(item.get(prompt_field), str)
                    for item in value
                    for prompt_field in prompt_fields
                ):
                    return f"{path}:{index + 1}: unknown {schema_name} {field} prompt schema"
        return None
    if source == "claude-tasks" and path.suffix.lower() == ".json":
        allowed_keysets = {frozenset(keyset) for keyset in CLAUDE_TASK_KEYSETS}
        for index, record in enumerate(records):
            if frozenset(record) not in allowed_keysets:
                return f"{path}:{index + 1}: unknown Claude task record schema"
            if not isinstance(record.get("description"), str):
                return f"{path}:{index + 1}: unknown Claude task description schema"
    return None


def source_path_error(
    path: Path,
    *,
    containment_root: Path | None = None,
    source: str = "",
) -> str | None:
    """Contain one source and admit only its explicitly typed alias contract."""

    lexical_root = containment_root or path.parent
    return inspect_source_path_custody(
        source,
        path,
        lexical_root,
        isolated_home=SOURCE_HOME_OVERRIDE,
    ).error


def _discover_candidate(
    rows: DiscoveredRows,
    *,
    source: str,
    path: Path,
    containment_root: Path,
    cutoff: float | None,
    limit: int,
    known_paths: set[str],
) -> bool:
    """Add one eligible source or return False when discovery reached its cap."""

    custody = inspect_source_path_custody(
        source,
        path,
        containment_root,
        isolated_home=SOURCE_HOME_OVERRIDE,
    )
    if custody.error is not None:
        rows.discovery_errors.append((source, f"{source}:{path}: {custody.error}"))
        if source == "claude-projects" and custody.blocker_reason in SOURCE_ALIAS_BLOCKER_REASONS:
            rows.source_alias_blocker_counts[str(custody.blocker_reason)] += 1
        return True
    try:
        if custody.alias_contract_id == CLAUDE_SUBAGENT_SESSION_ALIAS_ID and path.is_dir():
            return True
        if custody.alias_contract_id is None and not path.is_file():
            return True
        source_mtime = (
            int((custody.related_signatures or {}).get("memory_target", {}).get("mtime_ns") or 0) / 1_000_000_000
            if custody.alias_contract_id == CLAUDE_PROJECT_MEMORY_ALIAS_ID
            else path.stat().st_mtime
        )
    except OSError:
        return True
    if rows.discovered_count >= limit:
        rows.truncated_source = source
        return False
    rows.discovered_count += 1
    if cutoff is not None and source_mtime < cutoff:
        return True
    path_key = str(path)
    if path_key in known_paths:
        return True
    known_paths.add(path_key)
    rows.append({"source": source, "path": path, "mtime": source_mtime})
    return True


def generic_gemini_rows(
    lifecycle: Any,
    days: int | None,
    *,
    limits: ResourceLimits | None = None,
) -> DiscoveredRows:
    """Discover Gemini CLI chats with a hard cardinality and symlink boundary."""

    active_limits = limits or runtime_limits({})
    rows = DiscoveredRows()
    home = getattr(lifecycle, "HOME", None)
    if home is None:
        return rows
    root = Path(home) / ".gemini" / "tmp"
    if not root.exists():
        return rows
    cutoff = None if days is None else dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400
    known_paths: set[str] = set()
    for path in root.rglob("chats/*.jsonl"):
        if not _discover_candidate(
            rows,
            source="gemini-tmp",
            path=path,
            containment_root=root,
            cutoff=cutoff,
            limit=active_limits.max_discovery_units,
            known_paths=known_paths,
        ):
            break
    return rows


def regular_source_rows(
    lifecycle: Any,
    days: int | None,
    *,
    limits: ResourceLimits | None = None,
) -> DiscoveredRows:
    """Discover regular source files lazily under a hard cardinality ceiling."""

    active_limits = limits or runtime_limits({})
    rows = DiscoveredRows()
    cutoff = None if days is None else dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400
    known_paths: set[str] = set()
    stop = False
    for item in getattr(lifecycle, "LOCAL_SOURCES", ()):
        if not isinstance(item, (tuple, list)) or len(item) < 3:
            continue
        source, root, patterns = str(item[0]), Path(item[1]), item[2]
        if not root.exists():
            continue
        candidates = (root,) if root.is_file() else (path for pattern in patterns for path in root.rglob(str(pattern)))
        for path in candidates:
            if not _discover_candidate(
                rows,
                source=source,
                path=path,
                containment_root=root,
                cutoff=cutoff,
                limit=active_limits.max_discovery_units,
                known_paths=known_paths,
            ):
                stop = True
                break
        if stop:
            break
    if not stop:
        generic = generic_gemini_rows(lifecycle, days, limits=active_limits)
        for source, error in generic.discovery_errors:
            rows.discovery_errors.append((source, error))
        rows.source_alias_blocker_counts.update(generic.source_alias_blocker_counts)
        for row in generic:
            if not _discover_candidate(
                rows,
                source=str(row["source"]),
                path=Path(row["path"]),
                containment_root=Path(lifecycle.HOME) / ".gemini" / "tmp",
                cutoff=cutoff,
                limit=active_limits.max_discovery_units,
                known_paths=known_paths,
            ):
                stop = True
                break
        if generic.truncated_source and not stop:
            rows.truncated_source = generic.truncated_source
            stop = True
    if stop and rows.truncated_source is None:
        rows.truncated_source = "unknown"
    # Canonical prompt surfaces precede their transport indexes.  This ordering
    # is provenance, not recency policy, and prevents a bounded first drain from
    # materializing an echo before its primary source.
    source_rank = {
        "codex-sessions": 0,
        "claude-projects": 0,
        "gemini-tmp": 0,
        "gemini-tmp-agy": 0,
        "codex-history": 2,
        "claude-tasks": 2,
    }
    rows[:] = sorted(
        rows,
        key=lambda row: (
            source_rank.get(str(row.get("source") or ""), 1),
            str(row.get("mtime") or ""),
            str(row.get("source") or ""),
            str(row.get("path") or ""),
        ),
    )
    return rows


def source_discovery_spec(lifecycle: Any) -> dict[str, Any]:
    """Persist the exact private discovery roots needed to revalidate exact-all custody."""

    regular = []
    for item in getattr(lifecycle, "LOCAL_SOURCES", ()):
        if not isinstance(item, (tuple, list)) or len(item) < 3:
            continue
        patterns = item[2]
        if not isinstance(patterns, (tuple, list)):
            continue
        regular.append(
            {
                "source": str(item[0]),
                "root": str(Path(item[1]).expanduser().absolute()),
                "patterns": [str(pattern) for pattern in patterns],
            }
        )
    home = getattr(lifecycle, "HOME", None)
    opencode_db = Path(getattr(lifecycle, "OPENCODE_DB", "/definitely/missing/opencode.db"))
    agy_root = Path(getattr(lifecycle, "AGY_CLI_CONVERSATIONS", "/definitely/missing/agy"))
    return {
        "version": 1,
        "regular": regular,
        "gemini_root": str((Path(home) / ".gemini" / "tmp").absolute()) if home is not None else None,
        "opencode_db": str(opencode_db.expanduser().absolute()),
        "agy_conversations_root": str(agy_root.expanduser().absolute()),
    }


def source_family_container_available(lifecycle: Any, source: str) -> bool:
    if source == "opencode-db":
        return Path(lifecycle.OPENCODE_DB).exists()
    if source == "agy-cli-conversations":
        return Path(lifecycle.AGY_CLI_CONVERSATIONS).exists()
    if source == "gemini-tmp" and getattr(lifecycle, "HOME", None) is not None:
        return (Path(lifecycle.HOME) / ".gemini" / "tmp").exists()
    return any(
        isinstance(item, (tuple, list)) and len(item) >= 2 and str(item[0]) == source and Path(item[1]).exists()
        for item in getattr(lifecycle, "LOCAL_SOURCES", ())
    )


def existing_regular_families(lifecycle: Any) -> set[str]:
    families: set[str] = set()
    for item in getattr(lifecycle, "LOCAL_SOURCES", ()):
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            continue
        source, root = str(item[0]), Path(item[1])
        if root.exists():
            families.add(source)
    home = getattr(lifecycle, "HOME", None)
    if home is not None and (Path(home) / ".gemini" / "tmp").exists():
        families.add("gemini-tmp")
    return families


def primary_before_echo(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make matching transport echoes order-independent within a scan batch."""

    primary: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    positions = {id(event): index for index, event in enumerate(events)}
    for event in events:
        if event.get("authority") == "operator":
            primary[(str(event.get("session_ref")), digest(str(event.get("text") or "")))].append(event)
    for event in events:
        if event.get("provenance") != "transport_echo":
            continue
        candidates = primary.get((str(event.get("session_ref")), digest(str(event.get("text") or "")))) or []
        if len(candidates) == 1:
            event["timestamp"] = candidates[0].get("timestamp")
    group_start: dict[tuple[str, str], int] = {}
    for event in events:
        key = (str(event.get("session_ref")), digest(str(event.get("text") or "")))
        if key not in primary:
            continue
        group_start[key] = min(group_start.get(key, positions[id(event)]), positions[id(event)])

    def order_key(event: dict[str, Any]) -> tuple[int, int, int]:
        key = (str(event.get("session_ref")), digest(str(event.get("text") or "")))
        original = positions[id(event)]
        return (
            group_start.get(key, original),
            1 if event.get("provenance") == "transport_echo" else 0,
            original,
        )

    return sorted(
        events,
        key=order_key,
    )


def normalize_codex_file_events(
    source: str,
    events: list[dict[str, Any]],
    *,
    forked: bool,
) -> list[dict[str, Any]]:
    if source != "codex-sessions":
        return events
    echo_hashes = {
        digest(str(event.get("text") or "")) for event in events if event.get("provenance") == "transport_echo"
    }
    for event in events:
        media_primary = bool(event.pop("_codex_media_primary", False))
        if event.get("provenance") != "operator_typed":
            continue
        unmatched_effective_input = bool(
            not media_primary and echo_hashes and digest(str(event.get("text") or "")) not in echo_hashes
        )
        if forked:
            event["body_kind"] = "session_context"
            event["task_body"] = ""
            event["provenance"] = "continuation_summary"
            event["authority"] = "derived"
        elif unmatched_effective_input:
            # Effective-input rows may contain injected context, but older
            # Codex formats can also omit the event echo for a real turn. Keep
            # the atom with unknown authority instead of promoting or deleting.
            event["provenance"] = "unknown_user_input"
            event["authority"] = "unknown"
    return primary_before_echo(events)


def _codex_canonical_parent_record(obj: dict[str, Any]) -> bool:
    payload = obj.get("payload")
    return bool(
        obj.get("type") == "response_item"
        and isinstance(payload, dict)
        and payload.get("type") == "message"
        and payload.get("role") == "user"
    )


def codex_attachment_reference_line(path: Path) -> str:
    return f"pasted text file: {path.expanduser().absolute()}. Read this file before continuing."


def codex_attachment_reference_paths(lifecycle: Any, text: str) -> list[str]:
    """Resolve exact provider attachment envelopes without guessing at prompt text."""

    prefix = "pasted text file: "
    suffix = ". Read this file before continuing."
    targets: list[str] = []
    for line in text.splitlines():
        if not line.startswith(prefix) or not line.endswith(suffix):
            continue
        raw_path = line[len(prefix) : -len(suffix)]
        if not raw_path or "\x00" in raw_path:
            continue
        candidate = Path(raw_path)
        if not candidate.is_absolute() or ".." in candidate.parts:
            continue
        lexical = candidate.expanduser().absolute()
        if str(lexical) != raw_path:
            continue
        if source_relative_path(lifecycle, "codex-attachments", lexical) is None:
            continue
        if native_source_adapter_candidate_id(lifecycle, "codex-attachments", lexical) != (
            "codex-pasted-text-attachment-v1"
        ):
            continue
        targets.append(str(lexical))
    return targets


def codex_png_descriptor(block: dict[str, Any]) -> tuple[str | None, str | None]:
    """Validate one bounded inline PNG and return a private digest-only occurrence."""

    schema_error = codex_image_block_schema_error(block)
    if schema_error:
        return None, schema_error
    prefix = "data:image/png;base64,"
    encoded = str(block["image_url"])[len(prefix) :]
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None, "Codex input image is not strict base64"
    maximum = int(SOURCE_ADAPTER_RULES["codex-session-jsonl-v2"]["max_media_bytes"])
    if not payload or len(payload) > maximum:
        return None, f"Codex input image exceeds bounded byte ceiling {maximum}"
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return None, "Codex input image is not a canonical PNG"

    offset = 8
    width: int | None = None
    height: int | None = None
    saw_iend = False
    chunk_index = 0
    while offset < len(payload):
        if offset + 12 > len(payload):
            return None, "Codex input PNG is truncated"
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(payload) or re.fullmatch(rb"[A-Za-z]{4}", chunk_type) is None:
            return None, "Codex input PNG has a malformed chunk"
        chunk_data = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_data, zlib.crc32(chunk_type)) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            return None, "Codex input PNG has a corrupt chunk"
        if chunk_index == 0:
            if chunk_type != b"IHDR" or length != 13:
                return None, "Codex input PNG has no canonical IHDR"
            width, height = struct.unpack(">II", chunk_data[:8])
            if width <= 0 or height <= 0:
                return None, "Codex input PNG dimensions are malformed"
        elif chunk_type == b"IHDR":
            return None, "Codex input PNG repeats IHDR"
        if chunk_type == b"IEND":
            if length != 0 or chunk_end != len(payload):
                return None, "Codex input PNG has a malformed IEND"
            saw_iend = True
            offset = chunk_end
            break
        offset = chunk_end
        chunk_index += 1
    if not saw_iend or width is None or height is None or offset != len(payload):
        return None, "Codex input PNG is incomplete"
    media_hash = hashlib.sha256(payload).hexdigest()
    return (
        f"codex-input-image-v1:sha256={media_hash};bytes={len(payload)};width={width};height={height};detail=high",
        None,
    )


def codex_prompt_items_for(
    lifecycle: Any,
    obj: dict[str, Any],
) -> tuple[list[dict[str, Any]], str | None]:
    """Extract exact text and digest-only media occurrences from one Codex row."""

    payload = obj.get("payload")
    if (
        obj.get("type") == "response_item"
        and isinstance(payload, dict)
        and payload.get("type") == "message"
        and payload.get("role") == "user"
    ):
        items: list[dict[str, Any]] = []
        for block_index, block in enumerate(payload.get("content") or []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "input_text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    items.append({"text_index": block_index, "text": text})
                continue
            if block.get("type") == "input_image":
                descriptor, error = codex_png_descriptor(block)
                if error:
                    return [], error
                items.append(
                    {
                        "text_index": block_index,
                        "text": descriptor,
                        "body_kind": "nontext_input",
                        "media_primary": True,
                    }
                )
        return items, None
    if obj.get("type") == "event_msg" and isinstance(payload, dict) and payload.get("type") == "user_message":
        message = payload.get("message")
        return ([{"text_index": 0, "text": message}] if isinstance(message, str) and message.strip() else []), None
    if obj.get("type") == "compacted" and isinstance(payload, dict):
        items = []
        item_index = 0
        for history_item in payload.get("replacement_history") or []:
            if not isinstance(history_item, dict) or history_item.get("type") != "message":
                continue
            if history_item.get("role") != "user":
                continue
            for block in history_item.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "input_text":
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        items.append(
                            {
                                "text_index": item_index,
                                "text": text,
                                "body_kind": "session_context",
                                "provenance": "continuation_summary",
                                "authority": "derived",
                            }
                        )
                elif block.get("type") == "input_image":
                    descriptor, error = codex_png_descriptor(block)
                    if error:
                        return [], error
                    items.append(
                        {
                            "text_index": item_index,
                            "text": descriptor,
                            "body_kind": "nontext_context",
                            "provenance": "continuation_summary",
                            "authority": "derived",
                        }
                    )
                item_index += 1
        return items, None
    return [
        {"text_index": index, "text": text}
        for index, text in enumerate(prompt_texts_for(lifecycle, "codex-sessions", obj))
    ], None


def regular_file_events(
    lifecycle: Any,
    source: str,
    path: Path,
    records: list[dict[str, Any]],
    *,
    adapter_id: str | None,
    limits: ResourceLimits,
) -> tuple[list[dict[str, Any]], str | None]:
    """Normalize one schema-validated regular file into bounded prompt events."""

    file_session_id = canonical_file_session_id(source, path, records)
    file_is_forked = codex_file_is_forked(source, records)
    path_authority = claude_project_path_authority(lifecycle, source, path)
    file_events: list[dict[str, Any]] = []
    for event_index, obj in enumerate(records):
        if source == "codex-sessions":
            prompt_items, prompt_error = codex_prompt_items_for(lifecycle, obj)
            if prompt_error:
                return [], f"{path}:{event_index + 1}: {prompt_error}"
        else:
            prompt_items = [
                {"text_index": text_index, "text": text}
                for text_index, text in enumerate(prompt_texts_for(lifecycle, source, obj))
            ]
        for item in prompt_items:
            text_index = int(item["text_index"])
            text = str(item["text"])
            if "body_kind" in item:
                task_body, body_kind = "", str(item["body_kind"])
            elif adapter_id == "claude-remote-task-command-v1":
                task_body, body_kind = "", "direct"
            else:
                task_body, body_kind = lifecycle.normalize_task_body(text)
            provenance, authority = (
                (str(item["provenance"]), str(item["authority"]))
                if "provenance" in item and "authority" in item
                else provenance_for(source, obj, body_kind)
            )
            if path_authority == "derived" or (adapter_id and adapter_id != "codex-session-jsonl-v2"):
                provenance, authority = "delegated_task_frame", "derived"
            elif path_authority == "unknown" and provenance == "operator_typed":
                provenance, authority = "unknown_user_input", "unknown"
            payload = obj.get("payload")
            event_ref = (
                obj.get("uuid")
                or obj.get("id")
                or (payload.get("id") if isinstance(payload, dict) else None)
                or event_index
            )
            file_events.append(
                {
                    "source": source,
                    "session_ref": session_reference(
                        source,
                        path,
                        obj,
                        file_session_id=file_session_id,
                    ),
                    "event_ref": event_ref,
                    "event_index": event_index,
                    "text_index": text_index,
                    "source_locator": f"{path}#{event_index}:{text_index}",
                    "timestamp": event_timestamp(obj),
                    "text": text,
                    "task_body": task_body if body_kind == "flame_with_task_body" else "",
                    "body_kind": body_kind,
                    "provenance": provenance,
                    "authority": authority,
                    **({"claude_transport_candidate": True} if claude_transport_candidate(obj) else {}),
                    **(
                        {"_codex_attachment_parent": True}
                        if source == "codex-sessions" and _codex_canonical_parent_record(obj)
                        else {}
                    ),
                    **({"_codex_media_primary": True} if item.get("media_primary") else {}),
                }
            )
            if len(file_events) > limits.max_events_per_unit:
                break
        if len(file_events) > limits.max_events_per_unit:
            break
    if len(file_events) > limits.max_events_per_unit:
        return (
            [],
            f"prompt occurrence count exceeds bounded ceiling {limits.max_events_per_unit}",
        )
    file_events = normalize_claude_file_events(source, file_events)
    return normalize_codex_file_events(source, file_events, forked=file_is_forked), None


def targeted_codex_attachment_parent_events(
    lifecycle: Any,
    path: Path,
    _records: list[dict[str, Any]],
    *,
    limits: ResourceLimits,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Use the same byte-exact adapter for regular and oversized parent files."""

    signature = file_signature(path)
    if signature is None:
        return [], "attachment parent cannot be stat'ed", True
    return bounded_codex_attachment_parent_events_from_path(
        lifecycle,
        path,
        signature,
        limits=limits,
    )


def bounded_codex_attachment_parent_events_from_path(
    lifecycle: Any,
    path: Path,
    signature: dict[str, Any],
    *,
    limits: ResourceLimits,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Stream oversized JSONL parents under explicit byte, row, and candidate ceilings."""

    rule = SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]
    max_probe_bytes = int(rule["max_parent_probe_bytes"])
    max_record_bytes = int(rule["max_parent_record_bytes"])
    max_candidate_bytes = int(rule["max_parent_candidate_bytes"])
    max_parent_records = int(rule["max_parent_records"])
    max_session_ids = int(rule["max_parent_session_ids"])
    if int(signature.get("size") or 0) > max_probe_bytes:
        return [], f"attachment parent exceeds bounded byte ceiling {max_probe_bytes}", True

    session_ids: list[str] = []
    session_identity_error: str | None = None
    forked = False
    echo_hashes: set[str] = set()
    parent_completeness_unknown = False
    candidates: list[dict[str, Any]] = []
    candidate_bytes = 0
    record_index = 0
    bytes_read = 0
    try:
        with path.open("rb") as handle:
            while True:
                parts: list[bytes] = []
                oversized = False
                saw_data = False
                record_bytes = 0
                while True:
                    chunk = handle.readline(65536)
                    if not chunk:
                        break
                    saw_data = True
                    bytes_read += len(chunk)
                    if bytes_read > max_probe_bytes:
                        return [], f"attachment parent exceeds bounded byte ceiling {max_probe_bytes}", True
                    record_bytes += len(chunk)
                    if not oversized and record_bytes <= max_record_bytes:
                        parts.append(chunk)
                    else:
                        oversized = True
                        parts = []
                    if chunk.endswith(b"\n"):
                        break
                if not saw_data:
                    break
                if not oversized and not b"".join(parts).strip():
                    continue
                if record_index >= max_parent_records:
                    return (
                        [],
                        f"attachment parent record count exceeds bounded ceiling {max_parent_records}",
                        True,
                    )
                current_index = record_index
                record_index += 1
                if oversized:
                    # Raw marker probes are not evidence of absence: JSON may
                    # encode the same canonical text with escapes, and a late
                    # field may carry a second session identity. Any row we do
                    # not parse makes the complete parent provenance unknown.
                    parent_completeness_unknown = True
                    continue
                raw = b"".join(parts)
                try:
                    obj = json.loads(raw.decode("utf-8", errors="strict"))
                except (UnicodeError, ValueError):
                    parent_completeness_unknown = True
                    continue
                if not isinstance(obj, dict):
                    parent_completeness_unknown = True
                    continue
                payload = obj.get("payload")
                if obj.get("type") == "session_meta" and not isinstance(payload, dict):
                    session_identity_error = "attachment parent session metadata is malformed"
                    parent_completeness_unknown = True
                    continue
                if obj.get("type") == "session_meta" and isinstance(payload, dict):
                    identity_count = 0
                    for field in ("id", "session_id"):
                        value = payload.get(field)
                        if value is None:
                            continue
                        if not isinstance(value, str) or not value:
                            session_identity_error = "attachment parent session identity is malformed"
                            parent_completeness_unknown = True
                            continue
                        identity_count += 1
                        if value not in session_ids:
                            session_ids.append(value)
                    if identity_count == 0:
                        session_identity_error = "attachment parent session identity is malformed"
                        parent_completeness_unknown = True
                    if len(session_ids) > max_session_ids:
                        session_identity_error = "attachment parent has too many session identities"
                    forked = bool(
                        forked
                        or payload.get("forked_from_id")
                        or payload.get("parent_thread_id")
                        or payload.get("thread_source") == "subagent"
                    )
                    continue
                schema_error = native_record_schema_error(
                    lifecycle,
                    "codex-sessions",
                    path,
                    [obj],
                    adapter_id=None,
                    file_complete=False,
                )
                if schema_error:
                    parent_completeness_unknown = True
                    continue
                if (
                    obj.get("type") == "event_msg"
                    and isinstance(payload, dict)
                    and payload.get("type") == "user_message"
                ):
                    echo_hashes.update(digest(text) for text in prompt_texts_for(lifecycle, "codex-sessions", obj))
                    continue
                if not _codex_canonical_parent_record(obj):
                    continue
                event_ref = (
                    obj.get("uuid")
                    or obj.get("id")
                    or (payload.get("id") if isinstance(payload, dict) else None)
                    or current_index
                )
                for text_index, text in enumerate(prompt_texts_for(lifecycle, "codex-sessions", obj)):
                    references = codex_attachment_reference_paths(lifecycle, text)
                    if not references:
                        continue
                    candidate_bytes += len(text.encode("utf-8", errors="replace"))
                    if candidate_bytes > max_candidate_bytes:
                        return [], f"attachment parent candidates exceed bounded ceiling {max_candidate_bytes}", True
                    candidates.append(
                        {
                            "event_ref": event_ref,
                            "event_index": current_index,
                            "text_index": text_index,
                            "timestamp": event_timestamp(obj),
                            "text": text,
                        }
                    )
                    if len(candidates) > limits.max_events_per_unit:
                        return (
                            [],
                            f"attachment parent candidate count exceeds bounded ceiling {limits.max_events_per_unit}",
                            True,
                        )
    except OSError:
        return [], "attachment parent cannot be read", True

    if bytes_read != int(signature.get("size") or 0) or file_signature(path) != signature:
        return [], "attachment parent changed during bounded read", True
    if parent_completeness_unknown and candidates:
        return (
            [],
            "attachment parent completeness is unknown while attachment candidates exist; binding is fail-closed",
            True,
        )
    if not candidates:
        return [], None, parent_completeness_unknown
    if session_identity_error:
        return [], session_identity_error, parent_completeness_unknown
    path_matches = [value for value in session_ids if value in path.name]
    if len(session_ids) == 1:
        file_session_id = session_ids[0]
    elif len(path_matches) == 1:
        file_session_id = path_matches[0]
    elif not session_ids:
        return [], "attachment parent has no canonical session identity", False
    else:
        return [], "attachment parent session identity is ambiguous", False
    parent_events: list[dict[str, Any]] = []
    for candidate in candidates:
        text = str(candidate["text"])
        task_body, body_kind = lifecycle.normalize_task_body(text)
        provenance, authority = "operator_typed", "operator"
        if forked:
            task_body, body_kind = "", "session_context"
            provenance, authority = "continuation_summary", "derived"
        elif echo_hashes and digest(text) not in echo_hashes:
            provenance, authority = "unknown_user_input", "unknown"
        parent_events.append(
            {
                "source": "codex-sessions",
                "session_ref": f"codex:{file_session_id}",
                "event_ref": candidate["event_ref"],
                "event_index": candidate["event_index"],
                "text_index": candidate["text_index"],
                "source_locator": f"{path}#{candidate['event_index']}:{candidate['text_index']}",
                "timestamp": candidate["timestamp"],
                "text": text,
                "task_body": task_body if body_kind == "flame_with_task_body" else "",
                "body_kind": body_kind,
                "provenance": provenance,
                "authority": authority,
                "_codex_attachment_parent": True,
            }
        )
    return parent_events, None, False


def collect_codex_attachment_parents(
    lifecycle: Any,
    *,
    parent_path: Path,
    parent_signature: dict[str, Any],
    file_events: list[dict[str, Any]],
    parents: dict[str, list[dict[str, Any]]],
) -> None:
    """Index every exact reference occurrence; duplicates intentionally remain ambiguous."""

    for event in file_events:
        if not event.get("_codex_attachment_parent"):
            continue
        for reference_ordinal, target in enumerate(
            codex_attachment_reference_paths(lifecycle, str(event.get("text") or ""))
        ):
            parents.setdefault(target, []).append(
                {
                    "parent_locator": str(parent_path),
                    "parent_signature": parent_signature,
                    "event_ref": str(event.get("event_ref") or event.get("event_index") or "0"),
                    "event_index": int(event.get("event_index") or 0),
                    "text_index": int(event.get("text_index") or 0),
                    "session_ref": str(event.get("session_ref") or "unknown"),
                    "timestamp": event.get("timestamp"),
                    "provenance": str(event.get("provenance") or "unknown_user_input"),
                    "authority": str(event.get("authority") or "unknown"),
                    "reference_ordinal": reference_ordinal,
                }
            )


def _codex_attachment_parent_identity(parent: dict[str, Any]) -> tuple[Any, ...]:
    return (
        parent.get("parent_locator"),
        parent.get("event_ref"),
        parent.get("event_index"),
        parent.get("text_index"),
        parent.get("session_ref"),
        parent.get("reference_ordinal"),
    )


def merge_codex_attachment_parents(*groups: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for group in groups:
        for parent in group:
            identity = _codex_attachment_parent_identity(parent)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(parent)
    return merged


def codex_attachment_parent_material(
    attachment: Path,
    parent: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    parent_locator = str(parent["parent_locator"])
    reference = codex_attachment_reference_line(attachment)

    def hash_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()

    return (
        {"parent_session": dict(parent["parent_signature"])},
        {
            "parent_event": {
                "authority": str(parent["authority"]),
                "parent_event_index": int(parent["event_index"]),
                "parent_event_ref_sha256": hash_text(str(parent["event_ref"])),
                "parent_locator": parent_locator,
                "parent_locator_sha256": hash_text(parent_locator),
                "parent_session_ref_sha256": hash_text(str(parent["session_ref"])),
                "parent_text_index": int(parent["text_index"]),
                "provenance": str(parent["provenance"]),
                "reference_sha256": hash_text(reference),
                "timestamp": parent.get("timestamp"),
            }
        },
    )


def codex_attachment_receipt_parents(
    lifecycle: Any,
    attachment: Path,
    receipt: Any,
    *,
    limits: ResourceLimits,
) -> list[dict[str, Any]]:
    """Revalidate only the receipt-bound parent file on a cached second pass."""

    if not isinstance(receipt, dict):
        return []
    evidence = receipt.get("related_evidence")
    detail = evidence.get("parent_event") if isinstance(evidence, dict) else None
    related = receipt.get("related_signatures")
    expected_signature = related.get("parent_session") if isinstance(related, dict) else None
    if not isinstance(detail, dict) or not isinstance(expected_signature, dict):
        return []
    parent_locator = detail.get("parent_locator")
    if not isinstance(parent_locator, str):
        return []
    parent_path = Path(parent_locator)
    if source_relative_path(lifecycle, "codex-sessions", parent_path) is None:
        return []
    signature = file_signature(parent_path)
    if signature != expected_signature:
        return []
    records, error, supported = strict_native_records(
        lifecycle,
        "codex-sessions",
        parent_path,
        signature,
        limits=limits,
    )
    if error or not supported:
        file_events, event_error, parent_completeness_unknown = bounded_codex_attachment_parent_events_from_path(
            lifecycle,
            parent_path,
            signature,
            limits=limits,
        )
    else:
        file_events, event_error, parent_completeness_unknown = targeted_codex_attachment_parent_events(
            lifecycle,
            parent_path,
            records,
            limits=limits,
        )
    if parent_completeness_unknown or event_error or file_signature(parent_path) != signature:
        return []
    parents: dict[str, list[dict[str, Any]]] = {}
    collect_codex_attachment_parents(
        lifecycle,
        parent_path=parent_path,
        parent_signature=signature,
        file_events=file_events,
        parents=parents,
    )
    return parents.get(str(attachment.expanduser().absolute()), [])


def adapt_codex_attachment(
    lifecycle: Any,
    path: Path,
    signature: dict[str, Any],
    parents: Sequence[dict[str, Any]],
    *,
    limits: ResourceLimits,
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    str | None,
    bool,
]:
    """Bind a bounded pasted-text body to exactly one canonical parent event."""

    if len(parents) != 1:
        return [], {}, {}, None, False
    adapter_limit = int(SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]["max_probe_bytes"])
    maximum = min(adapter_limit, limits.max_source_bytes_per_unit)
    payload = _bounded_file_bytes(path, signature, maximum=maximum)
    if payload is None:
        return [], {}, {}, f"attachment exceeds bounded byte ceiling {maximum}", True
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError:
        return [], {}, {}, "attachment is not strict UTF-8 text", True
    if not text.strip():
        return [], {}, {}, "attachment body is empty", True
    parent = parents[0]
    if file_signature(Path(str(parent["parent_locator"]))) != parent.get("parent_signature"):
        return [], {}, {}, "attachment parent changed during binding", True
    related_signatures, related_evidence = codex_attachment_parent_material(path, parent)
    task_body, body_kind = lifecycle.normalize_task_body(text)
    attachment_ref = digest(str(path.expanduser().absolute()))[:24]
    event = {
        "source": "codex-attachments",
        "session_ref": str(parent["session_ref"]),
        "event_ref": f"{parent['event_ref']}:attachment:{attachment_ref}",
        "event_index": int(parent["event_index"]),
        "text_index": int(parent["text_index"]),
        "source_locator": f"{path}#0:0",
        "timestamp": parent.get("timestamp"),
        "text": text,
        "task_body": task_body if body_kind == "flame_with_task_body" else "",
        "body_kind": body_kind,
        "provenance": str(parent["provenance"]),
        "authority": str(parent["authority"]),
    }
    return [event], related_signatures, related_evidence, None, True


def scan_regular_sources(
    lifecycle: Any,
    cursor: dict[str, Any],
    *,
    days: int | None,
    budget: ScanBudget | dict[str, ScanBudget],
    rows: Sequence[dict[str, Any]] | None = None,
    limits: ResourceLimits | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    active_limits = limits or runtime_limits({})
    events: list[dict[str, Any]] = []
    files = dict(cursor.get("files") or {})
    unsupported_units = dict(cursor.get("unsupported_units") or {})
    excluded_unit_receipts = dict(cursor.get("excluded_unit_receipts") or {})
    adapted_unit_receipts = dict(cursor.get("adapted_unit_receipts") or {})
    excluded_file_keys: set[str] = set()
    exclusion_counts: Counter[str] = Counter()
    adapter_counts: Counter[str] = Counter()
    adapter_contract = source_adapter_contract()
    discovered: dict[str, Any] = {}
    coverage: dict[str, dict[str, int]] = {}
    for source in existing_regular_families(lifecycle):
        coverage_row(coverage, source)
    errors: list[str] = []
    unsupported: list[str] = []
    codex_attachment_parents: dict[str, list[dict[str, Any]]] = {}
    parent_completeness_unknown: set[str] = set()
    processed = 0
    pending = 0
    attempted = 0
    active_rows = (
        rows
        if rows is not None
        else regular_source_rows(
            lifecycle,
            days,
            limits=active_limits,
        )
    )
    source_alias_blocker_counts: Counter[str] = Counter(getattr(active_rows, "source_alias_blocker_counts", {}))
    has_codex_attachment_rows = any(str(row["source"]) == "codex-attachments" for row in active_rows)
    codex_session_proves_parent_completeness = bool(
        int(SOURCE_ADAPTER_RULES["codex-session-jsonl-v2"]["max_probe_bytes"])
        <= int(SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]["max_parent_probe_bytes"])
        and int(SOURCE_ADAPTER_RULES["codex-session-jsonl-v2"]["max_record_bytes"])
        <= int(SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]["max_parent_record_bytes"])
        and int(SOURCE_ADAPTER_RULES["codex-session-jsonl-v2"]["max_records"])
        <= int(SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]["max_parent_records"])
    )
    for source, error in getattr(active_rows, "discovery_errors", []):
        coverage_row(coverage, source)["errors"] += 1
        errors.append(error)
    truncated_source = getattr(active_rows, "truncated_source", None)
    if truncated_source:
        pending += 1
        truncated_counts = coverage_row(coverage, str(truncated_source))
        truncated_counts["pending"] += 1
        truncated_counts["errors"] += 1
        errors.append(
            f"{truncated_source}: source discovery exceeded bounded ceiling {active_limits.max_discovery_units}"
        )
    for row in active_rows:
        source = str(row["source"])
        lane_budget = source_scan_budget(budget, source)
        counts = coverage_row(coverage, source)
        path = Path(row["path"])
        custody = source_path_custody(lifecycle, source, path)
        if custody.error is not None:
            counts["errors"] += 1
            errors.append(f"{source}:{path}: {custody.error}")
            if source == "claude-projects" and custody.blocker_reason in SOURCE_ALIAS_BLOCKER_REASONS:
                source_alias_blocker_counts[str(custody.blocker_reason)] += 1
            continue
        signature = source_unit_signature(lifecycle, source, path)
        if signature is None:
            counts["discovered"] += 1
            counts["errors"] += 1
            errors.append(f"{source}:{path}: source disappeared or cannot be stat'ed")
            continue
        key = cursor_unit_key(source, path)
        discovered[key] = signature
        counts["discovered"] += 1
        exclusion_id = source_exclusion_candidate_id(lifecycle, source, path, signature)
        adapter_id = native_source_adapter_candidate_id(lifecycle, source, path)
        adapter_related_signatures: dict[str, dict[str, Any]] = {}
        adapter_related_evidence: dict[str, dict[str, Any]] = {}
        attachment_candidates: list[dict[str, Any]] = []
        targeted_parent_events: list[dict[str, Any]] = []
        claimed = False
        if exclusion_id:
            related_signatures = current_exclusion_related_signatures(
                lifecycle,
                source,
                path,
                exclusion_id,
            )
            expected_related_evidence = current_exclusion_related_evidence(
                lifecycle,
                source,
                path,
                exclusion_id,
            )
            if related_signatures is not None and source_unit_receipt_matches(
                excluded_unit_receipts.get(key),
                disposition="excluded",
                contract_id=exclusion_id,
                contract_digest=adapter_contract["digest"],
                source=source,
                locator=str(path),
                signature=signature,
                related_signatures=related_signatures,
                expected_related_evidence=expected_related_evidence,
            ):
                if (
                    source_unit_signature(lifecycle, source, path) != signature
                    or current_exclusion_related_signatures(
                        lifecycle,
                        source,
                        path,
                        exclusion_id,
                    )
                    != related_signatures
                    or (
                        expected_related_evidence is not None
                        and current_exclusion_related_evidence(
                            lifecycle,
                            source,
                            path,
                            exclusion_id,
                        )
                        != expected_related_evidence
                    )
                ):
                    excluded_unit_receipts.pop(key, None)
                    counts["errors"] += 1
                    errors.append(f"{source}:{path}: source changed during cached exclusion validation")
                    if exclusion_id in {
                        CLAUDE_PROJECT_MEMORY_ALIAS_ID,
                        CLAUDE_SUBAGENT_SESSION_ALIAS_ID,
                    }:
                        source_alias_blocker_counts["alias_changed"] += 1
                    continue
                exclusion_counts[exclusion_id] += 1
                counts["excluded"] += 1
                unsupported_units.pop(key, None)
                files.pop(key, None)
                excluded_file_keys.add(key)
                adapted_unit_receipts.pop(key, None)
                continue
            if not lane_budget.claim():
                pending += 1
                counts["pending"] += 1
                continue
            attempted += 1
            claimed = True
            refreshed_custody = source_path_custody(
                lifecycle,
                source,
                path,
                containment_root=containing_source_root(lifecycle, source, path) or path.parent,
            )
            escape = refreshed_custody.error
            if escape:
                counts["errors"] += 1
                errors.append(f"{source}:{path}: {escape}")
                if source == "claude-projects" and refreshed_custody.blocker_reason in SOURCE_ALIAS_BLOCKER_REASONS:
                    source_alias_blocker_counts[str(refreshed_custody.blocker_reason)] += 1
                continue
            confirmed = confirm_source_exclusion(
                lifecycle,
                source,
                path,
                signature,
                exclusion_id,
            )
            if confirmed is None:
                excluded_unit_receipts.pop(key, None)
                adapted_unit_receipts.pop(key, None)
                if exclusion_id in {
                    CLAUDE_PROJECT_MEMORY_ALIAS_ID,
                    CLAUDE_SUBAGENT_SESSION_ALIAS_ID,
                }:
                    counts["errors"] += 1
                    errors.append(f"{source}:{path}: approved alias changed during exclusion classification")
                    source_alias_blocker_counts["alias_changed"] += 1
                    continue
                counts["unsupported"] += 1
                unsupported.append(key)
                unsupported_units[key] = signature
                continue
            confirmed_id, related_signatures, related_evidence = confirmed
            related_changed = bool(
                exclusion_id
                in {
                    CLAUDE_PROJECT_MEMORY_ALIAS_ID,
                    CLAUDE_SUBAGENT_SESSION_ALIAS_ID,
                }
                and (
                    current_exclusion_related_signatures(lifecycle, source, path, exclusion_id) != related_signatures
                    or current_exclusion_related_evidence(lifecycle, source, path, exclusion_id) != related_evidence
                )
            )
            if source_unit_signature(lifecycle, source, path) != signature or related_changed:
                counts["errors"] += 1
                errors.append(f"{source}:{path}: source changed during exclusion classification")
                if exclusion_id in {
                    CLAUDE_PROJECT_MEMORY_ALIAS_ID,
                    CLAUDE_SUBAGENT_SESSION_ALIAS_ID,
                }:
                    source_alias_blocker_counts["alias_changed"] += 1
                continue
            excluded_unit_receipts[key] = {
                "version": SOURCE_ADAPTER_CONTRACT_VERSION,
                "disposition": "excluded",
                "contract_id": confirmed_id,
                "contract_digest": adapter_contract["digest"],
                "signature": signature,
                "related_signatures": related_signatures,
                "related_evidence": related_evidence,
            }
            exclusion_counts[confirmed_id] += 1
            counts["excluded"] += 1
            unsupported_units.pop(key, None)
            adapted_unit_receipts.pop(key, None)
            files.pop(key, None)
            excluded_file_keys.add(key)
            continue
        excluded_unit_receipts.pop(key, None)
        cached_adapter_matches = False
        if adapter_id == "codex-pasted-text-attachment-v1":
            receipt_parents = codex_attachment_receipt_parents(
                lifecycle,
                path,
                adapted_unit_receipts.get(key),
                limits=active_limits,
            )
            attachment_candidates = merge_codex_attachment_parents(
                codex_attachment_parents.get(str(path.expanduser().absolute()), []),
                receipt_parents,
            )
            if len(attachment_candidates) == 1:
                adapter_related_signatures, adapter_related_evidence = codex_attachment_parent_material(
                    path,
                    attachment_candidates[0],
                )
                cached_adapter_matches = source_unit_receipt_matches(
                    adapted_unit_receipts.get(key),
                    disposition="adapted",
                    contract_id=adapter_id,
                    contract_digest=adapter_contract["digest"],
                    source=source,
                    locator=str(path),
                    signature=signature,
                    related_signatures=adapter_related_signatures,
                    expected_related_evidence=adapter_related_evidence,
                )
        elif adapter_id:
            cached_adapter_matches = source_unit_receipt_matches(
                adapted_unit_receipts.get(key),
                disposition="adapted",
                contract_id=adapter_id,
                contract_digest=adapter_contract["digest"],
                source=source,
                locator=str(path),
                signature=signature,
            )
        if cached_adapter_matches and adapter_id is not None and files.get(key) == signature:
            parent_changed = bool(
                adapter_id == "codex-pasted-text-attachment-v1"
                and (
                    len(attachment_candidates) != 1
                    or file_signature(Path(attachment_candidates[0]["parent_locator"]))
                    != adapter_related_signatures.get("parent_session")
                )
            )
            if source_unit_signature(lifecycle, source, path) != signature or parent_changed:
                files.pop(key, None)
                adapted_unit_receipts.pop(key, None)
                counts["errors"] += 1
                errors.append(f"{source}:{path}: source changed during cached adapter validation")
                continue
            if adapter_id == "codex-session-jsonl-v2" and has_codex_attachment_rows:
                (
                    targeted_parent_events,
                    targeted_error,
                    targeted_completeness_unknown,
                ) = bounded_codex_attachment_parent_events_from_path(
                    lifecycle,
                    path,
                    signature,
                    limits=active_limits,
                )
                if targeted_completeness_unknown:
                    parent_completeness_unknown.add(key)
                if targeted_error:
                    files.pop(key, None)
                    adapted_unit_receipts.pop(key, None)
                    counts["errors"] += 1
                    errors.append(f"{source}:{targeted_error}")
                    continue
                collect_codex_attachment_parents(
                    lifecycle,
                    parent_path=path,
                    parent_signature=signature,
                    file_events=targeted_parent_events,
                    parents=codex_attachment_parents,
                )
            adapter_counts[adapter_id] += 1
            counts["adapted"] += 1
            counts["converged"] += 1
            unsupported_units.pop(key, None)
            continue
        adapted_unit_receipts.pop(key, None)
        if adapter_id:
            files.pop(key, None)
        if unsupported_units.get(key) == signature and not adapter_id:
            if source_unit_signature(lifecycle, source, path) != signature:
                unsupported_units.pop(key, None)
                counts["errors"] += 1
                errors.append(f"{source}:{path}: source changed during cached unsupported validation")
                continue
            counts["unsupported"] += 1
            unsupported.append(key)
            continue
        if files.get(key) == signature and not adapter_id:
            if source_unit_signature(lifecycle, source, path) != signature:
                files.pop(key, None)
                counts["errors"] += 1
                errors.append(f"{source}:{path}: source changed during cached parser validation")
                continue
            if source == "codex-sessions" and has_codex_attachment_rows:
                (
                    targeted_parent_events,
                    targeted_error,
                    targeted_completeness_unknown,
                ) = bounded_codex_attachment_parent_events_from_path(
                    lifecycle,
                    path,
                    signature,
                    limits=active_limits,
                )
                if targeted_completeness_unknown:
                    parent_completeness_unknown.add(key)
                if targeted_error:
                    files.pop(key, None)
                    counts["errors"] += 1
                    errors.append(f"{source}:{targeted_error}")
                    continue
                collect_codex_attachment_parents(
                    lifecycle,
                    parent_path=path,
                    parent_signature=signature,
                    file_events=targeted_parent_events,
                    parents=codex_attachment_parents,
                )
            counts["converged"] += 1
            continue
        if not claimed and not lane_budget.claim():
            pending += 1
            counts["pending"] += 1
            continue
        if not claimed:
            attempted += 1
        refreshed_custody = source_path_custody(
            lifecycle,
            source,
            path,
            containment_root=containing_source_root(lifecycle, source, path) or path.parent,
        )
        escape = refreshed_custody.error
        if escape:
            counts["errors"] += 1
            errors.append(f"{source}:{path}: {escape}")
            if source == "claude-projects" and refreshed_custody.blocker_reason in SOURCE_ALIAS_BLOCKER_REASONS:
                source_alias_blocker_counts[str(refreshed_custody.blocker_reason)] += 1
            continue
        if adapter_id == "codex-pasted-text-attachment-v1":
            file_events, adapter_related_signatures, adapter_related_evidence, error, supported = (
                adapt_codex_attachment(
                    lifecycle,
                    path,
                    signature,
                    attachment_candidates,
                    limits=active_limits,
                )
            )
        else:
            records, error, supported = strict_native_records(
                lifecycle,
                source,
                path,
                signature,
                limits=active_limits,
            )
            if source == "codex-sessions" and has_codex_attachment_rows:
                if (
                    adapter_id == "codex-session-jsonl-v2"
                    and codex_session_proves_parent_completeness
                    and not error
                    and supported
                ):
                    targeted_parent_events = []
                    targeted_error = None
                    targeted_completeness_unknown = False
                elif error or not supported:
                    (
                        targeted_parent_events,
                        targeted_error,
                        targeted_completeness_unknown,
                    ) = bounded_codex_attachment_parent_events_from_path(
                        lifecycle,
                        path,
                        signature,
                        limits=active_limits,
                    )
                else:
                    (
                        targeted_parent_events,
                        targeted_error,
                        targeted_completeness_unknown,
                    ) = targeted_codex_attachment_parent_events(
                        lifecycle,
                        path,
                        records,
                        limits=active_limits,
                    )
                if targeted_completeness_unknown:
                    parent_completeness_unknown.add(key)
                if targeted_error and not error:
                    error = targeted_error
                if targeted_parent_events and source_unit_signature(lifecycle, source, path) == signature:
                    collect_codex_attachment_parents(
                        lifecycle,
                        parent_path=path,
                        parent_signature=signature,
                        file_events=targeted_parent_events,
                        parents=codex_attachment_parents,
                    )
            if error or not supported:
                file_events = []
            else:
                if not error:
                    schema_error = native_record_schema_error(
                        lifecycle,
                        source,
                        path,
                        records,
                        adapter_id=adapter_id,
                    )
                    if schema_error:
                        files.pop(key, None)
                        adapted_unit_receipts.pop(key, None)
                        counts["unsupported"] += 1
                        unsupported.append(key)
                        unsupported_units[key] = signature
                        continue
                    file_events, error = regular_file_events(
                        lifecycle,
                        source,
                        path,
                        records,
                        adapter_id=adapter_id,
                        limits=active_limits,
                    )
                    if (
                        source == "codex-sessions"
                        and adapter_id == "codex-session-jsonl-v2"
                        and codex_session_proves_parent_completeness
                        and has_codex_attachment_rows
                        and not error
                    ):
                        collect_codex_attachment_parents(
                            lifecycle,
                            parent_path=path,
                            parent_signature=signature,
                            file_events=file_events,
                            parents=codex_attachment_parents,
                        )
                    supported = True
        if not supported:
            counts["unsupported"] += 1
            unsupported.append(key)
            unsupported_units[key] = signature
            continue
        if error:
            counts["errors"] += 1
            errors.append(f"{source}:{error}")
            continue
        if source_unit_signature(lifecycle, source, path) != signature:
            counts["errors"] += 1
            errors.append(f"{source}:{path}: source changed during scan; cursor not advanced")
            continue
        for event in file_events:
            event.pop("_codex_attachment_parent", None)
        events.extend(file_events)
        files[key] = signature
        unsupported_units.pop(key, None)
        if adapter_id:
            adapted_unit_receipts[key] = {
                "version": SOURCE_ADAPTER_CONTRACT_VERSION,
                "disposition": "adapted",
                "contract_id": adapter_id,
                "contract_digest": adapter_contract["digest"],
                "signature": signature,
                "related_signatures": adapter_related_signatures,
                "related_evidence": adapter_related_evidence,
            }
            adapter_counts[adapter_id] += 1
            counts["adapted"] += 1
        processed += 1
        counts["converged"] += 1
        counts["scanned"] += 1
    if days is None:
        files = {key: value for key, value in files.items() if key in discovered}
        unsupported_units = {key: value for key, value in unsupported_units.items() if key in discovered}
        excluded_unit_receipts = {key: value for key, value in excluded_unit_receipts.items() if key in discovered}
        adapted_unit_receipts = {key: value for key, value in adapted_unit_receipts.items() if key in discovered}
    return events, {
        "files": files,
        "discovered": discovered,
        "processed_files": processed,
        "attempted_files": attempted,
        "pending_files": pending,
        "errors": errors,
        "unsupported": unsupported,
        "parent_completeness_unknown": sorted(parent_completeness_unknown),
        "unsupported_units": unsupported_units,
        "excluded_unit_receipts": excluded_unit_receipts,
        "excluded_file_keys": sorted(excluded_file_keys),
        "source_exclusion_counts": dict(sorted(exclusion_counts.items())),
        "adapted_unit_receipts": adapted_unit_receipts,
        "source_adapter_counts": dict(sorted(adapter_counts.items())),
        "source_alias_blocker_counts": dict(sorted(source_alias_blocker_counts.items())),
        "coverage": coverage,
    }


def opencode_provenance(
    data: dict[str, Any],
    part_types: set[str],
    body_kind: str,
) -> tuple[str, str]:
    if part_types == {"compaction"}:
        return "continuation_summary", "derived"
    if "subtask" in part_types or body_kind in {"flame_scaffold", "flame_with_task_body"}:
        return "delegated_task_frame", "derived"
    proof = data.get("prompt_provenance")
    if (
        isinstance(proof, dict)
        and proof.get("primary") is True
        and proof.get("authority") == "operator"
        and proof.get("provenance") == "operator_typed"
    ):
        return "operator_typed", "operator"
    return "unknown_user_input", "unknown"


def opencode_user_schema_error(data: dict[str, Any], parts: list[dict[str, Any]]) -> str | None:
    allowed_message_keys = set(OPENCODE_USER_MESSAGE_KEYS)
    if data.get("role") != "user" or set(data) - allowed_message_keys:
        return "unknown OpenCode user-message schema"
    proof = data.get("prompt_provenance")
    if proof is not None and (
        not isinstance(proof, dict)
        or set(proof) != {"authority", "primary", "provenance"}
        or not isinstance(proof.get("primary"), bool)
        or not isinstance(proof.get("authority"), str)
        or not isinstance(proof.get("provenance"), str)
    ):
        return "unknown OpenCode prompt-provenance schema"
    for part in parts:
        part_type = str(part.get("type") or "")
        allowed_keysets = set(OPENCODE_USER_PART_KEYSETS.get(part_type, ()))
        if tuple(sorted(part)) not in allowed_keysets:
            return f"OpenCode user part {part_type or 'unknown'} requires an explicit adapter"
        if part_type == "text" and not isinstance(part.get("text"), str):
            return "unknown OpenCode user text schema"
        if part_type == "compaction" and "summary" in part and not isinstance(part.get("summary"), str):
            return "unknown OpenCode compaction schema"
        if part_type == "subtask" and not any(
            isinstance(part.get(field), str) and str(part.get(field)).strip() for field in ("prompt", "description")
        ):
            return "unknown OpenCode subtask schema"
    return None


def opencode_storage_signature(path: Path) -> dict[str, int] | None:
    """Bind every virtual session to the SQLite database and WAL identity."""

    database = file_signature(path)
    if database is None:
        return None
    wal_path = Path(f"{path}-wal")
    if os.path.lexists(wal_path) and source_path_error(wal_path, containment_root=path.parent):
        return None
    wal = file_signature(wal_path) if wal_path.exists() else None
    if wal is None:
        wal = {field: 0 for field in SOURCE_FILE_SIGNATURE_FIELDS}
    values = {
        **{f"db_{field}": int(database[field]) for field in SOURCE_FILE_SIGNATURE_FIELDS},
        **{f"wal_{field}": int(wal[field]) for field in SOURCE_FILE_SIGNATURE_FIELDS},
    }
    expected = set(OPENCODE_UNIT_SIGNATURE_FIELDS) - {"content_sha256", "time_created", "time_updated"}
    if set(values) != expected:
        raise RuntimeError("OpenCode storage signature contract drift")
    return values


def structured_user_prompt_marker(value: Any) -> bool:
    """Detect prompt-bearing aliases in an otherwise unsupported structured carrier."""

    pending = [value]
    while pending:
        candidate = pending.pop()
        if isinstance(candidate, dict):
            role = str(candidate.get("role") or "").strip().lower()
            marker_type = str(candidate.get("type") or "").strip().lower()
            if (
                role in {"human", "operator", "user"}
                or any(field in candidate for field in ("prompt", "instructions"))
                or any(token in marker_type for token in ("human", "operator", "prompt", "user"))
            ):
                return True
            pending.extend(candidate.values())
        elif isinstance(candidate, list):
            pending.extend(candidate)
    return False


def opencode_message_is_unknown_user_carrier(data: dict[str, Any]) -> bool:
    return structured_user_prompt_marker(data)


def opencode_integrity_error(connection: sqlite3.Connection, *, step_ceiling: int) -> str | None:
    """Fail closed on prompt rows that are unreachable from canonical sessions."""

    progress = {"steps": 0}

    def bounded_progress() -> int:
        progress["steps"] += 1_000
        return int(progress["steps"] > step_ceiling)

    connection.set_progress_handler(bounded_progress, 1_000)
    try:
        orphan_message = connection.execute(
            "SELECT 1 FROM message AS m LEFT JOIN session AS s ON s.id=m.session_id WHERE s.id IS NULL LIMIT 1"
        ).fetchone()
        if orphan_message is not None:
            return "OpenCode message row has no canonical session"
        orphan_part = connection.execute(
            "SELECT 1 FROM part AS p "
            "LEFT JOIN session AS s ON s.id=p.session_id "
            "LEFT JOIN message AS m ON m.id=p.message_id "
            "WHERE s.id IS NULL OR m.id IS NULL OR m.session_id != p.session_id LIMIT 1"
        ).fetchone()
        if orphan_part is not None:
            return "OpenCode part row has no same-session canonical message"
    finally:
        connection.set_progress_handler(None, 0)
    return None


def opencode_user_summary_schema_error(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    step_ceiling: int,
) -> str | None:
    """Validate the exact provider-generated patch-summary envelope in SQLite.

    The summary can be much larger than the user prompt.  Keep it outside the
    prompt projection only after proving its canonical shape without returning
    patch bodies to Python.
    """

    progress = {"steps": 0}

    def bounded_progress() -> int:
        progress["steps"] += 1_000
        return int(progress["steps"] > step_ceiling)

    connection.set_progress_handler(bounded_progress, 1_000)
    try:
        summary_rows = connection.execute(
            "SELECT id, json_extract(data, '$.role') AS role, "
            "json_type(data, '$.summary') AS summary_type, "
            "length(CAST(json_extract(data, '$.summary') AS BLOB)) AS summary_bytes "
            "FROM message WHERE session_id=? AND json_valid(data) "
            "AND json_extract(data, '$.role')='user' "
            "AND json_type(data, '$.summary') IS NOT NULL",
            (session_id,),
        ).fetchall()
        expected_diff_types = {
            "additions": "integer",
            "deletions": "integer",
            "file": "text",
            "patch": "text",
            "status": "text",
        }
        if set(expected_diff_types) != set(OPENCODE_USER_SUMMARY_DIFF_KEYS):
            raise RuntimeError("OpenCode summary field-type contract drift")
        allowed_placeholders = ", ".join("?" for _ in OPENCODE_USER_SUMMARY_DIFF_KEYS)
        exact_key_checks = " OR ".join(
            "(SELECT COUNT(*) FROM json_each(d.value) AS field WHERE field.key=?) != 1"
            for _ in OPENCODE_USER_SUMMARY_DIFF_KEYS
        )
        type_checks = " OR ".join(
            f"COALESCE(json_type(d.value, '$.{field}'), 'missing') != ?" for field in OPENCODE_USER_SUMMARY_DIFF_KEYS
        )
        invalid_diff_query = (
            "SELECT 1 FROM message AS m, json_each(m.data, '$.summary.diffs') AS d "
            "WHERE m.id=? AND (d.type != 'object' "
            "OR (SELECT COUNT(*) FROM json_each(d.value)) != ? "
            f"OR EXISTS (SELECT 1 FROM json_each(d.value) AS field WHERE field.key NOT IN ({allowed_placeholders})) "
            f"OR {exact_key_checks} OR {type_checks}) LIMIT 1"
        )
        for row in summary_rows:
            if row["role"] != "user" or row["summary_type"] != "object":
                return "OpenCode summary is not canonical user patch context"
            if int(row["summary_bytes"] or 0) > OPENCODE_USER_SUMMARY_MAX_BYTES:
                return f"OpenCode summary exceeds hard byte ceiling {OPENCODE_USER_SUMMARY_MAX_BYTES}"
            summary_keys = connection.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN key=? THEN 1 ELSE 0 END) AS expected, "
                "SUM(CASE WHEN key!=? THEN 1 ELSE 0 END) AS unexpected "
                "FROM message AS m, json_each(m.data, '$.summary') WHERE m.id=?",
                (OPENCODE_USER_SUMMARY_KEYS[0], OPENCODE_USER_SUMMARY_KEYS[0], row["id"]),
            ).fetchone()
            if (
                int(summary_keys["total"] or 0) != len(OPENCODE_USER_SUMMARY_KEYS)
                or int(summary_keys["expected"] or 0) != 1
                or int(summary_keys["unexpected"] or 0) != 0
            ):
                return "OpenCode summary has an unknown provider patch-context schema"
            summary_data = connection.execute(
                "SELECT json_type(data, '$.summary.diffs') AS diffs_type FROM message WHERE id=?",
                (row["id"],),
            ).fetchone()
            if summary_data is None or summary_data["diffs_type"] != "array":
                return "OpenCode summary diffs is not a canonical array"
            invalid_diff = connection.execute(
                invalid_diff_query,
                (
                    row["id"],
                    len(OPENCODE_USER_SUMMARY_DIFF_KEYS),
                    *OPENCODE_USER_SUMMARY_DIFF_KEYS,
                    *OPENCODE_USER_SUMMARY_DIFF_KEYS,
                    *(expected_diff_types[field] for field in OPENCODE_USER_SUMMARY_DIFF_KEYS),
                ),
            ).fetchone()
            if invalid_diff is not None:
                return "OpenCode summary contains an unknown provider diff schema"
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).lower():
            return "OpenCode summary validation exceeds bounded step ceiling"
        raise
    finally:
        connection.set_progress_handler(None, 0)
    return None


def opencode_assistant_task_event(
    lifecycle: Any,
    connection: sqlite3.Connection,
    *,
    path: Path,
    session_id: str,
    message: sqlite3.Row,
    message_data: dict[str, Any],
    part: sqlite3.Row,
    part_data: dict[str, Any],
    event_index: int,
    text_index: int,
    seen_call_ids: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Adapt one exact OpenCode task-tool call into a derived prompt event."""

    if set(message_data) not in [set(keyset) for keyset in OPENCODE_ASSISTANT_MESSAGE_KEYSETS]:
        return None, "OpenCode task-tool parent requires an explicit assistant-message adapter"
    if message_data.get("role") != "assistant":
        return None, "OpenCode task-tool parent is not a canonical assistant message"
    if set(part_data) != set(OPENCODE_TASK_TOOL_PART_KEYS):
        return None, "OpenCode task-tool part has an unknown envelope"
    call_id = part_data.get("callID")
    if not isinstance(call_id, str) or not call_id.strip():
        return None, "OpenCode task-tool callID must be a non-empty string"
    if call_id in seen_call_ids:
        return None, "OpenCode task-tool callID is duplicated within its session"
    seen_call_ids.add(call_id)
    state = part_data.get("state")
    if not isinstance(state, dict):
        return None, "OpenCode task-tool state is not an object"
    status = state.get("status")
    expected_state_keys = OPENCODE_TASK_TOOL_STATE_KEYSETS.get(status)
    if expected_state_keys is None or set(state) != set(expected_state_keys):
        return None, "OpenCode task-tool state requires an explicit status adapter"
    input_data = state.get("input")
    if not isinstance(input_data, dict) or set(input_data) not in [
        set(keyset) for keyset in OPENCODE_TASK_TOOL_INPUT_KEYSETS
    ]:
        return None, "OpenCode task-tool input has an unknown schema"
    for field in ("description", "prompt", "subagent_type"):
        if not isinstance(input_data.get(field), str) or not str(input_data[field]).strip():
            return None, f"OpenCode task-tool {field} must be a non-empty string"
    if "command" in input_data and (
        not isinstance(input_data.get("command"), str) or not str(input_data["command"]).strip()
    ):
        return None, "OpenCode task-tool command must be a non-empty string"
    metadata = state.get("metadata")
    if not isinstance(metadata, dict) or set(metadata) not in [
        set(keyset) for keyset in OPENCODE_TASK_TOOL_METADATA_KEYSETS
    ]:
        return None, "OpenCode task-tool metadata has an unknown schema"
    for field in ("parentSessionId", "sessionId"):
        if not isinstance(metadata.get(field), str) or not str(metadata[field]).strip():
            return None, f"OpenCode task-tool metadata {field} must be a non-empty string"
    if metadata["parentSessionId"] != session_id:
        return None, "OpenCode task-tool metadata does not name its canonical parent session"
    if "truncated" in metadata and not isinstance(metadata.get("truncated"), bool):
        return None, "OpenCode task-tool truncated metadata must be boolean"
    if "outputPath" in metadata and (
        not isinstance(metadata.get("outputPath"), str) or not str(metadata["outputPath"]).strip()
    ):
        return None, "OpenCode task-tool outputPath metadata must be a non-empty string"
    metadata_model = metadata.get("model")
    if not isinstance(metadata_model, dict) or set(metadata_model) != {"modelID", "providerID"}:
        return None, "OpenCode task-tool metadata model has an unknown schema"
    if any(
        not isinstance(metadata_model.get(field), str) or not str(metadata_model[field]).strip()
        for field in ("modelID", "providerID")
    ):
        return None, "OpenCode task-tool metadata model fields must be non-empty strings"
    time_data = state.get("time")
    expected_time_keys = OPENCODE_TASK_TOOL_TIME_KEYSETS[status]
    if not isinstance(time_data, dict) or set(time_data) != set(expected_time_keys):
        return None, "OpenCode task-tool time has an unknown schema"
    for field in expected_time_keys:
        if isinstance(time_data.get(field), bool) or not isinstance(time_data.get(field), int):
            return None, "OpenCode task-tool time fields must be exact integers"
    if status == "completed" and time_data["end"] < time_data["start"]:
        return None, "OpenCode task-tool completion precedes its start"
    if not isinstance(state.get("title"), str):
        return None, "OpenCode task-tool title must be a string"
    if status == "completed" and not isinstance(state.get("output"), str):
        return None, "OpenCode completed task-tool output must be a string"
    required_session_columns = {"id", "parent_id", "agent", "model"}
    session_columns = {str(row["name"]) for row in connection.execute("PRAGMA main.table_xinfo('session')").fetchall()}
    if not required_session_columns.issubset(session_columns):
        return None, "OpenCode task-tool child relationship fields are unavailable"
    child = connection.execute(
        "SELECT id, parent_id, agent, model FROM session WHERE id=?",
        (metadata["sessionId"],),
    ).fetchone()
    if child is None or child["parent_id"] != session_id:
        return None, "OpenCode task-tool child session is not canonically parented"
    if child["agent"] != input_data["subagent_type"]:
        return None, "OpenCode task-tool child session agent does not match its input"
    try:
        child_model = json.loads(child["model"]) if child["model"] else None
    except (TypeError, ValueError):
        child_model = None
    if not isinstance(child_model, dict) or set(child_model) != {"id", "providerID", "variant"}:
        return None, "OpenCode task-tool child session model has an unknown schema"
    if any(
        not isinstance(child_model.get(field), str) or not str(child_model[field]).strip()
        for field in ("id", "providerID", "variant")
    ):
        return None, "OpenCode task-tool child session model fields must be non-empty strings"
    if child_model["id"] != metadata_model["modelID"] or child_model["providerID"] != metadata_model["providerID"]:
        return None, "OpenCode task-tool child session model does not match its metadata"
    text = str(input_data["prompt"]).strip()
    task_body, normalized_kind = lifecycle.normalize_task_body(text)
    return (
        {
            "source": "opencode-db",
            "session_ref": f"opencode-db:{child['id']}:{path}",
            "event_ref": str(part["id"]),
            "event_index": event_index,
            "text_index": text_index,
            "source_locator": f"{path}#{part['id']}",
            "source_segment": "state.input.prompt",
            "timestamp": lifecycle.iso_from_epoch_ms(part["time_created"]),
            "text": text,
            "task_body": task_body if normalized_kind == "flame_with_task_body" else "",
            "body_kind": "delegated_task_frame",
            "provenance": "delegated_task_frame",
            "authority": "derived",
        },
        None,
    )


def scan_opencode(
    lifecycle: Any,
    cursor: dict[str, Any],
    *,
    days: int | None,
    budget: ScanBudget,
    limits: ResourceLimits | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    active_limits = limits or runtime_limits({})
    path = Path(lifecycle.OPENCODE_DB)
    coverage = {"opencode-db": empty_coverage()}
    counts = coverage["opencode-db"]
    adapter_contract = source_adapter_contract()
    adapter_contract_digest = str(adapter_contract["digest"])
    prior_adapted_receipts = cursor.get("adapted_unit_receipts") or {}
    if not path.exists():
        return [], {
            "discovered": {},
            "processed": {},
            "adapted_unit_receipts": {},
            "errors": [],
            "unsupported": [],
            "pending_files": 0,
            "attempted_files": 0,
            "coverage": coverage,
        }
    escape = source_path_error(path, containment_root=path.parent)
    if escape:
        counts["discovered"] += 1
        counts["errors"] += 1
        return [], {
            "discovered": {},
            "processed": {},
            "adapted_unit_receipts": {},
            "errors": [f"opencode-db:{path}: {escape}"],
            "unsupported": [],
            "pending_files": 0,
            "attempted_files": 0,
            "coverage": coverage,
        }
    database_signature = opencode_storage_signature(path)
    if database_signature is None:
        counts["discovered"] += 1
        counts["errors"] += 1
        return [], {
            "discovered": {},
            "processed": {},
            "adapted_unit_receipts": {},
            "errors": [f"opencode-db:{path}: source cannot be stat'ed"],
            "unsupported": [],
            "pending_files": 0,
            "attempted_files": 0,
            "coverage": coverage,
        }
    cutoff_ms = None
    if days is not None:
        cutoff_ms = int((dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400) * 1000)
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        counts["discovered"] += 1
        counts["errors"] += 1
        return [], {
            "discovered": {},
            "processed": {},
            "adapted_unit_receipts": {},
            "errors": [f"opencode-db:{path}: {exc}"],
            "unsupported": [],
            "pending_files": 0,
            "attempted_files": 0,
            "coverage": coverage,
        }
    connection.row_factory = sqlite3.Row
    events: list[dict[str, Any]] = []
    discovered: dict[str, Any] = {}
    processed: dict[str, Any] = {}
    adapted_unit_receipts: dict[str, Any] = {}
    errors: list[str] = []
    pending = 0
    attempted = 0
    try:
        connection.execute("BEGIN")
        integrity_error = opencode_integrity_error(
            connection,
            step_ceiling=max(1_000, active_limits.max_discovery_units * 1_000),
        )
        if integrity_error:
            raise ValueError(integrity_error)
        where = "WHERE time_updated >= ?" if cutoff_ms is not None else ""
        params: tuple[Any, ...] = (cutoff_ms,) if cutoff_ms is not None else ()
        session_cursor = connection.execute(
            f"SELECT id, time_created, time_updated FROM session {where} ORDER BY time_created, id LIMIT ?",
            (*params, active_limits.max_discovery_units + 1),
        )
        sessions = session_cursor.fetchmany(active_limits.max_discovery_units + 1)
        if len(sessions) > active_limits.max_discovery_units:
            sessions = sessions[: active_limits.max_discovery_units]
            pending += 1
            counts["pending"] += 1
            counts["errors"] += 1
            errors.append(f"opencode-db: session discovery exceeds bounded ceiling {active_limits.max_discovery_units}")
        for session in sessions:
            session_id = str(session["id"])
            unit_locator = f"{path}#session:{digest(session_id)[:24]}"
            unit_key = cursor_unit_key(
                "opencode-db",
                unit_locator,
            )
            base_unit_signature = {
                **database_signature,
                "time_created": session["time_created"],
                "time_updated": session["time_updated"],
            }
            cached_signature = (cursor.get("files") or {}).get(unit_key)
            cache_generation_matches = bool(
                isinstance(cached_signature, dict)
                and all(cached_signature.get(field) == value for field, value in base_unit_signature.items())
            )
            unit_signature = (
                dict(cached_signature) if cache_generation_matches else {**base_unit_signature, "content_sha256": ""}
            )
            discovered[unit_key] = unit_signature
            counts["discovered"] += 1
            if cache_generation_matches:
                processed[unit_key] = unit_signature
                cached_receipt = prior_adapted_receipts.get(unit_key)
                if source_unit_receipt_matches(
                    cached_receipt,
                    disposition="adapted",
                    contract_id="opencode-assistant-task-v1",
                    contract_digest=adapter_contract_digest,
                    source="opencode-db",
                    locator=unit_locator,
                    signature=unit_signature,
                ):
                    adapted_unit_receipts[unit_key] = cached_receipt
                    counts["adapted"] += 1
                counts["converged"] += 1
                continue
            max_rows = active_limits.max_events_per_unit * 10
            projected_message_data = (
                "CASE WHEN json_valid(data) AND json_extract(data, '$.role')='user' "
                "AND json_type(data, '$.summary') IS NOT NULL "
                "THEN json_remove(data, '$.summary') ELSE data END"
            )
            message_count, message_bytes, message_limit = bounded_sqlite_lengths(
                connection,
                "SELECT COALESCE(length(CAST((" + projected_message_data + ") AS BLOB)), 0) "
                "FROM message WHERE session_id=? LIMIT ?",
                (session_id,),
                max_rows=max_rows,
                max_bytes=active_limits.max_source_bytes_per_unit,
            )
            remaining_rows = max(1, max_rows - message_count)
            remaining_bytes = max(
                1,
                active_limits.max_source_bytes_per_unit - message_bytes,
            )
            part_count, part_bytes, part_limit = bounded_sqlite_lengths(
                connection,
                "SELECT COALESCE(length(CAST(data AS BLOB)), 0) FROM part WHERE session_id=? LIMIT ?",
                (session_id,),
                max_rows=remaining_rows,
                max_bytes=remaining_bytes,
            )
            record_count = message_count + part_count
            source_bytes = message_bytes + part_bytes
            if message_limit == "rows" or part_limit == "rows" or record_count > max_rows:
                counts["errors"] += 1
                errors.append(f"{unit_key}: SQLite row count {record_count} exceeds bounded ceiling {max_rows}")
                continue
            if (
                message_limit == "bytes"
                or part_limit == "bytes"
                or source_bytes > active_limits.max_source_bytes_per_unit
            ):
                counts["errors"] += 1
                errors.append(
                    f"{unit_key}: SQLite payload is {source_bytes} bytes; bounded ceiling is "
                    f"{active_limits.max_source_bytes_per_unit}"
                )
                continue
            summary_schema_error = opencode_user_summary_schema_error(
                connection,
                session_id=session_id,
                step_ceiling=max(100_000, active_limits.max_events_per_unit * 10_000),
            )
            if summary_schema_error:
                counts["errors"] += 1
                errors.append(f"{unit_key}: {summary_schema_error}")
                continue
            messages = connection.execute(
                "SELECT id, time_created, " + projected_message_data + " AS data "
                "FROM message WHERE session_id=? ORDER BY time_created, id",
                (session_id,),
            ).fetchall()
            part_rows = connection.execute(
                "SELECT id, message_id, time_created, data FROM part WHERE session_id=? ORDER BY time_created, id",
                (session_id,),
            ).fetchall()
            parts_by_message: dict[str, list[sqlite3.Row]] = {}
            for part in part_rows:
                parts_by_message.setdefault(str(part["message_id"]), []).append(part)
            content_sha256 = digest(
                {
                    "messages": [
                        [str(message["id"]), message["time_created"], str(message["data"] or "")]
                        for message in messages
                    ],
                    "parts": [
                        [
                            str(part["id"]),
                            str(part["message_id"]),
                            part["time_created"],
                            str(part["data"] or ""),
                        ]
                        for part in part_rows
                    ],
                }
            )
            unit_signature = {**base_unit_signature, "content_sha256": content_sha256}
            discovered[unit_key] = unit_signature
            if isinstance(cached_signature, dict) and cached_signature.get("content_sha256") == content_sha256:
                # The private checkpoint binds the cached digest. A global
                # SQLite/WAL generation change therefore needs only this exact
                # per-session content comparison; unrelated sessions retain
                # custody without consuming bounded parse work units.
                processed[unit_key] = unit_signature
                cached_receipt = prior_adapted_receipts.get(unit_key)
                if source_unit_receipt_matches(
                    cached_receipt,
                    disposition="adapted",
                    contract_id="opencode-assistant-task-v1",
                    contract_digest=adapter_contract_digest,
                    source="opencode-db",
                    locator=unit_locator,
                    signature=cached_signature,
                ):
                    adapted_unit_receipts[unit_key] = {
                        **cached_receipt,
                        "signature": unit_signature,
                    }
                    counts["adapted"] += 1
                counts["converged"] += 1
                continue
            if not budget.claim():
                pending += 1
                counts["pending"] += 1
                continue
            attempted += 1
            session_events: list[dict[str, Any]] = []
            session_error: str | None = None
            session_adapted = False
            seen_call_ids: set[str] = set()
            for event_index, message in enumerate(messages):
                try:
                    data = json.loads(message["data"]) if message["data"] else {}
                except (TypeError, ValueError) as exc:
                    session_error = f"{unit_key}: malformed message {message['id']}: {exc}"
                    break
                if not isinstance(data, dict):
                    session_error = f"{unit_key}: non-object message {message['id']}"
                    break
                parts = parts_by_message.get(str(message["id"]), [])
                part_types: set[str] = set()
                part_objects: list[dict[str, Any]] = []
                for part in parts:
                    try:
                        part_data = json.loads(part["data"]) if part["data"] else {}
                    except (TypeError, ValueError) as exc:
                        session_error = f"{unit_key}: malformed part for {message['id']}: {exc}"
                        break
                    if not isinstance(part_data, dict):
                        session_error = f"{unit_key}: non-object part for {message['id']}"
                        break
                    part_objects.append(part_data)
                    part_types.add(str(part_data.get("type") or ""))
                if session_error:
                    break
                if data.get("role") != "user":
                    for text_index, (part, part_data) in enumerate(zip(parts, part_objects, strict=True)):
                        if part_data.get("type") == "tool" and part_data.get("tool") == "task":
                            task_event, task_error = opencode_assistant_task_event(
                                lifecycle,
                                connection,
                                path=path,
                                session_id=session_id,
                                message=message,
                                message_data=data,
                                part=part,
                                part_data=part_data,
                                event_index=event_index,
                                text_index=text_index,
                                seen_call_ids=seen_call_ids,
                            )
                            if task_error:
                                session_error = f"{unit_key}: {task_error}"
                                break
                            if task_event is not None:
                                session_events.append(task_event)
                                session_adapted = True
                            continue
                        if structured_user_prompt_marker(part_data):
                            session_error = f"{unit_key}: unknown OpenCode user-bearing message or part schema"
                            break
                    if session_error:
                        break
                    if opencode_message_is_unknown_user_carrier(data):
                        session_error = f"{unit_key}: unknown OpenCode user-bearing message or part schema"
                        break
                    if len(session_events) > active_limits.max_events_per_unit:
                        session_error = (
                            f"{unit_key}: prompt occurrence count exceeds bounded ceiling "
                            f"{active_limits.max_events_per_unit}"
                        )
                        break
                    continue
                schema_error = opencode_user_schema_error(data, part_objects)
                if schema_error:
                    session_error = f"{unit_key}: {schema_error}"
                    break
                texts = lifecycle.opencode_part_texts(parts)
                text = "\n\n".join(texts).strip()
                if not text:
                    continue
                task_body, body_kind = lifecycle.normalize_task_body(text)
                provenance, authority = opencode_provenance(data, part_types, body_kind)
                session_events.append(
                    {
                        "source": "opencode-db",
                        "session_ref": f"opencode-db:{session_id}:{path}",
                        "event_ref": str(message["id"]),
                        "event_index": event_index,
                        "text_index": 0,
                        "source_locator": f"{path}#{message['id']}",
                        "timestamp": lifecycle.iso_from_epoch_ms(message["time_created"]),
                        "text": text,
                        "task_body": task_body if body_kind == "flame_with_task_body" else "",
                        "body_kind": body_kind,
                        "provenance": provenance,
                        "authority": authority,
                    }
                )
                if len(session_events) > active_limits.max_events_per_unit:
                    session_error = (
                        f"{unit_key}: prompt occurrence count exceeds bounded ceiling "
                        f"{active_limits.max_events_per_unit}"
                    )
                    break
            if session_error:
                counts["errors"] += 1
                errors.append(session_error)
                continue
            events.extend(session_events)
            processed[unit_key] = unit_signature
            if session_adapted:
                adapted_unit_receipts[unit_key] = {
                    "version": SOURCE_ADAPTER_CONTRACT_VERSION,
                    "disposition": "adapted",
                    "contract_id": "opencode-assistant-task-v1",
                    "contract_digest": adapter_contract_digest,
                    "signature": unit_signature,
                    "related_signatures": {},
                    "related_evidence": {},
                }
                counts["adapted"] += 1
            counts["converged"] += 1
            counts["scanned"] += 1
    except (sqlite3.Error, ValueError) as exc:
        counts["errors"] += 1
        errors.append(f"opencode-db:{path}: {exc}")
    finally:
        connection.close()
    final_database_signature = opencode_storage_signature(path)
    if final_database_signature != database_signature:
        events = []
        processed = {}
        adapted_unit_receipts = {}
        counts["converged"] = 0
        counts["scanned"] = 0
        counts["adapted"] = 0
        counts["errors"] += 1
        errors.append("opencode-db: database or WAL changed during scan; cursor not advanced")
    return events, {
        "discovered": discovered,
        "processed": processed,
        "adapted_unit_receipts": adapted_unit_receipts,
        "container_signature": database_signature if final_database_signature == database_signature else None,
        "errors": errors,
        "unsupported": [],
        "pending_files": pending,
        "attempted_files": attempted,
        "coverage": coverage,
    }


def agy_storage_signature(path: Path) -> dict[str, int] | None:
    storage = opencode_storage_signature(path)
    if storage is None:
        return None
    expected = set(AGY_CONVERSATION_UNIT_SIGNATURE_FIELDS) - {"content_sha256"}
    if set(storage) != expected:
        raise RuntimeError("Agy storage signature contract drift")
    return storage


def sqlite_cell_fingerprint(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"kind": "bytes", "size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, str):
        encoded = value.encode("utf-8", errors="replace")
        return {"kind": "text", "size": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}
    if value is None or isinstance(value, (int, float)):
        return value
    return {"kind": type(value).__name__, "sha256": digest(str(value))}


def agy_steps_schema_error(connection: sqlite3.Connection) -> str | None:
    """Validate the repository-owned Agy steps envelope without reading prompt bodies."""

    schema = SOURCE_RECORD_SCHEMAS["agy-conversation-v1"]
    try:
        object_rows = connection.execute("SELECT type, sql FROM main.sqlite_schema WHERE name = 'steps'").fetchall()
        if not object_rows:
            return "missing required steps table"
        if len(object_rows) != 1 or object_rows[0]["type"] != "table":
            return "required steps object must be a concrete table"
        create_sql = object_rows[0]["sql"]
        if not isinstance(create_sql, str) or not re.match(r"^\s*CREATE\s+TABLE\b", create_sql, re.IGNORECASE):
            return "required steps object must not be a virtual table"
        table_rows = connection.execute("PRAGMA main.table_xinfo('steps')").fetchall()
    except sqlite3.Error as exc:
        return f"cannot inspect steps schema: {exc}"
    if any(int(row["hidden"]) != 0 for row in table_rows):
        return "steps schema contains hidden or generated columns"
    names = [str(row["name"]) for row in table_rows]
    if len(names) != len(set(names)):
        return "steps schema has duplicate column names"
    required = [str(name) for name in schema["required_columns"]]
    admitted = [str(name) for name in schema.get("admitted_columns", [])]
    missing = [name for name in required if name not in names]
    if missing:
        return "steps schema is missing required columns: " + ", ".join(missing)
    unknown = sorted(set(names) - set(required) - set(admitted))
    if unknown:
        return "steps schema has unsupported columns: " + ", ".join(unknown)
    return None


def _agy_json_prompt_candidate(value: Any) -> tuple[str | None, str | None]:
    """Unwrap only exact, provider-neutral JSON prompt envelopes."""

    if isinstance(value, str):
        text = value.strip()
        return (text or None), None
    if not isinstance(value, dict):
        return None, "unsupported structured prompt envelope"
    fields = set(value)
    if fields == {"prompt"} and isinstance(value.get("prompt"), str):
        text = str(value["prompt"]).strip()
        return (text or None), None
    if fields == {"content", "role"} and value.get("role") in {"human", "operator", "user"}:
        if not isinstance(value.get("content"), str):
            return None, "structured prompt content must be a string"
        text = str(value["content"]).strip()
        return (text or None), None
    return None, "unsupported structured prompt envelope"


class AgyDuplicateJsonKeyError(ValueError):
    """A structured Agy carrier repeated a key and is therefore ambiguous."""


def _agy_unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AgyDuplicateJsonKeyError("duplicate JSON object key")
        value[key] = item
    return value


def agy_json_nesting_error(text: str, *, maximum: int) -> str | None:
    """Bound JSON container depth without counting brackets inside strings."""

    stripped = text.lstrip()
    if not stripped or stripped[0] not in "[{":
        return None
    depth = 0
    in_string = False
    escaped = False
    for character in stripped:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > maximum:
                return f"JSON nesting exceeds the bounded parser limit {maximum}"
        elif character in "]}":
            depth -= 1
            if depth < 0:
                return None
    return None


def agy_parse_json(text: str) -> tuple[Any, bool, str | None]:
    """Parse one possible envelope without collapsing duplicate object keys."""

    stripped = text.lstrip()
    json_looking = bool(stripped) and stripped[0] in '[{"'
    maximum_depth = int(SOURCE_RECORD_SCHEMAS["agy-conversation-v1"]["max_json_nesting_depth"])
    nesting_error = agy_json_nesting_error(text, maximum=maximum_depth)
    if nesting_error:
        return None, True, nesting_error
    try:
        return json.loads(text, object_pairs_hook=_agy_unique_json_object), True, None
    except AgyDuplicateJsonKeyError:
        return None, True, "duplicate JSON object keys are ambiguous"
    except RecursionError:
        return None, True, "JSON nesting exceeds the bounded parser limit"
    except json.JSONDecodeError:
        if json_looking:
            return None, True, "malformed or truncated JSON-looking carrier"
        return None, False, None
    except (TypeError, ValueError):
        if json_looking:
            return None, True, "malformed or truncated JSON-looking carrier"
        return None, False, None


def agy_binary_text_segments(value: bytes, *, maximum: int) -> tuple[list[str], str | None]:
    """Extract bounded printable source segments without a minimum-length blind spot."""

    decoded = value.decode("utf-8", errors="replace")
    characters = [
        character if character != "\ufffd" and (character in "\n\r\t" or character.isprintable()) else "\0"
        for character in decoded
    ]
    segments: list[str] = []
    for raw_segment in "".join(characters).split("\0"):
        segment = raw_segment.strip()
        if not segment:
            continue
        segments.append(segment)
        if len(segments) > maximum:
            return [], f"binary carrier exceeds bounded segment ceiling {maximum}"
    return segments, None


AGY_PROTO_ENVELOPE = SOURCE_RECORD_SCHEMAS["agy-conversation-v1"]["binary_payload_envelope"]


def agy_wire_parse(buffer: bytes, *, depth: int = 0) -> tuple[list[tuple[int, int, Any]] | None, str | None]:
    """Strict bounded protobuf wire walk: the WHOLE buffer must parse or nothing does.

    Returns ``(fields, None)`` on an exact parse — each field as
    ``(field_number, wire_type, value)`` with varint values as int, length-delimited
    payloads as bytes, and fixed32/64 as None — or ``(None, reason)`` on any anomaly
    (unknown wire type, group encoding, truncation, overrun, field zero, depth).
    Fail-closed by construction: callers treat a failed parse as "not this envelope"
    and fall back to the legacy segment contract, never to a permissive guess.
    """

    if depth > int(AGY_PROTO_ENVELOPE["max_wire_depth"]):
        return None, "wire nesting exceeds the bounded envelope depth"
    fields: list[tuple[int, int, Any]] = []
    index, size = 0, len(buffer)
    while index < size:
        tag = shift = 0
        start = index
        while True:
            if index >= size or index - start > 5:
                return None, "truncated field tag"
            byte = buffer[index]
            index += 1
            tag |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        field_number, wire_type = tag >> 3, tag & 7
        if field_number == 0:
            return None, "field number zero is invalid"
        if wire_type == 0:
            value = shift = 0
            start = index
            while True:
                if index >= size or index - start > 10:
                    return None, "truncated varint value"
                byte = buffer[index]
                index += 1
                value |= (byte & 0x7F) << shift
                shift += 7
                if not byte & 0x80:
                    break
            fields.append((field_number, 0, value))
        elif wire_type == 2:
            length = shift = 0
            start = index
            while True:
                if index >= size or index - start > 5:
                    return None, "truncated length prefix"
                byte = buffer[index]
                index += 1
                length |= (byte & 0x7F) << shift
                shift += 7
                if not byte & 0x80:
                    break
            if index + length > size:
                return None, "length-delimited field overruns the buffer"
            fields.append((field_number, 2, bytes(buffer[index : index + length])))
            index += length
        elif wire_type == 5:
            if index + 4 > size:
                return None, "fixed32 field overruns the buffer"
            index += 4
            fields.append((field_number, 5, None))
        elif wire_type == 1:
            if index + 8 > size:
                return None, "fixed64 field overruns the buffer"
            index += 8
            fields.append((field_number, 1, None))
        else:
            return None, f"unsupported wire type {wire_type}"
    return fields, None


def _agy_wire_messages(fields: list[tuple[int, int, Any]], field_number: int) -> list[bytes]:
    return [value for number, wire_type, value in fields if number == field_number and wire_type == 2]


def _agy_wire_exact_varint(fields: list[tuple[int, int, Any]], field_number: int) -> int | None:
    values = [value for number, wire_type, value in fields if number == field_number and wire_type == 0]
    return values[0] if len(values) == 1 else None


def _agy_wire_text(value: bytes) -> str | None:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if all(character in "\n\r\t" or character.isprintable() for character in text):
        return text
    return None


def agy_proto_prompt_text(
    fields: list[tuple[int, int, Any]],
) -> tuple[str | None, str | None]:
    """Extract the exactly-one prompt text from a parsed step-payload envelope.

    The registered envelope (``agy-step-payload-proto-v1``) carries the prompt
    message at field 19 with the text at field 2 and an annotated copy at
    field 3 → field 1 that must be byte-identical when present. Any deviation
    from exactly-one at each rung fails closed.
    """

    prompt_messages = _agy_wire_messages(fields, int(AGY_PROTO_ENVELOPE["prompt_message_field"]))
    if len(prompt_messages) != 1:
        return None, f"prompt envelope carries {len(prompt_messages)} prompt messages; exactly one is required"
    message_fields, message_error = agy_wire_parse(prompt_messages[0], depth=1)
    if message_error or message_fields is None:
        return None, f"prompt message is not exact wire format: {message_error}"
    texts = _agy_wire_messages(message_fields, int(AGY_PROTO_ENVELOPE["prompt_text_field"]))
    if len(texts) != 1:
        return None, f"prompt message carries {len(texts)} text fields; exactly one is required"
    text = _agy_wire_text(texts[0])
    if text is None:
        return None, "prompt text is not printable UTF-8"
    if not text.strip():
        return None, "prompt text is empty"
    annotated = _agy_wire_messages(message_fields, int(AGY_PROTO_ENVELOPE["annotated_copy_message_field"]))
    if annotated:
        annotated_fields, annotated_error = agy_wire_parse(annotated[0], depth=2)
        if annotated_error or annotated_fields is None:
            return None, f"annotated prompt copy is not exact wire format: {annotated_error}"
        copies = _agy_wire_messages(annotated_fields, int(AGY_PROTO_ENVELOPE["annotated_copy_text_field"]))
        if len(copies) != 1 or _agy_wire_text(copies[0]) != text:
            return None, "annotated prompt copy diverges from the prompt text"
    return text, None


def agy_proto_envelope_fields(value: bytes) -> list[tuple[int, int, Any]] | None:
    """Return parsed fields iff the whole cell is the registered proto envelope."""

    fields, error = agy_wire_parse(value)
    if error or not fields:
        return None
    return fields


def agy_prompt_cell_candidates(
    value: Any,
    *,
    column: str,
    maximum: int,
) -> tuple[list[tuple[str, int, str]], str | None]:
    """Return bounded prompt candidates tied to exact source segments.

    Text cells are one exact segment. Binary cells may contribute independently
    grounded printable segments through the legacy bounded binary splitter; the
    record adapter, not this helper, enforces exact-one cardinality.
    """

    if value is None:
        return [], None
    if isinstance(value, str):
        segments = [value]
    elif isinstance(value, bytes):
        envelope_fields = agy_proto_envelope_fields(value)
        if envelope_fields is not None:
            # Registered proto envelope: the prompt carrier is structural (field 19),
            # so segment scraping never runs — its printable noise is not grounded text.
            if not _agy_wire_messages(envelope_fields, int(AGY_PROTO_ENVELOPE["prompt_message_field"])):
                return [], None
            text, envelope_error = agy_proto_prompt_text(envelope_fields)
            if envelope_error or text is None:
                return [], f"{column} {envelope_error}"
            return [(column, 0, text)], None
        segments, segment_error = agy_binary_text_segments(value, maximum=maximum)
        if segment_error:
            return [], f"{column} {segment_error}"
    else:
        return [], f"{column} has unsupported SQLite value type"
    if len(segments) > maximum:
        return [], f"{column} exceeds bounded prompt-candidate ceiling {maximum}"

    candidates: list[tuple[str, int, str]] = []
    for ordinal, segment in enumerate(segments):
        text = segment.strip()
        if not text:
            continue
        structured, parsed, parse_error = agy_parse_json(text)
        if parse_error:
            return [], f"{column} contains an {parse_error}"
        if parsed:
            candidate, error = _agy_json_prompt_candidate(structured)
        else:
            candidate = text
            error = None
        if error:
            return [], f"{column} contains an {error}"
        if candidate:
            candidates.append((column, ordinal, candidate))
        if len(candidates) > maximum:
            return [], f"{column} exceeds bounded prompt-candidate ceiling {maximum}"
    return candidates, None


def agy_nonprompt_cell_error(
    value: Any,
    *,
    column: str,
    maximum: int,
) -> str | None:
    """Reject a purported non-prompt row when any prompt carrier is visible."""

    if value is None:
        return None
    if isinstance(value, str):
        spans = [value]
    elif isinstance(value, bytes):
        envelope_fields = agy_proto_envelope_fields(value)
        if envelope_fields is not None:
            # Registered proto envelope: prompt presence is the structural field-19
            # fact. Assistant/tool steps legitimately QUOTE prompt-marker text in
            # their output strings, so marker heuristics do not apply to an exact
            # parse — a failed parse still takes the full legacy marker contract.
            if _agy_wire_messages(envelope_fields, int(AGY_PROTO_ENVELOPE["prompt_message_field"])):
                return "non-prompt step contains a structured prompt-bearing carrier"
            return None
        spans, segment_error = agy_binary_text_segments(value, maximum=maximum)
        if segment_error:
            return f"{column} {segment_error}"
    else:
        return f"{column} has unsupported SQLite value type"
    prompt_markers = ("# FLAME", "## FLAME", "Complete task ", "/goal")
    structural_marker = re.compile(
        r"(?:^|[\s,{])(?:prompt|instructions)\s*[:=]|"
        r"(?:^|[\s,{])role\s*[:=]\s*(?:user|human|operator)|"
        r"(?:^|[\s,{])type\s*[:=]\s*(?:user|human|operator|prompt)",
        re.IGNORECASE,
    )
    for span in spans:
        if any(marker in span for marker in prompt_markers) or structural_marker.search(span):
            return "non-prompt step contains a prompt-bearing marker"
        structured, parsed, parse_error = agy_parse_json(span)
        if parse_error:
            return parse_error
        if not parsed:
            continue
        if structured_user_prompt_marker(structured):
            return "non-prompt step contains a structured prompt-bearing marker"
    return None


def agy_unit_receipt(
    *,
    disposition: str,
    contract_id: str,
    contract_digest: str,
    signature: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": SOURCE_ADAPTER_CONTRACT_VERSION,
        "disposition": disposition,
        "contract_id": contract_id,
        "contract_digest": contract_digest,
        "signature": signature,
        "related_signatures": {},
        "related_evidence": {},
    }


def scan_agy_conversations(
    lifecycle: Any,
    cursor: dict[str, Any],
    *,
    days: int | None,
    budget: ScanBudget,
    limits: ResourceLimits | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    active_limits = limits or runtime_limits({})
    root = Path(lifecycle.AGY_CLI_CONVERSATIONS)
    coverage = {"agy-cli-conversations": empty_coverage()}
    counts = coverage["agy-cli-conversations"]
    empty_result = {
        "discovered": {},
        "processed": {},
        "adapted_unit_receipts": {},
        "excluded_unit_receipts": {},
        "errors": [],
        "unsupported": [],
        "pending_files": 0,
        "attempted_files": 0,
        "coverage": coverage,
    }
    if os.path.lexists(root) and root.is_symlink():
        counts["errors"] += 1
        return [], {
            **empty_result,
            "errors": ["agy-cli-conversations: configured conversation root is a symlink"],
        }
    home = getattr(lifecycle, "HOME", None)
    if home is None:
        counts["errors"] += 1
        return [], {
            **empty_result,
            "errors": ["agy-cli-conversations: configured HOME is unavailable for root custody"],
        }
    root_contract_error = agy_conversation_root_error(Path(home), root)
    if root_contract_error:
        counts["errors"] += 1
        return [], {
            **empty_result,
            "errors": [f"agy-cli-conversations: {root_contract_error}"],
        }
    if not root.exists():
        return [], empty_result
    if not root.is_dir():
        counts["errors"] += 1
        return [], {
            **empty_result,
            "errors": ["agy-cli-conversations: configured conversation root is not a directory"],
        }
    root_escape = source_path_error(root, containment_root=root)
    if root_escape:
        counts["errors"] += 1
        return [], {
            **empty_result,
            "errors": [f"agy-cli-conversations:{root}: {root_escape}"],
        }
    cutoff = None if days is None else dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400
    events: list[dict[str, Any]] = []
    discovered: dict[str, Any] = {}
    processed: dict[str, Any] = {}
    adapted_unit_receipts: dict[str, Any] = {}
    excluded_unit_receipts: dict[str, Any] = {}
    prior_adapted_receipts = cursor.get("adapted_unit_receipts") or {}
    prior_excluded_receipts = cursor.get("excluded_unit_receipts") or {}
    adapter_contract = source_adapter_contract()
    contract_digest = str(adapter_contract["digest"])
    errors: list[str] = []
    pending = 0
    attempted = 0
    database_paths: list[Path] = []
    discovery_truncated = False
    for candidate in root.rglob("*.db"):
        if len(database_paths) >= active_limits.max_discovery_units:
            discovery_truncated = True
            break
        database_paths.append(candidate)
    if discovery_truncated:
        pending += 1
        counts["pending"] += 1
        counts["errors"] += 1
        errors.append(
            f"agy-cli-conversations: database discovery exceeds bounded ceiling {active_limits.max_discovery_units}"
        )
        # The candidate iterator has no ordering contract.  Processing the first bounded subset
        # would therefore let filesystem enumeration order decide whether this family emits prompt
        # events before reporting the overflow.  Once limit + 1 is observed, fail the whole family
        # closed while preserving the hard traversal bound.
        return [], {
            **empty_result,
            "errors": errors,
            "pending_files": pending,
        }
    for path in sorted(database_paths):
        escape = source_path_error(path, containment_root=root)
        if escape:
            counts["errors"] += 1
            errors.append(f"agy-cli-conversations:{path}: {escape}")
            continue
        relative = path.relative_to(root)
        if len(relative.parts) != 1:
            counts["errors"] += 1
            errors.append(
                f"agy-cli-conversations:{path}: unsupported database path role; "
                "conversation databases must be direct children of the configured root"
            )
            continue
        storage_error = agy_conversation_storage_error(path)
        if storage_error:
            counts["errors"] += 1
            errors.append(f"agy-cli-conversations:{path}: {storage_error}")
            continue
        storage_signature = agy_storage_signature(path)
        if storage_signature is None:
            counts["errors"] += 1
            errors.append(f"agy-cli-conversations:{path}: source cannot be stat'ed")
            continue
        source_mtime = max(storage_signature["db_mtime_ns"], storage_signature["wal_mtime_ns"]) / 1_000_000_000
        if cutoff is not None and source_mtime < cutoff:
            continue
        key = cursor_unit_key("agy-cli-conversations", path)
        cached_file_signature = (cursor.get("files") or {}).get(key)
        cached_adapted_receipt = prior_adapted_receipts.get(key) if isinstance(prior_adapted_receipts, dict) else None
        cached_excluded_receipt = (
            prior_excluded_receipts.get(key) if isinstance(prior_excluded_receipts, dict) else None
        )
        cached_receipt = cached_adapted_receipt or cached_excluded_receipt
        cached_signature = (
            cached_file_signature
            if isinstance(cached_file_signature, dict)
            else (cached_receipt.get("signature") if isinstance(cached_receipt, dict) else None)
        )
        cache_generation_matches = bool(
            isinstance(cached_signature, dict)
            and all(cached_signature.get(field) == value for field, value in storage_signature.items())
        )
        signature = dict(cached_signature) if cache_generation_matches else {**storage_signature, "content_sha256": ""}
        discovered[key] = signature
        counts["discovered"] += 1
        cached_adapted = bool(
            cache_generation_matches
            and cached_file_signature == cached_signature
            and source_unit_receipt_matches(
                cached_adapted_receipt,
                disposition="adapted",
                contract_id="agy-conversation-v1",
                contract_digest=contract_digest,
                source="agy-cli-conversations",
                locator=str(path),
                signature=signature,
            )
        )
        cached_excluded = bool(
            cache_generation_matches
            and cached_file_signature is None
            and source_unit_receipt_matches(
                cached_excluded_receipt,
                disposition="excluded",
                contract_id="agy-conversation-nonprompt-v1",
                contract_digest=contract_digest,
                source="agy-cli-conversations",
                locator=str(path),
                signature=signature,
            )
        )
        if cached_adapted or cached_excluded:
            if agy_storage_signature(path) != storage_signature:
                counts["errors"] += 1
                errors.append(f"{key}: database or WAL changed during cache validation; cursor not advanced")
                continue
            if agy_conversation_storage_error(path):
                counts["errors"] += 1
                errors.append(f"{key}: SQLite sidecar custody changed during cache validation; cursor not advanced")
                continue
            if cached_adapted:
                processed[key] = signature
                adapted_unit_receipts[key] = cached_adapted_receipt
                counts["adapted"] += 1
                counts["converged"] += 1
            else:
                excluded_unit_receipts[key] = cached_excluded_receipt
                counts["excluded"] += 1
            continue
        if not budget.claim():
            pending += 1
            counts["pending"] += 1
            continue
        attempted += 1
        try:
            connection = sqlite3.connect(f"{path.resolve(strict=True).as_uri()}?mode=ro", uri=True)
        except (OSError, sqlite3.Error) as exc:
            counts["errors"] += 1
            errors.append(f"{key}: {exc}")
            continue
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN")
            schema_error = agy_steps_schema_error(connection)
            if schema_error:
                raise ValueError(schema_error)
            max_rows = active_limits.max_events_per_unit * 10
            record_count, source_bytes, limit_kind = bounded_sqlite_lengths(
                connection,
                "SELECT COALESCE(length(CAST(step_payload AS BLOB)), 0) + "
                "COALESCE(length(CAST(metadata AS BLOB)), 0) + "
                "COALESCE(length(CAST(task_details AS BLOB)), 0) + "
                "COALESCE(length(CAST(error_details AS BLOB)), 0) + "
                "COALESCE(length(CAST(render_info AS BLOB)), 0) FROM steps LIMIT ?",
                (),
                max_rows=max_rows,
                max_bytes=active_limits.max_source_bytes_per_unit,
            )
            if limit_kind == "rows":
                raise ValueError(f"SQLite row count {record_count} exceeds bounded ceiling {max_rows}")
            if limit_kind == "bytes":
                raise ValueError(
                    f"SQLite payload is {source_bytes} bytes; bounded ceiling is "
                    f"{active_limits.max_source_bytes_per_unit}"
                )
            rows = connection.execute(
                "SELECT idx, step_type, status, step_payload, metadata, task_details, error_details, "
                "render_info FROM steps ORDER BY idx LIMIT ?",
                (max_rows,),
            ).fetchall()
            content_sha256 = digest(
                [
                    [
                        sqlite_cell_fingerprint(row[column])
                        for column in (
                            "idx",
                            "step_type",
                            "status",
                            "step_payload",
                            "metadata",
                            "task_details",
                            "error_details",
                            "render_info",
                        )
                    ]
                    for row in rows
                ]
            )
            signature = {**storage_signature, "content_sha256": content_sha256}
            discovered[key] = signature
        except (sqlite3.Error, ValueError) as exc:
            counts["errors"] += 1
            errors.append(f"{key}: {exc}")
            connection.close()
            continue
        db_events: list[dict[str, Any]] = []
        db_error: str | None = None
        seen_indexes: set[int] = set()
        prompt_columns = tuple(str(column) for column in SOURCE_RECORD_SCHEMAS["agy-conversation-v1"]["prompt_columns"])
        max_candidates = int(SOURCE_RECORD_SCHEMAS["agy-conversation-v1"]["max_prompt_candidates_per_record"])
        for row in rows:
            step_type = row["step_type"]
            row_index = row["idx"]
            status = row["status"]
            if (
                isinstance(step_type, bool)
                or not isinstance(step_type, int)
                or step_type < 0
                or isinstance(row_index, bool)
                or not isinstance(row_index, int)
                or row_index < 0
                or isinstance(status, bool)
                or not isinstance(status, int)
                or status < 0
            ):
                db_error = f"{key}: malformed step identity: exact non-negative integers required"
                break
            if row_index in seen_indexes:
                db_error = f"{key}: malformed step identity: duplicate idx values are not allowed"
                break
            seen_indexes.add(row_index)
            if step_type != 14:
                for column in prompt_columns:
                    marker_error = agy_nonprompt_cell_error(
                        row[column],
                        column=column,
                        maximum=max_candidates,
                    )
                    if marker_error:
                        db_error = (
                            f"{key}: Agy step type {step_type} requires an explicit prompt adapter; "
                            "typed non-prompt exclusion rejected: "
                            f"{marker_error}"
                        )
                        break
                if db_error:
                    break
                continue
            candidates: list[tuple[str, int, str]] = []
            for column in prompt_columns:
                cell_candidates, candidate_error = agy_prompt_cell_candidates(
                    row[column],
                    column=column,
                    maximum=max_candidates,
                )
                if candidate_error:
                    db_error = f"{key}: Agy prompt step has malformed carrier metadata: {candidate_error}"
                    break
                candidates.extend(cell_candidates)
                if len(candidates) > max_candidates:
                    db_error = f"{key}: Agy prompt step exceeds bounded prompt-candidate ceiling {max_candidates}"
                    break
            if db_error:
                break
            if len(candidates) != 1:
                cardinality = "none" if not candidates else "multiple"
                db_error = f"{key}: Agy prompt step has {cardinality} grounded source segments; exactly one is required"
                break
            carrier_column, carrier_ordinal, text = candidates[0]
            task_body, body_kind = lifecycle.normalize_task_body(text)
            provenance, authority = (
                ("delegated_task_frame", "derived")
                if body_kind in {"flame_scaffold", "flame_with_task_body"}
                else ("unknown_user_input", "unknown")
            )
            db_events.append(
                {
                    "source": "agy-cli-conversations",
                    "session_ref": f"agy-cli-conversations:{path.stem}:{path}",
                    "event_ref": row_index,
                    "event_index": row_index,
                    "text_index": carrier_ordinal,
                    "source_locator": f"{path}#step:{row['idx']}",
                    "source_segment": carrier_column,
                    "timestamp": lifecycle.iso_from_ts(source_mtime),
                    "text": text,
                    "task_body": task_body if body_kind == "flame_with_task_body" else "",
                    "body_kind": body_kind,
                    "provenance": provenance,
                    "authority": authority,
                }
            )
            if len(db_events) > active_limits.max_events_per_unit:
                db_error = f"{key}: prompt occurrence count exceeds bounded ceiling {active_limits.max_events_per_unit}"
                break
        connection.close()
        if db_error:
            counts["errors"] += 1
            errors.append(db_error)
            continue
        if agy_storage_signature(path) != storage_signature:
            counts["errors"] += 1
            errors.append(f"{key}: database or WAL changed during scan; cursor not advanced")
            continue
        if agy_conversation_storage_error(path):
            counts["errors"] += 1
            errors.append(f"{key}: SQLite sidecar custody changed during scan; cursor not advanced")
            continue
        events.extend(db_events)
        if db_events:
            processed[key] = signature
            adapted_unit_receipts[key] = agy_unit_receipt(
                disposition="adapted",
                contract_id="agy-conversation-v1",
                contract_digest=contract_digest,
                signature=signature,
            )
            counts["adapted"] += 1
            counts["converged"] += 1
            counts["scanned"] += 1
        else:
            excluded_unit_receipts[key] = agy_unit_receipt(
                disposition="excluded",
                contract_id="agy-conversation-nonprompt-v1",
                contract_digest=contract_digest,
                signature=signature,
            )
            counts["excluded"] += 1
    final_root_error = agy_conversation_root_error(Path(home), root)
    if final_root_error or not root.is_dir():
        counts["errors"] += 1
        counts["adapted"] = 0
        counts["excluded"] = 0
        counts["converged"] = 0
        counts["scanned"] = 0
        errors.append("agy-cli-conversations: conversation root custody changed during scan; cursor not advanced")
        events = []
        processed = {}
        adapted_unit_receipts = {}
        excluded_unit_receipts = {}
    return events, {
        "discovered": discovered,
        "processed": processed,
        "adapted_unit_receipts": adapted_unit_receipts,
        "excluded_unit_receipts": excluded_unit_receipts,
        "errors": errors,
        "unsupported": [],
        "pending_files": pending,
        "attempted_files": attempted,
        "coverage": coverage,
    }


def scan_native_sources(
    paths: LedgerPaths,
    *,
    days: int | None,
    max_files: int,
    policy: dict[str, Any] | None = None,
    unbounded: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if max_files < 0:
        raise ValueError("max-files cannot be negative")
    if max_files == 0 and not unbounded:
        raise ValueError("max-files must be positive unless --unbounded is explicit")
    if unbounded and max_files not in {0, DEFAULT_MAX_WORK_UNITS}:
        raise ValueError("--unbounded cannot be combined with an explicit max-files value")
    lifecycle = load_lifecycle_module()
    policy_path = getattr(paths, "policy", REPO / "docs" / "prompt-corpus-policy.json")
    if policy is None:
        policy = load_policy(policy_path)
    limits = runtime_limits(policy)
    loaded_cursor, cursor_read_errors = load_json_strict(paths.cursor)
    if cursor_read_errors:
        raise ValueError("invalid stored source cursor: " + "; ".join(cursor_read_errors))
    cursor_shape_errors = validate_cursor_shape(loaded_cursor, role="stored")
    if cursor_shape_errors:
        raise ValueError("invalid stored source cursor: " + "; ".join(cursor_shape_errors))
    if loaded_cursor and isinstance(paths, LedgerPaths):
        marker, marker_errors = load_json_strict(paths.private_snapshot)
        cursor_signature = _path_signature(paths.cursor)
        marker_cursor_signature = ((marker.get("journal_signatures") or {}).get("cursor")) if marker else None
        if (
            marker_errors
            or not marker
            or marker.get("source_cursor_digest") != cursor_digest(loaded_cursor)
            or marker_cursor_signature != cursor_signature
        ):
            raise ValueError("stored source cursor is not bound to the current private checkpoint")
    base_cursor_digest = cursor_digest(loaded_cursor)
    base_revision = int(loaded_cursor.get("revision") or 0)
    adapter_contract = source_adapter_contract()
    source_cache_reset = bool(
        loaded_cursor.get("scanner_version") != SCANNER_VERSION
        or loaded_cursor.get("source_adapter_contract") != adapter_contract
    )
    prior_target = str(loaded_cursor.get("target_scope") or loaded_cursor.get("scope") or "")
    target_scope = "all" if days is None or prior_target in {"all", "partial:all"} else f"recent:{days}"
    prior_baseline_complete = bool(
        loaded_cursor.get("scanner_version") == SCANNER_VERSION
        and not source_cache_reset
        and loaded_cursor.get("all_baseline_complete")
        and loaded_cursor.get("scope") == "all"
    )
    # Once the target is all-history, every pass must rediscover the complete
    # manifest. Narrow discovery would either erase unresolved old work or make
    # cached full custody disagree with the current source-unit manifest.
    effective_days = days
    if target_scope == "all":
        effective_days = None
    cursor = dict(loaded_cursor)
    if source_cache_reset:
        cursor["files"] = {}
        cursor["unsupported_units"] = {}
        cursor["unresolved_units"] = []
        cursor["excluded_unit_receipts"] = {}
        cursor["adapted_unit_receipts"] = {}
        prior_baseline_complete = False

    regular_rows = regular_source_rows(lifecycle, effective_days, limits=limits)
    budgets = fair_scan_budgets(
        max_files,
        rotation=base_revision,
        active_lanes=active_scan_lanes(lifecycle, regular_rows),
        unbounded=unbounded,
    )
    events, regular = scan_regular_sources(
        lifecycle,
        cursor,
        days=effective_days,
        budget=budgets,
        rows=regular_rows,
        limits=limits,
    )
    opencode_events, opencode_scan = scan_opencode(
        lifecycle,
        cursor,
        days=effective_days,
        budget=budgets["opencode"],
        limits=limits,
    )
    agy_events, agy_scan = scan_agy_conversations(
        lifecycle,
        cursor,
        days=effective_days,
        budget=budgets["agy"],
        limits=limits,
    )
    events.extend(opencode_events)
    events.extend(agy_events)
    files = dict(regular["files"])
    files.update(opencode_scan["processed"])
    for key in agy_scan["discovered"]:
        files.pop(key, None)
    files.update(agy_scan["processed"])
    discovered = dict(regular["discovered"])
    discovered.update(opencode_scan["discovered"])
    discovered.update(agy_scan["discovered"])
    source_errors = [*regular["errors"], *opencode_scan["errors"], *agy_scan["errors"]]
    source_alias_blocker_counts = dict(regular.get("source_alias_blocker_counts") or {})
    unsupported = [*regular["unsupported"], *opencode_scan["unsupported"], *agy_scan["unsupported"]]
    pending_files = sum(int(result.get("pending_files") or 0) for result in (regular, opencode_scan, agy_scan))
    source_coverage = merge_coverage(
        regular["coverage"],
        opencode_scan["coverage"],
        agy_scan["coverage"],
    )
    raw_prior_unresolved_units = [] if source_cache_reset else loaded_cursor.get("unresolved_units")
    prior_unresolved_set = set(raw_prior_unresolved_units) if isinstance(raw_prior_unresolved_units, list) else set()
    # For receipt emission purposes, always read the full prior unresolved set from the
    # loaded cursor — even on a cache reset — so we can emit exclusion receipts for
    # keys that are cleared by a scanner-version bump (version-superseded) or by path
    # reclamation (source-missing). Without receipts, merge_cursor rejects every proposal
    # for any cleared key that cannot be proven resolved.
    _raw_all_prior = loaded_cursor.get("unresolved_units")
    _all_prior_unresolved_set = set(_raw_all_prior) if isinstance(_raw_all_prior, list) else set()
    # Build a (source, path) lookup from the current discovered keys so we can detect
    # which prior unresolved keys are covered by a newly-keyed (version-superseded)
    # entry in the proposed manifest. Those do not need source-missing receipts —
    # merge_cursor handles them via its own version-superseded exception.
    _discovered_by_source_path: set[tuple[str, str]] = set()
    for _dk in discovered:
        if isinstance(_dk, str):
            _dp = _dk.split(":", 2)
            if len(_dp) == 3:
                _discovered_by_source_path.add((_dp[1], _dp[2]))
    # Partition prior unresolved OLD-scanner-version keys. After a version bump a key
    # can never be rediscovered under its recorded form, so each old key is either
    # version-superseded (its (source, path) reappears under the current key format —
    # merge_cursor's own exception resolves it, no receipt needed) or source-missing
    # (the pair is gone entirely: reclaimed path, or a deleted virtual key such as
    # opencode-db#session:... — resolved below with an exclusion receipt). Same-version
    # units that vanish keep the fail-closed "previously tracked source obligations are
    # unavailable" error instead — a missing volume must surface as an error, never as
    # a silent exclusion.
    _current_scan_prefix = f"scan-v{SCANNER_VERSION}"
    _missing_source_keys_early: set[str] = set()
    _version_superseded_keys_early: set[str] = set()
    for _key in _all_prior_unresolved_set - set(discovered):
        if not isinstance(_key, str):
            continue
        _parts = _key.split(":", 2)
        if len(_parts) != 3 or not _parts[0].startswith("scan-v") or _parts[0] == _current_scan_prefix:
            continue
        if (_parts[1], _parts[2]) in _discovered_by_source_path:
            _version_superseded_keys_early.add(_key)
        else:
            _missing_source_keys_early.add(_key)
    missing_prior_unresolved: set[str] = set()
    if effective_days is None:
        missing_obligation_sources: set[str] = set()
        missing_prior_unresolved = prior_unresolved_set - set(discovered)
        # Keys already resolved by the missing-source path or by a version-superseded
        # newer-key do not represent genuine "source unavailable" obligations — exclude them.
        for key in sorted(missing_prior_unresolved - _missing_source_keys_early - _version_superseded_keys_early):
            parts = key.split(":", 2) if isinstance(key, str) else []
            source = parts[1] if len(parts) == 3 and parts[0].startswith("scan-v") else "unknown"
            missing_obligation_sources.add(source)
        prior_families = {} if source_cache_reset else loaded_cursor.get("source_families")
        prior_families = prior_families if isinstance(prior_families, dict) else {}
        for source, prior_counts in prior_families.items():
            if not isinstance(source, str) or not isinstance(prior_counts, dict):
                continue
            prior_discovered = int(prior_counts.get("discovered") or 0)
            prior_unresolved = sum(int(prior_counts.get(field) or 0) for field in ("pending", "errors", "unsupported"))
            prior_activity = sum(
                int(prior_counts.get(field) or 0)
                for field in ("discovered", "converged", "adapted", "excluded", "pending", "errors", "unsupported")
            )
            current_counts = coverage_row(source_coverage, source)
            current_discovered = int(current_counts.get("discovered") or 0)
            missing_obligation = bool(
                (
                    prior_activity
                    and current_discovered == 0
                    and not source_family_container_available(lifecycle, source)
                )
                or (prior_unresolved and current_discovered < prior_discovered)
                or source in missing_obligation_sources
            )
            if not missing_obligation:
                continue
            current_counts["errors"] += 1
            source_errors.append(f"{source}: previously tracked source obligations are unavailable")
            missing_obligation_sources.discard(source)
        for source in sorted(missing_obligation_sources):
            coverage_row(source_coverage, source)["errors"] += 1
            source_errors.append(f"{source}: previously tracked source obligations are unavailable")
    unsupported_units = dict(regular["unsupported_units"])
    for counts in source_coverage.values():
        counts["unsupported"] = 0
    for key in unsupported_units:
        parts = key.split(":", 2)
        source = parts[1] if len(parts) == 3 and parts[0].startswith("scan-v") else "unknown"
        coverage_row(source_coverage, source)["unsupported"] += 1
    adapter_gaps = sorted(
        source
        for source, counts in source_coverage.items()
        if int(counts.get("errors") or 0) or int(counts.get("unsupported") or 0)
    )
    adapter_gap_routes = build_adapter_gap_routes(adapter_gaps, policy)
    excluded_unit_receipts = dict(regular["excluded_unit_receipts"])
    for key in agy_scan["discovered"]:
        excluded_unit_receipts.pop(key, None)
    excluded_unit_receipts.update(agy_scan.get("excluded_unit_receipts") or {})
    adapted_unit_receipts = dict(regular["adapted_unit_receipts"])
    for key in opencode_scan["discovered"]:
        adapted_unit_receipts.pop(key, None)
    adapted_unit_receipts.update(opencode_scan.get("adapted_unit_receipts") or {})
    for key in agy_scan["discovered"]:
        adapted_unit_receipts.pop(key, None)
    adapted_unit_receipts.update(agy_scan.get("adapted_unit_receipts") or {})
    adapted_unit_receipts_digest = digest(adapted_unit_receipts)
    source_adapter_counts = dict(
        sorted(
            Counter(
                str(receipt.get("contract_id") or "unknown")
                for receipt in adapted_unit_receipts.values()
                if isinstance(receipt, dict)
            ).items()
        )
    )
    adapted_source_count = len(adapted_unit_receipts)
    # Emit source-missing exclusion receipts for the pre-computed missing keys.
    # These paths have been reclaimed from disk and will never re-enter discovery;
    # without receipts, merge_cursor's invariant rejects every future proposal.
    _now_utc = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    _missing_source_keys = _missing_source_keys_early
    for _key in sorted(_missing_source_keys):
        if _key not in excluded_unit_receipts:
            excluded_unit_receipts[_key] = {
                "version": SOURCE_ADAPTER_CONTRACT_VERSION,
                "disposition": "excluded",
                "contract_id": SOURCE_MISSING_EXCLUSION_ID,
                "contract_digest": adapter_contract["digest"],
                "related_signatures": {},
                "related_evidence": {"observed_missing_at": _now_utc},
            }
    # Remove resolved missing-source keys and version-superseded keys from the
    # "unresolved" pool so they do not re-appear in unresolved_units on future scans.
    # Version-superseded keys are covered by the newer-version key in discovered;
    # they need not be tracked separately.
    missing_prior_unresolved -= _missing_source_keys
    missing_prior_unresolved -= _version_superseded_keys_early
    # Count missing-source units as "discovered" in source_coverage so the
    # family totals stay consistent with source_unit_count (validator invariant).
    for _key in sorted(_missing_source_keys):
        _parts = _key.split(":", 2)
        _src = _parts[1] if len(_parts) == 3 and _parts[0].startswith("scan-v") else "unknown"
        coverage_row(source_coverage, _src)["discovered"] += 1
    excluded_unit_receipts_digest = digest(excluded_unit_receipts)
    source_exclusion_counts = dict(
        sorted(
            Counter(
                str(receipt.get("contract_id") or "unknown")
                for receipt in excluded_unit_receipts.values()
                if isinstance(receipt, dict)
            ).items()
        )
    )
    excluded_source_count = len(excluded_unit_receipts)
    for counts in source_coverage.values():
        counts["excluded"] = 0
        counts["adapted"] = 0
    for key in excluded_unit_receipts:
        parts = key.split(":", 2)
        source = parts[1] if len(parts) == 3 and parts[0].startswith("scan-v") else "unknown"
        coverage_row(source_coverage, source)["excluded"] += 1
    for key in adapted_unit_receipts:
        parts = key.split(":", 2)
        source = parts[1] if len(parts) == 3 and parts[0].startswith("scan-v") else "unknown"
        coverage_row(source_coverage, source)["adapted"] += 1
    # Include missing-source keys in source_units so merge_cursor's invariant
    # sees them as resolved (they are now in excluded_unit_receipts too).
    source_units = sorted(set(discovered) | _missing_source_keys)
    source_unit_count = len(source_units)
    source_units_digest = digest(source_units)
    unsupported_source_count = len(unsupported_units)
    unsupported_units_digest = digest(unsupported_units)
    resolved_units = {
        key
        for key, signature in discovered.items()
        if files.get(key) == signature
        or (
            isinstance(excluded_unit_receipts.get(key), dict)
            and excluded_unit_receipts[key].get("signature") == signature
        )
    }
    current_unresolved_units = set(discovered) - resolved_units
    if effective_days is None:
        unresolved_units = sorted(current_unresolved_units | missing_prior_unresolved)
    else:
        preserved_unresolved = set(prior_unresolved_set)
        preserved_unresolved -= set(discovered)
        preserved_unresolved -= _missing_source_keys
        preserved_unresolved -= _version_superseded_keys_early
        unresolved_units = sorted(preserved_unresolved | current_unresolved_units)
    unresolved_unit_count = len(unresolved_units)
    unresolved_units_digest = digest(unresolved_units)
    incomplete = bool(pending_files or source_errors or unresolved_units or adapter_gaps)
    scope = f"partial:{target_scope}" if incomplete else target_scope
    all_baseline_complete = (
        target_scope == "all" and not incomplete and (effective_days is None or prior_baseline_complete)
    )
    stable_coverage = {
        source: {
            key: int(counts.get(key) or 0)
            for key in ("discovered", "converged", "adapted", "excluded", "pending", "errors", "unsupported")
        }
        for source, counts in source_coverage.items()
    }
    manifest = {
        "target_scope": target_scope,
        "effective_horizon_days": effective_days,
        "units": discovered,
        "coverage": stable_coverage,
        "adapter_gaps": adapter_gaps,
        "adapter_gap_routes": adapter_gap_routes,
        "source_unit_count": source_unit_count,
        "source_units_digest": source_units_digest,
        "unsupported_source_count": unsupported_source_count,
        "unsupported_units_digest": unsupported_units_digest,
        "unresolved_unit_count": unresolved_unit_count,
        "unresolved_units_digest": unresolved_units_digest,
        "source_adapter_contract": adapter_contract,
        "excluded_source_count": excluded_source_count,
        "source_exclusion_counts": source_exclusion_counts,
        "excluded_unit_receipts_digest": excluded_unit_receipts_digest,
        "adapted_source_count": adapted_source_count,
        "source_adapter_counts": source_adapter_counts,
        "adapted_unit_receipts_digest": adapted_unit_receipts_digest,
        "source_alias_blocker_counts": source_alias_blocker_counts,
        "resource_limits": {key: value for key, value in vars(limits).items()},
        "work_units_unbounded": unbounded,
        "prior_all_manifest": (
            loaded_cursor.get("all_source_manifest_digest")
            if prior_baseline_complete and effective_days is not None
            else None
        ),
    }
    source_manifest_digest = digest(manifest)
    all_source_manifest_digest = (
        source_manifest_digest if all_baseline_complete else loaded_cursor.get("all_source_manifest_digest")
    )
    updated = {
        # Compare-and-swap request metadata. The core writer consumes these
        # fields but excludes them from semantic cursor state and its digest.
        "base_cursor_digest": base_cursor_digest,
        "base_revision": base_revision,
        # An all-history pass has an exact complete manifest, so its parsed
        # cache must replace (not union with) prior custody. Exact CAS protects
        # this legitimate deletion path; recent scans still preserve keys that
        # are outside their horizon.
        "replace_files": source_cache_reset or effective_days is None,
        "version": 1,
        "scanner_version": SCANNER_VERSION,
        "scope": scope,
        "target_scope": target_scope,
        "horizon_days": None if target_scope == "all" else days,
        "effective_horizon_days": effective_days,
        "all_baseline_complete": all_baseline_complete,
        "pending_files": pending_files,
        "source_errors": source_errors,
        "source_unit_count": source_unit_count,
        "source_units": source_units,
        "source_units_digest": source_units_digest,
        "unsupported_source_count": unsupported_source_count,
        "unsupported_source_examples": unsupported[:100],
        "unsupported_units": unsupported_units,
        "unsupported_units_digest": unsupported_units_digest,
        "unresolved_unit_count": unresolved_unit_count,
        "unresolved_units": unresolved_units,
        "unresolved_units_digest": unresolved_units_digest,
        "source_adapter_contract": adapter_contract,
        "excluded_source_count": excluded_source_count,
        "source_exclusion_counts": source_exclusion_counts,
        "excluded_unit_receipts": excluded_unit_receipts,
        "excluded_unit_receipts_digest": excluded_unit_receipts_digest,
        "adapted_source_count": adapted_source_count,
        "source_adapter_counts": source_adapter_counts,
        "adapted_unit_receipts": adapted_unit_receipts,
        "adapted_unit_receipts_digest": adapted_unit_receipts_digest,
        "source_alias_blocker_counts": source_alias_blocker_counts,
        "excluded_file_keys": regular.get("excluded_file_keys") or [],
        "adapter_gaps": adapter_gaps,
        "adapter_gap_routes": adapter_gap_routes,
        "source_coverage": source_coverage,
        "source_families": source_coverage,
        "work_units_used": sum(budget.used for budget in budgets.values()),
        "work_units_unbounded": unbounded,
        "resource_limits": {key: value for key, value in vars(limits).items()},
        "source_discovery_spec": source_discovery_spec(lifecycle),
        "source_container_signatures": {
            "opencode-db": opencode_scan.get("container_signature"),
        },
        "last_scan_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_manifest_digest": source_manifest_digest,
        "all_source_manifest_digest": all_source_manifest_digest,
        "files": files,
    }
    attest_source_scan(updated, scanner_code_digest=current_source_scanner_code_digest())
    cursor_errors = validate_source_adapter_cursor(updated)
    if cursor_errors:
        raise ValueError("scanner produced invalid source cursor: " + "; ".join(cursor_errors))
    return events, updated


def rebind_checkpoint(paths: LedgerPaths) -> list[str]:
    """Rebuild and write the private checkpoint from the live cursor and journals.

    This is the recovery effector for the "cursor not bound to current private
    checkpoint" error: it replays the trusted rebuild logic that --check uses
    read-only and atomically rewrites the marker + public projections when, and
    only when, the cursor is readable/shape-valid and the journals load without
    errors.  No force flag; corrupt journals refuse unconditionally.

    Semantic validation findings (e.g. "operator repeats exceed limit without
    assessment", "operator occurrence lacks atom coverage") do NOT block the
    reseal: the trusted write lane (update_ledger, the --scan --write path)
    seals snapshots with those findings recorded in snapshot["validation"] and
    lets --check report them — this effector mirrors that exactly.  A stricter
    gate here would wedge recovery on any estate carrying chronic semantic
    debt, which is precisely the estate that needs the effector.

    Root-cause of the drift: the beat (or any scan from another worktree) can
    write the shared cursor file after the marker was sealed, advancing its
    mtime and digest.  _path_signature hashes size/mtime/mode, so any write to
    source-cursor.json — even an idempotent-content write — breaks the binding.
    """
    loaded_cursor, cursor_read_errors = load_json_strict(paths.cursor)
    if cursor_read_errors:
        return ["stored source cursor unreadable: " + "; ".join(cursor_read_errors)]
    if not loaded_cursor:
        return ["stored source cursor is empty; run a scan first to initialize it"]
    shape_errors = validate_cursor_shape(loaded_cursor, role="stored")
    if shape_errors:
        return ["invalid stored source cursor shape: " + "; ".join(shape_errors)]

    policy = load_policy(paths.policy)
    occurrence_rows, atom_rows, event_errors = load_event_journal(paths.event_journal)
    outcome_rows, outcome_errors = load_jsonl_strict(paths.outcome_journal)
    raw_errors = validate_raw_references(paths, occurrence_rows, verify_content=True)
    all_journal_errors = [*event_errors, *outcome_errors, *raw_errors]
    if all_journal_errors:
        return ["journals contain errors; refusing to rebind: " + "; ".join(str(e) for e in all_journal_errors)]

    snapshot = build_snapshot(
        occurrence_rows,
        atom_rows,
        outcome_rows,
        policy,
        loaded_cursor,
        journal_errors=[],
        evidence_root=paths.root,
    )
    # Semantic validation findings stay recorded in snapshot["validation"]
    # (exactly as update_ledger seals them); --check remains their reporter.

    public = public_projection(snapshot)
    seal = prompt_authority_seal(snapshot, public=public)
    markdown = render_markdown(public, policy)
    next_marker = private_marker(snapshot, public, seal, paths=paths)

    public_bytes = _json_bytes(public)
    seal_bytes = _json_bytes(seal)
    marker_bytes = _json_bytes(next_marker)
    markdown_bytes = markdown.encode("utf-8")

    paths.private_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(paths.public_snapshot, public_bytes, mode=0o644)
    atomic_write_bytes(paths.public_seal, seal_bytes, mode=0o644)
    atomic_write_bytes(paths.public_markdown, markdown_bytes, mode=0o644)
    # Write the marker last: a crash before this line leaves check_ledger red.
    atomic_write_bytes(paths.private_snapshot, marker_bytes, mode=0o600)
    return []


def check_cursor_state(paths: LedgerPaths) -> list[str]:
    """Cheap read-only source-cursor coherence probe (seconds, no journal replay).

    Proves the ask-lineage control plane can converge: the cursor parses and is
    shape-valid, it is bound to the current private checkpoint, its scanner
    version is current, and no unresolved obligation is orphaned on a stale
    scan-version key (the merge-deadlock class fixed by the version-superseded
    exception — a fresh drain pass clears them, and this probe fails until it has).
    """

    errors: list[str] = []
    loaded_cursor, cursor_read_errors = load_json_strict(paths.cursor)
    if cursor_read_errors:
        return ["stored source cursor unreadable: " + "; ".join(cursor_read_errors)]
    if not loaded_cursor:
        return ["stored source cursor is empty; run a scan first"]
    shape_errors = validate_cursor_shape(loaded_cursor, role="stored")
    if shape_errors:
        return ["invalid stored source cursor: " + "; ".join(shape_errors)]
    marker, marker_errors = load_json_strict(paths.private_snapshot)
    if (
        marker_errors
        or not marker
        or marker.get("source_cursor_digest") != cursor_digest(loaded_cursor)
        or ((marker.get("journal_signatures") or {}).get("cursor")) != _path_signature(paths.cursor)
    ):
        errors.append("stored source cursor is not bound to the current private checkpoint")
    if loaded_cursor.get("scanner_version") != SCANNER_VERSION:
        errors.append(
            f"cursor scanner_version {loaded_cursor.get('scanner_version')} != current {SCANNER_VERSION};"
            " next scan will reset the source cache"
        )
    current_prefix = f"scan-v{SCANNER_VERSION}:"
    orphaned = [
        key
        for key in (loaded_cursor.get("unresolved_units") or [])
        if isinstance(key, str) and not key.startswith(current_prefix)
    ]
    if orphaned:
        errors.append(
            f"{len(orphaned)} unresolved obligations are orphaned on stale scan-version keys"
            " (run an unbounded drain pass to resolve them)"
        )
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", action="store_true", help="scan changed native source files")
    parser.add_argument("--all", action="store_true", help="scan all local history")
    parser.add_argument("--days", type=int, default=14, help="recent native scan horizon")
    parser.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_MAX_WORK_UNITS,
        help=f"maximum changed source work units across every adapter (default {DEFAULT_MAX_WORK_UNITS})",
    )
    parser.add_argument(
        "--unbounded",
        action="store_true",
        help="explicitly disable only the work-unit ceiling; byte/event/protocol ceilings remain",
    )
    parser.add_argument("--events-jsonl", type=Path, help="provider-neutral normalized events")
    parser.add_argument("--outcomes-jsonl", type=Path, help="evidence-backed atom outcomes")
    parser.add_argument(
        "--reclassify",
        action="store_true",
        help="re-run the configured classifier over a bounded set of existing occurrences",
    )
    parser.add_argument("--write", action="store_true", help="append journals and refresh projections")
    parser.add_argument("--check", action="store_true", help="verify journal/projection convergence")
    parser.add_argument(
        "--check-cursor",
        action="store_true",
        help="cheap read-only cursor coherence probe (checkpoint binding, scanner version, no orphaned obligations)",
    )
    parser.add_argument(
        "--rebind-checkpoint",
        action="store_true",
        help=(
            "recovery effector: rebuild and atomically reseal the private checkpoint from the live cursor and "
            "journals; refuses if the cursor or journals are corrupt; semantic validation findings are sealed "
            "and recorded exactly as --scan --write does (reported by --check)"
        ),
    )
    parser.add_argument("--require-scope", choices=("all",), help="fail unless source scope matches")
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("LIMEN_ROOT", REPO)))
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--public-markdown", type=Path)
    parser.add_argument("--public-snapshot", type=Path)
    parser.add_argument("--public-seal", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument(
        "--source-home",
        type=Path,
        help="explicit source-discovery home (used by isolated canaries; process HOME is unchanged)",
    )
    return parser.parse_args()


def main() -> int:
    global SOURCE_HOME_OVERRIDE
    args = parse_args()
    SOURCE_HOME_OVERRIDE = args.source_home.resolve() if args.source_home else None
    paths = LedgerPaths.for_root(
        args.root.resolve(),
        private_root=args.private_root.resolve() if args.private_root else None,
        public_markdown=args.public_markdown.resolve() if args.public_markdown else None,
        public_snapshot=args.public_snapshot.resolve() if args.public_snapshot else None,
        public_seal=args.public_seal.resolve() if args.public_seal else None,
        policy=args.policy.resolve() if args.policy else None,
    )
    if args.rebind_checkpoint:
        errors = rebind_checkpoint(paths)
        if errors:
            for error in errors:
                print(f"FAIL: {error}")
            return 1
        print("prompt-atom-checkpoint: rebound")
        return 0

    if args.check_cursor:
        errors = check_cursor_state(paths)
        if errors:
            for error in errors:
                print(f"FAIL: {error}")
            return 1
        print("prompt-atom-cursor: PASS")
        return 0

    if args.check:
        errors = check_ledger(paths, require_scope=args.require_scope)
        if errors:
            for error in errors:
                print(f"FAIL: {error}")
            return 1
        print("prompt-atom-ledger: PASS")
        return 0

    policy = load_policy(paths.policy)
    events: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    cursor: dict[str, Any] | None = None
    if args.scan:
        if args.max_files < 0:
            print("FAIL: --max-files cannot be negative", file=sys.stderr)
            return 2
        if args.max_files == 0 and not args.unbounded:
            print("FAIL: --max-files must be positive unless --unbounded is explicit", file=sys.stderr)
            return 2
        if args.unbounded and args.max_files not in {0, DEFAULT_MAX_WORK_UNITS}:
            print("FAIL: --unbounded cannot be combined with --max-files", file=sys.stderr)
            return 2
        try:
            events, cursor = scan_native_sources(
                paths,
                days=None if args.all else max(0, args.days),
                max_files=args.max_files,
                policy=policy,
                unbounded=args.unbounded,
            )
        except ValueError as exc:
            print(f"FAIL: cannot scan prompt sources: {exc}", file=sys.stderr)
            return 2
    if args.events_jsonl:
        events.extend(load_jsonl(args.events_jsonl))
    if args.outcomes_jsonl:
        outcomes = load_jsonl(args.outcomes_jsonl)
    if args.reclassify:
        try:
            events.extend(existing_reclassification_events(paths, policy))
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"FAIL: cannot prepare reclassification: {exc}")
            return 1
    classifier = classify_events(
        events,
        command=os.environ.get("LIMEN_PROMPT_CLASSIFIER_CMD"),
        policy=policy,
    )
    events = classifier.events
    if classifier.error:
        print(f"WARN: runtime classifier unavailable; using structural fallback ({classifier.error})", file=sys.stderr)
    if not args.write:
        print(
            f"prompt-atom-ledger: would ingest {len(events)} occurrence event(s) and "
            f"{len(outcomes)} outcome row(s); re-run with --write"
        )
        return 0
    try:
        snapshot = update_ledger(paths, events=events, outcomes=outcomes, cursor=cursor)
    except ValueError as exc:
        print(f"FAIL: cannot update prompt atom ledger: {exc}", file=sys.stderr)
        return 1
    appended = snapshot["appended"]
    print(
        "prompt-atom-ledger: "
        f"{snapshot['coverage']['occurrences']} occurrences, {snapshot['coverage']['atoms']} atoms; "
        f"appended {appended['occurrences']}/{appended['atoms']}/{appended['outcomes']}; "
        f"changed={str(snapshot['write_changed']).lower()}; "
        f"work_units={int((cursor or {}).get('work_units_used') or 0)}"
    )
    if cursor and cursor.get("source_errors"):
        for error in cursor["source_errors"]:
            print(f"FAIL: {error}")
        return 1
    if not (snapshot.get("validation") or {}).get("ok"):
        for error in (snapshot.get("validation") or {}).get("errors") or []:
            print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
