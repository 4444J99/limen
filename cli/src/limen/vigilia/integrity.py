"""INTEGRITY — don't self-corrupt (CISO, integrity wing).

Managed executables are expected to update. Protected access is routed through
the fixed native Domus responsibility host so a Claude, Python, Homebrew, uv, or
Limen version rotation does not become a new TCC principal. This organ verifies
signatures and fails when an update-disabling control reappears. Read-only.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


from . import params

TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
UPDATE_DISABLE_KEYS = (
    "DISABLE_AUTOUPDATER",
    "DISABLE_UPDATES",
    "HOMEBREW_NO_AUTO_UPDATE",
)


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    # env override arrives as a string: split on os.pathsep or comma.
    sep = os.pathsep if os.pathsep in text else ","
    return [part.strip() for part in text.split(sep) if part.strip()]


def verify_target(target: str) -> dict:
    """codesign --verify one path. valid: True/False, or None if unknown/missing."""
    p = Path(target).expanduser()
    if not p.exists():
        return {"target": str(p), "exists": False, "valid": None}
    try:
        out = subprocess.run(
            ["codesign", "--verify", str(p)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "target": str(p),
            "exists": True,
            "valid": out.returncode == 0,
            "detail": (out.stderr or "").strip()[:200],
        }
    except Exception as exc:
        return {"target": str(p), "exists": True, "valid": None, "detail": str(exc)[:200]}


def disabled_update_controls() -> list[str]:
    """Return update-disabling environment controls that are currently active."""
    return [key for key in UPDATE_DISABLE_KEYS if str(os.environ.get(key, "")).strip().lower() in TRUE_VALUES]


def assess(
    results: list[dict],
    intended_enabled: bool,
    disabled_controls: list[str],
) -> bool:
    """Drift is an invalid signature, disabled update path, or stale policy."""
    sig_drift = any(r.get("valid") is False for r in results)
    required_drift = any(
        r.get("required") is True and (r.get("exists") is not True or r.get("valid") is not True) for r in results
    )
    update_drift = not intended_enabled or bool(disabled_controls)
    return bool(sig_drift or required_drift or update_drift)


def check(*, platform_name: str | None = None) -> dict:
    observed_platform = platform.system() if platform_name is None else platform_name
    require_agent_host = observed_platform == "Darwin"
    targets = params.get(
        "INTEGRITY_VERIFY_TARGETS",
        ["/Applications/Claude.app", "~/.local/bin/claude"],
    )
    host_executable = Path(
        str(
            params.get(
                "LIMEN_AGENT_HOST_BIN",
                "~/Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost",
            )
        )
    ).expanduser()
    if host_executable.parent.name == "MacOS" and host_executable.parent.parent.name == "Contents":
        required_host = host_executable.parents[2]
    else:
        required_host = host_executable
    required_path = str(required_host)
    target_values = _as_list(targets)
    if require_agent_host and required_path not in {str(Path(target).expanduser()) for target in target_values}:
        target_values.append(required_path)
    results = [verify_target(target) for target in target_values]
    for result in results:
        result["required"] = require_agent_host and result.get("target") == required_path
    intended = str(params.get("INTEGRITY_AUTOUPDATER", "enabled")).lower() == "enabled"
    disabled = disabled_update_controls()
    drift = assess(results, intended, disabled)
    return {
        "organ": "integrity",
        "platform": observed_platform,
        "targets": results,
        "autoupdater_intended": "enabled" if intended else "disabled",
        "autoupdater_actual": "disabled" if disabled else "enabled",
        "update_disable_controls": disabled,
        "drift": drift,
        "status": "drift" if drift else "ok",
    }
