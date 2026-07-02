#!/usr/bin/env python3
"""mcp-auth-verify — the MCP-connector consent predicate (Lane B of the credential estate).

The op:// service-secret lane (scripts/creds-hydrate.py) has two homes the MCP lane never had: a
local token store AND a validity probe (`creds-hydrate --verify`). This is the missing probe for the
OTHER lane — the claude.ai hosted MCP connectors whose OAuth grants live SERVER-SIDE in Anthropic's
cloud (no local token, no local refresh material). When one lapses it can only be re-consented
interactively via /mcp, which a headless beat structurally cannot do — so it used to re-nag in chat.

This script moves that nag OUT of chat and INTO the beat log, exactly like a dead op:// token: it
reads the connector-consent state and reports which connectors await one-time auth, pointing at the
ONE permanent cure — the ianva cloud aggregator (his-hand lever L-IANVA-CLOUD #263) that lets
claude.ai consent ONCE instead of per-connector.

Sources (in priority): live `claude mcp list` (--live) else the daemon's needs-auth marker cache at
~/.claude/mcp-needs-auth-cache.json (instant, offline). No secret material is read or printed — the
hosted connectors keep NO local token; the cache holds only connector names + internal server ids
(never printed).

Exit: 0 by default (fail-open — a lapsed OPTIONAL connector never blocks the beat, and the whole
point is to stop nagging). Nonzero only when a connector named in --required / $LIMEN_MCP_REQUIRED is
unauthenticated, or under --strict (any unauthenticated connector) — so a done.sh can gate on it
deliberately. Mirrors the creds-hydrate --verify contract: validity surfaced, beat never broken.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CACHE = Path(
    os.environ.get(
        "LIMEN_MCP_NEEDS_AUTH_CACHE",
        str(Path.home() / ".claude" / "mcp-needs-auth-cache.json"),
    )
)
# The one bearer'd aggregator claude.ai consents to ONCE — the permanent cure for this whole class.
CURE_LEVER = "L-IANVA-CLOUD (#263)"


def parse_needs_auth_cache(data) -> list[str]:
    """Connector names flagged needs-auth in the daemon's marker cache. Names only — no ids/tokens."""
    if not isinstance(data, dict):
        return []
    return sorted(data.keys())


def parse_mcp_list(text: str) -> dict[str, str]:
    """Parse `claude mcp list` -> {connector: 'connected'|'needs_auth'}.

    Robust to connector URLs containing ':' (https://, http://127.0.0.1:7666). The connector name is
    everything up to the first ': ' that precedes the url; status is read from the line's suffix.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("checking"):
            continue
        low = line.lower()
        if low.endswith("connected"):
            status = "connected"
        elif "needs authentication" in low:
            status = "needs_auth"
        else:
            continue
        m = re.match(r"^(.*?):\s+\S", line)
        name = (m.group(1) if m else line).strip()
        if name:
            out[name] = status
    return out


def load_cache(path: Path = CACHE):
    """Read the needs-auth marker cache. Returns None (fail-open) on absence or any parse error."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def run_mcp_list(timeout: int = 12) -> str | None:
    """Best-effort `claude mcp list`. Returns stdout, or None if the CLI is missing/slow/errors."""
    try:
        p = subprocess.run(
            ["claude", "mcp", "list"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.stdout or ""
    except Exception:
        return None


def _match_required(connector: str, required: set[str]) -> bool:
    """Case-insensitive substring match so 'sentry' matches the connector 'claude.ai Sentry'."""
    c = connector.lower()
    return any(r.lower() in c for r in required)


def verdict(needs_auth: list[str], connected: list[str] | None, required: set[str], strict: bool) -> dict:
    """Pure decision: which lapses matter and the resulting exit code. No I/O."""
    req_lapsed = sorted({c for c in needs_auth if _match_required(c, required)})
    if req_lapsed:
        code = 1
    elif strict and needs_auth:
        code = 1
    else:
        code = 0
    return {
        "needs_auth": sorted(needs_auth),
        "connected": sorted(connected) if connected is not None else None,
        "required_lapsed": req_lapsed,
        "exit": code,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Verify claude.ai MCP connector consent (Lane B of the credential estate)."
    )
    ap.add_argument(
        "--live",
        action="store_true",
        help="query `claude mcp list` (network, ~5s) for the full picture instead of the offline cache",
    )
    ap.add_argument(
        "--required",
        default=os.environ.get("LIMEN_MCP_REQUIRED", ""),
        help="comma list of connectors that MUST be authed; exit 1 if any lapses (else $LIMEN_MCP_REQUIRED)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if ANY connector awaits auth (for a deliberate done.sh / human gate)",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    required = {r.strip() for r in args.required.split(",") if r.strip()}

    connected: list[str] | None = None
    needs: list[str] | None = None
    source = str(CACHE)

    if args.live:
        text = run_mcp_list()
        if text is not None:
            parsed = parse_mcp_list(text)
            needs = [k for k, v in parsed.items() if v == "needs_auth"]
            connected = [k for k, v in parsed.items() if v == "connected"]
            source = "claude mcp list"

    if needs is None:  # default path, or --live fell through (CLI absent/slow) -> offline cache
        data = load_cache()
        if data is None:
            note = f"{CACHE} absent; `claude mcp list` unavailable"
            if args.json:
                print(json.dumps({"exit": 0, "note": "no-source", "detail": note}))
            else:
                print(f"mcp-auth-verify: no connector state available ({note}) — fail-open, skipping.")
            return 0
        needs = parse_needs_auth_cache(data)

    v = verdict(needs, connected, required, args.strict)

    if args.json:
        print(json.dumps({**v, "source": source, "cure": CURE_LEVER}))
        return v["exit"]

    print(f"mcp-auth-verify ({source}) — claude.ai MCP connector consent status:")
    if not needs:
        tail = f"; {len(connected)} connected" if connected is not None else ""
        print(f"  ✓ all known claude.ai connectors consented (0 awaiting auth{tail}).")
        return v["exit"]

    for c in needs:
        required_hit = c in v["required_lapsed"]
        flag = "✗" if required_hit else "!"
        tag = " REQUIRED" if required_hit else ""
        print(f"  {flag} {c:42} NEEDS AUTH{tag}")

    total = f" of {len(needs) + len(connected)}" if connected is not None else ""
    print(
        f"mcp-auth: {len(needs)}{total} connector(s) await one-time consent — "
        "server-side OAuth, no local token to refresh."
    )
    print(
        f"  Permanent cure: pull {CURE_LEVER} — one bearer'd aggregator claude.ai "
        "consents to ONCE, ending the per-connector re-auth."
    )
    print("  Surfaced here in the beat log, never recited in chat. Non-fatal — the beat continues.")
    if v["required_lapsed"]:
        print(
            f"mcp-auth: ✗ = a REQUIRED connector ({', '.join(v['required_lapsed'])}) "
            "is unauthenticated — exit 1."
        )
    return v["exit"]


if __name__ == "__main__":
    sys.exit(main())
