"""Filesystem layout for ianva, and the ~/.limen.env loader.

All paths are derived (never pinned) and overridable by env so ianva is relocatable and
testable. Defaults follow XDG and the fleet's existing conventions.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_path(var: str, default: Path) -> Path:
    val = os.environ.get(var)
    return Path(val).expanduser() if val else default


HOME = Path.home()

# ianva's own config/state dir (XDG). Override with IANVA_HOME.
IANVA_HOME = _env_path("IANVA_HOME", _env_path("XDG_CONFIG_HOME", HOME / ".config") / "ianva")

# The fleet's single secret store — the ONLY place upstream creds and fleet tokens live.
LIMEN_ENV = _env_path("LIMEN_ENV", HOME / ".limen.env")

# build-mcp-registry.py's inventory of every MCP server across all tools (its only consumer is us).
DEFAULT_REGISTRY = _env_path("IANVA_REGISTRY", HOME / ".agents" / "mcp" / "servers.json")

# ianva's own extra/override upstream definitions.
UPSTREAMS_JSON = IANVA_HOME / "upstreams.json"

# Materialized MCPHub settings — MCPHub reads `mcp_settings.json` from its working dir,
# so ianva writes it here and runs the backend with cwd=IANVA_HOME.
MCPHUB_SETTINGS = IANVA_HOME / "mcp_settings.json"

# Runtime state.
RUN_DIR = IANVA_HOME / "run"
LOCK_DIR = IANVA_HOME / "locks"
LOG_DIR = IANVA_HOME / "logs"

# Generated agent-config entries (golden output of `ianva gen-configs`; staged, not auto-installed).
GENERATED_DIR = _env_path("IANVA_GENERATED", Path(__file__).resolve().parents[2] / "generated")


def ensure_dirs() -> None:
    for d in (IANVA_HOME, RUN_DIR, LOCK_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_limen_env(path: Path | None = None) -> dict[str, str]:
    """Parse ~/.limen.env (`export KEY=VALUE` lines) into a dict. Never logs values."""
    p = path or LIMEN_ENV
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ")
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out
