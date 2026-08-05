#!/usr/bin/env python3
"""mat-organ.py — daily-engine keeper (ORGAN, beat-invoked; health-organ is the precedent).

Keeps the private daily engine self-feeding, at most once per ~20h regardless of
beat tempo: (1) incremental ChatGPT-session pull (idempotent; catches stray app
use), (2) day-card pre-compose so the iCloud mirror is fresh before wake,
(3) roadblocks-queue refresh (his logged friction = the fix roadmap).

Privacy contract: all reads/writes happen INSIDE the mode-700 private tree via
its own tools; this script and its public state are counts-only — no titles,
no content, no health vocabulary. Fail-open: never blocks the beat.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
ENGINE_TREE = Path(
    os.environ.get(
        "LIMEN_MAT_DIR",
        Path.home() / "Workspace/_health-private/daily-mat-strength-brainstorms",
    )
)
STATE_PATH = LOGS / "mat-organ-state.json"
THROTTLE_HOURS = float(os.environ.get("LIMEN_MAT_THROTTLE_HOURS", "20"))

# exit codes of tools/pull_fresh.py (its contract)
PULL_NO_FRESH = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _due() -> bool:
    """The daily lane (pull/compose) keys on its OWN last-run stamp — the
    living lane (autoday/meal-watch) stamps every fire and must not reset it."""
    if not STATE_PATH.exists():
        return True
    try:
        state = json.loads(STATE_PATH.read_text())
        ran_at = state.get("full_ran_at") or state.get("ran_at", "")
        last = datetime.fromisoformat(ran_at)
    except (ValueError, OSError, json.JSONDecodeError):
        return True
    return _now() - last > timedelta(hours=THROTTLE_HOURS)


def _run(args: list[str], timeout: int) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args, cwd=ENGINE_TREE, capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 127, ""


def _pull_counts() -> dict:
    """Counts-only view of the pull report — never titles or content."""
    try:
        report = json.loads((ENGINE_TREE / "metadata/pull-report.json").read_text())
        chats = report.get("chats", {})
        return {
            "chats_new": len(chats.get("new", [])),
            "chats_updated": len(chats.get("updated", [])),
            "strays": len(report.get("stray_fresh_sessions", [])),
        }
    except (OSError, ValueError):
        return {}


def _stamp(record: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    try:
        voice = LOGS / ".voice"
        voice.mkdir(parents=True, exist_ok=True)
        (voice / "mat").write_text(record["ran_at"], encoding="utf-8")
    except OSError:
        pass  # stamp failure never blocks the beat


def main() -> int:
    if not ENGINE_TREE.exists():
        _stamp({"ran_at": _now().isoformat(timespec="seconds"), "tree_present": False})
        print("mat-organ: engine tree absent — stamped, no-op")
        return 0
    record: dict = {
        "ran_at": _now().isoformat(timespec="seconds"),
        "tree_present": True,
    }

    # EVERY-FIRE lane (v2, zero-tap living): the day opens/closes itself and
    # freshly-synced plate photos become logged meals within a beat or two.
    auto_exit, out = _run(["python3", "engine/mat.py", "autoday", "--json"], timeout=180)
    record["autoday_ok"] = auto_exit == 0
    if auto_exit == 0:
        try:
            data = json.loads(out).get("data", {})
            record["auto_closed"] = len(data.get("auto_closed", []))
            record["auto_opened"] = bool(data.get("auto_opened_today"))
        except ValueError:
            pass
    watch_exit, out = _run(["python3", "tools/meal_watch.py", "--json"], timeout=900)
    record["meal_watch_ok"] = watch_exit == 0
    if watch_exit == 0:
        try:
            record["meals_logged"] = json.loads(out).get("meals", 0)
        except ValueError:
            pass

    prior_full = None
    try:
        prior_full = json.loads(STATE_PATH.read_text()).get("full_ran_at")
    except (OSError, ValueError):
        pass

    def _prior_ran_at() -> str | None:
        try:
            return json.loads(STATE_PATH.read_text()).get("ran_at")
        except (OSError, ValueError):
            return None
    if not _due():
        record["throttled"] = True
        # preserve the daily lane's clock (v1-state migration: seed from ran_at)
        record["full_ran_at"] = prior_full or _prior_ran_at()
        _stamp(record)
        print(f"mat-organ: living lane ok (meals={record.get('meals_logged', '?')}"
              f" auto_closed={record.get('auto_closed', '?')}) — pull/compose throttled")
        return 0
    record["full_ran_at"] = record["ran_at"]

    pull_exit, _ = _run(["python3", "tools/pull_fresh.py"], timeout=600)
    record["pull_exit"] = pull_exit
    record["pull_ok"] = pull_exit in (0, PULL_NO_FRESH)
    record.update(_pull_counts())

    compose_exit, out = _run(["python3", "engine/mat.py", "today", "--json"], timeout=180)
    record["card_ok"] = compose_exit == 0
    if compose_exit == 0:
        try:
            record["card_checks_green"] = bool(json.loads(out).get("ok"))
        except ValueError:
            record["card_checks_green"] = None

    rb_exit, out = _run(["python3", "engine/mat.py", "roadblocks", "--json"], timeout=60)
    if rb_exit == 0:
        try:
            record["roadblocks_open"] = len(json.loads(out)["data"]["open"])
        except (ValueError, KeyError):
            pass

    _stamp(record)
    print(
        f"mat-organ: pull={'ok' if record['pull_ok'] else pull_exit}"
        f" new={record.get('chats_new', '?')} card={'ok' if record.get('card_ok') else 'FAIL'}"
        f" meals={record.get('meals_logged', '?')}"
        f" roadblocks={record.get('roadblocks_open', '?')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
