"""The autonomic executive — the ONE hand.

VITALS sampling has a deliberately smaller clock than the full autonomic beat.
``sampled_at`` records the early, lightweight host observation; ``completed_at``
records when continuity and integrity finish. A slow downstream organ can therefore
delay full completion without rewriting the truth about when the host was sampled.

Every organ call is wrapped: one organ faulting never stops the others or the beat.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from . import continuity, integrity, params, vitals


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _status_dir() -> Path:
    root = params._repo_root() or Path(os.environ.get("LIMEN_ROOT", ".")).expanduser()
    directory = root / "logs" / "vigilia"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe(fn, organ: str) -> dict:
    try:
        return fn()
    except Exception as exc:  # an organ fault must never stop the others
        return {"organ": organ, "status": "error", "error": str(exc)[:200]}


def _load_status(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _update_status(mutator: Callable[[dict], dict]) -> dict:
    """Serialize the fast sampler and full beat, then replace the seat atomically."""
    directory = _status_dir()
    path = directory / "status.json"
    lock_path = directory / ".status.lock"
    try:
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            status = mutator(_load_status(path))
            status.pop("ts", None)  # retired: one timestamp cannot represent two cadences
            tmp = directory / f".status.{os.getpid()}.tmp"
            tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
            tmp.replace(path)
            return status
    except Exception:
        # The executive is fail-open, including its diagnostic seat.
        return mutator({})


def sample_vitals() -> dict:
    """Refresh only the host sample while preserving the last full-beat receipt."""
    sampled_at = _now().isoformat()
    observed = _safe(lambda: vitals.beat_gate(shed=False), "vitals")

    def merge(current: dict) -> dict:
        status = dict(current)
        status.update(
            {
                "institution": params.get("INSTITVTIO_NOMEN", "VIGILIA"),
                "sampled_at": sampled_at,
                "vitals": observed,
            }
        )
        status.setdefault("completed_at", None)
        return status

    return _update_status(merge)


def run_beat() -> dict:
    # Sampling is the first operation. A concurrent fast-wave sample may refresh it
    # again while the slower organs run; the merge below preserves whichever is newest.
    early = sample_vitals()
    continuity_status = _safe(continuity.beat, "continuity")
    integrity_status = _safe(integrity.check, "integrity")
    completed_at = _now().isoformat()

    def merge(current: dict) -> dict:
        return {
            "institution": params.get("INSTITVTIO_NOMEN", "VIGILIA"),
            "sampled_at": current.get("sampled_at") or early.get("sampled_at"),
            "completed_at": completed_at,
            "vitals": current.get("vitals") or early.get("vitals", {}),
            "continuity": continuity_status,
            "integrity": integrity_status,
        }

    return _update_status(merge)


def summary_line(status: dict) -> str:
    v = status.get("vitals", {})
    c = status.get("continuity", {})
    i = status.get("integrity", {})
    return (
        f"vigilia: vitals=L{v.get('level', '?')}/{v.get('action', '?')} "
        f"continuity={c.get('status', '?')} integrity={i.get('status', '?')}"
    )
