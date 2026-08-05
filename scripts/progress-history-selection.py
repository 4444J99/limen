#!/usr/bin/env python3
"""Capture work-universe history, compare arbitrary windows, and rank next work."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.capacity import LOCAL_CHECKOUT_AGENTS, capacity_census  # noqa: E402
from limen.host_admission import AdmissionController, collect_pressure  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.progress_history import (  # noqa: E402
    ProgressHistoryError,
    build_progress_snapshot,
    collect_history_sources,
    compare_snapshots,
    load_history_adapters,
    load_snapshots,
    persist_snapshot,
    snapshot_at_or_before,
)
from limen.progress_selection import rank_next_work  # noqa: E402
from limen.progress_source_registry import build_source_registry  # noqa: E402


OWNER_ROOT = Path(os.environ.get("LIMEN_ROOT", ROOT))
TASKS = Path(os.environ.get("LIMEN_TASKS", OWNER_ROOT / "tasks.yaml"))
SNAPSHOT_DIR = OWNER_ROOT / "logs" / "progress-history-snapshots"
LATEST = OWNER_ROOT / "logs" / "progress-history-selection.json"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def _host_pressure() -> dict[str, Any]:
    observed = collect_pressure()
    controller = AdmissionController()
    completed = controller._complete_pressure(observed, None, time.time())
    return {
        "reasons": controller._pressure_reasons(completed),
        "observation": completed,
    }


def _resolve_snapshot(
    selector: str,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for snapshot in snapshots:
        if snapshot.get("snapshot_id") == selector:
            return snapshot
    path = Path(selector).expanduser()
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
        except (OSError, UnicodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None
    try:
        boundary = datetime.fromisoformat(selector.replace("Z", "+00:00"))
    except ValueError:
        return None
    if boundary.tzinfo is None:
        return None
    return snapshot_at_or_before(snapshots, boundary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 unless current source history is exhaustive")
    parser.add_argument("--json", action="store_true", help="print the current snapshot and optional delta")
    parser.add_argument("--write", action="store_true", help="persist the content-addressed snapshot and latest view")
    parser.add_argument("--from", dest="from_selector", help="baseline snapshot ID, file, or RFC 3339 boundary")
    parser.add_argument("--to", dest="to_selector", help="comparison snapshot ID, file, or RFC 3339 boundary")
    parser.add_argument("--tasks", type=Path, default=TASKS)
    parser.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument("--latest-output", type=Path, default=LATEST)
    args = parser.parse_args()

    try:
        board = load_limen_file(args.tasks)
        registry = build_source_registry(OWNER_ROOT)
        adapters, adapter_failures = load_history_adapters(OWNER_ROOT)
        contributions, contribution_failures = collect_history_sources(OWNER_ROOT, registry, adapters)
        capacity = [{**row, "local": str(row["agent"]) in LOCAL_CHECKOUT_AGENTS} for row in capacity_census(board)]
        pressure = _host_pressure()
        selection = rank_next_work(board.tasks, capacity, pressure)
        snapshot = build_progress_snapshot(
            registry,
            contributions,
            selection,
            failures=[*adapter_failures, *contribution_failures],
        )
        if args.write:
            persist_snapshot(snapshot, args.snapshot_dir)
        snapshots = load_snapshots(args.snapshot_dir)
        if not any(row.get("snapshot_id") == snapshot["snapshot_id"] for row in snapshots):
            snapshots.append(snapshot)
            snapshots.sort(key=lambda row: (str(row.get("generated_at")), str(row.get("snapshot_id"))))
        current = _resolve_snapshot(args.to_selector, snapshots) if args.to_selector else snapshot
        baseline = _resolve_snapshot(args.from_selector, snapshots) if args.from_selector else None
        if baseline is None and not args.from_selector and len(snapshots) >= 2:
            baseline = snapshots[-2]
        delta = compare_snapshots(baseline, current) if baseline is not None and current is not None else None
    except (OSError, ValueError, ProgressHistoryError) as exc:
        print(f"progress history failed: {exc}", file=sys.stderr)
        return 1

    output = {"snapshot": snapshot, "delta": delta}
    if args.write:
        _atomic_write(args.latest_output, output)
    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        mark = "✓" if snapshot["exhaustive"] else "✗"
        summary = snapshot["summary"]
        top = (snapshot["selection"].get("candidates") or [None])[0]
        top_text = f"{top['task_id']} score={top['score']}" if top else "none"
        print(
            f"{mark} history snapshot={snapshot['snapshot_id'][:12]} sources={summary['source_count']} "
            f"leaves={summary['leaf_count']} coverage_debt={summary['coverage_debt']} next={top_text} "
            f"ineligible={snapshot['selection']['ineligible_task_count']} "
            f"zero_proven={str(snapshot['selection']['zero_launch_proven']).lower()}"
        )
        if delta:
            print(
                f"  delta arrivals={delta['arrivals']} closures={delta['closures']} "
                f"reopened={delta['reopened_debt']} aged={delta['aged_active_leaves']} "
                f"verified_value={delta['verified_value_delta']}"
            )
    return 1 if args.check and not snapshot["exhaustive"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
