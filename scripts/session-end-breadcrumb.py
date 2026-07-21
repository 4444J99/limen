#!/usr/bin/env python3
"""Constant-time Claude SessionEnd breadcrumb producer.

The hook path performs one bounded JSON decode and one append.  It never runs
Git, reads a transcript, scans worktrees, invokes a model, or waits for a slow
consumer.  The heartbeat-owned consumer performs those jobs later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "limen.session_end_breadcrumb.v1"
MAX_INPUT_BYTES = 1024 * 1024
MAX_SESSION_ID = 256
MAX_CWD = 4096


def default_output(environ: Mapping[str, str] | None = None) -> Path:
    """Return the one host-stable queue shared by all installed/runtime versions."""

    environ = os.environ if environ is None else environ
    configured = environ.get("LIMEN_SESSION_END_BREADCRUMBS")
    if configured:
        return Path(configured).expanduser()
    state_home = environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home).expanduser() / "limen" / "session-end-breadcrumbs.jsonl"
    home = Path(environ.get("HOME") or Path.home()).expanduser()
    return home / ".local" / "state" / "limen" / "session-end-breadcrumbs.jsonl"


def _bounded(value: object, limit: int) -> str:
    text = str(value or "").replace("\x00", "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def _decode(raw: bytes) -> tuple[dict[str, Any], bool]:
    if len(raw) > MAX_INPUT_BYTES:
        return {}, False
    try:
        value = json.loads(raw or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}, False
    return (value, True) if isinstance(value, dict) else ({}, False)


def _transcript_marker(payload: Mapping[str, Any]) -> str:
    """Return a metadata-only marker that changes when a resumed transcript grows."""

    raw_path = payload.get("transcript_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return ""
    try:
        stat_result = Path(raw_path).expanduser().stat()
    except OSError:
        return ""
    return ":".join(
        str(value)
        for value in (
            stat_result.st_dev,
            stat_result.st_ino,
            stat_result.st_size,
            stat_result.st_mtime_ns,
        )
    )


def breadcrumb(
    raw: bytes,
    *,
    source: str,
    environ: Mapping[str, str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Build one redacted occurrence breadcrumb from a bounded hook payload."""

    environ = os.environ if environ is None else environ
    payload, valid = _decode(raw)
    raw_digest = hashlib.sha256(raw[:MAX_INPUT_BYTES]).hexdigest()
    session_id = _bounded(payload.get("session_id") or environ.get("CLAUDE_SESSION_ID"), MAX_SESSION_ID)
    if not session_id:
        session_id = f"unknown-{raw_digest[:24]}"
    cwd = _bounded(
        payload.get("cwd") or environ.get("CLAUDE_PROJECT_DIR") or environ.get("PWD"),
        MAX_CWD,
    )
    ended_epoch = round(time.time() if now is None else now, 6)
    occurrence_marker = _transcript_marker(payload)
    occurrence_basis = "transcript" if occurrence_marker else "fallback"
    if not occurrence_marker:
        # A source-neutral payload identity lets the consumer pair the global and
        # project deliveries even when they straddle an arbitrary time boundary.
        # The delivery id below remains unique so a repeated same-source end starts
        # a fresh occurrence when no readable transcript revision is available.
        occurrence_marker = f"payload:{raw_digest}"
    event_id = hashlib.sha256(f"claude\0{session_id}\0{raw_digest}\0{occurrence_marker}".encode()).hexdigest()
    delivery_id = hashlib.sha256(
        f"{event_id}\0{source}\0{ended_epoch}\0{os.getpid()}\0{time.monotonic_ns()}".encode()
    ).hexdigest()
    return {
        "schema": SCHEMA,
        "event_id": event_id,
        "delivery_id": delivery_id,
        "occurrence_basis": occurrence_basis,
        "provider": "claude",
        "session_id": session_id,
        "source": _bounded(source, 32) or "unknown",
        "ended_epoch": ended_epoch,
        "cwd": cwd,
        "payload_valid": valid,
        "payload_sha256": raw_digest,
    }


def append_breadcrumb(path: Path, event: Mapping[str, Any]) -> bool:
    """Append exactly one bounded line; failure is fail-open for SessionEnd."""

    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink() or path.parent.is_symlink():
            return False
        encoded = (json.dumps(dict(event), sort_keys=True, separators=(",", ":")) + "\n").encode()
        if len(encoded) > 8192:
            return False
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            return os.write(fd, encoded) == len(encoded)
        finally:
            os.close(fd)
    except OSError:
        return False


def produce(
    raw: bytes,
    *,
    output: Path,
    source: str,
    environ: Mapping[str, str] | None = None,
    now: float | None = None,
) -> bool:
    """Create and append one breadcrumb, returning false only on a fail-open write."""

    return append_breadcrumb(output, breadcrumb(raw, source=source, environ=environ, now=now))


def main() -> int:
    """Run the constant-time stdin-to-queue producer CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="project")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output.expanduser() if args.output else default_output()
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    produce(raw, output=output, source=args.source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
