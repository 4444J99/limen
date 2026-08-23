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
import hashlib
import subprocess
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from . import continuity, integrity, params, vitals


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _boot_identity() -> str:
    try:
        result = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=3)
        if result.returncode != 0 or not result.stdout.strip():
            return "unavailable"
        return hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:20]
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _active_monotonic() -> float:
    clock = getattr(time, "CLOCK_UPTIME_RAW", time.CLOCK_MONOTONIC)
    return time.clock_gettime(clock)


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
    except Exception as exc:
        # The executive remains fail-open, but a sampler must not claim a timestamp that
        # never reached the watchdog-visible seat. The private marker is added only to
        # this in-memory fallback; successful receipts never persist diagnostic metadata.
        try:
            fallback = mutator({})
        except Exception as fallback_exc:
            return {
                "status": "error",
                "error": str(fallback_exc)[:200],
                "_persistence_error": str(exc)[:200],
            }
        fallback["_persistence_error"] = str(exc)[:200]
        return fallback


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
            current_time = _sample_time(status.get("sampled_at"))
            if current_time is not None and current_time > sampled_time:
                return status
            status["sample_error"] = observed
            status["sample_error_at"] = sampled_at
            status.setdefault("vitals", observed)
            return status
        current_time = _sample_time(status.get("sampled_at"))
        if current_time is not None and current_time > sampled_time:
            return status
        status.update(
            {
                "sampled_at": sampled_at,
                "boot_identity": _boot_identity(),
                "sampled_monotonic_seconds": round(_active_monotonic(), 3),
                "wake_state": os.environ.get("LIMEN_WAKE_STATE", "FullWake"),
                "vitals": observed,
            }
        )
        status.pop("sample_error", None)
        status.pop("sample_error_at", None)
        return status

    status = _update_status(merge)
    # Keep this bit out of status.json: it is a delivery receipt for the caller, not
    # another freshness clock. A failed seat write is therefore visible to the sampler.
    result = dict(status)
    result["sample_persisted"] = "_persistence_error" not in status
    return result


def run_beat() -> dict:
    # Sampling is the first operation. A concurrent fast-wave sample may refresh it
    # again while the slower organs run; the merge below preserves whichever is newest.
    early = sample_vitals()
    continuity_status = _safe(continuity.beat, "continuity")
    integrity_status = _safe(integrity.check, "integrity")
    completed_at = _now().isoformat()

    def merge(current: dict) -> dict:
        current_sampled_at = current.get("sampled_at")
        early_sampled_at = early.get("sampled_at")
        current_time = _sample_time(current_sampled_at)
        early_time = _sample_time(early_sampled_at)
        early_is_new_success = (
            early_time is not None
            and early.get("sample_error") is None
            and (current_time is None or early_time > current_time)
        )
        sampled_at = early_sampled_at if early_is_new_success else (current_sampled_at or early_sampled_at)
        current_error = current.get("sample_error")
        current_error_at = _sample_time(current.get("sample_error_at"))
        if current_error is not None and current_error_at is None:
            current_error_at = current_time
        early_error = early.get("sample_error")
        early_error_at = _sample_time(early.get("sample_error_at"))
        if early_error is not None and early_error_at is None:
            early_error_at = early_time
        sample_error = current_error
        sample_error_at = current_error_at
        if early_error is not None and (
            sample_error is None
            or (early_error_at is not None and (sample_error_at is None or early_error_at > sample_error_at))
        ):
            sample_error = early_error
            sample_error_at = early_error_at
        successful_samples = []
        if current_error is None and current_time is not None:
            successful_samples.append(current_time)
        if early.get("sample_error") is None and early_time is not None:
            successful_samples.append(early_time)
        latest_success = max(successful_samples) if successful_samples else None
        if (
            sample_error is not None
            and sample_error_at is not None
            and latest_success is not None
            and sample_error_at < latest_success
        ):
            sample_error = None
            sample_error_at = None
        result = {
            "institution": params.get("INSTITVTIO_NOMEN", "VIGILIA"),
            "sampled_at": sampled_at,
            "completed_at": completed_at,
            "vitals": (
                early.get("vitals", {}) if early_is_new_success else current.get("vitals") or early.get("vitals", {})
            ),
            "continuity": continuity_status,
            "integrity": integrity_status,
        }
        sample_source = early if early_is_new_success else current
        for key in ("boot_identity", "sampled_monotonic_seconds", "wake_state"):
            if sample_source.get(key) is not None:
                result[key] = sample_source[key]
        if sample_error is not None:
            result["sample_error"] = sample_error
            if sample_error_at is not None:
                result["sample_error_at"] = sample_error_at.isoformat()
        return result

    return _update_status(merge)


def summary_line(status: dict) -> str:
    v = status.get("vitals", {})
    c = status.get("continuity", {})
    i = status.get("integrity", {})
    sample_error = status.get("sample_error")
    if isinstance(sample_error, dict):
        error_detail = str(sample_error.get("error") or "sample failed")[:120]
        vitals_summary = f"ERROR/{error_detail}"
    else:
        vitals_summary = f"L{v.get('level', '?')}/{v.get('action', '?')}"
    return f"vigilia: vitals={vitals_summary} continuity={c.get('status', '?')} integrity={i.get('status', '?')}"
