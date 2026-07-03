"""consolidate — produce financial dashboard artifacts from entity registry + live data.

Reads:
  - entities.yaml          (this directory)
  - revenue-ladder.json    (root — product revenue pipeline)
  - obligations-ledger.json (root — obligations surfaced by mail organ)

Writes (to organs/financial/):
  - balance-sheet.md       Consolidated net position across all entities
  - cashflow.md            Rolling cash-flow projection (12-week horizon)
  - STATUS.md              One-page dashboard

Usage:
  python3 organs/financial/consolidate.py

The organ's generator beat (C_FEED / organ-selffeed) should call this on cadence.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[2]))
HERE = ROOT / "organs" / "financial"


def load_json(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def load_yaml_simple(path: Path) -> dict:
    """Minimal YAML-like loader — reads key:value trees from the entities.yaml.
    For a production organ, use PyYAML; this avoids a dependency for now."""
    import re
    result = {}
    current_section = result
    section_stack = [result]
    with open(path) as f:
        for line in f:
            stripped = line.rstrip()
            if stripped.startswith("#") or not stripped.strip():
                continue
            indent = len(line) - len(line.lstrip())
            while len(section_stack) > indent // 2 + 1:
                section_stack.pop()
            current = section_stack[-1]
            m = re.match(r'^(\w[\w_-]*):\s*(.*)', stripped)
            if m:
                key, val = m.group(1), m.group(2).strip()
                if val == "":
                    current[key] = {}
                    section_stack.append(current[key])
                elif val.startswith("|"):
                    current[key] = val[1:].strip()
                else:
                    current[key] = val
            elif stripped.startswith("- "):
                m2 = re.match(r'^-\s+(\w[\w_-]*):\s*(.*)', stripped)
                if m2:
                    entry = {m2.group(1): m2.group(2).strip()}
                    if "entities" in current and isinstance(current.get("entities"), list):
                        current["entities"].append(entry)
                    elif "accounts" in current and isinstance(current.get("accounts"), list):
                        current["accounts"].append(entry)
    return result


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_balance_sheet(entities: dict, revenue: dict, obligations: dict) -> str:
    """Produce a Markdown balance sheet from entity data."""
    lines = []
    lines.append("# Financial Office — Consolidated Balance Sheet (MACRO template)")
    lines.append("")
    lines.append(f"> Generated: {now_iso()}")
    lines.append("> *This is an advisory estimate. Balances marked `unknown` need principal input.")
    lines.append("")
    lines.append("## Net Position by Entity")
    lines.append("")
    lines.append("| Entity | Type | Accounts | Known Balance | Status |")
    lines.append("|---|---|---|---|---|")

    total_known = 0.0
    total_unknown = 0
    entity_list = entities.get("entities", [])

    for ent in entity_list:
        eid = ent.get("id", "?")
        etype = ent.get("type", "?")
        ename = ent.get("name", eid)
        accounts = ent.get("accounts", [])
        known_balance = 0.0
        has_known = False
        account_count = len(accounts)
        for acct in accounts:
            bal = acct.get("balance")
            if bal is not None:
                known_balance += float(bal)
                has_known = True
        if has_known:
            total_known += known_balance
            balance_str = f"${known_balance:,.2f}"
            status = "current"
        else:
            total_unknown += 1
            balance_str = "*(needs entry)*"
            status = "unconfirmed"

        lines.append(f"| **{ename}** | {etype} | {account_count} | {balance_str} | {status} |")

    lines.append("")
    lines.append("### Totals")
    lines.append("")
    known_str = f"${total_known:,.2f}" if total_known > 0 else "— (no known balances)"
    lines.append(f"- **Known balances:** {known_str}")
    lines.append(f"- **Entities with unconfirmed balances:** {total_unknown}")
    lines.append(f"- **As of:** {today_str()}")
    lines.append("")
    lines.append("### Action items")
    lines.append("")
    lines.append("1. Enter current balances for each account in `entities.yaml` (field: `balance`)")
    lines.append("2. Set `balance_known: true` and `as_of: <date>` for each confirmed balance")
    lines.append("3. Re-run `consolidate.py` to refresh this sheet")
    lines.append("")

    return "\n".join(lines)


def build_cashflow(entities: dict, revenue: dict, obligations: dict) -> str:
    """Produce a rolling 12-week cash-flow projection."""
    lines = []
    lines.append("# Financial Office — Rolling Cash-Flow Projection")
    lines.append("")
    lines.append(f"> Generated: {now_iso()}")
    lines.append("> *Forward-looking estimate based on known revenue stages and obligations.")
    lines.append("> Confidence increases as more balances are confirmed.*")
    lines.append("")
    lines.append("## Assumptions")
    lines.append("")
    lines.append("- No revenue is yet flowing (all products pre-revenue or deploy-ready)")
    lines.append("- First revenue projected: ChatGPT Exporter (rank 1, deploy-ready)")
    lines.append("- Current obligations are drawn from `obligations-ledger.json`")
    lines.append("- All amounts are estimates until principal confirms")
    lines.append("")

    # Build product pipeline from revenue-ladder
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

    # 12-week rolling projection
    start = datetime.now(timezone.utc)
    lines.append("## 12-Week Rolling Projection")
    lines.append("")
    lines.append("| Week | Starting | Known Inflows | Known Outflows | Net | Cumulative | Note |")
    lines.append("|---|---|---|---|---|---|---|")

    cumulative = 0.0
    for w in range(12):
        week_start = (start + timedelta(weeks=w)).strftime("%Y-%m-%d")
        week_label = f"W{w+1}"
        # No known inflows until first product goes live
        inflows = 0.0
        outflows = 0.0  # unknown until obligations are quantified
        net = inflows - outflows
        cumulative += net
        net_str = f"${net:+.2f}"
        cum_str = f"${cumulative:+.2f}"
        inflow_str = "—" if inflows == 0 else f"${inflows:.2f}"
        outflow_str = "—" if outflows == 0 else f"${outflows:.2f}"
        note = "Pre-revenue — deploy Exporter to start pipeline" if w == 0 else ""
        lines.append(f"| {week_label} | {week_start} | {inflow_str} | {outflow_str} | {net_str} | {cum_str} | {note} |")

    lines.append("")
    lines.append("### Runway alert")
    lines.append("")
    lines.append("- **Current runway:** Unknown (no balance data). Set balances in `entities.yaml` to enable runway calculation.")
    lines.append("- **Threshold:** < 4 weeks of obligations = alert principal.")
    lines.append("")

    # Obligations summary
    oblist = obligations.get("obligations", [])
    financial_obs = [o for o in oblist if o.get("rung") == "protocol"]
    lines.append("## Obligations (financial-material)")
    lines.append("")
    lines.append(f"Sourced from `obligations-ledger.json` — {len(financial_obs)} protocol-class obligations:")
    lines.append("")
    lines.append("| Priority | Title | Owner | Next Step |")
    lines.append("|---|---|---|---|")
    for ob in sorted(financial_obs, key=lambda o: o.get("priority", 50), reverse=True):
        title = ob.get("title", "?")
        priority = ob.get("priority", "?")
        owner = ob.get("owner", "?")
        step = ob.get("next_step", "Review")
        lines.append(f"| {priority} | {title} | {owner} | {step} |")
    lines.append("")

    return "\n".join(lines)


def build_dashboard(entities: dict, revenue: dict, obligations: dict) -> str:
    """Produce the one-page STATUS.md dashboard."""
    entity_list = entities.get("entities", [])
    products = revenue.get("products", [])
    oblist = obligations.get("obligations", [])

    lines = []
    lines.append("# Financial Office — STATUS Dashboard")
    lines.append("")
    lines.append(f"**Generated:** {now_iso()}  **Maturity:** Building (30% → 40%)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## At a glance")
    lines.append("")
    deployed_revenue = [p for p in products if p.get("stage") in ("deploy-ready", "live", "monetized")]
    lines.append(f"- **Entities tracked:** {len(entity_list)}")
    lines.append(f"- **Revenue products:** {len(products)} ({len(deployed_revenue)} deploy-ready or live)")
    lines.append(f"- **Open obligations:** {len(oblist)}")
    lines.append(f"- **First dollar path:** ChatGPT Exporter → MONETA/Ko-fi (deploy-ready, principal-gated)")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("| Artifact | File | Status |")
    lines.append("|---|---|---|")
    lines.append("| Entity Registry | `entities.yaml` | Live — {} entities registered |".format(len(entity_list)))
    lines.append("| Balance Sheet | `balance-sheet.md` | Generated — needs principal balance entry |")
    lines.append("| Cash-Flow Projection | `cashflow.md` | Generated — pre-revenue baseline |")
    lines.append("| Payrail Disbursement Map | `payrail.md` | Authored — all 4 hops mapped |")
    lines.append("| Obligations Ledger | `../../obligations-ledger.json` | Live — mail organ feed |")
    lines.append("| Revenue Ladder | `../../revenue-ladder.json` | Live — conductor beat |")
    lines.append("")
    lines.append("## Next deepen steps")
    lines.append("")
    lines.append("1. **Enter balances** — principal fills `balance` + `as_of` in `entities.yaml`")
    lines.append("2. **Deploy Exporter** — first dollar via MONETA or Ko-fi")
    lines.append("3. **Wire self-feed** — `generate-organ-backlog.py` already reads organ-ladder.json;"
                 " when maturity hits 40% it emits next deepen")
    lines.append("4. **Add credit accounts** — credit cards, loans, mortgages to entity registry")
    lines.append("5. **Investment accounts** — brokerage, retirement, crypto wallets")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    # Load data sources
    entities = load_yaml_simple(HERE / "entities.yaml")
    revenue = load_json(ROOT / "revenue-ladder.json")
    obligations = load_json(ROOT / "obligations-ledger.json")

    # Generate artifacts
    artifacts = {
        "balance-sheet.md": build_balance_sheet(entities, revenue, obligations),
        "cashflow.md": build_cashflow(entities, revenue, obligations),
        "STATUS.md": build_dashboard(entities, revenue, obligations),
    }

    for filename, content in artifacts.items():
        path = HERE / filename
        with open(path, "w") as f:
            f.write(content)
        print(f"[consolidate] wrote {path.relative_to(ROOT)} ({len(content)} chars)")

    print(f"[consolidate] done — {len(artifacts)} artifacts generated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
