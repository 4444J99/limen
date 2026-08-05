#!/usr/bin/env python3
"""Hermetic test for scripts/estate-audit-posture.py — no network, no subprocess to the real organs.

Covers: (1) probe parsing (guard JSON via a faked subprocess; stamps via faked _read_json);
(2) the health semantic — RED iff a Tier-2 owner is OFF, and Tier-1 'action' is telemetry not RED;
(3) fail-open — absent guard script / absent stamps → 'unknown', never RED; (4) exit codes.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "estate-audit-posture.py"
SPEC = importlib.util.spec_from_file_location("estate_audit_posture", SOURCE)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def fake_guard(stdout: str, exists: bool = True):
    def run(argv, capture_output=True, text=True, timeout=400):
        return subprocess.CompletedProcess(argv, 0, stdout, "")
    return run, exists


# --- 1. probe_tier2 parsing: drift vs clean vs absent ---
_orig_run, _orig_guard = m.subprocess.run, m.GUARD
try:
    # guard present, reports drift
    m.GUARD = SOURCE  # any existing path → .exists() True
    m.subprocess.run, _ = fake_guard('{"drifted": ["organvm/b"], "states": [1,2,3]}')
    t = m.probe_tier2()
    assert t["status"] == "drift" and t["drifted"] == ["organvm/b"], t

    # guard present, all clean
    m.subprocess.run, _ = fake_guard('{"drifted": [], "states": [1,2,3,4]}')
    t = m.probe_tier2()
    assert t["status"] == "clean" and t["repos"] == 4, t

    # guard script absent → unknown, fail-open
    m.GUARD = ROOT / "scripts" / "does-not-exist.py"
    t = m.probe_tier2()
    assert t["status"] == "unknown", t
finally:
    m.subprocess.run, m.GUARD = _orig_run, _orig_guard


# --- 2. probe_local / probe_estate stamp parsing (fake _read_json) ---
_orig_read = m._read_json
try:
    stamps = {
        m.STAMP_NPM: {"projects": {"app": {"pins": [{"sharp": ">=0.35 <1"}]}, "worker": {"pins": []}},
                      "generated": "2026-07-22T00:00:00Z"},
        m.STAMP_ESTATE: {"repos": [{"repo": "organvm/x", "tier1": 2}, {"repo": "organvm/y", "tier1": 0}],
                         "generated": "2026-07-22T00:00:00Z"},
    }
    m._read_json = lambda p: stamps.get(p)
    loc = m.probe_local()
    assert loc["status"] == "action" and "app" in loc["pins"], loc
    est = m.probe_estate()
    assert est["status"] == "action" and est["tier1_repos"] == ["organvm/x"], est

    # no stamps → unknown
    m._read_json = lambda p: None
    assert m.probe_local()["status"] == "unknown"
    assert m.probe_estate()["status"] == "unknown"
finally:
    m._read_json = _orig_read


# --- 3. composition + exit: RED iff Tier-2 drift; Tier-1 action is telemetry, not RED ---
_pt, _pl, _pe = m.probe_tier2, m.probe_local, m.probe_estate
try:
    # Tier-2 clean but Tier-1 action everywhere → HEALTHY (owned, not rot), exit 0
    m.probe_tier2 = lambda: {"status": "clean", "drifted": []}
    m.probe_local = lambda: {"status": "action", "pins": {"app": [1]}}
    m.probe_estate = lambda: {"status": "action", "tier1_repos": ["organvm/x"]}
    p = m.posture()
    assert p["healthy"] is True and p["advisories_pending"] is True, p
    assert m.run(as_json=False) == 0

    # Tier-2 DRIFT → UNHEALTHY, exit 1, even if Tier-1 is clean
    m.probe_tier2 = lambda: {"status": "drift", "drifted": ["organvm/b"]}
    m.probe_local = lambda: {"status": "clean", "pins": {}}
    m.probe_estate = lambda: {"status": "clean", "tier1_repos": []}
    p = m.posture()
    assert p["healthy"] is False, p
    assert m.run(as_json=True) == 1

    # Tier-2 unknown (fail-open) → HEALTHY (never RED on a blip), exit 0
    m.probe_tier2 = lambda: {"status": "unknown", "drifted": []}
    m.probe_local = lambda: {"status": "unknown"}
    m.probe_estate = lambda: {"status": "unknown"}
    assert m.posture()["healthy"] is True
    assert m.run(as_json=False) == 0
finally:
    m.probe_tier2, m.probe_local, m.probe_estate = _pt, _pl, _pe

print("PASS: estate-audit-posture.test.py")
