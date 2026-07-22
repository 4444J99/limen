#!/usr/bin/env python3
"""dependabot-security-guard.py — hold the Tier-2 deferral's owner enabled (monitored invariant).

`estate-audit-heal.py` (#1349) defers framework-major-held audit advisories (Tier-2) to Dependabot.
That deferral is only as good as Dependabot's SECURITY-updates actually being ON. Today all estate
audit-CI repos have alerts + security-updates ON — but nothing GUARDS that: if one drifts OFF, the
healer keeps deferring Tier-2 advisories to an owner that is no longer working, and they rot silently.

This organ makes "Dependabot owns Tier-2" a verified, self-healing invariant. It scopes to exactly the
repos where the deferral is active — the org's npm/pnpm audit-CI repos (limen excluded: it uses Renovate,
not Dependabot). For each it OBSERVES the GitHub setting; ``--check`` exits non-zero on drift; and, armed
(``LIMEN_DEPENDABOT_GUARD_APPLY=1``, read internally like the sibling organs), it re-ENABLES drift — ON
only, never disables. Enabling a benign, reversible safety setting; per-run cap; fail-open on missing gh.

  python3 scripts/dependabot-security-guard.py --check   # dry-run: per-repo posture, exit 1 on drift
  python3 scripts/dependabot-security-guard.py --json      # machine-readable
  python3 scripts/dependabot-security-guard.py --apply      # armed (also needs env lever): enable drift
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.environ.get("LIMEN_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT_DIR = os.path.join(ROOT, "scripts")
APPLY_ENV = "LIMEN_DEPENDABOT_GUARD_APPLY"
DEFAULT_CAP = int(os.environ.get("LIMEN_DEPENDABOT_GUARD_MAX", "10") or "10")
OWNER = os.environ.get("LIMEN_DEPENDABOT_GUARD_OWNER", "organvm")
SELF_REPO = "organvm/limen"  # limen uses Renovate, not Dependabot — out of scope


def _gh(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """gh with the cascade token; fail-open (mirrors sync-marketplace-config.py:72-86)."""
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return subprocess.CompletedProcess(args, 1, "", "offline")
    env = {**os.environ}
    try:
        tok = subprocess.run(
            ["bash", os.path.join(SCRIPT_DIR, "gh-app-token.sh")],
            capture_output=True, text=True, timeout=45,
        )
        if tok.returncode == 0 and tok.stdout.strip():
            env["GH_TOKEN"] = env["GITHUB_TOKEN"] = tok.stdout.strip()
    except Exception:
        pass
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, env=env)
    except Exception as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def discover_repos() -> list[str]:
    """The org's npm/pnpm audit-CI repos — where the Tier-2 deferral to Dependabot is active. Same
    derivation as estate-audit-heal. Override for tests via LIMEN_DEPENDABOT_GUARD_REPOS (colon-sep)."""
    override = os.environ.get("LIMEN_DEPENDABOT_GUARD_REPOS")
    if override:
        found = {r.strip() for r in override.split(":") if r.strip()}
    else:
        found = set()
        for term in ("npm audit", "pnpm audit"):
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
    found.discard(SELF_REPO)
    return sorted(found)


def observe(repo: str) -> dict:
    """Read the two Dependabot security postures for `repo` (read-only). Values: 'on'|'off'|'unknown'
    (unknown ⟺ the API call failed → fail-open, treated as not-drifted so we never thrash on a blip)."""
    sec = "unknown"
    r = _gh(["api", f"/repos/{repo}", "--jq", ".security_and_analysis.dependabot_security_updates.status"],
            timeout=30)
    if r.returncode == 0:
        val = (r.stdout or "").strip()
        sec = "on" if val == "enabled" else ("off" if val == "disabled" else "unknown")
    # vulnerability-alerts: 204 (on) → returncode 0 ; 404 (off) → non-zero with Not Found
    alerts = "unknown"
    a = _gh(["api", f"/repos/{repo}/vulnerability-alerts"], timeout=30)
    if a.returncode == 0:
        alerts = "on"
    elif "404" in (a.stderr or "") or "Not Found" in (a.stderr or ""):
        alerts = "off"
    return {"repo": repo, "security_updates": sec, "alerts": alerts}


def is_drifted(state: dict) -> bool:
    """Drift ⟺ a posture is explicitly OFF. 'unknown' (API blip) is NOT drift — fail-open, no thrash."""
    return state.get("security_updates") == "off" or state.get("alerts") == "off"


def enable(repo: str) -> dict:
    """Enable both postures — ON only, never disables (toward-desired-state). Uses the REST
    automated-security-fixes + vulnerability-alerts PUT endpoints. NOTE: `gh repo edit` has NO
    --enable-automated-security-fixes flag (only --enable-advanced-security); the documented path
    is `PUT /repos/{repo}/automated-security-fixes`. Verified empirically 2026-07-22 (full
    DELETE→disabled / PUT→enabled round-trip on a live repo)."""
    fixes = _gh(["api", "-X", "PUT", f"/repos/{repo}/automated-security-fixes"], timeout=45)
    alerts = _gh(["api", "-X", "PUT", f"/repos/{repo}/vulnerability-alerts"], timeout=30)
    return {"repo": repo,
            "security_fixes": "enabled" if fixes.returncode == 0 else f"FAILED:{(fixes.stderr or '')[:60]}",
            "alerts": "enabled" if alerts.returncode == 0 else f"FAILED:{(alerts.stderr or '')[:60]}"}


def run(*, apply: bool, as_json: bool) -> int:
    repos = discover_repos()
    if not repos:
        print("dependabot-security-guard: no audit-CI repos discovered (or offline) — nothing to do")
        return 0
    armed = apply and os.environ.get(APPLY_ENV, "0").strip() == "1"

    states = [observe(r) for r in repos]
    drifted = [s for s in states if is_drifted(s)]
    actions = []
    if armed and drifted:
        for s in drifted[:DEFAULT_CAP]:
            actions.append(enable(s["repo"]))

    if as_json:
        print(json.dumps({"armed": armed, "states": states, "drifted": [s["repo"] for s in drifted],
                          "actions": actions}, indent=2))
    else:
        for s in states:
            flag = "  DRIFT →" if is_drifted(s) else ""
            print(f"  {s['repo']}: alerts={s['alerts']} security-updates={s['security_updates']}{flag}")
        if drifted and not armed:
            print(f"dependabot-security-guard: {len(drifted)} repo(s) with Dependabot security posture OFF "
                  f"— DARK; set {APPLY_ENV}=1 to re-enable")
        for a in actions:
            print(f"  re-enabled {a['repo']}: security_fixes={a['security_fixes']} alerts={a['alerts']}")

    # exit non-zero on any drift (detection surfaces on the beat); armed runs re-check next beat
    return 1 if drifted else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dependabot security-updates monitored invariant")
    ap.add_argument("--check", action="store_true", help="detection only — never writes (even if armed)")
    ap.add_argument("--apply", action="store_true", help="force the armed path for a manual run")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    # bare beat invocation acts when the env lever is set (run() gates on APPLY_ENV); --check never acts.
    apply = not args.check
    return run(apply=apply, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
