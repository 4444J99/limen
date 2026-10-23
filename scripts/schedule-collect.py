#!/usr/bin/env python3
"""Bounded offline native evidence collection. No provider, launch or admission effects.

Inputs and exports are PRIVATE. Standard output contains counts/status only.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

try:
    import fcntl
except ImportError:
    fcntl = None

from _schedule_evidence import (
    EvidenceStore,
    _private_path,
    normalize_artifact,
    normalize_chatgpt,
    normalize_grok_email,
)

MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 1000
LOCK_TIMEOUT_SECONDS = 10


class SnapshotDurabilityError(OSError):
    """Replacement is visible but persistence is unconfirmed; do not advance checkpoints."""


@contextmanager
def export_lock(target):
    if fcntl is None:
        raise OSError("private export locking is unsupported")
    # This separate inode survives target replacement. Never unlink it: waiters must all
    # contend on the same lock across revisions and across first creation.
    lock_path = _private_path(target.with_name(f".{target.name}.lock"))
    descriptor = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("private export lock deadline exceeded") from None
                time.sleep(0.01)
        yield
    finally:
        os.close(descriptor)  # closes/releases only this writer's lock, not the stable path


def read_json(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("input exceeds bound")
    return json.loads(data)


def write_snapshot(path, snapshot, expected_sha256):
    target = _private_path(Path(path), create=False)
    with export_lock(target):
        target = _private_path(target, create=False)
        if target.exists():
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            if expected_sha256 != digest:
                raise ValueError("snapshot revision changed")
        elif expected_sha256 is not None:
            raise ValueError("expected snapshot missing")
        fd, name = tempfile.mkstemp(prefix=".schedule-export-", dir=target.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(snapshot, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, target)
            try:
                directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                raise SnapshotDurabilityError(
                    "snapshot replacement visible; directory sync failed; readback required before checkpoint"
                ) from None
        finally:
            if os.path.exists(name):
                os.unlink(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--source", choices=("chatgpt", "grok-email", "artifact"), required=True)
    for option in ("input", "db", "observed-at", "account-ref", "owner-ref"):
        collect.add_argument(f"--{option}", required=True)
    export = commands.add_parser("export")
    export.add_argument("--db", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--expected-sha256")
    incoming = commands.add_parser("import")
    incoming.add_argument("--db", required=True)
    incoming.add_argument("--input", required=True)
    assess = commands.add_parser("assess")
    for option in ("db", "observation-id", "owner-ref", "predicate", "evidence-ref", "artifact-sha256"):
        assess.add_argument(f"--{option}", required=True)
    assess.add_argument("--status", choices=("accepted", "delivered"), required=True)
    assess.add_argument("--destination-ref")
    checkpoint = commands.add_parser("checkpoint")
    for option in ("db", "source-id", "cursor"):
        checkpoint.add_argument(f"--{option}", required=True)
    checkpoint.add_argument("--observation-id", action="append", default=[])
    checkpoint.add_argument("--empty-window", action="store_true")
    checkpoint.add_argument("--complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command not in {"collect", "import"} and not Path(args.db).is_file():
            raise ValueError("evidence database missing")
        # Normalize the ENTIRE batch before opening/writing the database.
        if args.command == "collect":
            payload = read_json(args.input)
            payload = payload if isinstance(payload, list) else [payload]
            if not 0 < len(payload) <= MAX_ROWS or any(not isinstance(row, dict) for row in payload):
                raise ValueError("invalid bounded collection batch")
            if args.source == "artifact":
                if any(
                    row.get("account_ref") != args.account_ref or row.get("owner_ref") != args.owner_ref
                    for row in payload
                ):
                    raise ValueError("artifact scope mismatch")
                rows = [normalize_artifact(row, observed_at=args.observed_at) for row in payload]
            else:
                adapter = normalize_chatgpt if args.source == "chatgpt" else normalize_grok_email
                rows = [
                    adapter(row, observed_at=args.observed_at, account_ref=args.account_ref, owner_ref=args.owner_ref)
                    for row in payload
                ]
        with EvidenceStore(Path(args.db)) as store:
            if args.command == "collect":
                result = store.ingest(rows)
            elif args.command == "import":
                result = store.import_snapshot(read_json(args.input))
            elif args.command == "export":
                target = Path(args.output)
                if target.resolve() == Path(args.db).resolve() or (
                    target.exists() and os.path.samefile(target, args.db)
                ):
                    raise ValueError("export cannot replace evidence database")
                value = store.export()
                write_snapshot(args.output, value, args.expected_sha256)
                result = {"observations": len(value["observations"]), "assessments": len(value["assessments"])}
            elif args.command == "assess":
                store.assess(
                    args.observation_id,
                    status=args.status,
                    owner_ref=args.owner_ref,
                    predicate=args.predicate,
                    evidence_ref=args.evidence_ref,
                    artifact_sha256=args.artifact_sha256,
                    destination_ref=args.destination_ref,
                )
                result = {"assessment": args.status}
            else:
                if len(args.observation_id) > MAX_ROWS or bool(args.observation_id) == args.empty_window:
                    raise ValueError("explicit bounded checkpoint receipt required")
                known = {row["observation_id"] for row in store.export()["observations"]}
                if not set(args.observation_id) <= known:
                    raise ValueError("checkpoint observation not durably ingested")
                result = {"advanced": store.checkpoint(args.source_id, read_json(args.cursor), complete=args.complete)}
        print(json.dumps(dict(status="ok", **result), sort_keys=True))
        return 0
    except SnapshotDurabilityError:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "snapshot replacement visible; directory sync failed; readback required before checkpoint",
                }
            ),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        # Source exceptions can contain private paths, references and payload fragments.
        print(json.dumps({"status": "error", "error": "invalid or unavailable private evidence"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
