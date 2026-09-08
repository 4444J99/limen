"""Observe Claude Code's native control protocol without submitting a model turn.

The installed CLI owns configuration loading, plugin expansion and MCP handshakes.
Protocol source: anthropics/claude-agent-sdk-python, _internal/query.py and types.py.
Only initialize, mcp_status and get_context_usage requests are permitted. Native
startup requires the estate's quiet-launch check and machine-wide admission.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from mcp_native_observer import digest, file_digest, require_live_run
from mcp_protocol import ProtocolError, Wire


class ClaudeWire(Wire):
    def exchange(self, subtype):
        if subtype not in {"initialize", "mcp_status", "get_context_usage"}:
            raise ProtocolError("native operation outside collector contract")
        self.remaining()
        self.counter += 1
        request_id = f"estate_{self.counter}"
        request = {"subtype": subtype}
        if subtype == "initialize":
            request["hooks"] = None
        body = json.dumps({"type": "control_request", "request_id": request_id, "request": request}).encode() + b"\n"
        if len(body) > 4096 or os.write(self.process.stdin.fileno(), body) != len(body):
            raise ProtocolError("native request write failed")
        while True:
            message = json.loads(self.read_line())
            if not isinstance(message, dict):
                raise ProtocolError("invalid native envelope")
            if message.get("type") == "system":
                # No user/model transcript or unrequested control operation is consumed.
                continue
            response = message.get("response")
            if (
                message.get("type") != "control_response"
                or not isinstance(response, dict)
                or response.get("request_id") != request_id
                or response.get("subtype") != "success"
                or not isinstance(response.get("response"), dict)
            ):
                raise ProtocolError("native control request refused or unexpected message")
            if self.custody:
                self.custody.sample()
            return response["response"]


def status_index(response):
    """Preserve native names, scopes and effective launch bindings, excluding values."""
    from mcp_estate import normalize

    servers = response.get("mcpServers")
    if not isinstance(servers, list):
        raise ProtocolError("invalid native MCP status")
    result, effective, seen = [], {}, set()
    for server in servers:
        if (
            not isinstance(server, dict)
            or not isinstance(server.get("name"), str)
            or not server["name"]
            or server["name"] in seen
            or server.get("status") not in {"connected", "failed", "needs-auth", "pending", "disabled"}
            or not isinstance(server.get("serverInfo", {}), dict)
            or not isinstance(server.get("tools", []), list)
        ):
            raise ProtocolError("invalid native server identity")
        name = server["name"]
        seen.add(name)
        tools = server.get("tools", [])
        if any(not isinstance(t, dict) or not isinstance(t.get("name"), str) for t in tools):
            raise ProtocolError("invalid native tool catalog")
        spec = normalize(server.get("config"), "claude")
        # Native plugin names are namespaced. Keep them intact until an owner route
        # map proves their identity; suffix matching could certify the wrong plugin.
        effective[name] = {
            "launch_fingerprint": digest(spec),
            "disabled": server["status"] == "disabled" or spec["disabled"],
            "valid": not spec["invalid"] and spec["transport"] != "unsupported",
        }
        result.append(
            {
                "name": name,
                "plugin_id": None,
                "scope": server.get("scope"),
                "runtime_status": server["status"],
                "auth_status": "not_logged_in" if server["status"] == "needs-auth" else "unmeasured",
                "server_version": server.get("serverInfo", {}).get("version"),
                "tool_names": sorted(t["name"] for t in tools),
                "functional": {"state": "unmeasured"},
            }
        )
    return result, {"state": "observed", "registrations": effective}


def context_evidence(response):
    """Retain native token metrics, never memory paths or rendered private content.

    Context telemetry proves the native rendering account, not completeness of
    every skill description. Missing per-skill omission data stays unmeasured.
    """
    for key in ("totalTokens", "maxTokens", "rawMaxTokens"):
        if type(response.get(key)) is not int or response[key] < 0:
            raise ProtocolError("invalid native context metric")
    if response["maxTokens"] <= 0 or not isinstance(response.get("categories"), list):
        raise ProtocolError("invalid native context account")
    categories = []
    for category in response["categories"]:
        if (
            not isinstance(category, dict)
            or not isinstance(category.get("name"), str)
            or type(category.get("tokens")) is not int
            or category["tokens"] < 0
        ):
            raise ProtocolError("invalid native context category")
        categories.append({"name_fingerprint": digest(category["name"]), "tokens": category["tokens"]})
    metrics = {}
    skills = response.get("skills")
    if skills is not None and not isinstance(skills, dict):
        raise ProtocolError("invalid native skill usage")
    # Only public schema-shaped numeric keys escape; nested names/paths/content
    # remain private. Unknown fields do not establish absence or zero omissions.
    for key, value in (skills or {}).items():
        if (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", key)
            and type(value) in (int, float)
            and math.isfinite(value)
            and value >= 0
        ):
            metrics[key] = value
    return {
        "native_context_observed": True,
        "runtime_budget": response["maxTokens"],
        "total_tokens": response["totalTokens"],
        "raw_max_tokens": response["rawMaxTokens"],
        "categories": categories,
        "skill_usage_observed": isinstance(skills, dict),
        "skill_numeric_metrics": metrics,
        "skill_usage_fingerprint": digest(skills) if skills is not None else None,
        "stripped_descriptions": None,
        "fresh_native_loading_witness": False,
    }


def collect_claude(broker, run_id, project, timeout=45, include_mcp=False):
    started = time.time()
    binding = require_live_run(broker, run_id, started)
    if not include_mcp:
        # Unlike Codex config/read, Claude initialize can start all configured
        # servers. A catalog-only request cannot bypass the quiet-launch gate.
        raise ProtocolError("native Claude initialization requires quiet startup admission")
    if not 0 < timeout <= 120:
        raise ValueError("native collector deadline outside bounds")
    executable = shutil.which("claude")
    if not executable:
        raise ProtocolError("native Claude unavailable")
    binary = file_digest(executable)
    version = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, timeout=5, check=True
    ).stdout.strip()
    if not re.fullmatch(r"2\.\d+\.\d+ \(Claude Code\)", version):
        raise ProtocolError("native Claude adapter requires a verified version contract")
    session = str(uuid.uuid4())
    wire = ClaudeWire(
        {
            "transport": "stdio",
            "command": executable,
            "args": [
                "--print",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--verbose",
                "--permission-mode",
                "dontAsk",
                "--no-session-persistence",
                "--session-id",
                session,
            ],
            "cwd": str(Path(project).resolve()),
        },
        timeout,
        "native",
    )
    from limen.host_admission import hold_lease

    with hold_lease("heavy", owner=f"mcp-native-{os.getpid()}", surface="mcp-estate-native"):
        try:
            wire.start()
            initialized = wire.exchange("initialize")
            before = wire.exchange("mcp_status")
            servers, effective = status_index(before)
            context = context_evidence(wire.exchange("get_context_usage"))
            after_servers, after_effective = status_index(wire.exchange("mcp_status"))
            if (
                effective != after_effective
                or [(s["name"], s["server_version"]) for s in servers]
                != [(s["name"], s["server_version"]) for s in after_servers]
                or file_digest(executable) != binary
            ):
                raise ProtocolError("native dependencies changed during collection")
        finally:
            wire.close()
    return {
        "schema_version": "limen.native_observation.v1",
        "client": "claude",
        **binding,
        "native_session_id": session,
        "native_session_kind": "native-control-session",
        "native_process_id": wire.process.pid,
        "client_version": version,
        "binary_fingerprint": binary,
        "configuration_fingerprint": digest(effective),
        "effective_configuration": effective,
        "native_version_fingerprint": digest([version, binary]),
        "native_api_fingerprint": digest(sorted(initialized)),
        "started_at": started,
        "observed_at": time.time(),
        "latency_ms": int((time.time() - started) * 1000),
        "cleanup": wire.cleanup,
        "processes": wire.custody.report(),
        "skills": context,
        "servers": servers,
    }
