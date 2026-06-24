"""The set of MCP servers ianva fronts (the upstreams), normalized from two sources.

Source 1: build-mcp-registry.py's inventory (~/.agents/mcp/servers.json) — the fleet's
existing, unconsumed snapshot of every MCP server across every tool. ianva is finally its
consumer. Source 2: ianva's own ~/.config/ianva/upstreams.json for additions/overrides.

We parse defensively because the registry shape is not strictly versioned: it may be a list,
a {"servers": [...]} envelope, or a {name: def} map, and individual keys vary by tool
(command/args/env, url/serverUrl/httpUrl, type/transport, disabled/enabled).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import paths


@dataclass
class Upstream:
    name: str
    transport: str = "stdio"          # "stdio" | "http" | "sse"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    oauth: bool = False               # upstream requires OAuth → MCPHub holds + refreshes it
    enabled: bool = True
    group: str = "default"

    def is_remote(self) -> bool:
        return self.transport in ("http", "sse") or bool(self.url)


def _coerce(name: str, raw: dict) -> Upstream:
    url = raw.get("url") or raw.get("serverUrl") or raw.get("httpUrl") or raw.get("baseUrl")
    transport = (raw.get("transport") or raw.get("type") or "").lower()
    if transport in ("streamablehttp", "streamable-http", "http", "remote") and url:
        transport = "http"
    elif transport == "sse" or (url and "sse" in str(url)):
        transport = "sse"
    elif url:
        transport = "http"
    else:
        transport = "stdio"

    command = raw.get("command")
    args = raw.get("args") or []
    # opencode-style combined command array: ["bin", "arg1", ...]
    if isinstance(command, list):
        args = list(command[1:]) + list(args)
        command = command[0] if command else None

    enabled = raw.get("enabled", not raw.get("disabled", False))
    oauth = bool(raw.get("oauth") or raw.get("requiresOAuth") or raw.get("authProviderType"))

    return Upstream(
        name=name,
        transport=transport,
        command=command,
        args=list(args),
        env=dict(raw.get("env") or raw.get("environment") or {}),
        url=url,
        headers=dict(raw.get("headers") or {}),
        oauth=oauth,
        enabled=bool(enabled),
        group=str(raw.get("group") or "default"),
    )


def _iter_raw(blob) -> dict[str, dict]:
    """Yield name->def from any of the accepted container shapes."""
    if blob is None:
        return {}
    if isinstance(blob, dict):
        for key in ("servers", "mcpServers", "mcp"):
            if key in blob and isinstance(blob[key], (dict, list)):
                blob = blob[key]
                break
    out: dict[str, dict] = {}
    if isinstance(blob, list):
        for item in blob:
            if isinstance(item, dict) and item.get("name"):
                out[str(item["name"])] = item
    elif isinstance(blob, dict):
        for name, defn in blob.items():
            if isinstance(defn, dict):
                out[str(name)] = defn
    return out


def _read(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return _iter_raw(json.loads(path.read_text() or "null"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_upstreams(registry: Path | None = None, extra: Path | None = None,
                   include_disabled: bool = False) -> list[Upstream]:
    """Merge registry + extra (extra overrides by name), normalize, return enabled upstreams."""
    merged: dict[str, dict] = {}
    merged.update(_read(registry or paths.DEFAULT_REGISTRY))
    merged.update(_read(extra or paths.UPSTREAMS_JSON))
    ups = [_coerce(n, d) for n, d in sorted(merged.items())]
    return ups if include_disabled else [u for u in ups if u.enabled]
