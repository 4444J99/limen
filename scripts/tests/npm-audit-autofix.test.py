#!/usr/bin/env python3
"""Hermetic test for scripts/npm-audit-autofix.py — no network, no real npm.

Covers the pure core (advisory parse, patched-pin derivation, disposition policy, plan aggregation)
and the two subprocess-touching paths (apply merge-not-clobber, fail-open) via monkeypatch.
Mirrors scripts/tests/worktree-pr-receipts.test.py (importlib load + top-level assertions).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "npm-audit-autofix.py"
SPEC = importlib.util.spec_from_file_location("npm_audit_autofix", SOURCE)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


# --- 1. patched_pin: safe forward pin capped to the vulnerable major line ---
assert m.patched_pin("<0.35.0") == ">=0.35.0 <1.0.0", m.patched_pin("<0.35.0")
assert m.patched_pin("3.0.0 - 3.1.3") == ">=3.1.4 <4.0.0", m.patched_pin("3.0.0 - 3.1.3")
assert m.patched_pin(">=1.0.0 <1.2.3") == ">=1.2.3 <2.0.0", m.patched_pin(">=1.0.0 <1.2.3")
assert m.patched_pin("<=2.4.1") == ">=2.4.2 <3.0.0", m.patched_pin("<=2.4.1")
assert m.patched_pin("*") is None
assert m.patched_pin("") is None

# --- 2. parse_advisories + derive_override: the two REAL advisories from this incident ---
audit = {
    "vulnerabilities": {
        "sharp": {
            "name": "sharp", "severity": "high", "range": "<0.35.0",
            "via": [{"url": "https://github.com/advisories/GHSA-f88m-g3jw-g9cj"}],
            "fixAvailable": {"name": "next", "version": "14.2.35", "isSemVerMajor": False},
        },
        "fast-uri": {
            "name": "fast-uri", "severity": "high", "range": "3.0.0 - 3.1.3",
            "via": [{"url": "https://github.com/advisories/GHSA-v2hh-gcrm-f6hx"}],
            "fixAvailable": True,
        },
        "some-moderate": {  # must be ignored (below --audit-level=high)
            "name": "some-moderate", "severity": "moderate", "range": "<1.0.0", "fixAvailable": True,
        },
    }
}
advs = {a["name"]: a for a in m.parse_advisories(audit)}
assert set(advs) == {"sharp", "fast-uri"}, set(advs)  # moderate filtered out

sharp_ov = m.derive_override(advs["sharp"])
assert sharp_ov["pin"] == ">=0.35.0 <1.0.0" and sharp_ov["disposition"] == "auto", sharp_ov
fu_ov = m.derive_override(advs["fast-uri"])
assert fu_ov["pin"] == ">=3.1.4 <4.0.0" and fu_ov["disposition"] == "auto", fu_ov

# --- 3. fixAvailable:false → human (flag, no pin) ---
human = m.derive_override({"name": "stuck", "range": "<2.0.0", "fixable": False})
assert human["pin"] is None and human["disposition"] == "human", human

# --- 4. a leaf advisory pins within-major (auto); npm's parent-bump isSemVerMajor is irrelevant ---
leaf_adv = m.parse_advisories({"vulnerabilities": {
    "bigdep": {"name": "bigdep", "severity": "critical", "range": "<5.0.0",
               "via": [{"url": "https://example/advisory"}],
               "fixAvailable": {"name": "parent", "version": "1.0.0", "isSemVerMajor": True}}}})[0]
leaf_ov = m.derive_override(leaf_adv)
assert leaf_ov["pin"] == ">=5.0.0 <6.0.0" and leaf_ov["disposition"] == "auto", leaf_ov

# --- 4b. LEAF filter: a package vulnerable only transitively (via = strings) is skipped ---
transitive = m.parse_advisories({"vulnerabilities": {
    "sharp": {"name": "sharp", "severity": "high", "range": "<0.35.0",
              "via": [{"url": "https://advisory/sharp"}], "fixAvailable": True},
    "next": {"name": "next", "severity": "high", "range": "9.5.6 - 10.0.7 || 14.3.0 - 16.3.0",
             "via": ["sharp"], "fixAvailable": {"name": "next", "version": "14.2.35", "isSemVerMajor": True}},
}})
assert {a["name"] for a in transitive} == {"sharp"}, [a["name"] for a in transitive]  # next skipped

# --- 5. apply_overrides: MERGE into existing overrides, never clobber (npm install stubbed) ---
_real_run = m.subprocess.run
try:
    m.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "")
    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp)
        (pdir / "package.json").write_text(json.dumps(
            {"name": "x", "dependencies": {"next": "^16"}, "overrides": {"postcss": ">=8.5.10"}}), encoding="utf-8")
        m.apply_overrides(pdir, {"sharp": ">=0.35.0 <1.0.0"})
        got = json.loads((pdir / "package.json").read_text())["overrides"]
        assert got == {"postcss": ">=8.5.10", "sharp": ">=0.35.0 <1.0.0"}, got  # postcss preserved
finally:
    m.subprocess.run = _real_run

# --- 6. run_audit fail-open: npm absent → None, never raises ---
_real_run = m.subprocess.run
try:
    def _boom(*a, **k):
        raise FileNotFoundError("npm not installed")
    m.subprocess.run = _boom
    assert m.run_audit(Path("/nonexistent")) is None
finally:
    m.subprocess.run = _real_run

# --- 7. compute_plan aggregates + flags (run_audit stubbed per-dir) ---
_real_audit = m.run_audit
try:
    m.run_audit = lambda d: audit  # every dir returns the sharp+fast-uri payload
    plan = m.compute_plan([Path("/repo/web/app")])
    proj = plan["projects"]["app"]
    assert proj["pins"] == {"sharp": ">=0.35.0 <1.0.0", "fast-uri": ">=3.1.4 <4.0.0"}, proj["pins"]
    assert plan["has_human"] is False
finally:
    m.run_audit = _real_audit

# --- 8. resolve_overrides loops through the UNMASK: sharp masks fast-uri until pinned ---
def _adv(name, rng):
    return {"vulnerabilities": {name: {"name": name, "severity": "high", "range": rng,
                                       "via": [{"url": f"https://advisory/{name}"}], "fixAvailable": True}}}

_seq = [_adv("sharp", "<0.35.0"), _adv("fast-uri", "3.0.0 - 3.1.3"),
        {"vulnerabilities": {}}, {"vulnerabilities": {}}]
_real_audit, _real_apply = m.run_audit, m.apply_overrides
try:
    calls = iter(_seq)
    m.run_audit = lambda d: next(calls, {"vulnerabilities": {}})
    m.apply_overrides = lambda d, pins: None  # no real npm/file writes
    res = m.resolve_overrides(Path("/repo/web/worker"))
    assert res["pins"] == {"sharp": ">=0.35.0 <1.0.0", "fast-uri": ">=3.1.4 <4.0.0"}, res["pins"]
    assert res["clean"] is True and res["human"] == [], res
finally:
    m.run_audit, m.apply_overrides = _real_audit, _real_apply

print("PASS: npm-audit-autofix.test.py")
