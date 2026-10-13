"""One bounded, on-demand audit through the existing signed native application.

LaunchServices supplies the application's responsible identity. This is not a
scheduler or a permission grant. Every job has an owner birth identity, deadline,
bounded output/RSS, and independently verified native-host completion.
"""

from __future__ import annotations

import ctypes
import json
import os
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from limen.bounded_subprocess import BoundedSubprocessError, _DarwinProcessGroup, _ProcTaskInfo, run_bounded_subprocess
from limen.host_admission import host_temporary_root, process_identity

OUTPUT_LIMIT = 1048576
RSS_LIMIT = 536870912


class NativeAuditError(RuntimeError):
    pass


def source_root() -> Path:
    for candidate in (Path(__file__).resolve().parents[3], Path(sys.prefix).resolve().parent / "source"):
        if (candidate / "scripts/tcc-identity-audit.py").is_file():
            return candidate.resolve()
    raise NativeAuditError("native_audit_source_unavailable")


def _read(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > limit:
            raise NativeAuditError("native_audit_evidence_unsafe")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            value = stream.read(limit + 1)
        if len(value) > limit:
            raise NativeAuditError("native_audit_output_oversized")
        return value
    finally:
        os.close(fd)


def _write(path: Path, value: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _json(path: Path) -> dict:
    value = json.loads(_read(path, 16384))
    if not isinstance(value, dict):
        raise NativeAuditError("native_audit_evidence_invalid")
    return value


def _identity(pid: int) -> str | None:
    identity = process_identity(pid)
    if sys.platform == "darwin" and identity and not identity.startswith("darwin-proc-start:"):
        return None
    return identity


def _alive(pid: int, identity: str) -> bool:
    current = _identity(pid)
    if current is None:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        raise NativeAuditError("native_audit_identity_unmeasured")
    return current == identity


def _host_command_matches(pid: int, host: Path, request: Path) -> bool:
    result = subprocess.run(
        ["/bin/ps", "-ww", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=1, check=False
    )
    return result.returncode == 0 and str(host) in result.stdout and str(request) in result.stdout


def _rss(pid: int) -> int:
    if sys.platform == "darwin":
        group = _DarwinProcessGroup(pid)
        info = _ProcTaskInfo()
        size = group.library.proc_pidinfo(pid, 4, 0, ctypes.byref(info), ctypes.sizeof(info))
        if size != ctypes.sizeof(info):
            raise BoundedSubprocessError("unavailable", stage="rss_census")
        return int(info.resident_size)
    result = subprocess.run(["ps", "-p", str(pid), "-o", "rss="], capture_output=True, timeout=1, check=False)
    if result.returncode != 0 or not result.stdout.strip().isdigit():
        raise BoundedSubprocessError("unavailable", stage="rss_census")
    return int(result.stdout.strip()) * 1024


def _group_rss(pgid: int) -> int:
    if sys.platform == "darwin":
        return _DarwinProcessGroup(pgid).rss()
    result = subprocess.run(["ps", "-axo", "pgid=,rss="], capture_output=True, text=True, timeout=1, check=True)
    return sum(
        int(fields[1]) * 1024
        for line in result.stdout.splitlines()
        if len(fields := line.split()) == 2 and int(fields[0]) == pgid
    )


def _heartbeat_ancestor(root: Path) -> tuple[int, str] | None:
    pid = os.getppid()
    deadline = time.monotonic() + 1
    for _ in range(32):
        if pid <= 1:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise NativeAuditError("native_audit_ancestry_unmeasured")
        result = subprocess.run(
            ["/bin/ps", "-ww", "-p", str(pid), "-o", "ppid=,command="],
            capture_output=True,
            text=True,
            timeout=min(0.25, remaining),
            check=True,
        )
        fields = result.stdout.strip().split(None, 1)
        if len(fields) != 2:
            raise NativeAuditError("native_audit_ancestry_unmeasured")
        if str(root.parent / "venv/bin/limen") + " heartbeat --once" in fields[1]:
            identity = _identity(pid)
            if not identity:
                raise NativeAuditError("native_audit_ancestry_unmeasured")
            return pid, identity
        pid = int(fields[0])
    raise NativeAuditError("native_audit_ancestry_unmeasured")


def _failed(code: str) -> bytes:
    return json.dumps(
        {
            "schema": "limen.tcc_identity_audit.v2",
            "ok": False,
            "status": "unmeasured",
            "failures": [code],
            "native_output_complete": False,
            "malformed_claude_helpers": [],
            "measured": {"tcc_database": False, "launchservices": False, "native_job_cleanup": False},
        }
    ).encode()


def _context_rss(request: dict, host_pid: int, receiver_pid: int) -> int:
    owner_pid, owner_identity = request["owner_pid"], request["owner_identity"]
    if not _alive(owner_pid, owner_identity) or os.getpgid(owner_pid) != request["owner_group"]:
        raise BoundedSubprocessError("unavailable", stage="descendant_census")
    groups = {request["owner_group"]}
    ancestor = request.get("heartbeat_ancestor")
    if ancestor:
        if not _alive(ancestor[0], ancestor[1]):
            raise BoundedSubprocessError("unavailable", stage="descendant_census")
        groups.add(os.getpgid(ancestor[0]))
    return sum(_group_rss(group) for group in groups) + sum(
        _rss(pid) for pid in (host_pid, receiver_pid) if os.getpgid(pid) not in groups
    )


def receive(request_path: Path) -> int:
    request_path = request_path.resolve()
    directory = request_path.parent
    directory_info = directory.stat()
    if directory_info.st_uid != os.getuid() or directory_info.st_mode & 0o077:
        raise NativeAuditError("native_audit_directory_unsafe")
    request = _json(request_path)
    if request.get("schema") != "limen.native_tcc_request.v1" or request.get("implementation") != str(
        source_root() / "scripts/tcc-identity-audit.py"
    ):
        raise NativeAuditError("native_audit_request_invalid")
    owner_pid, owner_identity = request["owner_pid"], request["owner_identity"]
    remaining = request["deadline"] - time.monotonic()
    if remaining <= 2 or not _alive(owner_pid, owner_identity):
        raise NativeAuditError("native_audit_owner_expired")
    host_pid = os.getppid()
    host_identity = _identity(host_pid)
    if not host_identity or not _host_command_matches(host_pid, Path(request["host"]), request_path):
        raise NativeAuditError("native_audit_host_identity_invalid")
    claim = {
        "nonce": request["nonce"],
        "host_pid": host_pid,
        "host_identity": host_identity,
        "receiver_pid": os.getpid(),
        "receiver_identity": _identity(os.getpid()),
        "host_verified": True,
    }
    _write(directory / "claim.json", json.dumps(claim).encode())

    def cancelled(*_args):
        raise BoundedSubprocessError("unavailable")

    signal.setitimer(signal.ITIMER_REAL, 0)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, cancelled)
    signal.setitimer(signal.ITIMER_REAL, min(22, remaining - 1))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_LIMIT, OUTPUT_LIMIT))

    def extra_rss():
        if not _alive(owner_pid, owner_identity) or not _alive(host_pid, host_identity):
            raise BoundedSubprocessError("unavailable", stage="descendant_census")
        return _context_rss(request, host_pid, os.getpid())

    try:
        signal.signal(signal.SIGALRM, cancelled)
        timeout = min(20, remaining - 2)
        completed = run_bounded_subprocess(
            [
                sys.executable,
                request["implementation"],
                "--strict",
                "--json",
                "--budget-seconds",
                str(min(19, timeout - 1)),
            ],
            cwd=source_root(),
            timeout_seconds=timeout,
            cpu_seconds=60,
            rss_ceiling=RSS_LIMIT,
            stdout_ceiling=OUTPUT_LIMIT,
            stderr_ceiling=65536,
            additional_rss=extra_rss,
            env={"HOME": str(Path.home()), "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
        )
        stdout, stderr, code = completed.stdout, completed.stderr, completed.returncode
        verified_empty = True
    except BoundedSubprocessError as exc:
        stdout, stderr, code = _failed(f"native_tcc_audit_{exc.kind}"), b"", 69
        verified_empty = False
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    _write(directory / "stdout.bin", stdout)
    _write(directory / "stderr.bin", stderr)
    _write(
        directory / "result.json",
        json.dumps(
            {"nonce": request["nonce"], "returncode": code, "worker_group_verified_empty": verified_empty}
        ).encode(),
    )
    return 0


def launch(
    host: Path,
    implementation: Path,
    *,
    opener: str = "/usr/bin/open",
    budget_seconds: float = 27,
    scratch_root: Path | None = None,
) -> tuple[int, bytes, bytes]:
    if isinstance(budget_seconds, bool) or not 0 < budget_seconds <= 27:
        raise NativeAuditError("native_audit_budget_invalid")
    root = source_root()
    if implementation.resolve() != root / "scripts/tcc-identity-audit.py":
        raise NativeAuditError("native_audit_implementation_invalid")
    identity = _identity(os.getpid())
    if not identity:
        raise NativeAuditError("native_audit_owner_identity_unavailable")
    ancestor = _heartbeat_ancestor(root)
    directory = Path(tempfile.mkdtemp(prefix="limen-tcc-audit-", dir=scratch_root or host_temporary_root())).resolve()
    directory.chmod(0o700)
    request_path = directory / "request.json"
    job_deadline = time.monotonic() + budget_seconds
    request = {
        "schema": "limen.native_tcc_request.v1",
        "nonce": uuid.uuid4().hex,
        "owner_pid": os.getpid(),
        "owner_identity": identity,
        "owner_group": os.getpgrp(),
        "heartbeat_ancestor": ancestor,
        "deadline": job_deadline,
        "host": str(host),
        "implementation": str(implementation.resolve()),
    }
    _write(request_path, json.dumps(request).encode())
    for name in ("host.stdout", "host.stderr"):
        _write(directory / name, b"")
    app = host.parents[2]
    process = None
    claim = None
    verified_claim = False
    cleaned = False
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    next_rss = 0.0

    def read_claim():
        candidate = _json(directory / "bootstrap.json")
        if candidate.get("nonce") != request["nonce"]:
            raise NativeAuditError("native_audit_claim_invalid")
        host_identity = _identity(candidate["host_pid"])
        receiver_identity = _identity(candidate["receiver_pid"])
        if (
            not host_identity
            or not receiver_identity
            or not _host_command_matches(candidate["host_pid"], host, request_path)
        ):
            raise NativeAuditError("native_audit_claim_unmeasured")
        parent = subprocess.run(
            ["/bin/ps", "-p", str(candidate["receiver_pid"]), "-o", "ppid="],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=True,
        )
        if parent.stdout.strip() != str(candidate["host_pid"]):
            raise NativeAuditError("native_audit_claim_invalid")
        return {
            **candidate,
            "host_identity": host_identity,
            "receiver_identity": receiver_identity,
            "host_verified": True,
        }

    def cancelled(*_args):
        raise NativeAuditError("native_audit_cancelled")

    try:
        for sig in previous:
            signal.signal(sig, cancelled)
        process = subprocess.Popen(
            [
                opener,
                "-W",
                "-n",
                "-g",
                "-a",
                str(app),
                "--stdout",
                str(directory / "host.stdout"),
                "--stderr",
                str(directory / "host.stderr"),
                "--args",
                "run",
                "--",
                sys.executable,
                str(root / "scripts/protected-tcc-audit.py"),
                "--job",
                str(request_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        while time.monotonic() < job_deadline:
            if process.poll() not in (None, 0):
                raise NativeAuditError("native_audit_application_launch_failed")
            if claim is None:
                try:
                    candidate = read_claim()
                    claim = candidate
                    verified_claim = _alive(claim["host_pid"], claim["host_identity"]) and _host_command_matches(
                        claim["host_pid"], host, request_path
                    )
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
            if claim is not None:
                try:
                    result = _json(directory / "result.json")
                    if result.get("nonce") != request["nonce"]:
                        raise NativeAuditError("native_audit_result_invalid")
                    if not _alive(claim["host_pid"], claim["host_identity"]) and not _alive(
                        claim["receiver_pid"], claim["receiver_identity"]
                    ):
                        cleaned = True
                        stdout = _read(directory / "stdout.bin", OUTPUT_LIMIT)
                        payload = json.loads(stdout)
                        if not isinstance(payload, dict) or payload.get("schema") != "limen.tcc_identity_audit.v2":
                            raise NativeAuditError("native_audit_result_invalid")
                        payload.setdefault("measured", {})["native_job_cleanup"] = (
                            result.get("worker_group_verified_empty") is True
                        )
                        payload["native_output_complete"] = result.get("worker_group_verified_empty") is True
                        return (
                            result["returncode"],
                            json.dumps(payload).encode(),
                            _read(directory / "stderr.bin", 65536),
                        )
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                if (
                    time.monotonic() >= next_rss
                    and _alive(claim["host_pid"], claim["host_identity"])
                    and _alive(claim["receiver_pid"], claim["receiver_identity"])
                ):
                    next_rss = time.monotonic() + 1
                    if _context_rss(request, claim["host_pid"], claim["receiver_pid"]) > RSS_LIMIT:
                        raise NativeAuditError("native_audit_resource")
            time.sleep(0.025)
        raise NativeAuditError("native_audit_deadline")
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        # Cancellation can arrive after the receiver claimed its parent but
        # before this loop's next read. Recover that exact claim before cleanup.
        if claim is None or not verified_claim:
            try:
                candidate = read_claim()
                if candidate.get("nonce") == request["nonce"] and candidate.get("host_verified") is True:
                    claim = candidate
                    verified_claim = _alive(claim["host_pid"], claim["host_identity"]) and _host_command_matches(
                        claim["host_pid"], host, request_path
                    )
            except (OSError, ValueError, KeyError, subprocess.SubprocessError, NativeAuditError):
                pass
        if not cleaned:
            _write(
                directory / "cleanup.json",
                json.dumps(
                    {
                        "claim": claim,
                        "verified_claim": verified_claim,
                        "host_alive": bool(claim and _alive(claim["host_pid"], claim["host_identity"])),
                    }
                ).encode(),
            )
        if (
            claim
            and verified_claim
            and _alive(claim["host_pid"], claim["host_identity"])
            and _host_command_matches(claim["host_pid"], host, request_path)
        ):
            os.kill(claim["host_pid"], signal.SIGTERM)
            deadline = time.monotonic() + 1.2
            while time.monotonic() < deadline and _alive(claim["host_pid"], claim["host_identity"]):
                time.sleep(0.025)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.2)
        if claim:
            cleaned = cleaned or (
                not _alive(claim["host_pid"], claim["host_identity"])
                and not _alive(claim["receiver_pid"], claim["receiver_identity"])
            )
        if cleaned:
            shutil.rmtree(directory)


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--job":
            return receive(Path(sys.argv[2]))
        if len(sys.argv) == 4 and sys.argv[1] == "--launch":
            code, stdout, stderr = launch(Path(sys.argv[2]), Path(sys.argv[3]))
            sys.stdout.buffer.write(stdout)
            sys.stderr.buffer.write(stderr)
            return code
        raise NativeAuditError("native_audit_arguments_invalid")
    except (NativeAuditError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        failure_code = str(exc) if isinstance(exc, NativeAuditError) else "native_tcc_route_unavailable"
        sys.stdout.buffer.write(_failed(failure_code))
        return 69
