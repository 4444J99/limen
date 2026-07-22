#!/usr/bin/env python3
"""npm-audit autofix — the missing EFFECTOR for the trunk-green sensor's npm-audit case.

The gap this closes (2026-07-22): ``.github/workflows/ci.yml`` runs ``npm audit --audit-level=high``
as a HARD-FAIL step in the ``web`` (web/app) and ``worker`` (web/worker) jobs. When a new high/critical
advisory publishes against a **transitive** dep under a frozen lockfile, that step deterministically
reds and **jams the entire PR merge queue** until a human hand-pins an npm ``overrides`` fix. It just
happened with ``sharp <0.35.0`` (via next / wrangler→miniflare) and ``fast-uri 3.0.0-3.1.3`` (via ajv).

Renovate (bumps) and Dependabot (security-only) both exist here, but **neither authors ``overrides``** —
the only non-breaking fix for a transitive advisory whose parent has no in-range update. ``check-main-green.py``
DETECTS the resulting RED but has no effector for it. This organ is that effector: it computes the minimal
``overrides`` pin, regenerates the lockfile, verifies the advisory clears, and (when armed) opens a fix PR.

Design (mirrors scripts/check-main-green.py):
- **DETECT (always on):** ``--check`` runs ``npm audit --json`` per npm project, derives the pins, prints
  the proposed diff, exits non-zero when a high/critical advisory is present. Fail-open on missing npm.
- **FIX (dark until armed, ``LIMEN_NPM_AUDIT_AUTOFIX_APPLY=1``):** apply the pins, ``npm install
  --package-lock-only``, re-audit to 0 high/critical, and open a fix PR via the worktree→PR recipe from
  scripts/ship-docs.sh (mirrored inline — ship-docs refuses web/* paths by design). merge-policy.sh gates
  the merge: web/app is a deploy trigger → HOLD until CI green. CI (web build + worker check) is the net.
- **Breaking-major policy:** a fix npm marks ``isSemVerMajor`` is still pinned + PR'd, but as a DRAFT with
  no self-merge — surfaced for human review. A jammed queue is strictly worse than a pinned major that CI
  adjudicates on the fix PR alone. Non-major fixes take the armed auto-merge path.
- **No allow-list valve:** a time-boxed audit-ignore would let CI pass while the vuln is live+unpinned —
  a silent security regression. Resilience is fast auto-fix latency (aggressive beat cadence), not suppression.

pnpm repos (``pnpm.overrides``, different audit schema) are a v1 non-goal — the PackageManager seam is
left clean for a follow-up. ``npm_project_dirs`` already excludes them by keying on ``package-lock.json``.

Fail-open: no npm / offline / parse error → exit 0 (never breaks the beat).

  python3 scripts/npm-audit-autofix.py --check      # detect + print proposed overrides diff
  python3 scripts/npm-audit-autofix.py --json        # machine-readable plan
  python3 scripts/npm-audit-autofix.py --apply       # armed: apply + open fix PR (also needs the env lever)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
STAMP = ROOT / "logs" / "npm-audit-autofix.json"
HIGH_SEVERITIES = {"high", "critical"}
APPLY_ENV = "LIMEN_NPM_AUDIT_AUTOFIX_APPLY"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Project-dir derivation (mirrors check-gates.py: derive, don't hardcode)
# ---------------------------------------------------------------------------

def npm_project_dirs(root: Path) -> list[Path]:
    """npm projects = immediate web/* subdirs holding a package-lock.json (pnpm dirs excluded).

    Overridable via LIMEN_NPM_AUDIT_DIRS (colon-separated, relative-to-root or absolute) for tests.
    """
    override = os.environ.get("LIMEN_NPM_AUDIT_DIRS")
    if override:
        dirs = []
        for chunk in override.split(":"):
            chunk = chunk.strip()
            if not chunk:
                continue
            p = Path(chunk)
            p = p if p.is_absolute() else (root / p)
            if (p / "package-lock.json").is_file():
                dirs.append(p)
        return sorted(dirs)
    web = root / "web"
    if not web.is_dir():
        return []
    return sorted(d for d in web.iterdir() if d.is_dir() and (d / "package-lock.json").is_file())


# ---------------------------------------------------------------------------
# npm audit --json → advisories (pure parse)
# ---------------------------------------------------------------------------

def run_audit(project_dir: Path) -> dict | None:
    """Run `npm audit --json` in project_dir. npm exits non-zero when vulns exist — parse stdout
    regardless. Fail-open to None on missing npm / malformed JSON (never break the beat)."""
    try:
        proc = subprocess.run(
            ["npm", "audit", "--json"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    out = proc.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except (ValueError, json.JSONDecodeError):
        return None


def parse_advisories(audit_json: dict) -> list[dict]:
    """Pure. Extract high/critical, DIRECTLY-FLAWED vulnerabilities from an npm v7+ audit payload.

    Returns dicts: {name, severity, range, fixable, is_major, fix_version, urls}.
    `range` is the VULNERABLE version range for the package (used to derive the patched pin).

    Only LEAF advisories are returned. npm reports a package as vulnerable both when it is directly
    flawed (its `via` contains an advisory OBJECT/dict, e.g. sharp) AND when it merely depends on a
    flawed package (its `via` is a list of STRINGS naming the culprits, e.g. next→["sharp"]). Pinning
    the leaf (sharp) automatically clears every transitive parent, so pinning the parent is wrong (it
    would force a downgrade of a direct dep like next). We therefore keep only packages whose `via`
    holds ≥1 dict — the true leaves.
    """
    out: list[dict] = []
    vulns = (audit_json or {}).get("vulnerabilities") or {}
    if not isinstance(vulns, dict):
        return out
    for name, node in vulns.items():
        if not isinstance(node, dict):
            continue
        severity = str(node.get("severity", "")).lower()
        if severity not in HIGH_SEVERITIES:
            continue
        via = node.get("via") or []
        via = via if isinstance(via, list) else []
        # LEAF filter: skip packages vulnerable only transitively (via = strings only)
        if not any(isinstance(v, dict) for v in via):
            continue
        fix = node.get("fixAvailable", False)
        fixable = fix is not False  # False ⟺ no patched version exists at all
        urls = [v["url"] for v in via if isinstance(v, dict) and v.get("url")]
        out.append({
            "name": name,
            "severity": severity,
            "range": str(node.get("range", "")),
            "fixable": fixable,
            "urls": urls,
        })
    return out


# ---------------------------------------------------------------------------
# Patched-pin derivation (vendored narrow semver-bound parser — no npm dep)
# ---------------------------------------------------------------------------

_VER = r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?"


def _core(v: str) -> tuple[int, int, int] | None:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _next_patch(v: str) -> str | None:
    c = _core(v)
    if c is None:
        return None
    return f"{c[0]}.{c[1]}.{c[2] + 1}"


def patched_pin(range_str: str) -> str | None:
    """Derive a safe npm `overrides` pin from an advisory's VULNERABLE range.

    Rule: pin `>=<patched-floor> <<major(floor)+1>.0.0` — patch forward but STAY WITHIN the patched
    floor's major line, so forcing the transitive can't cross a major and break its parent (the fast-uri
    case: a bare `>3.1.3` would pull 4.x and break ajv's ^3.0.1; capping to `<4.0.0` keeps it in 3.x).

    Narrow grammar npm emits: `<x`, `<=x`, `>=a <b`, `a - b`, bare/`=x`. Returns None if unparseable.
    Limits: heuristic. Assumes the next-patch floor is published (npm resolves to the next available ≥ floor).
    """
    s = (range_str or "").strip()
    floor: str | None = None
    # `>=a <b`  → vulnerable below b; patched floor = b
    m = re.search(rf">=?\s*{_VER}\s*<\s*({_VER})", s)
    if m:
        floor = m.group(1)
    # `a - b`   → inclusive range; patched floor = next-patch(b)
    if floor is None:
        m = re.search(rf"({_VER})\s*-\s*({_VER})", s)
        if m:
            floor = _next_patch(m.group(2))
    # `<x`      → patched floor = x ; `<=x` → next-patch(x)
    if floor is None:
        m = re.match(rf"^<\s*({_VER})$", s)
        if m:
            floor = m.group(1)
    if floor is None:
        m = re.match(rf"^<=\s*({_VER})$", s)
        if m:
            floor = _next_patch(m.group(1))
    # bare `x` or `=x` (single vulnerable version) → next-patch(x)
    if floor is None:
        m = re.match(rf"^=?\s*({_VER})$", s)
        if m:
            floor = _next_patch(m.group(1))
    if floor is None:
        return None
    c = _core(floor)
    if c is None:
        return None
    return f">={floor} <{c[0] + 1}.0.0"


def derive_override(advisory: dict) -> dict:
    """Map one advisory → {name, pin, disposition}. disposition ∈ {auto, human}.

    - not fixable (fixAvailable:false, no patched version exists) or range unparseable → human (no pin).
    - otherwise → 'auto': pin the leaf forward via `patched_pin`, which caps WITHIN the leaf's major
      by construction (never a major leaf bump). CI on the isolated fix PR (merge-policy HOLDs web/app
      until green) adjudicates the rare case where forcing a leaf still breaks a parent — that reds only
      the fix PR, not the queue. (Leaf-major-crossing detection via the lockfile is a deliberate v1
      omission; the CI net makes it non-load-bearing.)
    """
    if not advisory.get("fixable"):
        return {"name": advisory["name"], "pin": None, "disposition": "human"}
    pin = patched_pin(advisory.get("range", ""))
    if pin is None:
        return {"name": advisory["name"], "pin": None, "disposition": "human"}
    return {"name": advisory["name"], "pin": pin, "disposition": "auto"}


def compute_plan(dirs: list[Path]) -> dict:
    """Aggregate a single-pass fix plan across projects (detection view — the armed path re-resolves
    with a loop to catch unmasked advisories). Returns:
    {projects: {dir_name: {dir, pins: {pkg: pin}, human: [pkg], advisories: n}}, has_human, audited}
    """
    plan: dict = {"projects": {}, "has_human": False, "audited": 0}
    for d in dirs:
        audit = run_audit(d)
        if audit is None:
            continue
        plan["audited"] += 1
        advisories = parse_advisories(audit)
        pins: dict[str, str] = {}
        human: list[str] = []
        for adv in advisories:
            ov = derive_override(adv)
            if ov["disposition"] == "human":
                human.append(ov["name"])
                plan["has_human"] = True
            else:
                pins[ov["name"]] = ov["pin"]
        if pins or human:
            plan["projects"][d.name] = {
                "dir": str(d),
                "pins": pins,
                "human": human,
                "advisories": len(advisories),
            }
    return plan


# ---------------------------------------------------------------------------
# Apply + verify (armed path)
# ---------------------------------------------------------------------------

def apply_overrides(project_dir: Path, pins: dict[str, str]) -> None:
    """Merge pins into package.json's `overrides` block (never clobber existing entries), then
    regenerate the lockfile with `npm install --package-lock-only`."""
    pkg_path = project_dir / "package.json"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    overrides = dict(pkg.get("overrides") or {})
    overrides.update(pins)
    pkg["overrides"] = overrides
    pkg_path.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")
    subprocess.run(
        ["npm", "install", "--package-lock-only"],
        cwd=str(project_dir), check=True, capture_output=True, text=True, timeout=300,
    )


def verify(project_dir: Path) -> bool:
    """Re-audit; True iff 0 high/critical advisories remain."""
    audit = run_audit(project_dir)
    if audit is None:
        return False
    return len(parse_advisories(audit)) == 0


def resolve_overrides(project_dir: Path, max_rounds: int = 6) -> dict:
    """Iteratively pin leaf advisories until the project audits clean, catching UNMASKED advisories.

    npm audit reports only the shallowest advisory, so fixing sharp can reveal fast-uri underneath.
    Each round: audit → derive leaf pins → if no NEW pin, stop → apply the accumulated set. Returns
    {pins, human, major, clean}. Applies changes to package.json/lockfile in project_dir (armed path only).
    """
    pins: dict[str, str] = {}
    human: set[str] = set()
    for _ in range(max_rounds):
        audit = run_audit(project_dir)
        if audit is None:
            break
        advisories = parse_advisories(audit)
        if not advisories:
            break  # clean
        new = False
        for adv in advisories:
            ov = derive_override(adv)
            if ov["disposition"] == "human":
                human.add(ov["name"])
                continue
            if pins.get(ov["name"]) != ov["pin"]:
                pins[ov["name"]] = ov["pin"]
                new = True
        if not new:
            break  # no further progress (remaining are human-flagged / unfixable)
        apply_overrides(project_dir, pins)
    return {"pins": pins, "human": sorted(human), "clean": verify(project_dir)}


# ---------------------------------------------------------------------------
# Throttle stamp (idempotence while a fix PR is already open)
# ---------------------------------------------------------------------------

def _plan_signature(plan: dict) -> str:
    parts = []
    for name in sorted(plan.get("projects", {})):
        proj = plan["projects"][name]
        parts.append(name + ":" + ",".join(f"{k}={v}" for k, v in sorted(proj["pins"].items())))
    return "|".join(parts)


def _read_stamp() -> dict:
    try:
        return json.loads(STAMP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_stamp(payload: dict) -> None:
    try:
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Fix PR (armed) — mirrors the scripts/ship-docs.sh worktree→PR→merge-policy recipe.
# ship-docs.sh itself REFUSES web/* paths (they're website-sensitive), so the recipe is
# replicated here where a web-touching automated PR is the honest home. merge-policy.sh
# still gates the merge (web/app → HOLD until CI green).
# ---------------------------------------------------------------------------

def open_fix_pr(root: Path, plan: dict) -> int:
    """Apply the plan in an isolated worktree cut from origin/main, open a PR, and (non-major only)
    self-merge via merge-policy.sh. Returns process exit code. Real git/gh/npm — armed path only."""
    stamp = _now().strftime("%Y%m%d%H%M%S")
    slug = "npm-audit-" + "-".join(sorted(
        p for proj in plan["projects"].values() for p in proj["pins"]
    ))[:60] or "npm-audit-fix"
    branch = f"fix/{slug}-{stamp}"
    wt_root = os.environ.get("LIMEN_WORKTREES") or str(Path.home() / "Workspace" / ".limen-worktrees")
    Path(wt_root).mkdir(parents=True, exist_ok=True)
    tmp = Path(wt_root) / f"npm-audit-autofix-{stamp}"

    def git(*args: str, cwd: Path = root) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)

    git("fetch", "origin", "main", "--quiet")
    git("worktree", "add", "--quiet", "-b", branch, str(tmp), "origin/main")
    try:
        # Re-resolve IN the worktree, looping per project until it audits clean (catches unmasked
        # advisories — sharp masks fast-uri until sharp is pinned). This is the authoritative pin set.
        touched: list[str] = []
        resolved: dict[str, dict] = {}
        for proj in plan["projects"].values():
            rel = Path(proj["dir"]).relative_to(root) if Path(proj["dir"]).is_absolute() else Path(proj["dir"])
            res = resolve_overrides(tmp / rel)
            if not res["pins"]:
                continue
            resolved[rel.name] = res
            touched.extend([str(rel / "package.json"), str(rel / "package-lock.json")])
        if not touched:
            print("npm-audit-autofix: nothing pinnable (all advisories are human-flagged/unfixable)")
            return 1
        git("add", "--", *touched, cwd=tmp)
        pins_desc = "; ".join(
            f"{name}: {', '.join(f'{k}{v}' for k, v in res['pins'].items())}"
            for name, res in resolved.items()
        )
        subprocess.run(
            ["git", "-C", str(tmp), "commit", "--quiet", "-m",
             f"fix: pin npm audit high-severity transitives via overrides\n\n{pins_desc}\n\n"
             "Auto-authored by scripts/npm-audit-autofix.py (dark-armed effector).\n\n"
             "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"],
            check=True, capture_output=True, text=True,
        )
        git("push", "--quiet", "-u", "origin", branch, cwd=tmp)
        body = (
            "Auto-authored by `scripts/npm-audit-autofix.py` — the npm-audit effector.\n\n"
            f"Pins (leaf advisories, capped within-major): {pins_desc}\n\n"
            "merge-policy gates the merge: web/app is a deploy trigger → HOLD until CI is green. "
            "If a forced pin breaks the build, CI reds THIS PR only (not the queue) for human review.\n"
        )
        pr_url = subprocess.run(
            ["gh", "pr", "create", "--title",
             "fix: clear npm audit high-severity advisories (overrides)", "--body", body],
            cwd=str(tmp), check=True, capture_output=True, text=True,
        ).stdout.strip()
        pr_num = pr_url.rstrip("/").split("/")[-1]
        print(f"npm-audit-autofix: opened PR #{pr_num} ({pr_url})")
        # merge-policy gates web/app (deploy-trigger) → HOLD until CI green; a broken pin never clears
        pol = subprocess.run([str(root / "scripts" / "merge-policy.sh"), pr_num], capture_output=True, text=True)
        if pol.returncode == 0:
            subprocess.run(["gh", "pr", "merge", pr_num, "--squash"], capture_output=True, text=True)
            print(f"  → merge-policy CLEARED; squash-merged #{pr_num}")
            return 0
        print(f"  → PR #{pr_num} left open (merge-policy exit {pol.returncode}: HOLD until CI green)")
        return 2
    finally:
        # Retain the worktree/branch for the reclaim/reap organs (ship-docs convention).
        print(f"npm-audit-autofix: retained worktree {tmp} + branch {branch} "
              "(cleanup → reclaim-worktrees.py / reap-branches.py)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_plan(plan: dict) -> None:
    if not plan["projects"]:
        print("npm-audit-autofix: no high/critical advisories in any npm project — clean")
        return
    for name, proj in sorted(plan["projects"].items()):
        for pkg, pin in sorted(proj["pins"].items()):
            print(f"  {name}: pin \"{pkg}\": \"{pin}\"")
        for pkg in sorted(proj["human"]):
            print(f"  {name}: {pkg} — NO clean fix (fixAvailable:false) → flag for human")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="npm-audit autofix effector")
    ap.add_argument("--check", action="store_true",
                    help="detection only — never act, even if armed (safe manual inspect)")
    ap.add_argument("--apply", action="store_true",
                    help="force the armed path for a manual run (bare invocation already acts if the env lever is set)")
    ap.add_argument("--json", action="store_true", help="emit the machine-readable plan")
    args = ap.parse_args(argv)

    dirs = npm_project_dirs(ROOT)
    if not dirs:
        print("npm-audit-autofix: no npm projects found — nothing to do")
        return 0

    plan = compute_plan(dirs)
    if plan["audited"] == 0:
        print("npm-audit-autofix: npm unavailable / no audit output — failing open")
        return 0

    if args.json:
        print(json.dumps(plan, indent=2, default=str))

    has_fix = any(proj["pins"] for proj in plan["projects"].values())
    has_any = bool(plan["projects"])

    # Arm on the env lever (mirrors check-main-green.py's LIMEN_MAIN_GREEN_APPLY): a BARE beat
    # invocation acts when the env is set; --apply forces it for a manual run; --check never acts.
    env_armed = os.environ.get(APPLY_ENV, "0").strip() == "1"
    armed = (env_armed or args.apply) and not args.check
    if armed and has_fix:
        # idempotence: same plan signature already handled recently → no-op
        sig = _plan_signature(plan)
        if _read_stamp().get("signature") == sig:
            print("npm-audit-autofix: identical fix plan already actioned (stamp) — no-op")
            return 0
        rc = open_fix_pr(ROOT, plan)
        _write_stamp({"signature": sig, "actioned_at": _now().isoformat(timespec="seconds"), "rc": rc})
        return 0 if rc == 0 else 1

    if not args.json:
        _print_plan(plan)
    if has_fix and not env_armed:
        print(f"npm-audit-autofix: fix available but DARK — set {APPLY_ENV}=1 to open the PR")

    # exit non-zero when a high/critical advisory is present (detection surfaces on the beat)
    return 1 if has_any else 0


if __name__ == "__main__":
    sys.exit(main())
