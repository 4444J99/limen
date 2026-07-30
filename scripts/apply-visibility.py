#!/usr/bin/env python3
"""apply-visibility.py — converge observed repo visibility toward the estate registry (class G's effector).

The GitOps direction: institutio/github/estate.yaml is desired-state; this script drives reality
toward it. The two directions carry ASYMMETRIC gates (autonomy is derived from reversibility):

  DEMOTE  desired private, observed public  — the standing leak-posture auto-guard. Reversible and
          protective: executes under --apply alone (the reconcile loop's LIMEN_GITVS_APPLY arming).
  PUBLISH desired public, observed private — irreversible exposure (history included). The
          build-in-public directive (2026-07-17) is the STANDING sanction — no per-repo lever (he
          will not click 90 gates; his directive IS the authorization). Gated on the REAL safety,
          evaluated loudest-first:
          (1) a green + fresh publish-sweep receipt (scripts/publish-sweep.py — FULL history swept);
          (2) DOUBLE-DARK: --apply AND LIMEN_VISIBILITY_APPLY=1 (the reap-remote-branches precedent).
          A `publish_candidate: true` override row is desired-public-PENDING-SWEEP (its
          operation_private class is nominally private; the green sweep — not a class flip —
          authorizes the flip).

Because candidacy is a CONDITIONAL desire, the two directions meet in a third case the effector was
blind to until 2026-07-30: a candidate already observed PUBLIC with no green+fresh receipt owning
the flip. Reading that as "converged" (desired == observed) is what let 32 operation-private repos
sit world-readable while every predicate reported green. It resolves by what the sweep actually
says, never by the bare absence of a receipt:

  SWEEP RED   a secret is exposed in live-public history — a genuine leak. Demote, auto-guard.
  NO RECEIPT  nobody has looked yet. UNKNOWN IS NOT UNSAFE: mass-demoting here would fight the
  or STALE    build-in-public directive, so this reports (reds --check, rides the beat) and routes
              to publish-sweep.py. The sweep adjudicates; the effector does not guess.
  GREEN+FRESH converged — the receipt legitimately owns the public posture.

Every action (and every held plan row) appends to logs/visibility-actions.jsonl. Fail-open, bounded
(LIMEN_VISIBILITY_MAX per run), offline → skip. Registered as the `repo` resource delegate effector
in estate.yaml — reconcile dispatches it; the gates above live HERE, never in the reconcile engine.

  python3 scripts/apply-visibility.py            # dry plan
  python3 scripts/apply-visibility.py --check    # sensor idiom: exit 0 ⟺ no actionable drift
  python3 scripts/apply-visibility.py --apply    # demote executes; publish needs sweep-green + double-dark
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


def _plan(estate: dict, rows: list[dict], gitvs, receipt_ok) -> list[dict]:
    """Drift rows: (repo, direction) where desired class visibility ≠ observed. A `publish_candidate`
    override is desired-public-pending-sweep, even when its class (operation_private) is nominally
    private — build-in-public: the green sweep, not the class, authorizes the flip.

    ``receipt_ok(repo) -> (bool, why)`` resolves that pending desire. It is needed HERE, not only at
    execution time, because the desire is conditional: an unswept candidate never earned
    desired-public, so an already-public one is an unauthorized flip, not a convergence."""
    classes = estate.get("classes") or {}
    overrides = estate.get("repo_overrides") or {}
    plan: list[dict] = []
    for row in rows:
        full = str(row.get("full_name") or "")
        cls_name = gitvs.classify_repo(full, estate, facts=row)
        desired = (classes.get(cls_name) or {}).get("visibility") if cls_name else None
        publish_candidate = bool((overrides.get(full) or {}).get("publish_candidate"))
        if publish_candidate:
            desired = "public"  # publish_candidate ⇒ desired-public (green sweep is the gate)
        if desired not in ("public", "private"):
            continue
        observed = "private" if row.get("private") else "public"
        if desired == observed:
            # Mirrors gitvs.visibility_drift's class-G citation: candidacy is a GATED desire, so
            # desired == observed == "public" only means converged when a receipt owns the flip.
            # The doctor names this case; this is the half that acts on it — and the ACTION splits
            # three ways, because receipt_fresh_green()'s single False hides three different worlds:
            #   red        → the sweep looked and FOUND a secret. A real leak: demote, auto-guard.
            #   no/stale   → nobody has looked. Unknown ≠ unsafe, and mass-demoting here would
            #                fight the standing build-in-public directive. Sweep it; the sweep
            #                adjudicates. Surfaced (so --check reds) but never flipped blind.
            #   green+fresh→ genuinely converged.
            if publish_candidate and observed == "public":
                ok, why = receipt_ok(full)
                if not ok:
                    leak = why == "receipt red"
                    plan.append(
                        {
                            "repo": full,
                            "class": cls_name,
                            "action": "demote" if leak else "sweep",
                            "why": (
                                "publish-sweep RED on a live-public candidate — history secret exposed"
                                if leak
                                else f"public candidate never cleared to be public ({why}) — sweep adjudicates"
                            ),
                        }
                    )
            continue
        plan.append(
            {
                "repo": full,
                "class": cls_name,
                "action": "publish" if desired == "public" else "demote",
                "why": f"class '{cls_name}' demands {desired}, observed {observed}",
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
    ap.add_argument("--apply", action="store_true", help="execute (demote auto; publish: sweep-green + double-dark)")
    ap.add_argument("--check", action="store_true", help="exit 0 ⟺ no actionable drift")
    ap.add_argument("--facts", help="(test seam) census-facts JSON path override")
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

    plan = _plan(estate, rows, gitvs, publish_sweep.receipt_fresh_green)
    if not plan:
        print("[apply-visibility] visibility drift == ∅ — nothing to converge")
        return 0
    if args.check:
        print(f"[apply-visibility] {len(plan)} visibility drift(s) actionable — run the effector")
        for p in plan[:10]:
            print(f"   {p['action']:7s} {p['repo']} (class {p['class']})")
        return 1

    armed_publish = bool(args.apply) and os.environ.get("LIMEN_VISIBILITY_APPLY") == "1"
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
            why = p.get("why") or "leak-posture auto-guard"
            if args.apply:
                result = _flip(repo, "private")
                done += 1
                _log({**p, "result": result, "mode": "apply"})
                print(f"   ✓ demote {repo} → private ({result}) — {why}")
            else:
                print(f"   · would demote {repo} → private (auto under --apply) — {why}")
            continue
        if action == "sweep":
            # Never a visibility flip: an unswept live-public candidate is UNKNOWN, not unsafe, and
            # the remedy is to look. Reported (so --check reds and the beat carries it) and routed
            # to its owner; publish-sweep.py --candidates is what clears or condemns it.
            _log({**p, "result": "reported", "mode": mode})
            print(f"   ! sweep  {repo} — {p.get('why')} → publish-sweep.py --repo {repo}")
            continue
        # publish — build-in-public: the directive is the standing sanction (no per-repo lever).
        # Gated on the REAL safety, loudest-first: a green+fresh sweep receipt, then double-dark arming.
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
        print(f"   ✓ publish {repo} → public ({result}) — sweep green, directive-armed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
