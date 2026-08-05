#!/usr/bin/env python3
"""conversion-funnel.py — name WHICH stage of the public-face funnel leaks.

The face is provable (the profile engine) — but provable != seen != converting. This fuses the
provable signals into one funnel and reports the single bottleneck, because that is what routes
Aug-1 ($10k/wk) effort:

    seen (gh /traffic)  ->  inbound (mailbox classification)  ->  revenue (deals)

Every number is sourced. A stage below its floor, walking top-down, IS the bottleneck:
  * seen < floor        -> DISCOVERY  (nobody's finding it: repos are proof, identity is discovery)
  * seen ok, inbound<f  -> FACE/OFFER (seen but not reaching out: tune the doors / the LinkedIn mirror)
  * inbound ok, rev<f   -> CLOSE      (leads but no deals: the sale)

    python scripts/conversion-funnel.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAFFIC = ROOT / "logs" / "observatory" / "traffic.jsonl"
OPP_STATUS = ROOT / "logs" / "opportunity-status.json"
OUT = ROOT / "logs" / "profile-conversion-funnel-latest.json"
LOGIN = "4444J99"

# Floors: the minimum at each stage below which THAT stage is the constraint. Modest, honest.
GATES = {
    "seen_uniques_14d": 200,      # enough eyeballs to reasonably expect a lead
    "inbound_leads_month": 1,     # at least one real inbound conversation a month
    "revenue_weekly_usd": 10000,  # the Aug-1 north star
}


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def gh_json(path: str, *, timeout: int = 30):
    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True,
                          timeout=timeout, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "gh failed").strip().splitlines()[-1][:160])
    return json.loads(proc.stdout or "null")


def latest_traffic() -> list[dict]:
    """Most recent snapshot per repo from the traffic ledger."""
    if not TRAFFIC.exists():
        return []
    by_repo: dict[str, dict] = {}
    for line in TRAFFIC.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        prev = by_repo.get(r["repo"])
        if prev is None or r.get("fetched_at", "") >= prev.get("fetched_at", ""):
            by_repo[r["repo"]] = r
    return list(by_repo.values())


def _ok(block) -> bool:
    return isinstance(block, dict) and "_error" not in block


def seen_stage(rows: list[dict]) -> dict:
    views = uniques = zero_view_repos = 0
    channels: Counter = Counter()
    per_repo = []
    for r in rows:
        v = r.get("views", {})
        if not _ok(v):
            continue
        vc, vu = int(v.get("count", 0) or 0), int(v.get("uniques", 0) or 0)
        views += vc
        uniques += vu
        if vu == 0:
            zero_view_repos += 1
        for ref in (r.get("referrers") or []):
            if isinstance(ref, dict) and ref.get("referrer"):
                channels[ref["referrer"]] += int(ref.get("uniques", 0) or 0)
        per_repo.append({"repo": r["repo"], "views": vc, "uniques": vu})
    per_repo.sort(key=lambda x: -x["uniques"])
    return {
        "views_14d": views,
        "unique_visitors_14d": uniques,
        "repos_measured": len(per_repo),
        "repos_with_zero_views": zero_view_repos,
        "discovery_channels": [{"channel": c, "uniques": n} for c, n in channels.most_common(8)],
        "top_repos": per_repo[:5],
        "source": "gh api repos/<r>/traffic/views + popular/referrers (scripts/traffic-collect.py)",
    }


def inbound_stage() -> dict:
    """Inbound leads from the mailbox classification (UMA obligations → opportunity-status.json)."""
    if not OPP_STATUS.exists():
        return {"leads_total": 0, "available": False,
                "note": "logs/opportunity-status.json absent — run the mail sweep; LinkedIn mirror likely OFF",
                "source": "scripts/opportunity-review-delta.py -> logs/opportunity-status.json"}
    try:
        d = json.loads(OPP_STATUS.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"leads_total": 0, "available": False, "note": f"unparseable: {exc}"}
    counts = d.get("counts", d)
    lead_keys = ["inbound-lead-hire", "inbound-lead-deploy", "inbound-linkedin"]
    by_class = {k: int(counts.get(k, 0) or 0) for k in lead_keys}
    return {
        "leads_total": sum(by_class.values()),
        "by_class": by_class,
        "available": True,
        "mirror_silence": d.get("mirror_silence"),
        "source": "scripts/opportunity-review-delta.py -> logs/opportunity-status.json (PII-clean counts)",
    }


def context() -> dict:
    followers = _try(lambda: int(gh_json(f"users/{LOGIN}").get("followers", 0)))
    return {"followers": followers, "source": f"gh api users/{LOGIN} .followers"}


def _try(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def diagnose(seen: dict, inbound: dict) -> dict:
    """Top-down: the first stage below its floor is the single bottleneck to attack."""
    if seen["unique_visitors_14d"] < GATES["seen_uniques_14d"]:
        return {
            "stage": "DISCOVERY",
            "why": f"{seen['unique_visitors_14d']} unique visitors/14d across {seen['repos_measured']} "
                   f"value-repos (floor {GATES['seen_uniques_14d']}); {seen['repos_with_zero_views']} repos "
                   f"have ZERO views. The face is provable but essentially unseen.",
            "route": "Drive DISCOVERY, not more building. Repos are PROOF, identity is the discovery path "
                     "(moat-audit #360): LinkedIn/outreach + SEO. Organs: opportunity-engine, niche-funnel. "
                     "Only public-record-data-scrapper pulls search referrals — replicate that SEO across the value-repos.",
        }
    if inbound["leads_total"] < GATES["inbound_leads_month"]:
        return {
            "stage": "FACE/OFFER",
            "why": f"seen is adequate ({seen['unique_visitors_14d']} uniques/14d) but inbound is "
                   f"{inbound['leads_total']} leads (floor {GATES['inbound_leads_month']}/mo). Visitors aren't "
                   "reaching out.",
            "route": "Tune the two-door CTAs / the offer; turn the LinkedIn mirror ON (LIMEN_MAIL_DRAFTS=1) "
                     "so inbound is even captured.",
        }
    return {
        "stage": "CLOSE",
        "why": f"leads exist ({inbound['leads_total']}) but revenue is below ${GATES['revenue_weekly_usd']}/wk.",
        "route": "The constraint is the SALE — qualification + close, not the face.",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Diagnose the public-face conversion funnel's bottleneck.")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    rows = latest_traffic()
    if not rows:
        print("conversion-funnel: no traffic data — run scripts/traffic-collect.py first", flush=True)
        return 2

    seen = seen_stage(rows)
    inbound = inbound_stage()
    ctx = context()
    bottleneck = diagnose(seen, inbound)

    report = {
        "_doc": "Public-face conversion funnel. Every number is sourced (see each stage's `source`). "
                "The `bottleneck` is the single stage to attack for the Aug-1 $10k/wk gate.",
        "generated": _now(),
        "gates": GATES,
        "funnel": {"seen": seen, "inbound": inbound, "revenue": {"weekly_usd": 0, "available": False,
                                                                 "note": "no deal instrument yet"}},
        "context": ctx,
        "bottleneck": bottleneck,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"conversion-funnel: BOTTLENECK = {bottleneck['stage']}")
    print(f"  seen: {seen['unique_visitors_14d']} unique visitors/14d "
          f"({seen['repos_with_zero_views']}/{seen['repos_measured']} repos at zero) · "
          f"inbound: {inbound['leads_total']} leads · followers: {ctx.get('followers')}")
    print(f"  channels: {', '.join(c['channel'] for c in seen['discovery_channels']) or '(none)'}")
    print(f"  → {bottleneck['route']}")
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
