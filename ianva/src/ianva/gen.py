"""Render the single "point at ianva" entry for every agent, in its exact native format.

One endpoint, seven configs. HTTP-capable agents get a direct URL entry; the rest get a
stdio entry that spawns sparfenyuk/mcp-proxy as a pure-transport shim to the same endpoint.
`build_entries()` returns structured entries; `write_golden()` stages them as files so the
result is reviewable BEFORE anything touches a real config (installs are a separate, gated step).

Per-agent quirks confirmed by adversarial verification against each agent's real schema:
  * Codex: `url=` under [mcp_servers.NAME] (byte-identical to `codex mcp add --url`).
  * Gemini: streamable-HTTP key is `httpUrl` (the CLI's own `mcp add` writes the wrong key).
  * opencode: `{type:"remote", url, headers}` under top-level "mcp"; its native
    `{env:NAME}` expansion keeps the bearer out of generated config.
  * Copilot CLI: the installed binary REQUIRES a per-server `tools` field, else "Invalid input".
  * agy/Cline: stdio `{command,args}` validates.
When a bearer is set (cloud face), the matching Authorization header / token-env is injected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .agents import AGENTS, SERVER_NAME, AgentTarget

BEARER_ENV = "IANVA_BEARER_TOKEN"


@dataclass
class Endpoint:
    host: str = "127.0.0.1"
    port: int = 7666
    path: str = "/mcp"
    public_url: str = ""  # set once tunneled (cloud face); preferred for remote agents
    bearer: str = ""  # when set, the gateway enforces it and entries carry the header
    proxy_bin: str = "uvx"
    proxy_args: list[str] = field(default_factory=lambda: ["mcp-proxy", "--transport", "streamablehttp"])

    def url(self) -> str:
        if self.public_url:
            return self.public_url.rstrip("/")
        return f"http://{self.host}:{self.port}{self.path}"

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.bearer}"} if self.bearer else {}


@dataclass
class Entry:
    key: str
    label: str
    path: str
    fmt: str
    transport: str
    rendered: str  # the snippet to place in the file (or the command to run)
    install: str  # human/script instruction for applying it
    payload: dict | None  # structured form (for JSON merge installers)
    filename: str  # golden output filename


def _stdio_payload(ep: Endpoint) -> dict:
    args = list(ep.proxy_args)
    if ep.bearer:
        # mcp-proxy passes -H KEY VALUE through to the upstream HTTP request.
        args += ["-H", "Authorization", f"Bearer {ep.bearer}"]
    args.append(ep.url())
    return {"command": ep.proxy_bin, "args": args}


def _http_payload_mcpservers(ep: Endpoint) -> dict:
    p: dict = {"httpUrl": ep.url()}  # Gemini-family streamable-HTTP key
    if ep.bearer:
        p["headers"] = ep.headers()
    return p


def _render_codex(ep: Endpoint) -> Entry:
    body = f'[mcp_servers.{SERVER_NAME}]\nurl = "{ep.url()}"\n'
    if ep.bearer:
        body += f'bearer_token_env_var = "{BEARER_ENV}"\n'
    body += "# startup_timeout_sec = 30\n"
    return Entry(
        key="codex",
        label="Codex (OpenAI)",
        path=str(Path.home() / ".codex" / "config.toml"),
        fmt="toml_codex",
        transport="http",
        rendered=body,
        install="Append this [mcp_servers.ianva] table to ~/.codex/config.toml.",
        payload=None,
        filename="codex.config.toml.snippet",
    )


def _render_json_mcpservers(a: AgentTarget, ep: Endpoint) -> Entry:
    payload = _http_payload_mcpservers(ep) if a.transport == "http" else _stdio_payload(ep)
    if a.key == "copilot":
        # Copilot CLI v0.0.361's validator requires `tools`; `type:"local"` is the accepted
        # local-process type ("stdio" is rejected). Verified empirically.
        payload = {**payload, "type": "local", "tools": ["*"]}
    blob = {"mcpServers": {SERVER_NAME: payload}}
    return Entry(
        key=a.key,
        label=a.label,
        path=str(a.path),
        fmt=a.fmt,
        transport=a.transport,
        rendered=json.dumps(blob, indent=2),
        install=f'Merge the "{SERVER_NAME}" key under "mcpServers" in {a.path} '
        f"(create the file with this content if absent).",
        payload=blob,
        filename=f"{a.key}.mcp.json",
    )


def _render_opencode(a: AgentTarget, ep: Endpoint) -> Entry:
    server: dict[str, object] = {"type": "remote", "url": ep.url()}
    if ep.bearer:
        # OpenCode expands {env:NAME} in config values.  Reference the credential wall's
        # environment owner instead of materializing a bearer in opencode.jsonc.
        server["headers"] = {"Authorization": f"Bearer {{env:{BEARER_ENV}}}"}
    blob = {"mcp": {SERVER_NAME: server}}
    return Entry(
        key=a.key,
        label=a.label,
        path=str(a.path),
        fmt=a.fmt,
        transport="http",
        rendered=json.dumps(blob, indent=2),
        install=f'Merge the "{SERVER_NAME}" key under the top-level "mcp" object in {a.path}.',
        payload=blob,
        filename="opencode.mcp.json",
    )


def _render_claude(ep: Endpoint) -> Entry:
    cmd = f"claude mcp add --transport http --scope user {SERVER_NAME} {ep.url()}"
    if ep.bearer:
        cmd += f' --header "Authorization: Bearer {ep.bearer}"'
    return Entry(
        key="claude",
        label="Claude Code",
        path=str(Path.home() / ".claude.json"),
        fmt="claude_cli",
        transport="http",
        rendered=cmd,
        install="Run this command (writes the user-scope mcpServers entry into ~/.claude.json).",
        payload=None,
        filename="claude.add.sh",
    )


def build_entries(ep: Endpoint | None = None) -> list[Entry]:
    ep = ep or Endpoint()
    out: list[Entry] = []
    for a in AGENTS:
        if a.fmt == "toml_codex":
            out.append(_render_codex(ep))
        elif a.fmt == "json_opencode":
            out.append(_render_opencode(a, ep))
        elif a.fmt == "claude_cli":
            out.append(_render_claude(ep))
        elif a.fmt in {"json_mcpservers", "json_stdio_mcpservers"}:
            out.append(_render_json_mcpservers(a, ep))
    return out


def write_golden(entries: list[Entry], outdir: Path | None = None) -> Path:
    outdir = outdir or paths.GENERATED_DIR
    outdir.mkdir(parents=True, exist_ok=True)
    index_lines = [
        "# ianva — generated agent config entries",
        "",
        "One entry per agent, in its native format. These are STAGED for review — applying them",
        "to real config files is a separate, explicit step (`ianva install-configs` / the installer).",
        "",
        "| agent | config file | transport | apply |",
        "|---|---|---|---|",
    ]
    for e in entries:
        (outdir / e.filename).write_text(e.rendered + ("\n" if not e.rendered.endswith("\n") else ""))
        index_lines.append(f"| {e.label} | `{e.path}` | {e.transport} | {e.install} |")
    index = outdir / "INSTALL.md"
    index.write_text("\n".join(index_lines) + "\n")
    return outdir
