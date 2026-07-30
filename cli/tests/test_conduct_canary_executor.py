from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from limen.conduct.canary_executor import (
    executor_client_from_environ,
    execute_native_canary_edge,
    NativeCanaryEdgeAck,
    NativeCanaryEdgeRequest,
    NativeCanaryExecutorError,
    WAKE_BIN_ENV,
    WAKE_TIMEOUT_ENV,
    _sanitized_bridge_env,
    request_from_bytes,
    wake_native_canary_edge,
)
from limen.conduct.client import HttpConductClient


RUNTIME_SHA = "a" * 40


def _request() -> NativeCanaryEdgeRequest:
    return NativeCanaryEdgeRequest(
        canary_id="b" * 64,
        edge_id="c" * 64,
        run_id="run-native-edge",
        lease_id="lease-native-edge",
        generation=3,
        packet_deadline=(datetime(2026, 7, 30, tzinfo=UTC) + timedelta(minutes=15)).isoformat(),
        packet_predicate=f"/bin/test {RUNTIME_SHA} = {RUNTIME_SHA}",
        receipt_id="receipt-native-edge",
        runtime_git_sha=RUNTIME_SHA,
        executor_session_id="executor-session",
        executor_native_session_id="provider-session",
        executor_native_run_id="provider-run",
        executor_credential_ref="LIMEN_EXECUTOR_CREDENTIAL_REF",
        executor_identity={
            "schema_version": "limen.agent_identity.v1",
            "agent": "arbitrary-lane",
            "surface": "canary-executor",
            "session_id": "executor-session",
            "native_run_id": "provider-run",
            "provider_identity": None,
        },
        expected_checks=(
            {
                "name": "executor-claim",
                "status": "success",
                "url": None,
                "head": "d" * 64,
            },
        ),
    )


def _bridge(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "native-canary-bridge"
    path.write_text(f"#!/usr/bin/env python3\n{body}", encoding="utf-8")
    path.chmod(0o700)
    return path


def test_bridge_forwards_only_the_credential_reference_and_exact_edge(
    tmp_path: Path,
) -> None:
    request = _request()
    bridge = _bridge(
        tmp_path,
        """
import hashlib
import json
import os
import sys

request = json.load(sys.stdin)
if "LIMEN_EXECUTOR_SECRET" in os.environ:
    raise SystemExit(41)
if os.environ.get("LIMEN_CONDUCT_CANARY_CREDENTIAL_REF") != request["executor_credential_ref"]:
    raise SystemExit(42)
fields = (
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
)
ack = {"schema_version": "limen.conduct_canary_native_edge_ack.v1"}
ack.update({field: request[field] for field in fields})
rendered = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
ack["request_sha256"] = hashlib.sha256(rendered).hexdigest()
json.dump(ack, sys.stdout)
""",
    )
    environment = {
        **os.environ,
        WAKE_BIN_ENV: str(bridge),
        "LIMEN_EXECUTOR_SECRET": "must-not-cross-the-bridge",
    }

    acknowledgement = wake_native_canary_edge(request, environ=environment)

    assert acknowledgement == NativeCanaryEdgeAck.expected(request)
    assert acknowledgement.sha256


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("import sys\nsys.stdout.write('not-json')\n", "invalid JSON"),
        (
            "import sys\nsys.stdout.write('x' * 40000)\nsys.stdout.flush()\n",
            "output ceiling",
        ),
    ],
)
def test_bridge_rejects_invalid_or_unbounded_output(
    tmp_path: Path,
    body: str,
    message: str,
) -> None:
    bridge = _bridge(tmp_path, body)

    with pytest.raises(NativeCanaryExecutorError, match=message):
        wake_native_canary_edge(
            _request(),
            environ={**os.environ, WAKE_BIN_ENV: str(bridge)},
        )


def test_bridge_timeout_is_finite_and_fails_closed(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, "import time\ntime.sleep(2)\n")

    with pytest.raises(NativeCanaryExecutorError, match="bounded timeout"):
        wake_native_canary_edge(
            _request(),
            environ={
                **os.environ,
                WAKE_BIN_ENV: str(bridge),
                WAKE_TIMEOUT_ENV: "1",
            },
        )


def test_request_decoder_rejects_trailing_or_oversized_material() -> None:
    payload = _request().to_payload()
    rendered = json.dumps(payload).encode()

    assert request_from_bytes(rendered) == _request()
    with pytest.raises(NativeCanaryExecutorError, match="invalid JSON"):
        request_from_bytes(rendered + b"\n{}")
    with pytest.raises(NativeCanaryExecutorError, match="bounded size"):
        request_from_bytes(b"x" * (64 * 1024 + 1))


def test_callback_process_identity_must_match_the_exact_native_session() -> None:
    request = _request()
    environment = {
        "LIMEN_SESSION_ID": request.executor_session_id,
        "LIMEN_NATIVE_SESSION_ID": "another-provider-session",
        "LIMEN_NATIVE_RUN_ID": request.executor_native_run_id,
        "LIMEN_CONDUCT_CANARY_CREDENTIAL_REF": request.executor_credential_ref,
    }

    with pytest.raises(NativeCanaryExecutorError, match="process identity"):
        execute_native_canary_edge(
            request,
            client=HttpConductClient("https://limen-runtime.example", "executor-token"),
            environ=environment,
        )


def test_callback_rejects_generic_token_when_named_credential_is_absent() -> None:
    request = _request()

    with pytest.raises(
        NativeCanaryExecutorError,
        match="executor credential reference is not hydrated",
    ):
        executor_client_from_environ(
            request,
            {
                "LIMEN_CONDUCT_URL": "https://limen-runtime.example",
                "LIMEN_CONDUCT_TOKEN": "generic-token-must-not-be-used",
            },
        )


def test_callback_hydrates_only_the_exact_named_executor_credential() -> None:
    request = _request()

    client = executor_client_from_environ(
        request,
        {
            "LIMEN_CONDUCT_URL": "https://limen-runtime.example",
            "LIMEN_CONDUCT_TOKEN": "generic-token-must-not-be-used",
            request.executor_credential_ref: "exact-executor-token",
        },
    )

    assert client.endpoint == "https://limen-runtime.example"
    assert client.token == "exact-executor-token"  # allow-secret: inert fixture proves exact-reference selection


@pytest.mark.parametrize("credential_ref", ["LIMEN_CONDUCT_TOKEN", "HOME", "PATH"])
def test_request_rejects_generic_or_bridge_visible_credential_references(
    credential_ref: str,
) -> None:
    with pytest.raises(NativeCanaryExecutorError, match="reserved environment variable"):
        replace(_request(), executor_credential_ref=credential_ref)


def test_bridge_sanitizer_defensively_removes_a_named_allowlisted_value() -> None:
    sanitized = _sanitized_bridge_env(
        {
            "HOME": "must-not-cross-the-bridge",
            "PATH": "/usr/bin",
            "LIMEN_CONDUCT_TOKEN": "generic-token-must-not-cross-the-bridge",
        },
        "HOME",
    )

    assert "HOME" not in sanitized
    assert "LIMEN_CONDUCT_TOKEN" not in sanitized
    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["LIMEN_CONDUCT_CANARY_CREDENTIAL_REF"] == "HOME"


def test_callback_rejects_a_stale_installed_runtime_before_remote_effects() -> None:
    request = _request()
    environment = {
        "LIMEN_SESSION_ID": request.executor_session_id,
        "LIMEN_NATIVE_SESSION_ID": request.executor_native_session_id,
        "LIMEN_NATIVE_RUN_ID": request.executor_native_run_id,
        "LIMEN_CONDUCT_CANARY_CREDENTIAL_REF": request.executor_credential_ref,
        "LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY": json.dumps(
            {
                "schema_version": "limen.conduct_runtime_identity.v1",
                "git_sha": "e" * 40,
                "deployment_id": "stale-deployment",
            }
        ),
    }

    with pytest.raises(NativeCanaryExecutorError, match="exact runtime"):
        execute_native_canary_edge(
            request,
            client=HttpConductClient("https://limen-runtime.example", "executor-token"),
            environ=environment,
        )
