"""Validated, provider-neutral contract for a conducted workstream.

The contract is copied into each continuation capsule so the launch surface can
admit a session without depending on the Limen checkout that rendered it.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, cast

SCHEMA = "limen.workstream.contract.v1"
SCHEMA_V2 = "limen.workstream.contract.v2"
RECEIPT_SCHEMA = "limen.workstream.receipt.v1"
IDENTITY_SCHEMA = "limen.workstream.capsule-identity.v2"
WORKSTREAM_SUCCESSOR_REQUIRED_LABEL = "workstream:successor-required"
DEFAULT_RUNWAY = "1d"
MIN_RUNWAY_SECONDS = 15 * 60
MAX_RUNWAY_SECONDS = 30 * 24 * 60 * 60
PREDECESSOR_RECEIPT_CEILING = 256 * 1024
GIT_CONTROL_STDOUT_CEILING = 4096
GIT_CONTROL_STDERR_CEILING = 4096
GIT_CONTROL_TIMEOUT_SECONDS = 10
SUCCESSOR_RUNWAY_MODES = frozenset({"inherit", "renew"})
_DURATION_RE = re.compile(r"^([1-9][0-9]*)([mhd])$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_WORKSTREAM_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
CODEX_SANDBOXES = frozenset({"read-only", "workspace-write", "danger-full-access"})
RECEIPT_MODULES = (
    "README.md",
    "manifest.md",
    "workstream.json",
    "workstream-contract.py",
    "intent.md",
    "runtime.md",
    "closeout.md",
    "kickstart.sh",
    "capsule.identity",
)
IDENTITY_MODULES = tuple(name for name in RECEIPT_MODULES if name != "capsule.identity")

AUTHORIZATION = {
    "mode": "full_non_destructive",
    "approval_mode": "never",
    "sandbox": "workspace-write",
    "reversible_in_scope": "proceed_without_confirmation",
    "retained_gates": [
        "destructive",
        "credential",
        "paid_spend",
        "public_send",
        "runtime_or_host_mutation",
    ],
}

CONDUCTOR = {
    "mode": "route_bounded_packets",
    "lane_selection": "derive_from_live_capabilities",
    "provider_and_model": "provider_neutral",
    "boundary_rule": "recheck_remaining_runway_before_each_packet",
    "expiry_rule": "stop_or_emit_successor_before_zero",
}


class ContractError(ValueError):
    """The workstream contract cannot be trusted."""


class RunwayExpired(ContractError):
    """No new session may be admitted at or after the deadline."""


class _BoundedCommandInterrupted(BaseException):
    """A handled wrapper signal interrupted one bounded command."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def parse_runway(raw: str) -> tuple[str, int]:
    value = str(raw or "").strip().lower()
    match = _DURATION_RE.fullmatch(value)
    if not match:
        raise ContractError("runway must be a bounded duration such as 90m, 8h, or 7d")
    count = int(match.group(1))
    multiplier = {"m": 60, "h": 3600, "d": 86400}[match.group(2)]
    seconds = count * multiplier
    if not MIN_RUNWAY_SECONDS <= seconds <= MAX_RUNWAY_SECONDS:
        raise ContractError(f"runway must be between {MIN_RUNWAY_SECONDS // 60}m and {MAX_RUNWAY_SECONDS // 86400}d")
    return value, seconds


def new_contract(runway: str = DEFAULT_RUNWAY) -> dict[str, Any]:
    normalized, seconds = parse_runway(runway)
    return {
        "schema": SCHEMA,
        "runway": {
            "requested": normalized,
            "duration_seconds": seconds,
            "started_at": None,
            "started_epoch": None,
            "deadline_at": None,
            "deadline_epoch": None,
        },
        "authorization": copy.deepcopy(AUTHORIZATION),
        "conductor": copy.deepcopy(CONDUCTOR),
    }


def _authorization_for_sandbox(sandbox: str) -> dict[str, Any]:
    if sandbox not in CODEX_SANDBOXES:
        allowed = ", ".join(sorted(CODEX_SANDBOXES))
        raise ContractError(f"Codex sandbox must be one of: {allowed}")
    authorization = copy.deepcopy(AUTHORIZATION)
    authorization["sandbox"] = sandbox
    return authorization


def _primary_launch(
    *,
    agent: object,
    model: object,
    reasoning_effort: object,
) -> dict[str, str]:
    primary_launch = {
        "agent": str(agent or "").strip(),
        "model": str(model or "").strip(),
        "reasoning_effort": str(reasoning_effort or "").strip(),
        "selection": "human_explicit",
    }
    if primary_launch["agent"] != "codex":
        raise ContractError("explicit workstream launch profiles require the Codex native lane")
    if not primary_launch["model"]:
        raise ContractError("explicit workstream launch profiles require a model")
    if not primary_launch["reasoning_effort"]:
        raise ContractError("explicit workstream launch profiles require a reasoning effort")
    return primary_launch


def new_contract_v2(
    runway: str,
    *,
    agent: str,
    model: str,
    reasoning_effort: str,
    sandbox: str,
) -> dict[str, Any]:
    contract = new_contract(runway)
    contract["schema"] = SCHEMA_V2
    contract["authorization"] = _authorization_for_sandbox(sandbox)
    contract["primary_launch"] = _primary_launch(
        agent=agent,
        model=model,
        reasoning_effort=reasoning_effort,
    )
    return contract


def _validate_v2_contract(value: dict[str, Any]) -> None:
    if set(value) != {"schema", "runway", "authorization", "conductor", "primary_launch"}:
        raise ContractError("workstream contract has unknown or missing top-level fields")
    primary_launch = value.get("primary_launch")
    if not isinstance(primary_launch, dict) or set(primary_launch) != {
        "agent",
        "model",
        "reasoning_effort",
        "selection",
    }:
        raise ContractError("workstream primary launch profile has unknown or missing fields")
    expected_primary = _primary_launch(
        agent=primary_launch.get("agent"),
        model=primary_launch.get("model"),
        reasoning_effort=primary_launch.get("reasoning_effort"),
    )
    if primary_launch != expected_primary:
        raise ContractError("workstream primary launch profile is invalid")
    authorization = value.get("authorization")
    if not isinstance(authorization, dict):
        raise ContractError("workstream authorization contract is invalid")
    expected_authorization = _authorization_for_sandbox(str(authorization.get("sandbox") or ""))
    if authorization != expected_authorization:
        raise ContractError("workstream authorization contract is invalid")


def validate_contract(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError("workstream contract has unknown or missing top-level fields")
    schema = value.get("schema")
    if schema == SCHEMA:
        if set(value) != {"schema", "runway", "authorization", "conductor"}:
            raise ContractError("workstream contract has unknown or missing top-level fields")
    elif schema == SCHEMA_V2:
        _validate_v2_contract(value)
    else:
        raise ContractError("workstream contract schema is unsupported")
    runway = value.get("runway")
    if not isinstance(runway, dict) or set(runway) != {
        "requested",
        "duration_seconds",
        "started_at",
        "started_epoch",
        "deadline_at",
        "deadline_epoch",
    }:
        raise ContractError("workstream runway has unknown or missing fields")
    requested, seconds = parse_runway(str(runway.get("requested") or ""))
    raw_seconds = runway.get("duration_seconds")
    if isinstance(raw_seconds, bool) or not isinstance(raw_seconds, int) or raw_seconds != seconds:
        raise ContractError("workstream runway duration does not match its requested value")

    started_epoch = runway.get("started_epoch")
    deadline_epoch = runway.get("deadline_epoch")
    started_at = runway.get("started_at")
    deadline_at = runway.get("deadline_at")
    if started_epoch is None:
        if any(item is not None for item in (deadline_epoch, started_at, deadline_at)):
            raise ContractError("unstarted workstream runway carries partial timing state")
    else:
        if (
            isinstance(started_epoch, bool)
            or not isinstance(started_epoch, int)
            or isinstance(deadline_epoch, bool)
            or not isinstance(deadline_epoch, int)
            or not isinstance(started_at, str)
            or not isinstance(deadline_at, str)
            or deadline_epoch != started_epoch + seconds
            or started_at != _iso(started_epoch)
            or deadline_at != _iso(deadline_epoch)
        ):
            raise ContractError("started workstream runway timing state is invalid")

    if schema == SCHEMA and value.get("authorization") != AUTHORIZATION:
        raise ContractError("workstream authorization contract is invalid")
    if value.get("conductor") != CONDUCTOR:
        raise ContractError("workstream conductor contract is invalid")
    return value


def validate_codex_launch(
    binary: str,
    *,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Prove an exact human override against the live local Codex catalog."""

    if not binary.strip():
        raise ContractError("Codex binary is required for live model validation")
    if not model.strip() or not reasoning_effort.strip():
        raise ContractError("Codex model and reasoning effort are required")
    if isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= 120:
        raise ContractError("Codex catalog timeout must be between 1 and 120 seconds")
    try:
        result = subprocess.run(
            [binary, "debug", "models"],
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContractError(f"live Codex model catalog is unavailable: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise ContractError(f"live Codex model catalog query failed{suffix}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("live Codex model catalog returned invalid JSON") from exc
    entries = payload if isinstance(payload, list) else payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ContractError("live Codex model catalog has an unsupported shape")
    selected = next(
        (entry for entry in entries if isinstance(entry, dict) and entry.get("slug") == model),
        None,
    )
    if selected is None:
        raise ContractError(f"Codex model {model!r} is not present in the live local catalog")
    raw_levels = selected.get("supported_reasoning_levels")
    if not isinstance(raw_levels, list):
        raise ContractError(f"Codex model {model!r} does not publish reasoning capabilities")
    levels = {
        level if isinstance(level, str) else level.get("effort") if isinstance(level, dict) else None
        for level in raw_levels
    }
    levels.discard(None)
    if reasoning_effort not in levels:
        raise ContractError(f"Codex model {model!r} does not support reasoning effort {reasoning_effort!r}")
    return selected


def validate_packet_contract(value: object) -> dict[str, Any]:
    """Validate the immutable workstream subset carried by a dispatch packet."""

    if not isinstance(value, dict) or set(value) != {"schema", "runway", "authorization", "conductor"}:
        raise ContractError("workstream packet contract has unknown or missing top-level fields")
    if value.get("schema") != SCHEMA:
        raise ContractError("workstream packet contract schema is unsupported")
    runway = value.get("runway")
    if not isinstance(runway, dict) or set(runway) != {
        "requested",
        "duration_seconds",
        "started_epoch",
        "deadline_epoch",
    }:
        raise ContractError("workstream packet runway has unknown or missing fields")
    _requested, seconds = parse_runway(str(runway.get("requested") or ""))
    raw_seconds = runway.get("duration_seconds")
    if isinstance(raw_seconds, bool) or not isinstance(raw_seconds, int) or raw_seconds != seconds:
        raise ContractError("workstream packet runway duration does not match its requested value")
    started_epoch = runway.get("started_epoch")
    deadline_epoch = runway.get("deadline_epoch")
    if (
        isinstance(started_epoch, bool)
        or not isinstance(started_epoch, int)
        or started_epoch < 0
        or isinstance(deadline_epoch, bool)
        or not isinstance(deadline_epoch, int)
        or deadline_epoch != started_epoch + seconds
    ):
        raise ContractError("workstream packet timing does not match its admitted duration")
    if value.get("authorization") != AUTHORIZATION:
        raise ContractError("workstream packet authorization contract is invalid")
    if value.get("conductor") != CONDUCTOR:
        raise ContractError("workstream packet conductor contract is invalid")
    return value


def read_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"workstream contract not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise ContractError(f"workstream contract is unreadable: {path}") from exc
    return validate_contract(value)


def _write_if_changed(path: Path, value: dict[str, Any]) -> bool:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
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


def _normalize_workstream_handle(workstream: str | None) -> str | None:
    normalized = (workstream or "").strip() or None
    if normalized is not None and not _WORKSTREAM_RE.fullmatch(normalized):
        raise ContractError("receipt workstream handle is invalid")
    return normalized


def _validate_branch(branch: str) -> str:
    if (
        not branch
        or len(branch.encode("utf-8")) > 255
        or branch.startswith(("-", "/", "."))
        or branch.endswith(("/", "."))
        or branch == "@"
        or ".." in branch
        or "@{" in branch
        or "//" in branch
        or any(ord(character) < 32 or ord(character) == 127 for character in branch)
        or any(character in " ~^:?*[\\\n\r\t" for character in branch)
    ):
        raise ContractError("receipt branch is invalid")
    components = branch.split("/")
    if any(not component or component.startswith(".") or component.endswith(".lock") for component in components):
        raise ContractError("receipt branch is invalid")
    return branch


def validate_receipt_metadata(
    *,
    slug: str,
    branch: str,
    workstream: str | None,
) -> tuple[str, str, str | None]:
    if not _SLUG_RE.fullmatch(slug):
        raise ContractError("receipt slug is invalid")
    return slug, _validate_branch(branch), _normalize_workstream_handle(workstream)


def _predecessor_metadata(
    *,
    slug: str | None,
    branch: str | None,
    receipt_sha256: str | None,
) -> dict[str, str] | None:
    values = (slug, branch, receipt_sha256)
    if not any(value for value in values):
        if any(value is not None and value != "" for value in values):
            raise ContractError("predecessor lineage must provide slug, branch, and receipt digest together")
        return None
    if not all(isinstance(value, str) and value for value in values):
        raise ContractError("predecessor lineage must provide slug, branch, and receipt digest together")
    validated_slug, validated_branch, _workstream = validate_receipt_metadata(
        slug=cast(str, slug),
        branch=cast(str, branch),
        workstream=None,
    )
    digest = cast(str, receipt_sha256)
    if not _SHA256_RE.fullmatch(digest):
        raise ContractError("predecessor receipt digest must be lowercase SHA-256")
    return {
        "slug": validated_slug,
        "branch": validated_branch,
        "receipt_sha256": digest,
    }


def validate_workstream_receipt(value: object) -> dict[str, Any]:
    """Validate one redacted workstream receipt without trusting its local path."""

    if not isinstance(value, dict):
        raise ContractError("workstream receipt must be an object")
    required = {"schema", "slug", "branch", "workstream", "contract", "private_capsule"}
    optional = {"provider_run", "predecessor"}
    if not required <= set(value) or not set(value) <= required | optional:
        raise ContractError("workstream receipt has unknown or missing fields")
    if value.get("schema") != RECEIPT_SCHEMA:
        raise ContractError("workstream receipt schema is unsupported")
    slug_value = value.get("slug")
    branch_value = value.get("branch")
    workstream_value = value.get("workstream")
    if (
        not isinstance(slug_value, str)
        or not isinstance(branch_value, str)
        or (workstream_value is not None and not isinstance(workstream_value, str))
    ):
        raise ContractError("workstream receipt metadata types are invalid")
    slug, branch, workstream = validate_receipt_metadata(
        slug=slug_value,
        branch=branch_value,
        workstream=workstream_value,
    )
    if value.get("workstream") != workstream:
        raise ContractError("workstream receipt handle is invalid")
    contract = validate_contract(value.get("contract"))
    if value.get("private_capsule") != {
        "content": "redacted",
        "modules": list(RECEIPT_MODULES),
    }:
        raise ContractError("workstream receipt private capsule declaration is invalid")

    normalized: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "slug": slug,
        "branch": branch,
        "workstream": workstream,
        "contract": contract,
        "private_capsule": value["private_capsule"],
    }
    provider_run = value.get("provider_run")
    if provider_run is not None:
        if not isinstance(provider_run, dict) or set(provider_run) != {"provider", "id", "url"}:
            raise ContractError("workstream provider run identity is invalid")
        provider = provider_run.get("provider")
        run_id = provider_run.get("id")
        if (
            not isinstance(provider, str)
            or not _SLUG_RE.fullmatch(provider)
            or not isinstance(run_id, str)
            or not run_id.isdigit()
            or provider_run.get("url") != f"https://jules.google.com/session/{run_id}"
        ):
            raise ContractError("workstream provider run identity is invalid")
        normalized["provider_run"] = provider_run

    predecessor = value.get("predecessor")
    if predecessor is not None:
        if not isinstance(predecessor, dict) or set(predecessor) != {
            "slug",
            "branch",
            "receipt_sha256",
        }:
            raise ContractError("workstream predecessor lineage is invalid")
        normalized_predecessor = _predecessor_metadata(
            slug=predecessor.get("slug"),
            branch=predecessor.get("branch"),
            receipt_sha256=predecessor.get("receipt_sha256"),
        )
        if predecessor != normalized_predecessor:
            raise ContractError("workstream predecessor lineage is invalid")
        normalized["predecessor"] = predecessor
    return normalized


def _git_control(
    root: Path,
    *args: str,
    stdout_ceiling: int = GIT_CONTROL_STDOUT_CEILING,
) -> bytes:
    """Run one Git custody probe with wall-clock and separate output ceilings."""

    if stdout_ceiling < 0:
        raise ContractError("committed predecessor receipt Git metadata ceiling is invalid")
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    streams: dict[int, tuple[str, Any]] = {}
    chunks: dict[str, list[bytes]] = {"stdout": [], "stderr": []}
    sizes = {"stdout": 0, "stderr": 0}
    ceilings = {"stdout": stdout_ceiling, "stderr": GIT_CONTROL_STDERR_CEILING}
    deadline = time.monotonic() + GIT_CONTROL_TIMEOUT_SECONDS
    try:
        process = subprocess.Popen(
            ["git", "-C", str(root), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=environment,
        )
        if process.stdout is None or process.stderr is None:  # pragma: no cover - PIPE invariant
            raise ContractError("committed predecessor receipt Git metadata pipes are unavailable")
        selector = selectors.DefaultSelector()
        for label, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            descriptor = stream.fileno()
            os.set_blocking(descriptor, False)
            selector.register(descriptor, selectors.EVENT_READ)
            streams[descriptor] = (label, stream)

        while streams:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ContractError("committed predecessor receipt Git metadata timed out")
            for key, _mask in selector.select(timeout=min(remaining, 0.1)):
                label, stream = streams[key.fd]
                remaining_output = ceilings[label] - sizes[label]
                chunk = os.read(key.fd, min(65_536, remaining_output + 1))
                if not chunk:
                    selector.unregister(key.fd)
                    streams.pop(key.fd)
                    stream.close()
                    continue
                sizes[label] += len(chunk)
                if sizes[label] > ceilings[label]:
                    raise ContractError("committed predecessor receipt Git metadata exceeded its output ceiling")
                chunks[label].append(chunk)
        try:
            returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise ContractError("committed predecessor receipt Git metadata timed out") from exc
    except ContractError:
        if process is not None:
            _terminate_process_group(process, process.pid)
        raise
    except OSError as exc:
        if process is not None:
            _terminate_process_group(process, process.pid)
        raise ContractError("committed predecessor receipt Git metadata is unavailable") from exc
    except BaseException:
        if process is not None:
            _terminate_process_group(process, process.pid)
        raise
    finally:
        if selector is not None:
            selector.close()
        for _label, stream in streams.values():
            stream.close()

    if returncode != 0:
        raise ContractError("committed predecessor receipt Git metadata is invalid")
    return b"".join(chunks["stdout"])


def _read_bounded_predecessor_receipt(receipt_path: Path) -> tuple[bytes, os.stat_result]:
    """Read one real local receipt through a single descriptor and a hard byte ceiling."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(receipt_path, flags)
        descriptor_info = os.fstat(descriptor)
        path_info = receipt_path.lstat()
        if (
            stat.S_ISLNK(path_info.st_mode)
            or not stat.S_ISREG(path_info.st_mode)
            or not stat.S_ISREG(descriptor_info.st_mode)
            or (path_info.st_dev, path_info.st_ino) != (descriptor_info.st_dev, descriptor_info.st_ino)
        ):
            raise ContractError("predecessor receipt must be a real file")
        if not 0 < descriptor_info.st_size <= PREDECESSOR_RECEIPT_CEILING:
            raise ContractError("predecessor receipt exceeds its bounded size")
        chunks: list[bytes] = []
        captured = 0
        while captured <= PREDECESSOR_RECEIPT_CEILING:
            chunk = os.read(descriptor, min(65_536, PREDECESSOR_RECEIPT_CEILING + 1 - captured))
            if not chunk:
                break
            captured += len(chunk)
            if captured > PREDECESSOR_RECEIPT_CEILING:
                raise ContractError("predecessor receipt exceeds its bounded size")
            chunks.append(chunk)
        local = b"".join(chunks)
        if len(local) != descriptor_info.st_size:
            raise ContractError("predecessor receipt changed during bounded capture")
        return local, descriptor_info
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError("predecessor receipt is unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _verify_predecessor_receipt_identity(receipt_path: Path, captured: os.stat_result) -> None:
    """Fail if the local custody path changed after its bounded descriptor capture."""

    try:
        current = receipt_path.lstat()
    except OSError as exc:
        raise ContractError("predecessor receipt is unavailable") from exc
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if (
        stat.S_ISLNK(current.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or any(getattr(current, field) != getattr(captured, field) for field in stable_fields)
    ):
        raise ContractError("predecessor receipt changed during bounded capture")


def predecessor_custody(receipt_path: Path) -> tuple[dict[str, Any], dict[str, str], str]:
    """Load one exact remotely custodied predecessor receipt and its checkout head."""

    local, local_info = _read_bounded_predecessor_receipt(receipt_path)
    try:
        resolved = receipt_path.resolve(strict=True)
        root_raw = _git_control(receipt_path.parent, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        root = Path(root_raw).resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ContractError("predecessor receipt must belong to one Git checkout") from exc
    relative_posix = PurePosixPath(relative.as_posix())
    if (
        len(relative_posix.parts) != 4
        or relative_posix.parts[:2] != ("docs", "continuations")
        or relative_posix.name != "workstream.json"
        or any(part in {"", ".", ".."} for part in relative_posix.parts)
    ):
        raise ContractError("predecessor receipt path is not canonical")

    object_name = f"HEAD:{relative_posix.as_posix()}"
    try:
        _git_control(root, "cat-file", "-e", object_name)
    except ContractError as exc:
        raise ContractError("predecessor receipt is not committed at the checkout HEAD") from exc
    try:
        committed_size = int(_git_control(root, "cat-file", "-s", object_name).decode("ascii").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise ContractError("predecessor receipt is not committed at the checkout HEAD") from exc
    if not 0 < committed_size <= PREDECESSOR_RECEIPT_CEILING:
        raise ContractError("predecessor receipt exceeds its bounded size")
    committed = _git_control(
        root,
        "cat-file",
        "blob",
        object_name,
        stdout_ceiling=PREDECESSOR_RECEIPT_CEILING,
    )
    if len(committed) != committed_size:
        raise ContractError("predecessor receipt changed during committed capture")
    _verify_predecessor_receipt_identity(receipt_path, local_info)
    if local != committed:
        raise ContractError("predecessor receipt must match its committed HEAD bytes")
    try:
        receipt = validate_workstream_receipt(json.loads(committed.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("committed predecessor receipt is invalid JSON") from exc
    if receipt["slug"] != relative_posix.parts[2]:
        raise ContractError("predecessor receipt slug does not match its custody path")
    try:
        checkout_branch = _git_control(root, "symbolic-ref", "--quiet", "--short", "HEAD").decode("utf-8").strip()
        checkout_head = _git_control(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ContractError("predecessor checkout Git identity is invalid") from exc
    if checkout_branch != receipt["branch"]:
        raise ContractError("predecessor receipt branch does not match its checkout branch")
    if not _GIT_OID_RE.fullmatch(checkout_head):
        raise ContractError("predecessor checkout HEAD is invalid")
    try:
        remote_raw = _git_control(
            root,
            "ls-remote",
            "--exit-code",
            "origin",
            f"refs/heads/{receipt['branch']}",
        ).decode("ascii")
    except (ContractError, UnicodeDecodeError) as exc:
        raise ContractError("predecessor receipt branch has no verifiable origin custody") from exc
    remote_rows = [line.split() for line in remote_raw.splitlines() if line.strip()]
    expected_ref = f"refs/heads/{receipt['branch']}"
    if (
        len(remote_rows) != 1
        or len(remote_rows[0]) != 2
        or not _GIT_OID_RE.fullmatch(remote_rows[0][0])
        or remote_rows[0][1] != expected_ref
    ):
        raise ContractError("predecessor receipt branch has invalid origin custody")
    if remote_rows[0][0] != checkout_head:
        raise ContractError("predecessor checkout HEAD is not the exact origin branch head")
    _verify_predecessor_receipt_identity(receipt_path, local_info)
    runway = receipt["contract"]["runway"]
    if runway["started_epoch"] is None or runway["deadline_epoch"] is None:
        raise ContractError("predecessor workstream has not been admitted")
    lineage = {
        "slug": receipt["slug"],
        "branch": receipt["branch"],
        "receipt_sha256": hashlib.sha256(committed).hexdigest(),
    }
    return receipt, lineage, checkout_head


def predecessor_lineage(receipt_path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Return validated path-free lineage while keeping checkout details ephemeral."""

    receipt, lineage, _checkout_head = predecessor_custody(receipt_path)
    return receipt, lineage


def successor_metadata(
    predecessor_receipt: Path,
    *,
    runway_mode: str = "inherit",
    requested: str | None = None,
) -> tuple[dict[str, Any], dict[str, str], str]:
    """Derive a successor contract, lineage, and its exact remotely custodied base."""

    if runway_mode not in SUCCESSOR_RUNWAY_MODES:
        raise ContractError("successor runway mode must be inherit or renew")
    if runway_mode == "inherit" and requested is not None:
        raise ContractError("inherited successors cannot specify a new runway")
    if runway_mode == "renew" and requested is None:
        raise ContractError("renewed successors require an explicit runway")
    receipt, lineage, checkout_head = predecessor_custody(predecessor_receipt)
    predecessor = receipt["contract"]
    if runway_mode == "inherit":
        inherited = new_contract(predecessor["runway"]["requested"])
        inherited["runway"] = copy.deepcopy(predecessor["runway"])
        return inherited, lineage, checkout_head

    return new_contract(cast(str, requested)), lineage, checkout_head


def successor_contract(
    predecessor_receipt: Path,
    *,
    runway_mode: str = "inherit",
    requested: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Derive one successor contract without changing predecessor state."""

    contract, lineage, _checkout_head = successor_metadata(
        predecessor_receipt,
        runway_mode=runway_mode,
        requested=requested,
    )
    return contract, lineage


def configure_successor_contract(
    path: Path,
    predecessor_receipt: Path,
    *,
    runway_mode: str = "inherit",
    requested: str | None = None,
    expected_receipt_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, str], bool]:
    """Write an exact successor contract while preserving predecessor bytes."""

    contract, lineage = successor_contract(
        predecessor_receipt,
        runway_mode=runway_mode,
        requested=requested,
    )
    if expected_receipt_sha256 is not None and lineage["receipt_sha256"] != expected_receipt_sha256:
        raise ContractError("predecessor receipt changed during successor creation")
    with _contract_lock(path):
        if path.exists():
            existing = read_contract(path)
            if existing != contract:
                raise ContractError("existing successor contract conflicts with its predecessor")
            return existing, lineage, False
        return contract, lineage, _write_if_changed(path, contract)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_capsule_modules(
    owner_path: Path,
    modules: list[tuple[str, Path]],
    *,
    expected_names: tuple[str, ...],
) -> tuple[Path, dict[str, Path]]:
    if owner_path.parent.name != ".limen-workstream" or owner_path.parent.is_symlink():
        raise ContractError("private capsule must live in a real .limen-workstream directory")
    try:
        capsule_dir = owner_path.parent.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"capsule directory is unreadable: {owner_path.parent}") from exc
    names = [name for name, _path in modules]
    if len(names) != len(set(names)):
        raise ContractError("private capsule module names must be unique")
    if set(names) != set(expected_names):
        raise ContractError("private capsule modules do not match the required set")
    by_name = dict(modules)
    normalized: dict[str, Path] = {}
    for name in expected_names:
        path = by_name[name]
        if path.name != name or path.is_symlink():
            raise ContractError(f"private capsule module is unsafe: {name}")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ContractError(f"private capsule module is unreadable: {name}") from exc
        if not path.is_file() or resolved.parent != capsule_dir:
            raise ContractError(f"private capsule module is outside the capsule: {name}")
        normalized[name] = path
    return capsule_dir, normalized


def _identity_payload(
    identity_path: Path,
    invocation_sha256: str,
    modules: list[tuple[str, Path]],
) -> dict[str, Any]:
    if identity_path.name != "capsule.identity" or identity_path.is_symlink():
        raise ContractError("capsule identity path is unsafe")
    if not _SHA256_RE.fullmatch(invocation_sha256):
        raise ContractError("capsule invocation identity is invalid")
    _capsule_dir, normalized = _private_capsule_modules(
        identity_path,
        modules,
        expected_names=IDENTITY_MODULES,
    )
    return {
        "schema": IDENTITY_SCHEMA,
        "invocation_sha256": invocation_sha256,
        "modules": {name: _sha256_file(normalized[name]) for name in IDENTITY_MODULES},
    }


def sync_identity(
    identity_path: Path,
    *,
    invocation_sha256: str,
    modules: list[tuple[str, Path]],
) -> tuple[dict[str, Any], bool]:
    if identity_path.parent.name != ".limen-workstream" or identity_path.parent.is_symlink():
        raise ContractError("private capsule must live in a real .limen-workstream directory")
    with _contract_lock(identity_path):
        payload = _identity_payload(identity_path, invocation_sha256, modules)
        return payload, _write_if_changed(identity_path, payload)


def verify_identity(
    identity_path: Path,
    *,
    invocation_sha256: str,
    modules: list[tuple[str, Path]],
) -> dict[str, Any]:
    expected = _identity_payload(identity_path, invocation_sha256, modules)
    try:
        actual = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"capsule identity is unreadable: {identity_path}") from exc
    if actual != expected:
        raise ContractError("capsule identity or module bytes changed; emit a successor capsule")
    return actual


@contextmanager
def _contract_lock(path: Path) -> Iterator[None]:
    """Serialize read-modify-replace operations without leaving a lock artifact.

    Locking the stable parent-directory inode avoids the stale-inode race that
    would result from locking ``workstream.json`` while atomically replacing it.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def configure_contract(
    path: Path,
    requested: str | None = None,
    *,
    agent: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    sandbox: str | None = None,
) -> tuple[dict[str, Any], bool]:
    launch_values = (agent, model, reasoning_effort, sandbox)
    explicit_launch = any(value is not None for value in launch_values)
    if explicit_launch and not all(value is not None for value in launch_values):
        raise ContractError("explicit workstream launch profiles require agent, model, reasoning effort, and sandbox")

    def configured_contract(runway: str) -> dict[str, Any]:
        if not explicit_launch:
            return new_contract(runway)
        return new_contract_v2(
            runway,
            agent=cast(str, agent),
            model=cast(str, model),
            reasoning_effort=cast(str, reasoning_effort),
            sandbox=cast(str, sandbox),
        )

    with _contract_lock(path):
        if path.exists():
            contract = read_contract(path)
            expected_schema = SCHEMA_V2 if explicit_launch else contract["schema"]
            if contract["schema"] != expected_schema:
                raise ContractError("cannot change an existing launch profile; emit a successor workstream")
            if explicit_launch:
                expected_launch = configured_contract(contract["runway"]["requested"])
                if (
                    contract["primary_launch"] != expected_launch["primary_launch"]
                    or contract["authorization"] != expected_launch["authorization"]
                ):
                    raise ContractError("cannot change an existing launch profile; emit a successor workstream")
            if requested is None:
                return contract, False
            normalized, seconds = parse_runway(requested)
            runway = contract["runway"]
            if runway["duration_seconds"] == seconds:
                return contract, False
            if runway["started_epoch"] is not None:
                raise ContractError("cannot change an admitted runway; emit a successor workstream")
            if contract["schema"] == SCHEMA_V2 and not explicit_launch:
                primary_launch = contract["primary_launch"]
                contract = new_contract_v2(
                    normalized,
                    agent=primary_launch["agent"],
                    model=primary_launch["model"],
                    reasoning_effort=primary_launch["reasoning_effort"],
                    sandbox=contract["authorization"]["sandbox"],
                )
            else:
                contract = configured_contract(normalized)
        else:
            contract = configured_contract(requested or DEFAULT_RUNWAY)
        return contract, _write_if_changed(path, contract)


def _iso(epoch: int) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat(timespec="seconds")


def admit_contract(path: Path, *, now_epoch: int | None = None) -> tuple[dict[str, Any], int]:
    with _contract_lock(path):
        contract = read_contract(path)
        runway = contract["runway"]
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        if runway["started_epoch"] is None:
            runway["started_epoch"] = now
            runway["started_at"] = _iso(now)
            runway["deadline_epoch"] = now + int(runway["duration_seconds"])
            runway["deadline_at"] = _iso(int(runway["deadline_epoch"]))
            _write_if_changed(path, contract)
        remaining = int(runway["deadline_epoch"]) - now
        if remaining <= 0:
            raise RunwayExpired("workstream runway is exhausted; emit a successor capsule")
        return contract, remaining


def admit_contract_with_identity(
    contract_path: Path,
    identity_path: Path,
    *,
    invocation_sha256: str,
    modules: list[tuple[str, Path]],
    now_epoch: int | None = None,
) -> tuple[dict[str, Any], int, bool]:
    """Admit one runway while advancing only the identity's mutable contract hash."""

    if identity_path.parent != contract_path.parent:
        raise ContractError("capsule identity and contract do not share one owner")
    with _contract_lock(contract_path):
        previous_identity = verify_identity(
            identity_path,
            invocation_sha256=invocation_sha256,
            modules=modules,
        )
        contract = read_contract(contract_path)
        original_contract = copy.deepcopy(contract)
        runway = contract["runway"]
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        identity_changed = False
        if runway["started_epoch"] is None:
            runway["started_epoch"] = now
            runway["started_at"] = _iso(now)
            runway["deadline_epoch"] = now + int(runway["duration_seconds"])
            runway["deadline_at"] = _iso(int(runway["deadline_epoch"]))
            try:
                _write_if_changed(contract_path, contract)
                advanced_identity = _identity_payload(identity_path, invocation_sha256, modules)
                for name in IDENTITY_MODULES:
                    if name == "workstream.json":
                        continue
                    if advanced_identity["modules"][name] != previous_identity["modules"][name]:
                        raise ContractError(
                            f"capsule module changed during admission: {name}; emit a successor capsule"
                        )
                try:
                    current_identity = json.loads(identity_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ContractError("capsule identity changed during admission") from exc
                if current_identity != previous_identity:
                    raise ContractError("capsule identity changed during admission")
                identity_changed = _write_if_changed(identity_path, advanced_identity)
                verify_identity(
                    identity_path,
                    invocation_sha256=invocation_sha256,
                    modules=modules,
                )
            except BaseException:
                _write_if_changed(contract_path, original_contract)
                _write_if_changed(identity_path, previous_identity)
                raise
        else:
            verify_identity(
                identity_path,
                invocation_sha256=invocation_sha256,
                modules=modules,
            )
        remaining = int(runway["deadline_epoch"]) - now
        if remaining <= 0:
            raise RunwayExpired("workstream runway is exhausted; emit a successor capsule")
        return contract, remaining, identity_changed


def sync_receipt(
    contract_path: Path,
    receipt_path: Path,
    *,
    slug: str,
    branch: str,
    workstream: str | None,
    modules: list[tuple[str, Path]],
    predecessor_slug: str | None = None,
    predecessor_branch: str | None = None,
    predecessor_receipt_sha256: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Write a tracked, redacted derivative of one private capsule.

    The receipt embeds the validated finite contract and safe custody facts, but
    never stores private module paths, bodies, or content-derived hashes.
    """

    slug, branch, normalized_workstream = validate_receipt_metadata(
        slug=slug,
        branch=branch,
        workstream=workstream,
    )
    predecessor = _predecessor_metadata(
        slug=predecessor_slug,
        branch=predecessor_branch,
        receipt_sha256=predecessor_receipt_sha256,
    )
    names = [name for name, _path in modules]
    if len(names) != len(set(names)):
        raise ContractError("receipt module names must be unique")
    if set(names) != set(RECEIPT_MODULES):
        raise ContractError("receipt modules do not match the required capsule set")

    with _contract_lock(contract_path):
        contract = read_contract(contract_path)
        capsule_dir, normalized_modules = _private_capsule_modules(
            contract_path,
            modules,
            expected_names=RECEIPT_MODULES,
        )
        if normalized_modules["workstream.json"].resolve() != contract_path.resolve():
            raise ContractError("receipt contract module does not match its contract owner")
        expected_receipt = capsule_dir.parent / "docs" / "continuations" / slug / "workstream.json"
        candidate_receipt = Path(os.path.abspath(receipt_path))
        if candidate_receipt != expected_receipt or candidate_receipt.resolve(strict=False) != expected_receipt:
            raise ContractError("receipt path escapes its tracked continuation custody home")

        identity_path = normalized_modules["capsule.identity"]
        try:
            identity_value = json.loads(identity_path.read_text(encoding="utf-8"))
            invocation_sha256 = identity_value["invocation_sha256"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ContractError("capsule identity is unreadable") from exc
        if not isinstance(invocation_sha256, str):
            raise ContractError("capsule invocation identity is invalid")
        verify_identity(
            identity_path,
            invocation_sha256=invocation_sha256,
            modules=[(name, normalized_modules[name]) for name in IDENTITY_MODULES],
        )

        receipt = {
            "schema": RECEIPT_SCHEMA,
            "slug": slug,
            "branch": branch,
            "workstream": normalized_workstream,
            "contract": contract,
            "private_capsule": {
                "content": "redacted",
                "modules": list(RECEIPT_MODULES),
            },
        }
        if predecessor is not None:
            receipt["predecessor"] = predecessor
        return receipt, _write_if_changed(receipt_path, receipt)


def _process_group_alive(process_group_id: int) -> bool:
    """Return whether any process remains in the bounded command's group."""

    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # A group that still exists but cannot be signalled is not clean.
        return True
    return True


def _wait_for_process_group_exit(
    process: subprocess.Popen[Any],
    process_group_id: int,
    timeout_seconds: float,
) -> bool:
    """Reap the leader while waiting finitely for every group member to exit."""

    deadline = time.monotonic() + timeout_seconds
    while True:
        process.poll()
        if not _process_group_alive(process_group_id):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))


def _terminate_process_group(
    process: subprocess.Popen[Any],
    process_group_id: int,
) -> bool:
    """Stop every remaining member of one bounded command's process group."""

    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return True
    if _wait_for_process_group_exit(process, process_group_id, 2):
        return True
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        return True
    return _wait_for_process_group_exit(process, process_group_id, 2)


def run_bounded(argv: list[str], timeout_seconds: int) -> int:
    """Run one capsule preflight in its own process group with a finite ceiling."""

    if not argv:
        raise ContractError("bounded command requires an executable")
    if isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= 300:
        raise ContractError("bounded command timeout must be between 1 and 300 seconds")
    if threading.current_thread() is not threading.main_thread():
        raise ContractError("bounded command must run on the main thread for signal-safe cleanup")

    watched_signals = tuple(
        signum
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        if signal.getsignal(signum) != signal.SIG_IGN
    )
    previous_handlers = {signum: signal.getsignal(signum) for signum in watched_signals}
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, watched_signals)
    installed_handlers: list[signal.Signals] = []
    process: subprocess.Popen[Any] | None = None
    process_group_id: int | None = None
    interruption_state: dict[str, int | bool | None] = {
        "cleaning": False,
        "signum": None,
    }
    interrupted_signal: int | None = None
    timed_out = False
    returncode = 127
    cleanup_ok = True
    start_error: OSError | None = None

    def handle_interrupt(signum: int, _frame: Any) -> None:
        if interruption_state["signum"] is None:
            interruption_state["signum"] = signum
        if process_group_id is None:
            return
        forwarded_signal = signal.SIGKILL if interruption_state["cleaning"] else signal.SIGTERM
        try:
            os.killpg(process_group_id, forwarded_signal)
        except ProcessLookupError:
            pass
        if not interruption_state["cleaning"]:
            raise _BoundedCommandInterrupted(signum)

    try:
        for signum in watched_signals:
            signal.signal(signum, handle_interrupt)
            installed_handlers.append(signum)
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        if interruption_state["signum"] is not None:
            raise _BoundedCommandInterrupted(int(interruption_state["signum"]))
        try:
            process = subprocess.Popen(argv, start_new_session=True)
            process_group_id = process.pid
        except OSError as exc:
            start_error = exc
        if interruption_state["signum"] is not None:
            if process_group_id is not None:
                try:
                    os.killpg(process_group_id, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            raise _BoundedCommandInterrupted(int(interruption_state["signum"]))

        if process is not None:
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                returncode = 124
    except _BoundedCommandInterrupted as exc:
        interrupted_signal = exc.signum
        returncode = 128 + exc.signum
    except KeyboardInterrupt:
        interrupted_signal = signal.SIGINT
        returncode = 128 + signal.SIGINT
    finally:
        interruption_state["cleaning"] = True
        if (
            process is not None
            and process_group_id is not None
            and _process_group_alive(process_group_id)
            and not _terminate_process_group(process, process_group_id)
        ):
            cleanup_ok = False
        if process is not None and process.poll() is None:
            cleanup_ok = False
        signal.pthread_sigmask(signal.SIG_BLOCK, watched_signals)
        if interrupted_signal is None and interruption_state["signum"] is not None:
            interrupted_signal = int(interruption_state["signum"])
            returncode = 128 + interrupted_signal
        try:
            for signum in reversed(installed_handlers):
                signal.signal(signum, previous_handlers[signum])
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)

    if start_error is not None:
        print(f"bounded command failed to start: {start_error}", file=sys.stderr)
        returncode = 127
    if not cleanup_ok:
        print(
            f"bounded command cleanup failed: {argv[0]}",
            file=sys.stderr,
        )
        returncode = 125
    if timed_out:
        print(f"bounded command timed out after {timeout_seconds}s: {argv[0]}", file=sys.stderr)
    if interrupted_signal is not None:
        signal.raise_signal(interrupted_signal)
    return returncode


def packet_contract(
    runway: str,
    *,
    now_epoch: int | None = None,
    started_epoch: int | None = None,
    deadline_epoch: int | None = None,
) -> dict[str, Any]:
    """Return one admitted immutable packet contract consumed by dispatch."""

    contract = new_contract(runway)
    seconds = int(contract["runway"]["duration_seconds"])
    if (started_epoch is None) != (deadline_epoch is None):
        raise ContractError("workstream packet timing requires both started and deadline epochs")
    if started_epoch is None:
        if isinstance(now_epoch, bool):
            raise ContractError("workstream packet admission epoch must be an integer")
        admitted_start = int(time.time()) if now_epoch is None else int(now_epoch)
        admitted_deadline = admitted_start + seconds
    else:
        admitted_start = started_epoch
        admitted_deadline = cast(int, deadline_epoch)
    value = {
        "schema": contract["schema"],
        "runway": {
            "requested": contract["runway"]["requested"],
            "duration_seconds": seconds,
            "started_epoch": admitted_start,
            "deadline_epoch": admitted_deadline,
        },
        "authorization": contract["authorization"],
        "conductor": contract["conductor"],
    }
    return validate_packet_contract(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser("normalize")
    normalize.add_argument("runway")

    configure = subparsers.add_parser("configure")
    configure.add_argument("--path", type=Path, required=True)
    configure.add_argument("--runway")
    configure.add_argument("--agent")
    configure.add_argument("--model")
    configure.add_argument("--reasoning-effort")
    configure.add_argument("--sandbox")

    for command_name in ("successor-metadata", "configure-successor"):
        successor = subparsers.add_parser(command_name)
        if command_name == "configure-successor":
            successor.add_argument("--path", type=Path, required=True)
            successor.add_argument("--expected-receipt-sha256")
        successor.add_argument("--predecessor-receipt", type=Path, required=True)
        successor.add_argument("--runway-mode", choices=sorted(SUCCESSOR_RUNWAY_MODES), default="inherit")
        successor.add_argument("--runway")

    # The STATIC half of validate-codex-launch, split out so a caller can reject an invalid sandbox
    # WITHOUT first resolving a codex binary. Argument validity is a property of the arguments, not
    # of what happens to be installed: CI (no codex) must reach the same verdict as a workstation
    # that has one. Deliberately takes no --binary, so it cannot regress into a binary-dependent
    # check. validate-codex-launch still runs this same authorization itself — this adds an earlier
    # gate, it never replaces one.
    codex_sandbox = subparsers.add_parser("validate-codex-sandbox")
    codex_sandbox.add_argument("--sandbox", required=True)

    codex_launch = subparsers.add_parser("validate-codex-launch")
    codex_launch.add_argument("--binary", required=True)
    codex_launch.add_argument("--model", required=True)
    codex_launch.add_argument("--reasoning-effort", required=True)
    codex_launch.add_argument("--sandbox", required=True)
    codex_launch.add_argument("--timeout-seconds", type=int, default=30)

    admit = subparsers.add_parser("admit")
    admit.add_argument("--path", type=Path, required=True)
    admit.add_argument("--now-epoch", type=int)

    receipt = subparsers.add_parser("sync-receipt")
    receipt.add_argument("--contract", type=Path, required=True)
    receipt.add_argument("--receipt", type=Path, required=True)
    receipt.add_argument("--slug", required=True)
    receipt.add_argument("--branch", required=True)
    receipt.add_argument("--workstream")
    receipt.add_argument("--predecessor-slug")
    receipt.add_argument("--predecessor-branch")
    receipt.add_argument("--predecessor-receipt-sha256")
    receipt.add_argument("--module", action="append", default=[], metavar="NAME=PATH")

    metadata = subparsers.add_parser("validate-receipt-metadata")
    metadata.add_argument("--slug", required=True)
    metadata.add_argument("--branch", required=True)
    metadata.add_argument("--workstream")

    for command_name in ("sync-identity", "verify-identity"):
        identity = subparsers.add_parser(command_name)
        identity.add_argument("--identity", type=Path, required=True)
        identity.add_argument("--invocation-sha256", required=True)
        identity.add_argument("--module", action="append", default=[], metavar="NAME=PATH")

    admit_identity = subparsers.add_parser("admit-identity")
    admit_identity.add_argument("--contract", type=Path, required=True)
    admit_identity.add_argument("--identity", type=Path, required=True)
    admit_identity.add_argument("--invocation-sha256", required=True)
    admit_identity.add_argument("--now-epoch", type=int)
    admit_identity.add_argument("--module", action="append", default=[], metavar="NAME=PATH")

    bounded = subparsers.add_parser("run-bounded")
    bounded.add_argument("--timeout-seconds", type=int, required=True)
    bounded.add_argument("argv", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    try:
        if args.command == "normalize":
            requested, seconds = parse_runway(args.runway)
            print(f"{requested}:{seconds}")
        elif args.command == "configure":
            _contract, changed = configure_contract(
                args.path,
                args.runway,
                agent=args.agent,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                sandbox=args.sandbox,
            )
            print("changed" if changed else "unchanged")
        elif args.command in {"successor-metadata", "configure-successor"}:
            if args.command == "configure-successor":
                contract, lineage, changed = configure_successor_contract(
                    args.path,
                    args.predecessor_receipt,
                    runway_mode=args.runway_mode,
                    requested=args.runway,
                    expected_receipt_sha256=args.expected_receipt_sha256,
                )
                print("changed" if changed else "unchanged")
                predecessor_head = ""
            else:
                contract, lineage, predecessor_head = successor_metadata(
                    args.predecessor_receipt,
                    runway_mode=args.runway_mode,
                    requested=args.runway,
                )
            print(lineage["slug"])
            print(lineage["branch"])
            print(lineage["receipt_sha256"])
            print(contract["runway"]["requested"])
            if predecessor_head:
                print(predecessor_head)
        elif args.command == "validate-codex-sandbox":
            # Raises ContractError on an unknown value; echo the accepted one, mirroring
            # validate-codex-launch printing its selected slug.
            print(_authorization_for_sandbox(args.sandbox)["sandbox"])
        elif args.command == "validate-codex-launch":
            _authorization_for_sandbox(args.sandbox)
            selected = validate_codex_launch(
                args.binary,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                timeout_seconds=args.timeout_seconds,
            )
            print(selected["slug"])
        elif args.command == "admit":
            contract, remaining = admit_contract(args.path, now_epoch=args.now_epoch)
            runway = contract["runway"]
            print(
                f"{runway['requested']}:{runway['duration_seconds']}:{runway['started_epoch']}:"
                f"{runway['deadline_epoch']}:{remaining}"
            )
        elif args.command == "validate-receipt-metadata":
            validate_receipt_metadata(
                slug=args.slug,
                branch=args.branch,
                workstream=args.workstream,
            )
            print("valid")
        elif args.command in {"sync-receipt", "sync-identity", "verify-identity", "admit-identity"}:
            modules: list[tuple[str, Path]] = []
            for raw_module in args.module:
                name, separator, raw_path = raw_module.partition("=")
                if not separator or not name or not raw_path:
                    raise ContractError("capsule modules must use NAME=PATH")
                modules.append((name, Path(raw_path)))
            if args.command == "sync-receipt":
                _receipt, changed = sync_receipt(
                    args.contract,
                    args.receipt,
                    slug=args.slug,
                    branch=args.branch,
                    workstream=args.workstream,
                    modules=modules,
                    predecessor_slug=args.predecessor_slug,
                    predecessor_branch=args.predecessor_branch,
                    predecessor_receipt_sha256=args.predecessor_receipt_sha256,
                )
                print("changed" if changed else "unchanged")
            elif args.command == "sync-identity":
                _identity, changed = sync_identity(
                    args.identity,
                    invocation_sha256=args.invocation_sha256,
                    modules=modules,
                )
                print("changed" if changed else "unchanged")
            elif args.command == "verify-identity":
                verify_identity(
                    args.identity,
                    invocation_sha256=args.invocation_sha256,
                    modules=modules,
                )
                print("valid")
            else:
                contract, remaining, _identity_changed = admit_contract_with_identity(
                    args.contract,
                    args.identity,
                    invocation_sha256=args.invocation_sha256,
                    modules=modules,
                    now_epoch=args.now_epoch,
                )
                runway = contract["runway"]
                print(
                    f"{runway['requested']}:{runway['duration_seconds']}:{runway['started_epoch']}:"
                    f"{runway['deadline_epoch']}:{remaining}"
                )
        else:
            command = list(args.argv)
            if command[:1] == ["--"]:
                command = command[1:]
            return run_bounded(command, args.timeout_seconds)
    except RunwayExpired as exc:
        print(f"workstream contract expired: {exc}", file=sys.stderr)
        return 3
    except ContractError as exc:
        print(f"invalid workstream contract: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
