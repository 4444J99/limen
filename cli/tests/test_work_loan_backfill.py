from __future__ import annotations

from pathlib import Path

import datetime as dt

from limen.estate import EstateCache, EstateRepo
from limen.work_loan import task_work_loan_readiness
from limen.work_loan_backfill import (
    RepoPredicates,
    derive_horizon,
    derive_loan_patch,
    derive_source_origin,
    load_repo_predicates,
)

REGISTRY = RepoPredicates(
    default_template=(
        'test "$(gh pr list --repo {repo} --state merged --search {task_id} --json number --jq length)" != 0'
    ),
    repos={"organvm/limen": {}, "organvm/portfolio": {"owner_surface": "portfolio-surface"}},
)


def _task(**overrides) -> dict:
    base = {
        "id": "GITVS-042",
        "title": "Cap the PR debt",
        "repo": "organvm/limen",
        "status": "open",
        "labels": [],
        "urls": [],
    }
    base.update(overrides)
    return base


def test_minted_patch_makes_the_task_loan_ready():
    patch, reason = derive_loan_patch(_task(), REGISTRY)
    assert reason == "minted"
    enriched = {**_task(), **patch}
    readiness = task_work_loan_readiness(enriched)
    assert readiness.ready, readiness.missing_fields


def test_patch_carries_only_missing_fields():
    task = _task(source_origin="human_prompt", horizon="future", budget_cost=3)
    patch, reason = derive_loan_patch(task, REGISTRY)
    assert reason == "minted"
    assert "source_origin" not in patch
    assert "horizon" not in patch
    assert "budget_cost" not in patch
    assert "predicate" in patch and "value_case" in patch


def test_repo_outside_registry_is_refused():
    patch, reason = derive_loan_patch(_task(repo="organvm/unknown-repo"), REGISTRY)
    assert patch is None
    assert reason == "unmintable:repo-not-in-predicate-registry"


def test_no_repo_is_refused():
    patch, reason = derive_loan_patch(_task(repo=""), REGISTRY)
    assert patch is None and reason == "unmintable:no-repo"


def test_non_open_and_already_ready_are_skipped():
    assert derive_loan_patch(_task(status="done"), REGISTRY)[1] == "excluded:not-open"
    ready = _task(
        source_origin="system_debt",
        horizon="present",
        budget_cost=1,
        value_case="A real case already written by a human.",
        owner_surface="organvm/limen",
        predicate="python3 scripts/check.py",
        receipt_target="github:organvm/limen:pull-request:GITVS-042",
    )
    assert derive_loan_patch(ready, REGISTRY)[1] == "already-ready"


def test_pr_url_wins_over_registry_template():
    task = _task(urls=["https://github.com/organvm/limen/pull/1234"])
    patch, reason = derive_loan_patch(task, REGISTRY)
    assert reason == "minted"
    assert "gh pr view 1234 --repo organvm/limen" in patch["predicate"]


def test_owner_surface_falls_back_to_repo_so_patch_omits_it():
    # task_work_loan_readiness derives owner_surface from `repo` when unset, so a task with a
    # repo never reports it missing — the patch must not restate a field readiness already owns.
    patch, reason = derive_loan_patch(_task(repo="organvm/portfolio"), REGISTRY)
    assert reason == "minted"
    assert "owner_surface" not in patch


def test_empty_template_and_no_pr_refuses_predicate():
    registry = RepoPredicates(default_template="", repos={"organvm/limen": {}})
    patch, reason = derive_loan_patch(_task(), registry)
    assert patch is None and reason == "unmintable:no-repo-predicate"


def test_origin_and_horizon_derivations():
    assert derive_source_origin(_task(id="HEAL-9")) == "system_debt"
    assert derive_source_origin(_task(labels=["generated"])) == "agent_recommendation"
    assert derive_source_origin(_task(labels=["origin:obligation"])) == "obligation"
    assert derive_horizon(_task(labels=["horizon:future"])) == "future"
    assert derive_horizon(_task()) == "present"


def test_target_agent_is_never_touched():
    patch, reason = derive_loan_patch(_task(target_agent="codex"), REGISTRY)
    assert reason == "minted"
    assert "target_agent" not in patch


def test_load_repo_predicates_roundtrip(tmp_path: Path):
    registry_path = tmp_path / "repo-predicates.yaml"
    registry_path.write_text(
        "schema: limen.repo_predicates.v1\n"
        "default_predicate_template: 'python3 scripts/probe.py {repo} {task_id}'\n"
        "repos:\n"
        "  organvm/limen: {}\n"
        "  organvm/portfolio:\n"
        "    owner_surface: portfolio-surface\n"
    )
    registry = load_repo_predicates(registry_path)
    assert "organvm/limen" in registry.repos
    assert registry.repos["organvm/portfolio"]["owner_surface"] == "portfolio-surface"
    patch, reason = derive_loan_patch(_task(), registry)
    assert reason == "minted"
    assert patch["predicate"] == "python3 scripts/probe.py organvm/limen GITVS-042"


def test_live_registry_parses_and_underwrites():
    root = Path(__file__).resolve().parents[2]
    registry = load_repo_predicates(root / "docs" / "repo-predicates.yaml")
    assert "organvm/limen" in registry.repos
    patch, reason = derive_loan_patch(_task(), registry)
    assert reason == "minted"
    enriched = {**_task(), **patch}
    assert task_work_loan_readiness(enriched).ready


ESTATE = EstateCache(
    fetched_at=dt.datetime(2026, 8, 6, 10, 0, tzinfo=dt.timezone.utc),
    repos={
        "organvm/limen": EstateRepo(archived=False, fork=False),
        "organvm/some-live-repo": EstateRepo(archived=False, fork=False),
        "organvm/mothballed": EstateRepo(archived=True, fork=False),
        "meta-organvm/moved-repo": EstateRepo(archived=False, fork=False),
    },
    aliases={"organvm/moved-repo": "meta-organvm/moved-repo"},
)


def test_estate_admits_unlisted_live_repo_under_default_template():
    patch, reason = derive_loan_patch(_task(repo="organvm/some-live-repo"), REGISTRY, ESTATE)
    assert reason == "minted"
    assert "organvm/some-live-repo" in patch["predicate"]
    assert "across the estate" in patch["value_case"]  # honest: estate-derived, not value-tier
    enriched = {**_task(repo="organvm/some-live-repo"), **patch}
    assert task_work_loan_readiness(enriched).ready


def test_registry_entry_still_claims_value_tier_with_estate_present():
    patch, reason = derive_loan_patch(_task(), REGISTRY, ESTATE)
    assert reason == "minted"
    assert "on the value tier" in patch["value_case"]


def test_archived_estate_repo_is_refused():
    patch, reason = derive_loan_patch(_task(repo="organvm/mothballed"), REGISTRY, ESTATE)
    assert patch is None and reason == "unmintable:repo-archived"


def test_repo_outside_estate_and_registry_is_refused():
    patch, reason = derive_loan_patch(_task(repo="stranger/elsewhere"), REGISTRY, ESTATE)
    assert patch is None and reason == "unmintable:repo-not-in-estate"


def test_no_estate_evidence_preserves_registry_only_behavior():
    patch, reason = derive_loan_patch(_task(repo="organvm/some-live-repo"), REGISTRY, None)
    assert patch is None and reason == "unmintable:repo-not-in-predicate-registry"


def test_registry_exclude_vetoes_even_estate_members():
    registry = RepoPredicates(default_template=REGISTRY.default_template, repos={"organvm/limen": {"exclude": True}})
    patch, reason = derive_loan_patch(_task(), registry, ESTATE)
    assert patch is None and reason == "excluded:repo-excluded"


def test_alias_resolves_transferred_repo_and_mints_against_canonical():
    patch, reason = derive_loan_patch(_task(repo="organvm/moved-repo"), REGISTRY, ESTATE)
    assert reason == "minted"
    # the loan points at where the repo LIVES, not at the redirect stub the board recorded
    assert patch["receipt_target"] == "github:meta-organvm/moved-repo:pull-request:GITVS-042"
    assert "meta-organvm/moved-repo" in patch["predicate"]
