"""consolidate — produce financial dashboard artifacts from entity registry + live data.

Reads:
  - entities.yaml          (this directory — entity registry + account classification)
  - balances-history.json  (this directory — persistent balance time-series journal)
  - revenue-ladder.json    (root — product revenue pipeline)
  - obligations-ledger.json (root — obligations surfaced by mail organ)

Writes (to organs/financial/):
  - balances-history.json  Append-only balance snapshot journal
  - balance-sheet.md       Consolidated net position with asset/liability breakdown
  - cashflow.md            Rolling cash-flow projection (12-week horizon)
  - STATUS.md              One-page dashboard

Writes (to web/app/public/):
  - financial-standing.json  Machine-readable dashboard face

Usage:
  python3 organs/financial/consolidate.py

The organ's generator beat (financial-organ.py) calls this on cadence.
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml as _yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[2]))
HERE = ROOT / "organs" / "financial"
WEB_FACE = ROOT / "web" / "app" / "public"

ACCOUNT_CLASSIFICATION = {
    "checking": "asset",
    "savings": "asset",
    "credit": "liability",
    "investment": "asset",
    "cash": "asset",
    "receivable": "asset",
    "payable": "liability",
    "crypto": "asset",
    "loan": "liability",
    "mortgage": "liability",
    "retirement": "asset",
}


def load_json(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    if HAS_YAML:
        with open(path) as f:
            return _yaml.safe_load(f) or {}
    return {}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def classify_account(acct_type: str) -> str:
    return ACCOUNT_CLASSIFICATION.get(acct_type, "asset")


def load_balance_journal() -> list:
    path = HERE / "balances-history.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return data.get("snapshots", [])
        except (json.JSONDecodeError, OSError):
            return []
    return []


def append_balance_journal(snapshots: list, entities: dict) -> list:
    now = today_str()
    entity_list = entities.get("entities", [])
    balances = {}
    for ent in entity_list:
        eid = ent.get("id", "?")
        for acct in ent.get("accounts", []):
            aid = acct.get("id", "?")
            key = f"{eid}:{aid}"
            balances[key] = {
                "balance": acct.get("balance"),
                "balance_known": acct.get("balance_known", False),
                "as_of": acct.get("as_of"),
                "type": acct.get("type"),
            }
    if snapshots and snapshots[-1].get("balances") == balances:
        return snapshots
    snapshots.append({
        "date": now,
        "generated_at": now_iso(),
        "balances": balances,
    })
    return snapshots


def write_balance_journal(snapshots: list) -> bool:
    path = HERE / "balances-history.json"
    content = {
        "schema": "1.0",
        "snapshots": snapshots,
    }
    try:
        existing = json.loads(path.read_text()) if path.exists() else {}
    except (json.JSONDecodeError, OSError):
        existing = {}
    if existing.get("snapshots") == snapshots:
        return False
    path.write_text(json.dumps(content, indent=2))
    return True


def classify_balances(snapshots: list, classification: dict) -> dict:
    if not snapshots:
        return {}
    latest = snapshots[-1]["balances"]
    assets = []
    liabilities = []
    total_assets = 0.0
    total_liabilities = 0.0
    known_assets = 0
    known_liabilities = 0
    unknown_count = 0

    for key, val in latest.items():
        acct_type = val.get("type", "checking")
        cls = classification.get(acct_type, "asset")
        bal = val.get("balance")
        bal_known = val.get("balance_known", False) and bal is not None
        entry = {
            "key": key,
            "balance": bal,
            "balance_known": bal_known,
            "type": acct_type,
            "classification": cls,
        }
        if cls == "asset":
            assets.append(entry)
            if bal_known:
                known_assets += 1
                total_assets += float(bal)
        else:
            liabilities.append(entry)
            if bal_known:
                known_liabilities += 1
                total_liabilities += float(bal)
        if not bal_known:
            unknown_count += 1

    net_worth = total_assets - total_liabilities if (known_assets or known_liabilities) else None

    snap_count = len(snapshots)
    prev_net_worth = None
    if snap_count >= 2:
        prev = snapshots[-2]["balances"]
        prev_assets = 0.0
        prev_liabilities = 0.0
        for key, val in prev.items():
            acct_type = val.get("type", "checking")
            cls = classification.get(acct_type, "asset")
            bal = val.get("balance")
            bal_known = val.get("balance_known", False) and bal is not None
            if not bal_known:
                continue
            if cls == "asset":
                prev_assets += float(bal)
            else:
                prev_liabilities += float(bal)
        prev_net_worth = prev_assets - prev_liabilities if (prev_assets or prev_liabilities) else None

    return {
        "assets": assets,
        "liabilities": liabilities,
        "total_assets": total_assets if known_assets > 0 else None,
        "total_liabilities": total_liabilities if known_liabilities > 0 else None,
        "net_worth": net_worth,
        "prev_net_worth": prev_net_worth,
        "known_assets": known_assets,
        "known_liabilities": known_liabilities,
        "unknown_count": unknown_count,
        "snapshot_count": snap_count,
        "latest_date": snapshots[-1]["date"] if snapshots else None,
    }


def build_balance_sheet(
    entities: dict, revenue: dict, obligations: dict, classified: dict
) -> str:
    lines = []
    lines.append("# Financial Office — Consolidated Balance Sheet")
    lines.append("")
    lines.append(f"> Generated: {now_iso()}")
    lines.append("> *Advisory estimate. Balances marked `-` need principal entry.")
    lines.append("")

    headroom = _net_worth_trend(classified)
    if headroom:
        lines.append(f"> {headroom}")
        lines.append("")

    lines.append("## Net Worth")
    lines.append("")
    nw = classified.get("net_worth")
    prev = classified.get("prev_net_worth")
    if nw is not None:
        direction = ""
        if prev is not None and prev != 0:
            pct = ((nw - prev) / abs(prev)) * 100
            direction = f" (prev: ${prev:,.2f}, {pct:+.1f}%)"
        lines.append(f"- **Net worth:** **${nw:,.2f}**{direction}")
    else:
        lines.append("- **Net worth:** *(no known balances — enter data in entities.yaml)*")
    lines.append("")

    lines.append("## Assets")
    lines.append("")
    lines.append("| Account | Type | Balance | Status |")
    lines.append("|---|---|---|---|")
    total_a = 0.0
    a_known = 0
    for a in classified.get("assets", []):
        bal = a.get("balance")
        known = a.get("balance_known", False)
        if known and bal is not None:
            total_a += float(bal)
            a_known += 1
            bal_str = f"${float(bal):,.2f}"
            status = "✓"
        else:
            bal_str = "-"
            status = "(needs entry)"
        lines.append(f"| {a['key']} | {a['type']} | {bal_str} | {status} |")
    lines.append(f"| **Total Assets** | | **${total_a:,.2f}** | {a_known} known |")
    lines.append("")

    lines.append("## Liabilities")
    lines.append("")
    lines.append("| Account | Type | Balance | Status |")
    lines.append("|---|---|---|---|")
    total_l = 0.0
    l_known = 0
    for a in classified.get("liabilities", []):
        bal = a.get("balance")
        known = a.get("balance_known", False)
        if known and bal is not None:
            total_l += float(bal)
            l_known += 1
            bal_str = f"${float(bal):,.2f}"
            status = "✓"
        else:
            bal_str = "-"
            status = "(needs entry)"
        lines.append(f"| {a['key']} | {a['type']} | {bal_str} | {status} |")
    lines.append(f"| **Total Liabilities** | | **${total_l:,.2f}** | {l_known} known |")
    lines.append("")

    if nw is not None:
        lines.append("### Net Worth Summary")
        lines.append("")
        lines.append(f"| | Amount |")
        lines.append("|---|---|")
        lines.append(f"| Total Assets | ${total_a:,.2f} |")
        lines.append(f"| Total Liabilities | ${total_l:,.2f} |")
        lines.append(f"| **Net Worth** | **${nw:,.2f}** |")
        lines.append("")

    lines.append("### Balance History (snapshots)")
    sc = classified.get("snapshot_count", 0)
    lines.append(f"- **Snapshots recorded:** {sc}")
    lines.append(f"- **Latest:** {classified.get('latest_date', '-')}")
    if sc >= 2:
        lines.append(
            "- **Trend tracking active** — run consolidate.py each beat to record changes"
        )
    else:
        lines.append(
            "- **First snapshot recorded** — trend data will appear after the next beat"
        )
    lines.append("")

    return "\n".join(lines)


def _net_worth_trend(classified: dict) -> str | None:
    nw = classified.get("net_worth")
    prev = classified.get("prev_net_worth")
    if nw is not None and prev is not None and prev != 0:
        direction = "📈 up" if nw > prev else "📉 down"
        pct = ((nw - prev) / abs(prev)) * 100
        return f"**Trend:** Net worth {direction} {pct:+.1f}% since last snapshot (${prev:,.2f} → ${nw:,.2f})"
    return None


def build_cashflow(
    entities: dict, revenue: dict, obligations: dict, classified: dict
) -> str:
    lines = []
    lines.append("# Financial Office — Rolling Cash-Flow Projection")
    lines.append("")
    lines.append(f"> Generated: {now_iso()}")
    lines.append(
        "> *Forward-looking estimate based on known revenue stages and obligations."
    )
    lines.append(
        "> Confidence increases as more balances and obligation amounts are confirmed.*"
    )
    lines.append("")

    products = revenue.get("products", [])
    lines.append("## Revenue Pipeline")
    lines.append("")
    lines.append("| Rank | Product | Stage | Path to First Dollar |")
    lines.append("|---|---|---|---|")
    for prod in sorted(products, key=lambda p: p.get("rank", 99)):
        rank = prod.get("rank", "?")
        name = prod.get("product", "?")
        stage = prod.get("stage", "?")
        path = prod.get("first_dollar_path", "TBD")
        lines.append(f"| {rank} | {name} | {stage} | {path} |")
    lines.append("")

    start = datetime.now(timezone.utc)
    lines.append("## 12-Week Rolling Projection")
    lines.append("")
    lines.append(
        "| Week | Starting | Known Inflows | Known Outflows | Net | Cumulative | Note |"
    )
    lines.append("|---|---|---|---|---|---|---|")

    oblist = obligations.get("obligations", [])
    financial_obs = [o for o in oblist if o.get("rung") == "protocol"]

    cumulative = 0.0
    for w in range(12):
        week_start = (start + timedelta(weeks=w)).strftime("%Y-%m-%d")
        week_label = f"W{w + 1}"
        inflows = 0.0
        outflows = 0.0
        notes = []

        deploy_week = 2
        if w >= deploy_week and any(
            p.get("stage") in ("deploy-ready", "live") for p in products
        ):
            notes.append("post-deploy")

        cumulative += inflows - outflows
        net_str = f"${inflows - outflows:+.2f}"
        cum_str = f"${cumulative:+.2f}"
        inflow_str = "—" if inflows == 0 else f"${inflows:.2f}"
        outflow_str = "—" if outflows == 0 else f"${outflows:.2f}"
        note_str = "; ".join(notes) if notes else ""
        if w == 0 and not any(p.get("stage") in ("deploy-ready", "live") for p in products):
            note_str = "Pre-revenue — deploy Exporter to start pipeline"
        lines.append(
            f"| {week_label} | {week_start} | {inflow_str} | {outflow_str} | {net_str} | {cum_str} | {note_str} |"
        )

    lines.append("")

    nw = classified.get("net_worth")
    lines.append("### Runway")
    lines.append("")
    if nw is not None:
        lines.append(f"- **Current net position:** ${nw:,.2f}")
    else:
        lines.append(
            "- **Current net position:** Unknown — set balances in `entities.yaml` to enable runway calculation."
        )
    lines.append("- **Threshold:** < 4 weeks of obligations = alert principal.")
    lines.append("")

    lines.append("## Obligations (financial-material)")
    lines.append("")
    lines.append(
        f"Sourced from `obligations-ledger.json` — {len(financial_obs)} protocol-class obligations:"
    )
    lines.append("")
    lines.append("| Priority | Title | Owner | Next Step |")
    lines.append("|---|---|---|---|")
    for ob in sorted(
        financial_obs, key=lambda o: o.get("priority", 50), reverse=True
    ):
        title = ob.get("title", "?")
        priority = ob.get("priority", "?")
        owner = ob.get("owner", "?")
        step = ob.get("next_step", "Review")
        lines.append(f"| {priority} | {title} | {owner} | {step} |")
    lines.append("")

    return "\n".join(lines)


def _maturity_from_ladder() -> str:
    ladder_path = ROOT / "organ-ladder.json"
    try:
        if ladder_path.exists():
            with open(ladder_path) as f:
                data = json.load(f)
            for o in data.get("organs") or []:
                if o.get("pillar") == "financial":
                    m = o.get("maturity", "?")
                    s = o.get("stage", "?")
                    return f"**Maturity:** {s} ({m}%)"
    except Exception:
        pass
    return "**Maturity:** unknown"


def build_dashboard(
    entities: dict, revenue: dict, obligations: dict, classified: dict
) -> str:
    entity_list = entities.get("entities", [])
    products = revenue.get("products", [])
    oblist = obligations.get("obligations", [])

    lines = []
    lines.append("# Financial Office — STATUS Dashboard")
    lines.append("")
    lines.append(f"**Generated:** {now_iso()}  {_maturity_from_ladder()}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## At a glance")
    lines.append("")
    deployed_revenue = [
        p
        for p in products
        if p.get("stage") in ("deploy-ready", "live", "monetized")
    ]

    nw = classified.get("net_worth")
    nw_str = f"${nw:,.2f}" if nw is not None else "unknown"
    prev_nw = classified.get("prev_net_worth")
    trend = ""
    if nw is not None and prev_nw is not None and prev_nw != 0:
        pct = ((nw - prev_nw) / abs(prev_nw)) * 100
        trend = f" ({pct:+.1f}% vs prev)"
    sc = classified.get("snapshot_count", 0)

    lines.append(f"- **Entities tracked:** {len(entity_list)}")
    lines.append(
        f"- **Revenue products:** {len(products)} ({len(deployed_revenue)} deploy-ready or live)"
    )
    lines.append(f"- **Open obligations:** {len(oblist)}")
    lines.append(f"- **Net worth:** {nw_str}{trend}")
    lines.append(f"- **Balance snapshots:** {sc}")
    lines.append(
        f"- **First dollar path:** ChatGPT Exporter → MONETA/Ko-fi (deploy-ready, principal-gated)"
    )
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("| Artifact | File | Status |")
    lines.append("|---|---|---|")
    lines.append(
        "| Entity Registry | `entities.yaml` | Live — {} entities registered |".format(
            len(entity_list)
        )
    )
    has_balances = classified.get("known_assets", 0) + classified.get(
        "known_liabilities", 0
    )
    bs_status = (
        "Live — {} known balances".format(has_balances) if has_balances else "Generated — needs principal balance entry"
    )
    lines.append(f"| Balance Sheet | `balance-sheet.md` | {bs_status} |")
    lines.append("| Cash-Flow Projection | `cashflow.md` | Generated — pre-revenue baseline |")
    lines.append("| Payrail Disbursement Map | `payrail.md` | Authored — all 4 hops mapped |")
    lines.append(
        "| Balance History | `balances-history.json` | {} snapshot(s) recorded |".format(sc)
    )
    lines.append(
        "| Financial Dashboard (JSON) | `web/app/public/financial-standing.json` | {} |".format(
            "Live" if (WEB_FACE / "financial-standing.json").exists() else "Generated"
        )
    )
    lines.append(
        "| Obligations Ledger | `../../obligations-ledger.json` | Live — mail organ feed |"
    )
    lines.append(
        "| Revenue Ladder | `../../revenue-ladder.json` | Live — conductor beat |"
    )
    lines.append("")
    lines.append("## Next deepen steps")
    lines.append("")
    lines.append(
        "1. **Enter balances** — principal fills `balance` + `as_of` in `entities.yaml` (unlocks real position tracking)"
    )
    lines.append(
        "2. **Deploy Exporter** — first dollar via MONETA or Ko-fi (unlocks revenue pipeline)"
    )
    lines.append(
        "3. ✅ **Self-feed wired** — `financial-organ.py` runs every 8 beats; auto-advances maturity as slices land"
    )
    lines.append(
        "4. ✅ **Web JSON dashboard** — `financial-standing.json` written to web face each beat"
    )
    lines.append(
        "5. ✅ **Balance journal** — `balances-history.json` persists time-series of snapshots"
    )
    lines.append(
        "6. **Add credit accounts** — credit cards, loans, mortgages to entity registry"
    )
    lines.append(
        "7. **Investment accounts** — brokerage, retirement, crypto wallets"
    )
    lines.append("")

    return "\n".join(lines)


def build_web_dashboard(entities: dict, classified: dict) -> dict:
    entity_list = entities.get("entities", [])
    return {
        "ts": now_iso(),
        "date": today_str(),
        "net_worth": classified.get("net_worth"),
        "prev_net_worth": classified.get("prev_net_worth"),
        "total_assets": classified.get("total_assets"),
        "total_liabilities": classified.get("total_liabilities"),
        "known_asset_accounts": classified.get("known_assets", 0),
        "known_liability_accounts": classified.get("known_liabilities", 0),
        "unknown_accounts": classified.get("unknown_count", 0),
        "entity_count": len(entity_list),
        "snapshot_count": classified.get("snapshot_count", 0),
        "latest_snapshot_date": classified.get("latest_date"),
        "maturity": _maturity_from_ladder(),
    }


def comparable_content(text: str) -> str:
    text = re.sub(r"^(> Generated:) \S+$", r"\1 <generated>", text, flags=re.MULTILINE)
    return re.sub(
        r"^(\*\*Generated:\*\*) \S+(\s+\*\*Maturity:\*\*)",
        r"\1 <generated>\2",
        text,
        flags=re.MULTILINE,
    )


def write_if_changed(path: Path, content: str) -> bool:
    try:
        existing = path.read_text()
    except OSError:
        existing = None
    if existing is not None and comparable_content(existing) == comparable_content(content):
        return False
    path.write_text(content)
    return True


def write_json_if_changed(path: Path, data: dict) -> bool:
    content = json.dumps(data, indent=2)
    try:
        existing = path.read_text()
        if existing.rstrip() == content.rstrip():
            return False
    except OSError:
        pass
    path.write_text(content)
    return True


def main() -> int:
    entities = load_yaml(HERE / "entities.yaml")
    revenue = load_json(ROOT / "revenue-ladder.json")
    obligations = load_json(ROOT / "obligations-ledger.json")

    classification = load_yaml(HERE / "entities.yaml").get(
        "account_classification", ACCOUNT_CLASSIFICATION
    ) or ACCOUNT_CLASSIFICATION

    snapshots = load_balance_journal()
    snapshots = append_balance_journal(snapshots, entities)
    if write_balance_journal(snapshots):
        print(f"[consolidate] wrote {HERE}/balances-history.json ({len(snapshots)} snapshots)")

    classified = classify_balances(snapshots, classification)

    artifacts = {
        "balance-sheet.md": build_balance_sheet(
            entities, revenue, obligations, classified
        ),
        "cashflow.md": build_cashflow(
            entities, revenue, obligations, classified
        ),
        "STATUS.md": build_dashboard(
            entities, revenue, obligations, classified
        ),
    }

    for filename, content in artifacts.items():
        path = HERE / filename
        if write_if_changed(path, content):
            print(f"[consolidate] wrote {path.relative_to(ROOT)} ({len(content)} chars)")
        else:
            print(f"[consolidate] unchanged {path.relative_to(ROOT)}")

    dashboard_json = build_web_dashboard(entities, classified)
    web_path = WEB_FACE / "financial-standing.json"
    WEB_FACE.mkdir(parents=True, exist_ok=True)
    if write_json_if_changed(web_path, dashboard_json):
        print(f"[consolidate] wrote {web_path.relative_to(ROOT)} (JSON dashboard face)")
    else:
        print(f"[consolidate] unchanged {web_path.relative_to(ROOT)}")

    print(f"[consolidate] done — {len(artifacts)} artifacts, {len(snapshots)} balance snapshots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
