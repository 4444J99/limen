from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from limen.progress_history import ProgressHistoryError, build_progress_snapshot, canonical_sha256
from limen.progress_tui import (
    TuiState,
    build_view,
    filter_dimensions,
    filtered_leaves,
    render_text,
    transition,
    validate_snapshot,
)


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]


def leaf(
    key: str,
    source: str,
    kind: str,
    state: str,
    *,
    terminal: bool,
    verified: bool,
    evidence: list[dict[str, str]] | None = None,
) -> dict:
    return {
        "leaf_key": key.rjust(64, "0")[-64:],
        "source_id": source,
        "kind": kind,
        "state": state,
        "terminal": terminal,
        "reopened": False,
        "verified_outcome": verified,
        "verified_value_units": 1 if verified else 0,
        "is_ask": kind == "ask",
        "opened_at": None,
        "actual": {
            "runs": 1,
            "input_tokens": None,
            "output_tokens": None,
            "cache_tokens": None,
            "dollars_usd": None,
            "elapsed_seconds": 2,
            "host_local_seconds": None,
        },
        "evidence": evidence or [],
        "content_sha256": "f" * 64,
    }


def snapshot(*, exhaustive: bool = False, leaves: list[dict] | None = None) -> dict:
    rows = leaves or [
        leaf(
            "1",
            "alpha-source",
            "ask",
            "open",
            terminal=False,
            verified=False,
            evidence=[
                {"field": "predicate", "value": "pytest -q"},
                {"field": "receipt", "value": "github:owner/repo:pull-request:1"},
            ],
        ),
        leaf("2", "alpha-source", "task", "done", terminal=True, verified=False),
        leaf("3", "beta-renamed", "task", "done", terminal=True, verified=True),
    ]
    contributions = []
    for source_id in sorted({row["source_id"] for row in rows}):
        owned = [row for row in rows if row["source_id"] == source_id]
        contributions.append(
            {
                "source_id": source_id,
                "owner": {"id": "owner", "surface": source_id},
                "cursor": {"cursor": "end"},
                "source_content_sha256": "a" * 64,
                "document_path_hash": "b" * 64,
                "document_content_sha256": "c" * 64,
                "exhaustive": exhaustive,
                "declared_leaf_count": len(owned),
                "known_leaf_count": len(owned),
                "truncated_leaf_count": 0,
                "leaf_failure_count": 0,
                "leaves": owned,
            }
        )
    registry = {
        "semantic_status": "ready" if exhaustive else "partial",
        "content_sha256": "d" * 64,
        "summary": {"coverage_debt": 0 if exhaustive else 1},
    }
    selection = {
        "schema": "limen.progress-selection.v1",
        "eligible_task_count": 1,
        "ineligible_task_count": 2,
        "zero_launch_proven": False,
        "candidates": [
            {
                "task_id": "NEXT-1",
                "rank": 1,
                "score": 4.25,
                "factors": {"value": 1, "provider_headroom": 0.5},
                "metric_debt": ["confidence-missing"],
                "eligible_capacity": [{"agent": "provider-renamed"}],
            }
        ],
        "content_sha256": "e" * 64,
    }
    return build_progress_snapshot(
        registry,
        contributions,
        selection,
        generated_at=NOW,
        failures=[] if exhaustive else ["alpha-source:partial"],
    )


def test_every_view_retains_exact_snapshot_and_visible_debt_warnings() -> None:
    current = snapshot()
    view = build_view(current, TuiState())

    assert view["source_snapshot_id"] == current["snapshot_id"]
    assert view["source_exhaustive"] is False
    assert view["warnings"][0].startswith("INCOMPLETE SOURCE COVERAGE")
    assert any("VERIFICATION DEBT: 1" in warning for warning in view["warnings"])
    assert any("SOURCE FAILURES" in warning for warning in view["warnings"])


def test_macro_source_leaf_detail_navigation_reaches_receipts_and_predicates() -> None:
    current = snapshot()
    state = transition(current, TuiState(), "enter")
    assert state.zoom == "sources"
    state = transition(current, state, "enter")
    assert state.zoom == "leaves"
    assert state.filters == {"source_id": "alpha-source"}
    state = transition(current, state, "enter")
    assert state.zoom == "detail"

    view = build_view(current, state)
    detail = view["rows"][0]["detail"]
    assert detail["evidence"] == [
        {"field": "predicate", "value": "pytest -q"},
        {"field": "receipt", "value": "github:owner/repo:pull-request:1"},
    ]
    assert "github:owner/repo:pull-request:1" in render_text(current, state)

    state = transition(current, state, "back")
    assert state.zoom == "leaves"
    state = transition(current, state, "back")
    assert state.zoom == "sources"


def test_cross_dimension_filters_and_debt_toggles_compose() -> None:
    current = snapshot()
    state = TuiState(zoom="leaves")
    state = transition(current, state, "filter", "source_id=alpha-source")
    state = transition(current, state, "filter", "kind=task")
    assert [row["state"] for row in filtered_leaves(current, state)] == ["done"]

    state = transition(current, state, "toggle-verification")
    assert len(filtered_leaves(current, state)) == 1
    state = transition(current, state, "toggle-debt")
    assert filtered_leaves(current, state) == []
    assert {"source_id", "kind", "state", "terminal", "verified_outcome"} <= set(filter_dimensions(current))


def test_filter_values_preserve_boolean_and_numeric_scalar_types() -> None:
    current = snapshot()

    assert transition(current, TuiState(), "filter", "terminal=false").filters["terminal"] is False
    assert transition(current, TuiState(), "filter", "verified_value_units=1").filters["verified_value_units"] == 1


def test_filter_rejects_dimensions_not_present_in_the_snapshot() -> None:
    with pytest.raises(ValueError, match="not present"):
        transition(snapshot(), TuiState(zoom="leaves"), "filter", "model=fixed")


def test_selection_zoom_and_candidate_drill_down_share_the_snapshot() -> None:
    current = snapshot()
    state = TuiState(zoom="selection")
    state = transition(current, state, "enter")
    view = build_view(current, state)

    assert state.zoom == "detail"
    assert view["source_snapshot_id"] == current["snapshot_id"]
    assert view["rows"][0]["detail"]["task_id"] == "NEXT-1"
    assert view["rows"][0]["detail"]["eligible_capacity"] == [{"agent": "provider-renamed"}]


def test_watch_refresh_preserves_filters_and_clamps_cursor() -> None:
    first = snapshot()
    state = TuiState(zoom="leaves", cursor=20, filters={"source_id": "alpha-source"})
    build_view(first, state)
    assert state.cursor == 1

    second = snapshot(leaves=[leaf("1", "alpha-source", "ask", "open", terminal=False, verified=False)])
    view = build_view(second, state)
    assert state.filters == {"source_id": "alpha-source"}
    assert view["cursor"] == 0
    assert view["source_snapshot_id"] == second["snapshot_id"]


def test_plain_renderer_never_hides_debt_behind_a_progress_bar() -> None:
    rendered = render_text(snapshot(), TuiState(), width=100)
    assert "SOURCE COVERAGE DEBT" in rendered
    assert "VERIFICATION DEBT" in rendered
    assert "ZERO LAUNCH" not in rendered  # one real candidate exists
    assert "% complete" not in rendered.lower()
    assert "snapshot=" in rendered


def test_unproven_zero_launch_is_always_a_warning_not_an_empty_success() -> None:
    current = snapshot()
    current["selection"]["candidates"] = []
    current["selection"]["eligible_task_count"] = 0
    material = {key: value for key, value in current.items() if key != "snapshot_id"}
    current["snapshot_id"] = canonical_sha256(material)

    view = build_view(current, TuiState())

    assert any("ZERO LAUNCH NOT PROVEN" in warning for warning in view["warnings"])


def test_tampered_snapshot_is_rejected_before_any_renderer_uses_it() -> None:
    current = snapshot(exhaustive=True)
    validate_snapshot(current)
    current["summary"]["leaf_count"] = 999
    with pytest.raises(ProgressHistoryError, match="content-address-invalid"):
        build_view(current, TuiState())


def test_json_and_plain_cli_render_the_same_content_addressed_snapshot(tmp_path: Path) -> None:
    current = snapshot()
    path = tmp_path / "latest.json"
    path.write_text(json.dumps({"snapshot": current}))
    env = {**os.environ, "PYTHONPATH": str(ROOT / "cli" / "src")}

    json_result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "progress-tui.py"), "--snapshot", str(path), "--json"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    plain_result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "progress-tui.py"), "--snapshot", str(path), "--plain"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert json_result.returncode == 0
    assert plain_result.returncode == 0
    assert json.loads(json_result.stdout)["source_snapshot_id"] == current["snapshot_id"]
    assert current["snapshot_id"][:12] in plain_result.stdout
    assert "SOURCE COVERAGE DEBT" in plain_result.stdout
