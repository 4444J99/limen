"""Collector-owned native observations; receipt files are never an authority input.

The Codex adapter uses the installed app-server protocol, not a direct MCP probe.
Other adapters remain explicitly unavailable until their native producer exists.
No model turn, login, config write, or server refresh is requested.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from mcp_protocol import ProtocolError, Wire


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class NativeWire(Wire):
    def exchange(self, method, params=None, notification=False):
        self.remaining()
        self.counter += 1
        request = {"method": method, "params": params or {}}
        if not notification:
            request["id"] = self.counter
        body = json.dumps(request).encode() + b"\n"
        if len(body) > 4096 or os.write(self.process.stdin.fileno(), body) != len(body):
            raise ProtocolError("native request write failed")
        if notification:
            return {}
        while True:
            message = json.loads(self.read_line())
            if not isinstance(message, dict):
                raise ProtocolError("invalid native envelope")
            if "id" not in message:
                continue
            if message.get("id") != self.counter or "error" in message or "method" in message:
                raise ProtocolError("native request refused or unexpected client request")
            result = message.get("result")
            if not isinstance(result, dict):
                raise ProtocolError("invalid native result")
            if self.custody:
                self.custody.sample()
            return result


def require_live_run(broker, run_id, now):
    graph = broker.graph(run_id)
    node = next((n for n in graph.get("nodes", []) if n.get("run_id") == run_id), {})
    lease = node.get("lease") or {}
    from datetime import datetime

    try:
        expires = datetime.fromisoformat(lease["hard_deadline"].replace("Z", "+00:00")).timestamp()
        heartbeat = datetime.fromisoformat(lease["heartbeat_at"].replace("Z", "+00:00")).timestamp()
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError("native collector requires a live broker lease") from exc
    authority = node.get("packet", {}).get("authority", {})
    if (
        lease.get("state") != "active"
        or expires <= now
        or not 0 <= now - heartbeat <= 300
        or lease.get("executor", {}).get("agent") != "codex"
        or not node.get("executor_session_id")
        or not {"read", "write"}.intersection(authority.get("actions", []))
    ):
        raise ProtocolError("native collector requires an admitted execution run")
    return {"run_id": run_id, "lease_id": lease["lease_id"], "generation": lease["generation"]}


def native_skills(response):
    entries, errors = [], 0
    groups = response.get("data")
    if not isinstance(groups, list):
        raise ProtocolError("invalid native skill catalog")
    for group in groups:
        if (
            not isinstance(group, dict)
            or not isinstance(group.get("skills"), list)
            or not isinstance(group.get("errors"), list)
        ):
            raise ProtocolError("invalid native skill group")
        errors += len(group["errors"])
        for skill in group["skills"]:
            if (
                not isinstance(skill, dict)
                or not all(isinstance(skill.get(k), str) for k in ("name", "path", "description", "scope"))
                or type(skill.get("enabled")) is not bool
            ):
                raise ProtocolError("invalid native skill metadata")
            entries.append(
                {
                    "name": skill["name"],
                    "path_fingerprint": hashlib.sha256(skill["path"].encode()).hexdigest(),
                    "name_chars": len(skill["name"]),
                    "path_chars": len(skill["path"]),
                    "description_chars": len(skill["description"]),
                    "description_fingerprint": hashlib.sha256(skill["description"].encode()).hexdigest(),
                    "scope": skill["scope"],
                    "enabled": skill["enabled"],
                }
            )
    return {
        "entries": entries,
        "native_skills": len(entries),
        "parse_failures": errors,
        "missing_descriptions": sum(e["description_chars"] == 0 for e in entries),
        "runtime_budget": None,
        "stripped_descriptions": None,
        "fresh_native_loading_witness": False,
        "native_catalog_observed": True,
    }


def collect_codex(broker, run_id, project, timeout=45, include_mcp=False):
    """Produce observations directly from a new native process under host admission.

    Skills listing proves the native catalog, not the model's rendered context budget.
    MCP status can initialize configured servers; callers must prove quiet configuration
    before requesting it. The default only reads configuration and skill metadata.
    """
    started = time.time()
    binding = require_live_run(broker, run_id, started)
    if not 0 < timeout <= 120:
        raise ValueError("native collector deadline outside bounds")
    executable = shutil.which("codex")
    if not executable:
        raise ProtocolError("native Codex unavailable")
    binary_before = file_digest(executable)
    version = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, timeout=5, check=True
    ).stdout.strip()
    from limen.host_admission import hold_lease

    wire = NativeWire(
        {
            "transport": "stdio",
            "command": executable,
            "args": ["app-server", "--stdio"],
            "cwd": str(Path(project).resolve()),
        },
        timeout,
        "native",
    )
    with hold_lease("heavy", owner=f"mcp-native-{os.getpid()}", surface="mcp-estate-native"):
        try:
            wire.start()
            initialized = wire.exchange("initialize", {"clientInfo": {"name": "limen-estate", "version": "1"}})
            if (
                not version
                or not isinstance(initialized.get("userAgent"), str)
                or version.split()[-1] not in initialized["userAgent"]
            ):
                raise ProtocolError("native client version identity mismatch")
            wire.exchange("initialized", notification=True)
            config_before = wire.exchange("config/read", {"includeLayers": True})
            catalog = native_skills(
                wire.exchange("skills/list", {"cwds": [str(Path(project).resolve())], "forceReload": True})
            )
            servers, cursor, seen = [], None, set()
            if include_mcp:
                for _ in range(100):
                    params = {"limit": 100}
                    if cursor is not None:
                        params["cursor"] = cursor
                    page = wire.exchange("mcpServerStatus/list", params)
                    if not isinstance(page.get("data"), list):
                        raise ProtocolError("invalid native server page")
                    servers.extend(page["data"])
                    cursor = page.get("nextCursor")
                    if cursor is None:
                        break
                    if not isinstance(cursor, str) or not cursor or cursor in seen:
                        raise ProtocolError("invalid native pagination")
                    seen.add(cursor)
                else:
                    raise ProtocolError("native pagination ceiling")
            config_after = wire.exchange("config/read", {"includeLayers": True})
            if config_before != config_after or binary_before != file_digest(executable):
                raise ProtocolError("native dependencies changed during collection")
        finally:
            wire.close()
    # Only sanitized metadata leaves the collector; no command env, URL, tool
    # arguments, resource URI, config values or raw native notifications escape.
    clean_servers = []
    for server in servers:
        if (
            not isinstance(server, dict)
            or not isinstance(server.get("name"), str)
            or not isinstance(server.get("serverInfo") or {}, dict)
        ):
            raise ProtocolError("invalid native server identity")
        info = server.get("serverInfo") or {}
        tools = server.get("tools", {})
        if not isinstance(tools, dict):
            raise ProtocolError("invalid native tool catalog")
        clean_servers.append(
            {
                "name": server["name"],
                "plugin_id": server.get("pluginId"),
                "server_version": info.get("version"),
                "auth_status": server.get("authStatus"),
                "runtime_status": server.get("runtimeStatus"),
                "tool_names": sorted(tools),
            }
        )
    return {
        "schema_version": "limen.native_observation.v1",
        "client": "codex",
        **binding,
        "native_session_id": str(uuid.uuid4()),
        "client_version": version,
        "native_session_kind": "app-server-connection",
        "native_process_id": wire.process.pid,
        "native_version_fingerprint": digest(initialized.get("userAgent")),
        "binary_fingerprint": binary_before,
        "configuration_fingerprint": digest(config_before),
        "started_at": started,
        "observed_at": time.time(),
        "latency_ms": int((time.time() - started) * 1000),
        "cleanup": wire.cleanup,
        "processes": wire.custody.report() if getattr(wire, "custody", None) else {"measurement": "unmeasured"},
        "skills": catalog,
        "servers": clean_servers,
    }
