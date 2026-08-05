#!/usr/bin/env python3
"""token-value-gauge.py — price the fleet's measured tokens at API-equivalent rates.

Phase-2 valuation layer of docs/sovereign-inference-plan.md: joins the dollar side
(organs/financial/ai-vendor-spend.md, receipt-verified) with the token side (real per-message
usage already on disk) to compute the sovereignty decision parameters:

  - api_equivalent_usd_month per vendor (what the observed usage would cost at API list rates)
  - arbitrage_multiple (api-equivalent / subscription price)
  - local_absorbable_share (haiku-class share of Claude volume — the tier the qwen3:8b floor targets)
  - hardware_payback_months (capex / open-weight-API value of the absorbable volume)

Sources (trust-stamped; gaps are explicit, never silent):
  measured  claude    ~/.claude/projects/**/*.jsonl  (per-message usage + model)
  measured  opencode  ~/.local/share/opencode/opencode.db  (session table token columns)
  unmodeled codex     vendor persists rate-limit %% only, no token counts on disk
  unmodeled gemini    no local token accounting
  unmodeled ollama    local floor, unmetered by design

Idempotent: all timestamps derive from the DATA (max observed event), never wall clock;
outputs are rewritten only when content changes. Exit 0 == gauge written/verified.

Rates: Claude API list prices per MTok (claude-api skill, cached 2026-06-04) —
opus 5/25, sonnet 3/15, haiku 1/5, fable 10/50; cache_read = 0.1x input,
cache_write = 1.25x input (5m TTL). Open-weight comparison: DeepSeek-class hosted
list rates ~0.28/0.42 per MTok (cache-hit input ~0.028) — constants, re-check quarterly.
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_MD = ROOT / "organs" / "financial" / "token-usage.md"
OUT_JSON = ROOT / "organs" / "financial" / "token-usage.json"

WINDOW_DAYS = 30
WINDOW_S = WINDOW_DAYS * 86400

CLAUDE_PRICES = {  # family substring -> (input $/MTok, output $/MTok)
    "fable": (10.0, 50.0),
    "mythos": (10.0, 50.0),
    "opus": (5.0, 25.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
}
CACHE_READ_X = 0.1
CACHE_WRITE_X = 1.25
OPEN_IN, OPEN_OUT, OPEN_CACHE_READ = 0.28, 0.42, 0.028  # open-weight hosted comparison

SUBS_USD_MONTH = {"claude": 217.75, "opencode": 10.00}  # receipt-verified (ai-vendor-spend.md)
CAPEX_SCENARIOS = {"mac-128gb": 3700.0, "mac-512gb": 9500.0}


def _family(model: str | None) -> str | None:
    m = (model or "").lower()
    for k in CLAUDE_PRICES:
        if k in m:
            return k
    return None


def _usd(family: str, i: float, o: float, cr: float, cw: float) -> float:
    pin, pout = CLAUDE_PRICES[family]
    return (i * pin + o * pout + cr * pin * CACHE_READ_X + cw * pin * CACHE_WRITE_X) / 1e6


def _open_usd(i: float, o: float, cr: float, cw: float) -> float:
    # open-weight hosts price cache writes as ordinary input
    return (i * OPEN_IN + o * OPEN_OUT + cr * OPEN_CACHE_READ + cw * OPEN_IN) / 1e6


def _iso_ts(s: str) -> float | None:
    try:
        from datetime import datetime

        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def scan_claude() -> tuple[dict, float, float]:
    """Per-model token sums from Claude Code transcripts, last WINDOW_DAYS anchored to the
    newest observed message (data-derived, so re-runs are idempotent). Streaming, mtime-bounded."""
    root = Path.home() / ".claude" / "projects"
    rows: list[tuple[float, str, float, float, float, float]] = []
    now = max((os.path.getmtime(f) for f in glob.glob(str(root / "*"))), default=0.0)
    for f in glob.glob(str(root / "**" / "*.jsonl"), recursive=True):
        try:
            if now - os.path.getmtime(f) > WINDOW_S + 86400:
                continue
        except OSError:
            continue
        try:
            for line in open(f, errors="ignore"):
                if '"usage"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                msg = o.get("message") or {}
                u = msg.get("usage") or o.get("usage")
                if not isinstance(u, dict):
                    continue
                ts = _iso_ts(o.get("timestamp", "") or "")
                if ts is None:
                    continue
                model = str(msg.get("model") or "")
                if not model or model == "<synthetic>":
                    continue
                rows.append(
                    (
                        ts,
                        model,
                        float(u.get("input_tokens") or 0),
                        float(u.get("output_tokens") or 0),
                        float(u.get("cache_read_input_tokens") or 0),
                        float(u.get("cache_creation_input_tokens") or 0),
                    )
                )
        except OSError:
            continue
    if not rows:
        return {}, 0.0, 0.0
    # Quantize the window anchor down to the hour: the fleet appends transcripts continuously,
    # so an exact max-timestamp anchor would shift every run and break idempotence.
    t_max = max(r[0] for r in rows) // 3600 * 3600
    t_cut = t_max - WINDOW_S
    agg: dict[str, list[float]] = {}
    for ts, model, i, o, cr, cw in rows:
        if ts < t_cut or ts > t_max:
            continue
        a = agg.setdefault(model, [0.0, 0.0, 0.0, 0.0, 0.0])
        a[0] += i
        a[1] += o
        a[2] += cr
        a[3] += cw
        a[4] += 1
    t_min = max(min(r[0] for r in rows), t_cut)
    return agg, t_min, t_max


def scan_opencode() -> tuple[dict, float, float, float]:
    """Per-model token sums + vendor-reported cost from the opencode SQLite session table."""
    db = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    if not db.exists():
        return {}, 0.0, 0.0, 0.0
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        t_max = con.execute("SELECT COALESCE(MAX(time_created),0) FROM session").fetchone()[0] / 1000.0
        t_max = t_max // 3600 * 3600  # hour-quantized anchor, same idempotence rationale as scan_claude
        t_cut = t_max - WINDOW_S
        q = """SELECT model, SUM(tokens_input), SUM(tokens_output), SUM(tokens_cache_read),
                      SUM(tokens_cache_write), SUM(cost), COUNT(*), MIN(time_created)
               FROM session WHERE time_created >= ? AND time_created <= ? GROUP BY model"""
        agg: dict[str, list[float]] = {}
        cost = 0.0
        t_min = t_max
        for model, i, o, cr, cw, c, n, tmin in con.execute(q, (t_cut * 1000.0, t_max * 1000.0)):
            name = model or "?"
            try:
                name = json.loads(model).get("id") or name
            except Exception:
                pass
            agg[name] = [float(i or 0), float(o or 0), float(cr or 0), float(cw or 0), float(n or 0)]
            cost += float(c or 0)
            t_min = min(t_min, (tmin or t_max * 1000) / 1000.0)
        return agg, t_min, t_max, cost
    finally:
        con.close()


def fmt_mtok(n: float) -> str:
    return f"{n / 1e6:,.1f}M"


def build() -> tuple[str, dict]:
    claude, c_min, c_max = scan_claude()
    oc, o_min, o_max, oc_cost = scan_opencode()

    from datetime import datetime, timezone

    def day(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else "-"

    # --- Claude valuation -------------------------------------------------
    c_days = max((c_max - c_min) / 86400.0, 1.0) if claude else 0.0
    c_rows = []
    c_usd = c_open_usd = 0.0
    c_tok = [0.0, 0.0, 0.0, 0.0]
    haiku_usd = haiku_open_usd = haiku_tok = 0.0
    for model, (i, o, cr, cw, n) in sorted(claude.items(), key=lambda kv: -sum(kv[1][:4])):
        fam = _family(model)
        if fam is None:
            continue
        usd = _usd(fam, i, o, cr, cw)
        c_usd += usd
        c_open_usd += _open_usd(i, o, cr, cw)
        for k, v in enumerate((i, o, cr, cw)):
            c_tok[k] += v
        if fam == "haiku":
            haiku_usd += usd
            haiku_open_usd += _open_usd(i, o, cr, cw)
            haiku_tok += i + o + cr + cw
        c_rows.append((model, i, o, cr, cw, int(n), usd))
    month_x = (30.0 / c_days) if c_days else 0.0
    c_month = c_usd * month_x
    c_total_tok = sum(c_tok)
    arb_claude = (c_month / SUBS_USD_MONTH["claude"]) if c_month else 0.0
    absorb_share = (haiku_tok / c_total_tok) if c_total_tok else 0.0
    absorb_open_month = haiku_open_usd * month_x
    payback = {
        k: (v / absorb_open_month if absorb_open_month > 0 else None) for k, v in CAPEX_SCENARIOS.items()
    }

    # --- opencode valuation ----------------------------------------------
    o_days = max((o_max - o_min) / 86400.0, 1.0) if oc else 0.0
    o_tok = sum(sum(v[:4]) for v in oc.values())
    o_open_usd = sum(_open_usd(*v[:4]) for v in oc.values())
    o_month_open = o_open_usd * (30.0 / o_days) if o_days else 0.0
    arb_oc = (o_month_open / SUBS_USD_MONTH["opencode"]) if o_month_open else 0.0

    payload = {
        "schema": 1,
        "window_days": WINDOW_DAYS,
        "rates_source": "claude-api skill cache 2026-06-04; open-weight = DeepSeek-class list",
        "vendors": {
            "claude": {
                "trust": "measured",
                "window": [day(c_min), day(c_max)],
                "observed_days": round(c_days, 1),
                "tokens": {
                    "input": round(c_tok[0]),
                    "output": round(c_tok[1]),
                    "cache_read": round(c_tok[2]),
                    "cache_write": round(c_tok[3]),
                },
                "api_equivalent_usd_window": round(c_usd),
                "api_equivalent_usd_month": round(c_month),
                "subscription_usd_month": SUBS_USD_MONTH["claude"],
                "arbitrage_multiple": round(arb_claude, 1),
                "per_model": {
                    m: {"tokens": round(i + o + cr + cw), "usd": round(usd, 2), "messages": n}
                    for m, i, o, cr, cw, n, usd in c_rows
                },
            },
            "opencode": {
                "trust": "measured",
                "window": [day(o_min), day(o_max)],
                "observed_days": round(o_days, 1),
                "tokens_total": round(o_tok),
                "vendor_reported_cost_usd": round(oc_cost, 2),
                "open_weight_equivalent_usd_month": round(o_month_open),
                "subscription_usd_month": SUBS_USD_MONTH["opencode"],
                "arbitrage_multiple": round(arb_oc, 1),
            },
            "codex": {"trust": "unmodeled", "note": "vendor persists rate-limit % only; Pro->Plus lever keeps its revisit-on-starvation guard"},
            "gemini": {"trust": "unmodeled", "note": "no local token accounting"},
            "ollama": {"trust": "unmodeled", "note": "local floor, unmetered by design"},
        },
        "decision_parameters": {
            "claude_arbitrage_multiple": round(arb_claude, 1),
            "local_absorbable_share_tokens": round(absorb_share, 3),
            "local_absorbable_open_usd_month": round(absorb_open_month, 2),
            "hardware_payback_months": {k: (round(v, 1) if v else None) for k, v in payback.items()},
            "claude_usage_at_open_weight_rates_usd_month": round(c_open_usd * month_x),
        },
    }

    pb = "; ".join(
        f"{k}: {'%.0f mo' % v if v and v < 1200 else 'not justified'}" for k, v in payback.items()
    )
    md_rows = "\n".join(
        f"| {m} | {fmt_mtok(i + o + cr + cw)} | {fmt_mtok(o)} | {fmt_mtok(cr)} | {n} | {usd:,.0f} |"
        for m, i, o, cr, cw, n, usd in c_rows
    )
    md = f"""# Token Usage — API-Equivalent Value

*Generated by `scripts/token-value-gauge.py` (idempotent; timestamps derive from the data, not the
clock). Joins [`ai-vendor-spend.md`](ai-vendor-spend.md) (the dollar side) with measured tokens.
Trust levels per `verify-budget-gauge.py` conventions; `unmodeled` rows are stated, never silent.*

## Decision parameters

| Parameter | Value | Basis |
|---|---|---|
| Claude arbitrage multiple | **{arb_claude:,.1f}x** | ${c_month:,.0f}/mo API-equivalent vs $217.75/mo Claude Max sub (measured, {day(c_min)} → {day(c_max)}) |
| Claude usage at open-weight rates | ${c_open_usd * month_x:,.0f}/mo | same volume priced at DeepSeek-class hosted rates |
| Local-absorbable share (haiku-class) | {absorb_share:.1%} of Claude tokens | the tier the qwen3:8b floor targets |
| Absorbable volume at open-weight rates | ${absorb_open_month:,.2f}/mo | what hosted open-weight would charge for it |
| Hardware payback | {pb} | capex / absorbable open-weight $/mo |
| OpenCode arbitrage multiple | {arb_oc:,.1f}x | ${o_month_open:,.0f}/mo open-weight-equivalent vs $10/mo sub |

## Claude — measured ({day(c_min)} → {day(c_max)}, {c_days:.1f} days observed)

Total: **{fmt_mtok(c_total_tok)} tokens** (input {fmt_mtok(c_tok[0])} · output {fmt_mtok(c_tok[1])} ·
cache-read {fmt_mtok(c_tok[2])} · cache-write {fmt_mtok(c_tok[3])}) ≈ **${c_usd:,.0f}** at API list
rates over the window → **${c_month:,.0f}/mo** normalized.

| Model | Tokens | Output | Cache-read | Messages | API-equiv $ |
|---|---|---|---|---|---|
{md_rows}

## OpenCode — measured ({day(o_min)} → {day(o_max)}, {o_days:.1f} days observed)

{fmt_mtok(o_tok)} tokens across {sum(int(v[4]) for v in oc.values())} sessions; vendor-reported cost
column sums to ${oc_cost:,.2f}; open-weight-equivalent **${o_month_open:,.0f}/mo** vs the $10/mo sub.

## Gaps (unmodeled — stated, not silent)

| Vendor | Why | Mitigation |
|---|---|---|
| codex | vendor persists rate-limit % only — no token counts on disk | Pro→Plus lever keeps its revisit-on-starvation guard |
| gemini | no local token accounting | dispatch-count proxy in `logs/usage.json` |
| ollama | local floor, unmetered by design | it is the thing the gauge justifies, not a cost |

*Rates: Claude API list (opus 5/25, sonnet 3/15, haiku 1/5, fable 10/50 per MTok; cache-read 0.1x,
cache-write 1.25x input). Open-weight comparison: DeepSeek-class ~0.28/0.42 per MTok. Machine ledger:
[`token-usage.json`](token-usage.json).*
"""
    return md, payload


def write_if_changed(path: Path, content: str) -> bool:
    old = path.read_text() if path.exists() else None
    if old == content:
        return False
    path.write_text(content)
    return True

def main() -> int:
    md, payload = build()
    js = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    ch_md = write_if_changed(OUT_MD, md)
    ch_js = write_if_changed(OUT_JSON, js)
    p = payload["decision_parameters"]
    print(f"claude arbitrage {p['claude_arbitrage_multiple']}x | absorbable {p['local_absorbable_share_tokens']:.1%} "
          f"| absorbable open-$ {p['local_absorbable_open_usd_month']}/mo | payback {p['hardware_payback_months']}")
    print(f"{'wrote' if ch_md or ch_js else 'unchanged'}: {OUT_MD.relative_to(ROOT)}, {OUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
