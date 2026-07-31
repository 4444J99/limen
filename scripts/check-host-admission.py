#!/usr/bin/env python3
"""Clause 1 of the autonomy maintenance resume predicate: is host admission VALID?

Exit 0 ⟺ the machine-wide host-admission subsystem answers coherently — it can be queried, it
returns well-formed state, its sensors are not erroring, and it holds no corrupt or unparseable
lease. That is what "host admission valid" means in
``logs/autonomy-policy.json``'s resume_predicate.

VALID IS DELIBERATELY NOT `allowed`. `host-work-admission.py status` reports `allowed: false`
whenever the host is momentarily under pressure — swap fraction, disk throughput, a Backblaze
re-crawl. Those oscillate minute to minute by design; that is the whole point of an admission
gate. Binding the autonomy resume to `allowed` would mean the estate could only ever un-pause
during a lull, and would read as "still blocked" for reasons that have nothing to do with the
custody reset the window was opened for. Worse, it would be indistinguishable from a genuinely
broken admission subsystem, which is exactly the confusion this clause exists to resolve.

So: `allowed` is a capacity signal, checked continuously by the thing that needs capacity.
`valid` is a health signal, and it is what a lifecycle boundary is entitled to require.

    python3 scripts/check-host-admission.py            # exit 0 iff valid
    python3 scripts/check-host-admission.py --json     # the verdict as JSON
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADMISSION = ROOT / "scripts" / "host-work-admission.py"

REQUIRED_FIELDS = ("allowed", "pressure")


def probe() -> tuple[bool, str, dict]:
    """(valid, reason, raw). Fail CLOSED: anything unparseable is invalid, never assumed fine."""
    if not ADMISSION.is_file():
        return False, f"host admission CLI missing at {ADMISSION.relative_to(ROOT)}", {}
    try:
        proc = subprocess.run(
            [sys.executable, str(ADMISSION), "status"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            cwd=str(ROOT),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"host admission status did not run: {exc}", {}

    if proc.returncode != 0:
        return False, f"host admission status exited {proc.returncode}", {}
    try:
        raw = json.loads(proc.stdout)
    except ValueError:
        return False, "host admission status did not return JSON", {}
    if not isinstance(raw, dict):
        return False, "host admission status returned a non-object", {}

    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        return False, f"host admission state is missing {', '.join(missing)}", raw

    pressure = raw.get("pressure")
    if not isinstance(pressure, dict):
        return False, "host admission pressure block is not an object", raw
    errors = pressure.get("sensor_errors")
    if errors:
        return False, f"host admission sensors are erroring: {errors}", raw

    leases = raw.get("leases")
    if leases is not None and not isinstance(leases, list):
        return False, "host admission lease list is corrupt", raw

    held = len(leases or [])
    allowed = raw.get("allowed")
    return (
        True,
        (
            f"host admission is valid — queryable, {len(pressure)} pressure field(s), "
            f"0 sensor errors, {held} lease(s); capacity right now is allowed={allowed}, "
            "which this clause deliberately does not gate on"
        ),
        raw,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the verdict as JSON")
    args = ap.parse_args(argv)

    valid, reason, raw = probe()
    if args.json:
        print(json.dumps({"valid": valid, "reason": reason, "allowed": raw.get("allowed")}, indent=2, sort_keys=True))
    else:
        print(f"host-admission: {'VALID' if valid else 'INVALID'} — {reason}", file=sys.stdout if valid else sys.stderr)
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
