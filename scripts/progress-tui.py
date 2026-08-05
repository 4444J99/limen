#!/usr/bin/env python3
"""Navigate one content-addressed progress-history snapshot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.progress_history import ProgressHistoryError, load_snapshots  # noqa: E402
from limen.progress_tui import TuiState, build_view, render_text, run_curses, transition, validate_snapshot  # noqa: E402


OWNER_ROOT = Path(os.environ.get("LIMEN_ROOT", ROOT))
SNAPSHOT_DIR = OWNER_ROOT / "logs" / "progress-history-snapshots"
LATEST = OWNER_ROOT / "logs" / "progress-history-selection.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProgressHistoryError(f"snapshot-unavailable:{path.name}") from exc
    if not isinstance(value, dict):
        raise ProgressHistoryError("snapshot-root-not-object")
    nested = value.get("snapshot")
    snapshot: dict[str, Any] = dict(nested) if isinstance(nested, dict) else value
    validate_snapshot(snapshot)
    return snapshot


def snapshot_loader(selector: str | None, snapshot_dir: Path, latest: Path):
    def load() -> dict[str, Any]:
        if selector:
            path = Path(selector).expanduser()
            if path.is_file():
                return _read(path)
            snapshots = load_snapshots(snapshot_dir)
            selected = next((row for row in snapshots if row.get("snapshot_id") == selector), None)
            if selected is None:
                raise ProgressHistoryError("snapshot-id-not-found")
            validate_snapshot(selected)
            return selected
        if latest.is_file():
            return _read(latest)
        snapshots = load_snapshots(snapshot_dir)
        if not snapshots:
            raise ProgressHistoryError("no-history-snapshot; run scripts/progress-history-selection.py --write first")
        return snapshots[-1]

    return load


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="snapshot file or content-addressed ID")
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--latest", type=Path, default=LATEST)
    parser.add_argument("--json", action="store_true", help="print the current zoom view as JSON")
    parser.add_argument("--plain", action="store_true", help="render the current zoom without curses")
    parser.add_argument("--zoom", choices=("macro", "sources", "leaves", "selection"), default="macro")
    parser.add_argument("--filter", action="append", default=[], help="repeatable dynamic field=value leaf filter")
    parser.add_argument("--debt-only", action="store_true")
    parser.add_argument("--verification-debt-only", action="store_true")
    parser.add_argument("--watch-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.watch_seconds < 0.25 or args.watch_seconds > 3600:
        parser.error("--watch-seconds must be between 0.25 and 3600")

    load = snapshot_loader(args.snapshot, args.snapshot_dir, args.latest)
    try:
        snapshot = load()
        state = TuiState(
            zoom=args.zoom,
            debt_only=args.debt_only,
            verification_debt_only=args.verification_debt_only,
        )
        for value in args.filter:
            state = transition(snapshot, state, "filter", value)
        if args.json:
            print(json.dumps(build_view(snapshot, state), indent=2, sort_keys=True))
            return 0
        if args.plain or not sys.stdout.isatty() or not sys.stdin.isatty():
            print(render_text(snapshot, state))
            return 0
        run_curses(load, watch_seconds=args.watch_seconds, initial_state=state)
        return 0
    except (OSError, ValueError, ProgressHistoryError) as exc:
        print(f"progress tui failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
