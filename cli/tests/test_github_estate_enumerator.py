from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from limen.github_estate_enumerator import (
    GitHubEstateContextV1,
    GitHubEstateSourceSnapshotV1,
    GitHubReadError,
    collect_github_estate_snapshot,
    enumerate_github_estate,
)

OBSERVED_AT = datetime(2026, 7, 29, 0, 30, tzinfo=UTC)
FROZEN_AT = datetime(2026, 7, 29, 1, tzinfo=UTC)
WAVE = "a" * 64
SOURCE_REGISTRY = "b" * 64


def _all_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {item for child in value.values() for item in _all_strings(child)}
    if isinstance(value, (list, tuple)):
        return {item for child in value for item in _all_strings(child)}
    return set()


def _context(dimension: str, *, frozen_at: datetime = FROZEN_AT) -> GitHubEstateContextV1:
    return GitHubEstateContextV1(
        dimension=dimension,
        source_kind="github_estate",
        owner_ref="institutio/github/estate.yaml",
        completeness_predicate="every live repository and access row has a disposition",
        privacy_projection_ref="github-estate-redacted-projection-v1",
        frozen_wave_sha256=WAVE,
        source_registry_sha256=SOURCE_REGISTRY,
        frozen_at=frozen_at,
    )


class FixtureGitHub:
    def __init__(self, *, reverse: bool = False, fail_repository: str | None = None) -> None:
        self.reverse = reverse
        self.fail_repository = fail_repository
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, arguments: tuple[str, ...]) -> Any:
        self.calls.append(arguments)
        if "graphql" in arguments:
            raise GitHubReadError("missing-project-scope")
        endpoint = arguments[-1]
        if endpoint.startswith("/orgs/organvm/repos?"):
            rows = [
                {"full_name": "organvm/alpha"},
                {"full_name": "organvm/beta"},
            ]
            return [list(reversed(rows)) if self.reverse else rows]
        if self.fail_repository and f"/repos/{self.fail_repository}/" in endpoint:
            raise GitHubReadError("repository-read-failed")
        if endpoint == "/repos/organvm/alpha/collaborators?affiliation=outside&per_page=100":
            rows = [{"login": "PrivateAlice", "role_name": "push"}]
            return [list(reversed(rows)) if self.reverse else rows]
        if endpoint == "/repos/organvm/alpha/invitations?per_page=100":
            return [[]]
        if endpoint == "/repos/organvm/beta/collaborators?affiliation=outside&per_page=100":
            return [[]]
        if endpoint == "/repos/organvm/beta/invitations?per_page=100":
            rows = [
                {
                    "invitee": {"login": "PrivateBob"},
                    "permissions": "read",
                }
            ]
            return [list(reversed(rows)) if self.reverse else rows]
        raise AssertionError(f"unexpected fixture endpoint: {endpoint}")


def _snapshot(fake: FixtureGitHub | None = None) -> GitHubEstateSourceSnapshotV1:
    return collect_github_estate_snapshot(
        repository_owner="organvm",
        project_owner="4444J99",
        observed_at=OBSERVED_AT,
        api_json=fake or FixtureGitHub(),
        workers=2,
    )


def test_snapshot_scans_every_repository_and_emits_only_redacted_identities() -> None:
    fake = FixtureGitHub()
    snapshot = _snapshot(fake)
    emitted = _all_strings(snapshot.model_dump(mode="json"))

    assert snapshot.repository_enumeration_complete
    assert snapshot.collaborator_enumeration_complete
    assert not snapshot.project_enumeration_complete
    assert not snapshot.project_scope_available
    assert len(snapshot.repository_ids) == 2
    assert len(snapshot.access_rows) == 2
    assert len(snapshot.project_debt_ids) == 1
    assert not {"organvm/alpha", "organvm/beta", "PrivateAlice", "PrivateBob"} & emitted
    repository_access_calls = [arguments for arguments in fake.calls if arguments[-1].startswith("/repos/")]
    assert len(repository_access_calls) == 4
    GitHubEstateSourceSnapshotV1.model_validate_json(snapshot.model_dump_json())


def test_snapshot_order_is_canonical_and_one_repo_failure_stays_visible() -> None:
    first = _snapshot(FixtureGitHub())
    reordered = _snapshot(FixtureGitHub(reverse=True))
    failed = _snapshot(FixtureGitHub(fail_repository="organvm/beta"))

    assert first == reordered
    assert first.github_read_receipt_sha256 == reordered.github_read_receipt_sha256
    assert failed.repository_enumeration_complete
    assert not failed.collaborator_enumeration_complete
    assert failed.collaborator_debt_ids
    assert len(failed.repository_ids) == 2


def test_snapshot_empty_repository_census_fails_closed() -> None:
    def empty(arguments: tuple[str, ...]) -> Any:
        if "graphql" in arguments:
            raise GitHubReadError("missing-project-scope")
        return [[]]

    snapshot = collect_github_estate_snapshot(
        repository_owner="organvm",
        project_owner="4444J99",
        observed_at=OBSERVED_AT,
        api_json=empty,
    )

    assert not snapshot.repository_enumeration_complete
    assert not snapshot.collaborator_enumeration_complete
    assert snapshot.repository_debt_ids
    assert snapshot.repository_ids == ()


def test_enumerator_preserves_repository_access_and_project_debt_without_false_entities(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(snapshot.model_dump_json())
    project = enumerate_github_estate(
        dimension="project",
        context=_context("project"),
        snapshot_path=snapshot_path,
    )
    collaborator = enumerate_github_estate(
        dimension="collaborator",
        context=_context("collaborator"),
        snapshot_path=snapshot_path,
    )

    assert not project["enumeration_complete"]
    assert not collaborator["enumeration_complete"]
    assert len(project["instances"]) == 3
    assert len(collaborator["instances"]) == 3
    assert all(not item["projects"] for item in project["instances"])
    assert all(not item["collaborators"] for item in collaborator["instances"])
    assert sum(len(item["unclassified_row_ids"]) for item in project["instances"]) == 5
    assert sum(len(item["unclassified_row_ids"]) for item in collaborator["instances"]) == 5
    assert all(not item["non_project_row_ids"] for item in collaborator["instances"])


def test_snapshot_newer_than_frozen_wave_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(snapshot.model_dump_json())

    with pytest.raises(ValueError, match="newer than the frozen wave"):
        enumerate_github_estate(
            dimension="census",
            context=_context(
                "census",
                frozen_at=OBSERVED_AT - timedelta(seconds=1),
            ),
            snapshot_path=snapshot_path,
        )
