#!/usr/bin/env python3
"""ledger — roll up the weighed records into the VALUE VERDICT. (Absorbs the dead ledger.sh stub.)

`score-dispatch.py` grades every resolved task (worth_it / marginal / wasted) into `logs/ledger.jsonl`.
This aggregates that into `logs/ledger.json` — the answer to "is the fleet earning its keep, or wasting
my money?":
  - per-lane scorecard : tasks, worth_it rate, sunk cost, cost-per-shipped → which vendor earns its keep
  - per-repo ROI       : spend vs. shipped value → which repos only ever burn money
  - revenue attribution: spend mapped onto revenue-ladder.json products → the dollar path
  - daily net verdict  : spent N, shipped M, wasted W → net WORTH IT / net WASTE + the worst offender

READ-ONLY on the fleet's data; writes only logs/ledger.json. Fail-open: prints what it can, never crashes.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
LEDGER_JSONL = LOGS / "ledger.jsonl"
LEDGER_JSON = LOGS / "ledger.json"
LADDER = ROOT / "revenue-ladder.json"


def _int_or_default(value, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _float_or_default(value, default: float) -> float:
    try:
        if isinstance(value, bool):
            return default
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _load_records() -> list[dict]:
    out: list[dict] = []
    if LEDGER_JSONL.exists():
        for ln in LEDGER_JSONL.read_text().splitlines():
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


def _revenue_repos() -> dict[str, str]:
    """repo -> product name, from the revenue ladder (so spend ties to the dollar path)."""
    try:
        d = json.loads(LADDER.read_text())
        return {p["repo"]: p.get("product", p["repo"]) for p in d.get("products", []) if p.get("repo")}
    except Exception:
        return {}


def _scorecard(records: list[dict]) -> dict:
    lanes: dict[str, dict] = defaultdict(lambda: {"tasks": 0, "worth_it": 0, "marginal": 0,
                                                   "wasted": 0, "spent": 0, "sunk": 0})
    repos: dict[str, dict] = defaultdict(lambda: {"spent": 0, "worth_it": 0, "wasted": 0, "sunk": 0})
    tot = {"tasks": 0, "worth_it": 0, "marginal": 0, "wasted": 0, "spent": 0, "sunk": 0}
    # per-(lane, class) tallies — class = task.type ∪ labels — so routing can steer a lane away from the
    # exact work-classes it wastes on, toward what it lands. [worth_it, total]
    klass: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    for r in records:
        g = r.get("grade")
        if g not in ("worth_it", "marginal", "wasted"):
            continue
        lane = r.get("lane") or "?"
        repo = r.get("repo") or "?"
        spent = _int_or_default(r.get("spent"), 0)
        sunk = _int_or_default(r.get("sunk"), 0)
        # tally this record against each of its classes (type + every label)
        classes = {c for c in ([r.get("type")] + list(r.get("labels") or [])) if c}
        for c in classes:
            cell = klass[lane][c]
            cell[1] += 1
            if g == "worth_it":
                cell[0] += 1
        for bucket, key in ((lanes[lane], None), (tot, None)):
            bucket["tasks"] += 1
            bucket[g] += 1
            bucket["spent"] += spent
            bucket["sunk"] += sunk
        repos[repo]["spent"] += spent
        repos[repo]["sunk"] += sunk
        if g == "worth_it":
            repos[repo]["worth_it"] += 1
        elif g == "wasted":
            repos[repo]["wasted"] += 1

    def _enrich(d: dict) -> dict:
        t = d["tasks"]
        d["success_rate"] = round(d["worth_it"] / t, 3) if t else 0.0
        d["cost_per_shipped"] = round(d["spent"] / d["worth_it"], 2) if d["worth_it"] else None
        return d

    lane_board = {k: _enrich(dict(v)) for k, v in lanes.items()}
    # waste/win classes: a lane WASTES a class if its worth-it rate there is below WASTE_RATE over a
    # meaningful volume (>= WASTE_MIN); it WINS a class above WIN_RATE. Routing reads these to shed the
    # waste-classes off the lane while keeping its winners. Thresholds env-tunable; data-driven, no pins.
    waste_rate = _float_or_default(os.environ.get("LIMEN_WASTE_RATE"), 0.34)
    win_rate = _float_or_default(os.environ.get("LIMEN_WIN_RATE"), 0.6)
    min_vol = _int_or_default(os.environ.get("LIMEN_WASTE_MIN"), 5) or 5
    for lane, board in lane_board.items():
        waste, win = [], []
        for c, (w, n) in klass.get(lane, {}).items():
            if n < min_vol:
                continue
            rate = w / n
            if rate < waste_rate:
                waste.append((c, n))
            elif rate >= win_rate:
                win.append((c, n))
        board["waste_classes"] = [c for c, _ in sorted(waste, key=lambda x: -x[1])]
        board["win_classes"] = [c for c, _ in sorted(win, key=lambda x: -x[1])]

    # rank lanes by earns-its-keep: high success rate, low cost-per-shipped, low sunk.
    ranked = sorted(lane_board.items(),
                    key=lambda kv: (-kv[1]["success_rate"], kv[1]["cost_per_shipped"] or 1e9, kv[1]["sunk"]))
    _enrich(tot)
    return {"lanes": lane_board, "lane_rank": [k for k, _ in ranked],
            "repos": dict(repos), "totals": tot}


def build() -> dict:
    records = _load_records()
    sc = _scorecard(records)
    tot = sc["totals"]
    rev = _revenue_repos()

    # revenue attribution: spend + ships on the actual product repos
    attribution = []
    for repo, name in rev.items():
        r = sc["repos"].get(repo)
        if r:
            attribution.append({"repo": repo, "product": name, "spent": r["spent"],
                                "shipped": r["worth_it"], "wasted": r["wasted"]})
    attribution.sort(key=lambda a: -a["spent"])

    # worst offender = repo with the most SUNK cost (money that bought nothing)
    worst = max(sc["repos"].items(), key=lambda kv: kv[1]["sunk"], default=(None, None))
    worst_repo = worst[0] if worst[1] and worst[1]["sunk"] > 0 else None

    shipped, wasted, spent, sunk = tot["worth_it"], tot["wasted"], tot["spent"], tot["sunk"]
    productive = spent - sunk
    net = "WORTH IT" if productive > sunk else ("WASTE" if sunk > productive else "EVEN")
    verdict = (f"net {net} — {shipped} shipped, {wasted} wasted; "
               f"{productive} of {spent} debits productive, {sunk} sunk"
               + (f"; worst sink = {worst_repo}" if worst_repo else ""))

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "net": net,
        "totals": tot,
        "lane_rank": sc["lane_rank"],
        "lanes": sc["lanes"],
        "revenue_attribution": attribution,
        "worst_sink": worst_repo,
        "records": len(records),
    }


def main() -> int:
    rep = build()
    LEDGER_JSON.parent.mkdir(exist_ok=True)
    try:
        LEDGER_JSON.write_text(json.dumps(rep, indent=2))
    except OSError as e:
        print(f"ledger: could not write {LEDGER_JSON} ({e})")

    print(f"=== VALUE LEDGER ({rep['records']} weighed tasks) ===")
    print(rep["verdict"])
    print(f"\nlanes (best earns-its-keep first): {', '.join(rep['lane_rank'])}")
    for lane in rep["lane_rank"]:
        v = rep["lanes"][lane]
        cps = v["cost_per_shipped"]
        print(f"  {lane:9} {v['tasks']:4} tasks  "
              f"{int(v['success_rate']*100):3}% worth-it  "
              f"sunk {v['sunk']:4}  cost/ship {cps if cps is not None else '—'}")
    if rep["revenue_attribution"]:
        print("\nrevenue products (spend → ships):")
        for a in rep["revenue_attribution"]:
            print(f"  {a['product']:28} spent {a['spent']:4}  shipped {a['shipped']:3}  wasted {a['wasted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
