"""ianva's own configuration. Every value is a derived default, overridable via ianva.toml.

Loaded with tomllib when available (py3.11+); on 3.10 the declarative ianva.toml is
documentation and the dataclass defaults (plus an optional ~/.config/ianva/ianva.json
override) drive the code. Backend commands are config knobs, never pinned literals — the
exact MCPHub / mcp-proxy invocation is a value to verify (`ianva doctor`), not to assume.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

try:  # py3.11+
    import tomllib  # type: ignore
except ModuleNotFoundError:  # py3.10
    tomllib = None  # type: ignore


@dataclass
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 7666
    path: str = "/mcp"
    public_url: str = ""

    backend: str = "mcphub"  # "mcphub" | "docker"
    # MCPHub (verified npm pkg @samanhappy/mcphub) reads mcp_settings.json from its CWD;
    # ianva runs it in IANVA_HOME (where it materializes that file) and passes PORT via env.
    # {port}/{settings} remain available for a custom backend command. Verify with `ianva doctor`.
    backend_cmd: str = "npx -y @samanhappy/mcphub@1.0.18"

    proxy_bin: str = "uvx"
    # mcp-proxy client mode: --transport streamablehttp connects to ianva's streamable-HTTP endpoint.
    proxy_args: list[str] = field(default_factory=lambda: ["mcp-proxy", "--transport", "streamablehttp"])

    registry: str = ""  # defaults to paths.DEFAULT_REGISTRY when empty
    extra: str = ""  # defaults to paths.UPSTREAMS_JSON when empty

    def backend_argv(self, settings_path: Path) -> list[str]:
        # Token-wise substitution (NOT str.format) so literal { } in a custom backend_cmd —
        # JSON args, shell ${VAR}, docker flags — never raise KeyError before the backend starts.
        subs = {"{port}": str(self.port), "{settings}": str(settings_path)}
        out = []
        for tok in shlex.split(self.backend_cmd):
            for needle, value in subs.items():
                tok = tok.replace(needle, value)
            out.append(tok)
        return out

    def endpoint_kwargs(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "public_url": self.public_url,
            "proxy_bin": self.proxy_bin,
            "proxy_args": list(self.proxy_args),
        }


def _config_files() -> list[Path]:
    here = Path(__file__).resolve().parents[2]  # ianva/
    return [here / "ianva.toml", paths.IANVA_HOME / "ianva.toml", paths.IANVA_HOME / "ianva.json"]


def _merge(cfg: GatewayConfig, data: dict) -> None:
    g = data.get("gateway", data)
    for key in ("host", "port", "path", "public_url"):
        if key in g:
            setattr(cfg, key, g[key])
    core = data.get("core", {})
    if "backend" in core:
        cfg.backend = core["backend"]
    if "backend_cmd" in core:
        cfg.backend_cmd = core["backend_cmd"]
    br = data.get("bridge", {})
    if "proxy_bin" in br:
        cfg.proxy_bin = br["proxy_bin"]
    if "proxy_args" in br:
        cfg.proxy_args = list(br["proxy_args"])
    up = data.get("upstreams", {})
    if "registry" in up:
        cfg.registry = up["registry"]
    if "extra" in up:
        cfg.extra = up["extra"]


def load_config() -> GatewayConfig:
    cfg = GatewayConfig()
    for f in _config_files():
        if not f.exists():
            continue
        try:
            if f.suffix == ".json":
                _merge(cfg, json.loads(f.read_text() or "{}"))
            elif tomllib is not None:
                _merge(cfg, tomllib.loads(f.read_text()))
        except (OSError, ValueError):
            continue
    return cfg
