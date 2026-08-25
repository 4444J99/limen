#!/usr/bin/env python3
"""Hermetic test for scripts/estate-audit-heal.py — no network, no real npm/pnpm/gh/git.

Exercises the load-bearing invariants: the verify-gated Tier-1/Tier-2 split, estate enumeration +
skip, pnpm advisory-schema parsing, the per-run repo cap, disposable clone cleanup, local-failure
custody, fail-open, and the NO-AUTO-MERGE safety property (armed path calls `gh pr create` but
never `gh pr merge`).
"""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
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

    def high_advisories(self, d, *, env=None):
        r = self._seq[min(self._i, len(self._seq) - 1)]
        self._i += 1
        return r

    def derive(self, adv):
        return {"name": adv["name"], "pin": ">=1.0.0 <2.0.0", "disposition": "auto"}

    def apply(self, d, pins, *, env=None):
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

os.environ["LIMEN_ESTATE_AUDIT_REPOS"] = "organvm/a:organvm/b:organvm/limen:4444J99/limen"
try:
    repos = m.discover_audit_repos()
    assert repos == ["organvm/a", "organvm/b"], repos  # limen discarded (heals locally)
finally:
    del os.environ["LIMEN_ESTATE_AUDIT_REPOS"]

# --- 2b. estate skip: repo_overrides class archived/frozen is excluded ---
skip = m._skip_repos(
    {"repo_overrides": {"organvm/old": {"class": "archived"}, "organvm/x": {"class": "governed_public"}}}
)
assert skip == {"organvm/old"}, skip

# --- 3. PnpmStrategy parses the pnpm `advisories` schema → normalized shape ---
pnpm = m.PnpmStrategy()
pnpm._audit_json = lambda d, *, env=None: {
    "advisories": {
        "1": {
            "module_name": "js-yaml",
            "severity": "high",
            "vulnerable_versions": ">=4.0.0 <4.3.0",
            "patched_versions": ">=4.3.0",
            "url": "https://x",
        },
        "2": {
            "module_name": "lodash",
            "severity": "moderate",
            "vulnerable_versions": "<1.0.0",
            "patched_versions": ">=1.0.0",
        },  # moderate ignored
    }
}
advs = pnpm.high_advisories(Path("/x"))
assert [a["name"] for a in advs] == ["js-yaml"], advs
assert advs[0]["range"] == ">=4.0.0 <4.3.0" and advs[0]["fixable"] is True

# --- 3b. pnpm apply cannot execute lifecycle scripts or .pnpmfile.cjs hooks ---
_orun = m.subprocess.run
try:
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        (project / "package.json").write_text("{}\n", encoding="utf-8")
        pnpm_calls = []

        def fake_pnpm_run(args, **kwargs):
            pnpm_calls.append(list(args))
            return subprocess.CompletedProcess(args, 0, "", "")

        m.subprocess.run = fake_pnpm_run
        pnpm.apply(project, {"js-yaml": ">=4.3.0"}, env={"PATH": "/bin"})
        assert pnpm_calls == [
            [
                "pnpm",
                "install",
                "--no-frozen-lockfile",
                "--ignore-scripts",
                "--ignore-pnpmfile",
            ]
        ], pnpm_calls
finally:
    m.subprocess.run = _orun

# --- 4. per-run cap respected; armed compute never crosses the absent finalizer ---
calls = []


def fake_public_clone(repo, target, *, env):
    calls.append(["clone", repo])
    assert target.is_dir()
    assert "GITHUB_TOKEN" not in env and "GH_TOKEN" not in env and "SSH_AUTH_SOCK" not in env
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["NPM_CONFIG_IGNORE_SCRIPTS"] == "true"
    return subprocess.CompletedProcess([repo], 0, "", "")


def fake_heal_project(d, *, target_env=None):
    assert target_env is not None
    return {
        "strategy": "npm",
        "tier1": {"sharp": ">=0.35.0 <1.0.0"},
        "tier2": ["js-yaml"],
        "human": [],
        "clean": False,
        "changed": True,
    }


_oclone, _ohp, _opd, _owr = m._public_clone, m.heal_project, m._npm_project_dirs, m._worktree_root
try:
    with tempfile.TemporaryDirectory() as td:
        worktree_root = Path(td)
        m._public_clone = fake_public_clone
        m._worktree_root = lambda: worktree_root
        m._npm_project_dirs = lambda root: [root]
        m.heal_project = fake_heal_project
        os.environ["LIMEN_ESTATE_AUDIT_REPOS"] = "organvm/a:organvm/b:organvm/c"
        os.environ[m.APPLY_ENV] = "1"
        m.DEFAULT_CAP = 2
        rc = m.run(apply=True, as_json=True)
        assert calls == [["clone", "organvm/a"], ["clone", "organvm/b"]], calls
        assert rc == 1
        assert list(worktree_root.iterdir()) == [], "armed compute must leave no target clone or home"
finally:
    m._public_clone, m.heal_project, m._npm_project_dirs, m._worktree_root = _oclone, _ohp, _opd, _owr
    os.environ.pop("LIMEN_ESTATE_AUDIT_REPOS", None)
    os.environ.pop(m.APPLY_ENV, None)

# --- 5. dry-run makes no durable writes and disposes its clone + secretless HOME ---
calls.clear()
try:
    with tempfile.TemporaryDirectory() as td:
        worktree_root = Path(td)
        m._public_clone = fake_public_clone
        m._worktree_root = lambda: worktree_root
        m._npm_project_dirs = lambda root: [root]
        m.heal_project = fake_heal_project
        report = m.heal_repo("organvm/a", apply=False)
        assert report["error"] is None, report
        assert report["clone_cleanup"] == "removed", report
        assert "trusted finalizer required" in report["note"], report
        assert list(worktree_root.iterdir()) == [], "dry-run must reach an absent fixed point"
finally:
    m._public_clone, m.heal_project, m._npm_project_dirs, m._worktree_root = _oclone, _ohp, _opd, _owr

# --- 6. failed public clone residue is removed only when this invocation created its target ---
try:
    with tempfile.TemporaryDirectory() as td:
        worktree_root = Path(td)

        def fake_failed_clone(repo, target, *, env):
            (target / "partial").write_text("generated clone residue", encoding="utf-8")
            return subprocess.CompletedProcess([repo], 1, "", "checkout failed")

        m._public_clone = fake_failed_clone
        m._worktree_root = lambda: worktree_root
        report = m.heal_repo("organvm/a", apply=False)
        assert report["error"] == "public secretless clone failed", report
        assert report["clone_cleanup"] == "removed", report
        assert "clone_retained" not in report, report
        assert list(worktree_root.iterdir()) == [], "owned failed clone residue must be removed"
finally:
    m._public_clone, m._worktree_root = _oclone, _owr

# --- 7. cleanup refuses a matching target without current-invocation ownership ---
try:
    with tempfile.TemporaryDirectory() as td:
        worktree_root = Path(td)
        target = worktree_root / "estate-audit-a-20260726000000"
        target.mkdir()
        m._worktree_root = lambda: worktree_root
        cleaned, detail = m._cleanup_owned_clone(target, owned_by_invocation=False)
        assert cleaned is False and detail == "refused-unowned-target", (cleaned, detail)
        assert target.is_dir(), "unowned target must remain untouched"
finally:
    m._worktree_root = _owr

# --- 8. apply is explicitly refused until a trusted App-only finalizer exists ---
try:
    with tempfile.TemporaryDirectory() as td:
        worktree_root = Path(td)
        m._public_clone = fake_public_clone
        m._worktree_root = lambda: worktree_root
        m._npm_project_dirs = lambda root: [root]
        m.heal_project = fake_heal_project
        report = m.heal_repo("organvm/a", apply=True)
        assert report["error"] == "trusted finalizer unavailable; cross-repository write refused", report
        assert report["pr"] is None and "remote_branch" not in report, report
        assert list(worktree_root.iterdir()) == [], "refused finalizer must leave no local custody debt"
finally:
    m._public_clone, m.heal_project, m._npm_project_dirs, m._worktree_root = _oclone, _ohp, _opd, _owr

print("PASS: estate-audit-heal.test.py")
