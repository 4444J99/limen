from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from limen.local_git_census import collect_local_git_census


NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True)


def _repository(path: Path, coordinate: str) -> None:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test User")
    _git(path, "commit", "-qm", "base", "--allow-empty")
    _git(path, "remote", "add", "origin", f"git@github.com:{coordinate}.git")
    _git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(path, "branch", "--set-upstream-to", "origin/main", "main")


def test_local_census_deduplicates_clone_seeds_and_enumerates_linked_worktrees(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    _repository(checkout, "owner/repo")
    sibling = tmp_path / "repo-topic"
    _git(checkout, "worktree", "add", "-q", str(sibling), "-b", "topic")

    private, tracked = collect_local_git_census(
        tmp_path,
        checkout_roots=(checkout, sibling, checkout),
        observed_at=NOW,
        require_protection_registry=False,
    )

    assert private["summary"]["checkout_seed_count"] == 3
    assert private["summary"]["root_count"] == 2
    assert private["summary"]["clone_group_count"] == 1
    assert private["summary"]["linked_worktree_count"] == 1
    assert {row["repository"] for row in private["roots"]} == {"owner/repo"}
    assert len({row["common_dir_key"] for row in private["roots"]}) == 1
    assert all("path" not in row and "repository" not in row for row in tracked["roots"])
    assert str(tmp_path) not in tracked["content_sha256"]


def test_local_census_reports_dirty_untracked_and_unpushed_custody_risk(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    _repository(checkout, "owner/repo")
    (checkout / "untracked.txt").write_text("preserve me", encoding="utf-8")
    _git(checkout, "checkout", "-qb", "topic")
    _git(checkout, "commit", "-qm", "topic", "--allow-empty")

    private, _ = collect_local_git_census(
        tmp_path,
        checkout_roots=(checkout,),
        observed_at=NOW,
        require_protection_registry=False,
    )

    root = private["roots"][0]
    assert root["dirty"] is True
    assert root["untracked"] is True
    assert root["unpushed"] is True
    assert root["custody_risk"] is True
    assert private["summary"]["custody_risk_count"] == 1


def test_local_census_fails_closed_when_repository_identity_is_unavailable(tmp_path: Path) -> None:
    checkout = tmp_path / "local-only"
    checkout.mkdir()
    _git(checkout, "init", "-q", "-b", "main")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "config", "user.name", "Test User")
    _git(checkout, "commit", "-qm", "base", "--allow-empty")

    private, tracked = collect_local_git_census(
        tmp_path,
        checkout_roots=(checkout,),
        observed_at=NOW,
        require_protection_registry=False,
    )

    assert private["summary"]["exhaustive"] is False
    assert private["summary"]["unaccounted"] == 1
    assert private["roots"][0]["errors"] == ["repository-identity-unavailable"]
    assert tracked["failures"][0]["scope"] == "git_root"
