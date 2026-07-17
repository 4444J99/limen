#!/usr/bin/env python3
"""apply-visibility.py — converge observed repo visibility toward the estate registry (class G's effector).

The GitOps direction: institutio/github/estate.yaml is desired-state; this script drives reality
toward it. The two directions carry ASYMMETRIC gates (autonomy is derived from reversibility):

  DEMOTE  desired private, observed public  — the standing leak-posture auto-guard. Reversible and
          protective: executes under --apply alone (the reconcile loop's LIMEN_GITVS_APPLY arming).
  PUBLISH desired public, observed private — irreversible exposure (history included). Triple-gated:
          (1) DOUBLE-DARK: --apply AND LIMEN_VISIBILITY_APPLY=1 (the reap-remote-branches precedent);
          (2) a released lever: a his-hand-levers.json row with id L-PORTAL-PUBLISH-*, status
              "released", whose `unlocks` list names the repo (the wave list is HIS sanction);
          (3) a green + fresh publish-sweep receipt (scripts/publish-sweep.py — history swept).

Every action (and every held plan row) appends to logs/visibility-actions.jsonl. Fail-open, bounded
(LIMEN_VISIBILITY_MAX per run), offline → skip. Registered as the `repo` resource delegate effector
in estate.yaml — reconcile dispatches it; the gates above live HERE, never in the reconcile engine.

  python3 scripts/apply-visibility.py            # dry plan
  python3 scripts/apply-visibility.py --check    # sensor idiom: exit 0 ⟺ no actionable drift
  python3 scripts/apply-visibility.py --apply    # demote executes; publish needs its triple gate
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.resolve()
ACTIONS = ROOT / "logs" / "visibility-actions.jsonl"

sys.path.insert(0, str(SCRIPT_DIR))


def _module(name: str, filename: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, str(SCRIPT_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _released_wave_repos(levers_path: Path) -> set[str]:
    """Repos sanctioned by a RELEASED publish-wave lever (id L-PORTAL-PUBLISH-*, status released,
    unlocks = the repo list). The lever file is his registry — this script only reads it."""
    try:
        data = json.loads(levers_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    levers = data.get("levers", data) if isinstance(data, dict) else data
    out: set[str] = set()
    for lv in levers if isinstance(levers, list) else []:
        if (
            isinstance(lv, dict)
            and str(lv.get("id") or "").startswith("L-PORTAL-PUBLISH-")
            and str(lv.get("status") or "").strip().lower() == "released"
            and isinstance(lv.get("unlocks"), list)
        ):
            out.update(str(r) for r in lv["unlocks"] if isinstance(r, str))
    return out


def _plan(estate: dict, rows: list[dict], gitvs) -> list[dict]:
    """Drift rows: (repo, direction) where desired class visibility ≠ observed."""
    classes = estate.get("classes") or {}
    plan: list[dict] = []
    for row in rows:
        full = str(row.get("full_name") or "")
        cls_name = gitvs.classify_repo(full, estate, facts=row)
        desired = (classes.get(cls_name) or {}).get("visibility") if cls_name else None
        if desired not in ("public", "private"):
            continue
        observed = "private" if row.get("private") else "public"
        if desired == observed:
            continue
        plan.append(
            {
                "repo": full,
                "class": cls_name,
                "action": "publish" if desired == "public" else "demote",
            }
        )
    return sorted(plan, key=lambda p: (p["action"], p["repo"]))


def _flip(repo: str, to: str) -> str:
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return "skipped (offline)"
    r = subprocess.run(
        ["gh", "repo", "edit", repo, "--visibility", to, "--accept-visibility-change-consequences"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return "flipped" if r.returncode == 0 else f"FAILED ({(r.stderr or '').strip()[:120]})"


def _log(entry: dict) -> None:
    try:
        ACTIONS.parent.mkdir(parents=True, exist_ok=True)
        entry["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with ACTIONS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except Exception:
        pass  # a receipt write must never break the effector


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Converge repo visibility toward the estate registry.")
    ap.add_argument("--apply", action="store_true", help="execute (demote auto; publish triple-gated)")
    ap.add_argument("--check", action="store_true", help="exit 0 ⟺ no actionable drift")
    ap.add_argument("--facts", help="(test seam) census-facts JSON path override")
    ap.add_argument("--levers", help="(test seam) levers JSON path override")
    args = ap.parse_args(argv)

    gitvs = _module("gitvs", "gitvs.py")
    publish_sweep = _module("publish_sweep", "publish-sweep.py")
    estate = gitvs.load_estate()

    facts_path = Path(args.facts) if args.facts else gitvs.FACTS
    try:
        rows = json.loads(facts_path.read_text(encoding="utf-8"))["repos"]
    except Exception:
        print("[apply-visibility] no census facts — run `gitvs.py census` first (skip, fail-open)")
        return 0

    plan = _plan(estate, rows, gitvs)
    if not plan:
        print("[apply-visibility] visibility drift == ∅ — nothing to converge")
        return 0
    if args.check:
        print(f"[apply-visibility] {len(plan)} visibility drift(s) actionable — run the effector")
        for p in plan[:10]:
            print(f"   {p['action']:7s} {p['repo']} (class {p['class']})")
        return 1

    armed_publish = bool(args.apply) and os.environ.get("LIMEN_VISIBILITY_APPLY") == "1"
    wave = _released_wave_repos(Path(args.levers) if args.levers else ROOT / "his-hand-levers.json")
    cap = int(os.environ.get("LIMEN_VISIBILITY_MAX", "10"))
    done = 0
    mode = "APPLY" if args.apply else "plan (dry)"
    print(f"[apply-visibility] {mode}: {len(plan)} drift(s), cap {cap}")
    for p in plan:
        repo, action = p["repo"], p["action"]
        if done >= cap:
            print(f"   ~ held  {action} {repo} — per-run cap reached")
            continue
        if action == "demote":
            if args.apply:
                result = _flip(repo, "private")
                done += 1
                _log({**p, "result": result, "mode": "apply"})
                print(f"   ✓ demote {repo} → private ({result}) — leak-posture auto-guard")
            else:
                print(f"   · would demote {repo} → private (auto under --apply)")
            continue
        # publish — the triple gate, evaluated loudest-first.
        if repo not in wave:
            print(f"   ~ held  publish {repo} — no released L-PORTAL-PUBLISH-* lever names it")
            continue
        ok, why = publish_sweep.receipt_fresh_green(repo)
        if not ok:
            print(f"   ~ held  publish {repo} — sweep receipt: {why}")
            continue
        if not armed_publish:
            print(f"   ~ held  publish {repo} — dark (needs --apply AND LIMEN_VISIBILITY_APPLY=1)")
            continue
        result = _flip(repo, "public")
        done += 1
        _log({**p, "result": result, "mode": "apply", "receipt": why})
        print(f"   ✓ publish {repo} → public ({result}) — lever-released, sweep green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
