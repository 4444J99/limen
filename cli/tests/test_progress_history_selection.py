from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from limen.progress_history import (
    ProgressHistoryError,
    build_progress_snapshot,
    canonical_sha256,
    collect_history_sources,
    compare_snapshots,
    load_history_adapters,
    load_snapshots,
    persist_snapshot,
    snapshot_at_or_before,
)
from limen.progress_selection import rank_next_work


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def registry(source_id: str, content_hash: str, *, ready: bool = True) -> dict:
    return {
        "schema": "limen.progress-source-registry.v1",
        "generated_at": NOW.isoformat(),
        "semantic_status": "ready" if ready else "partial",
        "content_sha256": "b" * 64,
        "summary": {"coverage_debt": 0 if ready else 1},
        "sources": [
            {
                "source_id": source_id,
                "owner": {"id": "owner/repo", "surface": "arbitrary-surface"},
                "cursor": {"page": "last"},
                "content_sha256": content_hash,
                "semantic_status": "ready" if ready else "partial",
                "exhaustive": ready,
            }
        ],
    }


def write_adapter(root: Path, source_id: str = "renamed-source") -> None:
    directory = root / "config" / "progress-history-sources"
    directory.mkdir(parents=True)
    (directory / "arbitrary.json").write_text(
        json.dumps(
            {
                "schema": "limen.progress-history-adapter.v1",
                "source_id": source_id,
                "document_paths": ["runtime/facts.json"],
                "evidence_fields": ["receipt"],
                "leaf_field": "items",
                "identity_fields": ["opaque_id"],
                "state_fields": ["phase"],
                "terminal_values": ["closed"],
                "reopened_values": ["reopened"],
                "verified_field": "verified",
                "actual_field": "usage",
                "kind_field": "kind",
                "ask_kind_values": ["ask"],
                "timestamp_fields": ["created_at"],
            }
        )
    )


def document(source_id: str, leaves: list[dict], content_hash: str) -> dict:
    return {
        "source_report": {
            "source_id": source_id,
            "content_sha256": content_hash,
            "exhaustive": True,
            "normalized_leaf_count": len(leaves),
        },
        "items": leaves,
    }


def test_dynamic_adapter_normalizes_renamed_source_without_exposing_identity(tmp_path: Path) -> None:
    source_id = "totally-renamed-owner-source"
    write_adapter(tmp_path, source_id)
    leaves = [
        {
            "opaque_id": "private-identity",
            "phase": "closed",
            "verified": True,
            "kind": "ask",
            "created_at": "2026-07-20T00:00:00Z",
            "usage": {"runs": 1, "dollars_usd": 0},
        }
    ]
    content_hash = canonical_sha256(leaves)
    facts = tmp_path / "runtime" / "facts.json"
    facts.parent.mkdir()
    facts.write_text(json.dumps(document(source_id, leaves, content_hash)))
    adapters, adapter_failures = load_history_adapters(tmp_path)

    contributions, failures = collect_history_sources(tmp_path, registry(source_id, content_hash), adapters)

    assert adapter_failures == []
    assert failures == []
    assert contributions[0]["exhaustive"] is True
    leaf = contributions[0]["leaves"][0]
    assert leaf["terminal"] is True
    assert leaf["verified_outcome"] is True
    assert leaf["is_ask"] is True
    assert leaf["actual"]["dollars_usd"] == 0
    assert "private-identity" not in json.dumps(contributions)


def test_missing_or_hash_mismatched_owner_document_stays_coverage_debt(tmp_path: Path) -> None:
    write_adapter(tmp_path)
    adapters, _ = load_history_adapters(tmp_path)
    contributions, failures = collect_history_sources(tmp_path, registry("renamed-source", "a" * 64), adapters)
    assert contributions == []
    assert failures == ["renamed-source:history-document-unavailable"]

    facts = tmp_path / "runtime" / "facts.json"
    facts.parent.mkdir()
    facts.write_text(json.dumps(document("renamed-source", [], "b" * 64)))
    contributions, failures = collect_history_sources(tmp_path, registry("renamed-source", "a" * 64), adapters)
    assert contributions == []
    assert failures == ["renamed-source:history-document-source-hash-mismatch"]


def selection() -> dict:
    return {"schema": "limen.progress-selection.v1", "candidates": [], "content_sha256": "c" * 64}


def leaf(
    key: str,
    *,
    terminal: bool = False,
    reopened: bool = False,
    verified: bool = False,
    ask: bool = False,
    runs: int = 0,
) -> dict:
    return {
        "leaf_key": key,
        "source_id": "source",
        "kind": "ask" if ask else "task",
        "state": "done" if terminal else "open",
        "terminal": terminal,
        "reopened": reopened,
        "verified_outcome": verified,
        "verified_value_units": 1 if verified else 0,
        "is_ask": ask,
        "opened_at": None,
        "actual": {
            "runs": runs,
            "input_tokens": None,
            "output_tokens": None,
            "cache_tokens": None,
            "dollars_usd": None,
            "elapsed_seconds": None,
            "host_local_seconds": None,
        },
        "content_sha256": key.rjust(64, "0")[-64:],
    }


def snapshot(leaves: list[dict], at: datetime) -> dict:
    contribution = {
        "source_id": "source",
        "owner": {"id": "owner", "surface": "surface"},
        "cursor": {},
        "source_content_sha256": "a" * 64,
        "document_path_hash": "b" * 64,
        "document_content_sha256": "c" * 64,
        "exhaustive": True,
        "declared_leaf_count": len(leaves),
        "known_leaf_count": len(leaves),
        "truncated_leaf_count": 0,
        "leaf_failure_count": 0,
        "leaves": leaves,
    }
    return build_progress_snapshot(registry("source", "a" * 64), [contribution], selection(), generated_at=at)


def test_content_addressed_snapshot_persistence_is_idempotent_and_tamper_evident(tmp_path: Path) -> None:
    current = snapshot([leaf("1")], NOW)
    path = persist_snapshot(current, tmp_path)
    assert persist_snapshot(current, tmp_path) == path
    assert path.stat().st_mode & 0o777 == 0o600
    assert load_snapshots(tmp_path) == [current]
    assert snapshot_at_or_before(load_snapshots(tmp_path), NOW + timedelta(seconds=1)) == current

    payload = json.loads(path.read_text())
    payload["summary"]["leaf_count"] = 99
    path.write_text(json.dumps(payload))
    with pytest.raises(ProgressHistoryError, match="content-address-invalid"):
        load_snapshots(tmp_path)


def test_arbitrary_window_delta_separates_arrival_closure_reopen_aging_and_spend() -> None:
    baseline = snapshot(
        [
            leaf("close"),
            leaf("reopen", terminal=True, verified=True, ask=True, runs=1),
            leaf("age"),
            leaf("disappear"),
        ],
        NOW,
    )
    current = snapshot(
        [
            leaf("close", terminal=True, verified=True, runs=2),
            leaf("reopen"),
            leaf("age"),
            leaf("arrival", ask=True, runs=3),
        ],
        NOW + timedelta(days=2),
    )

    delta = compare_snapshots(baseline, current)

    assert delta["arrivals"] == 1
    assert delta["closures"] == 1
    assert delta["reopened_debt"] == 1
    assert delta["disappeared_without_terminal_receipt"] == 1
    assert delta["aged_active_leaves"] == 1
    assert delta["aging_seconds_added"] == 172800
    assert delta["actual_spend_delta"]["runs"] == 4
    assert delta["verified_value_delta"] == 0
    assert delta["ask_arrival_delta"] == 0
    assert delta["verified_ask_outcome_delta"] == -1
    assert delta["ask_vs_outcome_gap_delta"] == 1


def task(task_id: str, **overrides) -> dict:
    row = {
        "id": task_id,
        "status": "open",
        "target_agent": "any",
        "budget_cost": 1,
        "depends_on": [],
        "labels": [],
        "repo": "owner/repo",
        "origin": "human_prompt",
        "horizon": "present",
        "value_case": "Deliver one bounded verified outcome",
        "owner_surface": "owner/repo",
        "predicate": "python3 -m pytest cli/tests/test_progress_history_selection.py -q",
        "receipt_target": f"github:owner/repo:pull-request:{task_id}",
        "value_score": 0,
        "cost_of_delay_score": 0,
        "confidence": 1,
    }
    row.update(overrides)
    return row


def capacity(agent: str, *, remaining: int | None, limit: int, local: bool, reachable: bool = True) -> dict:
    return {
        "agent": agent,
        "kind": "arbitrary-kind",
        "remaining": remaining,
        "limit": limit,
        "local": local,
        "reachable": reachable,
    }


def test_selection_ranks_live_value_delay_dependencies_confidence_and_headroom() -> None:
    tasks = [
        task("VALUE", value_score=3, confidence=0.9, target_agent="provider-renamed"),
        task("UNBLOCK", value_score=1, cost_of_delay_score=2, target_agent="provider-renamed"),
        task("DEPENDENT", depends_on=["UNBLOCK"], target_agent="provider-renamed"),
        task("PAUSED", value_score=100, labels=["operator-paused"], target_agent="provider-renamed"),
    ]
    result = rank_next_work(
        tasks,
        [capacity("provider-renamed", remaining=8, limit=10, local=False)],
        {"reasons": []},
        now=NOW,
    )

    assert [row["task_id"] for row in result["candidates"]] == ["UNBLOCK", "VALUE"]
    unblock = next(row for row in result["candidates"] if row["task_id"] == "UNBLOCK")
    assert unblock["factors"]["dependency_impact"] == 1
    assert unblock["factors"]["provider_headroom"] == 0.8
    assert result["ineligible"] == [
        {
            "task_id": "DEPENDENT",
            "reason": "dependencies-unmet",
            "metric_debt": ["dependency:UNBLOCK"],
        },
        {
            "task_id": "PAUSED",
            "reason": "task-held-by-durable-label",
            "metric_debt": ["operator-paused"],
        },
    ]
    assert all("model" not in json.dumps(row).lower() for row in result["candidates"])


def test_host_pressure_routes_to_live_remote_metadata_without_fixed_lane_table() -> None:
    result = rank_next_work(
        [task("REMOTE-SAFE")],
        [
            capacity("local-renamed", remaining=10, limit=10, local=True),
            capacity("remote-renamed", remaining=None, limit=0, local=False),
        ],
        {"reasons": ["swap-fraction"]},
        now=NOW,
    )

    [candidate] = result["candidates"]
    assert [row["agent"] for row in candidate["eligible_capacity"]] == ["remote-renamed"]
    assert "remote-renamed:provider-headroom-unmeasured" in candidate["metric_debt"]


def test_missing_selection_metrics_and_no_capacity_are_explicit_debt() -> None:
    result = rank_next_work(
        [
            task("UNKNOWN", value_score=None, cost_of_delay_score=None, confidence=None, target_agent="other"),
            task("NO-CAPACITY", target_agent="dark"),
        ],
        [capacity("other", remaining=1, limit=1, local=False)],
        {"reasons": []},
        now=NOW,
    )
    [candidate] = result["candidates"]
    assert candidate["task_id"] == "UNKNOWN"
    assert candidate["metric_debt"] == [
        "confidence-missing",
        "cost-of-delay-missing",
        "value-score-missing",
    ]
    assert result["ineligible"] == [
        {"task_id": "NO-CAPACITY", "reason": "no-live-eligible-capacity", "metric_debt": []}
    ]
    assert result["zero_launch_proven"] is False


def test_zero_launch_is_proven_only_when_exhaustive_board_has_no_open_work() -> None:
    result = rank_next_work(
        [task("DONE", status="done")],
        [capacity("renamed", remaining=1, limit=1, local=False)],
        {"reasons": []},
        now=NOW,
    )
    assert result["open_task_count"] == 0
    assert result["zero_launch_proven"] is True
