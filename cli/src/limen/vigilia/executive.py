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


def _sample_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _update_status(mutator: Callable[[dict], dict]) -> dict:
    """Serialize the fast sampler and full beat, then replace the seat atomically."""
    try:
        directory = _status_dir()
        path = directory / "status.json"
        lock_path = directory / ".status.lock"
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
    sampled_time = _now()
    sampled_at = sampled_time.isoformat()
    observed = _safe(lambda: vitals.beat_gate(shed=False), "vitals")

    def merge(current: dict) -> dict:
        status = dict(current)
        status["institution"] = params.get("INSTITVTIO_NOMEN", "VIGILIA")
        status.setdefault("completed_at", None)
        if observed.get("status") == "error":
            status["sample_error"] = observed
            status.setdefault("vitals", observed)
            return status
        current_time = _sample_time(status.get("sampled_at"))
        if current_time is not None and current_time > sampled_time:
            return status
        status.update(
            {
                "sampled_at": sampled_at,
                "vitals": observed,
            }
        )
        status.pop("sample_error", None)
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
        sampled_at = current.get("sampled_at") or early.get("sampled_at")
        sample_error = current.get("sample_error")
        # An early error remains relevant only until a later successful sample advances
        # the timestamp. Do not resurrect an obsolete failure from the slow beat's copy.
        if sample_error is None and early.get("sample_error") and current.get("sampled_at") == early.get("sampled_at"):
            sample_error = early["sample_error"]
        result = {
            "institution": params.get("INSTITVTIO_NOMEN", "VIGILIA"),
            "sampled_at": sampled_at,
            "completed_at": completed_at,
            "vitals": current.get("vitals") or early.get("vitals", {}),
            "continuity": continuity_status,
            "integrity": integrity_status,
        }
        if sample_error is not None:
            result["sample_error"] = sample_error
        return result

    return _update_status(merge)


def summary_line(status: dict) -> str:
    v = status.get("vitals", {})
    c = status.get("continuity", {})
    i = status.get("integrity", {})
    return (
        f"vigilia: vitals=L{v.get('level', '?')}/{v.get('action', '?')} "
        f"continuity={c.get('status', '?')} integrity={i.get('status', '?')}"
    )
