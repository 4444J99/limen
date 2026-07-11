#!/usr/bin/env python3
"""Incrementally atomize the private prompt corpus and publish a redacted control view."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import importlib.util
import json
import os
import re
import shlex
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REPO = Path(__file__).resolve().parents[1]
CLI_SRC = REPO / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.prompt_corpus import (  # noqa: E402
    LedgerPaths,
    check_ledger,
    cursor_digest,
    digest,
    load_event_journal,
    load_json,
    load_jsonl,
    load_policy,
    occurrence_from_event,
    read_raw_object,
    structural_segments,
    update_ledger,
)


SCANNER_VERSION = 2
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
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


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
    return next((value for value in candidates if value in path.name), candidates[0])


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
    if body_kind == "session_context":
        return "continuation_summary", "derived"
    if body_kind in {"flame_scaffold", "flame_with_task_body"}:
        return "delegated_task_frame", "derived"
    if bool(obj.get("isSidechain")):
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


def prompt_texts_for(lifecycle: Any, source: str, obj: dict[str, Any]) -> list[str]:
    """Extract prompt surfaces without turning transport/tool output into people."""

    if source.startswith("claude"):
        if source == "claude-tasks":
            return lifecycle.prompt_texts(source, obj)
        typ = obj.get("type")
        if typ in {"last-prompt", "queue-operation"}:
            return []
        if typ == "user":
            message = obj.get("message")
            if not isinstance(message, dict) or message.get("role") not in (None, "user"):
                return []
            content = message.get("content")
            if isinstance(content, str):
                return [content] if content.strip() else []
            if isinstance(content, list):
                texts: list[str] = []
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "text":
                        continue
                    texts.extend(lifecycle.text_from_content(block.get("text")))
                return texts
            return []
    parser_source = "gemini-tmp-agy" if source == "gemini-tmp" else source
    return lifecycle.prompt_texts(parser_source, obj)


def strict_json_records(
    path: Path,
    *,
    limits: ResourceLimits | None = None,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Read one supported JSON source atomically or return a closed error.

    The lifecycle compatibility reader intentionally skips malformed rows.  A
    source cursor cannot: skipping a torn line and recording the file signature
    would permanently certify missing operator input.
    """

    active_limits = limits or runtime_limits({})
    is_jsonl = path.suffix == ".jsonl" or path.name == "history.jsonl"
    if not is_jsonl and path.suffix != ".json":
        return [], None, False
    try:
        size = path.stat().st_size
        if size > active_limits.max_source_bytes_per_unit:
            return (
                [],
                f"{path}: source is {size} bytes; bounded ceiling is {active_limits.max_source_bytes_per_unit}",
                True,
            )
        if is_jsonl:
            rows: list[dict[str, Any]] = []
            with path.open(encoding="utf-8", errors="strict") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    if len(rows) >= active_limits.max_events_per_unit:
                        return (
                            [],
                            f"{path}: record count exceeds bounded ceiling {active_limits.max_events_per_unit}",
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
        if len(value) > active_limits.max_events_per_unit:
            return (
                [],
                f"{path}: record count exceeds bounded ceiling {active_limits.max_events_per_unit}",
                True,
            )
        return list(value), None, True
    return [], f"{path}: JSON source is not an object or object array", True


def source_path_error(path: Path) -> str | None:
    """Reject a symlinked source that escapes an explicit isolated source home."""

    if SOURCE_HOME_OVERRIDE is None:
        return None
    try:
        root = SOURCE_HOME_OVERRIDE.resolve(strict=True)
        candidate = path.resolve(strict=True)
    except OSError as exc:
        return f"source path cannot be resolved inside isolated home: {exc}"
    if candidate == root or root in candidate.parents:
        return None
    return "source path escapes isolated source home"


def _discover_candidate(
    rows: DiscoveredRows,
    *,
    source: str,
    path: Path,
    cutoff: float | None,
    limit: int,
    known_paths: set[str],
) -> bool:
    """Add one eligible source or return False when discovery reached its cap."""

    try:
        if not path.is_file():
            return True
        stat = path.stat()
    except OSError:
        return True
    if rows.discovered_count >= limit:
        rows.truncated_source = source
        return False
    rows.discovered_count += 1
    if cutoff is not None and stat.st_mtime < cutoff:
        return True
    path_key = str(path)
    if path_key in known_paths:
        return True
    escape = source_path_error(path)
    if escape:
        rows.discovery_errors.append((source, f"{source}:{path}: {escape}"))
        return True
    known_paths.add(path_key)
    rows.append({"source": source, "path": path, "mtime": stat.st_mtime})
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
        for row in generic:
            if not _discover_candidate(
                rows,
                source=str(row["source"]),
                path=Path(row["path"]),
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
        if event.get("provenance") != "operator_typed":
            continue
        unmatched_effective_input = bool(echo_hashes) and digest(str(event.get("text") or "")) not in echo_hashes
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
    discovered: dict[str, Any] = {}
    coverage: dict[str, dict[str, int]] = {}
    for source in existing_regular_families(lifecycle):
        coverage_row(coverage, source)
    errors: list[str] = []
    unsupported: list[str] = []
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
    for source, error in getattr(active_rows, "discovery_errors", []):
        coverage_row(coverage, source)["errors"] += 1
        errors.append(error)
    truncated_source = getattr(active_rows, "truncated_source", None)
    if truncated_source:
        pending += 1
        coverage_row(coverage, str(truncated_source))["pending"] += 1
        errors.append(
            f"{truncated_source}: source discovery exceeded bounded ceiling {active_limits.max_discovery_units}"
        )
    for row in active_rows:
        source = str(row["source"])
        lane_budget = source_scan_budget(budget, source)
        counts = coverage_row(coverage, source)
        path = Path(row["path"])
        signature = file_signature(path)
        if signature is None:
            counts["discovered"] += 1
            counts["errors"] += 1
            errors.append(f"{source}:{path}: source disappeared or cannot be stat'ed")
            continue
        key = cursor_unit_key(source, path)
        discovered[key] = signature
        counts["discovered"] += 1
        if unsupported_units.get(key) == signature:
            counts["unsupported"] += 1
            unsupported.append(key)
            continue
        if files.get(key) == signature:
            counts["converged"] += 1
            continue
        if not lane_budget.claim():
            pending += 1
            counts["pending"] += 1
            continue
        attempted += 1
        escape = source_path_error(path)
        if escape:
            counts["errors"] += 1
            errors.append(f"{source}:{path}: {escape}")
            continue
        records, error, supported = strict_json_records(path, limits=active_limits)
        if not supported:
            counts["unsupported"] += 1
            unsupported.append(key)
            unsupported_units[key] = signature
            continue
        if error:
            counts["errors"] += 1
            errors.append(f"{source}:{error}")
            continue
        file_session_id = canonical_file_session_id(source, path, records)
        file_is_forked = codex_file_is_forked(source, records)
        file_events: list[dict[str, Any]] = []
        for event_index, obj in enumerate(records):
            texts = prompt_texts_for(lifecycle, source, obj)
            for text_index, text in enumerate(texts):
                task_body, body_kind = lifecycle.normalize_task_body(text)
                provenance, authority = provenance_for(source, obj, body_kind)
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
                    }
                )
                if len(file_events) > active_limits.max_events_per_unit:
                    break
            if len(file_events) > active_limits.max_events_per_unit:
                break
        if len(file_events) > active_limits.max_events_per_unit:
            counts["errors"] += 1
            errors.append(
                f"{source}:{path}: prompt occurrence count exceeds bounded ceiling {active_limits.max_events_per_unit}"
            )
            continue
        if file_signature(path) != signature:
            counts["errors"] += 1
            errors.append(f"{source}:{path}: source changed during scan; cursor not advanced")
            continue
        events.extend(
            normalize_codex_file_events(
                source,
                file_events,
                forked=file_is_forked,
            )
        )
        files[key] = signature
        unsupported_units.pop(key, None)
        processed += 1
        counts["converged"] += 1
        counts["scanned"] += 1
    return events, {
        "files": files,
        "discovered": discovered,
        "processed_files": processed,
        "attempted_files": attempted,
        "pending_files": pending,
        "errors": errors,
        "unsupported": unsupported,
        "unsupported_units": unsupported_units,
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
    if not path.exists():
        return [], {
            "discovered": {},
            "processed": {},
            "errors": [],
            "unsupported": [],
            "pending_files": 0,
            "attempted_files": 0,
            "coverage": coverage,
        }
    escape = source_path_error(path)
    if escape:
        counts["discovered"] += 1
        counts["errors"] += 1
        return [], {
            "discovered": {},
            "processed": {},
            "errors": [f"opencode-db:{path}: {escape}"],
            "unsupported": [],
            "pending_files": 0,
            "attempted_files": 0,
            "coverage": coverage,
        }
    signature = file_signature(path)
    if signature is None:
        counts["discovered"] += 1
        counts["errors"] += 1
        return [], {
            "discovered": {},
            "processed": {},
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
    errors: list[str] = []
    pending = 0
    attempted = 0
    try:
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
            errors.append(f"opencode-db: session discovery exceeds bounded ceiling {active_limits.max_discovery_units}")
        for session in sessions:
            session_id = str(session["id"])
            unit_key = cursor_unit_key(
                "opencode-db",
                f"{path}#session:{digest(session_id)[:24]}",
            )
            unit_signature = {
                "time_created": session["time_created"],
                "time_updated": session["time_updated"],
            }
            discovered[unit_key] = unit_signature
            counts["discovered"] += 1
            if (cursor.get("files") or {}).get(unit_key) == unit_signature:
                counts["converged"] += 1
                continue
            if not budget.claim():
                pending += 1
                counts["pending"] += 1
                continue
            attempted += 1
            max_rows = active_limits.max_events_per_unit * 10
            message_count, message_bytes, message_limit = bounded_sqlite_lengths(
                connection,
                "SELECT COALESCE(length(CAST(data AS BLOB)), 0) FROM message WHERE session_id=? LIMIT ?",
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
            messages = connection.execute(
                "SELECT id, time_created, data FROM message WHERE session_id=? ORDER BY time_created, id",
                (session_id,),
            ).fetchall()
            parts_by_message: dict[str, list[sqlite3.Row]] = {}
            for part in connection.execute(
                "SELECT message_id, data FROM part WHERE session_id=? ORDER BY time_created, id",
                (session_id,),
            ):
                parts_by_message.setdefault(str(part["message_id"]), []).append(part)
            session_events: list[dict[str, Any]] = []
            session_error: str | None = None
            for event_index, message in enumerate(messages):
                try:
                    data = json.loads(message["data"]) if message["data"] else {}
                except (TypeError, ValueError) as exc:
                    session_error = f"{unit_key}: malformed message {message['id']}: {exc}"
                    break
                if not isinstance(data, dict):
                    session_error = f"{unit_key}: non-object message {message['id']}"
                    break
                if data.get("role") != "user":
                    continue
                parts = parts_by_message.get(str(message["id"]), [])
                part_types: set[str] = set()
                for part in parts:
                    try:
                        part_data = json.loads(part["data"]) if part["data"] else {}
                    except (TypeError, ValueError) as exc:
                        session_error = f"{unit_key}: malformed part for {message['id']}: {exc}"
                        break
                    if not isinstance(part_data, dict):
                        session_error = f"{unit_key}: non-object part for {message['id']}"
                        break
                    part_types.add(str(part_data.get("type") or ""))
                if session_error:
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
            counts["converged"] += 1
            counts["scanned"] += 1
    except sqlite3.Error as exc:
        counts["errors"] += 1
        errors.append(f"opencode-db:{path}: {exc}")
    finally:
        connection.close()
    return events, {
        "discovered": discovered,
        "processed": processed,
        "errors": errors,
        "unsupported": [],
        "pending_files": pending,
        "attempted_files": attempted,
        "coverage": coverage,
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
    if not root.exists():
        return [], {
            "discovered": {},
            "processed": {},
            "errors": [],
            "unsupported": [],
            "pending_files": 0,
            "attempted_files": 0,
            "coverage": coverage,
        }
    root_escape = source_path_error(root)
    if root_escape:
        counts["errors"] += 1
        return [], {
            "discovered": {},
            "processed": {},
            "errors": [f"agy-cli-conversations:{root}: {root_escape}"],
            "unsupported": [],
            "pending_files": 0,
            "attempted_files": 0,
            "coverage": coverage,
        }
    cutoff = None if days is None else dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400
    events: list[dict[str, Any]] = []
    discovered: dict[str, Any] = {}
    processed: dict[str, Any] = {}
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
        errors.append(
            f"agy-cli-conversations: database discovery exceeds bounded ceiling {active_limits.max_discovery_units}"
        )
    for path in sorted(database_paths):
        escape = source_path_error(path)
        if escape:
            counts["errors"] += 1
            errors.append(f"agy-cli-conversations:{path}: {escape}")
            continue
        signature = file_signature(path)
        if signature is None:
            counts["discovered"] += 1
            counts["errors"] += 1
            errors.append(f"agy-cli-conversations:{path}: source cannot be stat'ed")
            continue
        try:
            stat = path.stat()
        except OSError as exc:
            counts["errors"] += 1
            errors.append(f"agy-cli-conversations:{path}: cannot read source metadata: {exc}")
            continue
        if cutoff is not None and stat.st_mtime < cutoff:
            continue
        key = cursor_unit_key("agy-cli-conversations", path)
        discovered[key] = signature
        counts["discovered"] += 1
        if (cursor.get("files") or {}).get(key) == signature:
            counts["converged"] += 1
            continue
        if not budget.claim():
            pending += 1
            counts["pending"] += 1
            continue
        attempted += 1
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            counts["errors"] += 1
            errors.append(f"{key}: {exc}")
            continue
        connection.row_factory = sqlite3.Row
        try:
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
                "SELECT idx, step_type, step_payload, metadata, task_details, error_details, "
                "render_info FROM steps ORDER BY idx LIMIT ?",
                (max_rows,),
            ).fetchall()
        except (sqlite3.Error, ValueError) as exc:
            counts["errors"] += 1
            errors.append(f"{key}: {exc}")
            connection.close()
            continue
        db_events: list[dict[str, Any]] = []
        db_error: str | None = None
        for row in rows:
            try:
                step_type = int(row["step_type"])
                row_index = int(row["idx"])
            except (TypeError, ValueError) as exc:
                db_error = f"{key}: malformed step identity: {exc}"
                break
            if step_type != 14:
                continue
            spans: list[str] = []
            for column in ("step_payload", "metadata", "task_details", "error_details", "render_info"):
                value = row[column]
                if isinstance(value, str):
                    spans.append(value)
                else:
                    spans.extend(lifecycle.blob_text_spans(value))
            text = lifecycle.agy_prompt_from_spans(spans)
            if not text:
                continue
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
                    "text_index": 0,
                    "source_locator": f"{path}#step:{row['idx']}",
                    "timestamp": lifecycle.iso_from_ts(stat.st_mtime),
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
        if file_signature(path) != signature:
            counts["errors"] += 1
            errors.append(f"{key}: source changed during scan; cursor not advanced")
            continue
        events.extend(db_events)
        processed[key] = signature
        counts["converged"] += 1
        counts["scanned"] += 1
    return events, {
        "discovered": discovered,
        "processed": processed,
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
    loaded_cursor = load_json(paths.cursor) or {}
    base_cursor_digest = cursor_digest(loaded_cursor)
    base_revision = int(loaded_cursor.get("revision") or 0)
    prior_target = str(loaded_cursor.get("target_scope") or loaded_cursor.get("scope") or "")
    target_scope = "all" if days is None or prior_target in {"all", "partial:all"} else f"recent:{days}"
    prior_baseline_complete = bool(
        loaded_cursor.get("scanner_version") == SCANNER_VERSION
        and loaded_cursor.get("all_baseline_complete")
        and loaded_cursor.get("scope") == "all"
    )
    # A partial all-history pass remains an all-history drain.  Narrowing its
    # discovery window would make undiscovered old work disappear from pending
    # and falsely promote the cursor to ``all``.
    effective_days = days
    if target_scope == "all" and not prior_baseline_complete:
        effective_days = None
    cursor = dict(loaded_cursor)
    if loaded_cursor.get("scanner_version") != SCANNER_VERSION:
        cursor["files"] = {}
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
    files.update(agy_scan["processed"])
    discovered = dict(regular["discovered"])
    discovered.update(opencode_scan["discovered"])
    discovered.update(agy_scan["discovered"])
    source_errors = [*regular["errors"], *opencode_scan["errors"], *agy_scan["errors"]]
    unsupported = [*regular["unsupported"], *opencode_scan["unsupported"], *agy_scan["unsupported"]]
    pending_files = sum(int(result.get("pending_files") or 0) for result in (regular, opencode_scan, agy_scan))
    source_coverage = merge_coverage(
        regular["coverage"],
        opencode_scan["coverage"],
        agy_scan["coverage"],
    )
    adapter_gaps = sorted(
        source
        for source, counts in source_coverage.items()
        if int(counts.get("errors") or 0) or int(counts.get("unsupported") or 0)
    )
    adapter_gap_routes = build_adapter_gap_routes(adapter_gaps, policy)
    incomplete = bool(pending_files or source_errors or unsupported or adapter_gaps)
    scope = f"partial:{target_scope}" if incomplete else target_scope
    all_baseline_complete = (
        target_scope == "all" and not incomplete and (effective_days is None or prior_baseline_complete)
    )
    stable_coverage = {
        source: {
            key: int(counts.get(key) or 0) for key in ("discovered", "converged", "pending", "errors", "unsupported")
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
        "version": 1,
        "scanner_version": SCANNER_VERSION,
        "scope": scope,
        "target_scope": target_scope,
        "horizon_days": None if target_scope == "all" else days,
        "effective_horizon_days": effective_days,
        "all_baseline_complete": all_baseline_complete,
        "pending_files": pending_files,
        "source_errors": source_errors,
        "unsupported_source_count": len(unsupported),
        "unsupported_source_examples": unsupported[:100],
        "unsupported_units": regular["unsupported_units"],
        "adapter_gaps": adapter_gaps,
        "adapter_gap_routes": adapter_gap_routes,
        "source_coverage": source_coverage,
        "source_families": source_coverage,
        "work_units_used": sum(budget.used for budget in budgets.values()),
        "work_units_unbounded": unbounded,
        "resource_limits": {key: value for key, value in vars(limits).items()},
        "last_scan_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_manifest_digest": source_manifest_digest,
        "all_source_manifest_digest": all_source_manifest_digest,
        "files": files,
    }
    return events, updated


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
    parser.add_argument("--require-scope", choices=("all",), help="fail unless source scope matches")
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("LIMEN_ROOT", REPO)))
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--public-markdown", type=Path)
    parser.add_argument("--public-snapshot", type=Path)
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
        policy=args.policy.resolve() if args.policy else None,
    )
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
    snapshot = update_ledger(paths, events=events, outcomes=outcomes, cursor=cursor)
    appended = snapshot["appended"]
    print(
        "prompt-atom-ledger: "
        f"{snapshot['coverage']['occurrences']} occurrences, {snapshot['coverage']['atoms']} atoms; "
        f"appended {appended['occurrences']}/{appended['atoms']}/{appended['outcomes']}; "
        f"changed={str(snapshot['write_changed']).lower()}"
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
