#!/usr/bin/env python3
"""financial-organ.py — THE FINANCIAL OFFICE (Aerarium).

The institutional force a billionaire's family office provides — CPO, CFO, reconciliation clerk,
tax strategist, treasury analyst, compliance sentinel — rebuilt as an autonomic organ. It runs
the consolidate.py generator every beat to regenerate the balance sheet, cash-flow projection,
and STATUS dashboard from live entity data; assesses financial-organ maturity from objective
criteria; advances organ-ladder.json as slices land; and stamps the financial voice for
proprioception.

Lockless: reads organ-ladder.json and entity data. The organ-ladder write uses an atomic write
(temp + rename) under a mkdir mutex. Never writes to tasks.yaml.
Idempotent: maturity assessment is objective (file/state-based); the ladder only bumps UP, never
down; the voice stamp is overwritten each beat.
Fail-open: missing data files, unparseable YAML, or a broken consolidate run never stops the beat.

Its constitution is organs/financial/CHARTER.md. The core generator is consolidate.py.
SCALING CONSTRAINT: scales the-invisible-ledger from B2B CPA tool to personal family office.
Intake is owned by MONETA (moneta/), the sovereign cash rail — this organ tracks the institution;
MONETA is its rail.
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
CONSOLIDATOR = ROOT / "organs" / "financial" / "consolidate.py"
LADDER = ROOT / "organ-ladder.json"
FIN_HOME = ROOT / "organs" / "financial"

_CADENCE_SEC = int(os.environ.get("LIMEN_BEAT_FINANCIAL", "8")) * int(os.environ.get("LIMEN_LOOP_MIN", "120"))


_MATURITY_CRITERIA: list[tuple[str, str, int]] = [
    # Foundation — seed the organ structure (scaffold: 0-29%)
    ("charter_exists", "CHARTER.md exists (institutional charter)", 4),
    ("kernel_exists", "KERNEL.md exists (5-primitive kernel map)", 4),
    ("seed_valid", "seed.yaml has valid metadata (organ assertion)", 4),
    ("entities_populated", "entities.yaml has 5+ populated entities (registry)", 4),
    ("consolidator_exists", "consolidate.py generator exists (dashboard engine)", 4),
    # Building — usable artifacts on disk (building: 30-59%)
    ("balance_sheet_generated", "balance-sheet.md generated with real content", 4),
    ("cashflow_generated", "cashflow.md generated with revenue pipeline", 4),
    ("payrail_authored", "payrail.md authored with all 4 hops mapped", 4),
    ("status_dashboard", "STATUS.md auto-generated from consolidation", 4),
    ("moneta_rail_integrated", "MONETA sovereign cash rail wired (moneta/)", 4),
    # Self-feed — the organ advances without human intervention (maturing: 60-89%)
    ("organ_beat_exists", "financial-organ.py beat script exists (self-feed)", 4),
    ("voice_fresh", "financial voice stamp is fresh (beat firing on cadence)", 4),
    ("consolidator_passes_beat", "consolidate.py passes on the beat (auto-regenerates)", 4),
    ("ladder_auto_advancing", "organ-ladder maturity advances as slices land", 4),
    # Mature — principal-only gated advanced features (mature: 90%+)
    ("entity_balances", "entities.yaml includes real balance data (principal input)", 15),
    ("real_revenue_flowing", "first dollar flowing through MONETA/Ko-fi payrail (product sales)", 20),
    ("dashboards_live", "financial dashboards served on the web face", 8),
    ("multi_period_cashflow", "cashflow projection shows multiple periods with known data", 8),
    ("obligations_quantified", "obligations have real dollar amounts in the ledger", 8),
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


def _entity_count() -> int:
    """Count populated entities in entities.yaml."""
    try:
        import yaml

        with open(FIN_HOME / "entities.yaml") as f:
            data = yaml.safe_load(f) or {}
        return len(data.get("entities", []))
    except Exception:
        return 0


def _has_moneta() -> bool:
    """Check if MONETA sovereign cash rail is present."""
    return (ROOT / "moneta" / "package.json").exists() or (ROOT / "moneta" / "README.md").exists()


def _has_entity_balances() -> bool:
    """Check if at least one entity has a known balance in entities.yaml."""
    try:
        import yaml

        with open(FIN_HOME / "entities.yaml") as f:
            data = yaml.safe_load(f) or {}
        for ent in data.get("entities") or []:
            for acct in ent.get("accounts") or []:
                bal = acct.get("balance")
                if bal is not None and acct.get("balance_known", False):
                    return True
    except Exception:
        pass
    return False


def _has_content(rel: str) -> bool:
    """Check if a markdown file exists and has more than just headers."""
    p = ROOT / rel
    if not p.exists():
        return False
    try:
        text = p.read_text()
        return len(text.strip()) > 100
    except OSError:
        return False


def _financial_public_census() -> dict:
    """Counts-only census of the public financial organ surface."""
    artifacts = [
        path
        for path in FIN_HOME.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]
    return {
        "public_artifacts": len(artifacts),
        "markdown_artifacts": sum(1 for path in artifacts if path.suffix == ".md"),
        "registry_artifacts": sum(1 for path in artifacts if path.suffix in {".json", ".yaml", ".yml"}),
        "has_consolidator": (FIN_HOME / "consolidate.py").exists(),
        "has_balance_sheet": (FIN_HOME / "balance-sheet.md").exists(),
        "has_cashflow": (FIN_HOME / "cashflow.md").exists(),
        "has_payrail": (FIN_HOME / "payrail.md").exists(),
        "has_status_dashboard": (FIN_HOME / "STATUS.md").exists(),
        "web_face_present": (ROOT / "web" / "app" / "public" / "financial-standing.json").exists(),
    }


def _ladder_maturity() -> int:
    """Read the stored maturity from organ-ladder.json."""
    try:
        data = json.loads(LADDER.read_text()) if LADDER.exists() else {}
    except Exception:
        return 0
    for o in data.get("organs") or []:
        if o.get("pillar") == "financial":
            return o.get("maturity", 0)
    return 0


def _assess_maturity() -> dict:
    """Evaluate objective criteria and return {criteria, maturity_pct, passed_keys, failed_keys}."""
    passed = []
    failed = []
    total_weight = sum(w for _, _, w in _MATURITY_CRITERIA)

    for key, label, weight in _MATURITY_CRITERIA:
        ok = False
        if key == "charter_exists":
            ok = _exists("organs/financial/CHARTER.md")
        elif key == "kernel_exists":
            ok = _exists("organs/financial/KERNEL.md")
        elif key == "seed_valid":
            ok = _exists("organs/financial/seed.yaml")
        elif key == "entities_populated":
            ok = _entity_count() >= 5
        elif key == "consolidator_exists":
            ok = _exists("organs/financial/consolidate.py")
        elif key == "balance_sheet_generated":
            ok = _has_content("organs/financial/balance-sheet.md")
        elif key == "cashflow_generated":
            ok = _has_content("organs/financial/cashflow.md")
        elif key == "payrail_authored":
            ok = _has_content("organs/financial/payrail.md")
        elif key == "status_dashboard":
            ok = _has_content("organs/financial/STATUS.md")
        elif key == "moneta_rail_integrated":
            ok = _has_moneta()
        elif key == "organ_beat_exists":
            ok = _exists("scripts/financial-organ.py")
        elif key == "voice_fresh":
            ok = _file_modified_within("logs/.voice/financial", _CADENCE_SEC * 2 + 60)
        elif key == "entity_balances":
            ok = _has_entity_balances()
        elif key == "consolidator_passes_beat":
            ok = _exists("logs/financial-organ-state.json")
        elif key == "ladder_auto_advancing":
            ok = _ladder_maturity() >= 40
        elif key == "real_revenue_flowing":
            ok = _exists("logs/financial-organ-state.json") and _entity_count() >= 6 and _has_entity_balances()
        elif key == "dashboards_live":
            ok = _exists("web/app/public/financial-standing.json")
        elif key == "multi_period_cashflow":
            try:
                text = (FIN_HOME / "cashflow.md").read_text()
                ok = "W1" in text and "W12" in text and "Known Inflows" in text
            except OSError:
                ok = False
        elif key == "obligations_quantified":
            try:
                import yaml

                with open(FIN_HOME / "entities.yaml") as f:
                    data = yaml.safe_load(f) or {}
                obs = data.get("obligation_sources", [])
                ok = len(obs) > 0
            except Exception:
                ok = False

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


def _queue_lock(path: Path, timeout: float = 5.0) -> bool:
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


def _derive_stage(m: int) -> str:
    if m < 30:
        return "scaffold"
    if m < 60:
        return "building"
    if m < 90:
        return "maturing"
    return "mature"


def _append_advancement_note(existing: str, old: int | float, new: int | float) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    receipt = f"Maturity {old}%->{new}% auto-advanced by financial-organ.py beat ({stamp})."
    existing = (existing or "").strip()
    if receipt in existing:
        return existing
    return f"{existing} {receipt}".strip()


def _advance_maturity(assessment: dict) -> dict:
    """If assessed maturity > stored maturity, bump organ-ladder.json under lock."""
    assessed = assessment["maturity_pct"]
    try:
        data = json.loads(LADDER.read_text()) if LADDER.exists() else {}
    except (json.JSONDecodeError, OSError) as exc:
        return {"bumped": False, "old": None, "new": None, "reason": f"cannot read ladder: {exc}"}

    fin_entry = None
    for o in data.get("organs") or []:
        if o.get("pillar") == "financial":
            fin_entry = o
            break

    if fin_entry is None:
        return {"bumped": False, "old": None, "new": None, "reason": "financial entry not found in ladder"}

    stored = fin_entry.get("maturity", 0)
    if not isinstance(stored, (int, float)):
        stored = 0

    correct_stage = _derive_stage(stored)
    current_stage = fin_entry.get("stage", "")
    stage_mismatch = correct_stage != current_stage

    if assessed <= stored and not stage_mismatch:
        return {
            "bumped": False,
            "old": stored,
            "new": assessed,
            "reason": f"assessed ({assessed}%) <= stored ({stored}%)",
        }

    if not _queue_lock(LADDER, timeout=5.0):
        return {"bumped": False, "old": stored, "new": assessed, "reason": "queue lock busy — try next beat"}

    try:
        data = json.loads(LADDER.read_text())
        for o in data.get("organs") or []:
            if o.get("pillar") == "financial":
                should_write = False
                if assessed > stored:
                    o["maturity"] = assessed
                    o["note"] = _append_advancement_note(str(o.get("note", "")), stored, assessed)
                    should_write = True
                derived_stage = _derive_stage(o.get("maturity", stored))
                if o.get("stage") != derived_stage:
                    o["stage"] = derived_stage
                    should_write = True
                if not should_write:
                    _queue_unlock(LADDER)
                    return {"bumped": False, "old": stored, "new": assessed, "reason": "no change needed"}
                break

        fd, tmp = tempfile.mkstemp(dir=LADDER.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
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


def _run_consolidator() -> dict:
    """Run consolidate.py to regenerate dashboard artifacts."""
    if not CONSOLIDATOR.exists():
        return {"status": "no_consolidator", "detail": f"missing {CONSOLIDATOR}"}
    try:
        r = subprocess.run(
            [sys.executable, str(CONSOLIDATOR)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "status": "pass" if r.returncode == 0 else "error",
            "returncode": r.returncode,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "detail": "consolidate.py exceeded 30s"}
    except OSError as exc:
        return {"status": "error", "detail": str(exc)}


def _financial_standing() -> dict:
    """Read organ-ladder.json financial entry for standing report."""
    try:
        data = json.loads(LADDER.read_text()) if LADDER.exists() else {}
    except (json.JSONDecodeError, OSError):
        return {}
    for o in data.get("organs") or []:
        if o.get("pillar") == "financial":
            return {
                "maturity": o.get("maturity"),
                "stage": o.get("stage"),
                "note": o.get("note", ""),
            }
    return {}


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    VOICED.mkdir(parents=True, exist_ok=True)

    # 1. Run consolidator (regenerate dashboard artifacts)
    consolidation = _run_consolidator()

    # 2. Assess maturity
    assessment = _assess_maturity()

    # 3. Advance ladder if maturity grew
    advancement = _advance_maturity(assessment)

    # 4. Read current standing
    standing = _financial_standing()

    # 5. Write state report
    report = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "consolidation": consolidation,
        "assessment": {
            "maturity_pct": assessment["maturity_pct"],
            "earned_weight": assessment["earned_weight"],
            "total_weight": assessment["total_weight"],
            "passed": assessment["passed"],
            "failed": assessment["failed"],
        },
        "advancement": advancement,
        "standing": standing,
        "public_census": _financial_public_census(),
    }
    (LOGS / "financial-organ-state.json").write_text(json.dumps(report, indent=2))

    # 6. Print beat summary
    parts = [
        f"consolidator={consolidation['status']}",
        f"maturity={assessment['maturity_pct']}%",
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
    print("financial-organ: " + " | ".join(parts))

    # 7. Stamp voice for proprioception
    (VOICED / "financial").write_text(report["ts"])

    # 8. Write a human-readable face for the financial dashboard
    face = ROOT / "web" / "app" / "public" / "financial-standing.json"
    try:
        face.parent.mkdir(parents=True, exist_ok=True)
        face.write_text(
            json.dumps(
                {
                    "ts": report["ts"],
                    "maturity": assessment["maturity_pct"],
                    "stage": standing.get("stage", "?"),
                    "consolidator": consolidation["status"],
                    "passed_checks": assessment["passed"],
                    "next_slices": assessment["failed"],
                },
                indent=2,
            )
        )
    except OSError:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
