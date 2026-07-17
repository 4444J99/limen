"""Filesystem mutation and command-line boundary for recovery reacceptance."""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import fcntl
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from limen.reacceptance_contract import (
    COMPLETION_GATE_KEYS,
    RELEASE_SNAPSHOT_MAX_AGE,
    LedgerError,
    _parse_timestamp,
    _strict_json_dumps,
    load_json,
    load_json_snapshot,
    load_scope,
)
from limen.reacceptance_policy import validate_document
from limen.reacceptance_workflow import (
    build_document,
    build_live_release_candidate,
    migrate_v1_document,
)


DESTINATION_ABSENT = "destination:absent"
AT_FDCWD = -2
RENAME_EXCHANGE = 0x00000002


def _exchange_paths(first: Path, second: Path) -> None:
    """Atomically exchange two same-filesystem paths without clobbering either."""

    libc = ctypes.CDLL(None, use_errno=True)
    first_bytes = os.fsencode(first)
    second_bytes = os.fsencode(second)
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        result = libc.renamex_np(first_bytes, second_bytes, RENAME_EXCHANGE)
    elif hasattr(libc, "renameat2"):
        result = libc.renameat2(
            AT_FDCWD,
            first_bytes,
            AT_FDCWD,
            second_bytes,
            RENAME_EXCHANGE,
        )
    else:
        raise LedgerError("atomic path exchange is unavailable; refusing non-CAS ledger publication")
    if result != 0:
        error = ctypes.get_errno()
        raise LedgerError(f"atomic path exchange failed: {os.strerror(error)}")


def _write_atomic(path: Path, document: dict[str, Any], *, expected_digest: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _strict_json_dumps(document, indent=2, sort_keys=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    exchanged = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        fcntl.flock(directory_descriptor, fcntl.LOCK_EX)
        if expected_digest == DESTINATION_ABSENT:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise LedgerError("refresh destination appeared during generation; refusing stale overwrite") from exc
            os.unlink(temporary)
        elif expected_digest is not None:
            try:
                current_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                raise LedgerError(f"cannot verify refresh destination before exchange: {exc}") from exc
            if current_digest != expected_digest:
                raise LedgerError(
                    "refresh destination changed after the prior ledger snapshot; refusing stale overwrite"
                )
            _exchange_paths(Path(temporary), path)
            exchanged = True
            displaced_digest = hashlib.sha256(Path(temporary).read_bytes()).hexdigest()
            if displaced_digest != expected_digest:
                _exchange_paths(Path(temporary), path)
                exchanged = False
                raise LedgerError("refresh destination changed during publication; restored concurrent content")
            os.unlink(temporary)
            exchanged = False
        else:
            raise LedgerError("atomic publication requires a destination precondition")
        os.fsync(directory_descriptor)
    except BaseException:
        if exchanged:
            try:
                _exchange_paths(Path(temporary), path)
                exchanged = False
            except (LedgerError, OSError):
                pass
        raise
    finally:
        fcntl.flock(directory_descriptor, fcntl.LOCK_UN)
        os.close(directory_descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _destination_precondition(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return DESTINATION_ABSENT
    except OSError as exc:
        raise LedgerError(f"cannot snapshot refresh destination before generation: {exc}") from exc


def _emit_or_write(
    document: dict[str, Any],
    *,
    write: bool,
    output: Path | None,
    default_output: Path,
    expected_digest: str | None,
) -> None:
    if write:
        destination = output or default_output
        _write_atomic(destination, document, expected_digest=expected_digest)
        print(f"reacceptance-ledger: wrote {destination}")
        return
    if output is not None:
        raise LedgerError("--output requires --write; omit it for stdout")
    sys.stdout.write(_strict_json_dumps(document, indent=2) + "\n")


def _release_blockers(document: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    summary = document.get("summary")
    if not isinstance(summary, dict):
        return ["summary_missing"]
    if summary.get("repair_required"):
        blockers.append(f"historical_rows={summary['repair_required']}")
    if summary.get("repair_required_remedies"):
        blockers.append(f"remedies={summary['repair_required_remedies']}")
    for field in ("current_p1", "current_p2", "current_unclassified"):
        if summary.get(field):
            blockers.append(f"{field}={summary[field]}")
    gates = document.get("completion_gates")
    if isinstance(gates, dict):
        for key in sorted(COMPLETION_GATE_KEYS):
            gate = gates.get(key)
            if not isinstance(gate, dict) or gate.get("status") != "passed":
                reasons = gate.get("blockers") if isinstance(gate, dict) else ["missing"]
                blockers.append(f"{key}={','.join(str(reason) for reason in reasons)}")
    else:
        blockers.append("completion_gates_missing")
    return blockers


def _check_mode(
    target: Path,
    *,
    scope: dict[str, Any],
    require_release_ready: bool,
) -> int:
    document = load_json(target)
    errors = validate_document(document, scope)
    if errors:
        for error in errors:
            print(f"reacceptance-ledger: {error}", file=sys.stderr)
        return 1
    ready = bool(document["summary"]["release_ready"])
    if require_release_ready and ready:
        refreshed_at = _parse_timestamp(document.get("refreshed_at"))
        now = dt.datetime.now(dt.timezone.utc)
        if (
            refreshed_at is None
            or refreshed_at > now + dt.timedelta(minutes=5)
            or now - refreshed_at > RELEASE_SNAPSHOT_MAX_AGE
        ):
            print(
                "reacceptance-ledger: campaign incomplete: release snapshot is not current",
                file=sys.stderr,
            )
            return 3
        live = build_live_release_candidate(scope, previous_document=document)
        live_errors = validate_document(live, scope)
        if live_errors:
            print(
                "reacceptance-ledger: campaign incomplete: live candidate is structurally invalid: "
                + "; ".join(live_errors),
                file=sys.stderr,
            )
            return 3
        if live.get("evidence_digest") != document.get("evidence_digest"):
            print(
                "reacceptance-ledger: campaign incomplete: tracked evidence is stale against live owner reads",
                file=sys.stderr,
            )
            return 3
        if live.get("summary", {}).get("release_ready") is not True:
            print(
                "reacceptance-ledger: campaign incomplete: live owner gates are not release-ready: "
                + "; ".join(_release_blockers(live)),
                file=sys.stderr,
            )
            return 3
    print(
        "reacceptance-ledger: "
        f"structurally_valid=true release_ready={str(ready).lower()} "
        f"sessions={document['scope']['sessions']} workflows={document['scope']['workflows']} "
        f"pull_requests={document['scope']['pull_requests']} rows={document['scope']['rows']} "
        f"findings={document['scope']['findings']['total']}"
    )
    if require_release_ready and not ready:
        print(
            "reacceptance-ledger: campaign incomplete: " + "; ".join(_release_blockers(document)),
            file=sys.stderr,
        )
        return 3
    return 0


def main(
    argv: list[str] | None = None,
    *,
    scope_path: Path,
    ledger_path: Path,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="refresh current GitHub evidence")
    mode.add_argument(
        "--migrate-v1",
        type=Path,
        metavar="PATH",
        help="migrate a v1 ledger without claiming campaign completion",
    )
    mode.add_argument(
        "--check",
        nargs="?",
        const=str(ledger_path),
        metavar="PATH",
        help="validate structural integrity only (default: tracked ledger)",
    )
    mode.add_argument(
        "--require-release-ready",
        nargs="?",
        const=str(ledger_path),
        metavar="PATH",
        help="validate structural integrity and require every campaign gate",
    )
    parser.add_argument("--output", type=Path, help="write destination for refresh or migration")
    parser.add_argument("--write", action="store_true", help="explicitly write refresh or migration output")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--scope", type=Path, default=scope_path)
    parser.add_argument(
        "--previous",
        type=Path,
        help="prior v2 ledger to refresh (default: tracked ledger)",
    )
    args = parser.parse_args(argv)

    try:
        scope = load_scope(args.scope)
        if args.migrate_v1 is not None:
            if args.previous is not None:
                raise LedgerError("--previous cannot be combined with --migrate-v1")
            destination = args.output or ledger_path
            compare_digest = _destination_precondition(destination) if args.write else None
            previous, _previous_digest = load_json_snapshot(args.migrate_v1)
            document = migrate_v1_document(previous, scope)
            errors = validate_document(document, scope)
            if errors:
                raise LedgerError("; ".join(errors))
            _emit_or_write(
                document,
                write=args.write,
                output=args.output,
                default_output=ledger_path,
                expected_digest=compare_digest,
            )
            return 0

        if args.refresh:
            previous_path = args.previous or ledger_path
            destination = args.output or ledger_path
            compare_digest = _destination_precondition(destination) if args.write else None
            previous, _previous_digest = load_json_snapshot(previous_path)
            document = build_document(scope, previous_document=previous, workers=args.workers)
            errors = validate_document(document, scope)
            if errors:
                raise LedgerError("; ".join(errors))
            _emit_or_write(
                document,
                write=args.write,
                output=args.output,
                default_output=ledger_path,
                expected_digest=compare_digest,
            )
            return 0

        if args.write or args.output or args.previous:
            raise LedgerError("--write/--output/--previous require --refresh or --migrate-v1")
        if args.require_release_ready is not None:
            return _check_mode(
                Path(args.require_release_ready),
                scope=scope,
                require_release_ready=True,
            )
        target = Path(args.check) if args.check is not None else ledger_path
        return _check_mode(target, scope=scope, require_release_ready=False)
    except LedgerError as exc:
        print(f"reacceptance-ledger: {exc}", file=sys.stderr)
        return 2
