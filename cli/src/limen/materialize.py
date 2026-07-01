"""Event-sourced projection of the Limen board — step 1 of the evolved board design.

The problem this dissolves: `tasks.yaml` is a live, continuously-rewritten SSOT stored as one
monolithic YAML blob under git. Every mutation reserializes all ~72k lines, so the working tree is
never clean, a `+35 tasks` change diffs as ~50k lines of churn, and N uncoordinated writers tear
the file under a lock (the collapse-guard / torn-write incidents in io.py).

The evolved form: **commit the transitions, derive the state.** The board is not a document — it is
the current projection of an append-only stream of task transitions. `board = fold(events)`. The
log is the truth (tiny appends, concurrency-safe by construction, self-documenting history); the
72k-line `tasks.yaml` becomes a *cache* — regenerable at any time, therefore never load-bearing.

This module is that `fold`. It is deliberately **pure** — no subprocess, no filesystem, no clock —
so it is trivially testable and can later back the runtime projection unchanged. Step 1 commits us
to nothing: it only proves the ideal form reproduces reality *exactly*, by rebuilding a `LimenFile`
whose `io.save_limen_file` serialization is byte-identical to the live board (the on-disk board is
already canonical, so byte-identity through the existing serializer is the achievable bar).

Event shape (JSON-serializable dicts, so a log is a plain `events.jsonl`):

    {"type": "board.meta",   "data": {"version": "1.0", "portal": {...}}}
    {"type": "task.upsert",  "task_id": "T-123", "data": {<full task field-set>}}
    {"type": "task.remove",  "task_id": "T-123"}

`task.upsert` carries a task's whole field-set (create-or-replace); folding upserts in order and
updating a dict value in place preserves first-seen position — so an append-stable board round-trips
byte-identically. `task.remove` drops an id (a task pruned/archived out of the board).
"""

from __future__ import annotations

from typing import Any

from limen.models import LimenFile

# --- event type tags -------------------------------------------------------------------------
EV_BOARD_META = "board.meta"  # set version + portal (board-level metadata)
EV_BOARD_ORDER = "board.order"  # set the task display order (an id sequence) — order is state too
EV_TASK_UPSERT = "task.upsert"  # create-or-replace a task's full field-set, keyed by id
EV_TASK_REMOVE = "task.remove"  # drop a task id from the board (prune/archive-out)

Event = dict[str, Any]


def fold(events: list[Event]) -> LimenFile:
    """Replay an event stream into the materialized board — the whole thesis in one function.

    Deterministic and side-effect-free. Task position is first-seen insertion order: re-`upsert`ing
    an existing id updates its value *in place* (Python dict semantics) without moving it, so a
    board whose tasks are only ever appended reconstructs in the exact same order it was written —
    the property the byte-identity proof relies on.
    """
    version = "1.0"
    portal: dict[str, Any] | None = None
    tasks: dict[str, dict[str, Any]] = {}  # id -> field-set; dict preserves first-seen order
    order: list[str] | None = None  # explicit final task order, if the log ever set one

    for ev in events:
        etype = ev.get("type")
        if etype == EV_BOARD_META:
            data = ev.get("data") or {}
            if "version" in data:
                version = data["version"]
            if data.get("portal") is not None:
                portal = data["portal"]
        elif etype == EV_BOARD_ORDER:
            order = list(ev.get("data", {}).get("ids", []))
        elif etype == EV_TASK_UPSERT:
            tasks[ev["task_id"]] = ev["data"]
        elif etype == EV_TASK_REMOVE:
            tasks.pop(ev["task_id"], None)
        else:
            raise ValueError(f"unknown event type: {etype!r}")

    if order is not None:
        # honor the explicit order for ids still present, then append any never-ordered tasks in
        # first-seen order (so a stale order event can never drop a live task).
        ordered = [tasks[tid] for tid in order if tid in tasks]
        seen = set(order)
        ordered.extend(v for tid, v in tasks.items() if tid not in seen)
        task_list = ordered
    else:
        task_list = list(tasks.values())

    raw: dict[str, Any] = {"version": version}
    if portal is not None:
        raw["portal"] = portal
    raw["tasks"] = task_list
    # model_validate re-applies field defaults + validation, exactly as a normal load would — so a
    # folded board is indistinguishable from a loaded one, and save_limen_file serializes it the
    # same way.
    return LimenFile.model_validate(raw)


def seed_events_from_board(board: LimenFile) -> list[Event]:
    """Emit the minimal event stream that folds back to `board` — one `board.meta` + one
    `task.upsert` per task, in board order. This is the loss-free snapshot seed: `fold` of it
    reproduces the board. (Step 2 seeds the log instead by replaying real git-history transitions;
    both must fold to the same board — that is the design's consistency invariant.)
    """
    data = board.model_dump(mode="json", exclude_none=True)
    events: list[Event] = [
        {"type": EV_BOARD_META, "data": {"version": data.get("version", "1.0"), "portal": data.get("portal")}}
    ]
    for task in data.get("tasks", []):
        events.append({"type": EV_TASK_UPSERT, "task_id": task["id"], "data": task})
    return events


def diff_boards(prev: LimenFile | None, cur: LimenFile) -> list[Event]:
    """Derive the transition events between two successive board versions — the primitive that turns
    git history into an event log. Emits a `task.upsert` for every task that is new or whose
    field-set changed, a `task.remove` for every id that disappeared, and a `board.meta` when the
    board-level metadata (version/portal) changed. Folding the concatenation of these deltas across
    every commit reconstructs the final board (see the git-replay proof).
    """
    events: list[Event] = []
    prev_data = prev.model_dump(mode="json", exclude_none=True) if prev is not None else {"tasks": []}
    cur_data = cur.model_dump(mode="json", exclude_none=True)

    if (
        prev is None
        or prev_data.get("version") != cur_data.get("version")
        or prev_data.get("portal") != cur_data.get("portal")
    ):
        events.append(
            {
                "type": EV_BOARD_META,
                "data": {"version": cur_data.get("version", "1.0"), "portal": cur_data.get("portal")},
            }
        )

    prev_list = prev_data.get("tasks", [])
    cur_list = cur_data.get("tasks", [])
    prev_tasks = {t["id"]: t for t in prev_list}
    cur_ids = set()
    for task in cur_list:
        cur_ids.add(task["id"])
        if prev_tasks.get(task["id"]) != task:
            events.append({"type": EV_TASK_UPSERT, "task_id": task["id"], "data": task})
    for tid in prev_tasks:
        if tid not in cur_ids:
            events.append({"type": EV_TASK_REMOVE, "task_id": tid})

    # Order is state too: emit board.order iff the surviving id sequence was reordered (not merely
    # grown by appends, which first-seen fold already reproduces). Cheap to detect, rare in practice,
    # and it is what makes a full history-replay reconstruct the board's exact row order.
    cur_order = [t["id"] for t in cur_list]
    prev_order_surviving = [tid for tid in (t["id"] for t in prev_list) if tid in cur_ids]
    cur_order_previously_seen = [tid for tid in cur_order if tid in prev_tasks]
    if prev_order_surviving != cur_order_previously_seen:
        events.append({"type": EV_BOARD_ORDER, "data": {"ids": cur_order}})
    return events
