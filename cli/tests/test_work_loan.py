from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from limen.intake import is_durable_receipt_target, is_executable_predicate
from limen.work_loan import (
    WorkLoanV1,
    packet_is_non_capacity_projection,
    packet_work_loan_missing,
    task_source_lineage,
    task_work_loan_readiness,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads((ROOT / "spec/contracts/work-loan-v1-fixtures.json").read_text())


def task(**overrides):
    value = {
        "id": "WL-1",
        "repo": "organvm/limen",
        "budget_cost": 2,
        "labels": ["origin:human-prompt", "horizon:present"],
        "value_case": "Deliver one bounded, owner-receipted outcome",
        "predicate": "pytest -q cli/tests/test_work_loan.py",
        "receipt_target": "github:organvm/limen:pull-request:WL-1",
    }
    value.update(overrides)
    return value


def test_task_work_loan_derives_only_explicit_registry_fields() -> None:
    readiness = task_work_loan_readiness(task())

    assert readiness.ready
    assert readiness.reason_code is None
    assert readiness.loan == WorkLoanV1(
        source_origin="human_prompt",
        horizon="present",
        value_case="Deliver one bounded, owner-receipted outcome",
        budget_cost=2,
        owner_surface="organvm/limen",
    )


def test_missing_fields_are_stable_and_title_prose_never_underwrites() -> None:
    readiness = task_work_loan_readiness(
        task(
            title="Urgent human ask with huge value",
            repo=None,
            budget_cost=0,
            labels=[],
            value_case=None,
            predicate="should pass",
            receipt_target="receipt.txt",
        )
    )

    assert readiness.missing_fields == (
        "source_origin",
        "horizon",
        "value_case",
        "budget_cost",
        "owner_surface",
        "predicate",
        "receipt_target",
    )
    assert readiness.reason_code == (
        "task-not-underwritten:source_origin,horizon,value_case,budget_cost,owner_surface,predicate,receipt_target"
    )


def test_external_deadline_requires_due_at_but_ordinary_work_does_not() -> None:
    missing = task_work_loan_readiness(task(external_deadline=True))
    assert missing.reason_code == "task-not-underwritten:due_at"

    ready = task_work_loan_readiness(task(external_deadline=True, due_at="2026-08-01T12:00:00Z"))
    assert ready.ready
    assert ready.loan is not None and ready.loan.external_deadline is True

    with pytest.raises(ValueError, match="due_at is required"):
        WorkLoanV1(
            source_origin="obligation",
            horizon="present",
            value_case="Meet the external deadline",
            budget_cost=1,
            owner_surface="github:organvm/limen#1",
            external_deadline=True,
        )


@pytest.mark.parametrize(
    "case",
    FIXTURES["due_at_cases"],
    ids=lambda case: case["value"],
)
def test_due_at_fixtures_match_python_readiness(case: dict) -> None:
    readiness = task_work_loan_readiness(task(external_deadline=True, due_at=case["value"]))
    assert readiness.ready is case["valid"]
    assert (readiness.reason_code == "task-not-underwritten:due_at") is not case["valid"]


def test_validation_errors_name_the_actual_collateral_field() -> None:
    readiness = task_work_loan_readiness(task(owner_surface="\x00"))
    assert readiness.reason_code == "task-not-underwritten:owner_surface"


@pytest.mark.parametrize("case", FIXTURES["predicate_cases"], ids=lambda case: case["value"])
def test_predicate_fixtures_match_canonical_python_intake(case: dict) -> None:
    assert is_executable_predicate(case["value"]) is case["valid"]


@pytest.mark.parametrize(
    "case",
    FIXTURES["receipt_target_cases"],
    ids=lambda case: case["value"],
)
def test_receipt_fixtures_match_canonical_python_intake(case: dict) -> None:
    assert is_durable_receipt_target(case["value"]) is case["valid"]


def test_packet_work_loan_requires_canonical_origin_horizon_and_bound_cost() -> None:
    packet = {
        "predicate": "pytest -q cli/tests/test_work_loan.py",
        "receipt_target": "github:organvm/limen:pull-request:WL-PACKET",
        "spend": {"limit": 2},
        "work_loan": {
            "source_origin": "urgent",
            "horizon": "soon",
            "value_case": "Deliver one bounded packet",
            "budget_cost": 3,
            "owner_surface": "organvm/limen",
        },
    }

    assert packet_work_loan_missing(packet) == ("source_origin", "horizon", "budget_cost")


def test_only_exact_zero_cost_task_projection_is_non_capacity_compatibility_work() -> None:
    task_id = "LIMEN-PROJECTION-1"
    packet = {
        "intent": {"kind": "task.status", "task_id": task_id},
        "execution": {"adapter": "tabularius", "projection": "tasks.yaml"},
        "preferred_agent": "tabularius",
        "required_capabilities": ["board-write"],
        "resource_claims": [{"key": f"task/{task_id}", "mode": "exclusive"}],
        "predicate": "python3 scripts/validate-task-board.py --tasks tasks.yaml",
        "receipt_target": f"git:organvm/limen:tasks.yaml#{task_id}",
        "authority": {
            "actions": ["task.status"],
            "path_prefixes": ["tasks.yaml"],
            "external_effects": [],
            "may_delegate": False,
        },
        "effect": "write",
        "spend": {"unit": "runs", "limit": 0, "reserve": 0},
        "task_id": task_id,
    }

    assert packet_is_non_capacity_projection(packet)
    assert packet_work_loan_missing(packet) == ()

    packet["spend"]["limit"] = 1
    assert not packet_is_non_capacity_projection(packet)
    assert packet_work_loan_missing(packet) == (
        "source_origin",
        "horizon",
        "value_case",
        "budget_cost",
        "owner_surface",
    )


def test_source_lineage_is_never_inferred_from_title_or_repo() -> None:
    assert task_source_lineage(task(title="Feed cohort 7")) == "unknown"
    assert task_source_lineage(task(source_lineage="prompt-lineage-7")) == "prompt-lineage-7"
    assert task_source_lineage(task(labels=["lineage:feed-42"])) == "feed-42"


def test_sanctioned_producers_adopt_explicit_work_loan_collateral() -> None:
    task_producers = (
        "cli/src/limen/observatory/lever.py",
        "scripts/always-working.py",
        "scripts/append-tasks.py",
        "scripts/auto-scale.py",
        "scripts/batch-dispatch.py",
        "scripts/converge-organ.py",
        "scripts/corpus-converge.py",
        "scripts/current-session-fanout.py",
        "scripts/decorum-keeper.py",
        "scripts/discover-value.py",
        "scripts/dispatch-continuity-check.py",
        "scripts/generate-backlog.py",
        "scripts/generate-experience-backlog.py",
        "scripts/generate-organ-backlog.py",
        "scripts/generate-revenue-backlog.py",
        "scripts/generate-seo-backlog.py",
        "scripts/ingest-backlog.py",
        "scripts/insight-route.py",
        "scripts/check-main-green.py",
        "scripts/heal-dispatch.py",
        "scripts/mine-backlog.py",
        "scripts/overnight-watch.py",
        "scripts/quicken.py",
        "scripts/routine-freshness-audit.py",
        "scripts/self-heal.py",
    )
    for relative in task_producers:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "origin" in source, relative
        assert "horizon" in source, relative
        assert "value_case" in source, relative

    direct_task_producers = set()
    for source_root in (ROOT / "scripts", ROOT / "mcp/src/limen_mcp"):
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(
                isinstance(node, ast.Call)
                and (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "Task"
                    or isinstance(node.func, ast.Attribute)
                    and node.func.attr == "Task"
                )
                for node in ast.walk(tree)
            ):
                direct_task_producers.add(str(path.relative_to(ROOT)))
    assert direct_task_producers <= set(task_producers) | {"mcp/src/limen_mcp/server.py"}

    packet_producers = (
        "cli/src/limen/conduct/campaign.py",
        "scripts/current-session-fanout.py",
    )
    for relative in packet_producers:
        assert "WorkLoanV1(" in (ROOT / relative).read_text(encoding="utf-8"), relative
