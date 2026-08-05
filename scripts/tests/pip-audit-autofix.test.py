#!/usr/bin/env python3
"""Hermetic test for scripts/pip-audit-autofix.py — no network, no real pip-audit/uv/git.

Covers: (1) parse a canned `pip-audit --format=json` payload; (2) lowest_fix + derive_pin (minimal
forward bump; no-fix → human/Tier-2); (3) the requirements sanitizer (drops -e/local/ANSI); (4)
compute_plan split (pins vs human); (5) the verify-gate in resolve_pins (keeps only pins that clear;
a bump that never clears ends clean=False); (6) dark-by-default — --check never calls open_fix_pr.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "pip-audit-autofix.py"
SPEC = importlib.util.spec_from_file_location("pip_audit_autofix", SOURCE)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


# --- 1. parse_advisories ---
AUDIT = {"dependencies": [
    {"name": "cryptography", "version": "44.0.0", "vulns": [{"id": "GHSA-x", "fix_versions": ["48.0.1", "49.0.0"]}]},
    {"name": "starlette", "version": "1.2.0", "vulns": [{"id": "GHSA-y", "fix_versions": ["1.3.0"]}]},
    {"name": "somepkg", "version": "1.0.0", "vulns": [{"id": "GHSA-z", "fix_versions": []}]},  # no fix → human
    {"name": "safe", "version": "2.0.0", "vulns": []},  # no vulns → ignored
]}
advs = m.parse_advisories(AUDIT)
assert {a["name"] for a in advs} == {"cryptography", "starlette", "somepkg"}, advs
assert next(a for a in advs if a["name"] == "cryptography")["fixable"] is True
assert next(a for a in advs if a["name"] == "somepkg")["fixable"] is False

# --- 2. lowest_fix + derive_pin ---
assert m.lowest_fix(["49.0.0", "48.0.1"]) == "48.0.1"  # minimal forward bump
assert m.derive_pin({"name": "cryptography", "fixable": True, "fix_versions": ["48.0.1", "49.0.0"]}) \
    == {"name": "cryptography", "pin": ">=48.0.1", "disposition": "auto"}
assert m.derive_pin({"name": "somepkg", "fixable": False, "fix_versions": []})["disposition"] == "human"

# --- 3. sanitizer: drop -e/local/ANSI, keep real pins ---
raw = "\x1b[32m# comment\x1b[39m\n-e ../cli\nannotated-types==0.7.0\n./local\ngit+https://x\ncryptography==44.0.0\n"
san = m._sanitize_requirements(raw)
assert "annotated-types==0.7.0" in san and "cryptography==44.0.0" in san
assert "-e ../cli" not in san and "./local" not in san and "git+" not in san
assert "\x1b" not in san  # ANSI stripped

# --- 4/5. compute_plan + verify-gate via monkeypatched run_audit ---
_orig_audit, _orig_apply = m.run_audit, m.apply_pins

# compute_plan: one component with a fixable + a human advisory
try:
    m.run_audit = lambda comp: AUDIT
    m.python_components = lambda root: [Path("/x/cli")]
    plan = m.compute_plan([Path("/x/cli")])
    proj = plan["projects"]["cli"] if "cli" in plan["projects"] else next(iter(plan["projects"].values()))
    assert proj["pins"] == {"cryptography": ">=48.0.1", "starlette": ">=1.3.0"}, proj["pins"]
    assert proj["human"] == ["somepkg"], proj["human"]
    assert plan["has_human"] is True
finally:
    m.run_audit, m.apply_pins = _orig_audit, _orig_apply

# verify-gate: audit dirty then clean → pins kept, clean True
try:
    calls = {"n": 0}
    def audit_then_clean(comp):
        calls["n"] += 1
        return AUDIT if calls["n"] == 1 else {"dependencies": []}
    m.run_audit = audit_then_clean
    m.apply_pins = lambda comp, pins: None  # no real uv
    res = m.resolve_pins(Path("/x/cli"))
    assert res["pins"] == {"cryptography": ">=48.0.1", "starlette": ">=1.3.0"}, res
    assert res["clean"] is True
finally:
    m.run_audit, m.apply_pins = _orig_audit, _orig_apply

# verify-gate: audit NEVER clears (bump capped) → clean False (would be reclassified Tier-2)
try:
    m.run_audit = lambda comp: {"dependencies": [
        {"name": "capped", "version": "1.0.0", "vulns": [{"id": "G", "fix_versions": ["2.0.0"]}]}]}
    m.apply_pins = lambda comp, pins: None
    res = m.resolve_pins(Path("/x/cli"))
    assert res["clean"] is False, res  # never verified clean → not shippable, defers to Dependabot
finally:
    m.run_audit, m.apply_pins = _orig_audit, _orig_apply

# --- 6. dark-by-default: --check never calls open_fix_pr ---
_orig_pr, _orig_comps, _orig_plan = m.open_fix_pr, m.python_components, m.compute_plan
try:
    fired = {"pr": False}
    m.open_fix_pr = lambda root, plan: fired.__setitem__("pr", True) or 0
    m.python_components = lambda root: [Path("/x/cli")]
    m.compute_plan = lambda comps: {"projects": {"cli": {"dir": "/x/cli", "pins": {"a": ">=1"}, "human": [], "advisories": 1}},
                                     "has_human": False, "audited": 1}
    os.environ[m.APPLY_ENV] = "1"  # even armed, --check must not act
    rc = m.main(["--check"])
    assert fired["pr"] is False, "--check must never open a PR, even armed"
    assert rc == 1  # advisory present → non-zero detection
finally:
    m.open_fix_pr, m.python_components, m.compute_plan = _orig_pr, _orig_comps, _orig_plan
    os.environ.pop(m.APPLY_ENV, None)

print("PASS: pip-audit-autofix.test.py")
