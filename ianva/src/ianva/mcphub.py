"""Backend supervisor: materialize the aggregator's settings, start/stop/status it.

ianva's primary backend is MCPHub — it implements the full upstream OAuth 2.1 client flow
(Authorization-Code+PKCE, WWW-Authenticate/RFC8414 discovery, DCR/RFC7591, resource
indicators/RFC8707) AND persistent auto-refresh, writing rotated tokens back to its settings
so they survive restarts. That is the hard part we deliberately wrap instead of rebuild.

ianva owns the settings file (materialized from the normalized upstream set) and supervises
the process. The backend command itself is a config knob (config.backend_cmd) because the
exact flags are version-specific and must be verified, not assumed.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from pathlib import Path

from . import creds, paths
from .config import GatewayConfig
from .preflight import reachable
from .upstreams import Upstream

PIDFILE = paths.RUN_DIR / "backend.pid"
LOGFILE = paths.LOG_DIR / "backend.log"


def materialize_settings(upstreams: list[Upstream], path: Path | None = None, bearer: str | None = None) -> Path:
    """Write the aggregator settings (MCPHub mcp_settings shape) from ianva's upstream set.

    Bearer policy is ALWAYS written explicitly, because MCPHub defaults
    `routing.enableBearerAuth` to **true** when the key is absent (verified in its
    sseService.js / auth.js: `systemConfig?.routing?.enableBearerAuth ?? true`). So an omitted
    systemConfig does NOT mean "open" — it means the global /mcp route demands a bearer and every
    agent gets 401. Therefore:
      * bearer given (cloud face)  -> enableBearerAuth:true + bearerKeys:[bearer]  (must present it)
      * no bearer (loopback local) -> enableBearerAuth:false                        (open on 127.0.0.1)"""
    path = path or paths.MCPHUB_SETTINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    servers: dict[str, dict] = {}
    for u in upstreams:
        if u.is_remote():
            entry: dict = {"type": "sse" if u.transport == "sse" else "streamable-http", "url": u.url}
            if u.headers:
                entry["headers"] = u.headers
        else:
            entry = {"command": u.command, "args": u.args}
            if u.env:
                entry["env"] = u.env
        entry["enabled"] = u.enabled
        if u.group and u.group != "default":
            entry["group"] = u.group
        servers[u.name] = entry
    settings: dict = {"mcpServers": servers}
    routing = {"enableBearerAuth": True, "bearerKeys": [bearer]} if bearer else {"enableBearerAuth": False}
    settings["systemConfig"] = {"routing": routing}
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path


def _read_pid() -> int | None:
    try:
        return int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start(cfg: GatewayConfig, settings_path: Path) -> tuple[bool, str]:
    paths.ensure_dirs()
    pid = _read_pid()
    if pid and _alive(pid):
        return True, f"backend already running (pid {pid})"
    argv = cfg.backend_argv(settings_path)
    # sanitize_child_env strips CLAUDE_CODE_OAUTH_TOKEN (#37512) and applies the fleet auth
    # precedence (LIMEN_CLAUDE_* -> ANTHROPIC_*), so the backend never touches the Keychain.
    env = creds.sanitize_child_env(fleet_claude=True)
    env.setdefault("PORT", str(cfg.port))
    # Robust settings discovery — MCPHub honors MCPHUB_SETTING_PATH before its fragile cwd fallback.
    env["MCPHUB_SETTING_PATH"] = str(settings_path)
    try:
        log = open(LOGFILE, "ab")
    except OSError:
        log = subprocess.DEVNULL  # type: ignore
    try:
        proc = subprocess.Popen(
            argv,
            env=env,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            cwd=str(paths.IANVA_HOME),
            start_new_session=True,  # MCPHub finds mcp_settings.json here
        )
    except FileNotFoundError:
        if hasattr(log, "close"):
            log.close()  # close the log fd opened above; else it leaks on every missing-binary attempt
        return False, f"backend binary not found: {argv[0]!r} (set core.backend_cmd in ianva.toml)"
    PIDFILE.write_text(str(proc.pid))
    return True, f"started backend: {' '.join(argv)} (pid {proc.pid}, log {LOGFILE})"


def stop(cfg: GatewayConfig) -> str:
    pid = _read_pid()
    if not pid:
        return "no backend pidfile"
    if not _alive(pid):
        PIDFILE.unlink(missing_ok=True)
        return f"backend pid {pid} was not running"
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    PIDFILE.unlink(missing_ok=True)
    return f"stopped backend (pid {pid})"


def status(cfg: GatewayConfig) -> dict:
    pid = _read_pid()
    pid_alive = bool(pid and _alive(pid))
    endpoint_reachable = reachable(cfg.host, cfg.port, timeout=1.5)
    return {
        "pid": pid,
        "pid_alive": pid_alive,
        "pidfile_state": "tracked" if pid_alive else ("stale" if pid else "missing"),
        # launchd owns the foreground backend without going through ``ianva up``.
        # A reachable endpoint is therefore running truth even when an old
        # interactive pidfile remains after the custody transition.
        "running": pid_alive or endpoint_reachable,
        "endpoint": f"http://{cfg.host}:{cfg.port}{cfg.path}",
        "endpoint_reachable": endpoint_reachable,
        "settings": str(paths.MCPHUB_SETTINGS),
        "log": str(LOGFILE),
    }
