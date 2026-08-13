#!/usr/bin/env python3
"""Run one bounded predicate against an already-checked-out exact Git head."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FULL_HEAD = re.compile(r"^[0-9a-f]{40}$")
SCHEMA_VERSION = "limen.positioning_flagship_receipt_request.v1"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_request(request: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if request.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported request schema")
    for field in ("flagship_id", "repository", "repository_path", "expected_head", "predicate", "limitations"):
        if field not in request:
            errors.append(f"missing request field: {field}")
    if not FULL_HEAD.fullmatch(str(request.get("expected_head", ""))):
        errors.append("expected_head must be a full lowercase Git head")
    predicate = request.get("predicate")
    if not isinstance(predicate, dict):
        errors.append("predicate must be an object")
    else:
        argv = predicate.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
            errors.append("predicate.argv must be a non-empty string array")
        timeout = predicate.get("timeout_seconds")
        if not isinstance(timeout, int) or not 1 <= timeout <= 1800:
            errors.append("predicate timeout must be between 1 and 1800 seconds")
    if not isinstance(request.get("limitations"), list) or not request.get("limitations"):
        errors.append("receipt request requires explicit limitations")
    return errors


def run_request(request: dict[str, Any], *, base: Path | None = None) -> dict[str, Any]:
    errors = validate_request(request)
    started_at = _timestamp()
    if errors:
        return {
            "schema_version": "limen.positioning_flagship_receipt.v1",
            "flagship_id": request.get("flagship_id"),
            "result": "blocked_external",
            "started_at": started_at,
            "finished_at": _timestamp(),
            "errors": errors,
        }

    repository_path = Path(request["repository_path"])
    if base is not None and not repository_path.is_absolute():
        repository_path = (base / repository_path).resolve()
    if not repository_path.is_dir():
        return {
            "schema_version": "limen.positioning_flagship_receipt.v1",
            "flagship_id": request["flagship_id"],
            "repository": request["repository"],
            "expected_head": request["expected_head"],
            "result": "blocked_external",
            "started_at": started_at,
            "finished_at": _timestamp(),
            "errors": ["repository_path is unavailable"],
            "limitations": request["limitations"],
        }

    observed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_path,
        check=False,
        capture_output=True,
        text=True,
    )
    observed_head = observed.stdout.strip() if observed.returncode == 0 else None
    if observed_head != request["expected_head"]:
        return {
            "schema_version": "limen.positioning_flagship_receipt.v1",
            "flagship_id": request["flagship_id"],
            "repository": request["repository"],
            "expected_head": request["expected_head"],
            "observed_head": observed_head,
            "result": "not_current",
            "started_at": started_at,
            "finished_at": _timestamp(),
            "errors": ["checked-out head does not match the requested exact head"],
            "limitations": request["limitations"],
        }

    predicate = request["predicate"]
    try:
        completed = subprocess.run(
            predicate["argv"],
            cwd=repository_path,
            check=False,
            capture_output=True,
            timeout=predicate["timeout_seconds"],
        )
        output = completed.stdout + completed.stderr
        exit_code: int | None = completed.returncode
        result = "current_pass" if completed.returncode == 0 else "current_fail"
        errors = []
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, bytes) else (exc.stdout or "").encode()
        stderr = exc.stderr if isinstance(exc.stderr, bytes) else (exc.stderr or "").encode()
        output = stdout + stderr
        exit_code = None
        result = "current_fail"
        errors = ["predicate exceeded its bounded timeout"]

    return {
        "schema_version": "limen.positioning_flagship_receipt.v1",
        "flagship_id": request["flagship_id"],
        "repository": request["repository"],
        "default_branch": request.get("default_branch"),
        "exact_head": observed_head,
        "predicate": predicate,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "started_at": started_at,
        "finished_at": _timestamp(),
        "exit_code": exit_code,
        "result": result,
        "artifact_digest": hashlib.sha256(output).hexdigest(),
        "output_bytes": len(output),
        "limitations": request["limitations"],
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise ValueError("request root must be an object")
    receipt = run_request(request, base=args.request.parent)
    serialized = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if receipt.get("result") == "current_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
