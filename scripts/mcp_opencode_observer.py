"""Observe the installed OpenCode native HTTP runtime in a fresh owned session.

Contract: https://opencode.ai/docs/server/ (installed 1.18.20 inspected).
The live OpenAPI document and health version are checked before session creation.
No model message, command, permission response, login or config mutation is sent.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from mcp_native_observer import digest, file_digest, require_live_run
from mcp_protocol import LIMIT, NoRedirect, ProtocolError
from mcp_process_custody import Custody


class NativeHTTP:
    def __init__(self, executable, project, timeout):
        self.deadline = time.monotonic() + timeout
        self.project = str(Path(project).resolve())
        self.password = secrets.token_urlsafe(32)  # allow-secret: ephemeral owned loopback capability; never persisted
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.origin = f"http://127.0.0.1:{port}"
        self.argv = [executable, "serve", "--hostname", "127.0.0.1", "--port", str(port)]
        self.process = self.custody = None
        self.session_id = None
        self.cleanup = "unmeasured"
        self.session_cleanup = "not_applicable"
        self.bytes_read = 0

    def start(self):
        self.process = subprocess.Popen(
            self.argv,
            cwd=self.project,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "OPENCODE_SERVER_PASSWORD": self.password, "OPENCODE_SERVER_USERNAME": "limen-estate"},
        )
        self.custody = Custody(self.process)
        self.custody.sample()

    def request(self, path, method="GET", body=None, cleanup=False):
        read_paths = {"/global/health", "/doc", "/config", "/path", "/mcp", "/experimental/tool/ids"}
        session_path = "/session/" + urllib.parse.quote(self.session_id, safe="") if self.session_id else None
        if not (
            (method == "GET" and path in read_paths)
            or (method == "POST" and path == "/session")
            or (method == "DELETE" and path == session_path)
        ):
            raise ProtocolError("native operation outside collector contract")
        remaining = 2 if cleanup else self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("native observation deadline")
        credentials = base64.b64encode(("limen-estate:" + self.password).encode()).decode()
        request = urllib.request.Request(
            self.origin + path + "?" + urllib.parse.urlencode({"directory": self.project}),
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Basic " + credentials, "Content-Type": "application/json"},
            method=method,
        )
        read_deadline = time.monotonic() + remaining
        chunks = []
        with urllib.request.build_opener(NoRedirect).open(request, timeout=min(2, remaining)) as response:
            while time.monotonic() < read_deadline:
                chunk = response.read1(65536)
                self.bytes_read += len(chunk)
                if self.bytes_read > LIMIT:
                    raise ProtocolError("native output ceiling")
                if not chunk:
                    break
                chunks.append(chunk)
            else:
                raise TimeoutError("native response deadline")
        raw = b"".join(chunks)
        value = json.loads(raw)
        self.custody.sample()
        return value

    def ready(self):
        while self.process.poll() is None and time.monotonic() < self.deadline:
            try:
                return self.request("/global/health")
            except urllib.error.HTTPError:
                raise ProtocolError("native authentication or health route refused") from None
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.05)
        raise ProtocolError("owned native runtime did not become ready")

    def close(self):
        try:
            if self.session_id:
                self.session_cleanup = (
                    "pass"
                    if self.request("/session/" + urllib.parse.quote(self.session_id, safe=""), "DELETE", cleanup=True)
                    is True
                    else "fail"
                )
        except (OSError, ValueError, ProtocolError):
            self.session_cleanup = "fail"
        finally:
            if self.custody:
                self.cleanup = self.custody.close()


def collect_opencode(broker, run_id, project, timeout=45, include_mcp=False):
    from mcp_estate import native_configuration_index

    started = time.time()
    binding = require_live_run(broker, run_id, started)
    if not 0 < timeout <= 120:
        raise ValueError("native collector deadline outside bounds")
    executable = shutil.which("opencode")
    if not executable:
        raise ProtocolError("native OpenCode unavailable")
    binary = file_digest(executable)
    version = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, timeout=5, check=True
    ).stdout.strip()
    if not re.fullmatch(r"1\.\d+\.\d+(?:[-+][\w.-]+)?", version):
        raise ProtocolError("native OpenCode adapter requires a verified version contract")
    from limen.host_admission import hold_lease

    native = NativeHTTP(executable, project, timeout)
    with hold_lease("heavy", owner=f"mcp-native-{os.getpid()}", surface="mcp-estate-native"):
        try:
            native.start()
            health = native.ready()
            if not isinstance(health, dict) or health.get("healthy") is not True or health.get("version") != version:
                raise ProtocolError("native OpenCode runtime version mismatch")
            schema = native.request("/doc")
            paths = schema.get("paths", {}) if isinstance(schema, dict) else {}
            required = {
                "/config": "get",
                "/path": "get",
                "/mcp": "get",
                "/session": "post",
                "/session/{sessionID}": "delete",
            }
            if any(method not in paths.get(path, {}) for path, method in required.items()):
                raise ProtocolError("native OpenCode API contract changed")
            config = native.request("/config")
            scope = native.request("/path")
            if (
                not isinstance(config, dict)
                or not isinstance(scope, dict)
                or Path(scope.get("directory", "")).resolve() != Path(project).resolve()
            ):
                raise ProtocolError("native project scope mismatch")
            session = native.request("/session", "POST", {"title": "MCP estate observation"})
            if (
                not isinstance(session, dict)
                or not isinstance(session.get("id"), str)
                or not re.fullmatch(r"ses_[A-Za-z0-9_-]+", session["id"])
            ):
                raise ProtocolError("invalid native session identity")
            native.session_id = session["id"]
            statuses = native.request("/mcp") if include_mcp else {}
            if not isinstance(statuses, dict) or any(
                not isinstance(v, dict) or not isinstance(v.get("status"), str) for v in statuses.values()
            ):
                raise ProtocolError("invalid native MCP status")
            if native.request("/config") != config or file_digest(executable) != binary:
                raise ProtocolError("native dependencies changed during collection")
        finally:
            native.close()
    return {
        "schema_version": "limen.native_observation.v1",
        "client": "opencode",
        **binding,
        "native_session_id": native.session_id,
        "native_session_kind": "native-http-session",
        "native_process_id": native.process.pid,
        "client_version": version,
        "binary_fingerprint": binary,
        "configuration_fingerprint": digest(config),
        "effective_configuration": native_configuration_index("opencode", config),
        "native_version_fingerprint": digest(health),
        "native_api_fingerprint": digest(schema),
        "scope_fingerprint": digest(scope),
        "started_at": started,
        "observed_at": time.time(),
        "latency_ms": int((time.time() - started) * 1000),
        "cleanup": native.cleanup,
        "session_cleanup": native.session_cleanup,
        "processes": native.custody.report(),
        "servers": [
            {"name": name, "plugin_id": None, "runtime_status": value["status"], "server_version": None}
            for name, value in statuses.items()
        ],
    }
