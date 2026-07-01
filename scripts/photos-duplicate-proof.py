#!/usr/bin/env python3
"""Bounded duplicate proof for Photos Universe reports.

The bootstrap report groups possible duplicates by size/path only. This script
turns those candidates into hash evidence in small resumable batches. It never
deletes, moves, imports, or rewrites media; full paths and hashes stay in the
ignored private state, while the optional public receipt contains aggregates
only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_ROOT", ROOT / ".limen-private"))
RUN_ROOT = PRIVATE_ROOT / "photos-universe" / "20260629-182431"
DEFAULT_CANDIDATES = RUN_ROOT / "report" / "duplicate-candidates.json"
DEFAULT_STATE = RUN_ROOT / "duplicate-proof-state.json"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _hash_text(*parts: str) -> str:
    h = hashlib.sha1()
    for part in parts:
        h.update(part.encode("utf-8", "replace"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _group_id(group: dict) -> str:
    paths = [str(p) for p in group.get("paths") or []]
    return _hash_text(str(group.get("bytes", "")), *paths)


def _classify_path(path: str) -> str:
    p = Path(path)
    parts = p.parts
    suffix = p.suffix.lower() or "(none)"
    if parts[:3] == ("/", "Users", "4jp"):
        return f"home:{suffix}"
    if len(parts) >= 3 and parts[1] == "Volumes":
        return f"volume:{parts[2]}:{suffix}"
    return f"other:{suffix}"


def _proof_group(group: dict) -> dict:
    paths = [str(p) for p in group.get("paths") or []]
    available: list[dict] = []
    missing: list[str] = []
    for raw in paths:
        p = Path(raw)
        if not p.is_file():
            missing.append(raw)
            continue
        try:
            available.append({
                "path": raw,
                "sha256": _sha256(p),
                "bytes": p.stat().st_size,
                "class": _classify_path(raw),
            })
        except Exception as exc:
            missing.append(f"{raw} ({exc})")
    hashes = {item["sha256"] for item in available}
    expected_bytes = int(group.get("bytes") or 0)
    byte_mismatches = [item for item in available if expected_bytes and item["bytes"] != expected_bytes]
    if len(available) < 2:
        status = "insufficient_available"
    elif len(hashes) == 1 and not byte_mismatches and not missing:
        status = "all_available_match"
    elif len(hashes) == 1 and not byte_mismatches:
        status = "available_match_partial"
    else:
        status = "hash_mismatch"
    return {
        "group_id": _group_id(group),
        "expected_bytes": expected_bytes,
        "path_count": len(paths),
        "available_count": len(available),
        "missing_count": len(missing),
        "status": status,
        "hashed_at": _now(),
        "available": available,
        "missing": missing,
    }


def _public_summary(candidates_total: int, processed: dict, processed_this_run: int) -> dict:
    statuses: dict[str, int] = {}
    classes: dict[str, int] = {}
    bytes_proven = 0
    for result in processed.values():
        status = result.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        if status == "all_available_match":
            bytes_proven += int(result.get("expected_bytes") or 0)
        for item in result.get("available") or []:
            klass = item.get("class") or "unknown"
            classes[klass] = classes.get(klass, 0) + 1
    return {
        "generated_at": _now(),
        "source": "redacted photos-universe duplicate-candidates.json",
        "candidates_total": candidates_total,
        "processed_total": len(processed),
        "processed_this_run": processed_this_run,
        "status_counts": dict(sorted(statuses.items())),
        "available_path_classes": dict(sorted(classes.items())),
        "hashed_duplicate_groups": statuses.get("all_available_match", 0),
        "bytes_proven_duplicate": bytes_proven,
        "safety": {
            "read_only": True,
            "deleted_or_moved_files": False,
            "full_paths_or_hashes_in_public_receipt": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="bounded, resumable duplicate hash proof")
    ap.add_argument("--candidates", default=str(DEFAULT_CANDIDATES), help="candidate JSON report")
    ap.add_argument("--state", default=str(DEFAULT_STATE), help="private state JSON")
    ap.add_argument("--receipt", default=None, help="optional public aggregate receipt JSON")
    ap.add_argument("--limit-groups", type=int, default=int(os.environ.get("PHOTOS_DUPLICATE_PROOF_LIMIT", "25")),
                    help="maximum unprocessed candidate groups to hash this run")
    ap.add_argument("--dry-run", action="store_true", help="hash and summarize without writing state/receipt")
    args = ap.parse_args(argv)

    candidates_path = Path(args.candidates).expanduser()
    if not candidates_path.is_file():
        print(f"[photos-duplicate-proof] candidates {candidates_path} not present - nothing to prove")
        return 0
    candidates = _load_json(candidates_path, [])
    if not isinstance(candidates, list):
        print("[photos-duplicate-proof] candidates file is not a list - skipping")
        return 0

    state_path = Path(args.state).expanduser()
    state = _load_json(state_path, {"processed": {}, "runs": []})
    processed: dict = state.setdefault("processed", {})
    processed_this_run = 0
    limit = max(0, int(args.limit_groups))
    for group in candidates:
        if processed_this_run >= limit:
            break
        if not isinstance(group, dict):
            continue
        gid = _group_id(group)
        if gid in processed:
            continue
        result = _proof_group(group)
        processed[gid] = result
        processed_this_run += 1

    summary = _public_summary(len(candidates), processed, processed_this_run)
    state.setdefault("runs", []).append({
        "ts": summary["generated_at"],
        "limit_groups": limit,
        "processed_this_run": processed_this_run,
        "dry_run": bool(args.dry_run),
    })
    if not args.dry_run:
        _write_json(state_path, state)
        if args.receipt:
            _write_json(Path(args.receipt).expanduser(), summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
