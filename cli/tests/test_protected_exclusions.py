from __future__ import annotations

import json
from pathlib import Path

import pytest
from limen.protected_exclusions import (
    ProtectedExclusion,
    ProtectedExclusionError,
    ProtectedExclusionRegistry,
    paths_overlap,
)


def _exclusion() -> ProtectedExclusion:
    return ProtectedExclusion(
        exclusion_id="career-portal",
        owner="career-owner",
        path=Path(".worktrees/career-portal"),
        branch="work/career-portal",
        registration=Path(".git/worktrees/career-portal"),
        blocks_omega=True,
        reason="active externally owned workstream",
    )


def test_ancestor_descendant_and_branch_overlap_fail_closed(tmp_path: Path) -> None:
    (tmp_path / ".git" / "worktrees" / "career-portal").mkdir(parents=True)
    protected = tmp_path / ".worktrees" / "career-portal"
    protected.mkdir(parents=True)
    registry = ProtectedExclusionRegistry.from_exclusions(tmp_path, (_exclusion(),))

    assert paths_overlap(tmp_path / ".worktrees", protected)
    assert registry.match(protected / "nested") == ("protected-exclusion:career-portal:path-overlap")
    assert registry.match(tmp_path) == "protected-exclusion:career-portal:path-overlap"
    assert (
        registry.match(
            tmp_path / "elsewhere",
            branch="work/career-portal",
        )
        == "protected-exclusion:career-portal:branch-match"
    )
    assert registry.match(tmp_path / ".git" / "worktrees") == ("protected-exclusion:career-portal:registration-overlap")


def test_projection_redacts_paths_and_branch(tmp_path: Path) -> None:
    (tmp_path / ".git" / "worktrees" / "career-portal").mkdir(parents=True)
    (tmp_path / ".worktrees" / "career-portal").mkdir(parents=True)
    registry = ProtectedExclusionRegistry.from_exclusions(tmp_path, (_exclusion(),))

    projection = registry.projection()
    encoded = json.dumps(projection, sort_keys=True)

    assert str(tmp_path) not in encoded
    assert ".worktrees/career-portal" not in encoded
    assert "work/career-portal" not in encoded
    assert projection["omega_blocker_count"] == 1
    assert projection["protected_exclusions"][0]["path_exists"] is True


def test_owner_declaration_blocks_omega_even_when_root_disappears(
    tmp_path: Path,
) -> None:
    registry = ProtectedExclusionRegistry.from_exclusions(tmp_path, (_exclusion(),))

    projection = registry.projection()

    assert projection["protected_exclusions"][0]["path_exists"] is False
    assert projection["omega_blocker_count"] == 1


def test_registry_rejects_escaping_relative_path(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "limen.reconciliation_protected_exclusions.v1",
                "exclusions": [
                    {
                        "exclusion_id": "escape",
                        "owner": "owner",
                        "path": "../outside",
                        "branch": "work/escape",
                        "registration": ".git/worktrees/escape",
                        "blocks_omega": True,
                        "reason": "unsafe",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProtectedExclusionError, match="path-must-be-safe-relative"):
        ProtectedExclusionRegistry.load(tmp_path, registry)


def test_registry_translates_missing_repository_root(tmp_path: Path) -> None:
    with pytest.raises(
        ProtectedExclusionError,
        match="protected-exclusion-repository-root-unavailable",
    ):
        ProtectedExclusionRegistry.load(tmp_path / "missing")
