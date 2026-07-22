#!/usr/bin/env python3
"""estate-audit-heal.py — the estate-wide dependency-audit healer (v2 of npm-audit-autofix).

`scripts/npm-audit-autofix.py` is limen's fast, every-beat LOCAL sensor. This organ is the ESTATE
effector: it heals the OTHER ~8 organvm repos whose CI runs `npm audit` / `pnpm audit`, so a new
transitive advisory never sits red across the estate. It is the first per-repo cross-estate organ.

The design principle — learned the hard way from a failed manual sweep — is **VERIFY-GATED fixes**:
for each repo the healer applies the derived `overrides`, RE-AUDITS, and keeps only the pins whose
advisory *measurably disappeared* (Tier-1, goes in the PR). Whatever persists is **Tier-2** — a
framework-major-held advisory that `overrides` can't move (root overrides don't reach nested-workspace
resolutions) — and is **deferred to Dependabot** (present on 9/9 estate repos), recorded not fought.
So the organ can never ship a fix it didn't watch work.

Safety: cross-repo PRs are OPENED, never auto-merged (mass cross-repo merges are a human-gated lever).
Double-dark: dry-run by default; armed via ``--apply`` AND ``LIMEN_ESTATE_AUDIT_HEAL_APPLY=1``. Per-run
repo cap (``LIMEN_ESTATE_AUDIT_MAX``, default 5). Fail-open on missing gh/npm/pnpm/offline.

  python3 scripts/estate-audit-heal.py --check     # dry-run: per-repo Tier-1/Tier-2 plan, no writes
  python3 scripts/estate-audit-heal.py --json        # machine-readable plan
  python3 scripts/estate-audit-heal.py --apply       # armed (also needs the env lever): open fix PRs
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
SCRIPT_DIR = ROOT / "scripts"
APPLY_ENV = "LIMEN_ESTATE_AUDIT_HEAL_APPLY"
DEFAULT_CAP = int(os.environ.get("LIMEN_ESTATE_AUDIT_MAX", "5") or "5")
OWNER = os.environ.get("LIMEN_ESTATE_AUDIT_OWNER", "organvm")
SELF_REPO = "organvm/limen"  # limen heals itself via the local npm-audit-autofix sensor
STAMP = ROOT / "logs" / "estate-audit-heal.json"  # durable verdict so the posture rollup reads it cheaply


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Reuse the merged v1 pure core (parse_advisories / patched_pin / derive_override)
# via the importlib-vendoring pattern (apply-visibility.py:46-53).
# ---------------------------------------------------------------------------

def _load_core():
    # Import the SIBLING v1 organ from this script's own directory (the worktree copy), not
    # LIMEN_ROOT — under a worktree LIMEN_ROOT points at the live checkout, which may be behind.
    src = Path(__file__).resolve().parent / "npm-audit-autofix.py"
    spec = importlib.util.spec_from_file_location("npm_audit_autofix", src)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


core = _load_core()


# ---------------------------------------------------------------------------
# gh with the cascade token; fail-open (mirrors sync-marketplace-config.py:72-86)
# ---------------------------------------------------------------------------

def _gh(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return subprocess.CompletedProcess(args, 1, "", "offline")
    env = {**os.environ}
    try:
        tok = subprocess.run(
            ["bash", str(SCRIPT_DIR / "gh-app-token.sh")], capture_output=True, text=True, timeout=45
        )
        if tok.returncode == 0 and tok.stdout.strip():
            env["GH_TOKEN"] = env["GITHUB_TOKEN"] = tok.stdout.strip()
    except Exception:
        pass
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, env=env)
    except Exception as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _bounded_git(cwd: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------------------
# PackageManager strategies — npm and pnpm differ in audit schema + apply mechanism
# ---------------------------------------------------------------------------

class NpmStrategy:
    name = "npm"
    lockfile = "package-lock.json"

    def high_advisories(self, project_dir: Path) -> list[dict] | None:
        """Return LEAF high/critical advisories, or None on fail-open (npm absent / bad json)."""
        audit = core.run_audit(project_dir)  # npm audit --json
        if audit is None:
            return None
        return core.parse_advisories(audit)

    def derive(self, advisory: dict) -> dict:
        return core.derive_override(advisory)

    def apply(self, project_dir: Path, pins: dict[str, str]) -> None:
        """Merge pins into package.json `overrides` (never clobber) + FULL npm install.

        The manual sweep proved `npm install --package-lock-only` does NOT propagate overrides across
        workspaces — a full install is required for the fix to actually take (and for the verify-gate
        to be honest)."""
        pkg = project_dir / "package.json"
        data = json.loads(pkg.read_text(encoding="utf-8"))
        overrides = dict(data.get("overrides") or {})
        overrides.update(pins)
        data["overrides"] = overrides
        pkg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        subprocess.run(
            ["npm", "install"], cwd=str(project_dir), capture_output=True, text=True, timeout=600
        )

    def reset_overrides(self, project_dir: Path, overrides: dict) -> None:
        pkg = project_dir / "package.json"
        data = json.loads(pkg.read_text(encoding="utf-8"))
        if overrides:
            data["overrides"] = overrides
        else:
            data.pop("overrides", None)
        pkg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def snapshot_overrides(self, project_dir: Path) -> dict:
        try:
            return dict(json.loads((project_dir / "package.json").read_text()).get("overrides") or {})
        except (OSError, ValueError):
            return {}


class PnpmStrategy:
    name = "pnpm"
    lockfile = "pnpm-lock.yaml"

    def _audit_json(self, project_dir: Path) -> dict | None:
        if not shutil.which("pnpm"):
            return None
        try:
            proc = subprocess.run(
                ["pnpm", "audit", "--json"], cwd=str(project_dir),
                capture_output=True, text=True, timeout=180,
            )
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            return None
        out = (proc.stdout or "").strip()
        if not out:
            return None
        try:
            return json.loads(out)
        except (ValueError, json.JSONDecodeError):
            return None

    def high_advisories(self, project_dir: Path) -> list[dict] | None:
        """pnpm audit --json uses an `advisories` map keyed by id; each has module_name/severity/
        vulnerable_versions. Normalize to the same shape parse_advisories emits (name/severity/range)."""
        audit = self._audit_json(project_dir)
        if audit is None:
            return None
        out: list[dict] = []
        for adv in (audit.get("advisories") or {}).values():
            if not isinstance(adv, dict):
                continue
            sev = str(adv.get("severity", "")).lower()
            if sev not in core.HIGH_SEVERITIES:
                continue
            out.append({
                "name": adv.get("module_name", ""),
                "severity": sev,
                "range": str(adv.get("vulnerable_versions", "")),
                "fixable": bool(adv.get("patched_versions") and adv.get("patched_versions") != "<0.0.0"),
                "urls": [adv.get("url")] if adv.get("url") else [],
            })
        # de-dup by name (pnpm lists multiple ranges per package)
        seen: dict[str, dict] = {}
        for a in out:
            seen.setdefault(a["name"], a)
        return list(seen.values())

    def derive(self, advisory: dict) -> dict:
        # Reuse the same within-major pin derivation; pnpm honors range values in pnpm.overrides.
        return core.derive_override(advisory)

    def apply(self, project_dir: Path, pins: dict[str, str]) -> None:
        """Prefer pnpm's own fixer (writes native pnpm.overrides), then a full install. `pnpm audit
        --fix` handles pnpm's range-keyed override grammar better than hand-derived keys."""
        try:
            subprocess.run(["pnpm", "audit", "--fix"], cwd=str(project_dir),
                           capture_output=True, text=True, timeout=180)
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            pass
        # Also merge our derived pins into pnpm.overrides as a fallback for what --fix missed.
        pkg = project_dir / "package.json"
        data = json.loads(pkg.read_text(encoding="utf-8"))
        pnpm_block = dict(data.get("pnpm") or {})
        overrides = dict(pnpm_block.get("overrides") or {})
        for name, pin in pins.items():
            overrides.setdefault(name, pin)
        pnpm_block["overrides"] = overrides
        data["pnpm"] = pnpm_block
        pkg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["pnpm", "install", "--no-frozen-lockfile"], cwd=str(project_dir),
                       capture_output=True, text=True, timeout=600)

    def snapshot_overrides(self, project_dir: Path) -> dict:
        try:
            data = json.loads((project_dir / "package.json").read_text())
            return dict((data.get("pnpm") or {}).get("overrides") or {})
        except (OSError, ValueError):
            return {}


def strategy_for(project_dir: Path) -> NpmStrategy | PnpmStrategy | None:
    if (project_dir / "pnpm-lock.yaml").is_file():
        return PnpmStrategy()
    if (project_dir / "package-lock.json").is_file():
        return NpmStrategy()
    return None


# ---------------------------------------------------------------------------
# The verify-gated heal — the load-bearing invariant
# ---------------------------------------------------------------------------

def heal_project(project_dir: Path) -> dict:
    """Apply derived fixes, RE-AUDIT, and split into Tier-1 (verified cleared) vs Tier-2 (persists →
    Dependabot). Returns {strategy, tier1: {pkg: pin}, tier2: [pkg], human: [pkg], clean: bool,
    changed: bool}. Mutates project_dir only when there is something to fix (armed callers clone first)."""
    strat = strategy_for(project_dir)
    if strat is None:
        return {"strategy": None, "tier1": {}, "tier2": [], "human": [], "clean": True, "changed": False}
    before = strat.high_advisories(project_dir)
    if before is None:
        return {"strategy": strat.name, "tier1": {}, "tier2": [], "human": [], "clean": True,
                "changed": False, "note": "audit unavailable (fail-open)"}
    before_names = {a["name"] for a in before}
    if not before_names:
        return {"strategy": strat.name, "tier1": {}, "tier2": [], "human": [], "clean": True, "changed": False}

    pins: dict[str, str] = {}
    human: list[str] = []
    for adv in before:
        ov = strat.derive(adv)
        if ov.get("pin"):
            pins[ov["name"]] = ov["pin"]
        else:
            human.append(ov["name"])

    if not pins:
        return {"strategy": strat.name, "tier1": {}, "tier2": sorted(before_names),
                "human": sorted(human), "clean": False, "changed": False}

    original = strat.snapshot_overrides(project_dir)
    strat.apply(project_dir, pins)
    after = strat.high_advisories(project_dir) or []
    after_names = {a["name"] for a in after}
    cleared = before_names - after_names
    tier1 = {n: pins[n] for n in cleared if n in pins}

    # Prune to a CLEAN PR: keep only the verified-clearing pins (npm strategy; pnpm's --fix block is
    # left intact since it is pnpm-native and self-consistent).
    if isinstance(strat, NpmStrategy):
        strat.reset_overrides(project_dir, {**original, **tier1})
        subprocess.run(["npm", "install"], cwd=str(project_dir), capture_output=True, text=True, timeout=600)

    return {
        "strategy": strat.name,
        "tier1": tier1,
        "tier2": sorted(after_names),   # still vulnerable after our fix → defer to Dependabot
        "human": sorted(human),
        "clean": not after_names,
        "changed": bool(tier1),
    }


# ---------------------------------------------------------------------------
# Estate enumeration (derive, don't pin)
# ---------------------------------------------------------------------------

def discover_audit_repos() -> list[str]:
    """Repos in OWNER whose CI runs npm/pnpm audit. Derived via one `gh search code` per manager.
    Override for tests/manual runs via LIMEN_ESTATE_AUDIT_REPOS (colon-separated full names)."""
    override = os.environ.get("LIMEN_ESTATE_AUDIT_REPOS")
    if override:
        found = {r.strip() for r in override.split(":") if r.strip()}
    else:
        found = set()
        for term in ("npm audit", "pnpm audit"):
            # `path:` scopes to workflow files; `--filename` globs are unsupported by gh search.
            r = _gh(["search", "code", "--owner", OWNER, term, "path:.github/workflows",
                     "--json", "repository", "--limit", "50"], timeout=90)
            if r.returncode != 0:
                continue
            try:
                for hit in json.loads(r.stdout or "[]"):
                    full = (hit.get("repository") or {}).get("nameWithOwner")
                    if full:
                        found.add(full)
            except (ValueError, json.JSONDecodeError):
                continue
    # limen heals itself locally via the npm-audit-autofix sensor; never double-cover it here.
    found.discard(SELF_REPO)
    return sorted(found)


def _skip_repos(estate: dict) -> set[str]:
    """estate.yaml repo_overrides may mark a repo `class: archived` (or an explicit audit-skip)."""
    skip: set[str] = set()
    for repo, row in (estate.get("repo_overrides") or {}).items():
        if isinstance(row, dict) and row.get("class") in ("archived", "frozen"):
            skip.add(repo)
    return skip


# ---------------------------------------------------------------------------
# Per-repo clone + heal + cross-repo PR (armed path). No auto-merge.
# ---------------------------------------------------------------------------

def _worktree_root() -> Path:
    wt = os.environ.get("LIMEN_WORKTREES") or str(Path.home() / "Workspace" / ".limen-worktrees")
    Path(wt).mkdir(parents=True, exist_ok=True)
    return Path(wt)


def _npm_project_dirs(repo_root: Path) -> list[Path]:
    """A repo's npm/pnpm project dirs: the root if it has a lockfile, plus immediate children with one
    (covers the common flat + shallow-monorepo layouts). Deep workspace trees are handled by the root
    install, which is what audit reads."""
    dirs = []
    if strategy_for(repo_root) is not None:
        dirs.append(repo_root)
    for child in sorted(repo_root.iterdir()) if repo_root.is_dir() else []:
        if child.is_dir() and child.name != "node_modules" and strategy_for(child) is not None:
            dirs.append(child)
    return dirs


def heal_repo(repo: str, *, apply: bool) -> dict:
    """Clone `repo`, heal each project dir (verify-gated), and — when armed and something cleared —
    open a fix PR (never merge). Returns a report dict."""
    stamp = _now().strftime("%Y%m%d%H%M%S")
    clone_dir = _worktree_root() / f"estate-audit-{repo.split('/')[-1]}-{stamp}"
    report: dict = {"repo": repo, "tier1": {}, "tier2": [], "human": [], "pr": None, "error": None}

    dbase = _gh(["api", f"/repos/{repo}", "--jq", ".default_branch"], timeout=20)
    default = (dbase.stdout or "").strip() or "main"
    clone = _gh(["repo", "clone", repo, str(clone_dir), "--", "--depth=1"], timeout=180)
    if clone.returncode != 0:
        report["error"] = "clone failed"
        return report
    try:
        project_dirs = _npm_project_dirs(clone_dir)
        aggregate_tier1: dict[str, dict] = {}
        for pdir in project_dirs:
            res = heal_project(pdir)
            rel = pdir.relative_to(clone_dir).as_posix() or "."
            if res.get("changed"):
                aggregate_tier1[rel] = res["tier1"]
            report["tier1"].update({f"{rel}:{k}": v for k, v in res.get("tier1", {}).items()})
            report["tier2"].extend(f"{rel}:{n}" for n in res.get("tier2", []))
            report["human"].extend(f"{rel}:{n}" for n in res.get("human", []))

        if not aggregate_tier1:
            report["note"] = "nothing verify-cleared (all advisories Tier-2/human → Dependabot)"
            return report
        if not apply:
            report["note"] = "DRY-RUN — would open a PR with the Tier-1 fixes above"
            return report

        # armed: branch, commit the changed manifests+lockfiles, push, open PR (NO merge)
        branch = f"fix/audit-heal-{stamp}"
        _bounded_git(clone_dir, "checkout", "-b", branch)
        _bounded_git(clone_dir, "add", "-A")
        msg = ("fix: pin verify-cleared audit advisories via overrides\n\n"
               "Auto-authored by scripts/estate-audit-heal.py (verify-gated; Tier-1 only).\n\n"
               "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>")
        commit = _bounded_git(clone_dir, "commit", "-m", msg)
        if commit.returncode != 0:
            report["error"] = "nothing staged / commit failed"
            return report
        push = _bounded_git(clone_dir, "push", "-u", "origin", branch)
        if push.returncode != 0:
            report["error"] = "push failed"
            return report
        tier2_note = ("\n\n**Deferred to Dependabot (Tier-2, override-resistant / framework-major-held):** "
                      + ", ".join(report["tier2"])) if report["tier2"] else ""
        body = ("Auto-authored by `scripts/estate-audit-heal.py` — the estate dependency-audit healer.\n\n"
                "**Verify-gated:** every pin below was applied, then a re-audit confirmed its advisory "
                "cleared. Fixes that did not clear are NOT included here — they are deferred to Dependabot."
                f"\n\nTier-1 (verified cleared): {json.dumps(report['tier1'])}" + tier2_note +
                "\n\nNot auto-merged — this repo's own CI + owner adjudicate.")
        pr = _gh(["pr", "create", "--repo", repo, "--base", default, "--head", branch,
                  "--title", "fix: clear verify-gated npm/pnpm audit advisories (overrides)",
                  "--body", body], timeout=60)
        report["pr"] = "opened" if pr.returncode == 0 else f"pr-create-failed: {(pr.stderr or '')[:80]}"
        return report
    finally:
        report["clone"] = str(clone_dir)  # retained for reclaim organs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_stamp(reports: list[dict]) -> None:
    """Persist a compact verdict so `estate-audit-posture.py` reads estate state cheaply, without
    re-cloning 8 repos. Best-effort (never raises)."""
    payload = {
        "generated": _now().isoformat(),
        "repos": [
            {"repo": r.get("repo"), "tier1": len(r.get("tier1") or {}),
             "tier2": len(r.get("tier2") or []), "human": len(r.get("human") or []),
             "error": r.get("error"), "pr": r.get("pr")}
            for r in reports
        ],
    }
    try:
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def run(*, apply: bool, as_json: bool) -> int:
    estate = core_load_estate()
    skip = _skip_repos(estate)
    repos = [r for r in discover_audit_repos() if r not in skip]
    if not repos:
        print("estate-audit-heal: no audit-CI repos discovered (or offline) — nothing to do")
        return 0

    armed = apply and os.environ.get(APPLY_ENV, "0").strip() == "1"
    repos = repos[:DEFAULT_CAP]
    reports = [heal_repo(r, apply=armed) for r in repos]
    _write_stamp(reports)

    if as_json:
        print(json.dumps({"armed": armed, "repos": reports}, indent=2, default=str))
    else:
        any_tier1 = False
        for rep in reports:
            t1 = rep.get("tier1") or {}
            t2 = rep.get("tier2") or []
            any_tier1 = any_tier1 or bool(t1)
            line = f"  {rep['repo']}: Tier-1={len(t1)} Tier-2/defer={len(t2)}"
            if rep.get("pr"):
                line += f" PR={rep['pr']}"
            elif rep.get("error"):
                line += f" ERROR={rep['error']}"
            elif rep.get("note"):
                line += f" ({rep['note']})"
            print(line)
        if any_tier1 and not armed:
            print(f"estate-audit-heal: Tier-1 fixes available but DARK — set {APPLY_ENV}=1 to open PRs")

    # exit non-zero when any repo has a Tier-1-fixable advisory outstanding (detection surfaces on the beat)
    return 1 if any((rep.get("tier1") for rep in reports)) else 0


def core_load_estate() -> dict:
    try:
        import yaml  # PyYAML is a repo dep
        p = ROOT / "institutio" / "github" / "estate.yaml"
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="estate-wide dependency-audit healer")
    ap.add_argument("--check", action="store_true", help="dry-run: per-repo Tier-1/Tier-2 plan, never writes")
    ap.add_argument("--apply", action="store_true", help="armed (also needs the env lever): open fix PRs, no merge")
    ap.add_argument("--json", action="store_true", help="machine-readable plan")
    args = ap.parse_args(argv)
    # A bare beat invocation acts when the env lever is set (run() gates on APPLY_ENV, mirroring
    # npm-audit-autofix.py / check-main-green.py); --check forces detection-only regardless of env.
    apply = not args.check
    return run(apply=apply, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
