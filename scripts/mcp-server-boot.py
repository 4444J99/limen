#!/usr/bin/env python3
"""mcp-server-boot — the MCP-server liveness predicate (Lane A of the MCP estate).

The MCP estate has two failure lanes. Lane B (scripts/mcp-auth-verify.py) is the claude.ai *hosted*
connectors whose OAuth consent lives server-side. THIS is Lane A: the *local/stdio* MCP servers that
every agent CLI spawns itself (copilot, codex, gemini, agy, claude, cline, opencode). Nothing in the
beat ever checked whether a configured local server actually BOOTS — so two of Copilot's four servers
sat red for weeks (github: `docker run …` on a Docker-less host; desktop-commander: a corrupt npx
cache that crashes on start) with no sensor to see it. This closes that blind spot: it enumerates
every configured server across every agent config and confirms it can start / is reachable.

The heal effector (`--apply`, gated by LIMEN_MCP_BOOT_HEAL=1) uses ianva's EXISTING verbs — it adds
no new remediation. `ianva install-configs --apply` re-lands a dropped agent entry (the opencode
gap); an npx-cache clear cures the corrupt-cache crash class. Populating the empty ianva upstream
registry is NOT auto-guessed (the upstream set is a registry decision, not a probe result) — the cure
is reported, not executed. Default (unarmed) = report-only, exactly like launch-agent-liveness.

Exit: 0 when every CONFIGURED server boots/reaches (or when no agent configs exist at all — a CI host
has none, so the sensor is a no-op there, never a false red). Nonzero when a configured server fails
to start / is unreachable; the offenders are printed (env VALUES are never printed — only names). The
beat runs this at `severity: advisory`, so a red surfaces in the log without breaking the beat, the
same fail-open contract as its Lane-B sibling. No secret material is ever emitted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import select
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# ── The agent-CLI MCP config estate (paths confirmed by the 2026-07-18 estate recon) ──────────────
# Each entry: the on-disk config + the format hint used to parse it. Absent files are skipped
# silently (an agent that isn't installed on this host simply contributes no servers).
HOME = Path.home()
CONFIG_PATHS: list[tuple[str, Path, str]] = [
    ("copilot", HOME / ".copilot" / "mcp-config.json", "json"),
    ("codex", HOME / ".codex" / "config.toml", "toml"),
    ("gemini", HOME / ".gemini" / "settings.json", "json"),
    ("agy", HOME / ".gemini" / "config" / "mcp_config.json", "json"),
    ("claude", HOME / ".claude.json", "json"),
    ("cline", HOME / ".cline" / "data" / "settings" / "cline_mcp_settings.json", "json"),
    ("opencode", HOME / ".config" / "opencode" / "opencode.jsonc", "jsonc"),
]

# The doorway everything points at — a bare 127.0.0.1 hub reachability is checked once, separately,
# by verify-mcp-estate.sh (upstream count). Here we only probe what each agent config declares.
DEFAULT_TIMEOUT = 15  # seconds per server; the beat wraps the whole sensor in its own ceiling too.


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
        "url": url,
        "disabled": bool(spec.get("disabled")) or spec.get("enabled") is False,
    }


def discover() -> list[dict]:
    """Enumerate every non-disabled MCP server across every present agent config."""
    servers: list[dict] = []
    for agent, path, fmt in CONFIG_PATHS:
        if not path.exists():
            continue
        data = _load_toml(path) if fmt == "toml" else _load_json_lenient(path)
        if not data:
            continue
        for name, spec in _server_map(data).items():
            if not isinstance(spec, dict):
                continue
            s = _normalize(name, spec)
            if s["disabled"]:
                continue
            s["agent"] = agent
            s["config"] = str(path)
            servers.append(s)
    return servers


def _probe_http(url: str, timeout: int) -> tuple[bool, str]:
    """Reachable iff a TCP connect to the url's host:port succeeds. Any listener = reachable."""
    try:
        u = urlparse(url)
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if u.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"reachable {host}:{port}"
    except Exception as e:  # connection refused / DNS / timeout
        return False, f"unreachable ({type(e).__name__})"


def _probe_stdio(server: dict, timeout: int) -> tuple[bool, str]:
    """Boots iff the command resolves AND the process starts without immediately crashing.

    Layered so it catches the real failure modes without depending on framing details, and
    judges the handshake BEFORE the exit code (a server can handshake cleanly yet exit nonzero on
    stdin-EOF — github-mcp-server does):
      1. binary unresolvable                       -> FAIL  (github's old `docker run`, Docker-less host)
      2. a JSON-RPC initialize reply arrives        -> BOOTS (handshake, the authoritative signal)
      3. no reply, still alive at timeout           -> BOOTS (alive; some servers need a real init)
      4. no reply, exited nonzero                   -> FAIL  (a real crash: corrupt-npx-cache, bad token)
      5. no reply, exited clean (rc 0)              -> BOOTS (started, didn't crash)
    """
    command = server["command"]
    if not command:
        return False, "no command"
    if not shutil.which(command):
        return False, f"command not found: {command}"

    argv = [command, *[str(a) for a in server["args"]]]
    env = {**os.environ, **{str(k): str(v) for k, v in server["env"].items()}}
    init = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-server-boot", "version": "0.1"},
            },
        }
    )
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            start_new_session=True,
        )
    except Exception as e:
        return False, f"spawn failed ({type(e).__name__})"

    try:
        try:
            proc.stdin.write(init + "\n")
            proc.stdin.flush()
        except Exception:
            pass  # a server that closed stdin instantly is judged by its exit below

        # Read stdout for a JSON-RPC initialize reply while keeping stdin OPEN. Closing stdin
        # (what communicate() does) makes servers that treat stdin-EOF as shutdown exit nonzero
        # BEFORE they answer — github-mcp-server logs "server is closing: EOF" and exits rc=1 even
        # though it handshakes cleanly when the pipe stays open. So a valid handshake is the
        # authoritative BOOTS signal and is judged FIRST; a nonzero exit only fails when no
        # handshake ever arrived (a real crash, e.g. desktop-commander's corrupt-npx-cache).
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            rlist, _, _ = select.select([proc.stdout], [], [], remaining)
            if not rlist:
                break  # nothing readable within the budget
            line = proc.stdout.readline()
            if line == "":
                break  # stdout EOF — the process is done writing
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("id") == 1 and "result" in msg:
                return True, "boots (initialize handshake ok)"

        # No handshake captured. Distinguish a still-alive server (needs a real init / slow to
        # answer — case 4) from an actual crash, consulting the exit code only NOW.
        rc = proc.poll()
        if rc is None:
            return True, "boots (alive, no handshake within timeout)"
        if rc != 0:
            return False, f"exited rc={rc} on start"
        return True, "boots (clean start, no handshake)"
    finally:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass


def probe(server: dict, timeout: int) -> dict:
    if server["transport"] == "http":
        ok, detail = _probe_http(server["url"], timeout)
    elif server["transport"] == "stdio":
        ok, detail = _probe_stdio(server, timeout)
    else:
        ok, detail = False, "unknown transport (no command or url)"
    return {**server, "ok": ok, "detail": detail}


# ── Heal effector (dormant unless --apply, which the sensor only passes when LIMEN_MCP_BOOT_HEAL=1) ─
def _heal(failed: list[dict]) -> list[str]:
    """Best-effort, idempotent heal via ianva's existing verbs + an npx-cache clear. Reports actions.

    Never guesses ianva upstreams (that set is a registry decision) — it re-lands dropped agent
    entries and clears corrupt npx caches, the two mechanically-safe cures.
    """
    actions: list[str] = []
    if shutil.which("ianva"):
        try:
            r = subprocess.run(
                ["ianva", "install-configs", "--apply"],
                capture_output=True, text=True, timeout=60,
            )
            actions.append(f"ianva install-configs --apply -> rc={r.returncode}")
        except Exception as e:
            actions.append(f"ianva install-configs --apply -> error {type(e).__name__}")
    else:
        actions.append("ianva not on PATH — cannot re-land dropped agent entries")

    npx_failed = [s for s in failed if s.get("command") == "npx"]
    if npx_failed:
        for root in (HOME / ".npm" / "_npx", HOME / ".cache" / "npm" / "_npx"):
            if root.exists():
                try:
                    shutil.rmtree(root)
                    actions.append(f"cleared npx cache {root}")
                except Exception as e:
                    actions.append(f"npx cache {root} -> error {type(e).__name__}")
    return actions


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify local MCP servers boot across every agent CLI (Lane A).")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per server (default 15)")
    ap.add_argument("--apply", action="store_true", help="arm the heal effector (ianva install-configs + npx-cache clear)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    present_configs = [p for _, p, _ in CONFIG_PATHS if p.exists()]
    if not present_configs:
        note = "no agent-CLI MCP configs present (CI host?) — nothing to probe, fail-open."
        print(json.dumps({"exit": 0, "note": "no-configs"}) if args.json else f"mcp-server-boot: {note}")
        return 0

    servers = discover()
    if not servers:
        note = f"{len(present_configs)} config(s) present but declare 0 MCP servers — nothing to probe."
        print(json.dumps({"exit": 0, "note": "no-servers"}) if args.json else f"mcp-server-boot: {note}")
        return 0

    results = [probe(s, args.timeout) for s in servers]
    failed = [r for r in results if not r["ok"]]

    healed: list[str] = []
    if args.apply and failed:
        healed = _heal(failed)
        results = [probe(s, args.timeout) for s in servers]  # re-probe once after heal
        failed = [r for r in results if not r["ok"]]

    if args.json:
        payload = {
            "exit": 1 if failed else 0,
            "servers": [
                {"agent": r["agent"], "name": r["name"], "transport": r["transport"], "ok": r["ok"], "detail": r["detail"]}
                for r in results
            ],
            "failed": [f"{r['agent']}/{r['name']}" for r in failed],
        }
        if healed:
            payload["healed"] = healed
        print(json.dumps(payload))
        return payload["exit"]

    print(f"mcp-server-boot — local MCP servers across {len(present_configs)} agent config(s):")
    for r in results:
        mark = "✓" if r["ok"] else "✗"
        label = f"{r['agent']}/{r['name']}"
        print(f"  {mark} {label:34} [{r['transport']}] {r['detail']}")
    if healed:
        print("  heal (--apply):")
        for a in healed:
            print(f"    · {a}")
    if failed:
        names = ", ".join(f"{r['agent']}/{r['name']}" for r in failed)
        print(f"mcp-server-boot: {len(failed)} configured server(s) fail to boot/reach — {names}.")
        print("  Cure: arm LIMEN_MCP_BOOT_HEAL=1 (ianva install-configs re-lands dropped entries, npx-cache clear")
        print("  cures corrupt-cache crashes); an EMPTY ianva upstream registry is a registry decision — see")
        print("  verify-mcp-estate.sh doorway check + `ianva add-upstream`. Surfaced in the beat log, non-fatal.")
        return 1
    print(f"  all {len(results)} configured MCP server(s) boot/reach.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
