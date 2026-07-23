"""P2-SYNTH — weekly KEEP / TEST / REJECT synthesis of the mechanism history.

Folds the immutable ``mechanisms.jsonl`` ledger into standing priors: which surface mechanisms keep
recurring with real, transferable priority (**KEEP**), which are still too new to judge (**TEST**),
and which keep appearing but never pay off (**REJECT**). Runs at most once per ISO week (a
state-file gate, the ``conducting-report.py`` once-per-period idiom) and only when
``OBSERVATORY_SYNTH_ENABLED`` is armed. It writes **recommendations only** — it never edits the
human-curated ``mechanisms.yaml``. Fail-open: any fault returns a status dict and writes nothing
partial. ``_now`` is a seam so tests pin the week deterministically.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime

from . import config, ledger

_STATE = "synth-state.json"  # {"iso_week": "YYYY-Www"} — the once-per-week gate
_MIN_OCCURRENCES = 3  # a prior needs a few observations before we trust it
_KEEP_PRIORITY = 2.0  # mean priority at/above → a durable, transferable win
_REJECT_PRIORITY = 0.5  # recurs this often but stays below → not transferable


def _now() -> datetime:
    """A seam — tests monkeypatch this to pin the ISO week."""
    return datetime.now(UTC)


def _iso_week(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _state_week() -> str | None:
    """The ISO week last synthesized (from the state file), or None if never / unreadable."""
    try:
        wk = json.loads((config.data_dir() / _STATE).read_text(encoding="utf-8")).get("iso_week")
        return wk if isinstance(wk, str) else None
    except Exception:
        return None


def _bucket(mechanisms: list[dict]) -> dict:
    """Group scored claims by mechanism → KEEP/TEST/REJECT by recurrence × mean priority. Pure."""
    agg: dict[str, list[float]] = defaultdict(list)
    for m in mechanisms:
        name = m.get("mechanism")
        if isinstance(name, str):
            agg[name].append(float(m.get("priority") or 0.0))
    keep: list[dict] = []
    test: list[dict] = []
    reject: list[dict] = []
    for name in sorted(agg):
        prios = agg[name]
        occ = len(prios)
        mean = round(sum(prios) / occ, 4) if occ else 0.0
        row = {"mechanism": name, "occurrences": occ, "mean_priority": mean}
        if occ >= _MIN_OCCURRENCES and mean >= _KEEP_PRIORITY:
            keep.append(row)
        elif occ >= _MIN_OCCURRENCES and mean < _REJECT_PRIORITY:
            reject.append(row)
        else:
            test.append(row)
    return {"keep": keep, "test": test, "reject": reject}


def synthesize(mechanisms: list[dict], iso_week: str) -> dict:
    """The pure synthesis doc for a week's mechanism history."""
    distinct = {m.get("mechanism") for m in mechanisms if isinstance(m.get("mechanism"), str)}
    return {
        "schema": "limen.observatory.synthesis.v1",
        "iso_week": iso_week,
        "window_mechanisms": len(distinct),
        **_bucket(mechanisms),
    }


def run(*, apply: bool = False) -> dict:
    """Executive **synthesize** stage — at most once per ISO week when armed. Fail-open."""
    if not config.get("OBSERVATORY_SYNTH_ENABLED", 0, cast=int):
        return {"stage": "synthesize", "status": "off"}
    try:
        week = _iso_week(_now())
        if _state_week() == week:
            return {"stage": "synthesize", "status": "current", "iso_week": week}
        doc = synthesize(ledger.read_jsonl("mechanisms.jsonl"), week)
        ledger.write_latest("synthesis-weekly-latest.json", doc)
        ledger.snapshot_line("synthesis.jsonl", doc)
        ledger.write_latest(_STATE, {"iso_week": week})
        return {
            "stage": "synthesize",
            "status": "ok",
            "iso_week": week,
            "keep": len(doc["keep"]),
            "test": len(doc["test"]),
            "reject": len(doc["reject"]),
        }
    except Exception as exc:  # a synthesis fault must never stop the beat
        return {"stage": "synthesize", "status": "error", "error": str(exc)[:200]}
