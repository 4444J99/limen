"""Pure view model plus stdlib curses shell for progress-history snapshots."""

from __future__ import annotations

import curses
import json
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from limen.progress_history import ProgressHistoryError, SNAPSHOT_SCHEMA, canonical_sha256


VIEW_SCHEMA = "limen.progress-tui-view.v1"
ZOOMS = ("macro", "sources", "leaves", "selection", "detail")
Zoom = Literal["macro", "sources", "leaves", "selection", "detail"]


@dataclass
class TuiState:
    zoom: Zoom = "macro"
    cursor: int = 0
    filters: dict[str, Any] = field(default_factory=dict)
    debt_only: bool = False
    verification_debt_only: bool = False
    paused: bool = False
    selected_key: str | None = None
    detail_kind: str | None = None
    trail: list[tuple[Zoom, int, dict[str, Any]]] = field(default_factory=list)


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    snapshot_id = str(snapshot.get("snapshot_id") or "")
    material = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
    if snapshot.get("schema") != SNAPSHOT_SCHEMA or snapshot_id != canonical_sha256(material):
        raise ProgressHistoryError("tui-snapshot-content-address-invalid")


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def filter_dimensions(snapshot: dict[str, Any]) -> list[str]:
    leaves = snapshot.get("leaves") or []
    fields = {
        key
        for leaf in leaves
        if isinstance(leaf, dict)
        for key, value in leaf.items()
        if _scalar(value) and key not in {"leaf_key", "content_sha256", "opened_at"}
    }
    return sorted(fields)


def _matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    return all(row.get(field) == value for field, value in filters.items())


def filtered_leaves(snapshot: dict[str, Any], state: TuiState) -> list[dict[str, Any]]:
    rows = [dict(row) for row in snapshot.get("leaves") or [] if isinstance(row, dict)]
    rows = [row for row in rows if _matches(row, state.filters)]
    if state.debt_only:
        rows = [row for row in rows if not bool(row.get("terminal"))]
    if state.verification_debt_only:
        rows = [row for row in rows if bool(row.get("terminal")) and not bool(row.get("verified_outcome"))]
    return sorted(rows, key=lambda row: (str(row.get("source_id")), str(row.get("leaf_key"))))


def _warnings(snapshot: dict[str, Any]) -> list[str]:
    summary = snapshot.get("summary") or {}
    selection = snapshot.get("selection") or {}
    warnings: list[str] = []
    if snapshot.get("exhaustive") is not True:
        warnings.append("INCOMPLETE SOURCE COVERAGE: snapshot is not exhaustive")
    coverage = int(summary.get("coverage_debt") or 0)
    if coverage:
        warnings.append(f"SOURCE COVERAGE DEBT: {coverage}")
    failures = snapshot.get("failures") or []
    if failures:
        warnings.append(f"SOURCE FAILURES: {len(failures)}")
    non_exhaustive = sum(not bool(source.get("exhaustive")) for source in snapshot.get("sources") or [])
    if non_exhaustive:
        warnings.append(f"NON-EXHAUSTIVE OWNERS: {non_exhaustive}")
    verification_debt = sum(
        bool(leaf.get("terminal")) and not bool(leaf.get("verified_outcome")) for leaf in snapshot.get("leaves") or []
    )
    if verification_debt:
        warnings.append(f"VERIFICATION DEBT: {verification_debt} terminal leaves lack verified outcomes")
    if not selection.get("candidates") and selection.get("zero_launch_proven") is not True:
        warnings.append(
            f"ZERO LAUNCH NOT PROVEN: {int(selection.get('ineligible_task_count') or 0)} ineligible open tasks"
        )
    return warnings


def _macro_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    summary = snapshot.get("summary") or {}
    selection = snapshot.get("selection") or {}
    return [
        {
            "row_type": "macro",
            "target": "sources",
            "label": "Source owners",
            "count": int(summary.get("source_count") or 0),
            "debt": sum(not bool(row.get("exhaustive")) for row in snapshot.get("sources") or []),
        },
        {
            "row_type": "macro",
            "target": "leaves",
            "preset_filter": {"terminal": False},
            "label": "Active leaves",
            "count": int(summary.get("active_count") or 0),
            "debt": int(summary.get("active_count") or 0),
        },
        {
            "row_type": "macro",
            "target": "leaves",
            "preset_filter": {"terminal": True},
            "label": "Terminal leaves",
            "count": int(summary.get("terminal_count") or 0),
            "debt": 0,
        },
        {
            "row_type": "macro",
            "target": "selection",
            "label": "Ranked next work",
            "count": int(selection.get("eligible_task_count") or 0),
            "debt": int(selection.get("ineligible_task_count") or 0),
        },
    ]


def _source_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "row_type": "source",
            "source_id": str(row.get("source_id")),
            "label": str(row.get("source_id")),
            "known_leaf_count": int(row.get("known_leaf_count") or 0),
            "declared_leaf_count": row.get("declared_leaf_count"),
            "exhaustive": row.get("exhaustive") is True,
            "owner": row.get("owner"),
        }
        for row in sorted(snapshot.get("sources") or [], key=lambda item: str(item.get("source_id")))
    ]


def _leaf_rows(snapshot: dict[str, Any], state: TuiState) -> list[dict[str, Any]]:
    return [
        {
            "row_type": "leaf",
            "leaf_key": row["leaf_key"],
            "label": f"{str(row['leaf_key'])[:12]} {row.get('source_id')} {row.get('kind')} {row.get('state')}",
            "source_id": row.get("source_id"),
            "kind": row.get("kind"),
            "state": row.get("state"),
            "terminal": row.get("terminal"),
            "verified_outcome": row.get("verified_outcome"),
            "evidence_count": len(row.get("evidence") or []),
        }
        for row in filtered_leaves(snapshot, state)
    ]


def _selection_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "row_type": "candidate",
            "task_id": row.get("task_id"),
            "label": f"#{row.get('rank')} {row.get('task_id')} score={row.get('score')}",
            "score": row.get("score"),
            "metric_debt": row.get("metric_debt") or [],
        }
        for row in snapshot.get("selection", {}).get("candidates") or []
    ]


def _detail(snapshot: dict[str, Any], state: TuiState) -> dict[str, Any] | None:
    if state.detail_kind == "leaf":
        return next(
            (dict(row) for row in snapshot.get("leaves") or [] if row.get("leaf_key") == state.selected_key),
            None,
        )
    if state.detail_kind == "candidate":
        return next(
            (
                dict(row)
                for row in snapshot.get("selection", {}).get("candidates") or []
                if row.get("task_id") == state.selected_key
            ),
            None,
        )
    return None


def build_view(snapshot: dict[str, Any], state: TuiState) -> dict[str, Any]:
    validate_snapshot(snapshot)
    if state.zoom == "macro":
        rows = _macro_rows(snapshot)
    elif state.zoom == "sources":
        rows = _source_rows(snapshot)
    elif state.zoom == "leaves":
        rows = _leaf_rows(snapshot, state)
    elif state.zoom == "selection":
        rows = _selection_rows(snapshot)
    else:
        detail = _detail(snapshot, state)
        rows = [{"row_type": "detail", "label": state.selected_key, "detail": detail}] if detail else []
    cursor = min(max(0, state.cursor), max(0, len(rows) - 1))
    state.cursor = cursor
    return {
        "schema": VIEW_SCHEMA,
        "source_snapshot_id": snapshot["snapshot_id"],
        "source_generated_at": snapshot["generated_at"],
        "source_exhaustive": snapshot["exhaustive"],
        "zoom": state.zoom,
        "breadcrumb": " / ".join([item[0] for item in state.trail] + [state.zoom]),
        "cursor": cursor,
        "filters": dict(sorted(state.filters.items())),
        "debt_only": state.debt_only,
        "verification_debt_only": state.verification_debt_only,
        "watch_paused": state.paused,
        "available_filter_dimensions": filter_dimensions(snapshot),
        "warnings": _warnings(snapshot),
        "rows": rows,
    }


def _push(state: TuiState) -> None:
    state.trail.append((state.zoom, state.cursor, deepcopy(state.filters)))


def transition(snapshot: dict[str, Any], state: TuiState, action: str, value: str | None = None) -> TuiState:
    updated = deepcopy(state)
    view = build_view(snapshot, updated)
    rows = view["rows"]
    if action == "down":
        updated.cursor = min(updated.cursor + 1, max(0, len(rows) - 1))
    elif action == "up":
        updated.cursor = max(0, updated.cursor - 1)
    elif action == "toggle-debt":
        updated.debt_only = not updated.debt_only
        updated.cursor = 0
    elif action == "toggle-verification":
        updated.verification_debt_only = not updated.verification_debt_only
        updated.cursor = 0
    elif action == "toggle-pause":
        updated.paused = not updated.paused
    elif action == "clear-filters":
        updated.filters = {}
        updated.debt_only = False
        updated.verification_debt_only = False
        updated.cursor = 0
    elif action == "filter":
        if not value or "=" not in value:
            raise ValueError("filter must be field=value")
        field_name, raw = value.split("=", 1)
        if field_name not in filter_dimensions(snapshot):
            raise ValueError("filter dimension is not present in this snapshot")
        normalized: Any = raw
        candidate = "null" if raw.lower() == "none" else raw
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            decoded = raw
        if _scalar(decoded):
            normalized = decoded
        updated.filters[field_name] = normalized
        updated.cursor = 0
    elif action == "back":
        if updated.trail:
            updated.zoom, updated.cursor, updated.filters = updated.trail.pop()
            updated.selected_key = None
            updated.detail_kind = None
    elif action == "enter" and rows:
        row = rows[updated.cursor]
        if updated.zoom == "macro":
            _push(updated)
            updated.zoom = row["target"]
            updated.filters.update(row.get("preset_filter") or {})
            updated.cursor = 0
        elif updated.zoom == "sources":
            _push(updated)
            updated.filters["source_id"] = row["source_id"]
            updated.zoom = "leaves"
            updated.cursor = 0
        elif updated.zoom == "leaves":
            _push(updated)
            updated.selected_key = row["leaf_key"]
            updated.detail_kind = "leaf"
            updated.zoom = "detail"
            updated.cursor = 0
        elif updated.zoom == "selection":
            _push(updated)
            updated.selected_key = row["task_id"]
            updated.detail_kind = "candidate"
            updated.zoom = "detail"
            updated.cursor = 0
    return updated


def _row_text(row: dict[str, Any]) -> list[str]:
    if row["row_type"] == "macro":
        return [f"{row['label']}: {row['count']}  debt={row['debt']}"]
    if row["row_type"] == "source":
        return [
            f"{row['label']}: known={row['known_leaf_count']} declared={row['declared_leaf_count']} "
            f"exhaustive={str(row['exhaustive']).lower()}"
        ]
    if row["row_type"] in {"leaf", "candidate"}:
        return [str(row["label"])]
    detail = row.get("detail") or {}
    lines = [f"DETAIL {row.get('label')}"]
    for key, value in sorted(detail.items()):
        if key == "evidence":
            lines.append("evidence / receipts:")
            lines.extend(f"  {item.get('field')}: {item.get('value')}" for item in value)
        elif key not in {"content_sha256"}:
            lines.append(f"{key}: {json.dumps(value, sort_keys=True)}")
    return lines


def render_text(snapshot: dict[str, Any], state: TuiState, *, width: int = 120) -> str:
    view = build_view(snapshot, state)
    lines = [
        f"LIMEN WORK UNIVERSE  snapshot={view['source_snapshot_id'][:12]}  "
        f"exhaustive={str(view['source_exhaustive']).lower()}  zoom={view['zoom']}",
        f"path: {view['breadcrumb']}",
    ]
    lines.extend(f"! {warning}" for warning in view["warnings"])
    filters = ", ".join(f"{key}={value}" for key, value in view["filters"].items()) or "none"
    lines.append(
        f"filters: {filters}; debt_only={str(view['debt_only']).lower()}; "
        f"verification_debt={str(view['verification_debt_only']).lower()}"
    )
    lines.append(
        "keys: arrows/jk move; enter zoom; h/backspace back; f filter; c clear; d debt; v verify; space pause; q quit"
    )
    for index, row in enumerate(view["rows"]):
        rendered = _row_text(row)
        marker = ">" if index == view["cursor"] else " "
        lines.append(f"{marker} {rendered[0]}")
        lines.extend(f"    {line}" for line in rendered[1:])
    return "\n".join(line[: max(20, width)] for line in lines)


def run_curses(
    loader: Callable[[], dict[str, Any]],
    *,
    watch_seconds: float = 2.0,
    initial_state: TuiState | None = None,
) -> None:
    def session(screen) -> None:
        state = initial_state if initial_state is not None else TuiState()
        snapshot = loader()
        last_refresh = time.monotonic()
        screen.keypad(True)
        screen.timeout(250)
        while True:
            height, width = screen.getmaxyx()
            screen.erase()
            for line_number, line in enumerate(render_text(snapshot, state, width=width).splitlines()[:height]):
                try:
                    screen.addnstr(line_number, 0, line, max(1, width - 1))
                except curses.error:
                    pass
            screen.refresh()
            key = screen.getch()
            if key in {ord("q"), 27}:
                return
            action = None
            if key in {curses.KEY_DOWN, ord("j")}:
                action = "down"
            elif key in {curses.KEY_UP, ord("k")}:
                action = "up"
            elif key in {curses.KEY_RIGHT, ord("l"), 10, 13}:
                action = "enter"
            elif key in {curses.KEY_LEFT, ord("h"), curses.KEY_BACKSPACE, 127}:
                action = "back"
            elif key == ord("d"):
                action = "toggle-debt"
            elif key == ord("v"):
                action = "toggle-verification"
            elif key == ord("c"):
                action = "clear-filters"
            elif key == ord(" "):
                action = "toggle-pause"
            elif key == ord("f"):
                curses.echo()
                screen.addstr(max(0, height - 1), 0, "filter field=value: ")
                raw = screen.getstr(max(0, height - 1), 20, max(1, width - 21)).decode(errors="replace")
                curses.noecho()
                try:
                    state = transition(snapshot, state, "filter", raw)
                except ValueError:
                    pass
            elif key == ord("r"):
                snapshot = loader()
                last_refresh = time.monotonic()
            if action:
                state = transition(snapshot, state, action)
            if not state.paused and time.monotonic() - last_refresh >= watch_seconds:
                refreshed = loader()
                if refreshed.get("snapshot_id") != snapshot.get("snapshot_id"):
                    snapshot = refreshed
                    build_view(snapshot, state)
                last_refresh = time.monotonic()

    curses.wrapper(session)
