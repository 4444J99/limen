#!/usr/bin/env python3
"""Report visibility drift without executing legacy estate-wide visibility changes.

The September portfolio-contraction decision supersedes July build-in-public.
Owner globs, publish_candidate and a green secret scan are not publication approval.
The legacy --apply interface fails closed in BOTH directions, even when armed.
Reviewed one-repository administrative changes remain explicit operations with
private custody, public-reference, privacy, cost and postflight evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.resolve()

sys.path.insert(0, str(SCRIPT_DIR))


def _module(name: str, filename: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, str(SCRIPT_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _plan(estate: dict, rows: list[dict], gitvs, receipt_ok) -> list[dict]:
    """Report proposals only; candidacy and class membership never authorize a flip."""
    classes = estate.get("classes") or {}
    overrides = estate.get("repo_overrides") or {}
    plan: list[dict] = []
    for row in rows:
        full = str(row.get("full_name") or "")
        cls_name = gitvs.classify_repo(full, estate, facts=row)
        desired = (classes.get(cls_name) or {}).get("visibility") if cls_name else None
        publish_candidate = bool((overrides.get(full) or {}).get("publish_candidate"))
        if publish_candidate:
            desired = "public"  # a reportable proposal, never mutation authority
        if desired not in ("public", "private"):
            continue
        observed = "private" if row.get("private") else "public"
        if desired == observed:
            if publish_candidate and observed == "public":
                ok, why = receipt_ok(full)
                leak = not ok and why == "receipt red"
                plan.append(
                    {
                        "repo": full,
                        "class": cls_name,
                        "action": "demote" if leak else "sweep",
                        "why": (
                            "publish-sweep RED on live-public history; reviewed containment required"
                            if leak
                            else f"publication review required; secret sweep alone is insufficient ({why})"
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Report repository visibility for individual review.")
    ap.add_argument("--apply", action="store_true", help="legacy interface; refuses automatic visibility changes")
    ap.add_argument("--check", action="store_true", help="exit 1 when review or visibility drift remains")
    ap.add_argument("--facts", help="census-facts JSON path override")
    args = ap.parse_args(argv)

    # Run before any census, receipt, API or environment handling. Neither an
    # old cron command nor all legacy arming flags may bypass the contraction.
    if args.apply:
        print("[apply-visibility] held: automatic visibility changes are disabled; "
              "use one privately recorded repository review and explicit administrative action")
        return 2

    gitvs = _module("gitvs", "gitvs.py")
    publish_sweep = _module("publish_sweep", "publish-sweep.py")
    estate = gitvs.load_estate()
    facts_path = Path(args.facts) if args.facts else gitvs.FACTS
    try:
        rows = json.loads(facts_path.read_text(encoding="utf-8"))["repos"]
    except (OSError, ValueError, KeyError):
        print("[apply-visibility] no readable census facts; visibility is unmeasured")
        return 1

    plan = _plan(estate, rows, gitvs, publish_sweep.receipt_fresh_green)
    if not plan:
        print("[apply-visibility] visibility drift == ∅ — nothing to review")
        return 0
    print(f"[apply-visibility] review-only: {len(plan)} finding(s); zero mutations")
    for p in plan:
        if p["action"] == "demote":
            print(f"   · would demote {p['repo']} → private after individual review — {p['why']}")
        elif p["action"] == "sweep":
            print(f"   ! sweep  {p['repo']} — {p['why']}")
        else:
            print(f"   ~ held  publish {p['repo']} — individual public-admission review required")
    return 1 if args.check else 0


if __name__ == "__main__":
    raise SystemExit(main())
