#!/usr/bin/env python3
"""pip-audit autofix — the Python tier of the estate dependency-audit model (mirrors npm-audit-autofix).

The gap this closes (2026-07-22): npm/pnpm advisories are owned end-to-end (npm-audit-autofix +
estate-audit-heal + a Dependabot guard), but limen's OWN CORE is mostly Python (`cli/`, `web/api/`,
`mcp/`) and **nothing audits its Python dependencies** — `.github/workflows/ci.yml` runs `npm audit`
but no `pip-audit`/`safety`. So the estate-audit-posture rollup over-reports "healthy" over an entirely
unscanned ecosystem. This organ is the Python Tier-1 local healer; the pip-audit CI gate is the detector;
the Tier-2 owner (Dependabot) already covers pip and is already guarded by dependabot-security-guard.

Design (mirrors scripts/npm-audit-autofix.py exactly, one ecosystem over):
- **DETECT (always on):** `--check` runs `pip-audit --no-deps -r <pinned-reqs> --format=json` per Python
  component, derives the minimal forward pin for each fixable advisory, prints the plan, exits non-zero
  when any advisory is present. Fail-open on missing pip-audit / offline / parse error (never break the beat).
- **FIX (dark until armed, `LIMEN_PIP_AUDIT_AUTOFIX_APPLY=1`):** apply the pin (uv components →
  `uv lock --upgrade-package`; plain requirements → rewrite the pin), RE-AUDIT to verify the advisory
  measurably cleared (verify-gated — like estate-audit-heal), and open a fix PR via the worktree→PR recipe.
  merge-policy gates the merge; the PR's own CI adjudicates. Whatever persists is deferred to Dependabot.
- **No severity filter:** pip-audit's JSON carries no severity field, so the criterion is simply "any
  advisory with `fix_versions` → Tier-1 pin; none available → Tier-2 (defer to Dependabot)."

pip-audit resolves an isolated env for unpinned inputs (slow); we audit the already-pinned lockfiles with
`--no-deps` (fast) — uv components are exported first. `ianva/` is stdlib-only by design → skipped.

  python3 scripts/pip-audit-autofix.py --check      # detect + print the proposed pins
  python3 scripts/pip-audit-autofix.py --json         # machine-readable plan
  python3 scripts/pip-audit-autofix.py --apply        # armed: apply + open fix PR (also needs the env lever)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
STAMP = ROOT / "logs" / "pip-audit-autofix.json"
APPLY_ENV = "LIMEN_PIP_AUDIT_AUTOFIX_APPLY"
# Python components with external deps. ianva/ is stdlib-only by design. Override via LIMEN_PIP_AUDIT_DIRS.
DEFAULT_COMPONENTS = ["cli", "web/api", "mcp"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Component derivation (mirrors npm_project_dirs: derive, don't hardcode)
# ---------------------------------------------------------------------------

def python_components(root: Path) -> list[Path]:
    """Python audit units = component dirs holding a requirements.txt OR a uv.lock (a pinned set we can
    audit fast). Overridable via LIMEN_PIP_AUDIT_DIRS (colon-separated, relative-to-root or absolute)."""
    override = os.environ.get("LIMEN_PIP_AUDIT_DIRS")
    names = [c.strip() for c in override.split(":")] if override else DEFAULT_COMPONENTS
    out = []
    for name in names:
        if not name:
            continue
        p = Path(name)
        p = p if p.is_absolute() else (root / p)
        if (p / "requirements.txt").is_file() or (p / "uv.lock").is_file():
            out.append(p)
    return sorted(out)


# ---------------------------------------------------------------------------
# pip-audit --format=json → advisories (pure parse)
# ---------------------------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _sanitize_requirements(text: str) -> str:
    """Drop lines pip-audit can't audit from a temp file: editable/local/VCS installs (`-e ../cli`,
    `./pkg`, `git+...`) and nested `-r`/`-c` includes. These are first-party code or path refs, not
    PyPI deps — leaving them makes pip-audit error out (which silently skips the whole component).
    Also strips ANSI color escapes (uv colorizes even when captured, which breaks pip-audit's parser)."""
    out = []
    for raw in text.splitlines():
        line = _ANSI.sub("", raw)
        s = line.strip()
        low = s.lower()
        if low.startswith(("-e", "--editable", "-r", "--requirement", "-c", "--constraint")):
            continue
        if s.startswith((".", "/")) or low.startswith(("git+", "http://", "https://", "file:")):
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def _pinned_requirements(component: Path) -> str | None:
    """Produce a fully-pinned, PyPI-only requirements string for `component` to feed
    `pip-audit --no-deps`: prefer an existing requirements.txt; else export the uv.lock. None if neither."""
    reqs = component / "requirements.txt"
    if reqs.is_file():
        try:
            return _sanitize_requirements(reqs.read_text(encoding="utf-8"))
        except OSError:
            return None
    if (component / "uv.lock").is_file():
        try:
            r = subprocess.run(
                ["uv", "export", "--format", "requirements-txt", "--no-hashes", "--no-emit-project"],
                cwd=str(component), capture_output=True, text=True, timeout=180,
                env={**os.environ, "NO_COLOR": "1"},
            )
            return _sanitize_requirements(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            return None
    return None


def run_audit(component: Path) -> dict | None:
    """Run `pip-audit --no-deps -r <pinned-reqs> --format=json` for `component`. Fail-open to None on
    missing pip-audit / offline / malformed JSON (never break the beat)."""
    reqs_text = _pinned_requirements(component)
    if reqs_text is None:
        return None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(reqs_text)
            reqs_path = fh.name
    except OSError:
        return None
    try:
        proc = subprocess.run(
            ["pip-audit", "--no-deps", "-r", reqs_path, "--format=json", "--progress-spinner=off"],
            capture_output=True, text=True, timeout=180,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    finally:
        try:
            os.unlink(reqs_path)
        except OSError:
            pass
    out = (proc.stdout or "").strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except (ValueError, json.JSONDecodeError):
        return None


def parse_advisories(audit_json: dict) -> list[dict]:
    """Pure. Extract advisories from a `pip-audit --format=json` payload.

    Shape: {"dependencies": [{"name", "version", "vulns": [{"id", "fix_versions": [...], "aliases": [...]}]}]}.
    pip-audit only reports real known advisories (no severity field), so every returned dep IS actionable.
    Returns dicts: {name, version, id, fix_versions, fixable}. fixable ⟺ at least one fix version exists.
    """
    out: list[dict] = []
    deps = (audit_json or {}).get("dependencies") or []
    if not isinstance(deps, list):
        return out
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        vulns = dep.get("vulns") or []
        for v in vulns:
            if not isinstance(v, dict):
                continue
            fixes = [f for f in (v.get("fix_versions") or []) if isinstance(f, str)]
            out.append({
                "name": dep.get("name", ""),
                "version": dep.get("version", ""),
                "id": v.get("id", ""),
                "fix_versions": fixes,
                "fixable": bool(fixes),
            })
    return out


# ---------------------------------------------------------------------------
# Pin derivation (minimal forward bump)
# ---------------------------------------------------------------------------

def _version_key(v: str) -> tuple:
    """Sort key for a PEP 440-ish version — numeric segments compared numerically, rest lexically."""
    parts = re.split(r"[.\-+]", v.strip())
    key = []
    for p in parts:
        key.append((0, int(p)) if p.isdigit() else (1, p))
    return tuple(key)


def lowest_fix(fix_versions: list[str]) -> str | None:
    """The least-disruptive fix = the LOWEST published fix version (minimal forward bump)."""
    valid = [f for f in fix_versions if _core(f) is not None]
    if not valid:
        return None
    return sorted(valid, key=_version_key)[0]


def _core(v: str) -> tuple[int, int, int] | None:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def derive_pin(advisory: dict) -> dict:
    """Map one advisory → {name, pin, disposition}. disposition ∈ {auto, human}.

    - not fixable (no published fix version) → human (defer to Dependabot / manual).
    - otherwise → 'auto': pin `name>=<lowest fix>` (minimal forward bump). The verify-gate (re-audit)
      is the safety net: if the bump can't actually be resolved (a pyproject cap holds it back), the
      advisory persists and is reclassified Tier-2, exactly like estate-audit-heal.
    """
    name = advisory.get("name", "")
    if not advisory.get("fixable"):
        return {"name": name, "pin": None, "disposition": "human"}
    fix = lowest_fix(advisory.get("fix_versions") or [])
    if fix is None:
        return {"name": name, "pin": None, "disposition": "human"}
    return {"name": name, "pin": f">={fix}", "disposition": "auto"}


def compute_plan(components: list[Path]) -> dict:
    """Aggregate a single-pass fix plan across components (detection view). Returns:
    {projects: {name: {dir, pins: {pkg: pin}, human: [pkg], advisories: n}}, has_human, audited}."""
    plan: dict = {"projects": {}, "has_human": False, "audited": 0}
    for comp in components:
        audit = run_audit(comp)
        if audit is None:
            continue
        plan["audited"] += 1
        advisories = parse_advisories(audit)
        pins: dict[str, str] = {}
        human: list[str] = []
        for adv in advisories:
            ov = derive_pin(adv)
            if ov["disposition"] == "human":
                human.append(ov["name"])
                plan["has_human"] = True
            elif ov["name"] not in pins:
                pins[ov["name"]] = ov["pin"]
        if pins or human:
            plan["projects"][_component_name(comp)] = {
                "dir": str(comp), "pins": pins, "human": sorted(set(human)), "advisories": len(advisories),
            }
    return plan


def _component_name(comp: Path) -> str:
    try:
        return str(comp.relative_to(ROOT))
    except ValueError:
        return comp.name


# ---------------------------------------------------------------------------
# Apply + verify (armed path) — uv components re-lock; plain requirements rewrite the pin.
# ---------------------------------------------------------------------------

def apply_pins(component: Path, pins: dict[str, str]) -> None:
    """Apply forward pins. uv component (has uv.lock) → `uv lock --upgrade-package <name>` (bumps within
    pyproject constraints, then re-export requirements.txt if present). Plain requirements → rewrite the
    line to `name>=fix`. The caller re-audits to verify (verify-gated)."""
    if (component / "uv.lock").is_file():
        for name in pins:
            subprocess.run(["uv", "lock", "--upgrade-package", name],
                           cwd=str(component), check=True, capture_output=True, text=True, timeout=300)
        if (component / "requirements.txt").is_file():
            exported = subprocess.run(
                ["uv", "export", "--format", "requirements-txt", "--no-hashes", "--no-emit-project"],
                cwd=str(component), capture_output=True, text=True, timeout=180,
            )
            if exported.returncode == 0 and exported.stdout.strip():
                (component / "requirements.txt").write_text(exported.stdout, encoding="utf-8")
        return
    # plain requirements.txt: rewrite each pinned package's line to name>=fix (case-insensitive match).
    # We only need the leading PEP 508 distribution name (which must start alphanumeric); matching just
    # the name — a pattern with no comparison operators — sidesteps the CodeQL py/bad-tag-filter
    # heuristic that misreads a `<|>`-bearing specifier alternation as a naive HTML-tag sanitizer.
    reqs = component / "requirements.txt"
    pin_by_norm = {n.lower(): v for n, v in pins.items()}
    out = []
    for line in reqs.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if m and m.group(1).lower() in pin_by_norm:
            out.append(f"{m.group(1)}{pin_by_norm[m.group(1).lower()]}")
        else:
            out.append(line)
    reqs.write_text("\n".join(out) + "\n", encoding="utf-8")


def verify(component: Path) -> bool:
    """Re-audit; True iff 0 advisories remain for the component."""
    audit = run_audit(component)
    if audit is None:
        return False
    return len(parse_advisories(audit)) == 0


def resolve_pins(component: Path, max_rounds: int = 4) -> dict:
    """Iteratively apply forward pins until the component audits clean, keeping only pins whose advisory
    measurably cleared (verify-gated). Returns {pins, human, clean}. Mutates the component (armed path)."""
    pins: dict[str, str] = {}
    human: set[str] = set()
    for _ in range(max_rounds):
        audit = run_audit(component)
        if audit is None:
            break
        advisories = parse_advisories(audit)
        if not advisories:
            break
        new = False
        for adv in advisories:
            ov = derive_pin(adv)
            if ov["disposition"] == "human":
                human.add(ov["name"])
                continue
            if pins.get(ov["name"]) != ov["pin"]:
                pins[ov["name"]] = ov["pin"]
                new = True
        if not new:
            break
        apply_pins(component, pins)
    return {"pins": pins, "human": sorted(human), "clean": verify(component)}


# ---------------------------------------------------------------------------
# Throttle + rollup stamp
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


def _write_stamp(plan: dict, extra: dict | None = None) -> None:
    """Rich stamp: {generated, projects:{name:{pins}}, ...} — the shape estate-audit-posture's probe
    reads (so limen-Python telemetry is real), plus idempotence keys."""
    payload = {
        "generated": _now().isoformat(timespec="seconds"),
        "projects": {n: {"pins": list((p.get("pins") or {}).keys())} for n, p in plan.get("projects", {}).items()},
    }
    if extra:
        payload.update(extra)
    try:
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Fix PR (armed) — mirrors npm-audit-autofix.open_fix_pr / the ship-docs worktree→PR recipe.
# ---------------------------------------------------------------------------

def open_fix_pr(root: Path, plan: dict) -> int:
    """Apply the plan in an isolated worktree cut from origin/main, verify-gate, open a PR, self-merge
    via merge-policy.sh when it clears. Returns process exit code. Real git/gh/uv — armed path only."""
    stamp = _now().strftime("%Y%m%d%H%M%S")
    slug = "pip-audit-" + "-".join(sorted(
        p for proj in plan["projects"].values() for p in proj["pins"]
    ))[:60] or "pip-audit-fix"
    branch = f"fix/{slug}-{stamp}"
    wt_root = os.environ.get("LIMEN_WORKTREES") or str(Path.home() / "Workspace" / ".limen-worktrees")
    Path(wt_root).mkdir(parents=True, exist_ok=True)
    tmp = Path(wt_root) / f"pip-audit-autofix-{stamp}"

    def git(*args: str, cwd: Path = root) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)

    git("fetch", "origin", "main", "--quiet")
    git("worktree", "add", "--quiet", "-b", branch, str(tmp), "origin/main")
    try:
        touched: list[str] = []
        resolved: dict[str, dict] = {}
        for proj_name, proj in plan["projects"].items():
            rel = Path(proj["dir"]).relative_to(root) if Path(proj["dir"]).is_absolute() else Path(proj["dir"])
            res = resolve_pins(tmp / rel)
            if not res["pins"] or not res["clean"]:
                continue  # verify-gate: only ship pins that measurably cleared the advisory
            resolved[proj_name] = res
            for fname in ("requirements.txt", "uv.lock"):
                if (tmp / rel / fname).is_file():
                    touched.append(str(rel / fname))
        if not touched:
            print("pip-audit-autofix: nothing pinnable (advisories are human-flagged, capped, or unfixable → Dependabot)")
            return 1
        git("add", "--", *touched, cwd=tmp)
        pins_desc = "; ".join(
            f"{name}: {', '.join(f'{k}{v}' for k, v in res['pins'].items())}"
            for name, res in resolved.items()
        )
        subprocess.run(
            ["git", "-C", str(tmp), "commit", "--quiet", "-m",
             f"fix: pin python audit advisories forward\n\n{pins_desc}\n\n"
             "Auto-authored by scripts/pip-audit-autofix.py (dark-armed, verify-gated effector).\n\n"
             "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"],
            check=True, capture_output=True, text=True,
        )
        git("push", "--quiet", "-u", "origin", branch, cwd=tmp)
        body = (
            "Auto-authored by `scripts/pip-audit-autofix.py` — the Python tier of the estate audit model.\n\n"
            f"Forward pins (verify-gated: each advisory re-audited clean): {pins_desc}\n\n"
            "merge-policy gates the merge; the PR's own CI adjudicates. Residual advisories defer to Dependabot.\n"
        )
        pr_url = subprocess.run(
            ["gh", "pr", "create", "--title", "fix: clear python audit advisories (forward pins)", "--body", body],
            cwd=str(tmp), check=True, capture_output=True, text=True,
        ).stdout.strip()
        pr_num = pr_url.rstrip("/").split("/")[-1]
        print(f"pip-audit-autofix: opened PR #{pr_num} ({pr_url})")
        pol = subprocess.run([str(root / "scripts" / "merge-policy.sh"), pr_num], capture_output=True, text=True)
        if pol.returncode == 0:
            subprocess.run(["gh", "pr", "merge", pr_num, "--squash"], capture_output=True, text=True)
            print(f"  → merge-policy CLEARED; squash-merged #{pr_num}")
            return 0
        print(f"  → PR #{pr_num} left open (merge-policy exit {pol.returncode}: HOLD until CI green)")
        return 2
    finally:
        print(f"pip-audit-autofix: retained worktree {tmp} + branch {branch} "
              "(cleanup → reclaim-worktrees.py / reap-branches.py)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_plan(plan: dict) -> None:
    if not plan["projects"]:
        print("pip-audit-autofix: no advisories in any Python component — clean")
        return
    for name, proj in sorted(plan["projects"].items()):
        for pkg, pin in sorted(proj["pins"].items()):
            print(f"  {name}: pin {pkg}{pin}")
        for pkg in sorted(proj["human"]):
            print(f"  {name}: {pkg} — no published fix → defer to Dependabot")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="pip-audit autofix effector (Python tier)")
    ap.add_argument("--check", action="store_true", help="detection only — never act, even if armed")
    ap.add_argument("--apply", action="store_true", help="force the armed path for a manual run")
    ap.add_argument("--json", action="store_true", help="emit the machine-readable plan")
    args = ap.parse_args(argv)

    comps = python_components(ROOT)
    if not comps:
        print("pip-audit-autofix: no Python components found — nothing to do")
        return 0

    plan = compute_plan(comps)
    if plan["audited"] == 0:
        print("pip-audit-autofix: pip-audit unavailable / no audit output — failing open")
        return 0

    if args.json:
        print(json.dumps(plan, indent=2, default=str))

    has_fix = any(proj["pins"] for proj in plan["projects"].values())
    has_any = bool(plan["projects"])

    env_armed = os.environ.get(APPLY_ENV, "0").strip() == "1"
    armed = (env_armed or args.apply) and not args.check
    if armed and has_fix:
        sig = _plan_signature(plan)
        if _read_stamp().get("signature") == sig:
            print("pip-audit-autofix: identical fix plan already actioned (stamp) — no-op")
            return 0
        rc = open_fix_pr(ROOT, plan)
        _write_stamp(plan, {"signature": sig, "actioned_at": _now().isoformat(timespec="seconds"), "rc": rc})
        return 0 if rc == 0 else 1

    _write_stamp(plan)  # keep the rollup stamp fresh on every detection pass
    if not args.json:
        _print_plan(plan)
        if has_fix and not env_armed:
            print(f"pip-audit-autofix: fix available but DARK — set {APPLY_ENV}=1 to open the PR")

    return 1 if has_any else 0


if __name__ == "__main__":
    sys.exit(main())
