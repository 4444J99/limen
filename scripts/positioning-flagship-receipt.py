#!/usr/bin/env python3
"""Run one bounded predicate against an already-checked-out exact Git head."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import selectors
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FULL_HEAD = re.compile(r"^[0-9a-f]{40}$")
BRANCH_NAME = re.compile(r"^(?!/)(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9][A-Za-z0-9._/-]*$")
REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_ORIGIN_PATTERNS = (
    re.compile(r"^https://github\.com/(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"),
    re.compile(r"^git@github\.com:(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$"),
    re.compile(r"^ssh://git@github\.com/(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"),
)
RUN_TOKEN_ENV = "FLAGSHIP_RECEIPT_RUN_TOKEN"
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
    repository = request.get("repository")
    if not isinstance(repository, str) or not REPOSITORY_NAME.fullmatch(repository):
        errors.append("repository must be a canonical owner/name slug")
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
        timeout=60,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def _remote_default(result: subprocess.CompletedProcess[bytes]) -> tuple[str | None, str | None]:
    """Parse the authoritative branch name and head from git ls-remote --symref origin HEAD."""
    if result.returncode != 0:
        return None, None
    branch: str | None = None
    head: str | None = None
    for raw_line in result.stdout.decode(errors="replace").splitlines():
        fields = raw_line.split()
        if len(fields) == 3 and fields[0] == "ref:" and fields[2] == "HEAD":
            prefix = "refs/heads/"
            branch = fields[1][len(prefix) :] if fields[1].startswith(prefix) else None
        elif len(fields) == 2 and fields[1] == "HEAD" and FULL_HEAD.fullmatch(fields[0]):
            head = fields[0]
    return branch, head


def _github_repository_from_origin(result: subprocess.CompletedProcess[bytes]) -> str | None:
    if result.returncode != 0:
        return None
    value = result.stdout.decode(errors="replace").strip()
    for pattern in GITHUB_ORIGIN_PATTERNS:
        match = pattern.fullmatch(value)
        if match is not None:
            return match.group("repository").lower()
    return None


def _tagged_process_ids(run_token: str) -> set[int]:
    marker = f"{RUN_TOKEN_ENV}={run_token}".encode()
    proc_root = Path("/proc")
    tagged: set[int] = set()
    if proc_root.is_dir():
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                environment = (entry / "environ").read_bytes()
            except OSError:
                continue
            if marker in environment.split(b"\0"):
                tagged.add(int(entry.name))
        return tagged
    try:
        completed = subprocess.run(
            ["ps", "eww", "-axo", "pid=,command="],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return tagged
    if completed.returncode != 0:
        return tagged
    marker_text = marker.decode()
    for raw_line in completed.stdout.decode(errors="replace").splitlines():
        fields = raw_line.strip().split(maxsplit=1)
        if len(fields) == 2 and fields[0].isdigit() and marker_text in fields[1]:
            tagged.add(int(fields[0]))
    return tagged


def _signal_processes(process_ids: set[int], sig: signal.Signals) -> None:
    for process_id in process_ids:
        try:
            os.kill(process_id, sig)
        except (ProcessLookupError, PermissionError):
            continue


def _process_group_alive(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + 1
    while _process_group_alive(process.pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    if _process_group_alive(process.pid):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def _stop_run_scope(process: subprocess.Popen[bytes], run_token: str) -> bool:
    tagged = _tagged_process_ids(run_token)
    observed_descendant = bool(tagged - {process.pid}) or _process_group_alive(process.pid)
    _stop_process(process)
    tagged = _tagged_process_ids(run_token)
    if tagged:
        observed_descendant = observed_descendant or bool(tagged - {process.pid})
        _signal_processes(tagged, signal.SIGTERM)
        deadline = time.monotonic() + 1
        while tagged and time.monotonic() < deadline:
            time.sleep(0.02)
            tagged = _tagged_process_ids(run_token)
        if tagged:
            _signal_processes(tagged, signal.SIGKILL)
            deadline = time.monotonic() + 1
            while tagged and time.monotonic() < deadline:
                time.sleep(0.02)
                tagged = _tagged_process_ids(run_token)
    return observed_descendant


def _run_bounded_predicate(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    max_output_bytes: int,
) -> tuple[int | None, bytes, str | None]:
    """Run a predicate without allowing stdout/stderr to grow beyond the declared memory budget."""
    run_token = secrets.token_hex(24)
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env={**os.environ, RUN_TOKEN_ENV: run_token},
    )
    assert process.stdout is not None
    descriptor = process.stdout.fileno()
    os.set_blocking(descriptor, False)
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + timeout_seconds
    failure: str | None = None
    eof = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "predicate exceeded its bounded timeout"
                _stop_run_scope(process, run_token)
                break
            events = selector.select(timeout=min(0.1, remaining))
            for _key, _mask in events:
                budget = max_output_bytes - len(output)
                try:
                    chunk = os.read(descriptor, min(65536, max(1, budget + 1)))
                except BlockingIOError:
                    continue
                if not chunk:
                    eof = True
                    selector.unregister(descriptor)
                    break
                if len(chunk) > budget:
                    output.extend(chunk[: max(0, budget)])
                    failure = "predicate exceeded its bounded output budget"
                    _stop_run_scope(process, run_token)
                    break
                output.extend(chunk)
            if failure is not None:
                break
            return_code = process.poll()
            if return_code is not None and eof:
                if _process_group_alive(process.pid) or _tagged_process_ids(run_token):
                    _stop_run_scope(process, run_token)
                    failure = "predicate left a live descendant process"
                return return_code, bytes(output), failure
        return process.returncode, bytes(output), failure
    finally:
        _stop_run_scope(process, run_token)
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
    except (OSError, subprocess.TimeoutExpired) as exc:
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
        origin = _run_git(repository_path, ["config", "--get", "remote.origin.url"])
    except (OSError, subprocess.TimeoutExpired) as exc:
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
    origin_repository = _github_repository_from_origin(origin)
    if origin_repository != request["repository"].lower():
        receipt = _not_current_receipt(
            request,
            started_at,
            "origin does not identify the requested GitHub repository",
            observed_head=observed_head,
            default_branch_head=default_branch_head,
        )
        receipt["origin_repository"] = origin_repository
        return receipt
    try:
        remote_tip = _run_git(
            repository_path,
            ["ls-remote", "--symref", "--exit-code", "origin", "HEAD"],
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _blocked_receipt(
            request,
            started_at,
            f"remote default-branch inspection could not start: {exc}",
            observed_head=observed_head,
        )
    remote_default_branch, remote_default_branch_head = _remote_default(remote_tip)
    if remote_default_branch is None or remote_default_branch_head is None:
        return _blocked_receipt(
            request,
            started_at,
            "remote default-branch tip could not be inspected",
            observed_head=observed_head,
        )
    if remote_default_branch != request["default_branch"]:
        receipt = _not_current_receipt(
            request,
            started_at,
            "requested branch is not the authoritative remote default branch",
            observed_head=observed_head,
            default_branch_head=default_branch_head,
        )
        receipt["remote_default_branch"] = remote_default_branch
        receipt["remote_default_branch_head"] = remote_default_branch_head
        return receipt
    if remote_default_branch_head != observed_head:
        receipt = _not_current_receipt(
            request,
            started_at,
            "tested head is not the current remote default-branch tip",
            observed_head=observed_head,
            default_branch_head=default_branch_head,
        )
        receipt["remote_default_branch_head"] = remote_default_branch_head
        return receipt

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

    if exit_code is not None:
        try:
            post_head = _run_git(repository_path, ["rev-parse", "HEAD"])
            post_status = _run_git(repository_path, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
            post_branch = _run_git(
                repository_path,
                ["rev-parse", "--verify", f"refs/heads/{request['default_branch']}^{{commit}}"],
            )
            post_origin = _run_git(repository_path, ["config", "--get", "remote.origin.url"])
            post_remote = _run_git(
                repository_path,
                ["ls-remote", "--symref", "--exit-code", "origin", "HEAD"],
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = "blocked_external"
            errors.append(f"post-predicate Git inspection could not complete: {exc}")
        else:
            final_head = post_head.stdout.decode(errors="replace").strip() if post_head.returncode == 0 else None
            final_branch_head = (
                post_branch.stdout.decode(errors="replace").strip() if post_branch.returncode == 0 else None
            )
            final_remote_branch, final_remote_head = _remote_default(post_remote)
            invariant_errors = []
            if final_head != observed_head:
                invariant_errors.append("checked-out head changed while the predicate ran")
            if post_status.returncode != 0 or post_status.stdout:
                invariant_errors.append("worktree changed while the predicate ran")
            if final_branch_head != observed_head:
                invariant_errors.append("local default-branch tip changed while the predicate ran")
            if _github_repository_from_origin(post_origin) != origin_repository:
                invariant_errors.append("origin repository identity changed while the predicate ran")
            if invariant_errors:
                result = "not_current"
                errors.extend(invariant_errors)
            elif final_remote_branch is None or final_remote_head is None:
                result = "blocked_external"
                errors.append("post-predicate remote default-branch tip could not be inspected")
            elif final_remote_branch != remote_default_branch:
                result = "not_current"
                errors.append("authoritative remote default branch changed while the predicate ran")
            elif final_remote_head != observed_head:
                result = "not_current"
                errors.append("remote default-branch tip changed while the predicate ran")

    return {
        "schema_version": "limen.positioning_flagship_receipt.v1",
        "flagship_id": request["flagship_id"],
        "repository": request["repository"],
        "origin_repository": origin_repository,
        "default_branch": request.get("default_branch"),
        "remote_default_branch": remote_default_branch,
        "exact_head": observed_head,
        "remote_default_branch_head": remote_default_branch_head,
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
