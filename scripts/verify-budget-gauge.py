#!/usr/bin/env python3
"""verify-budget-gauge.py — is the fleet's budget GAUGE telling the truth?

The fleet already has good *controllers*: route._pick_local steers by runway +
cliff-urgency, usage-telemetry decays a reserve toward each reset, dispatch cascades
a rate-limited lane onto the next, capacity picks cheapest-first. A controller can
only pace as well as its gauge. This predicate audits the GAUGE — the per-lane
{cap, unit, window, trust} every controller reads — and fails loudly on the
pathologies that let a lane silently overrun (the pre-condition of a usage-window
blowout):

  FICTIONAL-CAP   a TOKEN lane steered by an estimate cap so large the controller
                  reads it as near-infinite headroom (claude/codex 100M/5h) and never
                  sheds early. Untrusted caps must bind PESSIMISTICALLY, not optimistically.
  DRIFT           one lane carries two different caps in two places (tasks.yaml vs gauge).
  SHARED-POOL     lanes that draw on ONE vendor plan — claude-cli + the Claude app +
                  this interactive session; codex-cli + the ChatGPT app — metered as
                  independent lanes, so the shared pool overruns while each lane reads "fine".
  WEEKLY-BLIND    a plan whose real reset is weekly, expressed on a 5h/24h cadence the
                  reset engine (_window_hours) cannot parse.
  APP-PLANE       the $200/mo app allotments (deep-research / scheduled-task runs) are a
                  distinct allotment CLASS, entirely unmodeled → invisible spend.

Every finding prints the DATA behind it — this is the data-grounded assessment, executable.
Read-only. Exit 0 ⟺ gauge fully TRUE (every dispatchable lane trusted, no drift, pools
and app-plane modeled). --json emits the machine record.

The reduction that makes the whole thing comparable: every allotment — tokens, runs,
app-runs — normalizes to ONE quantity, fraction_of_window_remaining ∈ [0,1], carrying a
trust ∈ {measured, proxy, calibrated, estimate, unmodeled, unknown}. That single number is
what a controller should steer on; trust decides how conservatively to read it. (`calibrated`
= a real windowed numerator over a cap anchored to a one-time /status observation.)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))

# Caps this large, on a token lane, are effectively "infinite headroom" to a runway
# controller — the FICTIONAL-CAP threshold. A real Claude/Codex plan window is far smaller.
_FICTIONAL_TOKEN_CAP = 50_000_000

# Windows the daemon's _window_hours() can actually parse today (Nh / today / day). Anything
# else silently defaults to 24h — so a "weekly" label is WEEKLY-BLIND until the engine learns it.
_PARSEABLE_WINDOW = re.compile(r"(\d+)\s*h|today|day", re.IGNORECASE)


def _load_default_limits() -> dict:
    """The tracked source of truth: _DEFAULT_LIMITS in usage-telemetry.py (loaded without
    importing the package, since the filename has a hyphen)."""
    spec = importlib.util.spec_from_file_location(
        "usage_telemetry", str(ROOT / "scripts" / "usage-telemetry.py")
    )
    if not spec or not spec.loader:  # pragma: no cover - environment guard
        return {}
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(getattr(mod, "_DEFAULT_LIMITS", {}))


def _load_override() -> dict:
    """The daemon-owned runtime override (gitignored logs/usage-limits.json), if present."""
    path = ROOT / "logs" / "usage-limits.json"
    if not path.exists():
        return {}
    try:
        return {k: v for k, v in json.loads(path.read_text()).items() if isinstance(v, dict)}
    except Exception:
        return {}


def _load_board_caps() -> dict:
    """per-agent caps declared on the dispatch board (tasks.yaml portal.budget.per_agent)."""
    path = ROOT / "tasks.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
    except ModuleNotFoundError:
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}
    budget = (((data.get("portal") or {}).get("budget")) or {})
    return dict(budget.get("per_agent") or {})


def _trust_of(entry: dict) -> str:
    """Machine-readable trust. Prefer an explicit `trust`; else infer from the prose `source`."""
    explicit = entry.get("trust")
    if explicit:
        return str(explicit)
    source = str(entry.get("source", "")).lower()
    if "known hard cap" in source or "measured" in source:
        return "measured"
    if "estimate" in source:
        return "estimate"
    return "unknown"


def codex_live_rate_limits() -> dict:
    """The TRUE Codex gauge — the vendor already reports it. Every codex token_count event
    carries a `rate_limits` object: primary (the 5h rolling window) and secondary (the weekly
    window), each with used_percent + window_minutes + resets_at, plus plan_type. We read the
    newest session's last such event. This is a real, self-updating, two-window fuel gauge — no
    fictional cap, no /status paste, never stale. Returns {} if none found (fail-open)."""
    import glob
    base = os.path.expanduser("~/.codex/sessions")
    files = glob.glob(f"{base}/**/rollout-*.jsonl", recursive=True)
    if not files:
        return {}
    newest = max(files, key=os.path.getmtime)
    last: dict = {}
    try:
        for line in open(newest, encoding="utf-8", errors="ignore"):
            if '"rate_limits"' not in line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            payload = row.get("payload") or {}
            rl = (payload.get("info") or {}).get("rate_limits") or payload.get("rate_limits")
            if rl:
                last = rl
    except OSError:
        return {}
    return last


def build_gauge() -> dict:
    """Merge tracked defaults ← runtime override, the same precedence load_limits() uses, then
    overlay the codex lane with its REAL vendor-reported gauge when available."""
    gauge = {k: dict(v) for k, v in _load_default_limits().items()}
    for k, v in _load_override().items():
        gauge.setdefault(k, {}).update(v)

    rl = codex_live_rate_limits()
    primary, secondary = rl.get("primary") or {}, rl.get("secondary") or {}
    if primary or secondary:
        c = gauge.setdefault("codex", {})
        c["trust"] = "measured"  # vendor-reported, not an estimate
        c["source"] = f"vendor rate_limits (plan={rl.get('plan_type')})"
        c["pool_cap"] = 100  # the gauge is a percentage — 100% IS the cap, per window
        c["unit"] = "percent"
        if primary:
            c["used_percent"] = primary.get("used_percent")
            c["window"] = f"{int(primary.get('window_minutes', 0)) // 60}h"
        if secondary:
            c["weekly_used_percent"] = secondary.get("used_percent")
            c["weekly_window"] = f"{int(secondary.get('window_minutes', 0)) // 60}h"

    # claude: resolve from the cascade (scripts/claude-usage.py). Always surface the % + which
    # avenue answered; only UPGRADE the row (clear the fictional-cap findings) when an avenue gives
    # a TRUSTED reading — an `estimate` reading vs the fleet's own fictional cap must leave the debt
    # standing so the audit stays honest.
    try:
        spec = importlib.util.spec_from_file_location("claude_usage", str(ROOT / "scripts" / "claude-usage.py"))
        cu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cu)
        cr = cu.resolve()
        if cr.get("used_percent") is not None:
            cl = gauge.setdefault("claude", {})
            cl["gauge_avenue"], cl["used_percent"] = cr.get("avenue"), cr.get("used_percent")
            # `calibrated` = real windowed numerator over a cap anchored to a /status observation —
            # no longer the fictional cap, so it clears the debt alongside measured/proxy.
            if cr.get("trust") in ("measured", "proxy", "calibrated"):
                cl["trust"], cl["unit"], cl["pool_cap"] = cr["trust"], "percent", 100
                cl["source"] = f"cascade avenue={cr.get('avenue')}"
    except Exception:
        pass
    return gauge


def audit() -> dict:
    gauge = build_gauge()
    board = _load_board_caps()
    lanes = sorted(set(gauge) | set(board))
    findings: list[dict] = []

    def finding(sev: str, code: str, lane: str, msg: str, data: dict | None = None) -> None:
        findings.append({"severity": sev, "code": code, "lane": lane, "msg": msg, "data": data or {}})

    rows = []
    for lane in lanes:
        e = gauge.get(lane, {})
        unit = e.get("unit")
        cap = e.get("limit")
        window = e.get("window", "")
        trust = _trust_of(e)
        plane = e.get("plane", "fleet" if e else "?")
        pool = e.get("pool")
        rows.append({
            "lane": lane, "unit": unit, "cap": cap, "window": window,
            "trust": trust, "plane": plane, "pool": pool,
            "board_cap": board.get(lane),
            "used_percent": e.get("used_percent"),
            "weekly_used_percent": e.get("weekly_used_percent"),
        })

        # --- FICTIONAL-CAP: a token lane whose cap the controller reads as infinite ---
        if unit == "tokens" and isinstance(cap, (int, float)) and cap >= _FICTIONAL_TOKEN_CAP:
            sev = "warn" if trust in ("estimate", "unmodeled") else "error"
            finding(sev, "FICTIONAL-CAP", lane,
                    f"token lane steered by a {cap:,}-token cap (trust={trust}); a runway "
                    f"controller reads this as ~infinite headroom and never sheds early",
                    {"cap": cap, "trust": trust, "window": window})

        # --- UNTRUSTED-CAP: any binding gate on an untrusted number ---
        if trust in ("estimate", "unknown", "unmodeled") and cap is not None:
            finding("warn" if trust != "unknown" else "error", "UNTRUSTED-CAP", lane,
                    f"cap {cap} is trust={trust}; an untrusted cap must bind PESSIMISTICALLY "
                    f"(shed earlier), and its untrustedness must be machine-readable",
                    {"cap": cap, "trust": trust, "source": e.get("source")})

        # --- WEEKLY-BLIND: window the reset engine cannot parse ---
        if window and not _PARSEABLE_WINDOW.search(str(window)):
            finding("error", "WEEKLY-BLIND", lane,
                    f"window {window!r} is not parseable by _window_hours() → silently "
                    f"treated as 24h", {"window": window})

    # --- DRIFT: same lane, two different run caps in board vs gauge ---
    for lane in lanes:
        e, bc = gauge.get(lane, {}), board.get(lane)
        gc = e.get("limit")
        if bc is not None and gc is not None and e.get("unit") == "runs" and bc != gc:
            finding("warn", "DRIFT", lane,
                    f"board per_agent cap={bc} but gauge cap={gc} (both 'runs'); reconcile the "
                    f"semantics (per-beat board cap vs vendor per-window cap) or the numbers lie",
                    {"board_cap": bc, "gauge_cap": gc})

    # --- SHARED-POOL: pools with >1 member and no pool-level cap ---
    pools: dict[str, list[str]] = {}
    for lane in lanes:
        p = gauge.get(lane, {}).get("pool")
        if p:
            pools.setdefault(p, []).append(lane)
    for pool, members in pools.items():
        pool_cap = next((gauge[m].get("pool_cap") for m in members if gauge.get(m, {}).get("pool_cap")), None)
        has_token = any(gauge.get(m, {}).get("unit") == "tokens" for m in members)
        # A pool with a token lane is shared with the app tier AND interactive use (unmetered
        # here) — so it needs a real pool_cap even when only one FLEET lane sits in it.
        if pool_cap is None and (has_token or len(members) > 1):
            finding("error", "SHARED-POOL", pool,
                    f"lanes {members} draw on one subscription pool (also shared with the app "
                    f"tier + interactive use) but there is no pool_cap; the pool overruns while "
                    f"each lane reads 'fine'", {"members": members})
    # The two account-level pools that MUST exist (defensible from auth: same subscription).
    for pool, expect in {"claude-plan": "claude", "openai-plan": "codex"}.items():
        if not any(gauge.get(l, {}).get("pool") == pool for l in lanes):
            finding("warn", "SHARED-POOL-MISSING", pool,
                    f"no lane declares pool={pool!r}; {expect}-cli, its app tier, and interactive "
                    f"use share ONE subscription window but nothing links them",
                    {})

    # --- APP-PLANE: the $200/mo app allotments as a distinct class ---
    if not any(r["plane"] == "app" for r in rows):
        finding("warn", "APP-PLANE", "-",
                "no lane has plane='app'; deep-research / scheduled-task allotments on the "
                "ChatGPT-Pro and Claude-Max subscriptions are unmodeled → invisible spend", {})

    errors = [f for f in findings if f["severity"] == "error"]
    warns = [f for f in findings if f["severity"] == "warn"]
    status = "true" if not findings else ("silent-debt" if errors else "declared-debt")
    exit_code = 0 if not findings else (2 if errors else 1)
    return {
        "status": status, "exit_code": exit_code, "rows": rows,
        "findings": findings, "errors": len(errors), "warnings": len(warns),
    }


def _print_human(report: dict) -> None:
    print("=== FLEET BUDGET GAUGE ===")
    print(f"{'lane':<12}{'plane':<8}{'unit':<8}{'cap':>16}  {'window':<12}{'trust':<10}{'pool':<12}{'board':>7}")
    for r in report["rows"]:
        if r.get("used_percent") is not None:  # real vendor gauge: show %-used, not a fake cap
            wk = r.get("weekly_used_percent")
            cap = f"{r['used_percent']:g}%" + (f"/{wk:g}%wk" if wk is not None else "")
        else:
            cap = f"{r['cap']:,}" if isinstance(r["cap"], (int, float)) else str(r["cap"])
        bc = "" if r["board_cap"] is None else str(r["board_cap"])
        print(f"{r['lane']:<12}{str(r['plane']):<8}{str(r['unit']):<8}{cap:>16}  "
              f"{str(r['window']):<12}{r['trust']:<10}{str(r['pool'] or ''):<12}{bc:>7}")
    print(f"\n=== FINDINGS ({report['errors']} error · {report['warnings']} warn) ===")
    order = {"error": 0, "warn": 1}
    for f in sorted(report["findings"], key=lambda x: order.get(x["severity"], 9)):
        mark = "✗" if f["severity"] == "error" else "!"
        print(f"  {mark} [{f['code']:<18}] {f['lane']:<12} {f['msg']}")
    print(f"\nSTATUS: {report['status']}  (exit {report['exit_code']})")
    print("  true=gauge trusted · declared-debt=debt visible+acknowledged · silent-debt=dangerous")


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit the fleet budget gauge for truth.")
    ap.add_argument("--json", action="store_true", help="emit the machine record")
    args = ap.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
