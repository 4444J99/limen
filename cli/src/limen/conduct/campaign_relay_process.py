"""Bounded provider selection, broker registration, and process/FD proof helpers."""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.conduct.campaign_relay import (
    _CONTROL_LINE_CEILING,
    _REGISTRATION_OUTPUT_CEILING,
    _REGISTRATION_TIMEOUT_SECONDS,
    _RELAY_CONTROL_SCHEMA,
    _STARTUP_OUTPUT_CEILING,
    _TERMINAL_STATES,
    CampaignRelayError,
    _deadline_timeout,
)
from limen.conduct.campaign_relay_state import _read_relay, _replace_relay
from limen.conduct.models import CampaignRelayReceiptV1


def _live_relay_lanes(_root: Path) -> tuple[str, ...]:
    """Resolve installed lanes through the live capacity census before consuming the attempt."""

    try:
        from limen.capacity import select_lanes
        from limen.census import by_name

        live = select_lanes("auto")
    except Exception as exc:
        raise CampaignRelayError(
            "relay_capacity_unavailable",
            "live provider capacity could not be derived",
        ) from exc
    selected: list[str] = []
    for name in live:
        vendor = by_name(name)
        if vendor is None:
            continue
        profile = getattr(vendor, "execution", None)
        direct_native = (
            vendor.local_checkout
            if profile is None
            else profile.transport == "native-cli" or profile.transport.startswith("ianva-")
        )
        if not direct_native:
            continue
        env_key = f"LIMEN_{vendor.name.upper().replace('-', '_')}_BIN"
        override = os.environ.get(env_key, "").strip()
        candidates = tuple(
            dict.fromkeys(
                value
                for value in (
                    override,
                    vendor.name,
                    vendor.binary if vendor.binary == vendor.name else "",
                )
                if value
            )
        )
        if any(shutil.which(candidate) for candidate in candidates):
            selected.append(vendor.name)
    if not selected:
        raise CampaignRelayError(
            "relay_capacity_unavailable",
            "no healthy provider lane has live quota, capacity, and an installed native transport",
        )
    return tuple(selected)


def _bounded_registration(
    *,
    root: Path,
    env: dict[str, str],
    agent: str,
    capabilities: tuple[str, ...],
    session_id: str,
    worktree: Path,
    accepting_work: bool,
    deadline_monotonic: float | None = None,
) -> tuple[str, int]:
    binary = env.get("LIMEN_CLI_BIN", "").strip() or "limen"
    resolved = shutil.which(binary)
    if resolved is None:
        raise CampaignRelayError(
            "relay_registration_unavailable",
            "campaign relay registration client is unavailable",
        )
    command = [
        resolved,
        "conduct",
        "register",
        "--agent",
        agent,
        "--surface",
        "workstream",
        "--session-id",
        session_id,
        "--origin",
        "relay",
        "--worktree",
        str(worktree),
        "--concurrency",
        "1",
        "--accepting-work" if accepting_work else "--not-accepting-work",
    ]
    for capability in capabilities:
        command.extend(["--capability", capability])
    try:
        result = run_bounded_subprocess(
            command,
            cwd=root,
            env=env,
            timeout_seconds=_deadline_timeout(
                deadline_monotonic,
                _REGISTRATION_TIMEOUT_SECONDS,
            ),
            stdout_ceiling=_REGISTRATION_OUTPUT_CEILING,
            stderr_ceiling=_REGISTRATION_OUTPUT_CEILING,
        )
    except BoundedSubprocessError as exc:
        if exc.kind == "timeout":
            raise CampaignRelayError(
                "relay_registration_timeout",
                "campaign relay registration exceeded its bounded deadline",
            ) from exc
        if exc.kind == "output":
            raise CampaignRelayError(
                "relay_registration_oversized",
                "campaign relay registration exceeded its output ceiling",
            ) from exc
        raise CampaignRelayError(
            "relay_registration_unavailable",
            "campaign relay registration client could not start",
        ) from exc
    response = result.stdout
    if result.returncode != 0 or not response:
        raise CampaignRelayError(
            "relay_registration_failed",
            "campaign relay registration was rejected",
        )
    try:
        payload = json.loads(response)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignRelayError(
            "relay_registration_invalid",
            "campaign relay registration response is invalid",
        ) from exc
    identity = payload.get("identity") if isinstance(payload, dict) else None
    returned_capabilities = payload.get("capabilities") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("session_id") != session_id
        or payload.get("origin") != "relay"
        or payload.get("accepting_work") is not accepting_work
        or payload.get("worktree") != str(worktree.resolve())
        or not isinstance(identity, dict)
        or identity.get("agent") != agent
        or identity.get("surface") != "workstream"
        or not isinstance(returned_capabilities, list)
        or set(returned_capabilities) != set(capabilities)
    ):
        raise CampaignRelayError(
            "relay_registration_invalid",
            "campaign relay registration response does not bind the exact dormant session",
        )
    return hashlib.sha256(response).hexdigest(), len(response)


def _process_start_identity(pid: int) -> str:
    identity = ""
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.is_file():
        try:
            raw = proc_stat.read_text(encoding="ascii")
            fields = raw[raw.rindex(")") + 2 :].split()
            identity = f"linux-clock-ticks:{fields[19]}"
        except (OSError, UnicodeError, ValueError, IndexError):
            identity = ""
    elif sys.platform == "darwin":

        class ProcBSDInfo(ctypes.Structure):
            _fields_ = [
                ("flags", ctypes.c_uint32),
                ("status", ctypes.c_uint32),
                ("xstatus", ctypes.c_uint32),
                ("pid", ctypes.c_uint32),
                ("ppid", ctypes.c_uint32),
                ("uid", ctypes.c_uint32),
                ("gid", ctypes.c_uint32),
                ("ruid", ctypes.c_uint32),
                ("rgid", ctypes.c_uint32),
                ("svuid", ctypes.c_uint32),
                ("svgid", ctypes.c_uint32),
                ("rfu_1", ctypes.c_uint32),
                ("comm", ctypes.c_char * 16),
                ("name", ctypes.c_char * 32),
                ("nfiles", ctypes.c_uint32),
                ("pgid", ctypes.c_uint32),
                ("pjobc", ctypes.c_uint32),
                ("e_tdev", ctypes.c_uint32),
                ("e_tpgid", ctypes.c_uint32),
                ("nice", ctypes.c_int32),
                ("start_tvsec", ctypes.c_uint64),
                ("start_tvusec", ctypes.c_uint64),
            ]

        try:
            library = ctypes.CDLL("/usr/lib/libproc.dylib")
            value = ProcBSDInfo()
            size = library.proc_pidinfo(
                pid,
                3,
                0,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if size == ctypes.sizeof(value):
                identity = f"darwin-timeval:{value.start_tvsec}:{value.start_tvusec}"
        except (OSError, AttributeError):
            identity = ""
    if not identity or len(identity) > 256:
        raise CampaignRelayError(
            "relay_process_identity_unavailable",
            "campaign relay process identity is invalid",
        )
    return identity


class _BoundedStreamDigest:
    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self._bytes = 0
        self._truncated = False
        self._read_failed = False
        self._lock = threading.Lock()
        self._output_ceiling_crossed = threading.Event()

    def consume(self, stream: Any) -> None:
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                with self._lock:
                    remaining = max(0, _STARTUP_OUTPUT_CEILING - self._bytes)
                    captured = chunk[:remaining]
                    if captured:
                        self._digest.update(captured)
                        self._bytes += len(captured)
                    if len(chunk) > remaining:
                        self._truncated = True
                        self._bytes = _STARTUP_OUTPUT_CEILING + 1
                        self._output_ceiling_crossed.set()
        except (OSError, ValueError):
            with self._lock:
                self._read_failed = True
        finally:
            try:
                stream.close()
            except (OSError, ValueError):
                with self._lock:
                    self._read_failed = True

    def snapshot(self) -> tuple[str, int, bool]:
        with self._lock:
            return self._digest.hexdigest(), self._bytes, self._truncated

    def read_failed(self) -> bool:
        with self._lock:
            return self._read_failed

    def output_ceiling_crossed(self) -> bool:
        """Report an output-cap breach immediately, without waiting for stream EOF."""

        return self._output_ceiling_crossed.is_set()

    def wait_for_output_ceiling(self, timeout: float | None = None) -> bool:
        """Wait for an output-cap breach without coupling it to stream completion."""

        return self._output_ceiling_crossed.wait(timeout)


def _startup_evidence(
    stdout: _BoundedStreamDigest,
    stderr: _BoundedStreamDigest,
) -> dict[str, Any]:
    stdout_sha, stdout_bytes, stdout_truncated = stdout.snapshot()
    stderr_sha, stderr_bytes, stderr_truncated = stderr.snapshot()
    return {
        "startup_stdout_sha256": stdout_sha,
        "startup_stdout_bytes": stdout_bytes,
        "startup_stdout_truncated": stdout_truncated,
        "startup_stderr_sha256": stderr_sha,
        "startup_stderr_bytes": stderr_bytes,
        "startup_stderr_truncated": stderr_truncated,
    }


def _terminalize_relay(
    root: Path,
    relay_id: str,
    *,
    state: str,
    code: str,
    stdout: _BoundedStreamDigest,
    stderr: _BoundedStreamDigest,
    deadline_monotonic: float | None = None,
) -> CampaignRelayReceiptV1:
    current = _read_relay(
        root,
        relay_id,
        deadline_monotonic=deadline_monotonic,
    )
    if current.state == "ready" or current.state in _TERMINAL_STATES:
        return current
    return _replace_relay(
        root,
        relay_id,
        expected_states=frozenset({"launching", "registered", "published"}),
        updates={
            "state": state,
            "terminal_code": code,
            **_startup_evidence(stdout, stderr),
        },
        deadline_monotonic=deadline_monotonic,
    )


def _validate_control_event(raw: bytes, relay_id: str) -> dict[str, Any]:
    if len(raw) > _CONTROL_LINE_CEILING:
        raise CampaignRelayError(
            "relay_control_oversized",
            "campaign relay control event exceeded its bounded size",
        )
    try:
        event = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignRelayError(
            "relay_control_invalid",
            "campaign relay control event is invalid",
        ) from exc
    if (
        not isinstance(event, dict)
        or event.get("schema") != _RELAY_CONTROL_SCHEMA
        or event.get("relay_id") != relay_id
        or event.get("stage") not in {"selected", "published", "exec_pending"}
    ):
        raise CampaignRelayError(
            "relay_control_invalid",
            "campaign relay control event is invalid",
        )
    return event


def _acknowledge_relay(descriptor: int, payload: bytes) -> None:
    if payload not in {b"registered\n", b"launch\n"}:
        raise CampaignRelayError(
            "relay_ack_invalid",
            "campaign relay acknowledgement is invalid",
        )
    try:
        while payload:
            written = os.write(descriptor, payload)
            payload = payload[written:]
    except OSError as exc:
        raise CampaignRelayError(
            "relay_ack_failed",
            "campaign relay acknowledgement channel closed unexpectedly",
        ) from exc


def _spawn_relay_process(
    command: list[str],
    *,
    root: Path,
    env: dict[str, str],
    ack_descriptor: int,
    control_descriptor: int,
    exec_descriptor: int,
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        command,
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=(ack_descriptor, control_descriptor, exec_descriptor),
    )


def _reap_relay_process(process: subprocess.Popen[bytes]) -> None:
    """Reap the long-lived provider after the finite startup controller returns."""

    if process.poll() is not None:
        return
    threading.Thread(
        target=process.wait,
        name=f"campaign-relay-reaper-{process.pid}",
        daemon=True,
    ).start()


def _open_activation_directory(worktree: Path) -> int:
    capsule_dir = worktree / ".limen-workstream"
    try:
        resolved_worktree = worktree.resolve(strict=True)
        resolved_capsule = capsule_dir.resolve(strict=True)
        resolved_capsule.relative_to(resolved_worktree)
    except (OSError, ValueError) as exc:
        raise CampaignRelayError(
            "relay_activation_marker_failed",
            "campaign relay activation directory is unavailable",
        ) from exc
    if (
        capsule_dir.is_symlink()
        or not resolved_capsule.is_dir()
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
    ):
        raise CampaignRelayError(
            "relay_activation_marker_failed",
            "campaign relay activation directory is invalid",
        )
    try:
        descriptor = os.open(
            resolved_capsule,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        path_metadata = os.stat(resolved_capsule, follow_symlinks=False)
        opened_metadata = os.fstat(descriptor)
    except OSError as exc:
        raise CampaignRelayError(
            "relay_activation_marker_failed",
            "campaign relay activation directory could not be opened safely",
        ) from exc
    if (
        not stat.S_ISDIR(path_metadata.st_mode)
        or not stat.S_ISDIR(opened_metadata.st_mode)
        or (path_metadata.st_dev, path_metadata.st_ino) != (opened_metadata.st_dev, opened_metadata.st_ino)
    ):
        os.close(descriptor)
        raise CampaignRelayError(
            "relay_activation_marker_failed",
            "campaign relay activation directory identity changed",
        )
    return descriptor


def _write_activation_marker(worktree: Path, relay_id: str) -> None:
    directory = _open_activation_directory(worktree)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(
            "relay-activated",
            flags,
            0o600,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(f"{relay_id}\n".encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory)
    except OSError as exc:
        raise CampaignRelayError(
            "relay_activation_marker_failed",
            "campaign relay activation marker could not be persisted",
        ) from exc
    finally:
        os.close(directory)


@contextmanager
def _activation_registration_lock(
    worktree: Path,
    *,
    deadline_monotonic: float | None = None,
) -> Iterator[None]:
    directory = _open_activation_directory(worktree)
    descriptor = -1
    locked = False
    try:
        descriptor = os.open(
            "relay-registration.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise CampaignRelayError(
                "relay_activation_lock_failed",
                "campaign relay activation lock is not a private regular file",
            )
        deadline = time.monotonic() + _deadline_timeout(
            deadline_monotonic,
            _REGISTRATION_TIMEOUT_SECONDS + 1,
        )
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise CampaignRelayError(
                        "relay_activation_lock_failed",
                        "campaign relay activation lock exceeded its bounded deadline",
                    ) from exc
                time.sleep(0.05)
        yield
    except CampaignRelayError:
        raise
    except OSError as exc:
        raise CampaignRelayError(
            "relay_activation_lock_failed",
            "campaign relay activation lock is unavailable",
        ) from exc
    finally:
        if locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def _clear_activation_marker(worktree: Path, relay_id: str) -> None:
    directory = _open_activation_directory(worktree)
    descriptor = -1
    try:
        try:
            descriptor = os.open(
                "relay-activated",
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=directory,
            )
        except FileNotFoundError:
            return
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise CampaignRelayError(
                "relay_activation_rollback_failed",
                "campaign relay activation marker is not a private regular file",
            )
        raw = os.read(descriptor, 66)
        if raw != f"{relay_id}\n".encode():
            raise CampaignRelayError(
                "relay_activation_rollback_failed",
                "campaign relay activation marker identity changed",
            )
        os.close(descriptor)
        descriptor = -1
        os.unlink("relay-activated", dir_fd=directory)
        os.fsync(directory)
    except CampaignRelayError:
        raise
    except OSError as exc:
        raise CampaignRelayError(
            "relay_activation_rollback_failed",
            "campaign relay activation marker could not be cleared",
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def _finish_drains(
    threads: tuple[threading.Thread, threading.Thread],
    *,
    deadline: float,
) -> bool:
    for thread in threads:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        thread.join(timeout=remaining)
    return not any(thread.is_alive() for thread in threads)
