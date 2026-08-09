#!/usr/bin/env python3
"""Hermetic test for scripts/check-operator-gates.py — no network, no real board.

Exercises each held invariant (A–E), the shrink-only baseline ratchet, and the one regression
that matters most: an unreachable runtime store must surface as UNEVALUATED, never as a pass.
That bug was real — the first cut resolved `.agent-runtime` relative to the git WORKTREE, found
nothing, fail-opened, and silently reported 7 ghost escalations as live sessions.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "check-operator-gates.py"
SPEC = importlib.util.spec_from_file_location("check_operator_gates", SOURCE)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

failures: list[str] = []


def check(name: str, cond: bool) -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}")
        failures.append(name)


def stage(
    tmp: Path,
    *,
    tasks: list[dict],
    levers: list[dict] | None = None,
    marker: str | None = None,
    baseline: list[str] | None = None,
    runtime: bool = True,
) -> None:
    """Point the module's module-level paths at a synthetic estate."""
    (tmp / "logs").mkdir(parents=True, exist_ok=True)
    (tmp / "institutio" / "governance").mkdir(parents=True, exist_ok=True)
    board = tmp / "tasks.yaml"
    board.write_text(yaml.safe_dump({"version": "1.0", "tasks": tasks}), encoding="utf-8")
    lever_file = tmp / "his-hand-levers.json"
    lever_file.write_text(json.dumps({"levers": levers or []}), encoding="utf-8")
    base_file = tmp / "institutio" / "governance" / "operator-gate-baseline.txt"
    if baseline is not None:
        base_file.write_text("".join(f"{i}\n" for i in baseline), encoding="utf-8")
    # Clear what this stage does not set: the temp dir is reused across cases, and a marker or
    # baseline left behind by a previous case would leak into the next one.
    marker_file = tmp / "logs" / "AUTONOMY_PAUSED"
    if marker is not None:
        marker_file.write_text(marker, encoding="utf-8")
    elif marker_file.exists():
        marker_file.unlink()
    if baseline is None and base_file.exists():
        base_file.unlink()

    m.ROOT = tmp
    m.BOARD = board
    m.LEVERS = lever_file
    m.MARKER = marker_file
    m.BASELINE = base_file
    if runtime:
        (tmp / ".agent-runtime" / "claude").mkdir(parents=True, exist_ok=True)
    m.runtime_root = lambda: (tmp / ".agent-runtime") if runtime else None  # noqa: E731


def ids_for(violations: list[dict], check_id: str) -> set[str]:
    return {v["id"] for v in violations if v["check"] == check_id}


OK_LEVER = {"id": "L-FINE", "status": "open"}

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)

    # --- A: operator-paused is not a board label -------------------------------------
    stage(
        tmp,
        tasks=[
            {"id": "T-1", "status": "open", "labels": ["operator-paused"]},
            {"id": "T-2", "status": "open", "labels": ["other"]},
        ],
        levers=[OK_LEVER],
    )
    v, census = m.evaluate()
    check("A flags the machine-stamped operator-paused label", ids_for(v, "A") == {"T-1"})
    check("A ignores tasks without the label", "T-2" not in ids_for(v, "A"))
    check("census counts the label", census["operator_paused_labels"] == 1)

    # --- B: projection bookkeeping is not a human atom --------------------------------
    book = {
        "id": "T-BOOK",
        "status": "needs_human",
        "dispatch_log": [
            {
                "status": "needs_human",
                "agent": "heal-board",
                "output": "board-heal: append current status to reconcile latest transition log",
            }
        ],
    }
    real = {
        "id": "T-REAL",
        "status": "needs_human",
        "dispatch_log": [
            {
                "status": "needs_human",
                "agent": "limen",
                "output": "Awaiting human: authorize the irreversible state-dir relocation",
            }
        ],
    }
    stage(tmp, tasks=[book, real], levers=[OK_LEVER])
    v, _ = m.evaluate()
    check("B flags bookkeeping-set needs_human", ids_for(v, "B") == {"T-BOOK"})
    check("B leaves a genuine human atom alone", "T-REAL" not in ids_for(v, "B"))

    # --- C: ghost escalations, and the fail-open regression ---------------------------
    ghost = {"id": "ASK-quicken-escalate-deadbeef", "status": "needs_human"}
    stage(tmp, tasks=[ghost], levers=[OK_LEVER], runtime=True)
    v, census = m.evaluate()
    check("C flags an escalation whose session is absent", ids_for(v, "C") == {ghost["id"]})
    check("C reports nothing unevaluated when the store is reachable", census["unevaluated"] == [])

    stage(tmp, tasks=[ghost], levers=[OK_LEVER], runtime=False)
    v, census = m.evaluate()
    check(
        "REGRESSION: unreachable store yields UNEVALUATED, not a violation",
        ids_for(v, "C") == set() and census["unevaluated"] == [ghost["id"]],
    )
    check("REGRESSION: unreachable store is reported, never silently passed", census["runtime_store"] == "UNREACHABLE")

    # --- D: levers must carry an enum status ------------------------------------------
    stage(
        tmp,
        tasks=[],
        levers=[
            {"id": "L-NONE"},
            {"id": "L-PROSE", "status": "open — but only after the quota resets"},
            {"id": "L-OK", "status": "discharged"},
        ],
    )
    v, census = m.evaluate()
    check("D flags a lever with no status", "L-NONE" in ids_for(v, "D"))
    check("D flags a lever whose status is prose", "L-PROSE" in ids_for(v, "D"))
    check("D accepts an enum status", "L-OK" not in ids_for(v, "D"))
    check("census counts unreadable levers", census["levers_without_enum_status"] == 2)

    # --- E: a present marker must be attributable --------------------------------------
    stage(tmp, tasks=[], levers=[OK_LEVER], marker="reason: operator armed this\nexpires_at: 2030-01-01\n")
    v, _ = m.evaluate()
    check("E accepts a well-formed pause marker", ids_for(v, "E") == set())

    stage(tmp, tasks=[], levers=[OK_LEVER], marker="something happened\n")
    v, _ = m.evaluate()
    check("E flags an unattributed pause marker", ids_for(v, "E") == {"logs/AUTONOMY_PAUSED"})

    # --- baseline exempts, and only exempts what it lists -------------------------------
    stage(
        tmp, tasks=[{"id": "T-1", "status": "open", "labels": ["operator-paused"]}], levers=[OK_LEVER], baseline=["T-1"]
    )
    v, census = m.evaluate()
    check("baseline exempts a recorded id", v == [])
    check("baseline count is reported", census["baselined"] == 1)

    stage(
        tmp,
        tasks=[{"id": "T-NEW", "status": "open", "labels": ["operator-paused"]}],
        levers=[OK_LEVER],
        baseline=["T-1"],
    )
    v, _ = m.evaluate()
    check("baseline does NOT exempt a fresh violation", ids_for(v, "A") == {"T-NEW"})

print()
if failures:
    print(f"operator-gates.test: FAIL ({len(failures)} check(s)): {failures}")
    raise SystemExit(1)
print("operator-gates.test: OK")
