#!/usr/bin/env python3
"""Hermetic test for scripts/dependabot-security-guard.py — no network.

Exercises: enumeration (env override, limen excluded), observe → on/off/unknown mapping, drift
detection, --check exit codes, dark-by-default, the armed path enabling ONLY drifted repos (never
already-ON, never disabling), the repo cap, and fail-open on unknown.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "dependabot-security-guard.py"
SPEC = importlib.util.spec_from_file_location("dependabot_security_guard", SOURCE)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


# --- 1. discover: env override wins, limen excluded ---
os.environ["LIMEN_DEPENDABOT_GUARD_REPOS"] = "organvm/a:organvm/b:organvm/limen"
try:
    assert m.discover_repos() == ["organvm/a", "organvm/b"], m.discover_repos()
finally:
    del os.environ["LIMEN_DEPENDABOT_GUARD_REPOS"]


# --- fake gh keyed on a per-repo posture map ---
def make_fake_gh(posture: dict, calls: list):
    def fake_gh(args, timeout=60):
        calls.append(list(args))
        # observe: security-updates status
        if args[:1] == ["api"] and len(args) >= 2 and args[1].startswith("/repos/") and "--jq" in args:
            repo = args[1][len("/repos/"):]
            sec = posture.get(repo, {}).get("security_updates", "unknown")
            val = {"on": "enabled", "off": "disabled"}.get(sec, "")
            return subprocess.CompletedProcess(args, 0, val, "")
        # observe: vulnerability-alerts (204 on / 404 off)
        if args[:1] == ["api"] and len(args) >= 2 and args[1].endswith("/vulnerability-alerts") and "-X" not in args:
            repo = args[1][len("/repos/"):-len("/vulnerability-alerts")]
            al = posture.get(repo, {}).get("alerts", "unknown")
            if al == "on":
                return subprocess.CompletedProcess(args, 0, "", "")
            if al == "off":
                return subprocess.CompletedProcess(args, 1, "", "HTTP 404: Not Found")
            return subprocess.CompletedProcess(args, 1, "", "timeout")  # unknown
        # enable actions
        return subprocess.CompletedProcess(args, 0, "", "")
    return fake_gh


def enabled_repos(calls: list) -> list:
    """Repos the guard called ENABLE on. enable() uses `gh api -X PUT /repos/<r>/automated-security-fixes`
    (gh repo edit has NO --enable-automated-security-fixes flag — verified empirically 2026-07-22)."""
    out = []
    for c in calls:
        if c[:1] == ["api"] and "PUT" in c and c[-1].endswith("/automated-security-fixes"):
            out.append(c[-1][len("/repos/"):-len("/automated-security-fixes")])
    return sorted(out)


# --- 2/3/4. observe mapping + drift + --check exit codes ---
posture = {
    "organvm/a": {"security_updates": "on", "alerts": "on"},     # clean
    "organvm/b": {"security_updates": "off", "alerts": "on"},    # DRIFT (fixes off)
    "organvm/c": {"security_updates": "on", "alerts": "off"},    # DRIFT (alerts off)
    "organvm/d": {"security_updates": "unknown", "alerts": "unknown"},  # blip → NOT drift
}
calls: list = []
_orig = m._gh
try:
    m._gh = make_fake_gh(posture, calls)
    os.environ["LIMEN_DEPENDABOT_GUARD_REPOS"] = "organvm/a:organvm/b:organvm/c:organvm/d"

    # observe mapping
    assert m.observe("organvm/a") == {"repo": "organvm/a", "security_updates": "on", "alerts": "on"}
    assert m.is_drifted(m.observe("organvm/b")) is True
    assert m.is_drifted(m.observe("organvm/c")) is True
    assert m.is_drifted(m.observe("organvm/d")) is False  # unknown is fail-open, not drift

    # --check (unarmed): exit 1 (b + c drift), and NO write actions (repo edit / PUT)
    calls.clear()
    rc = m.run(apply=False, as_json=True)
    assert rc == 1
    writes = [c for c in calls if c[:2] == ["repo", "edit"] or (c[:1] == ["api"] and "-X" in c and "PUT" in c)]
    assert writes == [], f"dark run must not write, got {writes}"
finally:
    m._gh = _orig
    os.environ.pop("LIMEN_DEPENDABOT_GUARD_REPOS", None)

# --- 5. armed: enable ONLY the drifted repos, never already-ON, never disable ---
calls = []
try:
    m._gh = make_fake_gh(posture, calls)
    os.environ["LIMEN_DEPENDABOT_GUARD_REPOS"] = "organvm/a:organvm/b:organvm/c:organvm/d"
    os.environ[m.APPLY_ENV] = "1"
    m.run(apply=True, as_json=True)
    assert enabled_repos(calls) == ["organvm/b", "organvm/c"], enabled_repos(calls)  # only drifted, not a/d
    # never a disable: only PUT (enable) endpoints are used — never DELETE, never a --disable flag
    assert not any("DELETE" in c for c in calls)
    assert not any("--disable" in " ".join(c) for c in calls)
finally:
    m._gh = _orig
    os.environ.pop("LIMEN_DEPENDABOT_GUARD_REPOS", None)
    os.environ.pop(m.APPLY_ENV, None)

# --- 6. all-clean → exit 0, no writes ---
clean = {"organvm/a": {"security_updates": "on", "alerts": "on"}}
calls = []
try:
    m._gh = make_fake_gh(clean, calls)
    os.environ["LIMEN_DEPENDABOT_GUARD_REPOS"] = "organvm/a"
    os.environ[m.APPLY_ENV] = "1"
    rc = m.run(apply=True, as_json=False)
    assert rc == 0
    assert enabled_repos(calls) == [], "no writes when all clean"
finally:
    m._gh = _orig
    os.environ.pop("LIMEN_DEPENDABOT_GUARD_REPOS", None)
    os.environ.pop(m.APPLY_ENV, None)

# --- 7. cap respected ---
many = {f"organvm/r{i}": {"security_updates": "off", "alerts": "on"} for i in range(5)}
calls = []
try:
    m._gh = make_fake_gh(many, calls)
    os.environ["LIMEN_DEPENDABOT_GUARD_REPOS"] = ":".join(many)
    os.environ[m.APPLY_ENV] = "1"
    m.DEFAULT_CAP = 2
    m.run(apply=True, as_json=True)
    assert len(enabled_repos(calls)) == 2, f"cap=2 → 2 enables, got {len(enabled_repos(calls))}"
finally:
    m._gh = _orig
    os.environ.pop("LIMEN_DEPENDABOT_GUARD_REPOS", None)
    os.environ.pop(m.APPLY_ENV, None)

print("PASS: dependabot-security-guard.test.py")
