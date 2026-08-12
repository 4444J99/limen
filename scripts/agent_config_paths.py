#!/usr/bin/env python3
"""Resolve the config file each agent CLI ACTUALLY reads.

Every agent CLI on this estate can have its config root relocated by an environment
variable — `CLAUDE_CONFIG_DIR`, `GEMINI_CLI_HOME`, `CODEX_HOME` — and this host sets all
three from `~/.zshenv` so the agent runtime lives inside the repo
(`LIMEN_AGENT_RUNTIME_ROOT`). A surface that composes `Path.home() / ".claude.json"` by hand
therefore reads a file the CLI abandoned, and the abandoned copy keeps its last-known-good
contents forever — so the read *succeeds*, returns plausible data, and nothing looks wrong.

That failure mode was live in three separate places at once (measured 2026-08-12):

* `mcp-server-boot.py` (beat sensor 0b2) reported 4 claude MCP servers and two boot
  failures; `claude mcp list` had **zero** servers. The two "failures" were routed to
  issue #2045 and recorded in lever `L-MCP-BOOT-HEAL-ARM`.
* `session-opening-floor.py` read `~/.codex/config.toml` and reported
  `model_reasoning_effort = "ultra"` as an above-ceiling cost breach; the file codex reads
  said `"max"`.
* `ianva install-configs --apply` — the *cure* prescribed by that same lever — wrote to the
  abandoned path, which would have made the sensor go green while the CLI still had nothing.

Detection and cure sharing one wrong path is what makes this class self-concealing, so the
path is owned here once and derived everywhere else.

Two reducers, because the two questions are genuinely different:

* :func:`active_config_path` — the single file the CLI reads *right now*. Deterministic from
  the environment, with no existence probing: an unwritten config under an explicit
  `CLAUDE_CONFIG_DIR` is still the active path, and falling back to `$HOME` because it does
  not exist yet is exactly the bug. Use this to measure or to write.
* :func:`candidate_config_paths` — every root a config could live under (active, the `$HOME`
  default, and the agent-runtime copy). Use this only when a setting must be true in *all*
  of them, which is why `tcc-identity-audit.py` flips `autoUpdates` across the whole list.

Measuring with the candidate list would double-count: the stale and live claude configs
would both contribute servers, inventing servers that boot.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "VENDORS",
    "VendorConfig",
    "active_config_path",
    "agent_runtime_root",
    "candidate_config_paths",
]


@dataclass(frozen=True)
class VendorConfig:
    """One agent CLI's config location, expressed as roots rather than a literal path.

    ``env_relative`` and ``home_relative`` differ whenever the relocation variable replaces a
    dotted subdirectory rather than the home directory itself: ``CODEX_HOME`` *is* the
    ``~/.codex`` directory, so its config is ``$CODEX_HOME/config.toml``, while
    ``GEMINI_CLI_HOME`` stands in for ``$HOME`` and keeps the ``.gemini/`` segment.
    """

    key: str
    fmt: str
    home_relative: str
    root_env: str | None = None
    env_relative: str = ""
    runtime_relative: str | None = None


# The estate, ordered as `mcp-server-boot.py` has always probed it. `fmt` is the parse hint
# that sensor needs; surfaces that only want a path can ignore it.
VENDORS: dict[str, VendorConfig] = {
    "copilot": VendorConfig(
        key="copilot",
        fmt="json",
        home_relative=".copilot/mcp-config.json",
    ),
    "codex": VendorConfig(
        key="codex",
        fmt="toml",
        home_relative=".codex/config.toml",
        root_env="CODEX_HOME",
        env_relative="config.toml",
        runtime_relative="codex/config.toml",
    ),
    "gemini": VendorConfig(
        key="gemini",
        fmt="json",
        home_relative=".gemini/settings.json",
        root_env="GEMINI_CLI_HOME",
        env_relative=".gemini/settings.json",
        runtime_relative="gemini/home/.gemini/settings.json",
    ),
    "agy": VendorConfig(
        key="agy",
        fmt="json",
        home_relative=".gemini/config/mcp_config.json",
        root_env="GEMINI_CLI_HOME",
        env_relative=".gemini/config/mcp_config.json",
        runtime_relative="gemini/home/.gemini/config/mcp_config.json",
    ),
    "claude": VendorConfig(
        key="claude",
        fmt="json",
        home_relative=".claude.json",
        root_env="CLAUDE_CONFIG_DIR",
        env_relative=".claude.json",
        runtime_relative="claude/.claude.json",
    ),
    "cline": VendorConfig(
        key="cline",
        fmt="json",
        home_relative=".cline/data/settings/cline_mcp_settings.json",
    ),
    "opencode": VendorConfig(
        key="opencode",
        fmt="jsonc",
        home_relative=".config/opencode/opencode.jsonc",
    ),
    # Not an MCP surface: `settings.json` sits *inside* `~/.claude/` but *beside* the config
    # document under an explicit CLAUDE_CONFIG_DIR. Declared here so the one asymmetry in the
    # estate is written down once instead of being rediscovered per consumer.
    "claude-settings": VendorConfig(
        key="claude-settings",
        fmt="json",
        home_relative=".claude/settings.json",
        root_env="CLAUDE_CONFIG_DIR",
        env_relative="settings.json",
        runtime_relative="claude/settings.json",
    ),
}

# The vendors `mcp-server-boot.py` probes, in its historical order.
MCP_VENDOR_KEYS: tuple[str, ...] = ("copilot", "codex", "gemini", "agy", "claude", "cline", "opencode")


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _home(env: Mapping[str, str]) -> Path:
    return Path(env.get("HOME", str(Path.home()))).expanduser()


def _expand_user_path(value: str, env: Mapping[str, str]) -> Path:
    if value == "~":
        return _home(env)
    if value.startswith("~/"):
        return _home(env) / value[2:]
    return Path(value).expanduser()


def agent_runtime_root(env: Mapping[str, str] | None = None) -> Path:
    """Where the relocated agent runtime lives, whether or not the vendor vars are exported.

    `LIMEN_AGENT_RUNTIME_ROOT` is the variable `~/.zshenv` actually sets; `LIMEN_ROOT` is the
    older spelling `tcc-identity-audit.py` derived it from. Both resolve to the same place, and
    accepting either keeps the candidate list complete on a host that exports only one.
    """
    environ = _env(env)
    if explicit := environ.get("LIMEN_AGENT_RUNTIME_ROOT"):
        return _expand_user_path(explicit, environ)
    limen_root = _expand_user_path(
        environ.get("LIMEN_ROOT", str(_home(environ) / "Workspace/limen")),
        environ,
    )
    return limen_root / ".agent-runtime"


def _vendor(vendor: str | VendorConfig) -> VendorConfig:
    if isinstance(vendor, VendorConfig):
        return vendor
    try:
        return VENDORS[vendor]
    except KeyError:
        raise KeyError(f"unknown agent vendor {vendor!r}; known: {', '.join(sorted(VENDORS))}") from None


def active_config_path(vendor: str | VendorConfig, env: Mapping[str, str] | None = None) -> Path:
    """The config file this CLI reads under the current environment.

    Deliberately does not check existence. A CLI told to use `CLAUDE_CONFIG_DIR` reads that
    location whether or not a file is there yet, so probing existence and silently falling back
    to `$HOME` would reintroduce the exact defect this module exists to remove.
    """
    environ = _env(env)
    spec = _vendor(vendor)
    if spec.root_env:
        root = (environ.get(spec.root_env) or "").strip()
        if root:
            return _expand_user_path(root, environ) / spec.env_relative
    return _home(environ) / spec.home_relative


def candidate_config_paths(vendor: str | VendorConfig, env: Mapping[str, str] | None = None) -> list[Path]:
    """Every plausible home for this vendor's config, active first, de-duplicated.

    Only for consumers that must hold a setting true everywhere it could be read — the
    `autoUpdates` audit is the motivating case, because a session under one root never sees
    the other. Anything that *counts* or *measures* wants :func:`active_config_path`.
    """
    environ = _env(env)
    spec = _vendor(vendor)
    candidates = [active_config_path(spec, environ), _home(environ) / spec.home_relative]
    if spec.runtime_relative:
        candidates.append(agent_runtime_root(environ) / spec.runtime_relative)

    seen: set[Path] = set()
    result: list[Path] = []
    for path in candidates:
        resolved = path.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Resolve the config file each agent CLI actually reads.")
    ap.add_argument("vendor", nargs="?", help="one vendor key; omit to report the MCP estate")
    ap.add_argument("--all", action="store_true", help="include non-MCP vendors (claude-settings)")
    ap.add_argument("--candidates", action="store_true", help="print every candidate root, not just the active one")
    ap.add_argument("--existing", action="store_true", help="print only paths that exist on disk")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    # Default to the MCP estate: `claude-settings` is a settings document, not an MCP config, and a
    # consumer scanning "every config" for MCP servers must not be handed it.
    keys = [args.vendor] if args.vendor else (list(VENDORS) if args.all else list(MCP_VENDOR_KEYS))
    for key in keys:
        if key not in VENDORS:
            print(f"unknown vendor {key!r}; known: {', '.join(sorted(VENDORS))}", file=sys.stderr)
            return 2

    rows = []
    for key in keys:
        paths = candidate_config_paths(key) if args.candidates else [active_config_path(key)]
        for path in paths:
            if args.existing and not path.exists():
                continue
            rows.append({"vendor": key, "path": str(path), "exists": path.exists(), "fmt": VENDORS[key].fmt})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print(row["path"] if args.vendor else f"{row['vendor']}\t{row['path']}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI shim
    raise SystemExit(main())
