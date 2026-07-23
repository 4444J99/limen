from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import limen.dispatch as D
import pytest
from limen import census
from limen.models import BudgetTrack, Task
from limen.plan_handoff import (
    BUILD_FROM_PLAN_LABEL,
    PLAN_ONLY_LABEL,
    PLAN_RECEIPT_SCHEMA,
    PlanHandoffResult,
    PlanReceiptError,
    build_plan_receipt,
    builder_task_from_receipt,
    select_live_builder,
    task_contract_digest,
    validate_plan_receipt,
)


def _task(**updates: object) -> Task:
    values: dict[str, object] = {
        "id": "PLAN-1",
        "title": "design a bounded repair",
        "description": "keep the build separate from planning",
        "repo": "organvm/example",
        "target_agent": "claude",
        "labels": [PLAN_ONLY_LABEL, "tier:planner-context", "repair"],
        "context": "Existing evidence.",
        "predicate": "focused tests pass",
        "receipt_target": "PR checks",
        "created": date(2026, 7, 23),
    }
    values.update(updates)
    return Task(**values)  # type: ignore[arg-type]


def _profile(*capabilities: str) -> census.ExecutionProfile:
    return census.ExecutionProfile(
        capabilities=frozenset(capabilities),
        transport="fixture",
        native_fanout=False,
        harvest_method="fixture",
        concurrency_ref="fixture",
        meter_ref="fixture",
        health_ref="fixture",
        auth_ref="fixture",
    )


def _row(agent: str, *, reachable: bool) -> dict[str, object]:
    return {
        "agent": agent,
        "kind": "local-cli",
        "reachable": reachable,
        "detail": "fixture",
        "command": [agent],
        "limit": 10,
        "spent": 0,
        "remaining": 10,
    }


def _resign(receipt: dict[str, object]) -> None:
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    receipt["receipt_digest"] = hashlib.sha256(canonical.encode()).hexdigest()


def test_plan_receipt_is_digest_bound_and_contains_no_model_selection() -> None:
    task = _task(claude_tier="opus")
    receipt = build_plan_receipt(
        task,
        "1. Inspect the parser.\n2. Add a focused regression.",
        planner_agent="claude",
        created_at=datetime(2026, 7, 23, 12, tzinfo=UTC),
    )

    assert receipt["schema"] == PLAN_RECEIPT_SCHEMA
    assert receipt["task_contract_digest"] == task_contract_digest(task)
    assert receipt["execution_profile"] == {"planning_only": True, "build_allowed": False}
    assert "model" not in json.dumps(receipt).lower()
    assert validate_plan_receipt(receipt) == receipt


def test_plan_receipt_rejects_provider_model_or_catalog_pins() -> None:
    receipt = build_plan_receipt(_task(), "Implement the bounded fix.", planner_agent="codex")
    receipt["builder_requirements"]["selected_model"] = "provider/name"
    _resign(receipt)

    with pytest.raises(PlanReceiptError, match="model or catalog pin"):
        validate_plan_receipt(receipt)


def test_builder_selection_uses_each_fresh_capacity_and_capability_snapshot() -> None:
    receipt = build_plan_receipt(_task(), "Implement and verify.", planner_agent="claude")
    profiles = {
        "codex": _profile("code", "execute", "local-worktree"),
        "opencode": _profile("code", "execute", "local-worktree"),
        "claude": _profile("review", "inspect"),
    }

    first = select_live_builder(
        receipt,
        capacity_rows=[_row("codex", reachable=True), _row("opencode", reachable=True)],  # type: ignore[list-item]
        execution_profiles=profiles,
    )
    second = select_live_builder(
        receipt,
        capacity_rows=[_row("codex", reachable=False), _row("opencode", reachable=True)],  # type: ignore[list-item]
        execution_profiles=profiles,
    )

    assert first == "codex"
    assert second == "opencode"


def test_builder_task_strips_planner_authority_and_inherited_tier_pin() -> None:
    task = _task(claude_tier="fable")
    receipt = build_plan_receipt(task, "1. Patch one module.\n2. Run its tests.", planner_agent="claude")

    builder = builder_task_from_receipt(task, receipt, builder="codex")

    assert PLAN_ONLY_LABEL not in builder.labels
    assert BUILD_FROM_PLAN_LABEL in builder.labels
    assert not any(label.startswith("tier:") for label in builder.labels)
    assert builder.claude_tier is None
    assert builder.target_agent == "codex"
    assert builder.plan_receipt == receipt
    assert "1. Patch one module." in str(builder.context)
    assert task_contract_digest(builder) == receipt["task_contract_digest"]
    assert task.context == "Existing evidence."

    repeated = builder_task_from_receipt(builder, receipt, builder="opencode")
    assert repeated.context == builder.context
    assert repeated.labels.count(BUILD_FROM_PLAN_LABEL) == 1


def test_builder_task_rejects_a_stale_task_contract() -> None:
    task = _task()
    receipt = build_plan_receipt(task, "Implement the accepted shape.", planner_agent="claude")
    changed = task.model_copy(update={"title": "different task"})

    with pytest.raises(PlanReceiptError, match="stale"):
        builder_task_from_receipt(changed, receipt, builder="codex")


def test_plan_only_agent_output_becomes_receipt_only_when_worktree_is_clean(tmp_path: Path, monkeypatch) -> None:
    task = _task()
    monkeypatch.setattr(
        D,
        "_run_capture",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 0, "1. Inspect.\n2. Implement later.\n", ""),
    )
    monkeypatch.setattr(
        D,
        "_git",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["git"], 0, "", ""),
    )

    result = D._run_isolated_agent("claude", task, tmp_path, ["claude"], 3)

    assert isinstance(result, PlanHandoffResult)
    assert result.receipt["plan"].startswith("1. Inspect.")


def test_plan_only_agent_mutation_blocks_the_handoff(tmp_path: Path, monkeypatch) -> None:
    task = _task()
    monkeypatch.setattr(
        D,
        "_run_capture",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["claude"], 0, "A plan.", ""),
    )
    monkeypatch.setattr(
        D,
        "_git",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["git"], 0, " M changed.py\0", ""),
    )

    result = D._run_isolated_agent("claude", task, tmp_path, ["claude"], 3)

    assert D._is_blocked_result(result)
    assert "mutated" in D._blocked_reason(result)


def test_apply_plan_result_reopens_to_builder_and_claim_reruns_live_selection(monkeypatch) -> None:
    task = _task(claude_tier="opus")
    receipt = build_plan_receipt(task, "Implement the focused repair.", planner_agent="claude")
    selections = iter(["codex", "opencode"])
    monkeypatch.setattr(D, "select_live_builder", lambda _receipt: next(selections))
    track = BudgetTrack(date="2026-07-23")

    D._apply_result(
        task,
        "claude",
        PlanHandoffResult(receipt),
        datetime(2026, 7, 23, 12, tzinfo=UTC),
        track,
    )

    assert task.status == "open"
    assert task.target_agent == "codex"
    assert task.dispatch_log[-1].route_to == "codex"
    assert task.dispatch_log[-1].status == "open"
    assert task.plan_receipt == receipt
    assert track.per_agent["claude"] == task.budget_cost
    assert D._effective_target_agent(task) == "opencode"


def test_plan_only_prompt_forbids_mutation_and_pr_creation() -> None:
    prompt = D._build_prompt(_task())

    assert "PLAN-ONLY AUTHORITY" in prompt
    assert "Do not edit, create, delete" in prompt
    assert "do not commit, push, open a PR" in prompt
