"""The agents that point AT ianva, and the exact shape each one needs.

This is the registry that turns "all agent config files (not just claude)" into code. Every
fact here was ground-truthed on this machine (config path, file format, MCP-declaration key,
which transports the agent accepts). Per-agent we choose the most robust single entry:

  * Agents with first-class remote/HTTP MCP support → a DIRECT http entry to ianva's endpoint
    (no extra process; ianva/MCPHub holds all the upstream creds behind it).
  * Agents whose HTTP support is unconfirmed → a stdio entry that spawns sparfenyuk/mcp-proxy
    as a thin stdio↔HTTP shim to the same endpoint. mcp-proxy carries no credentials; it is
    pure transport, so this is safe and uniform.

`fmt` selects the renderer in gen.py. `path` is user-scope (one write per agent, not per repo).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HOME = Path.home()


@dataclass(frozen=True)
class AgentTarget:
    key: str
    label: str
    path: Path
    fmt: str                 # "toml_codex" | "json_mcpservers" | "json_opencode" | "claude_cli"
    transport: str           # how ianva is wired into THIS agent: "http" | "stdio"
    creates_file: bool       # True if the config file may be absent and we create it
    note: str = ""


# server name ianva registers under, inside each agent's config
SERVER_NAME = "ianva"

AGENTS: list[AgentTarget] = [
    AgentTarget(
        key="claude", label="Claude Code",
        path=HOME / ".claude.json", fmt="claude_cli", transport="http", creates_file=False,
        note="Installed via `claude mcp add --transport http`; first-class streamable-HTTP support.",
    ),
    AgentTarget(
        key="codex", label="Codex (OpenAI)",
        path=HOME / ".codex" / "config.toml", fmt="toml_codex", transport="http", creates_file=False,
        note="TOML [mcp_servers.NAME]; supports url= + bearer_token_env_var for HTTP servers.",
    ),
    AgentTarget(
        key="gemini", label="Gemini CLI",
        path=HOME / ".gemini" / "settings.json", fmt="json_mcpservers", transport="http", creates_file=True,
        note="settings.json mcpServers; httpUrl key for streamable HTTP. User-scope file created if absent.",
    ),
    AgentTarget(
        key="opencode", label="opencode",
        path=HOME / ".config" / "opencode" / "opencode.jsonc", fmt="json_opencode", transport="http", creates_file=False,
        note="Unique shape: top-level \"mcp\" with {type:\"remote\", url}.",
    ),
    AgentTarget(
        key="agy", label="antigravity (agy)",
        path=HOME / ".gemini" / "config" / "mcp_config.json", fmt="json_mcpservers", transport="stdio", creates_file=True,
        note="agy has no `mcp` subcommand → file edit only. stdio via mcp-proxy avoids guessing its HTTP key.",
    ),
    AgentTarget(
        key="copilot", label="GitHub Copilot CLI",
        path=HOME / ".copilot" / "mcp-config.json", fmt="json_mcpservers", transport="stdio", creates_file=True,
        note="Standard mcpServers JSON; HTTP support unconfirmed → stdio via mcp-proxy.",
    ),
    AgentTarget(
        key="cline", label="Cline",
        path=HOME / ".cline" / "data" / "settings" / "cline_mcp_settings.json",
        fmt="json_mcpservers", transport="stdio", creates_file=True,
        note="Standard mcpServers JSON; stdio via mcp-proxy for maximum compatibility.",
    ),
]


def by_key(key: str) -> AgentTarget | None:
    return next((a for a in AGENTS if a.key == key), None)
