from __future__ import annotations

import ast
import os
import subprocess
from datetime import date
from pathlib import Path

import pytest
from limen.intake import (
    IntakeContractError,
    boundedness_finding,
    contract_fields,
    github_issue_contract,
    github_main_green_contract,
    github_pr_contract,
    is_durable_receipt_target,
    is_executable_predicate,
    normalize_selected_legacy_task,
    validate_intake_contract,
)
from limen.models import LimenFile, Task

ROOT = Path(__file__).resolve().parents[2]


def _task(**over):
    row = {
        "id": "T-1",
        "title": "One bounded task",
        "repo": "organvm/limen",
        "target_agent": "codex",
        "created": date(2026, 7, 12),
        **contract_fields(github_pr_contract("organvm/limen", "T-1")),
    }
    row.update(over)
    return row


def test_legacy_board_remains_loadable_without_typed_fields() -> None:
    board = LimenFile.model_validate(
        {
            "tasks": [
                {
                    "id": "LEGACY-1",
                    "title": "Historical task",
                    "repo": "organvm/limen",
                    "target_agent": "codex",
                    "status": "open",
                    "created": "2026-07-01",
                }
            ]
        }
    )
    assert board.tasks[0].predicate is None
    assert board.tasks[0].receipt_target is None
    assert board.tasks[0].execution_requirements is None


def test_cli_and_mcp_task_models_expose_optional_typed_fields() -> None:
    cli_fields = Task.model_fields
    for field in ("predicate", "receipt_target"):
        assert field in cli_fields
        assert cli_fields[field].is_required() is False
    assert "execution_requirements" in cli_fields
    assert cli_fields["execution_requirements"].is_required() is False

    # The MCP distribution is intentionally a separate install and its runtime
    # dependency is not present in the CLI test environment.  Parse its model
    # declaration directly so schema parity is still a mandatory offline gate.
    tree = ast.parse((ROOT / "mcp/src/limen_mcp/server.py").read_text(encoding="utf-8"))
    task_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Task")
    mcp_fields = {
        node.target.id: node
        for node in task_class.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    for field in ("predicate", "receipt_target"):
        assert field in mcp_fields
        assert isinstance(mcp_fields[field].value, ast.Constant)
        assert mcp_fields[field].value.value is None
    assert "execution_requirements" in mcp_fields
    assert isinstance(mcp_fields["execution_requirements"].value, ast.Constant)
    assert mcp_fields["execution_requirements"].value.value is None

    add_task = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "add_task")
    required_count = len(add_task.args.args) - len(add_task.args.defaults)
    required_arguments = {argument.arg for argument in add_task.args.args[:required_count]}
    assert {"predicate", "receipt_target"} <= required_arguments


def test_portable_runtime_mirrors_match_canonical_byte_for_byte() -> None:
    canonical = (ROOT / "cli/src/limen/intake.py").read_bytes()
    for mirror in (ROOT / "web/api/limen_intake.py", ROOT / "mcp/src/limen_mcp/intake.py"):
        assert mirror.read_bytes() == canonical, mirror

    dockerfile = (ROOT / "web/api/Dockerfile").read_text(encoding="utf-8")
    web_main = (ROOT / "web/api/main.py").read_text(encoding="utf-8")
    mcp_server = (ROOT / "mcp/src/limen_mcp/server.py").read_text(encoding="utf-8")
    assert "COPY limen_intake.py ." in dockerfile
    assert "from limen_intake import" in web_main
    assert "from limen_mcp.intake import" in mcp_server


def test_new_and_open_tasks_require_executable_predicate_and_durable_receipt() -> None:
    with pytest.raises(IntakeContractError, match="predicate"):
        validate_intake_contract(_task(predicate=None), is_new=True)
    with pytest.raises(IntakeContractError, match="receipt_target"):
        validate_intake_contract(_task(receipt_target="/tmp/result.json"), is_new=True)
    assert validate_intake_contract(_task(), is_new=True) is not None


def test_contract_accepts_environment_prefixed_commands_and_safe_repository_paths() -> None:
    assert is_executable_predicate("PYTHONPATH=cli/src python3 -m pytest -q")
    assert is_executable_predicate("env LIMEN_ROOT=. python3 scripts/ask-gate.py --audit")
    assert is_durable_receipt_target("git:4444J99/4444J99:README.md")
    assert not is_durable_receipt_target("git:organvm/limen:../private.json")


def test_generated_github_predicates_fail_when_receipt_is_absent(tmp_path: Path) -> None:
    fake_gh = tmp_path / "gh"
    fake_gh.write_text("#!/bin/sh\nprintf '%s\\n' \"$FAKE_GH_OUTPUT\"\n", encoding="utf-8")
    fake_gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ.get('PATH', '')}"}

    pr_contract = github_pr_contract("organvm/limen", "NO-SUCH-RECEIPT")
    absent = subprocess.run(pr_contract.predicate, shell=True, env={**env, "FAKE_GH_OUTPUT": "0"}, check=False)
    present = subprocess.run(pr_contract.predicate, shell=True, env={**env, "FAKE_GH_OUTPUT": "1"}, check=False)
    assert absent.returncode != 0
    assert present.returncode == 0

    issue_contract = github_issue_contract("organvm/limen", 957)
    open_issue = subprocess.run(
        issue_contract.predicate,
        shell=True,
        env={**env, "FAKE_GH_OUTPUT": "OPEN"},
        check=False,
    )
    closed_issue = subprocess.run(
        issue_contract.predicate,
        shell=True,
        env={**env, "FAKE_GH_OUTPUT": "CLOSED"},
        check=False,
    )
    assert open_issue.returncode != 0
    assert closed_issue.returncode == 0

    main_contract = github_main_green_contract("organvm/limen", "a" * 40)
    stale_head = subprocess.run(
        main_contract.predicate,
        shell=True,
        env={**env, "FAKE_GH_OUTPUT": "0"},
        check=False,
    )
    exact_green_head = subprocess.run(
        main_contract.predicate,
        shell=True,
        env={**env, "FAKE_GH_OUTPUT": "1"},
        check=False,
    )
    assert stale_head.returncode != 0
    assert exact_green_head.returncode == 0


def test_terminal_legacy_task_may_omit_contract_but_not_carry_half_contract() -> None:
    assert validate_intake_contract(_task(status="done", predicate=None, receipt_target=None)) is None
    with pytest.raises(IntakeContractError, match="receipt_target"):
        validate_intake_contract(_task(status="done", receipt_target=None))


def test_active_status_transition_cannot_bypass_contract() -> None:
    for status in ("open", "dispatched", "in_progress"):
        with pytest.raises(IntakeContractError, match="predicate"):
            validate_intake_contract(_task(status=status, predicate=None, receipt_target=None))


def test_boundedness_ignores_ordinary_and_but_rejects_numbered_bundle() -> None:
    ordinary = _task(
        context=(
            "Rebase the branch AND keep its unique change AND restore current base content "
            "AND verify the PR AND preserve its owner receipt."
        )
    )
    assert boundedness_finding(ordinary) is None
    bundled = _task(context="(1) build one (2) build two (3) build three (4) build four")
    assert "4 numbered objectives" in str(boundedness_finding(bundled))


def test_selected_legacy_task_normalizes_from_exact_issue_owner() -> None:
    task = Task.model_validate(
        {
            "id": "GH-organvm-limen-957",
            "title": "Close the owner issue",
            "repo": "organvm/limen",
            "target_agent": "codex",
            "urls": ["https://github.com/organvm/limen/issues/957"],
            "created": "2026-07-12",
        }
    )
    contract = normalize_selected_legacy_task(task)
    assert contract == github_issue_contract("organvm/limen", 957)
    assert task.predicate == contract.predicate
    assert task.receipt_target == contract.receipt_target


def test_selected_legacy_task_fails_closed_without_owner_repo() -> None:
    task = Task.model_validate({"id": "NO-OWNER", "title": "Unowned", "target_agent": "codex", "created": "2026-07-12"})
    with pytest.raises(IntakeContractError, match="owner/repo"):
        normalize_selected_legacy_task(task)


def test_every_tabularius_task_producer_declares_typed_fields() -> None:
    producers = {
        Path("scripts/always-working.py"),
        Path("scripts/append-tasks.py"),
        Path("scripts/auto-scale.py"),
        Path("scripts/batch-dispatch.py"),
        Path("scripts/converge-organ.py"),
        Path("scripts/corpus-converge.py"),
        Path("scripts/discover-value.py"),
        Path("scripts/generate-backlog.py"),
        Path("scripts/generate-organ-backlog.py"),
        Path("scripts/generate-revenue-backlog.py"),
        Path("scripts/ingest-backlog.py"),
        Path("scripts/insight-route.py"),
        Path("scripts/mine-backlog.py"),
        Path("cli/src/limen/observatory/lever.py"),
    }
    for relative in sorted(producers):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "submit_task_upsert" in text
        assert "predicate" in text or "contract_fields" in text, relative
        assert "receipt_target" in text or "contract_fields" in text, relative

    # Current-session fanout no longer creates lifecycle tasks. It reserves a
    # bounded conduct DAG before any native child can consume capacity.
    fanout = (ROOT / "scripts/current-session-fanout.py").read_text(encoding="utf-8")
    assert "WorkPacketV1" in fanout
    assert "client.submit" in fanout
    assert "client.split" in fanout
    assert "predicate=" in fanout
    assert "receipt_target=" in fanout

    direct_or_assignment_producers = {
        Path("scripts/check-main-green.py"),
        Path("scripts/dispatch-continuity-check.py"),
        Path("scripts/probe-runtime-adapter.py"),
        Path("scripts/quicken.py"),
        Path("scripts/routine-freshness-audit.py"),
        Path("scripts/self-heal.py"),
    }
    for relative in sorted(direct_or_assignment_producers):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "predicate" in text or "contract_fields" in text, relative
        assert "receipt_target" in text or "contract_fields" in text, relative
