"""Bounded MCP exchanges. No login, UI, arbitrary smoke calls or shared-process cleanup.

The caller declares the protocol; negotiation never silently upgrades to stateless.
Only probe-created process groups are terminated. Wire payloads never enter receipts.
"""

from __future__ import annotations

import json
import os
import selectors
import signal

from mcp_process_custody import Custody
import subprocess
import time
import threading
import urllib.error
import urllib.request

VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"}
LIMIT = 2 * 1024 * 1024


class ProtocolError(Exception):
    pass


class RpcResponseError(ProtocolError):
    """A valid JSON-RPC error response, without retaining server-controlled detail."""

    _CLASSES = {
        -32700: "parse_error",
        -32600: "invalid_request",
        -32601: "method_not_found",
        -32602: "invalid_params",
        -32603: "internal_error",
    }

    def __init__(self, error: object):
        code = error.get("code") if isinstance(error, dict) else None
        self.code = code if type(code) is int else None
        self.error_class = self._CLASSES.get(self.code, "other_rpc_error")
        super().__init__("server RPC error")


class AuthenticationRequired(ProtocolError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProtocolError("redirect refused; authentication remains owner-managed")


class Wire:
    def __init__(self, server, timeout, version):
        self.server, self.version = server, version
        self.deadline = time.monotonic() + timeout
        self.process = None
        self.buffer = b""
        self.session = None
        self.counter = 0
        self.bytes_read = 0
        self.cleanup = "not_applicable"
        self.custody = None
        self.transport = "unmeasured"

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("protocol deadline")
        return remaining

    def start(self):
        if self.server["transport"] == "stdio":
            command = self.server.get("command")
            argv = command if isinstance(command, list) else [command, *self.server.get("args", [])]
            if not argv or not isinstance(argv[0], str):
                raise ProtocolError("missing executable")
            self.process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=self.server.get("cwd"),
                env={**os.environ, **self.server.get("env", {})},
                start_new_session=True,
            )
            os.set_blocking(self.process.stdout.fileno(), False)
            os.set_blocking(self.process.stdin.fileno(), False)
            self.transport = "pass"
            self.cleanup = "unmeasured"
            self.custody = Custody(self.process)
            self.custody.sample()
        elif self.server["transport"] != "http":
            raise ProtocolError("unsupported transport")

    def read_line(self):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b"\n" not in self.buffer:
                if not selector.select(self.remaining()):
                    if self.process is not None and self.process.poll() is not None:
                        raise ProtocolError("EOF without response")
                    raise TimeoutError("protocol deadline")
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise ProtocolError("EOF without response")
                self.bytes_read += len(chunk)
                if self.bytes_read > LIMIT:
                    raise ProtocolError("output ceiling")
                self.buffer += chunk
            line, self.buffer = self.buffer.split(b"\n", 1)
            return line

    def exchange(self, method, params=None, notification=False):
        self.remaining()
        self.counter += 1
        params = dict(params or {})
        if self.version == "2026-07-28":
            params["_meta"] = {
                "io.modelcontextprotocol/protocolVersion": self.version,
                "io.modelcontextprotocol/clientInfo": {"name": "limen-estate", "version": "1"},
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        request = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            request["id"] = self.counter
        body = json.dumps(request).encode() + b"\n"
        if self.process:
            # Probe requests are deliberately below PIPE_BUF; never block on a silent reader.
            if len(body) > 4096:
                raise ProtocolError("request write failed")
            try:
                written = os.write(self.process.stdin.fileno(), body)
            except BrokenPipeError as exc:
                raise ProtocolError("request write failed") from exc
            if written != len(body):
                raise ProtocolError("request write failed")
            if notification:
                return {}
            while True:
                try:
                    response = json.loads(self.read_line())
                except (ValueError, UnicodeError) as exc:
                    raise ProtocolError("invalid JSON on protocol stdout") from exc
                if not isinstance(response, dict):
                    raise ProtocolError("invalid RPC envelope")
                if response.get("id") == request["id"]:
                    break
                # Notifications may interleave; do not grant sampling/elicitation permissions.
                if "id" in response:
                    raise ProtocolError("unexpected RPC response or server request")
        else:
            headers = {
                **self.server.get("headers", {}),
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": self.version,
                "Mcp-Method": method,
            }
            for name, reference in self.server.get("env_http_headers", {}).items():
                value = os.environ.get(reference)
                if not value:
                    raise AuthenticationRequired("missing credential reference")
                headers[name] = value
            if "name" in params:
                headers["Mcp-Name"] = params["name"]
            if self.session:
                headers["Mcp-Session-Id"] = self.session
            env_ref = self.server.get("bearer_token_env_var")
            if env_ref:
                token = os.environ.get(env_ref)  # allow-secret: owner-declared env reference; never emitted
                if not token:
                    raise AuthenticationRequired("missing credential reference")
                headers["Authorization"] = "Bearer " + token
            try:
                req = urllib.request.Request(self.server["url"], data=body, headers=headers)
                with urllib.request.build_opener(NoRedirect).open(req, timeout=self.remaining()) as stream:
                    self.transport = "pass"
                    self.session = stream.headers.get("Mcp-Session-Id", self.session)
                    if notification:
                        return {}
                    if "text/event-stream" in stream.headers.get("Content-Type", ""):
                        raw = b""
                        while True:
                            self.remaining()
                            line = stream.readline(LIMIT + 1)
                            self.bytes_read += len(line)
                            if self.bytes_read > LIMIT:
                                raise ProtocolError("output ceiling")
                            if not line:
                                raise ProtocolError("SSE EOF without response")
                            if line.startswith(b"data:"):
                                raw += line[5:].strip()
                            elif not line.strip() and raw:
                                break
                    else:
                        raw = stream.read(LIMIT + 1)
                        self.bytes_read += len(raw)
                        if self.bytes_read > LIMIT:
                            raise ProtocolError("output ceiling")
                    if len(raw) > LIMIT:
                        raise ProtocolError("output ceiling")
                    response = json.loads(raw)
            except urllib.error.HTTPError as exc:
                self.transport = "pass"
                if exc.code in (401, 403):
                    raise AuthenticationRequired("server requires authentication") from None
                raise ProtocolError(f"HTTP {exc.code}") from None
        if (
            not isinstance(response, dict)
            or response.get("jsonrpc") != "2.0"
            or response.get("id") != request["id"]
        ):
            raise ProtocolError("invalid RPC envelope")
        if "error" in response:
            raise RpcResponseError(response["error"])
        if not isinstance(response.get("result"), dict):
            raise ProtocolError("invalid RPC result")
        if self.custody:
            self.custody.sample()
        return response["result"]

    def close(self):
        if not self.process:
            return
        try:
            self.cleanup = self.custody.close() if self.custody else "unmeasured"
        finally:
            for stream in (self.process.stdin, self.process.stdout):
                stream.close()


def verify(server, timeout=15, expected=None, version="2025-11-25", safe_calls=None):
    """A wall deadline also bounds HTTP peers trickling bytes without finishing a line."""
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL)[0]:
        return {
            "dimensions": dict.fromkeys(
                ("transport", "protocol", "authentication", "capabilities", "cleanup"), "unmeasured"
            ),
            "reason": "deadline_admission_unavailable",
        }

    def expired(signum, frame):
        raise TimeoutError("protocol hard deadline")

    previous = signal.signal(signal.SIGALRM, expired)
    # Normal reads honor the exact deadline. A one-second outer guard catches trickling
    # HTTP peers while leaving cleanup a distinct, bounded two-second allowance.
    signal.setitimer(signal.ITIMER_REAL, timeout + 1)
    try:
        return _verify(server, timeout, expected, version, safe_calls)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _verify(server, timeout=15, expected=None, version="2025-11-25", safe_calls=None):
    dimensions = dict.fromkeys(
        ("transport", "protocol", "authentication", "capabilities", "functional", "cleanup"), "unmeasured"
    )
    report = {
        "dimensions": dimensions,
        "server_version": None,
        "protocol_version": version,
        "capability_names": {},
        "rpc_error_code": None,
        "rpc_error_class": None,
        "reason": None,
    }
    if version not in VERSIONS:
        report["reason"] = "unsupported_protocol"
        return report
    wire = Wire(server, timeout, version)
    started = time.monotonic()
    try:
        wire.start()
        if version == "2026-07-28":
            info = wire.exchange("server/discover")
        else:
            info = wire.exchange(
                "initialize",
                {
                    "protocolVersion": version,
                    "capabilities": {},
                    "clientInfo": {"name": "limen-estate", "version": "1"},
                },
            )
            if info.get("protocolVersion") != version:
                report["reason"] = "unsupported_protocol"
                return report
            wire.exchange("notifications/initialized", notification=True)
        if not isinstance(info.get("capabilities"), dict) or not isinstance(info.get("serverInfo"), dict):
            raise ProtocolError("invalid discovery result")
        dimensions["protocol"] = dimensions["authentication"] = "pass"
        report["server_version"] = info["serverInfo"].get("version")
        missing = []
        for kind in ("tools", "resources", "prompts"):
            if kind not in info["capabilities"]:
                missing.extend((expected or {}).get(kind, []))
                continue
            names, cursors, params = set(), set(), {}
            while True:
                result = wire.exchange(f"{kind}/list", params)
                rows = result.get(kind)
                key = "uri" if kind == "resources" else "name"
                if not isinstance(rows, list) or any(
                    not isinstance(r, dict) or not isinstance(r.get(key), str) for r in rows
                ):
                    raise ProtocolError("invalid capability list")
                names.update(r[key] for r in rows)
                cursor = result.get("nextCursor")
                if cursor is None:
                    break
                if not isinstance(cursor, str) or not cursor or cursor in cursors or len(cursors) >= 100:
                    raise ProtocolError("invalid pagination")
                cursors.add(cursor)
                params = {"cursor": cursor}
            report["capability_names"][kind] = sorted(names)
            missing.extend(set((expected or {}).get(kind, [])) - names)
        report["missing_capabilities"] = len(missing)
        dimensions["capabilities"] = "fail" if missing else ("pass" if expected else "unmeasured")
        if safe_calls is not None:
            if not isinstance(safe_calls, list) or len(safe_calls) > 10:
                raise ProtocolError("invalid safe-call contract")
            # Validate the entire owner-declared batch before making any functional call.
            for call in safe_calls:
                if (
                    not isinstance(call, dict)
                    or call.get("read_only") is not True
                    or call.get("method") not in ("tools/call", "resources/read", "prompts/get")
                    or not isinstance(call.get("params"), dict)
                ):
                    raise ProtocolError("functional call lacks read-only owner contract")
            dimensions["functional"] = "not_applicable" if not safe_calls else "pass"
            report["functional_calls"] = {"attempted": 0, "passed": 0}
            for call in safe_calls:
                report["functional_calls"]["attempted"] += 1
                result = wire.exchange(call["method"], call["params"])
                if result.get("isError") is True:
                    dimensions["functional"] = "fail"
                    break
                expected_field = {"tools/call": "content", "resources/read": "contents", "prompts/get": "messages"}[
                    call["method"]
                ]
                if not isinstance(result.get(expected_field), list):
                    dimensions["functional"] = "fail"
                    raise ProtocolError("invalid functional result")
                report["functional_calls"]["passed"] += 1
    except AuthenticationRequired:
        dimensions["authentication"] = "required"
        report["reason"] = "authentication_required"
    except RpcResponseError as exc:
        dimensions["protocol"] = "fail"
        report["reason"] = "server_rpc_error"
        report["rpc_error_code"] = exc.code
        report["rpc_error_class"] = exc.error_class
    except (OSError, ValueError, ProtocolError, TimeoutError) as exc:
        dimensions["protocol"] = "fail"
        report["reason"] = type(exc).__name__
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        wire.close()
        dimensions["transport"] = wire.transport
        dimensions["cleanup"] = wire.cleanup
        report["processes"] = wire.custody.report() if wire.custody else {"measurement": "not_applicable"}
        report["latency_ms"] = round((time.monotonic() - started) * 1000)
    return report
