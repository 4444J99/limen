#!/usr/bin/env python3
"""Run one bounded predicate against an already-checked-out exact Git head."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
PROOF_CONTRACT = ROOT / "docs/positioning/proof/psp-c04-proof-contract.json"
FULL_HEAD = re.compile(r"^[0-9a-f]{40}$")
BRANCH_NAME = re.compile(r"^(?!/)(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9][A-Za-z0-9._/-]*$")
REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_ORIGIN_PATTERNS = (
    re.compile(r"^https://github\.com/(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"),
    re.compile(r"^git@github\.com:(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?$"),
    re.compile(r"^ssh://git@github\.com/(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"),
)
SCHEMA_VERSION = "limen.positioning_flagship_receipt_request.v1"
REQUEST_FIELDS = {
    "schema_version",
    "flagship_id",
    "repository",
    "repository_path",
    "default_branch",
    "expected_head",
    "predicate",
    "limitations",
}
PREDICATE_FIELDS = {"argv", "timeout_seconds", "max_output_bytes"}
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
DARWIN_PAUSED_EXEC = r"""
import json
import os
import signal
import sys

error_path, *argv = sys.argv[1:]
os.kill(os.getpid(), signal.SIGSTOP)
try:
    os.execvpe(argv[0], argv, os.environ)
except OSError as exc:
    status = {"spawn_error": f"[Errno {exc.errno}] {exc.strerror or str(exc)}"}
    temporary_status = f"{error_path}.{os.getpid()}.tmp"
    with open(temporary_status, "x", encoding="utf-8") as status_file:
        json.dump(status, status_file, sort_keys=True, separators=(",", ":"))
        status_file.flush()
        os.fsync(status_file.fileno())
    os.replace(temporary_status, error_path)
    raise SystemExit(253)
"""
DARWIN_SUPERVISOR = r"""
import json
import os
import signal
import subprocess
import sys

status_path, environment_path, output_path, process_path, error_path, paused_exec, cwd, *argv = sys.argv[1:]
os.kill(os.getpid(), signal.SIGSTOP)
status = {}
try:
    with open(environment_path, encoding="utf-8") as environment_file:
        environment = json.load(environment_file)
    output_fd = os.open(output_path, os.O_WRONLY)
    with os.fdopen(output_fd, "wb", buffering=0) as output:
        process = subprocess.Popen(
            [sys.executable, "-c", paused_exec, error_path, *argv],
            cwd=cwd,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        temporary_process = f"{process_path}.{os.getpid()}.tmp"
        with open(temporary_process, "x", encoding="utf-8") as process_file:
            json.dump({"pid": process.pid}, process_file, sort_keys=True, separators=(",", ":"))
            process_file.flush()
            os.fsync(process_file.fileno())
        os.replace(temporary_process, process_path)
        returncode = process.wait()
    try:
        with open(error_path, encoding="utf-8") as error_file:
            status = json.load(error_file)
    except FileNotFoundError:
        status = {"returncode": returncode}
except OSError as exc:
    status = {"spawn_error": f"[Errno {exc.errno}] {exc.strerror or str(exc)}"}
except BaseException as exc:
    status = {"supervisor_error": f"{type(exc).__name__}: {exc}"}
temporary_status = f"{status_path}.{os.getpid()}.tmp"
with open(temporary_status, "x", encoding="utf-8") as status_file:
    json.dump(status, status_file, sort_keys=True, separators=(",", ":"))
    status_file.flush()
    os.fsync(status_file.fileno())
os.replace(temporary_status, status_path)
"""
DARWIN_PROC_ALL_PIDS = 1
DARWIN_PROC_PIDCOALITIONINFO = 20
DARWIN_COALITION_INFO_BYTES = 5 * ctypes.sizeof(ctypes.c_uint64)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _flagship_contract(flagship_id: str) -> dict[str, Any] | None:
    payload = json.loads(PROOF_CONTRACT.read_text(encoding="utf-8"))
    receipt_plan = payload.get("exact_head_receipt_plan") if isinstance(payload, dict) else None
    contracts = receipt_plan.get("flagship_predicates") if isinstance(receipt_plan, dict) else None
    if not isinstance(contracts, dict):
        raise ValueError("proof contract has no exact flagship predicate registry")
    contract = contracts.get(flagship_id)
    if contract is None:
        return None
    if not isinstance(contract, dict) or set(contract) != {"repository", "default_branch", "predicate"}:
        raise ValueError("proof contract flagship predicate has an invalid exact schema")
    predicate = contract.get("predicate")
    if not isinstance(predicate, dict) or set(predicate) != PREDICATE_FIELDS:
        raise ValueError("proof contract flagship predicate command has an invalid exact schema")
    return contract


def validate_request(request: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    unexpected = sorted(set(request) - REQUEST_FIELDS)
    if unexpected:
        errors.append(f"request has prohibited or unknown fields: {', '.join(unexpected)}")
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
    repository_path = request.get("repository_path")
    if not isinstance(repository_path, str) or not repository_path.strip():
        errors.append("repository_path must be a nonblank path string")
    flagship_id = request.get("flagship_id")
    if (
        not isinstance(flagship_id, str)
        or not flagship_id.strip()
        or flagship_id != flagship_id.strip()
        or "\0" in flagship_id
    ):
        errors.append("flagship_id must be nonblank text")
    predicate = request.get("predicate")
    if not isinstance(predicate, dict):
        errors.append("predicate must be an object")
    else:
        unexpected_predicate = sorted(set(predicate) - PREDICATE_FIELDS)
        if unexpected_predicate:
            errors.append(f"predicate has prohibited or unknown fields: {', '.join(unexpected_predicate)}")
        argv = predicate.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(item, str) and item and "\0" not in item for item in argv)
        ):
            errors.append("predicate.argv must be a non-empty NUL-free string array")
        timeout = predicate.get("timeout_seconds")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 1800:
            errors.append("predicate timeout must be between 1 and 1800 seconds")
        output_limit = predicate.get("max_output_bytes")
        if (
            not isinstance(output_limit, int)
            or isinstance(output_limit, bool)
            or not 1024 <= output_limit <= MAX_OUTPUT_BYTES
        ):
            errors.append(f"predicate max_output_bytes must be between 1024 and {MAX_OUTPUT_BYTES}")
    limitations = request.get("limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or not all(isinstance(value, str) and value.strip() for value in limitations)
    ):
        errors.append("receipt request requires explicit limitations")
    if isinstance(flagship_id, str) and flagship_id.strip() == flagship_id and "\0" not in flagship_id:
        try:
            contract = _flagship_contract(flagship_id)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"flagship predicate contract is unavailable: {exc}")
        else:
            if contract is None:
                errors.append("flagship_id is not selected by the proof contract")
            else:
                if repository != contract.get("repository"):
                    errors.append("repository differs from the contract-owned flagship repository")
                if default_branch != contract.get("default_branch"):
                    errors.append("default_branch differs from the contract-owned flagship branch")
                if predicate != contract.get("predicate"):
                    errors.append("predicate differs from the contract-owned flagship command")
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
        env=_sanitized_git_environment(),
    )


def _sanitized_git_environment() -> dict[str, str]:
    """Remove ambient object, config, and transport overrides from evidence reads."""
    environment = dict(os.environ)
    exact_overrides = {
        "ALL_PROXY",
        "CURL_CA_BUNDLE",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_SHALLOW_FILE",
        "GIT_SSL_CAINFO",
        "GIT_SSL_CAPATH",
        "GIT_SSL_NO_VERIFY",
        "GIT_SSL_VERSION",
        "GIT_WORK_TREE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
    }
    for key in tuple(environment):
        if (
            key in exact_overrides
            or key.startswith("GIT_CONFIG_KEY_")
            or key.startswith("GIT_CONFIG_VALUE_")
            or key.startswith("GIT_SSL_")
            or key.lower() in {"all_proxy", "http_proxy", "https_proxy", "no_proxy"}
        ):
            environment.pop(key, None)
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_COUNT": "0",
            "GIT_GRAFT_FILE": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _run_canonical_remote(repository: str) -> subprocess.CompletedProcess[bytes]:
    """Query github.com without repository, user, or system Git URL rewrites."""
    anchor = Path(Path.cwd().anchor or os.sep)
    return subprocess.run(
        [
            "git",
            "ls-remote",
            "--symref",
            "--exit-code",
            f"https://github.com/{repository}.git",
            "HEAD",
        ],
        cwd=anchor,
        check=False,
        capture_output=True,
        timeout=60,
        env=_sanitized_git_environment(),
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


def _signal_processes(process_ids: set[int], sig: signal.Signals) -> None:
    for process_id in process_ids:
        if process_id <= 1 or process_id == os.getpid():
            continue
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


def _pid_alive(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _linux_parent_map() -> dict[int, int]:
    parents: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "stat").read_text(encoding="utf-8")
        except OSError:
            continue
        closing = raw.rfind(")")
        fields = raw[closing + 2 :].split() if closing >= 0 else []
        if len(fields) > 1 and fields[1].isdigit():
            parents[int(entry.name)] = int(fields[1])
    return parents


def _descendants(parents: dict[int, int], root: int) -> set[int]:
    result: set[int] = set()
    frontier = {root}
    while frontier:
        children = {pid for pid, parent in parents.items() if parent in frontier and pid not in result}
        result.update(children)
        frontier = children
    return result


def _linux_subreaper_state() -> bool:
    libc = ctypes.CDLL(None, use_errno=True)
    value = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(value), 0, 0, 0) != 0:  # PR_GET_CHILD_SUBREAPER
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return bool(value.value)


def _linux_set_subreaper(enabled: bool) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, int(enabled), 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _darwin_libproc() -> ctypes.CDLL:
    libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    libproc.proc_listpids.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    libproc.proc_listpids.restype = ctypes.c_int
    libproc.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    libproc.proc_pidinfo.restype = ctypes.c_int
    return libproc


def _darwin_all_process_ids(libproc: ctypes.CDLL) -> set[int]:
    required = libproc.proc_listpids(DARWIN_PROC_ALL_PIDS, 0, None, 0)
    if required <= 0:
        error = ctypes.get_errno()
        raise OSError(error or 5, os.strerror(error or 5))
    capacity = required + 4096
    while capacity <= 16 * 1024 * 1024:
        count = capacity // ctypes.sizeof(ctypes.c_int)
        buffer = (ctypes.c_int * count)()
        used = libproc.proc_listpids(
            DARWIN_PROC_ALL_PIDS,
            0,
            buffer,
            ctypes.sizeof(buffer),
        )
        if used < 0:
            error = ctypes.get_errno()
            raise OSError(error or 5, os.strerror(error or 5))
        if used < ctypes.sizeof(buffer):
            return {process_id for process_id in buffer[: used // ctypes.sizeof(ctypes.c_int)] if process_id > 0}
        capacity *= 2
    raise OSError("Darwin process enumeration exceeded its bounded buffer")


def _darwin_resource_coalition(
    libproc: ctypes.CDLL,
    process_id: int,
    *,
    required: bool = False,
) -> int | None:
    values = (ctypes.c_uint64 * 5)()
    ctypes.set_errno(0)
    used = libproc.proc_pidinfo(
        process_id,
        DARWIN_PROC_PIDCOALITIONINFO,
        0,
        values,
        ctypes.sizeof(values),
    )
    if used == DARWIN_COALITION_INFO_BYTES and values[0] > 0:
        return int(values[0])
    if not required:
        return None
    error = ctypes.get_errno()
    if error:
        raise OSError(error, os.strerror(error))
    raise OSError(f"resource coalition unavailable for process {process_id}")


def _darwin_coalition_process_ids(libproc: ctypes.CDLL, coalition_id: int) -> set[int]:
    return {
        process_id
        for process_id in _darwin_all_process_ids(libproc)
        if _darwin_resource_coalition(libproc, process_id) == coalition_id
    }


def _darwin_signal_processes(process_ids: set[int], sig: signal.Signals) -> None:
    safe = sorted(process_id for process_id in process_ids if process_id > 1 and process_id != os.getpid())
    if not safe:
        return
    subprocess.run(
        ["/bin/kill", f"-{signal.Signals(sig).name.removeprefix('SIG')}", *map(str, safe)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _darwin_remove_job(label: str) -> None:
    subprocess.run(
        ["/bin/launchctl", "remove", label],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _darwin_cleanup_job(label: str, libproc: ctypes.CDLL, coalition_ids: set[int]) -> None:
    _darwin_remove_job(label)
    members = set().union(*(_darwin_coalition_process_ids(libproc, coalition_id) for coalition_id in coalition_ids))
    _darwin_signal_processes(members, signal.SIGTERM)
    deadline = time.monotonic() + 1
    while members and time.monotonic() < deadline:
        time.sleep(0.02)
        members = set().union(*(_darwin_coalition_process_ids(libproc, coalition_id) for coalition_id in coalition_ids))
    if members:
        _darwin_signal_processes(members, signal.SIGKILL)


def _darwin_job_pid(label: str, deadline: float) -> int:
    target = f"gui/{os.getuid()}/{label}"
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["/bin/launchctl", "print", target],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            match = re.search(rb"(?:^|\n)\s*pid = ([0-9]+)(?:\n|$)", result.stdout)
            if match is not None:
                return int(match.group(1))
        time.sleep(0.02)
    raise OSError("launchd predicate supervisor did not publish its process ID")


def _darwin_wait_stopped(process_id: int, deadline: float) -> None:
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["/bin/ps", "-o", "state=", "-p", str(process_id)],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0 and result.stdout.strip().startswith(b"T"):
            return
        if not _pid_alive(process_id):
            break
        time.sleep(0.02)
    raise OSError("launchd predicate supervisor did not stop before execution")


def _darwin_predicate_pid(process_path: Path, deadline: float) -> int:
    while time.monotonic() < deadline:
        try:
            value = json.loads(process_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            time.sleep(0.02)
            continue
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OSError(f"predicate process receipt is unreadable: {exc}") from exc
        if (
            isinstance(value, dict)
            and set(value) == {"pid"}
            and isinstance(value["pid"], int)
            and not isinstance(value["pid"], bool)
            and value["pid"] > 1
        ):
            return value["pid"]
        raise OSError("predicate process receipt has an invalid schema")
    raise OSError("predicate supervisor did not publish the stopped predicate process")


def _extend_bounded_output(
    descriptor: int,
    output: bytearray,
    max_output_bytes: int,
) -> str | None:
    while True:
        budget = max_output_bytes - len(output)
        try:
            chunk = os.read(descriptor, min(65536, max(1, budget + 1)))
        except BlockingIOError:
            return None
        if not chunk:
            return None
        if len(chunk) > budget:
            output.extend(chunk[: max(0, budget)])
            return "predicate exceeded its bounded output budget"
        output.extend(chunk)


def _read_darwin_status(status_path: Path) -> tuple[int | None, str | None] | None:
    try:
        value = json.loads(status_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OSError(f"predicate supervisor status is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise OSError("predicate supervisor status is not an object")
    if set(value) == {"returncode"}:
        return_code = value["returncode"]
        if not isinstance(return_code, int) or isinstance(return_code, bool):
            raise OSError("predicate supervisor return code is invalid")
        return return_code, None
    if set(value) == {"spawn_error"} and isinstance(value["spawn_error"], str):
        return None, value["spawn_error"]
    if set(value) == {"supervisor_error"} and isinstance(value["supervisor_error"], str):
        raise OSError(f"predicate supervisor failed: {value['supervisor_error']}")
    raise OSError("predicate supervisor status has an invalid schema")


def _run_darwin_bounded_predicate(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    max_output_bytes: int,
) -> tuple[int | None, bytes, str | None]:
    """Run a predicate in a unique launchd resource coalition and reap every member."""
    label = f"local.limen.flagship.{os.getpid()}.{time.monotonic_ns()}"
    libproc = _darwin_libproc()
    coalition_ids: set[int] = set()
    supervisor_pid: int | None = None
    predicate_pid: int | None = None
    output = bytearray()
    failure: str | None = None
    return_code: int | None = None
    descriptor: int | None = None
    selector: selectors.BaseSelector | None = None
    with tempfile.TemporaryDirectory(prefix="limen-flagship-") as temporary:
        private_root = Path(temporary)
        environment_path = private_root / "environment.json"
        status_path = private_root / "status.json"
        process_path = private_root / "process.json"
        error_path = private_root / "spawn-error.json"
        output_path = private_root / "output.pipe"
        environment_path.write_text(
            json.dumps(dict(os.environ), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        environment_path.chmod(0o600)
        os.mkfifo(output_path, 0o600)
        descriptor = os.open(output_path, os.O_RDWR | os.O_NONBLOCK)
        selector = selectors.DefaultSelector()
        selector.register(descriptor, selectors.EVENT_READ)
        try:
            submitted = subprocess.run(
                [
                    "/bin/launchctl",
                    "submit",
                    "-l",
                    label,
                    "--",
                    sys.executable,
                    "-c",
                    DARWIN_SUPERVISOR,
                    str(status_path),
                    str(environment_path),
                    str(output_path),
                    str(process_path),
                    str(error_path),
                    DARWIN_PAUSED_EXEC,
                    str(cwd),
                    *argv,
                ],
                check=False,
                capture_output=True,
            )
            if submitted.returncode != 0:
                detail = submitted.stderr.decode(errors="replace").strip()
                raise OSError(f"launchd predicate supervisor submission failed: {detail or submitted.returncode}")
            startup_deadline = time.monotonic() + 5
            supervisor_pid = _darwin_job_pid(label, startup_deadline)
            _darwin_wait_stopped(supervisor_pid, startup_deadline)
            supervisor_coalition = _darwin_resource_coalition(libproc, supervisor_pid, required=True)
            assert supervisor_coalition is not None
            coalition_ids.add(supervisor_coalition)
            resumed = subprocess.run(
                ["/bin/kill", "-CONT", str(supervisor_pid)],
                check=False,
                capture_output=True,
            )
            if resumed.returncode != 0:
                detail = resumed.stderr.decode(errors="replace").strip()
                raise OSError(f"predicate supervisor could not resume: {detail or resumed.returncode}")

            predicate_pid = _darwin_predicate_pid(process_path, startup_deadline)
            _darwin_wait_stopped(predicate_pid, startup_deadline)
            predicate_coalition = _darwin_resource_coalition(libproc, predicate_pid, required=True)
            assert predicate_coalition is not None
            coalition_ids.add(predicate_coalition)
            resumed = subprocess.run(
                ["/bin/kill", "-CONT", str(predicate_pid)],
                check=False,
                capture_output=True,
            )
            if resumed.returncode != 0:
                detail = resumed.stderr.decode(errors="replace").strip()
                raise OSError(f"stopped predicate could not resume: {detail or resumed.returncode}")

            deadline = time.monotonic() + timeout_seconds
            missing_status_since: float | None = None
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    failure = "predicate exceeded its bounded timeout"
                    break
                failure = _extend_bounded_output(descriptor, output, max_output_bytes)
                if failure is not None:
                    break
                status = _read_darwin_status(status_path)
                if status is not None:
                    return_code, spawn_error = status
                    failure = _extend_bounded_output(descriptor, output, max_output_bytes)
                    if spawn_error is not None:
                        raise OSError(spawn_error)
                    break
                if supervisor_pid is not None and not _pid_alive(supervisor_pid):
                    if missing_status_since is None:
                        missing_status_since = time.monotonic()
                    elif time.monotonic() - missing_status_since >= 0.1:
                        raise OSError("predicate supervisor exited without a status receipt")
                selector.select(timeout=min(0.02, remaining))

            if failure is None:
                members = _darwin_coalition_process_ids(libproc, predicate_coalition)
                members.discard(supervisor_pid)
                members.discard(predicate_pid)
                if members:
                    failure = "predicate left a live descendant process"
            return return_code, bytes(output), failure
        finally:
            _darwin_cleanup_job(label, libproc, coalition_ids)
            if selector is not None:
                selector.close()
            if descriptor is not None:
                os.close(descriptor)


def _prepare_process_scope() -> dict[str, Any]:
    system = platform.system()
    if system == "Linux":
        previous = _linux_subreaper_state()
        _linux_set_subreaper(True)
        parents = _linux_parent_map()
        return {
            "kind": "linux-subreaper",
            "previous": previous,
            "baseline_children": {pid for pid, parent in parents.items() if parent == os.getpid()},
        }
    raise OSError(f"process containment is unsupported on {system or 'this platform'}")


def _reap_adopted(process_ids: set[int]) -> None:
    for process_id in process_ids:
        try:
            os.waitpid(process_id, os.WNOHANG)
        except (ChildProcessError, ProcessLookupError):
            continue


def _scope_process_ids(scope: dict[str, Any], process_id: int) -> tuple[set[int], str | None]:
    parents = _linux_parent_map()
    direct = {
        pid
        for pid, parent in parents.items()
        if parent == os.getpid() and pid not in scope["baseline_children"] and pid != process_id
    }
    active = _descendants(parents, process_id) | direct
    _reap_adopted(active)
    return {pid for pid in active if _pid_alive(pid)}, None


def _finish_process_scope(scope: dict[str, Any]) -> None:
    _linux_set_subreaper(bool(scope["previous"]))


def _stop_run_scope(process: subprocess.Popen[bytes], scope: dict[str, Any]) -> tuple[bool, str | None]:
    descendants, tracking_error = _scope_process_ids(scope, process.pid)
    observed_descendant = bool(descendants) or _process_group_alive(process.pid)
    _stop_process(process)
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        current, current_error = _scope_process_ids(scope, process.pid)
        tracking_error = tracking_error or current_error
        descendants.update(current)
        if not current:
            break
        _signal_processes(current, signal.SIGTERM)
        time.sleep(0.02)
    current, current_error = _scope_process_ids(scope, process.pid)
    tracking_error = tracking_error or current_error
    descendants.update(current)
    if current:
        _signal_processes(current, signal.SIGKILL)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            current, current_error = _scope_process_ids(scope, process.pid)
            tracking_error = tracking_error or current_error
            if not current:
                break
            time.sleep(0.02)
    _reap_adopted(descendants)
    return observed_descendant or bool(descendants), tracking_error


def _run_bounded_predicate(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    max_output_bytes: int,
) -> tuple[int | None, bytes, str | None]:
    """Run a predicate without allowing stdout/stderr to grow beyond the declared memory budget."""
    if platform.system() == "Darwin":
        return _run_darwin_bounded_predicate(
            argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
    scope = _prepare_process_scope()
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    output = bytearray()
    deadline = time.monotonic() + timeout_seconds
    failure: str | None = None
    eof = False
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        assert process.stdout is not None
        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        selector = selectors.DefaultSelector()
        selector.register(descriptor, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "predicate exceeded its bounded timeout"
                _stop_run_scope(process, scope)
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
                    _stop_run_scope(process, scope)
                    break
                output.extend(chunk)
            if failure is not None:
                break
            descendants, tracking_error = _scope_process_ids(scope, process.pid)
            if tracking_error is not None:
                failure = tracking_error
                _stop_run_scope(process, scope)
                break
            return_code = process.poll()
            if return_code is not None:
                if _process_group_alive(process.pid) or descendants:
                    _stop_run_scope(process, scope)
                    failure = "predicate left a live descendant process"
                    return return_code, bytes(output), failure
                if eof:
                    return return_code, bytes(output), failure
        return process.returncode, bytes(output), failure
    finally:
        if process is not None:
            _stop_run_scope(process, scope)
            if process.stdout is not None:
                process.stdout.close()
        if selector is not None:
            selector.close()
        _finish_process_scope(scope)


def run_request(
    request: dict[str, Any],
    *,
    base: Path | None = None,
    canonical_remote_lookup: Callable[[str], subprocess.CompletedProcess[bytes]] | None = None,
) -> dict[str, Any]:
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
    lookup = canonical_remote_lookup or _run_canonical_remote
    try:
        remote_tip = lookup(request["repository"])
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
    except (OSError, ValueError) as exc:
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
            post_remote = lookup(request["repository"])
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
