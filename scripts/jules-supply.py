#!/usr/bin/env python3
"""Jules supply organ: keep the board holding a floor of dispatchable Jules packets.

Gauge + effector pair for the 100/day engine: the quota sensor (jules-quota) measures
used-vs-target; THIS organ measures supply-vs-floor and, when armed, mints the deficit
from the declared template registry (docs/jules-supply-templates.yaml) as TABVLARIVS
upsert tickets — the beat's relay lands them on the keeper. Dry-run by default:
LIMEN_JULES_SUPPLY_APPLY=1 arms minting.

Exit 0 = supply at floor (or unarmed dry-run). Exit 1 (advisory) = supply below floor.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.capacity import derived_daily_floor  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.jules_supply import dispatchable_supply, expand_supply, load_supply_registry  # noqa: E402
from limen.tabularius import submit_task_upsert  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
REGISTRY = Path(os.environ.get("LIMEN_JULES_SUPPLY_TEMPLATES", str(ROOT / "docs" / "jules-supply-templates.yaml")))


def pending_inbox_ids(board_path: Path) -> set[str]:
    """Task ids already queued as tickets — never double-mint between relays."""
    inbox = board_path.parent / "logs" / "tickets" / "inbox"
    ids: set[str] = set()
    for path in inbox.glob("*.json") if inbox.is_dir() else ():
        try:
            task_id = json.loads(path.read_text(encoding="utf-8")).get("task_id")
        except (OSError, ValueError):
            continue
        if task_id:
            ids.add(str(task_id))
    return ids


def main() -> int:
    board = load_limen_file(TASKS)
    registry = load_supply_registry(REGISTRY)
    supply = dispatchable_supply(board)
    floor_raw = os.environ.get(registry.floor_env, "").strip()
    try:
        floor = int(floor_raw) if floor_raw else derived_daily_floor("jules", board)
    except ValueError:
        floor = derived_daily_floor("jules", board)

    pending = pending_inbox_ids(TASKS)
    deficit = max(floor - supply - len(pending), 0)
    armed = "--apply" in sys.argv[1:] or os.environ.get("LIMEN_JULES_SUPPLY_APPLY", "") == "1"

    minted = 0
    if deficit:
        existing = {task.id for task in board.tasks} | pending
        patches = expand_supply(
            registry,
            existing,
            deficit,
            created=datetime.now(timezone.utc).date().isoformat(),
        )
        if armed:
            for patch in patches:
                submit_task_upsert(TASKS, patch, agent="claude", session_id="jules-supply-organ")
                minted += 1
        else:
            minted = 0
            print(f"  jules-supply: DRY-RUN would mint {len(patches)} packet(s) — arm with LIMEN_JULES_SUPPLY_APPLY=1")

    print(f"  jules-supply: supply={supply} floor={floor} pending={len(pending)} deficit={deficit} minted={minted}")
    return 1 if deficit and not minted else 0


if __name__ == "__main__":
    raise SystemExit(main())
