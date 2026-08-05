#!/usr/bin/env python3
"""_notify — onset-deduped macOS notification helper (the VIGILIA escalation path).

IF-HOST-PRESSURE form 4: before 2026-07-16 the only pressure signal was an advisory
line in a beat log — the operator was the sensor of last resort. This helper gives
sensors a LOUD path (osascript display notification, the conducting-report.py
precedent; works from launchd) with onset dedup so a condition notifies once when it
begins, not once per beat.

State lives in ``logs/vigilia/relief-state.json`` under the caller's root: a key per
active condition. ``notify_once`` records + fires on first sight of a key;
``clear_condition`` removes it when the condition ends so a future onset re-fires.
Kill-switch: LIMEN_NOTIFY=0 keeps the dedup bookkeeping but never calls osascript
(also how the hermetic tests stay silent). Fail-open everywhere.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def _state_path(root: Path | str) -> Path:
    return Path(root) / "logs" / "vigilia" / "relief-state.json"


def _load(root: Path | str) -> dict:
    try:
        state = json.loads(_state_path(root).read_text())
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _save(root: Path | str, state: dict) -> None:
    try:
        path = _state_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=1, sort_keys=True))
    except Exception:
        pass


def _enabled(enabled: bool | None) -> bool:
    if enabled is not None:
        return enabled
    return os.environ.get("LIMEN_NOTIFY", "1") not in ("0", "false", "False")


def notify_once(
    root: Path | str,
    key: str,
    message: str,
    title: str = "LIMEN host pressure",
    enabled: bool | None = None,
) -> bool:
    """Fire one notification per condition onset. Returns True iff this call fired.

    The dedup record is written even when notifications are disabled, so arming
    LIMEN_NOTIFY later does not replay every already-active condition.
    """
    state = _load(root)
    if key in state:
        return False
    state[key] = {"first_seen": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "message": message[:300]}
    _save(root, state)
    if _enabled(enabled):
        try:
            msg = message.replace('"', "'")
            ttl = title.replace('"', "'")
            subprocess.run(
                ["osascript", "-e", f'display notification "{msg}" with title "{ttl}"'],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
    return True


def clear_condition(root: Path | str, key: str) -> bool:
    """Forget an ended condition so its next onset notifies again."""
    state = _load(root)
    if key not in state:
        return False
    del state[key]
    _save(root, state)
    return True


def active_conditions(root: Path | str) -> list[str]:
    return sorted(_load(root))
