"""Tests for the Jules supply organ (limen.jules_supply + scripts/jules-supply.py)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jules-supply.py"
REGISTRY_PATH = ROOT / "docs" / "jules-supply-templates.yaml"
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.io import save_limen_file
from limen.jules_supply import (
    dispatchable_supply,
    expand_supply,
    load_supply_registry,
    next_indices,
)
from limen.models import LimenFile, Task
from limen.work_loan import task_work_loan_readiness


def load_script():
    spec = importlib.util.spec_from_file_location("jules_supply_script_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _loan_task(tid: str, **over) -> Task:
    fields = {
        "id": tid,
        "title": f"packet {tid}",
        "repo": "organvm/victoroff-os",
        "target_agent": "jules",
        "status": "open",
        "created": date(2026, 7, 23),
        "predicate": "pnpm test",
        "receipt_target": f"github:organvm/victoroff-os:pull-request:{tid}",
        "origin": "human_prompt",
        "horizon": "present",
        "value_case": f"Deliver {tid}",
        "owner_surface": "client-one-governance",
        "budget_cost": 1,
        **over,
    }
    return Task(**fields)


def test_registry_loads_and_templates_are_loan_complete() -> None:
    registry = load_supply_registry(REGISTRY_PATH)
    assert registry.per_run_cap > 0
    patches = expand_supply(registry, set(), 3, created="2026-07-23")
    assert len(patches) == 3
    for patch in patches:
        readiness = task_work_loan_readiness(Task(**patch))
        assert not readiness.missing_fields, (patch["id"], readiness.missing_fields)
        assert "Forbidden paths" in patch["context"]
        assert patch["receipt_target"].endswith(patch["id"])


def test_expand_supply_series_indices_skip_existing_and_round_robin() -> None:
    registry = load_supply_registry(REGISTRY_PATH)
    existing = {"VIC-CONTRACT-DEEPEN-002", "VIC-CONTRACT-DEEPEN-007", "unrelated-task"}
    patches = expand_supply(registry, existing, 8, created="2026-07-23")
    ids = [patch["id"] for patch in patches]
    assert "VIC-CONTRACT-DEEPEN-008" in ids  # continues past the highest used index
    assert len(ids) == len(set(ids))  # no duplicates within one run
    prefixes = {task_id.rsplit("-", 1)[0] for task_id in ids}
    assert len(prefixes) > 1  # round-robin across series, not one series drained first


def test_expand_supply_respects_cap_and_zero_deficit() -> None:
    registry = load_supply_registry(REGISTRY_PATH)
    assert expand_supply(registry, set(), 0, created="2026-07-23") == []
    flood = expand_supply(registry, set(), 10_000, created="2026-07-23")
    assert len(flood) == registry.per_run_cap


def test_next_indices_parses_only_three_digit_series() -> None:
    assert next_indices({"A-001", "A-003", "B-010", "C-7", "D"}) == {"A": 3, "B": 10}


def test_dispatchable_supply_counts_only_loan_ready_open_jules() -> None:
    board = LimenFile(
        tasks=[
            _loan_task("S-1"),
            _loan_task("S-2", status="done"),
            _loan_task("S-3", target_agent="codex"),
            Task(
                id="S-4",
                title="legacy, no loan fields",
                repo="organvm/victoroff-os",
                target_agent="jules",
                status="open",
                created=date(2026, 7, 23),
            ),
        ]
    )
    assert dispatchable_supply(board) == 1


def test_script_dry_run_reports_deficit_without_minting(monkeypatch, tmp_path: Path, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, LimenFile(tasks=[_loan_task("S-1")]))
    monkeypatch.delenv("LIMEN_JULES_SUPPLY_APPLY", raising=False)
    monkeypatch.setenv("LIMEN_JULES_SUPPLY_FLOOR", "5")
    module = load_script()
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(module, "REGISTRY", REGISTRY_PATH)

    assert module.main() == 1
    out = capsys.readouterr().out
    assert "supply=1 floor=5 pending=0 deficit=4 minted=0" in out
    assert "DRY-RUN would mint 4" in out
    assert not (tmp_path / "logs").exists()  # nothing queued


def test_script_armed_mints_tickets_and_counts_pending(monkeypatch, tmp_path: Path, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, LimenFile(tasks=[_loan_task("S-1")]))
    monkeypatch.setenv("LIMEN_JULES_SUPPLY_APPLY", "1")
    monkeypatch.setenv("LIMEN_JULES_SUPPLY_FLOOR", "3")
    module = load_script()
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(module, "REGISTRY", REGISTRY_PATH)

    assert module.main() == 0
    assert "deficit=2 minted=2" in capsys.readouterr().out
    inbox = tasks_path.parent / "logs" / "tickets" / "inbox"
    assert len(list(inbox.glob("*.json"))) == 2

    # Second run: queued tickets count as pending — no double-mint.
    module_again = load_script()
    monkeypatch.setattr(module_again, "TASKS", tasks_path)
    monkeypatch.setattr(module_again, "REGISTRY", REGISTRY_PATH)
    assert module_again.main() == 0
    assert "pending=2 deficit=0 minted=0" in capsys.readouterr().out
    assert len(list(inbox.glob("*.json"))) == 2


def test_registry_rejects_wrong_schema(tmp_path: Path) -> None:
    bad = tmp_path / "registry.yaml"
    bad.write_text("schema_version: nope\n")
    with pytest.raises(ValueError, match="unsupported jules supply registry schema"):
        load_supply_registry(bad)
