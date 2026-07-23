"""INTEGRITY — don't self-corrupt (CISO, integrity wing).

The autoupdater flips the version-path of Claude.app / the ``claude`` CLI; that
churn is the root of the "Claude app is corrupt" dialog and recurring TCC/Gatekeeper
prompts. The lever (``DISABLE_AUTOUPDATER=1``) existed but was ungoverned. This
organ governs it: verify the operating binaries' signatures each beat and alert on
drift instead of letting Gatekeeper interrupt. Read-only + fail-open.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import params

_TRUE = ("1", "true", "yes", "on")


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


def autoupdater_disabled() -> bool:
    """True if the documented lever (DISABLE_AUTOUPDATER) is set truthy."""
    return str(os.environ.get("DISABLE_AUTOUPDATER", "")).lower() in _TRUE


def assess(results: list[dict], intended_disabled: bool, actually_disabled: bool) -> bool:
    """drift = any verified-invalid signature, or the autoupdater isn't in its intended state."""
    sig_drift = any(r.get("valid") is False for r in results)
    lever_drift = intended_disabled and not actually_disabled
    return bool(sig_drift or lever_drift)


def check() -> dict:
    targets = params.get(
        "INTEGRITY_VERIFY_TARGETS",
        ["/Applications/Claude.app", "~/.local/bin/claude"],
    )
    results = [verify_target(t) for t in _as_list(targets)]
    intended = str(params.get("INTEGRITY_AUTOUPDATER", "disabled")).lower() == "disabled"
    actual = autoupdater_disabled()
    drift = assess(results, intended, actual)
    return {
        "organ": "integrity",
        "targets": results,
        "autoupdater_intended": "disabled" if intended else "enabled",
        "autoupdater_actual": "disabled" if actual else "enabled",
        "drift": drift,
        "status": "drift" if drift else "ok",
    }
