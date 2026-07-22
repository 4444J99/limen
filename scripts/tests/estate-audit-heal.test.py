#!/usr/bin/env python3
"""Hermetic test for scripts/estate-audit-heal.py — no network, no real npm/pnpm/gh/git.

Exercises the load-bearing invariants: the verify-gated Tier-1/Tier-2 split, estate enumeration +
skip, pnpm advisory-schema parsing, the per-run repo cap, dry-run makes no writes, fail-open, and
the NO-AUTO-MERGE safety property (armed path calls `gh pr create` but never `gh pr merge`).
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "estate-audit-heal.py"
SPEC = importlib.util.spec_from_file_location("estate_audit_heal", SOURCE)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def _adv(name, rng="<9.9.9", sev="high"):
    return {"name": name, "severity": sev, "range": rng, "fixable": True, "urls": []}


# --- 1. heal_project verify-gate: cleared → Tier-1, persistent → Tier-2 ---
class FakeStrategy:
    name = "fake"

    def __init__(self, before, after):
        self._seq = [before, after]
        self._i = 0

    def high_advisories(self, d):
        r = self._seq[min(self._i, len(self._seq) - 1)]
        self._i += 1
        return r

    def derive(self, adv):
        return {"name": adv["name"], "pin": ">=1.0.0 <2.0.0", "disposition": "auto"}

    def apply(self, d, pins):
        pass

    def snapshot_overrides(self, d):
        return {}


_orig_strategy_for = m.strategy_for
try:
    # sharp clears after apply; js-yaml persists (Tier-2 → Dependabot)
    m.strategy_for = lambda d: FakeStrategy(before=[_adv("sharp"), _adv("js-yaml")], after=[_adv("js-yaml")])
    res = m.heal_project(Path("/fake/repo"))
    assert res["tier1"] == {"sharp": ">=1.0.0 <2.0.0"}, res["tier1"]
    assert res["tier2"] == ["js-yaml"], res["tier2"]
    assert res["changed"] is True and res["clean"] is False, res
finally:
    m.strategy_for = _orig_strategy_for

# --- 1b. all-clear: nothing persists → clean, no Tier-2 ---
try:
    m.strategy_for = lambda d: FakeStrategy(before=[_adv("sharp")], after=[])
    res = m.heal_project(Path("/fake/repo"))
    assert res["tier1"] == {"sharp": ">=1.0.0 <2.0.0"} and res["tier2"] == [] and res["clean"] is True, res
finally:
    m.strategy_for = _orig_strategy_for

# --- 1c. no lockfile → strategy None → clean no-op ---
try:
    m.strategy_for = lambda d: None
    res = m.heal_project(Path("/fake/repo"))
    assert res["changed"] is False and res["clean"] is True, res
finally:
    m.strategy_for = _orig_strategy_for

# --- 2. enumeration: env override wins, limen self-discarded ---
import os
os.environ["LIMEN_ESTATE_AUDIT_REPOS"] = "organvm/a:organvm/b:organvm/limen"
try:
    repos = m.discover_audit_repos()
    assert repos == ["organvm/a", "organvm/b"], repos  # limen discarded (heals locally)
finally:
    del os.environ["LIMEN_ESTATE_AUDIT_REPOS"]

# --- 2b. estate skip: repo_overrides class archived/frozen is excluded ---
skip = m._skip_repos({"repo_overrides": {"organvm/old": {"class": "archived"}, "organvm/x": {"class": "governed_public"}}})
assert skip == {"organvm/old"}, skip

# --- 3. PnpmStrategy parses the pnpm `advisories` schema → normalized shape ---
pnpm = m.PnpmStrategy()
pnpm._audit_json = lambda d: {"advisories": {
    "1": {"module_name": "js-yaml", "severity": "high", "vulnerable_versions": ">=4.0.0 <4.3.0",
          "patched_versions": ">=4.3.0", "url": "https://x"},
    "2": {"module_name": "lodash", "severity": "moderate", "vulnerable_versions": "<1.0.0",
          "patched_versions": ">=1.0.0"},  # moderate ignored
}}
advs = pnpm.high_advisories(Path("/x"))
assert [a["name"] for a in advs] == ["js-yaml"], advs
assert advs[0]["range"] == ">=4.0.0 <4.3.0" and advs[0]["fixable"] is True

# --- 4. per-run cap respected + NO-AUTO-MERGE on the armed path ---
calls = []


def fake_gh(args, timeout=60):
    calls.append(list(args))
    # default_branch / clone / pr create all "succeed"
    if args[:1] == ["api"]:
        return subprocess.CompletedProcess(args, 0, "main", "")
    return subprocess.CompletedProcess(args, 0, "", "")


def fake_git(cwd, *args, timeout=120):
    calls.append(["git", *args])
    return subprocess.CompletedProcess(args, 0, "", "")


_og, _ogit, _ohp, _opd = m._gh, m._bounded_git, m.heal_project, m._npm_project_dirs
try:
    m._gh = fake_gh
    m._bounded_git = fake_git
    m._npm_project_dirs = lambda root: [root]
    m.heal_project = lambda d: {"strategy": "npm", "tier1": {"sharp": ">=0.35.0 <1.0.0"},
                                "tier2": ["js-yaml"], "human": [], "clean": False, "changed": True}
    os.environ["LIMEN_ESTATE_AUDIT_REPOS"] = "organvm/a:organvm/b:organvm/c"
    os.environ[m.APPLY_ENV] = "1"
    m.DEFAULT_CAP = 2  # cap below the 3 discovered
    rc = m.run(apply=True, as_json=True)
    # exactly 2 repos processed (cap), each opened a PR, and NO `gh pr merge` ever issued
    pr_creates = [c for c in calls if c[:2] == ["pr", "create"]]
    pr_merges = [c for c in calls if c[:2] == ["pr", "merge"]]
    assert len(pr_creates) == 2, f"expected 2 PR creates (cap), got {len(pr_creates)}"
    assert pr_merges == [], f"NO auto-merge allowed, got {pr_merges}"
    assert rc == 1  # Tier-1 outstanding
finally:
    m._gh, m._bounded_git, m.heal_project, m._npm_project_dirs = _og, _ogit, _ohp, _opd
    os.environ.pop("LIMEN_ESTATE_AUDIT_REPOS", None)
    os.environ.pop(m.APPLY_ENV, None)

# --- 5. dry-run makes no writes (no gh/git mutations) ---
calls.clear()
_og2, _ohp2 = m._gh, m.heal_project
try:
    m._gh = fake_gh
    m._bounded_git = fake_git
    os.environ["LIMEN_ESTATE_AUDIT_REPOS"] = "organvm/a"
    # unarmed: heal_repo is called with apply=False → clones + heals but never branches/commits/PRs
    m.heal_project = lambda d: {"strategy": "npm", "tier1": {"sharp": ">=0.35.0 <1.0.0"},
                                "tier2": [], "human": [], "clean": False, "changed": True}
    m._npm_project_dirs = lambda root: [root]
    rc = m.run(apply=False, as_json=False)
    assert [c for c in calls if c[:2] == ["pr", "create"]] == [], "dry-run must not open PRs"
    assert [c for c in calls if c and c[0] == "git" and "push" in c] == [], "dry-run must not push"
finally:
    m._gh, m.heal_project = _og2, _ohp2
    os.environ.pop("LIMEN_ESTATE_AUDIT_REPOS", None)

print("PASS: estate-audit-heal.test.py")
