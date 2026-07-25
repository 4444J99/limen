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
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, cast

SCHEMA = "limen.workstream.contract.v1"
SCHEMA_V2 = "limen.workstream.contract.v2"
RECEIPT_SCHEMA = "limen.workstream.receipt.v1"
IDENTITY_SCHEMA = "limen.workstream.capsule-identity.v2"
WORKSTREAM_SUCCESSOR_REQUIRED_LABEL = "workstream:successor-required"
DEFAULT_RUNWAY = "1d"
MIN_RUNWAY_SECONDS = 15 * 60
MAX_RUNWAY_SECONDS = 30 * 24 * 60 * 60
_DURATION_RE = re.compile(r"^([1-9][0-9]*)([mhd])$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_WORKSTREAM_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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
