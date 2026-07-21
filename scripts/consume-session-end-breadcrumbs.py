#!/usr/bin/env python3
"""Idempotently drain constant-time SessionEnd breadcrumbs on heartbeat.

Each session owns one bounded receipt keyed by a hash of its session ID. Global
and project producers therefore converge on the same work. Slow consumers have
finite timeouts, at most three attempts, output digests instead of logs, and
independent status so a successful consumer is never rerun for reassurance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

BREADCRUMB_SCHEMA = "limen.session_end_breadcrumb.v1"
CURSOR_SCHEMA = "limen.session_end_cursor.v1"
RECEIPT_SCHEMA = "limen.session_end_consumer_receipt.v1"
MAX_BATCH_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 4096
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: bytes
    duration_ms: int
    timed_out: bool = False


@dataclass(frozen=True)
class ConsumerSpec:
    name: str
    timeout_seconds: int
    command: Callable[[Path, Mapping[str, Any]], Sequence[str]]


Runner = Callable[[Sequence[str], int, Path], CommandResult]


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


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)


def _load_json(path: Path, default: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return value if isinstance(value, dict) else dict(default)


def _session_key(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()


def _normalized_event(line: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(line).hexdigest()
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        event = {}
    valid = bool(
        isinstance(event, dict)
        and event.get("schema") == BREADCRUMB_SCHEMA
        and isinstance(event.get("session_id"), str)
        and event.get("session_id")
        and isinstance(event.get("event_id"), str)
    )
    if not valid:
        return {
            "schema": BREADCRUMB_SCHEMA,
            "event_id": digest,
            "provider": "unknown",
            "session_id": f"invalid-{digest[:24]}",
            "source": "malformed-line",
            "ended_epoch": 0,
            "cwd": "",
            "payload_valid": False,
            "payload_sha256": digest,
        }
    return {
        "schema": BREADCRUMB_SCHEMA,
        "event_id": str(event["event_id"])[:128],
        "provider": str(event.get("provider") or "unknown")[:32],
        "session_id": str(event["session_id"])[:256],
        "source": str(event.get("source") or "unknown")[:32],
        "ended_epoch": float(event.get("ended_epoch") or 0),
        "cwd": str(event.get("cwd") or "")[:4096],
        "payload_valid": event.get("payload_valid") is True,
        "payload_sha256": str(event.get("payload_sha256") or digest)[:64],
    }


def _initial_consumer_state(payload_valid: bool) -> dict[str, dict[str, Any]]:
    names = ["compatibility_closeout", *(spec.name for spec in default_consumer_specs())]
    if not payload_valid:
        return {name: {"status": "not_applicable", "attempts": 0} for name in names}
    return {name: {"status": "pending", "attempts": 0} for name in names}


def _receipt_for(event: Mapping[str, Any], existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if existing and existing.get("schema") == RECEIPT_SCHEMA:
        receipt = dict(existing)
        sources = {str(value) for value in receipt.get("sources") or []}
        sources.add(str(event["source"]))
        receipt["sources"] = sorted(sources)
        receipt["last_seen_epoch"] = max(
            float(receipt.get("last_seen_epoch") or 0),
            float(event.get("ended_epoch") or 0),
        )
        return receipt
    return {
        "schema": RECEIPT_SCHEMA,
        "event_id": event["event_id"],
        "session_id": event["session_id"],
        "session_key": _session_key(str(event["session_id"])),
        "provider": event["provider"],
        "sources": [event["source"]],
        "first_seen_epoch": float(event.get("ended_epoch") or 0),
        "last_seen_epoch": float(event.get("ended_epoch") or 0),
        "cwd": event.get("cwd") or "",
        "payload_valid": event.get("payload_valid") is True,
        "payload_sha256": event.get("payload_sha256"),
        "consumers": _initial_consumer_state(event.get("payload_valid") is True),
    }


def ingest(
    source: Path,
    *,
    cursor_path: Path,
    receipt_root: Path,
    max_bytes: int = MAX_BATCH_BYTES,
) -> tuple[list[Path], int]:
    cursor = _load_json(cursor_path, {"schema": CURSOR_SCHEMA, "offset": 0, "device": None, "inode": None})
    try:
        stat_result = source.stat()
    except OSError:
        return [], 0
    offset = int(cursor.get("offset") or 0)
    if (
        offset < 0
        or offset > stat_result.st_size
        or cursor.get("device") not in {None, stat_result.st_dev}
        or cursor.get("inode") not in {None, stat_result.st_ino}
    ):
        offset = 0
    with source.open("rb") as handle:
        handle.seek(offset)
        chunk = handle.read(max(1, min(max_bytes, MAX_BATCH_BYTES)))
    complete = chunk.rfind(b"\n") + 1
    if complete <= 0:
        return [], 0
    paths: list[Path] = []
    for line in chunk[:complete].splitlines():
        if not line:
            continue
        event = _normalized_event(line)
        receipt_path = receipt_root / f"{_session_key(str(event['session_id']))}.json"
        existing = _load_json(receipt_path, {}) if receipt_path.exists() else None
        _atomic_json(receipt_path, _receipt_for(event, existing))
        paths.append(receipt_path)
    _atomic_json(
        cursor_path,
        {
            "schema": CURSOR_SCHEMA,
            "offset": offset + complete,
            "device": stat_result.st_dev,
            "inode": stat_result.st_ino,
        },
    )
    return list(dict.fromkeys(paths)), len(paths)


def default_consumer_specs() -> tuple[ConsumerSpec, ...]:
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
        ),
    )


def run_bounded(command: Sequence[str], timeout_seconds: int, cwd: Path) -> CommandResult:
    started = time.monotonic()
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "LIMEN_ROOT": str(cwd)},
        )
        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                exit_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                exit_code = process.wait()
        output.seek(0)
        captured = output.read(MAX_OUTPUT_BYTES + 1)
    duration_ms = round((time.monotonic() - started) * 1000)
    return CommandResult(
        exit_code=124 if timed_out else exit_code,
        output=captured[:MAX_OUTPUT_BYTES],
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


def _append_compatibility(root: Path, receipt: Mapping[str, Any]) -> CommandResult:
    started = time.monotonic()
    record = {
        "ts": int(float(receipt.get("last_seen_epoch") or 0)),
        "sid": receipt["session_id"],
        "cwd": receipt.get("cwd") or "",
        "branch": "unknown",
    }
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path = root / "logs" / "session-closeout.jsonl"
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            written = os.write(fd, encoded)
        finally:
            os.close(fd)
        exit_code = 0 if written == len(encoded) else 1
    except OSError:
        exit_code = 1
    return CommandResult(exit_code, b"", round((time.monotonic() - started) * 1000))


def _result_state(prior: Mapping[str, Any], result: CommandResult) -> dict[str, Any]:
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
        "output_truncated": len(result.output) >= MAX_OUTPUT_BYTES,
    }


def process_receipt(
    path: Path,
    *,
    root: Path,
    runner: Runner = run_bounded,
    specs: Sequence[ConsumerSpec] | None = None,
    deadline: float | None = None,
) -> tuple[int, int]:
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
            lambda spec=spec: runner(spec.command(root, receipt), spec.timeout_seconds, root),
        )
        for spec in specs
    )
    for name, invoke in ordered:
        state = dict(consumers.get(name) or {"status": "pending", "attempts": 0})
        if state.get("status") in {"complete", "failed", "not_applicable"}:
            continue
        if int(state.get("attempts") or 0) >= MAX_ATTEMPTS:
            state["status"] = "failed"
            consumers[name] = state
            continue
        if deadline is not None and time.monotonic() >= deadline:
            break
        result = invoke()
        attempted += 1
        state = _result_state(state, result)
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
    ingested_paths, ingested = ingest(source, cursor_path=cursor_path, receipt_root=receipt_root)
    pending = [
        path
        for path in sorted(receipt_root.glob("*.json"))
        if path not in ingested_paths
        and any(
            state.get("status") in {"pending", "retry"}
            for state in (_load_json(path, {}).get("consumers") or {}).values()
            if isinstance(state, dict)
        )
    ]
    candidates = list(dict.fromkeys([*ingested_paths, *pending]))[: max(1, max_sessions)]
    deadline = time.monotonic() + max(1, runway_seconds)
    attempted = completed = processed = 0
    for path in candidates:
        if time.monotonic() >= deadline:
            break
        count, successes = process_receipt(path, root=root, runner=runner, specs=specs, deadline=deadline)
        attempted += count
        completed += successes
        processed += 1
    return {
        "ingested": ingested,
        "processed": processed,
        "attempted": attempted,
        "completed": completed,
    }


def check(cursor_path: Path, receipt_root: Path) -> int:
    cursor = _load_json(cursor_path, {})
    if cursor and cursor.get("schema") != CURSOR_SCHEMA:
        print("session-end-consumer --check: FAIL — invalid cursor")
        return 1
    for path in receipt_root.glob("*.json"):
        if _load_json(path, {}).get("schema") != RECEIPT_SCHEMA:
            print(f"session-end-consumer --check: FAIL — invalid receipt {path.name}")
            return 1
    print("session-end-consumer --check: OK")
    return 0


def main() -> int:
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
        args.receipt_root.expanduser()
        if args.receipt_root
        else root / "logs" / "session-end-consumer-receipts"
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
