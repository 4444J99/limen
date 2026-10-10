"""Tests for the Jules supply organ (limen.jules_supply + scripts/jules-supply.py).

THE PARTNER-LANE EXCLUSION IS WHY THIS SUITE USES A FIXTURE REGISTRY.

Every expansion test here used to run against the LIVE registry
(``docs/jules-supply-templates.yaml``) and assert that it minted packets. All 7 of that
registry's declared templates target one unfunded partner lane, so those assertions were pinning
the largest single producer of the board's client-attributed rows: each beat that ran short of
Jules supply minted client-engagement tasks onto a board whose projection publishes to a PUBLIC
head.

Expansion mechanics (round-robin, series indices, per-run cap) have nothing to do with whose work
is in the registry, so they are tested against a fixture registry on a non-partner repo. Exactly
one test still reads the live file, and it asserts the exclusion.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jules-supply.py"
REGISTRY_PATH = ROOT / "docs" / "jules-supply-templates.yaml"
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.io import save_limen_file  # noqa: E402
from limen.jules_supply import (  # noqa: E402
    dispatchable_supply,
    expand_supply,
    load_supply_registry,
    next_indices,
    partner_lane_repos,
)
from limen.models import LimenFile, Task  # noqa: E402
from limen.work_loan import task_work_loan_readiness  # noqa: E402

# The operator's own repo — deliberately not a partner lane, so these tests exercise expansion
# rather than the boundary. `organvm/limen` is the system itself.
OWN_REPO = "organvm/limen"

_FIXTURE_REGISTRY = textwrap.dedent(
    f"""\
    schema_version: limen.jules_supply.v1
    floor_env: LIMEN_JULES_SUPPLY_FLOOR
    per_run_cap: 25
    repos:
      - repo: {OWN_REPO}
        owner_surface: limen-governance
        workstream: governance
        target_agent: jules
        forbidden_paths: "tasks.yaml, AGENTS.md"
        authority: "bounded packet only"
        templates:
          - id_prefix: OWN-ALPHA-DEEPEN
            title: "Alpha deepening, round {{n}}"
            allowed: "cli/src/**"
            behavior: "Add one adversarial round of coverage, round {{n}}."
            predicate: "python -m pytest cli/tests -q"
            value_case: "Each round hardens a class of input."
            budget_cost: 1
          - id_prefix: OWN-BETA-DEEPEN
            title: "Beta deepening, round {{n}}"
            allowed: "scripts/**"
            behavior: "Add one adversarial round of coverage, round {{n}}."
            predicate: "python -m pytest cli/tests -q"
            value_case: "Each round hardens a class of input."
            budget_cost: 1
    """
)


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    path = tmp_path / "supply.yaml"
    path.write_text(_FIXTURE_REGISTRY, encoding="utf-8")
    return path


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
        "repo": OWN_REPO,
        "target_agent": "jules",
        "status": "open",
        "created": date(2026, 7, 23),
        "predicate": "pnpm test",
        "receipt_target": f"github:{OWN_REPO}:pull-request:{tid}",
        "origin": "human_prompt",
        "horizon": "present",
        "value_case": f"Deliver {tid}",
        "owner_surface": "limen-governance",
        "budget_cost": 1,
        **over,
    }
    return Task(**fields)


# --- the exclusion ----------------------------------------------------------------------------


def test_the_live_registry_mints_nothing_because_it_is_all_one_partner_lane() -> None:
    """The leak this suite used to assert. Every declared template targets an unfunded partner
    lane, so the generator must produce zero packets from the live file rather than minting client
    engagements onto a board that publishes to a public head."""
    registry = load_supply_registry(REGISTRY_PATH)
    assert registry.repos, "the registry still declares repos; only the minting is excluded"
    assert partner_lane_repos(registry) != (), "expected the live registry's repos to be excluded"
    assert expand_supply(registry, set(), 25, created="2026-07-23") == []


def test_a_registry_mixing_lanes_mints_only_the_non_partner_half(tmp_path: Path) -> None:
    """The exclusion is per repo entry, not all-or-nothing for the file."""
    mixed = tmp_path / "mixed.yaml"
    live = REGISTRY_PATH.read_text(encoding="utf-8")
    partner_block = live[live.index("  - repo:") :]
    mixed.write_text(_FIXTURE_REGISTRY + partner_block, encoding="utf-8")

    registry = load_supply_registry(mixed)
    patches = expand_supply(registry, set(), 6, created="2026-07-23")

    assert patches, "the non-partner half must still mint"
    assert {patch["repo"] for patch in patches} == {OWN_REPO}


def test_partner_lane_repos_names_what_was_skipped() -> None:
    """No silent caps: the caller has to be able to report the exclusion."""
    registry = load_supply_registry(REGISTRY_PATH)
    assert len(partner_lane_repos(registry)) == len(registry.repos)


# --- expansion mechanics, on a fixture registry -----------------------------------------------


def test_registry_loads_and_templates_are_loan_complete(registry_path: Path) -> None:
    registry = load_supply_registry(registry_path)
    assert registry.per_run_cap > 0
    patches = expand_supply(registry, set(), 3, created="2026-07-23")
    assert len(patches) == 3
    for patch in patches:
        readiness = task_work_loan_readiness(Task(**patch))
        assert not readiness.missing_fields, (patch["id"], readiness.missing_fields)
        assert "Forbidden paths" in patch["context"]
        assert patch["receipt_target"].endswith(patch["id"])


def test_expand_supply_series_indices_skip_existing_and_round_robin(registry_path: Path) -> None:
    registry = load_supply_registry(registry_path)
    existing = {"OWN-ALPHA-DEEPEN-002", "OWN-ALPHA-DEEPEN-007", "unrelated-task"}
    patches = expand_supply(registry, existing, 8, created="2026-07-23")
    ids = [patch["id"] for patch in patches]
    assert "OWN-ALPHA-DEEPEN-008" in ids  # continues past the highest used index
    assert len(ids) == len(set(ids))  # no duplicates within one run
    prefixes = {task_id.rsplit("-", 1)[0] for task_id in ids}
    assert len(prefixes) > 1  # round-robin across series, not one series drained first


def test_expand_supply_respects_cap_and_zero_deficit(registry_path: Path) -> None:
    registry = load_supply_registry(registry_path)
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
                repo=OWN_REPO,
                target_agent="jules",
                status="open",
                created=date(2026, 7, 23),
            ),
        ]
    )
    assert dispatchable_supply(board) == 1


# --- the script wrapper -----------------------------------------------------------------------


def test_script_dry_run_reports_deficit_without_minting(monkeypatch, tmp_path: Path, capsys, registry_path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, LimenFile(tasks=[_loan_task("S-1")]))
    monkeypatch.delenv("LIMEN_JULES_SUPPLY_APPLY", raising=False)
    monkeypatch.setenv("LIMEN_JULES_SUPPLY_FLOOR", "5")
    module = load_script()
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(module, "REGISTRY", registry_path)

    assert module.main() == 1
    out = capsys.readouterr().out
    assert "supply=1 floor=5 pending=0 deficit=4 minted=0" in out
    assert "DRY-RUN would mint 4" in out
    assert not (tmp_path / "logs").exists()  # nothing queued


def test_script_armed_mints_tickets_and_counts_pending(monkeypatch, tmp_path: Path, capsys, registry_path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, LimenFile(tasks=[_loan_task("S-1")]))
    monkeypatch.setenv("LIMEN_JULES_SUPPLY_APPLY", "1")
    monkeypatch.setenv("LIMEN_JULES_SUPPLY_FLOOR", "3")
    module = load_script()
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(module, "REGISTRY", registry_path)

    assert module.main() == 0
    assert "deficit=2 minted=2" in capsys.readouterr().out
    inbox = tasks_path.parent / "logs" / "tickets" / "inbox"
    assert len(list(inbox.glob("*.json"))) == 2

    # Second run: queued tickets count as pending — no double-mint.
    module_again = load_script()
    monkeypatch.setattr(module_again, "TASKS", tasks_path)
    monkeypatch.setattr(module_again, "REGISTRY", registry_path)
    assert module_again.main() == 0
    assert "pending=2 deficit=0 minted=0" in capsys.readouterr().out
    assert len(list(inbox.glob("*.json"))) == 2


def test_script_reports_the_exclusion_instead_of_minting_client_work(monkeypatch, tmp_path: Path, capsys) -> None:
    """Against the LIVE registry the rung must report an unmet deficit and name the cause.

    Exit 1 is correct and not noise: the Jules supply pipeline genuinely has no legitimate source
    declared, and a rung that went green while minting nothing would hide that.
    """
    tasks_path = tmp_path / "tasks.yaml"
    save_limen_file(tasks_path, LimenFile(tasks=[_loan_task("S-1")]))
    monkeypatch.setenv("LIMEN_JULES_SUPPLY_APPLY", "1")
    monkeypatch.setenv("LIMEN_JULES_SUPPLY_FLOOR", "3")
    module = load_script()
    monkeypatch.setattr(module, "TASKS", tasks_path)
    monkeypatch.setattr(module, "REGISTRY", REGISTRY_PATH)

    assert module.main() == 1
    out = capsys.readouterr().out
    assert "EXCLUDED 1 partner-lane repo(s)" in out
    assert "minted=0" in out
    inbox = tasks_path.parent / "logs" / "tickets" / "inbox"
    assert not list(inbox.glob("*.json")), "no client packet may be queued"
    # The report must not republish the lane's name — logs/ auto-pushes to a public origin.
    assert "victoroff" not in out.lower()


def test_registry_rejects_wrong_schema(tmp_path: Path) -> None:
    bad = tmp_path / "registry.yaml"
    bad.write_text("schema_version: nope\n")
    with pytest.raises(ValueError, match="unsupported jules supply registry schema"):
        load_supply_registry(bad)
