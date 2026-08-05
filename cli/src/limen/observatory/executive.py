"""The convener — one hand that runs the loop for a beat.

Mirrors ``limen.vigilia.executive``: it convenes the pipeline stages
(collect → analyze → reconcile → brief), wraps each in ``_safe`` so one faulting
stage never stops the others or the beat, records the whole picture to
``logs/observatory/status.json``, and returns a one-line summary.

Stages are resolved lazily by name. A stage module that is not built yet (the
scaffold ships only this spine) is recorded as ``pending`` rather than crashing —
later build steps drop in ``collect``/``mechanism``/``reconcile``/``brief`` and the
convener picks them up with no change here.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone

from . import ledger

# (stage label, module, entry function) — the loop, declared as data.
_PIPELINE = [
    ("collect", "limen.observatory.collect", "run"),
    ("analyze", "limen.observatory.mechanism", "run"),
    ("reconcile", "limen.observatory.reconcile", "run"),
    ("brief", "limen.observatory.brief", "run"),
    # P2-SYNTH — folds the mechanism history into weekly KEEP/TEST/REJECT priors. Self-gates on
    # OBSERVATORY_SYNTH_ENABLED + an ISO-week state file, so it evaluates daily but acts weekly.
    ("synthesize", "limen.observatory.synthesis", "run"),
]


def _safe(label: str, module: str, entry: str, apply: bool) -> dict:
    try:
        mod = importlib.import_module(module)
    except Exception:
        return {"stage": label, "status": "pending"}  # not built yet
    fn = getattr(mod, entry, None)
    if fn is None:
        return {"stage": label, "status": "pending"}
    try:
        result = fn(apply=apply)
        summary = result if isinstance(result, dict) else {"result": result}
        return {"stage": label, "status": "ok", **summary}
    except Exception as exc:  # a stage fault must never stop the others
        return {"stage": label, "status": "error", "error": str(exc)[:200]}


def run_beat(*, apply: bool = False) -> dict:
    """Run the whole loop for one beat; write status.json; return the status dict."""
    stages = [_safe(label, mod, entry, apply) for (label, mod, entry) in _PIPELINE]
    status = {
        "institution": "OBSERVATORY",
        "ts": datetime.now(timezone.utc).isoformat(),
        "apply": bool(apply),
        "stages": stages,
    }
    ledger.write_latest("status.json", status)
    ledger.stamp(
        {
            "apply": bool(apply),
            "stages_ok": sum(1 for s in stages if s.get("status") == "ok"),
            "stages_pending": sum(1 for s in stages if s.get("status") == "pending"),
        }
    )
    return status


def summary_line(status: dict) -> str:
    parts = [f"{s['stage']}={s.get('status', '?')}" for s in status.get("stages", [])]
    return "observatory: " + " ".join(parts)
