#!/usr/bin/env python3
"""npm-audit-gate.py — `npm audit` with a recorded, EXPIRING exception registry.

Why this exists (2026-08-14): GHSA-2v37-7h3g-55p8 (nanoid < 3.3.18, high) was
published while the 3.x line's newest release was the vulnerable 3.3.17 — the
advisory's "fix" did not exist on the registry, `npm audit fix` was a no-op,
and the raw `npm audit --audit-level=high` CI step turned every PR in the
repository red with nothing any diff could do about it. A gate that demands an
impossible action is not a gate; silently weakening it to `--audit-level=
critical` hides real findings. The disciplined middle is this wrapper:

  - every high/critical advisory still fails the gate, EXCEPT ones listed in
    institutio/governance/npm-audit-exceptions.json;
  - every exception carries an id, a reason, a scope, and an EXPIRY DATE —
    and an expired exception stops excepting, so the gate goes red again by
    itself instead of the allowlist quietly becoming permanent;
  - every applied exception is printed loudly in the passing output.

Usage:  python3 scripts/npm-audit-gate.py <package-dir> [--today YYYY-MM-DD]
Exit 0 ⟺ no non-excepted high/critical advisories. stdlib only (the CI web
job has no PyYAML), so the registry is JSON.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCEPTIONS = REPO_ROOT / "institutio" / "governance" / "npm-audit-exceptions.json"
BLOCKING = {"high", "critical"}


def ghsa_ids(via) -> set[str]:
    """Advisory ids reachable from a vulnerability's `via` list (dicts are
    advisories; strings are transitive package references)."""
    out: set[str] = set()
    for v in via or []:
        if isinstance(v, dict):
            url = str(v.get("url", ""))
            if "/advisories/" in url:
                out.add(url.rsplit("/", 1)[-1])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("package_dir", help="directory containing package-lock.json")
    ap.add_argument("--today", help="override today's date (ISO) for testing")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    pkg = (REPO_ROOT / args.package_dir).resolve()
    proc = subprocess.run(
        ["npm", "audit", "--audit-level=high", "--json"],
        cwd=pkg,
        capture_output=True,
        text=True,
    )
    try:
        report = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        print(f"npm-audit-gate: npm audit produced unparseable output (exit {proc.returncode})")
        print(proc.stdout[:2000])
        print(proc.stderr[:2000], file=sys.stderr)
        return 1

    exceptions = []
    if EXCEPTIONS.exists():
        exceptions = json.loads(EXCEPTIONS.read_text())["exceptions"]

    def exception_for(gid: str):
        for e in exceptions:
            if e["id"] == gid and e.get("scope", args.package_dir) == args.package_dir:
                return e
        return None

    blocking: dict[str, dict] = {}
    for name, vuln in (report.get("vulnerabilities") or {}).items():
        if vuln.get("severity") not in BLOCKING:
            continue
        for gid in ghsa_ids(vuln.get("via")):
            blocking.setdefault(gid, {"packages": set(), "severity": vuln["severity"]})
            blocking[gid]["packages"].add(name)

    failed = 0
    for gid, info in sorted(blocking.items()):
        exc = exception_for(gid)
        pkgs = ", ".join(sorted(info["packages"]))
        if exc is None:
            print(f"FAIL {gid} ({info['severity']}) in {pkgs} — no exception recorded")
            failed += 1
            continue
        expires = dt.date.fromisoformat(exc["expires"])
        if today > expires:
            print(
                f"FAIL {gid} ({info['severity']}) in {pkgs} — exception EXPIRED {exc['expires']}. "
                f"Re-assess: {exc['reason']}"
            )
            failed += 1
        else:
            print(f"EXCEPTED {gid} ({info['severity']}) in {pkgs} — until {exc['expires']}: {exc['reason']}")

    if failed:
        print(f"npm-audit-gate: {args.package_dir} — {failed} blocking advisor(ies)")
        return 1
    n = len(blocking)
    print(
        f"npm-audit-gate: {args.package_dir} clean"
        + (f" ({n} advisory(ies) under recorded, unexpired exception)" if n else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
