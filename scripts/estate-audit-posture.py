#!/usr/bin/env python3
"""estate-audit-posture.py — the single rollup predicate for the estate's dependency-audit posture.

The three-organ ownership model has three separate sensors; this composes them into ONE view + ONE
hard exit code, so "is the estate's dependency-audit posture healthy?" is a single line, not three:

  - dependabot-security-guard  → Tier-2 owner (Dependabot security-updates ON, all audit-CI repos).  HARD.
  - npm-audit-autofix          → limen-local Tier-1 leaves (web/app, web/worker).                     telemetry.
  - estate-audit-heal          → the other 8 org repos' Tier-1 leaves.                                 telemetry.

Health semantic (derived from the model, not arbitrary): a Tier-1 advisory is ALWAYS owned — the
autofix/heal organs detect and report it every beat, dark or armed, so it never rots silently. The ONLY
way an advisory rots with no working owner is its Tier-2 owner (Dependabot) drifting OFF. So the rollup
is RED (exit 1) ⟺ dependabot-guard reports drift. The Tier-1 organs' latest verdicts fold in as posture
telemetry (`advisories_pending`) — surfaced, never rot — so there is one place to read the whole picture.

Light by design: the Tier-2 owner is an API-only live check; the two heavy Tier-1 organs are read from
their durable stamps (`logs/npm-audit-autofix.json`, `logs/estate-audit-heal.json`) — never re-run here
(estate-heal clones 8 repos). Fail-open everywhere: an absent script/stamp is 'unknown', never RED.

  python3 scripts/estate-audit-posture.py --check   # one line + exit 1 iff a Tier-2 owner is OFF
  python3 scripts/estate-audit-posture.py --json      # the composed posture, machine-readable
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
SCRIPT_DIR = Path(__file__).resolve().parent  # sibling organs live next to this file (worktree-safe)
GUARD = SCRIPT_DIR / "dependabot-security-guard.py"
STAMP_NPM = ROOT / "logs" / "npm-audit-autofix.json"
STAMP_ESTATE = ROOT / "logs" / "estate-audit-heal.json"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def probe_tier2() -> dict:
    """HARD: live, API-only Dependabot posture across the audit-CI repos. Fail-open → 'unknown'."""
    if not GUARD.exists():
        return {"status": "unknown", "reason": "dependabot-security-guard.py absent (pending #1351)", "drifted": []}
    try:
        r = subprocess.run(
            [sys.executable, str(GUARD), "--check", "--json"],
            capture_output=True, text=True, timeout=400,
        )
    except Exception as e:  # noqa: BLE001 — fail-open on any subprocess error
        return {"status": "unknown", "reason": str(e)[:80], "drifted": []}
    data = _read_json_str(r.stdout)
    if data is None:
        return {"status": "unknown", "reason": "unparseable guard output", "drifted": []}
    drifted = data.get("drifted") or []
    return {"status": "drift" if drifted else "clean", "drifted": drifted,
            "repos": len(data.get("states") or [])}


def probe_local() -> dict:
    """Telemetry: limen-local Tier-1 leaves, read from the npm-audit-autofix stamp. Unknown if unrun."""
    data = _read_json(STAMP_NPM)
    if not data:
        return {"status": "unknown", "reason": "no npm-audit-autofix stamp yet"}
    projects = data.get("projects") or {}
    pins = {name: proj.get("pins") for name, proj in projects.items() if proj.get("pins")}
    return {"status": "action" if pins else "clean", "pins": pins, "stamp": data.get("generated")}


def probe_estate() -> dict:
    """Telemetry: the 8 org repos' Tier-1 leaves, read from the estate-audit-heal stamp. Unknown if unrun."""
    data = _read_json(STAMP_ESTATE)
    if not data:
        return {"status": "unknown", "reason": "no estate-audit-heal stamp yet"}
    repos = data.get("repos") or []
    with_tier1 = [r["repo"] for r in repos if r.get("tier1")]
    return {"status": "action" if with_tier1 else "clean", "tier1_repos": with_tier1,
            "repos": len(repos), "stamp": data.get("generated")}


def _read_json_str(text: str) -> dict | None:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def posture() -> dict:
    tier2 = probe_tier2()
    local = probe_local()
    estate = probe_estate()
    pending = local.get("status") == "action" or estate.get("status") == "action"
    return {
        "healthy": tier2["status"] != "drift",   # RED iff a Tier-2 owner (Dependabot) is OFF
        "advisories_pending": pending,            # owned Tier-1 fixes awaiting an armed organ (not rot)
        "tier2_owner": tier2,
        "limen_local": local,
        "estate_repos": estate,
    }


def run(*, as_json: bool) -> int:
    p = posture()
    if as_json:
        print(json.dumps(p, indent=2))
    else:
        t2 = p["tier2_owner"]
        verdict = "HEALTHY" if p["healthy"] else "UNHEALTHY — a Tier-2 owner (Dependabot) is OFF"
        print(f"estate-audit-posture: {verdict}")
        print(f"  Tier-2 owner (Dependabot): {t2['status']}"
              + (f" — drifted: {', '.join(t2['drifted'])}" if t2.get("drifted") else ""))
        print(f"  limen-local (npm-audit-autofix): {p['limen_local']['status']}")
        print(f"  estate repos (estate-audit-heal): {p['estate_repos']['status']}")
        if p["advisories_pending"]:
            print("  note: Tier-1 fixes are available and OWNED (a dark organ will open them once armed) — not rot")
    return 0 if p["healthy"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Estate dependency-audit posture — single rollup predicate")
    ap.add_argument("--check", action="store_true", help="human-readable rollup (default)")
    ap.add_argument("--json", action="store_true", help="machine-readable composed posture")
    args = ap.parse_args(argv)
    return run(as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
