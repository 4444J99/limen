"""Heavy-admission wrapper for one long-lived campaign relay provider."""

from __future__ import annotations

import json
import os
import re
import resource
import select
import signal
import stat
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from limen.host_admission import (
    AdmissionController,
    AdmissionStateError,
    pid_is_alive,
    process_identity,
)
from limen.vigilia import params

ADMISSION_SCHEMA = "limen.campaign_relay_admission.v1"
ADMISSION_HANDSHAKE_CEILING = 2_048
ADMISSION_HANDSHAKE_SECONDS = 10.0
_RELAY_ID_RE = re.compile(r"^[0-9a-f]{64}$")


def _write_handshake(descriptor: int, *, allowed: bool, reasons: Sequence[str]) -> None:
    normalized = sorted(set(reasons))
    payload = (
        json.dumps(
            {
                "allowed": allowed,
                "reasons": normalized,
                "schema": ADMISSION_SCHEMA,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    if len(payload) > ADMISSION_HANDSHAKE_CEILING:
        raise OSError("campaign relay admission handshake exceeded its ceiling")
    while payload:
        written = os.write(descriptor, payload)
        payload = payload[written:]


def _lease_ttl_seconds() -> int:
    return int(params.get("LIMEN_HOST_ADMISSION_LEASE_SECONDS", 900, cast=int))


def _monitor_provider_lease(
    controller: AdmissionController,
    *,
    lease_id: str,
    owner: str,
    provider_pid: int,
    provider_identity: str,
    ttl_seconds: int,
    ready_descriptor: int | None = None,
    alive: Callable[[int], bool] = pid_is_alive,
    identity: Callable[[int], str | None] = process_identity,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Refresh one exact provider lease until its PID or start identity changes."""

    initial = controller.refresh(
        lease_id=lease_id,
        owner=owner,
        pid=provider_pid,
        ttl_seconds=ttl_seconds,
    )
    if not initial["allowed"]:
        if ready_descriptor is not None:
            os.write(ready_descriptor, b"failed\n")
        return
    if ready_descriptor is not None:
        os.write(ready_descriptor, b"ready\n")
        os.close(ready_descriptor)
        ready_descriptor = None

    interval = max(10.0, min(60.0, float(ttl_seconds) / 3.0))
    next_refresh = monotonic() + interval
    while True:
        if not alive(provider_pid):
            controller.release(lease_id=lease_id, owner=owner, pid=provider_pid)
            return
        observed_identity = identity(provider_pid)
        if observed_identity is None:
            # An unavailable identity is never authority to release another process's lease.
            return
        if observed_identity != provider_identity:
            controller.release(lease_id=lease_id, owner=owner, pid=provider_pid)
            return
        now = monotonic()
        if now >= next_refresh:
            refreshed = controller.refresh(
                lease_id=lease_id,
                owner=owner,
                pid=provider_pid,
                ttl_seconds=ttl_seconds,
            )
            if not refreshed["allowed"]:
                return
            next_refresh = now + interval
        sleep(min(1.0, max(0.01, next_refresh - now)))


def _monitor_fd_limit() -> int:
    soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft == resource.RLIM_INFINITY:
        return 1_048_576
    return max(4, min(int(soft), 1_048_576))


def _detach_monitor(ready_descriptor: int) -> int:
    """Detach the refresher without retaining relay control or output descriptors."""

    try:
        os.setsid()
    except OSError:
        pass
    if ready_descriptor != 3:
        os.dup2(ready_descriptor, 3)
        os.close(ready_descriptor)
    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        for descriptor in (0, 1, 2):
            os.dup2(devnull, descriptor)
    finally:
        if devnull > 3:
            os.close(devnull)
    os.closerange(4, _monitor_fd_limit())
    return 3


def _stop_monitor(pid: int) -> None:
    """Stop only the unlaunched wrapper's own monitor child."""

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            finished, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return
        if finished == pid:
            return
        time.sleep(0.02)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass


def _start_lease_monitor(
    controller: AdmissionController,
    *,
    lease_id: str,
    owner: str,
    provider_pid: int,
    provider_identity: str,
    ttl_seconds: int,
) -> int:
    ready_reader, ready_writer = os.pipe()
    monitor_pid = os.fork()
    if monitor_pid == 0:
        os.close(ready_reader)
        descriptor = _detach_monitor(ready_writer)
        try:
            _monitor_provider_lease(
                controller,
                lease_id=lease_id,
                owner=owner,
                provider_pid=provider_pid,
                provider_identity=provider_identity,
                ttl_seconds=ttl_seconds,
                ready_descriptor=descriptor,
            )
        except BaseException:
            try:
                os.write(descriptor, b"failed\n")
            except OSError:
                pass
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
        os._exit(0)

    os.close(ready_writer)
    deadline = time.monotonic() + ADMISSION_HANDSHAKE_SECONDS
    payload = bytearray()
    try:
        while b"\n" not in payload and len(payload) <= 16:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            readable, _writable, _exceptional = select.select([ready_reader], [], [], remaining)
            if not readable:
                break
            chunk = os.read(ready_reader, 17 - len(payload))
            if not chunk:
                break
            payload.extend(chunk)
    finally:
        os.close(ready_reader)
    if bytes(payload) != b"ready\n":
        _stop_monitor(monitor_pid)
        raise OSError("campaign relay admission monitor did not become ready")
    return monitor_pid


def _exec_provider(file: str, args: Sequence[str], environ: dict[str, str]) -> NoReturn:
    """Adapt os.execvpe to the wrapper's deliberately narrow injectable type."""

    os.execvpe(file, list(args), environ)


def run_admission_wrapper(
    command: Sequence[str],
    *,
    handshake_descriptor: int,
    controller: AdmissionController | None = None,
    provider_pid: int | None = None,
    start_monitor: Callable[..., int] = _start_lease_monitor,
    execvpe: Callable[[str, Sequence[str], dict[str, str]], Any] = _exec_provider,
) -> int:
    """Acquire and retain heavy admission before executing any provider command."""

    relay_id = os.environ.get("LIMEN_CAMPAIGN_RELAY_ID", "")
    if not command or not _RELAY_ID_RE.fullmatch(relay_id):
        _write_handshake(
            handshake_descriptor,
            allowed=False,
            reasons=("relay-shape-invalid",),
        )
        os.close(handshake_descriptor)
        return 125

    controller = controller or AdmissionController()
    provider_pid = provider_pid or os.getpid()
    owner = f"campaign-relay-{relay_id[:32]}"
    ttl_seconds = _lease_ttl_seconds()
    try:
        decision = controller.acquire(
            "heavy",
            owner=owner,
            surface="campaign-relay-provider",
            pid=provider_pid,
            ttl_seconds=ttl_seconds,
        )
    except (AdmissionStateError, OSError, ValueError):
        _write_handshake(
            handshake_descriptor,
            allowed=False,
            reasons=("admission-state-unavailable",),
        )
        os.close(handshake_descriptor)
        return 75

    if not decision["allowed"]:
        _write_handshake(
            handshake_descriptor,
            allowed=False,
            reasons=tuple(str(reason) for reason in decision.get("reasons") or ("admission-denied",)),
        )
        os.close(handshake_descriptor)
        return 75
    if decision.get("inherited"):
        # The finite controller may release its ancestor lease before the provider exits.
        # Without a transferable exact-PID lease, launching here would silently lose admission.
        _write_handshake(
            handshake_descriptor,
            allowed=False,
            reasons=("inherited-heavy-lease",),
        )
        os.close(handshake_descriptor)
        return 75

    lease = decision["lease"]
    try:
        monitor_pid = start_monitor(
            controller,
            lease_id=lease["lease_id"],
            owner=owner,
            provider_pid=provider_pid,
            provider_identity=lease["process_identity"],
            ttl_seconds=ttl_seconds,
        )
    except (OSError, ValueError):
        controller.release(
            lease_id=lease["lease_id"],
            owner=owner,
            pid=provider_pid,
        )
        _write_handshake(
            handshake_descriptor,
            allowed=False,
            reasons=("admission-monitor-unavailable",),
        )
        os.close(handshake_descriptor)
        return 75

    try:
        _write_handshake(handshake_descriptor, allowed=True, reasons=())
    except OSError:
        _stop_monitor(monitor_pid)
        controller.release(
            lease_id=lease["lease_id"],
            owner=owner,
            pid=provider_pid,
        )
        return 125
    finally:
        try:
            os.close(handshake_descriptor)
        except OSError:
            pass

    try:
        execvpe(command[0], list(command), dict(os.environ))
    except OSError:
        controller.release(
            lease_id=lease["lease_id"],
            owner=owner,
            pid=provider_pid,
        )
        return 126
    raise AssertionError("execvpe unexpectedly returned")


def _main(argv: Sequence[str]) -> NoReturn:
    if len(argv) < 3 or argv[1] != "--":
        raise SystemExit(64)
    try:
        descriptor = int(argv[0])
        metadata = os.fstat(descriptor)
    except (OSError, ValueError):
        raise SystemExit(64)
    command = tuple(argv[2:])
    if descriptor < 3 or descriptor > 4_096 or not stat.S_ISFIFO(metadata.st_mode) or not command:
        raise SystemExit(64)
    raise SystemExit(
        run_admission_wrapper(
            command,
            handshake_descriptor=descriptor,
        )
    )


if __name__ == "__main__":
    _main(sys.argv[1:])
