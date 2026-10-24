#!/usr/bin/env python3
"""Bounded offline native evidence collection. No provider, launch or admission effects.

Inputs and exports are PRIVATE. Standard output contains counts/status only.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import uuid

try:
    import fcntl
except ImportError:
    fcntl = None

import _schedule_evidence as evidence_module
from _schedule_evidence import (
    EvidenceStore,
    _private_path,
    _time,
    normalize_artifact,
    normalize_chatgpt,
    normalize_grok_email,
    validate_account_binding,
)

MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 1000
LOCK_TIMEOUT_SECONDS = 10


class SnapshotDurabilityError(OSError):
    """Replacement is visible but persistence is unconfirmed; do not advance checkpoints."""


class SnapshotReadbackError(OSError):
    """A visible replacement does not match the intended bytes; commit state is uncertain."""


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


def read_json(path, *, with_digest=False):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("input exceeds bound")
    value = json.loads(data)
    return (value, hashlib.sha256(data).hexdigest()) if with_digest else value


def write_snapshot(path, snapshot, expected_sha256):
    encoded = json.dumps(snapshot, sort_keys=True).encode("utf-8")
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
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
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
            if target.read_bytes() != encoded:
                raise SnapshotReadbackError("snapshot replacement visible; readback mismatch")
            return hashlib.sha256(encoded).hexdigest()
        finally:
            if os.path.exists(name):
                os.unlink(name)


def begin_receipt(args, started_at):
    """Reserve a new private invocation record before effects; never replace an old receipt."""
    target = Path(args.receipt)
    protected = [Path(value) for option in ("db", "input", "output", "account_binding", "profile_observation")
                 if (value := getattr(args, option, None)) is not None]
    database = Path(args.db)
    protected.extend(database.with_name(database.name + suffix) for suffix in ("-journal", "-wal", "-shm"))
    if args.command == "export":
        output = Path(args.output)
        protected.append(output.with_name(f".{output.name}.lock"))
    for candidate in (target, target.with_name(f".{target.name}.lock")):
        for value in protected:
            if (candidate.resolve() == value.resolve()
                    or (candidate.exists() and value.exists() and os.path.samefile(candidate, value))):
                raise ValueError("execution receipt conflicts with an input or output")
    receipt = {
        "schema": "limen.schedule_collection_execution.v1",
        "evidence_kind": "local-cli-self-report", "invocation_id": str(uuid.uuid4()),
        "claim_limit": "Local self-report; operation_outcome precedes receipt publication. Actual process exit requires the execution-tool result. No independent authentication or native scheduled execution proof.",
        "command": args.command, "started_at": started_at.isoformat(), "finished_at": None,
        "source_files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (Path(__file__), Path(evidence_module.__file__))},
        "caller_attested": {"source": getattr(args, "source", None), "source_window": None,
                            "observed_at": None},
        "account_binding": {"status": "unvalidated" if getattr(args, "account_binding", None) is not None
                            or getattr(args, "profile_observation", None) is not None else "not-configured"},
        "operation_outcome": {"status": "started", "exit_code": None}, "result": None,
        "observation_ids": [], "input_sha256": None, "export_sha256": None,
    }
    revision = write_snapshot(target, receipt, None)
    return receipt, revision


def collection_window(args):
    if (args.window_start is None) != (args.window_end is None):
        raise ValueError("source window requires both boundaries")
    if args.window_start is None:
        return None
    start, end = _time(args.window_start), _time(args.window_end)
    if start is None or end is None or start >= end:
        raise ValueError("invalid source window")
    return {"start": args.window_start, "end": args.window_end}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--source", choices=("chatgpt", "grok-email", "artifact"), required=True)
    for option in ("input", "db", "observed-at", "account-ref", "owner-ref"):
        collect.add_argument(f"--{option}", required=True)
    for option in ("account-binding", "profile-observation", "receipt", "window-start", "window-end"):
        collect.add_argument(f"--{option}")
    export = commands.add_parser("export")
    export.add_argument("--db", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--expected-sha256")
    export.add_argument("--receipt")
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
    started_at = datetime.now(timezone.utc)
    receipt, receipt_revision = None, None
    exit_code = 2
    try:
        if getattr(args, "receipt", None) is not None:
            receipt, receipt_revision = begin_receipt(args, started_at)
        if args.command not in {"collect", "import"} and not Path(args.db).is_file():
            raise ValueError("evidence database missing")
        # Normalize the ENTIRE batch before opening/writing the database.
        if args.command == "collect":
            if (args.account_binding is None) != (args.profile_observation is None):
                raise ValueError("account binding requires a profile observation")
            window = collection_window(args)
            payload, input_digest = read_json(args.input, with_digest=True)
            if receipt is not None:
                receipt["input_sha256"] = input_digest
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
            binding_result = None
            if args.account_binding is not None:
                binding = read_json(_private_path(Path(args.account_binding), create=False))
                profile = read_json(_private_path(Path(args.profile_observation), create=False))
                binding_result = validate_account_binding(
                    binding, profile, source=args.source, account_ref=args.account_ref,
                    rows=rows, now=datetime.now(timezone.utc),
                )
            if receipt is not None:
                receipt["caller_attested"].update(source_window=window, observed_at=args.observed_at)
                if binding_result is not None:
                    receipt["account_binding"] = binding_result
        with EvidenceStore(Path(args.db)) as store:
            if args.command == "collect":
                result = store.ingest(rows)
                if receipt is not None:
                    receipt["observation_ids"] = sorted({row["observation_id"] for row in rows})
            elif args.command == "import":
                result = store.import_snapshot(read_json(args.input))
            elif args.command == "export":
                target = Path(args.output)
                if target.resolve() == Path(args.db).resolve() or (
                    target.exists() and os.path.samefile(target, args.db)
                ):
                    raise ValueError("export cannot replace evidence database")
                value = store.export()
                digest = write_snapshot(args.output, value, args.expected_sha256)
                if receipt is not None:
                    receipt["export_sha256"] = digest
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
        result = dict(status="ok", **result)
        exit_code = 0
    except SnapshotReadbackError:
        result = {"status": "error", "commit_state": "uncertain",
                  "error": "snapshot replacement visible; readback mismatch; evidence may have committed; readback required before checkpoint"}
    except SnapshotDurabilityError:
        result = {"status": "error",
                  "error": "snapshot replacement visible; directory sync failed; readback required before checkpoint"}
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        # Source exceptions can contain private paths, references and payload fragments.
        result = {"status": "error", "error": "invalid or unavailable private evidence"}
    if receipt is not None and receipt_revision is not None:
        receipt.update(finished_at=datetime.now(timezone.utc).isoformat(), result=result,
                       operation_outcome={"status": result["status"], "exit_code": exit_code})
        try:
            write_snapshot(args.receipt, receipt, receipt_revision)
        except (OSError, ValueError, TypeError):
            result = {"status": "error", "error": "execution receipt unavailable; evidence operation may have committed"}
            exit_code = 2
    print(json.dumps(result, sort_keys=True), file=sys.stderr if exit_code else sys.stdout)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
