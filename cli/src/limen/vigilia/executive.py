"""The autonomic executive — the ONE hand.

Convenes the three autonomic organs each beat, records their state to the seat's
live status file (``logs/vigilia/status.json``), and returns a one-line summary.
VITALS' load-shedding decision rides a separate fast path (the vitals-gate, run
early in the beat before dispatch); here it is recorded read-only alongside
continuity and integrity so one file shows the whole autonomic picture.

Every organ call is wrapped: one organ faulting never stops the others or the beat.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from . import continuity, integrity, params, vitals


def _status_dir() -> Path:
    root = params._repo_root() or Path(os.environ.get("LIMEN_ROOT", ".")).expanduser()
    d = root / "logs" / "vigilia"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe(fn, organ: str) -> dict:
    try:
        return fn()
    except Exception as exc:  # an organ fault must never stop the others
        return {"organ": organ, "status": "error", "error": str(exc)[:200]}


def run_beat() -> dict:
    status = {
        "institution": params.get("INSTITVTIO_NOMEN", "VIGILIA"),
        "ts": datetime.now(UTC).isoformat(),
        # vitals recorded read-only here (shed=False); the gate path does the shedding.
        "vitals": _safe(lambda: vitals.beat_gate(shed=False), "vitals"),
        "continuity": _safe(continuity.beat, "continuity"),
        "integrity": _safe(integrity.check, "integrity"),
    }
    try:
        (_status_dir() / "status.json").write_text(json.dumps(status, indent=2))
    except Exception:
        pass
    return status


def summary_line(status: dict) -> str:
    v = status.get("vitals", {})
    c = status.get("continuity", {})
    i = status.get("integrity", {})
    return (
        f"vigilia: vitals=L{v.get('level', '?')}/{v.get('action', '?')} "
        f"continuity={c.get('status', '?')} integrity={i.get('status', '?')}"
    )
