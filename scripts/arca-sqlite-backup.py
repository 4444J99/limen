#!/usr/bin/env python3
"""Capture a live SQLite database consistently for subsequent encrypted custody."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import time
from contextlib import closing
from pathlib import Path


class CaptureError(RuntimeError):
    """The source or the protected output could not be proven safe."""


def _identity(path: Path) -> tuple[int, int]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise CaptureError("SQLite source identity is unavailable") from exc
    if not stat.S_ISREG(info.st_mode):
        raise CaptureError("SQLite source is not a regular file")
    return info.st_dev, info.st_ino


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def capture(source: Path, output: Path, *, deadline_seconds: float = 120) -> dict[str, object]:
    """Create a no-overwrite online backup; retain partials after any failure."""
    if deadline_seconds <= 0 or deadline_seconds > 1800:
        raise CaptureError("invalid capture deadline")
    original = _identity(source)
    parent = output.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.is_symlink() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise CaptureError("backup parent must be a private real directory")
    if output.exists() or output.is_symlink():
        raise CaptureError("backup destination already exists")
    partial = output.with_name(f".{output.name}.partial")
    if partial.exists() or partial.is_symlink():
        raise CaptureError("prior partial backup requires investigation")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    deadline = time.monotonic() + deadline_seconds

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() >= deadline:
            raise CaptureError("SQLite backup deadline exceeded; partial retained")

    try:
        uri = f"{source.resolve(strict=True).as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=1)) as reader:
            with closing(sqlite3.connect(partial, timeout=1)) as writer:
                reader.backup(writer, pages=256, progress=progress, sleep=0.1)
                writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                if writer.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                    raise CaptureError("SQLite backup journal could not be sealed; partial retained")
            with closing(sqlite3.connect(f"{partial.as_uri()}?mode=ro&immutable=1", uri=True)) as check:
                check.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10_000)
                if check.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise CaptureError("SQLite backup integrity check failed; partial retained")
        if any(partial.with_name(f"{partial.name}{suffix}").exists() for suffix in ("-wal", "-shm")):
            raise CaptureError("SQLite backup journal sidecar remains; partial retained")
        if time.monotonic() >= deadline:
            raise CaptureError("SQLite backup deadline exceeded; partial retained")
        if _identity(source) != original:
            raise CaptureError("SQLite source path identity changed; partial retained")
        with partial.open("rb") as stream:
            os.fsync(stream.fileno())
        if output.exists() or output.is_symlink():
            raise CaptureError("backup destination appeared during capture; partial retained")
        os.link(partial, output)
        partial.unlink()
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except (OSError, sqlite3.Error) as exc:
        raise CaptureError("SQLite backup failed; partial retained") from exc
    return {
        "schema": "arca.sqlite_backup.v1",
        "state": "captured-needs-encrypted-remote-custody",
        "bytes": output.stat().st_size,
        "sha256": _digest(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--deadline-seconds", type=float, default=120)
    args = parser.parse_args()
    try:
        print(json.dumps(capture(args.source, args.output, deadline_seconds=args.deadline_seconds)))
    except CaptureError as exc:
        parser.exit(1, f"arca-sqlite-backup: {exc}\n")
    except OSError:
        parser.exit(1, "arca-sqlite-backup: filesystem operation failed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
