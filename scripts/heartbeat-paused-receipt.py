#!/usr/bin/env python3
"""Maintain the byte-stable receipt for a sleeping paused heartbeat."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

SCHEMA = "limen.heartbeat_pause.v1"


def receipt_bytes(cadence_seconds: int) -> bytes:
    if cadence_seconds < 60 or cadence_seconds > 86_400:
        raise ValueError("cadence_seconds must be between 60 and 86400")
    payload = {
        "schema": SCHEMA,
        "mode": "paused",
        "cadence_seconds": cadence_seconds,
        "substantive_probes": False,
        "resume": "autonomy governor leaves paused mode",
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def write_paused(path: Path, cadence_seconds: int) -> bool:
    payload = receipt_bytes(cadence_seconds)
    try:
        if path.read_bytes() == payload:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return True


def clear_paused(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--clear", action="store_true")
    parser.add_argument("--cadence-seconds", type=int, default=300)
    parser.add_argument(
        "--path",
        type=Path,
        default=Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
        / "logs"
        / "heartbeat-paused.json",
    )
    args = parser.parse_args()
    changed = write_paused(args.path, args.cadence_seconds) if args.write else clear_paused(args.path)
    print("changed" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
