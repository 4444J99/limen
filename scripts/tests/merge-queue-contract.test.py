#!/usr/bin/env python3
"""Focused contracts for Limen's native merge-queue workflow and ruleset body."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "pr-gate.yml"
AUTO_SCALE = ROOT / ".github" / "workflows" / "auto-scale.yml"
OPERATE = ROOT / ".github" / "workflows" / "operate.yml"
SETUP = ROOT / "scripts" / "setup-rulesets.py"
TABULARIUS_ORGAN = ROOT / "scripts" / "tabularius-organ.py"
sys.path.insert(0, str(ROOT / "cli" / "src"))
from limen import tabularius  # noqa: E402


def load_setup_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("setup_rulesets_contract", SETUP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_tabularius_organ_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tabularius_organ_contract", TABULARIUS_ORGAN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow_doc() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML 1.1 parses the bare workflow key `on` as boolean True.
    if True in doc and "on" not in doc:
        doc["on"] = doc.pop(True)
    return doc


def named_step(doc: dict, prefix: str) -> dict:
    return next(step for step in doc["jobs"]["pr-gate"]["steps"] if str(step.get("name", "")).startswith(prefix))


def test_workflow_event_contract() -> None:
    doc = workflow_doc()
    triggers = doc["on"]
    assert triggers["merge_group"] == {"types": ["checks_requested"]}
    assert "workflow_dispatch" in triggers

    pull_request = named_step(doc, "Verify implicated PR gates")
    assert "github.event_name == 'pull_request'" in pull_request["if"]
    assert pull_request["env"]["LIMEN_VERIFY_REQUIRE_BASE"] == "1"
    assert "--skip-ci-covered pr-gate.yml:pr-gate" in pull_request["run"]
    assert "--integration" not in pull_request["run"]

    merge_group = named_step(doc, "Verify merge-group integration gates")
    assert "github.event_name == 'merge_group'" in merge_group["if"]
    assert merge_group["env"]["MERGE_GROUP_BASE_SHA"] == "${{ github.event.merge_group.base_sha }}"
    assert "--changed --integration" in merge_group["run"]
    assert '--base "$MERGE_GROUP_BASE_SHA"' in merge_group["run"]
    assert "--skip-ci-covered" not in merge_group["run"]

    manual = named_step(doc, "Verify manual run")
    assert "github.event_name == 'workflow_dispatch'" in manual["if"]
    assert "--changed" in manual["run"]
    assert '--base "origin/${GITHUB_BASE_REF:-main}"' in manual["run"]
    assert "--skip-ci-covered pr-gate.yml:pr-gate" in manual["run"]


def test_targeted_ruleset_and_classic_protection_contract() -> None:
    module = load_setup_module()
    assert module.checks_for_repo("organvm/limen") == ["pr-gate"]

    protection = module.classic_protection_body(["pr-gate"])
    assert protection["required_status_checks"] == {
        "strict": False,
        "contexts": ["pr-gate"],
    }
    assert protection["enforce_admins"] is True
    assert protection["required_pull_request_reviews"] is None
    assert module.classic_protection_contract_holds(
        {
            "required_status_checks": {"strict": False, "contexts": ["pr-gate"]},
            "enforce_admins": {"enabled": True},
            "required_pull_request_reviews": None,
            "restrictions": None,
        },
        ["pr-gate"],
    )
    assert not module.classic_protection_contract_holds(
        {
            "required_status_checks": {"strict": False, "contexts": ["pr-gate"]},
            "enforce_admins": {"enabled": False},
            "required_pull_request_reviews": None,
            "restrictions": None,
        },
        ["pr-gate"],
    )

    ruleset = module.merge_queue_ruleset_body()
    assert ruleset["conditions"] == {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}
    assert ruleset["enforcement"] == "active"
    assert ruleset["bypass_actors"] == []
    assert [rule["type"] for rule in ruleset["rules"]] == ["pull_request", "merge_queue"]
    assert ruleset["rules"][0]["parameters"] == {
        "allowed_merge_methods": ["squash"],
        "dismiss_stale_reviews_on_push": False,
        "require_code_owner_review": False,
        "require_last_push_approval": False,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": False,
    }
    assert ruleset["rules"][1]["parameters"] == {
        "check_response_timeout_minutes": 60,
        "grouping_strategy": "HEADGREEN",
        "max_entries_to_build": 4,
        "max_entries_to_merge": 1,
        "merge_method": "SQUASH",
        "min_entries_to_merge": 1,
        "min_entries_to_merge_wait_minutes": 0,
    }
    assert module._ruleset_contract_holds(ruleset)
    bypassed = {**ruleset, "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole"}]}
    assert not module._ruleset_contract_holds(bypassed)


def test_automation_writers_use_board_pr_publication() -> None:
    docs = []
    for path in (AUTO_SCALE, OPERATE):
        source = path.read_text(encoding="utf-8")
        doc = yaml.safe_load(source)
        if True in doc and "on" not in doc:
            doc["on"] = doc.pop(True)
        docs.append(doc)
        assert "pull-requests: write" in source
        assert "actions: write" in source
        assert "LIMEN_ROOT: ${{ github.workspace }}" in source
        assert "LIMEN_TASKS: ${{ github.workspace }}/tasks.yaml" in source
        assert "python scripts/tabularius-organ.py --preflight" in source
        assert "scripts/tabularius-organ.py --require-published" in source
        assert "git push" not in source
        assert "HEAD:main" not in source
        assert "git pull --rebase" not in source
        assert "git add" not in source
        assert doc["concurrency"] == {
            "group": "tabularius-board-publication",
            "cancel-in-progress": False,
        }
    auto_steps = docs[0]["jobs"]["auto-scale"]["steps"]
    assert next(i for i, step in enumerate(auto_steps) if step.get("id") == "board-preflight") < next(
        i for i, step in enumerate(auto_steps) if step.get("name") == "Run Auto-Scaler"
    )
    assert "ruff check --fix" not in OPERATE.read_text(encoding="utf-8")


def test_required_publication_failure_precedence() -> None:
    module = load_tabularius_organ_module()
    check = module._publication_required_failure
    assert check(False, SimpleNamespace(published=False, reason="push-rejected:race")) is False
    assert check(True, None) is True
    assert check(True, SimpleNamespace(published=True, reason="")) is False
    assert check(True, SimpleNamespace(published=True, reason="publication-in-flight")) is False
    assert check(True, SimpleNamespace(published=False, reason="publication-in-flight")) is True
    assert check(True, SimpleNamespace(published=True, reason="pr-gate-dispatch-failed:denied")) is True
    assert check(True, SimpleNamespace(published=False, reason="push-rejected:non-fast-forward")) is True


def test_required_publication_main_paths_fail_closed() -> None:
    deferred = SimpleNamespace(pending=3, deferred=True)
    preserve = SimpleNamespace(published=False, reason="queue-lock-held")
    module = load_tabularius_organ_module()
    with (
        mock.patch.object(module, "drain_once", return_value=deferred),
        mock.patch.object(module, "preserve_board_projection", return_value=preserve),
        contextlib.redirect_stdout(io.StringIO()),
    ):
        assert module.main(["--require-published"]) == 2

    module = load_tabularius_organ_module()
    module.ENABLED = False
    with contextlib.redirect_stdout(io.StringIO()):
        assert module.main(["--require-published"]) == 2
        assert module.main(["--preflight"]) == 2

    module = load_tabularius_organ_module()
    in_flight = SimpleNamespace(
        published=True,
        deferred=True,
        reason="publication-in-flight",
        pr_number=77,
    )
    with (
        mock.patch.object(module, "board_publication_preflight", return_value=in_flight),
        contextlib.redirect_stdout(io.StringIO()),
    ):
        assert module.main(["--preflight"]) == 75


def test_github_workspace_is_the_runner_root_fallback() -> None:
    with mock.patch.dict(
        os.environ,
        {"LIMEN_ROOT": "", "GITHUB_WORKSPACE": "/tmp/limen-actions-workspace"},
        clear=False,
    ):
        module = load_tabularius_organ_module()
    assert module.ROOT == Path("/tmp/limen-actions-workspace")
    assert module.BOARD == Path("/tmp/limen-actions-workspace/tasks.yaml")


def test_actions_board_publisher_dispatches_pr_gate_on_exact_branch() -> None:
    success = SimpleNamespace(returncode=0, stdout="", stderr="")
    with (
        mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False),
        mock.patch.object(tabularius, "_gh", return_value=success) as gh_call,
    ):
        assert (
            tabularius._dispatch_pr_gate(
                ROOT,
                "organvm/limen",
                tabularius.BOARD_PUBLICATION_BRANCH,
            )
            == ""
        )
    gh_call.assert_called_once_with(
        ROOT,
        [
            "workflow",
            "run",
            "pr-gate.yml",
            "--repo",
            "organvm/limen",
            "--ref",
            tabularius.BOARD_PUBLICATION_BRANCH,
        ],
    )


def test_actions_permissions_are_explicit_and_verified() -> None:
    module = load_setup_module()
    body = module.actions_workflow_permissions_body()
    success = SimpleNamespace(returncode=0, stdout="", stderr="")
    with (
        mock.patch.object(module, "gh_input", return_value=success) as mutation,
        mock.patch.object(module, "gh_json_checked", return_value=(body, "")) as verify,
        contextlib.redirect_stdout(io.StringIO()),
    ):
        assert module.ensure_actions_pr_permissions("organvm/limen") is True
    mutation.assert_called_once_with(
        "PUT",
        "/repos/organvm/limen/actions/permissions/workflow",
        {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": True,
        },
    )
    verify.assert_called_once()


def test_ruleset_apply_is_idempotent_and_targeted() -> None:
    module = load_setup_module()
    success = SimpleNamespace(returncode=0, stdout='{"id": 731}', stderr="")
    observed = {**module.merge_queue_ruleset_body(), "id": 731}

    for existing, method, path in (
        (
            [{"id": 731, "name": module.MERGE_QUEUE_RULESET_NAME}],
            "PUT",
            "/repos/organvm/limen/rulesets/731",
        ),
        ([], "POST", "/repos/organvm/limen/rulesets"),
    ):
        responses = iter([(existing, ""), (observed, "")])
        with (
            mock.patch.object(module, "gh_json_checked", side_effect=lambda *_args: next(responses)),
            mock.patch.object(module, "gh_input", return_value=success) as api,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            assert module.ensure_merge_queue("organvm/limen") is True
        api.assert_called_once_with(method, path, module.merge_queue_ruleset_body())

    with mock.patch.object(module, "gh_input") as api:
        assert module.ensure_merge_queue("organvm/another-repo") is True
        api.assert_not_called()


def test_dry_run_never_calls_mutating_seams() -> None:
    module = load_setup_module()
    module.APPLY = False
    with (
        mock.patch.object(module, "target_repos", return_value=["organvm/limen"]),
        mock.patch.object(
            module,
            "gh_json",
            return_value={"defaultBranchRef": {"name": "main"}},
        ),
        mock.patch.object(module, "gh") as gh_call,
        mock.patch.object(module, "gh_input") as gh_input_call,
        mock.patch.object(module, "ensure_actions_pr_permissions") as actions_call,
        mock.patch.object(module, "ensure_merge_queue") as queue_call,
        mock.patch.object(module, "ensure_copilot_review") as copilot_call,
        contextlib.redirect_stdout(io.StringIO()),
    ):
        module.main()
    gh_call.assert_not_called()
    gh_input_call.assert_not_called()
    actions_call.assert_not_called()
    queue_call.assert_not_called()
    copilot_call.assert_not_called()


def test_apply_aggregates_ruleset_failure_and_skips_weaker_mutations() -> None:
    module = load_setup_module()
    module.APPLY = True
    order: list[str] = []

    def queue(_repo):
        order.append("ruleset")
        return False

    with (
        mock.patch.object(module, "target_repos", return_value=["organvm/limen"]),
        mock.patch.object(module, "gh_json", return_value={"defaultBranchRef": {"name": "main"}}),
        mock.patch.object(module, "gh") as weaker_repo_mutation,
        mock.patch.object(module, "gh_input") as weaker_classic_mutation,
        mock.patch.object(module, "ensure_actions_pr_permissions", return_value=True),
        mock.patch.object(module, "ensure_merge_queue", side_effect=queue),
        mock.patch.object(module, "ensure_copilot_review", return_value=True),
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        assert module.main() == 1
    assert order == ["ruleset"]
    weaker_repo_mutation.assert_not_called()
    weaker_classic_mutation.assert_not_called()


def test_apply_seam_has_one_protection_write_plus_one_readback() -> None:
    source = SETUP.read_text(encoding="utf-8")
    assert 'APPLY = "--apply" in sys.argv' in source
    assert source.count('f"/repos/{repo}/branches/{branch}/protection"') == 2
    assert source.count('gh_input("PUT", f"/repos/{repo}/branches/{branch}/protection"') == 1


def main() -> None:
    test_workflow_event_contract()
    test_targeted_ruleset_and_classic_protection_contract()
    test_automation_writers_use_board_pr_publication()
    test_required_publication_failure_precedence()
    test_required_publication_main_paths_fail_closed()
    test_github_workspace_is_the_runner_root_fallback()
    test_actions_board_publisher_dispatches_pr_gate_on_exact_branch()
    test_actions_permissions_are_explicit_and_verified()
    test_ruleset_apply_is_idempotent_and_targeted()
    test_dry_run_never_calls_mutating_seams()
    test_apply_aggregates_ruleset_failure_and_skips_weaker_mutations()
    test_apply_seam_has_one_protection_write_plus_one_readback()
    print("merge-queue-contract: all focused contracts pass")


if __name__ == "__main__":
    main()
