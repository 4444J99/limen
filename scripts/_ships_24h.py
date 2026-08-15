#!/usr/bin/env python3
"""_ships_24h.py — shared reader for the ships-24h-refresh.py ground-truth cache.

Sibling to `_root.py`/`_notify.py`: a small, dependency-free module both `money-view.py` and
`omni-view.py` import so the "PRs merged in the last 24h" logic exists in exactly one place,
instead of the two divergent `merge-drain.log`-parsing copies this replaces.

Fails open to (0, {}, []) on a missing, malformed, or STALE cache — serving a silently-stale
number is worse than admitting "unknown right now" (the cache itself already carries `error` for
transport failures; staleness here catches the case where nothing has refreshed it at all).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

STALE_AFTER_MINUTES_DEFAULT = 40  # 2x ships-24h-refresh.py's own default refresh interval (20m)


def _parse_stamp(stamp):
    try:
        when = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.astimezone()
    return when


def read_ships_24h(root):
    """Return (total, by_repo, recent) from logs/ships-24h.json, or (0, {}, []) if the cache is
    missing, malformed, or older than LIMEN_SHIPS_24H_STALE_MINUTES."""
    path = Path(root) / "logs" / "ships-24h.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return 0, {}, []
    if not isinstance(data, dict):
        return 0, {}, []

    when = _parse_stamp(data.get("generated_at"))
    if when is None:
        return 0, {}, []
    try:
        stale_after = int(os.environ.get("LIMEN_SHIPS_24H_STALE_MINUTES", STALE_AFTER_MINUTES_DEFAULT))
    except ValueError:
        stale_after = STALE_AFTER_MINUTES_DEFAULT
    age_minutes = (datetime.now(timezone.utc) - when.astimezone(timezone.utc)).total_seconds() / 60.0
    if age_minutes > stale_after:
        return 0, {}, []

    total = data.get("total")
    by_repo = data.get("by_repo")
    recent = data.get("recent")
    if not isinstance(total, int) or not isinstance(by_repo, dict) or not isinstance(recent, list):
        return 0, {}, []
    return total, by_repo, [r for r in recent if isinstance(r, str)]
