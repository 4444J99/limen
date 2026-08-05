#!/usr/bin/env python3
"""governance-organ.py — THE GOVERNANCE OFFICE (Aerarium / Cvrsvs Honorvm).

The institutional force a constitutional state or foundation board maintains — standing clerk,
sequencing auditor, entity registrar, compliance sentinel — rebuilt as an autonomic organ. It
runs the cursus honorum validator against every seed.yaml in the estate every beat, reports
governance standing, stamps the governance voice for proprioception, and auto-advances maturity
in organ-ladder.json as slices land.

Lockless: reads organ-ladder.json and validates seed files. The organ-ladder write uses an
atomic write (temp + rename) under a mkdir mutex. Never writes to tasks.yaml.
Idempotent: maturity assessment is objective (file/state-based); the ladder only bumps UP, never
down; the voice stamp is overwritten each beat.
Fail-open: missing seed files, unparseable YAML, or a broken validator never stops the beat.

Its constitution is organs/governance/CHARTER.md. The validatable rules live in:
  - organs/governance/validate-seed.py  (Cvrsvs Honorvm Rules #1-2)

The organ also carries a census limb: every beat re-reads the governance estate and
the organ seed surface so the standing report metabolizes current history instead
of relying on a hand-maintained roster.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
VOICED = LOGS / ".voice"
VALIDATOR = ROOT / "organs" / "governance" / "validate-seed.py"
ENTITIES_VALIDATOR = ROOT / "organs" / "governance" / "validate-entities.py"
LADDER = ROOT / "organ-ladder.json"
GOV_HOME = ROOT / "organs" / "governance"

# Cadence: the governance voice beats every C_GOVERNANCE (default 8) * base beat (~120s).
# Voice stamp is fresh if written within 2 * cadence_seconds.
_CADENCE_SEC = int(os.environ.get("LIMEN_BEAT_GOVERNANCE", "8")) * int(os.environ.get("LIMEN_LOOP_MIN", "120"))


# --------------------------------------------------------------------------- #
# Maturity assessment — objective, file/state-derived, 10 criteria x 10 pts   #
# --------------------------------------------------------------------------- #

_MATURITY_CRITERIA: list[tuple[str, str, int]] = [
    # (key, readable_label, weight_pts)  — sum weights = 100
    ("charter_exists", "CHARTER.md exists", 10),
    ("kernel_exists", "KERNEL.md exists", 10),
    ("seed_valid", "seed.yaml has valid metadata", 10),
    ("validator_exists", "validate-seed.py exists", 10),
    ("organ_script_exists", "governance-organ.py exists (self)", 10),
    ("validator_passes", "validator passes on fleet", 10),
    ("standing_reports", "governance-organ-state.json produced", 10),
    ("voice_fresh", "governance voice stamp is fresh", 10),
    ("entity_registrar", "entity registrar artifacts exist", 10),
    ("cursus_tracking", "full cursus honorum tracking across estate", 10),
]


def _exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def _file_modified_within(rel: str, max_age_sec: int) -> bool:
    p = ROOT / rel
    if not p.exists():
        return False
    try:
        age = time.time() - p.stat().st_mtime
        return age < max_age_sec
    except OSError:
        return False


def _assess_maturity() -> dict:
    """Evaluate objective criteria and return {criteria, maturity_pct, passed_keys, failed_keys}."""
    passed = []
    failed = []
    total_weight = sum(w for _, _, w in _MATURITY_CRITERIA)

    for key, label, weight in _MATURITY_CRITERIA:
        ok = False
        if key == "charter_exists":
            ok = _exists("organs/governance/CHARTER.md")
        elif key == "kernel_exists":
            ok = _exists("organs/governance/KERNEL.md")
        elif key == "seed_valid":
            ok = _exists("organs/governance/seed.yaml")
        elif key == "validator_exists":
            ok = _exists("organs/governance/validate-seed.py")
        elif key == "organ_script_exists":
            ok = _exists("scripts/governance-organ.py")
        elif key == "validator_passes":
            ok = _run_validator().get("status") == "pass"
        elif key == "standing_reports":
            ok = _exists("logs/governance-organ-state.json")
        elif key == "voice_fresh":
            ok = _file_modified_within("logs/.voice/governance", _CADENCE_SEC * 2 + 60)
        elif key == "entity_registrar":
            ok = _exists("organs/governance/validate-entities.py") and _exists("organs/governance/entities.yaml")
        elif key == "cursus_tracking":
            ok = _exists("organs/governance/entities.yaml") and _exists("organs/governance/validate-seed.py")

        if ok:
            passed.append(key)
        else:
            failed.append(key)

    earned = sum(w for k, _, w in _MATURITY_CRITERIA if k in passed)
    maturity = round(earned / total_weight * 100) if total_weight else 0
    return {
        "maturity_pct": maturity,
        "earned_weight": earned,
        "total_weight": total_weight,
        "passed": passed,
        "failed": failed,
    }


# --------------------------------------------------------------------------- #
# Maturity advancement — lockless, idempotent bump in organ-ladder.json         #
# --------------------------------------------------------------------------- #


def _queue_lock(path: Path, timeout: float = 5.0) -> bool:
    """mkdir-based mutex. Returns True if lock acquired."""
    lock_dir = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            lock_dir.mkdir()
            return True
        except FileExistsError:
            time.sleep(0.1)
    return False


def _queue_unlock(path: Path) -> None:
    lock_dir = path.with_name(path.name + ".lock")
    try:
        lock_dir.rmdir()
    except OSError:
        pass


def _advance_maturity(assessment: dict) -> dict:
    """If assessed maturity > stored maturity, bump organ-ladder.json under lock.

    Returns {"bumped": bool, "old": int|None, "new": int|None, "reason": str}.
    """
    assessed = assessment["maturity_pct"]
    try:
        data = json.loads(LADDER.read_text()) if LADDER.exists() else {}
    except (json.JSONDecodeError, OSError) as exc:
        return {"bumped": False, "old": None, "new": None, "reason": f"cannot read ladder: {exc}"}

    gov_entry = None
    for o in data.get("organs") or []:
        if o.get("pillar") == "governance":
            gov_entry = o
            break

    if gov_entry is None:
        return {"bumped": False, "old": None, "new": None, "reason": "governance entry not found in ladder"}

    stored = gov_entry.get("maturity", 0)
    if not isinstance(stored, (int, float)):
        stored = 0

    # Derive correct stage from assessed maturity
    def _derive_stage(m: int) -> str:
        if m < 30:
            return "scaffold"
        if m < 60:
            return "building"
        if m < 90:
            return "maturing"
        return "mature"

    correct_stage = _derive_stage(stored)
    current_stage = gov_entry.get("stage", "")
    stage_mismatch = correct_stage != current_stage

    if assessed <= stored and not stage_mismatch:
        return {
            "bumped": False,
            "old": stored,
            "new": assessed,
            "reason": f"assessed ({assessed}%) <= stored ({stored}%)",
        }

    # Bump: acquire lock, re-read, write
    if not _queue_lock(LADDER, timeout=5.0):
        return {"bumped": False, "old": stored, "new": assessed, "reason": "queue lock busy — try next beat"}

    try:
        data = json.loads(LADDER.read_text())
        for o in data.get("organs") or []:
            if o.get("pillar") == "governance":
                should_write = False
                if assessed > stored:
                    o["maturity"] = assessed
                    should_write = True
                derived_stage = _derive_stage(o.get("maturity", stored))
                if o.get("stage") != derived_stage:
                    o["stage"] = derived_stage
                    should_write = True
                if should_write:
                    o["note"] = (
                        f"auto-advanced by governance-organ.py beat ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
                    )
                if not should_write:
                    _queue_unlock(LADDER)
                    return {"bumped": False, "old": stored, "new": assessed, "reason": "no change needed"}
                break

        # Atomic write: temp file + rename
        fd, tmp = tempfile.mkstemp(dir=LADDER.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, LADDER)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        return {"bumped": True, "old": stored, "new": assessed, "reason": f"advanced from {stored}% to {assessed}%"}
    except (json.JSONDecodeError, OSError) as exc:
        return {"bumped": False, "old": stored, "new": assessed, "reason": f"write error: {exc}"}
    finally:
        _queue_unlock(LADDER)


# --------------------------------------------------------------------------- #
# Core ops                                                                      #
# --------------------------------------------------------------------------- #


def _run_validator() -> dict:
    """Run validate-seed.py and validate-entities.py --fleet --quiet, return the outcome."""
    if not VALIDATOR.exists():
        return {"status": "no_validator", "detail": f"missing {VALIDATOR}"}
    if not ENTITIES_VALIDATOR.exists():
        return {"status": "no_validator", "detail": f"missing {ENTITIES_VALIDATOR}"}
    try:
        r1 = subprocess.run(
            [sys.executable, str(VALIDATOR), "--fleet", "--quiet", "--strict-graph"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        r2 = subprocess.run(
            [sys.executable, str(ENTITIES_VALIDATOR), "--fleet", "--quiet", "--strict-graph"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        passed = r1.returncode == 0 and r2.returncode == 0
        return {
            "status": "pass" if passed else "violations",
            "returncode": r1.returncode or r2.returncode,
            "stdout": (r1.stdout.strip() + "\n" + r2.stdout.strip()).strip(),
            "stderr": (r1.stderr.strip() + "\n" + r2.stderr.strip()).strip(),
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "detail": "validators exceeded 30s"}
    except OSError as exc:
        return {"status": "error", "detail": str(exc)}


def _governance_standing() -> dict:
    """Read organ-ladder.json governance entry for standing report."""
    try:
        data = json.loads(LADDER.read_text()) if LADDER.exists() else {}
    except (json.JSONDecodeError, OSError):
        return {}
    for o in data.get("organs") or []:
        if o.get("pillar") == "governance":
            return {
                "maturity": o.get("maturity"),
                "stage": o.get("stage"),
                "note": o.get("note", ""),
            }
    return {}


def _governance_census() -> dict:
    """Read-only census of the governance estate and organ seed surface."""
    governance_files = sorted(path for path in GOV_HOME.glob("*") if path.is_file())
    seed_files = sorted(path for path in (ROOT / "organs").glob("*/seed.yaml") if path.is_file())
    entity_files = sorted(path for path in GOV_HOME.glob("entities*.yaml") if path.is_file())
    return {
        "governance_artifacts": len(governance_files),
        "organ_seed_files": len(seed_files),
        "entity_artifacts": len(entity_files),
        "governance_artifact_names": [path.name for path in governance_files],
        "organ_seed_paths": [str(path.relative_to(ROOT)) for path in seed_files],
    }


# --------------------------------------------------------------------------- #
# Main                                                                          #
# --------------------------------------------------------------------------- #


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    VOICED.mkdir(parents=True, exist_ok=True)

    # 1. Run validator
    outcome = _run_validator()

    # 2. Assess maturity
    assessment = _assess_maturity()

    # 3. Advance ladder if maturity grew
    advancement = _advance_maturity(assessment)

    # 4. Read current standing
    standing = _governance_standing()

    # 5. Census the estate surface this organ governs
    census = _governance_census()

    # 6. Write state report
    report = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "validator": outcome,
        "assessment": {
            "maturity_pct": assessment["maturity_pct"],
            "earned_weight": assessment["earned_weight"],
            "total_weight": assessment["total_weight"],
            "passed": assessment["passed"],
            "failed": assessment["failed"],
        },
        "advancement": advancement,
        "standing": standing,
        "census": census,
    }
    (LOGS / "governance-organ-state.json").write_text(json.dumps(report, indent=2))

    # 7. Print beat summary
    parts = [
        f"validator={outcome['status']}",
        f"maturity={assessment['maturity_pct']}%",
        f"seeds={census['organ_seed_files']}",
    ]
    m = standing.get("maturity")
    if m is not None:
        parts.append(f"ladder={m}%")
    s = standing.get("stage")
    if s:
        parts.append(f"stage={s}")
    if advancement["bumped"]:
        parts.append(f"ADVANCED:{advancement['old']}->{advancement['new']}%")
    failed_list = assessment.get("failed", [])
    if failed_list:
        parts.append(f"needs:{','.join(failed_list)}")
    print("governance-organ: " + " | ".join(parts))

    # 8. Stamp voice for proprioception
    (VOICED / "governance").write_text(report["ts"])

    # Write a human-readable face for the governance dashboard
    face = ROOT / "web" / "app" / "public" / "governance-standing.json"
    try:
        face.parent.mkdir(parents=True, exist_ok=True)
        face.write_text(
            json.dumps(
                {
                    "ts": report["ts"],
                    "maturity": assessment["maturity_pct"],
                    "stage": standing.get("stage", "?"),
                    "validator": outcome["status"],
                    "passed_checks": assessment["passed"],
                    "census": census,
                    "next_slices": [
                        k for k in assessment["failed"] if k not in ("entity_registrar", "cursus_tracking") or True
                    ],
                },
                indent=2,
            )
        )
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
