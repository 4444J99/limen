#!/usr/bin/env python3
"""governance-organ.py — THE GOVERNANCE OFFICE (Aerarium / Cvrsvs Honorvm).

The institutional force a constitutional state or foundation board maintains — standing clerk,
sequencing auditor, entity registrar, compliance sentinel — rebuilt as an autonomic organ. It
runs the cursus honorum validator against every seed.yaml in the estate every beat, reports
governance standing, and stamps the governance voice for proprioception.

Lockless: reads organ-ladder.json and validates seed files. Never writes to tasks.yaml.
Idempotent: validating seed files is read-only; the voice stamp is overwritten each beat.
Fail-open: missing seed files, unparseable YAML, or a broken validator never stops the beat.

Its constitution is organs/governance/CHARTER.md. The validatable rules live in:
  - organs/governance/validate-seed.py  (Cvrsvs Honorvm Rules #1-2)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
VOICED = LOGS / ".voice"
VALIDATOR = ROOT / "organs" / "governance" / "validate-seed.py"
LADDER = ROOT / "organ-ladder.json"


def _run_validator() -> dict:
    """Run validate-seed.py --fleet --quiet, return the outcome."""
    if not VALIDATOR.exists():
        return {"status": "no_validator", "detail": f"missing {VALIDATOR}"}
    try:
        r = subprocess.run(
            [sys.executable, str(VALIDATOR), "--fleet", "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
        passed = r.returncode == 0
        return {
            "status": "pass" if passed else "violations",
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "detail": "validate-seed.py exceeded 30s"}
    except OSError as exc:
        return {"status": "error", "detail": str(exc)}


def _governance_standing() -> dict:
    """Read organ-ladder.json governance entry for standing report."""
    try:
        data = json.loads(LADDER.read_text()) if LADDER.exists() else {}
    except (json.JSONDecodeError, OSError):
        return {}
    for o in (data.get("organs") or []):
        if o.get("pillar") == "governance":
            return {
                "maturity": o.get("maturity"),
                "stage": o.get("stage"),
                "note": o.get("note", ""),
            }
    return {}


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    VOICED.mkdir(parents=True, exist_ok=True)

    outcome = _run_validator()
    standing = _governance_standing()

    report = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "validator": outcome,
        "standing": standing,
    }
    (LOGS / "governance-organ-state.json").write_text(json.dumps(report, indent=2))

    print(f"governance-organ: validator={outcome['status']}", end="")
    if standing.get("maturity") is not None:
        print(f" maturity={standing['maturity']}% stage={standing.get('stage','?')}", end="")
    # stamp the governance voice for proprioception (organ-health.py reads this)
    (VOICED / "governance").write_text(report["ts"])
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
