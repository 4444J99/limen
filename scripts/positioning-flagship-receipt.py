#!/usr/bin/env python3
"""Run one bounded predicate against an already-checked-out exact Git head."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import selectors
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FULL_HEAD = re.compile(r"^[0-9a-f]{40}$")
BRANCH_NAME = re.compile(r"^(?!/)(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9][A-Za-z0-9._/-]*$")
SCHEMA_VERSION = "limen.positioning_flagship_receipt_request.v1"
MAX_OUTPUT_BYTES = 10 * 1024 * 1024


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_request(request: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if request.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported request schema")
    for field in (
        "flagship_id",
        "repository",
        "repository_path",
        "default_branch",
        "expected_head",
        "predicate",
        "limitations",
    ):
        if field not in request:
            errors.append(f"missing request field: {field}")
    default_branch = request.get("default_branch")
    if not isinstance(default_branch, str) or not BRANCH_NAME.fullmatch(default_branch):
        errors.append("default_branch must be a safe branch name")
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
        output_limit = predicate.get("max_output_bytes")
        if (
            not isinstance(output_limit, int)
            or isinstance(output_limit, bool)
            or not 1024 <= output_limit <= MAX_OUTPUT_BYTES
        ):
            errors.append(f"predicate max_output_bytes must be between 1024 and {MAX_OUTPUT_BYTES}")
    if not isinstance(request.get("limitations"), list) or not request.get("limitations"):
        errors.append("receipt request requires explicit limitations")
    return errors


def _blocked_receipt(
    request: dict[str, Any],
    started_at: str,
    error: str,
    *,
    observed_head: str | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": "limen.positioning_flagship_receipt.v1",
        "flagship_id": request.get("flagship_id"),
        "repository": request.get("repository"),
        "default_branch": request.get("default_branch"),
        "expected_head": request.get("expected_head"),
        "result": "blocked_external",
        "started_at": started_at,
        "finished_at": _timestamp(),
        "errors": [error],
        "limitations": request.get("limitations", []),
    }
    if observed_head is not None:
        receipt["observed_head"] = observed_head
    return receipt


def _not_current_receipt(
    request: dict[str, Any],
    started_at: str,
    error: str,
    *,
    observed_head: str | None,
    default_branch_head: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "limen.positioning_flagship_receipt.v1",
        "flagship_id": request["flagship_id"],
        "repository": request["repository"],
        "default_branch": request["default_branch"],
        "expected_head": request["expected_head"],
        "observed_head": observed_head,
        "default_branch_head": default_branch_head,
        "result": "not_current",
        "started_at": started_at,
        "finished_at": _timestamp(),
        "errors": [error],
        "limitations": request["limitations"],
    }


def _run_git(repository_path: Path, argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *argv],
        cwd=repository_path,
        check=False,
        capture_output=True,
    )


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


def _run_bounded_predicate(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    max_output_bytes: int,
) -> tuple[int | None, bytes, str | None]:
    """Run a predicate without allowing stdout/stderr to grow beyond the declared memory budget."""
    process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert process.stdout is not None
    descriptor = process.stdout.fileno()
    os.set_blocking(descriptor, False)
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout_seconds
    failure: str | None = None
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "predicate exceeded its bounded timeout"
                _stop_process(process)
                break
            events = selector.select(timeout=min(0.1, remaining))
            for _key, _mask in events:
                budget = max_output_bytes - len(output)
                chunk = os.read(descriptor, min(65536, max(1, budget + 1)))
                if not chunk:
                    continue
                if len(chunk) > budget:
                    output.extend(chunk[: max(0, budget)])
                    failure = "predicate exceeded its bounded output budget"
                    _stop_process(process)
                    break
                output.extend(chunk)
            if failure is not None:
                break
            return_code = process.poll()
            if return_code is not None:
                while len(output) <= max_output_bytes:
                    budget = max_output_bytes - len(output)
                    chunk = os.read(descriptor, min(65536, max(1, budget + 1)))
                    if not chunk:
                        break
                    if len(chunk) > budget:
                        output.extend(chunk[: max(0, budget)])
                        failure = "predicate exceeded its bounded output budget"
                        break
                    output.extend(chunk)
                return return_code, bytes(output), failure
        return process.returncode, bytes(output), failure
    finally:
        selector.close()
        process.stdout.close()


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

    try:
        observed = _run_git(repository_path, ["rev-parse", "HEAD"])
    except OSError as exc:
        return _blocked_receipt(request, started_at, f"git inspection could not start: {exc}")
    observed_head = observed.stdout.decode(errors="replace").strip() if observed.returncode == 0 else None
    if observed_head != request["expected_head"]:
        return _not_current_receipt(
            request,
            started_at,
            "checked-out head does not match the requested exact head",
            observed_head=observed_head,
        )

    try:
        status = _run_git(repository_path, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
        branch_tip = _run_git(
            repository_path,
            ["rev-parse", "--verify", f"refs/heads/{request['default_branch']}^{{commit}}"],
        )
    except OSError as exc:
        return _blocked_receipt(
            request, started_at, f"git inspection could not start: {exc}", observed_head=observed_head
        )
    if status.returncode != 0:
        return _blocked_receipt(
            request, started_at, "git status could not inspect the worktree", observed_head=observed_head
        )
    if status.stdout:
        return _not_current_receipt(
            request,
            started_at,
            "worktree contains tracked or untracked changes",
            observed_head=observed_head,
        )
    default_branch_head = branch_tip.stdout.decode(errors="replace").strip() if branch_tip.returncode == 0 else None
    if default_branch_head != observed_head:
        return _not_current_receipt(
            request,
            started_at,
            "tested head is not the current local default-branch tip",
            observed_head=observed_head,
            default_branch_head=default_branch_head,
        )

    predicate = request["predicate"]
    try:
        exit_code, output, bounded_failure = _run_bounded_predicate(
            predicate["argv"],
            cwd=repository_path,
            timeout_seconds=predicate["timeout_seconds"],
            max_output_bytes=predicate["max_output_bytes"],
        )
        result = "current_pass" if exit_code == 0 and bounded_failure is None else "current_fail"
        errors = [bounded_failure] if bounded_failure else []
    except OSError as exc:
        output = b""
        exit_code = None
        result = "blocked_external"
        errors = [f"predicate could not start: {exc}"]

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
