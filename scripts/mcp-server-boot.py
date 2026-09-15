#!/usr/bin/env python3
"""MCP estate command boundary and legacy configuration parsing helpers.

The default command delegates to the desired/observed estate reducer. Empty, malformed,
unsupported or incompletely measured estates return unavailable (77), never success.
Domus owns narrow repairs; the historical global config reinstall/cache deletion is removed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_config_paths import (  # noqa: E402
    MCP_VENDOR_KEYS,
    VENDORS,
    active_config_path,
    candidate_config_paths,
)

# ── The agent-CLI MCP config estate ────────────────────────────────────────────────────────────────
# Each entry: the on-disk config + the format hint used to parse it. Absent files are skipped
# silently (an agent that isn't installed on this host simply contributes no servers).
#
# These paths are DERIVED, never composed here. Hardcoding `HOME / ".claude.json"` is what made this
# sensor report 4 claude servers — including two "boot failures" routed to issue #2045 and recorded
# in lever L-MCP-BOOT-HEAL-ARM — on a host whose `claude mcp list` returned zero, because
# `CLAUDE_CONFIG_DIR` had moved the live config into the agent runtime and the abandoned copy still
# parsed fine. `active_config_path` is the single owner of that fact; see agent_config_paths.py.
HOME = Path.home()
CONFIG_PATHS: list[tuple[str, Path, str]] = [
    (key, active_config_path(key), VENDORS[key].fmt) for key in MCP_VENDOR_KEYS
]

# The doorway everything points at — a bare 127.0.0.1 hub reachability is checked once, separately,
# by verify-mcp-estate.sh (upstream count). Here we only probe what each agent config declares.
DEFAULT_TIMEOUT = 15  # seconds per server; the beat wraps the whole sensor in its own ceiling too.

_AUTH_NEEDED_STATES = frozenset(
    {
        "auth_needed",
        "needs_auth",
        "needs_authentication",
        "unauthenticated",
        "not_authenticated",
        "oauth_required",
        "login_required",
    }
)
_AUTHENTICATED_STATES = frozenset({"authenticated", "connected", "ready", "logged_in"})
_HEALABLE_STATES = frozenset({"unreachable", "boot_failed", "invalid"})


def _normalized_auth_state(value: object) -> str | None:
    """Reduce Codex CLI authentication labels to the estate's stable semantic states."""
    if not isinstance(value, str):
        return None
    label = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    compact = re.sub(r"[^a-z0-9]+", "", value.strip().lower())
    if label in _AUTH_NEEDED_STATES or compact == "notloggedin":
        return "auth_needed"
    if label in _AUTHENTICATED_STATES or compact in {"oauth", "loggedin"}:
        return "authenticated"
    if compact == "unsupported":
        return "reachable"
    return None


def parse_codex_mcp_statuses(payload: object) -> dict[str, str | dict[str, str]]:
    """Parse tolerated Codex MCP-list JSON envelopes into name -> auth state.

    Codex owns the command boundary, while this repository owns only the two semantic
    states it consumes. Unknown labels are intentionally ignored instead of being
    guessed into a healthy or unhealthy authentication result.
    """
    rows: object = payload
    if isinstance(payload, dict):
        for key in ("servers", "mcp_servers", "mcpServers"):
            candidate = payload.get(key)
            if isinstance(candidate, (dict, list)):
                rows = candidate
                break

    if isinstance(rows, dict):
        entries = rows.items()
    elif isinstance(rows, list):
        entries = ((row.get("name"), row) for row in rows if isinstance(row, dict) and isinstance(row.get("name"), str))
    else:
        return {}

    statuses: dict[str, str | dict[str, str]] = {}
    for name, row in entries:
        if not isinstance(name, str) or not isinstance(row, dict):
            continue
        auth = row.get("auth_status") or row.get("authStatus")
        authentication = row.get("authentication")
        if auth is None and isinstance(authentication, dict):
            auth = authentication.get("status") or authentication.get("state")
        if auth is None:
            auth = row.get("status")
        compact_auth = re.sub(r"[^a-z0-9]+", "", str(auth).strip().lower())
        if compact_auth == "bearertoken":
            transport = row.get("transport")
            transport = transport if isinstance(transport, dict) else {}
            env_name = (
                row.get("bearer_token_env_var")
                or row.get("bearerTokenEnvVar")
                or transport.get("bearer_token_env_var")
                or transport.get("bearerTokenEnvVar")
            )
            if not isinstance(env_name, str) or not env_name.strip():
                statuses[name.casefold()] = "auth_unknown"
            elif os.environ.get(env_name):
                statuses[name.casefold()] = "authenticated"
            else:
                statuses[name.casefold()] = {
                    "state": "auth_needed",
                    "missing_env": env_name,
                }
            continue
        state = _normalized_auth_state(auth)
        if state:
            statuses[name.casefold()] = state
    return statuses


def _codex_executable() -> str | None:
    """Resolve the registry-owned Codex executable without assuming it is on PATH."""
    reference = os.environ.get("LIMEN_CODEX_BIN", "").strip() or "codex"
    has_separator = os.sep in reference or bool(os.altsep and os.altsep in reference)
    if has_separator:
        candidate = Path(reference).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    return shutil.which(reference)


def _codex_mcp_statuses() -> tuple[dict[str, str | dict[str, str]], str | None]:
    """Return Codex semantic states plus a sanitized probe failure, if any."""
    codex_bin = _codex_executable()
    if codex_bin is None:
        return {}, "Codex CLI unavailable"
    try:
        result = subprocess.run(
            [codex_bin, "mcp", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            return {}, f"Codex status probe exited rc={result.returncode}"
        return parse_codex_mcp_statuses(json.loads(result.stdout)), None
    except json.JSONDecodeError:
        return {}, "Codex status probe returned invalid JSON"
    except subprocess.TimeoutExpired:
        return {}, "Codex status probe timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return {}, f"Codex status probe failed ({type(exc).__name__})"


def _strip_jsonc(text: str) -> str:
    """Strip // line and /* */ block comments from JSONC, preserving anything inside strings.

    A minimal scanner (not a full JSON parser) — good enough for the agent config files, which are
    hand- or tool-written JSONC, never adversarial. Trailing commas are also tolerated below.
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    quote = ""
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:  # keep escaped char verbatim
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                in_str = False
            i += 1
            continue
        if c in ('"', "'"):
            in_str = True
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":  # line comment
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":  # block comment
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _load_json_lenient(path: Path) -> dict | None:
    """Parse .json/.jsonc tolerantly (strip comments + trailing commas). None on any failure."""
    try:
        raw = path.read_text()
    except Exception:
        return None
    stripped = _strip_jsonc(raw)
    stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)  # trailing commas
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _load_toml(path: Path) -> dict | None:
    try:
        import tomllib  # py3.11+
    except Exception:
        return None
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except Exception:
        return None


def _server_map(data: dict) -> dict:
    """Pull the server table out of whichever envelope a config uses.

    Handles `mcpServers` (copilot/gemini/claude/cline), `mcp_servers` (codex TOML), `servers`, and
    `mcp` (opencode). Returns a name->spec dict; a list envelope is keyed by each spec's own name.
    """
    for key in ("mcpServers", "mcp_servers", "servers", "mcp"):
        val = data.get(key)
        if isinstance(val, dict) and val:
            return val
        if isinstance(val, list) and val:
            out = {}
            for item in val:
                if isinstance(item, dict) and item.get("name"):
                    out[item["name"]] = item
            if out:
                return out
    return {}


def _normalize(name: str, spec: dict) -> dict:
    """Coerce one server spec to {name, transport, command, args, env, url}. transport ∈ stdio|http."""
    url = spec.get("url") or spec.get("serverUrl") or spec.get("httpUrl") or spec.get("baseUrl")
    command = spec.get("command")
    ttype = (spec.get("type") or spec.get("transport") or "").lower()
    if url and not command:
        transport = "http"
    elif command:
        transport = "stdio"
    elif ttype in ("http", "sse", "streamable-http"):
        transport = "http"
    else:
        transport = "stdio" if command else "unknown"
    return {
        "name": name,
        "transport": transport,
        "command": command,
        "args": spec.get("args") or [],
        "env": spec.get("env") or {},
        "cwd": spec.get("cwd"),
        "url": url,
        "bearer_token_env_var": spec.get("bearer_token_env_var") or spec.get("bearerTokenEnvVar"),
        "disabled": bool(spec.get("disabled")) or spec.get("enabled") is False,
    }


def _servers_in(agent: str, path: Path, fmt: str) -> list[dict]:
    """Every non-disabled MCP server declared by ONE config file."""
    if not path.exists():
        return []
    data = _load_toml(path) if fmt == "toml" else _load_json_lenient(path)
    if not data:
        return []
    found: list[dict] = []
    for name, spec in _server_map(data).items():
        if not isinstance(spec, dict):
            continue
        s = _normalize(name, spec)
        if s["disabled"]:
            continue
        s["agent"] = agent
        s["config"] = str(path)
        found.append(s)
    return found


def discover() -> list[dict]:
    """Enumerate every non-disabled MCP server across every ACTIVE agent config."""
    servers: list[dict] = []
    for agent, path, fmt in CONFIG_PATHS:
        servers.extend(_servers_in(agent, path, fmt))
    return servers


def stranded_configs() -> list[dict]:
    """Vendors whose live config declares nothing while an abandoned copy still declares servers.

    Resolving paths correctly removes a false RED, but on its own it would replace that red with
    SILENCE: a vendor contributing zero servers looks exactly like a vendor that never had any,
    and the sensor simply stops mentioning it. That is the wrong trade — the operator loses the
    only evidence that a relocation dropped four working servers on the floor.

    So the migration is named directly. Relocating a config root (CLAUDE_CONFIG_DIR,
    GEMINI_CLI_HOME, CODEX_HOME) leaves the previous file intact and parseable; the CLI reads the
    new root and finds nothing. Active-empty while a candidate root is non-empty is precisely that
    situation, and it is a finding, not a hush.
    """
    findings: list[dict] = []
    for agent, active, fmt in CONFIG_PATHS:
        if _servers_in(agent, active, fmt):
            continue
        resolved_active = active.resolve(strict=False)
        for candidate in candidate_config_paths(agent):
            if candidate.resolve(strict=False) == resolved_active:
                continue
            orphaned = _servers_in(agent, candidate, fmt)
            if orphaned:
                findings.append(
                    {
                        "agent": agent,
                        "active": str(active),
                        "stale": str(candidate),
                        "servers": sorted(s["name"] for s in orphaned),
                    }
                )
                break
    return findings


def _probe_http(url: str, timeout: int) -> tuple[bool, str]:
    from mcp_protocol import verify

    result = verify({"transport": "http", "url": url}, timeout=timeout)
    ok = result["dimensions"]["protocol"] == "pass"
    return ok, "MCP exchange verified" if ok else result.get("reason", "unmeasured")


def _probe_stdio(server: dict, timeout: int) -> tuple[bool, str]:
    from mcp_protocol import verify

    result = verify(server, timeout=timeout)
    ok = result["dimensions"]["protocol"] == "pass"
    if ok:
        return True, "MCP exchange verified"
    if result.get("reason") == "server_rpc_error" and type(result.get("rpc_error_code")) is int:
        return False, f"server_rpc_error:{result['rpc_error_code']}"
    return False, result.get("reason", "unmeasured")


def probe(server: dict, timeout: int) -> dict:
    if server["transport"] == "http":
        ok, detail = _probe_http(server["url"], timeout)
        state = "reachable" if ok else "unreachable"
    elif server["transport"] == "stdio":
        ok, detail = _probe_stdio(server, timeout)
        state = "boots" if ok else "boot_failed"
    else:
        ok, detail = False, "unknown transport (no command or url)"
        state = "invalid"
    return {**server, "ok": ok, "state": state, "detail": detail}


def _apply_codex_semantic_state(
    result: dict,
    statuses: dict[str, str | dict[str, str]],
    status_error: str | None,
) -> dict:
    """Overlay Codex authentication truth on a successful HTTP transport probe."""
    if result["agent"] != "codex" or result["transport"] != "http" or not result["ok"]:
        return result
    parsed_url = urlparse(result.get("url") or "")
    if (
        result["name"].casefold() == "ianva"
        and parsed_url.hostname in {"127.0.0.1", "::1", "localhost"}
        and not result.get("bearer_token_env_var")
    ):
        # Codex reports the generic `not_logged_in` label for authless HTTP MCPs too.
        # ianva's open loopback face is intentionally transport-only; treating that label
        # as hosted OAuth would recreate the dashboard-auth false positive this predicate owns.
        return result
    if status_error:
        return {
            **result,
            "ok": False,
            "state": "auth_unknown",
            "detail": f"{result['detail']}; {status_error}",
        }
    auth_status = statuses.get(result["name"].casefold(), "auth_unknown")
    if isinstance(auth_status, dict):
        auth_state = auth_status.get("state", "auth_unknown")
        missing_env = auth_status.get("missing_env")
    else:
        auth_state = auth_status
        missing_env = None
    if auth_state == "auth_needed":
        auth_detail = (
            f"missing bearer environment {missing_env}" if missing_env else "Codex OAuth authentication required"
        )
        return {
            **result,
            "ok": False,
            "state": "auth_needed",
            "detail": f"{result['detail']}; {auth_detail}",
        }
    if auth_state == "auth_unknown":
        return {
            **result,
            "ok": False,
            "state": "auth_unknown",
            "detail": f"{result['detail']}; Codex authentication state unknown",
        }
    if auth_state == "authenticated":
        return {**result, "state": "authenticated"}
    return result


def probe_all(servers: list[dict], timeout: int) -> list[dict]:
    """Probe transport once per server and Codex semantic status once per batch."""
    if any(s["agent"] == "codex" and s["transport"] == "http" for s in servers):
        codex_statuses, codex_status_error = _codex_mcp_statuses()
    else:
        codex_statuses, codex_status_error = {}, None
    return [
        _apply_codex_semantic_state(
            probe(server, timeout),
            codex_statuses,
            codex_status_error,
        )
        for server in servers
    ]


def _healable_failures(results: list[dict]) -> list[dict]:
    """Return only failures the bounded config/boot healer can actually repair."""
    return [result for result in results if result.get("state") in _HEALABLE_STATES]


def _failure_cures(failed: list[dict]) -> list[str]:
    """Return state-specific, actionable cures without suggesting an unrelated effector."""
    cures: list[str] = []
    for result in failed:
        state = result.get("state")
        if state == "auth_needed":
            missing_env_match = re.search(
                r"missing bearer environment ([A-Za-z_][A-Za-z0-9_]*)", result.get("detail", "")
            )
            if missing_env_match:
                cure = f"populate {missing_env_match.group(1)} through the credential organ"
            else:
                cure = f"codex mcp login {result['name']}"
        elif state == "auth_unknown":
            cure = "codex mcp list --json (restore semantic auth telemetry)"
        elif state in _HEALABLE_STATES:
            cure = "arm LIMEN_MCP_BOOT_HEAL=1 (re-land config and clear corrupt npx caches)"
        else:
            continue
        if cure not in cures:
            cures.append(cure)
    return cures


# ── Heal effector (dormant unless --apply, which the sensor only passes when LIMEN_MCP_BOOT_HEAL=1) ─


def _print_stranded(stranded: list[dict]) -> None:
    """Name a relocation that dropped servers, with the exact re-land command."""
    for row in stranded:
        names = ", ".join(row["servers"])
        print(f"  ✗ {row['agent']:32} STRANDED — active config declares 0 servers")
        print(f"      active: {row['active']}")
        print(f"      stale : {row['stale']}  (still declares: {names})")
    if stranded:
        print("  Cure: re-land the entries into the ACTIVE config (`ianva install-configs --apply`,")
        print("  or `claude mcp add …`). The stale file is not read and must not be edited.")


def main(argv=None) -> int:
    from mcp_estate import main as estate_main

    return estate_main(argv)


if __name__ == "__main__":
    sys.exit(main())
