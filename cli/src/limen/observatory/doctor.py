"""``observatory doctor`` — the organ's self-verifying predicate.

Exit 0 ⟺ the spine is wired and safe. This is the scaffold-stage acceptance check
(later steps extend it with determinism + shape assertions). It is offline-safe: it
never faults on a missing ``gh`` — a live read simply reports SKIP.

Checks (each a named rung, GITVS's ``doctor`` idiom):
  wiring       every core module imports and exposes its public surface
  paths        ``logs/observatory/`` is writable
  params       the shared parameter panel resolves (or degrades to in-code defaults)
  registries   the three read-only ground-truth registries load (empty is OK)
  online       a live gh probe (SKIP when offline — never a faked PASS)
"""

from __future__ import annotations

import importlib

from . import config, gh, ledger

_CORE_MODULES = [
    "limen.observatory.config",
    "limen.observatory.gh",
    "limen.observatory.ledger",
    "limen.observatory.executive",
    "limen.observatory.doctor",
]


def _check_wiring() -> dict:
    missing = []
    for m in _CORE_MODULES:
        try:
            importlib.import_module(m)
        except Exception as exc:
            missing.append(f"{m}: {str(exc)[:80]}")
    return {"rung": "wiring", "ok": not missing, "missing": missing}


def _check_paths() -> dict:
    try:
        d = config.data_dir()
        probe = d / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"rung": "paths", "ok": True, "data_dir": str(d)}
    except Exception as exc:
        return {"rung": "paths", "ok": False, "error": str(exc)[:120]}


def _check_params() -> dict:
    # The panel is fail-open: a resolvable value (even the in-code default) is a pass.
    enabled = config.get("OBSERVATORY_ENABLED", "0")
    winners = config.get("OBSERVATORY_WINNERS_LIMIT", 3, cast=int)
    return {"rung": "params", "ok": winners is not None, "enabled": str(enabled), "winners_limit": winners}


def _check_registries() -> dict:
    # Loading is the check; emptiness is allowed (fail-CLOSED hero list is valid).
    return {
        "rung": "registries",
        "ok": True,
        "value_repos": len(config.value_repos()),
        "revenue_ladder": bool(config.revenue_ladder()),
        "estate_ledger": bool(config.estate_ledger()),
    }


def _check_online() -> dict:
    tok = gh.token()
    if not gh.online(tok):
        return {"rung": "online", "ok": True, "status": "SKIP", "reason": "offline"}
    head = gh.rate_headroom_pct(tok)
    return {"rung": "online", "ok": True, "status": "live", "rate_headroom_pct": head}


def run(*, offline: bool = False) -> dict:
    """Return ``{ok, rungs}``. ``offline`` skips the live probe entirely."""
    rungs = [_check_wiring(), _check_paths(), _check_params(), _check_registries()]
    if not offline:
        rungs.append(_check_online())
    ok = all(r.get("ok") for r in rungs)
    report = {"organ": "OBSERVATORY", "ok": ok, "rungs": rungs}
    ledger.write_latest("doctor-latest.json", report)
    return report
