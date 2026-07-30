"""Credential-isolated native executor half of the conduct full-mesh canary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from limen.conduct.broker import ConductError
from limen.conduct.client import HttpConductClient
from limen.conduct.models import (
    AgentIdentityV1,
    CheckEvidenceV1,
    ConductPrincipalV1,
    PredicateEvidenceV1,
    RunReceiptV1,
)

WAKE_BIN_ENV = "LIMEN_CONDUCT_CANARY_WAKE_BIN"
WAKE_TIMEOUT_ENV = "LIMEN_CONDUCT_CANARY_WAKE_TIMEOUT_SECONDS"
WAKE_REQUEST_SCHEMA = "limen.conduct_canary_native_edge_request.v1"
WAKE_ACK_SCHEMA = "limen.conduct_canary_native_edge_ack.v1"
_DEFAULT_WAKE_TIMEOUT_SECONDS = 60
_MAX_WAKE_TIMEOUT_SECONDS = 300
_WAKE_OUTPUT_CEILING = 32 * 1024
_WAKE_REQUEST_CEILING = 64 * 1024
_PREDICATE_SUMMARY = "observed active heartbeat with unchanged runtime head for one authenticated canary edge"
_IDENTIFIER_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/@+-")
_HASH_LENGTHS = frozenset({40, 64})
_TOKEN_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_BRIDGE_ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "SHELL",
        "TMPDIR",
        "USER",
        "XDG_RUNTIME_DIR",
    }
)
_RESERVED_EXECUTOR_CREDENTIAL_REFS = _BRIDGE_ENV_ALLOWLIST | frozenset(
    {
        "LIMEN_CONDUCT_URL",
        "LIMEN_CONDUCT_TOKEN",
        "LIMEN_CONDUCT_CANARY_CREDENTIAL_REF",
        "LIMEN_CONDUCT_CANARY_CREDENTIAL_REFS",
        "LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY",
        WAKE_BIN_ENV,
        WAKE_TIMEOUT_ENV,
        "LIMEN_SESSION_ID",
        "LIMEN_NATIVE_SESSION_ID",
        "LIMEN_NATIVE_RUN_ID",
    }
)


class NativeCanaryExecutorError(ConductError):
    """A bounded, credential-free native callback failure."""


def _identifier(value: Any, field: str) -> str:
    text = value if isinstance(value, str) else ""
    if (
        not 1 <= len(text) <= 256
        or text[0] not in _IDENTIFIER_CHARS
        or any(character not in _IDENTIFIER_CHARS for character in text)
    ):
        raise NativeCanaryExecutorError(f"{field} must be a bounded protocol identifier")
    return text


def _git_object(value: Any, field: str) -> str:
    text = value if isinstance(value, str) else ""
    if len(text) not in _HASH_LENGTHS or any(character not in "0123456789abcdef" for character in text):
        raise NativeCanaryExecutorError(f"{field} must be an exact lowercase Git object")
    return text


def _positive_generation(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise NativeCanaryExecutorError("generation must be a positive integer")
    return value


def validate_executor_credential_reference(value: Any) -> str:
    """Validate a named executor secret without admitting generic or bridge-visible variables."""

    text = value if isinstance(value, str) else ""
    if not _TOKEN_ENV_RE.fullmatch(text):
        raise NativeCanaryExecutorError("executor_credential_ref must name a bounded environment reference")
    if text in _RESERVED_EXECUTOR_CREDENTIAL_REFS:
        raise NativeCanaryExecutorError("executor_credential_ref must not name a reserved environment variable")
    return text


@dataclass(frozen=True)
class NativeCanaryEdgeRequest:
    canary_id: str
    edge_id: str
    run_id: str
    lease_id: str
    generation: int
    packet_deadline: str
    packet_predicate: str
    receipt_id: str
    runtime_git_sha: str
    executor_session_id: str
    executor_native_session_id: str
    executor_native_run_id: str
    executor_credential_ref: str
    executor_identity: dict[str, Any]
    expected_checks: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        for field in (
            "canary_id",
            "edge_id",
            "run_id",
            "lease_id",
            "receipt_id",
            "executor_session_id",
            "executor_native_session_id",
            "executor_native_run_id",
        ):
            _identifier(getattr(self, field), field)
        validate_executor_credential_reference(self.executor_credential_ref)
        _positive_generation(self.generation)
        _git_object(self.runtime_git_sha, "runtime_git_sha")
        try:
            deadline = datetime.fromisoformat(self.packet_deadline.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise NativeCanaryExecutorError("packet_deadline must be an RFC 3339 timestamp") from exc
        if deadline.tzinfo is None:
            raise NativeCanaryExecutorError("packet_deadline must include a timezone")
        AgentIdentityV1.model_validate(self.executor_identity)
        if not self.packet_predicate or len(self.packet_predicate) > 8192 or "\x00" in self.packet_predicate:
            raise NativeCanaryExecutorError("packet_predicate must be bounded")
        if not self.expected_checks:
            raise NativeCanaryExecutorError("expected_checks must not be empty")
        for check in self.expected_checks:
            CheckEvidenceV1.model_validate(check)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": WAKE_REQUEST_SCHEMA,
            "canary_id": self.canary_id,
            "edge_id": self.edge_id,
            "run_id": self.run_id,
            "lease_id": self.lease_id,
            "generation": self.generation,
            "packet_deadline": self.packet_deadline,
            "packet_predicate": self.packet_predicate,
            "receipt_id": self.receipt_id,
            "runtime_git_sha": self.runtime_git_sha,
            "executor_session_id": self.executor_session_id,
            "executor_native_session_id": self.executor_native_session_id,
            "executor_native_run_id": self.executor_native_run_id,
            "executor_credential_ref": self.executor_credential_ref,
            "executor_identity": self.executor_identity,
            "expected_checks": list(self.expected_checks),
        }

    @property
    def sha256(self) -> str:
        rendered = json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(rendered).hexdigest()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "NativeCanaryEdgeRequest":
        expected = {
            "schema_version",
            "canary_id",
            "edge_id",
            "run_id",
            "lease_id",
            "generation",
            "packet_deadline",
            "packet_predicate",
            "receipt_id",
            "runtime_git_sha",
            "executor_session_id",
            "executor_native_session_id",
            "executor_native_run_id",
            "executor_credential_ref",
            "executor_identity",
            "expected_checks",
        }
        if set(payload) != expected or payload.get("schema_version") != WAKE_REQUEST_SCHEMA:
            raise NativeCanaryExecutorError("native canary request has an invalid schema")
        identity = payload.get("executor_identity")
        checks = payload.get("expected_checks")
        if (
            not isinstance(identity, dict)
            or not isinstance(checks, list)
            or not all(isinstance(check, dict) for check in checks)
        ):
            raise NativeCanaryExecutorError("native canary request contains malformed evidence")
        return cls(
            canary_id=str(payload.get("canary_id") or ""),
            edge_id=str(payload.get("edge_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            lease_id=str(payload.get("lease_id") or ""),
            generation=payload.get("generation"),  # type: ignore[arg-type]
            packet_deadline=str(payload.get("packet_deadline") or ""),
            packet_predicate=str(payload.get("packet_predicate") or ""),
            receipt_id=str(payload.get("receipt_id") or ""),
            runtime_git_sha=str(payload.get("runtime_git_sha") or ""),
            executor_session_id=str(payload.get("executor_session_id") or ""),
            executor_native_session_id=str(payload.get("executor_native_session_id") or ""),
            executor_native_run_id=str(payload.get("executor_native_run_id") or ""),
            executor_credential_ref=str(payload.get("executor_credential_ref") or ""),
            executor_identity=identity,
            expected_checks=tuple(checks),
        )


@dataclass(frozen=True)
class NativeCanaryEdgeAck:
    canary_id: str
    edge_id: str
    run_id: str
    lease_id: str
    generation: int
    receipt_id: str
    runtime_git_sha: str
    executor_session_id: str
    executor_native_session_id: str
    executor_native_run_id: str
    executor_credential_ref: str
    request_sha256: str

    def __post_init__(self) -> None:
        for field in (
            "canary_id",
            "edge_id",
            "run_id",
            "lease_id",
            "receipt_id",
            "executor_session_id",
            "executor_native_session_id",
            "executor_native_run_id",
        ):
            _identifier(getattr(self, field), field)
        validate_executor_credential_reference(self.executor_credential_ref)
        _positive_generation(self.generation)
        _git_object(self.runtime_git_sha, "runtime_git_sha")
        _git_object(self.request_sha256, "request_sha256")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": WAKE_ACK_SCHEMA,
            "canary_id": self.canary_id,
            "edge_id": self.edge_id,
            "run_id": self.run_id,
            "lease_id": self.lease_id,
            "generation": self.generation,
            "receipt_id": self.receipt_id,
            "runtime_git_sha": self.runtime_git_sha,
            "executor_session_id": self.executor_session_id,
            "executor_native_session_id": self.executor_native_session_id,
            "executor_native_run_id": self.executor_native_run_id,
            "executor_credential_ref": self.executor_credential_ref,
            "request_sha256": self.request_sha256,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "NativeCanaryEdgeAck":
        expected = {
            "schema_version",
            "canary_id",
            "edge_id",
            "run_id",
            "lease_id",
            "generation",
            "receipt_id",
            "runtime_git_sha",
            "executor_session_id",
            "executor_native_session_id",
            "executor_native_run_id",
            "executor_credential_ref",
            "request_sha256",
        }
        if set(payload) != expected or payload.get("schema_version") != WAKE_ACK_SCHEMA:
            raise NativeCanaryExecutorError("native canary callback returned an invalid acknowledgement")
        return cls(
            canary_id=str(payload.get("canary_id") or ""),
            edge_id=str(payload.get("edge_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            lease_id=str(payload.get("lease_id") or ""),
            generation=payload.get("generation"),  # type: ignore[arg-type]
            receipt_id=str(payload.get("receipt_id") or ""),
            runtime_git_sha=str(payload.get("runtime_git_sha") or ""),
            executor_session_id=str(payload.get("executor_session_id") or ""),
            executor_native_session_id=str(payload.get("executor_native_session_id") or ""),
            executor_native_run_id=str(payload.get("executor_native_run_id") or ""),
            executor_credential_ref=str(payload.get("executor_credential_ref") or ""),
            request_sha256=str(payload.get("request_sha256") or ""),
        )

    @classmethod
    def expected(cls, request: NativeCanaryEdgeRequest) -> "NativeCanaryEdgeAck":
        return cls(
            canary_id=request.canary_id,
            edge_id=request.edge_id,
            run_id=request.run_id,
            lease_id=request.lease_id,
            generation=request.generation,
            receipt_id=request.receipt_id,
            runtime_git_sha=request.runtime_git_sha,
            executor_session_id=request.executor_session_id,
            executor_native_session_id=request.executor_native_session_id,
            executor_native_run_id=request.executor_native_run_id,
            executor_credential_ref=request.executor_credential_ref,
            request_sha256=request.sha256,
        )

    @property
    def sha256(self) -> str:
        rendered = json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(rendered).hexdigest()


def _session_for_request(capabilities: Mapping[str, Any], request: NativeCanaryEdgeRequest) -> dict[str, Any]:
    principal_fields = set(ConductPrincipalV1.model_fields)
    raw_principal = capabilities.get("authenticated_principal")
    if not isinstance(raw_principal, dict) or set(raw_principal) != principal_fields:
        raise NativeCanaryExecutorError("native callback lacks exact authenticated principal evidence")
    principal = ConductPrincipalV1.model_validate(raw_principal)
    if principal.roles != frozenset({"observer", "executor"}):
        raise NativeCanaryExecutorError("native callback credential is not executor-only")
    bound = capabilities.get("authenticated_session_ids")
    if (
        not isinstance(bound, list)
        or any(not isinstance(value, str) or not value for value in bound)
        or bound != sorted(set(bound))
        or request.executor_session_id not in bound
    ):
        raise NativeCanaryExecutorError("native callback credential is not bound to the executor session")
    sessions = [
        row
        for row in capabilities.get("sessions", [])
        if isinstance(row, dict) and row.get("session_id") == request.executor_session_id
    ]
    if len(sessions) != 1:
        raise NativeCanaryExecutorError("native callback executor session is unavailable or ambiguous")
    session = sessions[0]
    identity = session.get("identity")
    if (
        identity != request.executor_identity
        or not isinstance(identity, dict)
        or principal.agent != identity.get("agent")
        or principal.surface != identity.get("surface")
        or session.get("native_session_id") != request.executor_native_session_id
        or session.get("native_run_id") != request.executor_native_run_id
        or session.get("healthy") is not True
        or session.get("accepting_work") is not True
    ):
        raise NativeCanaryExecutorError("native callback executor session identity changed")
    return session


def runtime_identity_from_environ(environ: Mapping[str, str]) -> dict[str, Any]:
    """Load the callback process's independently installed runtime identity."""

    raw = environ.get("LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY", "").strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NativeCanaryExecutorError("native callback runtime identity must contain valid JSON") from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "git_sha", "deployment_id"}
        or value.get("schema_version") != "limen.conduct_runtime_identity.v1"
    ):
        raise NativeCanaryExecutorError("native callback runtime identity is malformed")
    _git_object(value.get("git_sha"), "runtime_git_sha")
    deployment_id = value.get("deployment_id")
    if not isinstance(deployment_id, str) or not deployment_id or "\x00" in deployment_id or len(deployment_id) > 512:
        raise NativeCanaryExecutorError("native callback deployment identity is malformed")
    return value


def request_from_bytes(payload: bytes) -> NativeCanaryEdgeRequest:
    """Decode one bounded request without admitting trailing protocol material."""

    if not payload or len(payload) > _WAKE_REQUEST_CEILING:
        raise NativeCanaryExecutorError("native canary request exceeds its bounded size")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeCanaryExecutorError("native canary request contains invalid JSON") from exc
    if not isinstance(value, dict):
        raise NativeCanaryExecutorError("native canary request must contain an object")
    return NativeCanaryEdgeRequest.from_payload(value)


def read_native_canary_request(stream: BinaryIO) -> NativeCanaryEdgeRequest:
    """Read exactly one bounded request from the callback's standard input."""

    return request_from_bytes(stream.read(_WAKE_REQUEST_CEILING + 1))


def _require_callback_context(
    request: NativeCanaryEdgeRequest,
    environ: Mapping[str, str],
) -> None:
    expected = {
        "LIMEN_SESSION_ID": request.executor_session_id,
        "LIMEN_NATIVE_SESSION_ID": request.executor_native_session_id,
        "LIMEN_NATIVE_RUN_ID": request.executor_native_run_id,
        "LIMEN_CONDUCT_CANARY_CREDENTIAL_REF": request.executor_credential_ref,
    }
    if any(environ.get(name, "").strip() != value for name, value in expected.items()):
        raise NativeCanaryExecutorError(
            "native callback process identity does not match the requested executor session"
        )


def executor_client_from_environ(
    request: NativeCanaryEdgeRequest,
    environ: Mapping[str, str],
) -> HttpConductClient:
    """Hydrate only the exact executor credential named by the edge request."""

    endpoint = environ.get("LIMEN_CONDUCT_URL", "").strip()
    token = environ.get(request.executor_credential_ref, "").strip()  # allow-secret: exact named executor credential
    if not token:
        raise NativeCanaryExecutorError("native callback executor credential reference is not hydrated")
    try:
        return HttpConductClient(endpoint, token)
    except (ConductError, ValueError) as exc:
        raise NativeCanaryExecutorError("native callback authenticated remote client is not configured") from exc


def execute_native_canary_edge(
    request: NativeCanaryEdgeRequest,
    *,
    client: HttpConductClient,
    environ: Mapping[str, str],
    predicate_runner: Any = subprocess.run,
) -> NativeCanaryEdgeAck:
    """Claim and settle one canary edge from the bound native executor process."""

    if not isinstance(client, HttpConductClient):
        raise NativeCanaryExecutorError("native canary callback requires the authenticated HTTP client")
    _require_callback_context(request, environ)
    runtime_identity = runtime_identity_from_environ(environ)
    if (
        set(runtime_identity) != {"schema_version", "git_sha", "deployment_id"}
        or runtime_identity.get("schema_version") != "limen.conduct_runtime_identity.v1"
        or runtime_identity.get("git_sha") != request.runtime_git_sha
    ):
        raise NativeCanaryExecutorError("native callback runtime does not match the requested exact runtime")
    capabilities = client.capabilities()
    if capabilities.get("runtime_identity") != dict(runtime_identity):
        raise NativeCanaryExecutorError("native callback and keeper runtime identities do not match")
    _session_for_request(capabilities, request)
    claim = client.claim(request.lease_id, request.generation)
    capability_token = str(claim.get("capability_token") or "")
    if (
        claim.get("run_id") != request.run_id
        or claim.get("lease_id") != request.lease_id
        or claim.get("generation") != request.generation
        or not capability_token
    ):
        raise NativeCanaryExecutorError("native callback received an invalid executor claim")
    heartbeat = client.heartbeat(
        request.lease_id,
        capability_token,
        generation=request.generation,
        observed_heads={"runtime": request.runtime_git_sha},
    )
    lease = heartbeat.get("lease")
    if (
        heartbeat.get("status") != "active"
        or not isinstance(lease, dict)
        or lease.get("run_id") != request.run_id
        or lease.get("lease_id") != request.lease_id
        or lease.get("generation") != request.generation
        or lease.get("executor") != request.executor_identity
        or lease.get("observed_heads") != {"runtime": request.runtime_git_sha}
        or lease.get("state") != "active"
    ):
        raise NativeCanaryExecutorError("native callback heartbeat did not bind the exact edge")
    expected_command = f"/bin/test {request.runtime_git_sha} = {request.runtime_git_sha}"
    if request.packet_predicate != expected_command:
        raise NativeCanaryExecutorError("native callback packet predicate is not the exact read-effect probe")
    try:
        result = predicate_runner(
            ("/bin/test", request.runtime_git_sha, "=", request.runtime_git_sha),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NativeCanaryExecutorError("native callback predicate could not complete") from exc
    exit_code = getattr(result, "returncode", None)
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise NativeCanaryExecutorError("native callback predicate returned an invalid exit status")
    if exit_code != 0:
        raise NativeCanaryExecutorError("native callback read-effect predicate failed")
    receipt = RunReceiptV1(
        receipt_id=request.receipt_id,
        run_id=request.run_id,
        lease_id=request.lease_id,
        lease_generation=request.generation,
        executor=AgentIdentityV1.model_validate(request.executor_identity),
        provider_identity=request.executor_native_session_id,
        observed_heads_before={"runtime": request.runtime_git_sha},
        observed_heads_after={"runtime": request.runtime_git_sha},
        changed_paths=(),
        predicate=PredicateEvidenceV1(
            command=request.packet_predicate,
            exit_code=exit_code,
            summary=_PREDICATE_SUMMARY,
        ),
        checks=tuple(CheckEvidenceV1.model_validate(check) for check in request.expected_checks),
        spend={"runs": 0},
        outcome="succeeded",
    )
    report = client.report(
        request.lease_id,
        capability_token,
        receipt,
        generation=request.generation,
    )
    if report.get("mutation_authorized") is not True or report.get("run_status") != "succeeded":
        raise NativeCanaryExecutorError("native callback receipt was not accepted as a successful read effect")
    return NativeCanaryEdgeAck.expected(request)


def _wake_timeout(environ: Mapping[str, str]) -> int:
    raw = environ.get(WAKE_TIMEOUT_ENV, str(_DEFAULT_WAKE_TIMEOUT_SECONDS)).strip()
    try:
        timeout = int(raw)
    except ValueError as exc:
        raise NativeCanaryExecutorError("native canary wake timeout must be an integer") from exc
    if not 1 <= timeout <= _MAX_WAKE_TIMEOUT_SECONDS:
        raise NativeCanaryExecutorError("native canary wake timeout must be between 1 and 300 seconds")
    return timeout


def _bridge_binary(environ: Mapping[str, str]) -> str:
    configured = environ.get(WAKE_BIN_ENV, "").strip()
    resolved = shutil.which(configured) if configured else None
    if resolved is None:
        raise NativeCanaryExecutorError(f"native canary requires a session-owned wake bridge in {WAKE_BIN_ENV}")
    candidate = Path(resolved)
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise NativeCanaryExecutorError("native canary wake bridge is not an executable file")
    return str(candidate)


def resolve_native_canary_bridge(environ: Mapping[str, str]) -> tuple[str, int]:
    """Resolve the session-owned bridge before any canary graph mutation."""

    return _bridge_binary(environ), _wake_timeout(environ)


def _sanitized_bridge_env(environ: Mapping[str, str], credential_ref: str) -> dict[str, str]:
    sanitized = {key: value for key, value in environ.items() if key in _BRIDGE_ENV_ALLOWLIST and key != credential_ref}
    sanitized["LIMEN_CONDUCT_CANARY_CREDENTIAL_REF"] = credential_ref
    return sanitized


def _consume_pipe(
    stream: Any,
    destination: bytearray,
    overflow: threading.Event,
) -> None:
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                return
            remaining = _WAKE_OUTPUT_CEILING - len(destination)
            if len(chunk) > remaining:
                destination.extend(chunk[: max(0, remaining)])
                overflow.set()
                return
            destination.extend(chunk)
    finally:
        stream.close()


def _stop_bridge_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            try:
                process.kill()
            except OSError:
                pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired as exc:
        raise NativeCanaryExecutorError("native canary wake bridge could not be stopped within its bound") from exc


def wake_native_canary_edge(
    request: NativeCanaryEdgeRequest,
    *,
    environ: Mapping[str, str],
    resolved_bridge: tuple[str, int] | None = None,
) -> NativeCanaryEdgeAck:
    """Wake one session-owned callback through a generic, credential-free bridge."""

    binary, timeout = resolved_bridge or resolve_native_canary_bridge(environ)
    payload = (json.dumps(request.to_payload(), sort_keys=True) + "\n").encode()
    try:
        process = subprocess.Popen(
            (binary,),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_sanitized_bridge_env(environ, request.executor_credential_ref),
            start_new_session=True,
        )
    except OSError as exc:
        raise NativeCanaryExecutorError("native canary wake bridge could not start") from exc
    if process.stdin is None or process.stdout is None or process.stderr is None:
        _stop_bridge_process(process)
        raise NativeCanaryExecutorError("native canary wake bridge streams are unavailable")
    stdout = bytearray()
    stderr = bytearray()
    overflow = threading.Event()
    stdout_thread = threading.Thread(
        target=_consume_pipe,
        args=(process.stdout, stdout, overflow),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_consume_pipe,
        args=(process.stderr, stderr, overflow),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    try:
        process.stdin.write(payload)
        process.stdin.close()
    except OSError as exc:
        _stop_bridge_process(process)
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        raise NativeCanaryExecutorError("native canary wake bridge closed its request channel") from exc
    deadline = time.monotonic() + timeout
    while process.poll() is None and not overflow.is_set() and time.monotonic() < deadline:
        time.sleep(0.02)
    timed_out = process.poll() is None and not overflow.is_set()
    _stop_bridge_process(process)
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    if stdout_thread.is_alive() or stderr_thread.is_alive():
        raise NativeCanaryExecutorError("native canary wake bridge did not close its output streams")
    if overflow.is_set():
        raise NativeCanaryExecutorError("native canary wake bridge exceeded its output ceiling")
    if timed_out:
        raise NativeCanaryExecutorError("native canary wake bridge exceeded its bounded timeout")
    if process.returncode != 0:
        raise NativeCanaryExecutorError("native canary wake bridge rejected the edge")
    try:
        value = json.loads(bytes(stdout).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeCanaryExecutorError("native canary wake bridge returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise NativeCanaryExecutorError("native canary wake bridge acknowledgement must be an object")
    acknowledgement = NativeCanaryEdgeAck.from_payload(value)
    if acknowledgement != NativeCanaryEdgeAck.expected(request):
        raise NativeCanaryExecutorError("native canary wake bridge acknowledged a different edge")
    return acknowledgement
