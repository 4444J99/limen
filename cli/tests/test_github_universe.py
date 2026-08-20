from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from limen.github_universe import (
    GitHubProjectMemberSnapshotV1,
    GitHubRepositoryGrantSnapshotV1,
    GitHubUniverseCardSnapshotV1,
    GitHubUniverseProjectSnapshotV1,
    GitHubUniverseSnapshotV1,
    reconcile_github_universe,
)
from limen.prima_materia import (
    CollaboratorProjectRelationshipV1,
    CollaboratorRepositoryAccessV1,
    CollaboratorUniverseEntryV1,
    CollaboratorUniverseManifestV1,
    ProjectUniverseEntryV1,
    ProjectUniverseManifestV1,
)
from limen.universe_audit import GitHubProjectionPlanV1, canonical_digest

WAVE = "a" * 64
RUNTIME = "b" * 40
SOURCE_REGISTRY = "c" * 64
READ_RECEIPT = "d" * 64
OBSERVED_AT = datetime(2026, 7, 28, 20, tzinfo=UTC)
PROJECT_ID = "projectIdentifierA1"
PROJECT_NODE = "githubProjectNode001"
CARD_ID = "githubProjectCard001"
ADMIN = "1" * 64
CONTRIBUTOR = "2" * 64
ADVISOR = "3" * 64
REPOSITORY_ONLY = "4" * 64


def _project_manifest() -> ProjectUniverseManifestV1:
    project = ProjectUniverseEntryV1(
        project_id=PROJECT_ID,
        alias_ids=("projectLegacyAlias1",),
        source_lineage_ids=("source-lineage-project-a",),
        repository_ids=("repository-a",),
        child_task_ids=("task-row-001",),
        artifact_refs=("artifact-project-a",),
        collaborator_ids=(
            "advisorIdentity001",
            "coBuilderIdentity01",
            "contributorId001",
            "repositoryOnlyId01",
        ),
        lifecycle_stage="live",
        predicate_refs=("build-project-a",),
        receipt_refs=("receipt-project-a",),
        coverage_disposition="complete",
        build_status="passed",
    )
    return ProjectUniverseManifestV1(
        manifest_id="projectManifest001",
        frozen_at=OBSERVED_AT,
        frozen_wave_digest=WAVE,
        source_registry_digest=SOURCE_REGISTRY,
        enumeration_complete=True,
        required_source_instance_ids=("sourceInstanceA01",),
        observed_source_instance_ids=("sourceInstanceA01",),
        missing_source_instance_ids=(),
        unexpected_source_instance_ids=(),
        required_project_ids=(PROJECT_ID,),
        missing_project_ids=(),
        unexpected_project_ids=(),
        projects=(project,),
    )


def _collaborator(
    *,
    collaborator_id: str,
    github_digest: str,
    roles: tuple[str, ...],
    project_level: str = "none",
    project_status: str = "not_granted",
    repository_accesses: tuple[CollaboratorRepositoryAccessV1, ...] = (),
) -> CollaboratorUniverseEntryV1:
    return CollaboratorUniverseEntryV1(
        collaborator_id=collaborator_id,
        source_lineage_ids=(f"lineage-{collaborator_id}",),
        github_login_sha256=github_digest,
        github_identity_receipt_ref=f"github-proof-{collaborator_id}",
        relationships=(
            CollaboratorProjectRelationshipV1(
                project_id=PROJECT_ID,
                roles=roles,
                project_access_level=project_level,
                project_access_status=project_status,
                project_authority_ref=(f"project-authority-{collaborator_id}" if project_status == "active" else None),
                project_access_receipt_refs=(
                    (f"project-access-{collaborator_id}",) if project_status != "not_granted" else ()
                ),
                repository_accesses=repository_accesses,
            ),
        ),
        coverage_disposition="reconciled",
        disposition_receipt_refs=(f"disposition-{collaborator_id}",),
    )


def _collaborator_manifest(
    project_manifest: ProjectUniverseManifestV1,
) -> CollaboratorUniverseManifestV1:
    repository_access = CollaboratorRepositoryAccessV1(
        repository_id="repository-a",
        access_level="write",
        status="active",
        authority_ref="repository-authority-a",
        receipt_refs=("repository-receipt-a",),
    )
    repository_only_access = CollaboratorRepositoryAccessV1(
        repository_id="repository-a",
        access_level="read",
        status="active",
        authority_ref="repository-authority-read",
        receipt_refs=("repository-receipt-read",),
    )
    collaborators = (
        _collaborator(
            collaborator_id="advisorIdentity001",
            github_digest=ADVISOR,
            roles=("advisor", "reference"),
            project_level="read",
            project_status="active",
        ),
        _collaborator(
            collaborator_id="coBuilderIdentity01",
            github_digest=ADMIN,
            roles=("co_builder",),
            project_level="admin",
            project_status="active",
            repository_accesses=(repository_access,),
        ),
        _collaborator(
            collaborator_id="contributorId001",
            github_digest=CONTRIBUTOR,
            roles=("contributor",),
            project_level="write",
            project_status="active",
        ),
        _collaborator(
            collaborator_id="repositoryOnlyId01",
            github_digest=REPOSITORY_ONLY,
            roles=("contributor",),
            repository_accesses=(repository_only_access,),
        ),
    )
    return CollaboratorUniverseManifestV1(
        manifest_id="collaboratorManifest001",
        frozen_at=OBSERVED_AT,
        frozen_wave_digest=WAVE,
        source_registry_digest=SOURCE_REGISTRY,
        project_universe_manifest_digest=canonical_digest(project_manifest),
        enumeration_complete=True,
        required_source_instance_ids=("sourceInstanceA01",),
        observed_source_instance_ids=("sourceInstanceA01",),
        missing_source_instance_ids=(),
        unexpected_source_instance_ids=(),
        project_ids=(PROJECT_ID,),
        required_collaborator_ids=tuple(collaborator.collaborator_id for collaborator in collaborators),
        missing_collaborator_ids=(),
        unexpected_collaborator_ids=(),
        collaborators=collaborators,
    )


def _card(project_manifest: ProjectUniverseManifestV1) -> GitHubUniverseCardSnapshotV1:
    project = project_manifest.projects[0]
    return GitHubUniverseCardSnapshotV1(
        card_id=CARD_ID,
        project_id=project.project_id,
        lifecycle_stage=project.lifecycle_stage,
        build_status=project.build_status,
        artifact_refs=project.artifact_refs,
        receipt_refs=project.receipt_refs,
        collaborator_ids=project.collaborator_ids,
    )


def _snapshot(
    project_manifest: ProjectUniverseManifestV1,
    *,
    projects: tuple[GitHubUniverseProjectSnapshotV1, ...] | None = None,
    repository_grants: tuple[GitHubRepositoryGrantSnapshotV1, ...] | None = None,
) -> GitHubUniverseSnapshotV1:
    exact_project = GitHubUniverseProjectSnapshotV1(
        project_node_id=PROJECT_NODE,
        title="ORGANVM Universe",
        marker="organvm-universe:v1",
        cards=(_card(project_manifest),),
        members=(
            GitHubProjectMemberSnapshotV1(
                github_login_sha256=ADMIN,
                access_level="admin",
            ),
            GitHubProjectMemberSnapshotV1(
                github_login_sha256=CONTRIBUTOR,
                access_level="write",
            ),
            GitHubProjectMemberSnapshotV1(
                github_login_sha256=ADVISOR,
                access_level="read",
            ),
        ),
    )
    exact_grants = (
        GitHubRepositoryGrantSnapshotV1(
            repository_id="repository-a",
            github_login_sha256=ADMIN,
            access_level="write",
        ),
        GitHubRepositoryGrantSnapshotV1(
            repository_id="repository-a",
            github_login_sha256=REPOSITORY_ONLY,
            access_level="read",
        ),
    )
    return GitHubUniverseSnapshotV1(
        observed_at=OBSERVED_AT,
        owner="4444J99",
        enumeration_complete=True,
        github_read_receipt_sha256=READ_RECEIPT,
        projects=(exact_project,) if projects is None else projects,
        repository_grants=exact_grants if repository_grants is None else repository_grants,
    )


def _reconcile(snapshot: GitHubUniverseSnapshotV1):
    project_manifest = _project_manifest()
    collaborator_manifest = _collaborator_manifest(project_manifest)
    return reconcile_github_universe(
        frozen_wave_sha256=WAVE,
        installed_runtime_sha=RUNTIME,
        project_manifest=project_manifest,
        collaborator_manifest=collaborator_manifest,
        snapshot=snapshot,
    )


def test_exact_existing_marker_project_is_adopted_idempotently() -> None:
    project_manifest = _project_manifest()
    result = _reconcile(_snapshot(project_manifest))

    assert result.idempotent
    assert result.safe_to_apply
    assert result.actions == ()
    assert result.projection_plan.change_count == 0
    assert result.projection_plan.project_owner == "4444J99"
    assert result.projection_plan.project_marker == "organvm-universe:v1"


def test_absent_project_plans_creation_cards_and_access_without_conflating_repo_grants() -> None:
    project_manifest = _project_manifest()
    result = _reconcile(
        _snapshot(
            project_manifest,
            projects=(),
            repository_grants=(),
        )
    )

    assert result.safe_to_apply
    assert not result.idempotent
    kinds = tuple(action.kind for action in result.actions)
    assert "create_project" in kinds
    assert "create_card" in kinds
    assert kinds.count("grant_project_access") == 3
    assert kinds.count("grant_repository_access") == 2
    assert result.projection_plan.change_count == 7
    assert not any(
        action.target_type == "project_access" and action.target_id == REPOSITORY_ONLY for action in result.actions
    )


def test_duplicate_projects_and_unbound_cards_fail_closed() -> None:
    project_manifest = _project_manifest()
    exact = _snapshot(project_manifest).projects[0]
    duplicate = exact.model_copy(update={"project_node_id": "githubProjectNode002"})
    duplicated = _reconcile(_snapshot(project_manifest, projects=(exact, duplicate)))
    assert not duplicated.safe_to_apply
    assert duplicated.actions == ()
    assert duplicated.projection_plan.duplicate_project_ids == (
        "githubProjectNode001",
        "githubProjectNode002",
    )

    unbound = GitHubUniverseCardSnapshotV1(
        card_id="githubUnboundCard01",
    )
    project_with_unbound = exact.model_copy(update={"cards": (exact.cards[0], unbound)})
    unbound_result = _reconcile(_snapshot(project_manifest, projects=(project_with_unbound,)))
    assert not unbound_result.safe_to_apply
    assert unbound_result.actions == ()
    assert unbound_result.projection_plan.unbound_card_ids == ("githubUnboundCard01",)

    duplicate_card = exact.cards[0].model_copy(update={"card_id": "githubProjectCard002"})
    duplicate_cards = exact.model_copy(update={"cards": (exact.cards[0], duplicate_card)})
    duplicate_card_result = _reconcile(_snapshot(project_manifest, projects=(duplicate_cards,)))
    assert not duplicate_card_result.safe_to_apply
    assert duplicate_card_result.projection_plan.unbound_card_ids == (
        "githubProjectCard001",
        "githubProjectCard002",
    )


def test_stronger_and_unclassified_live_access_is_visible_but_never_downgraded() -> None:
    project_manifest = _project_manifest()
    exact = _snapshot(project_manifest)
    project = exact.projects[0]
    stronger_members = tuple(
        member.model_copy(update={"access_level": "admin"}) if member.github_login_sha256 == ADVISOR else member
        for member in project.members
    )
    extra_digest = "5" * 64
    stronger_project = project.model_copy(
        update={
            "members": (
                *stronger_members,
                GitHubProjectMemberSnapshotV1(
                    github_login_sha256=extra_digest,
                    access_level="read",
                ),
            )
        }
    )
    stronger_grants = tuple(
        grant.model_copy(update={"access_level": "admin"}) if grant.github_login_sha256 == ADMIN else grant
        for grant in exact.repository_grants
    )
    result = _reconcile(
        _snapshot(
            project_manifest,
            projects=(stronger_project,),
            repository_grants=stronger_grants,
        )
    )

    assert not result.safe_to_apply
    assert result.projection_plan.change_count == 0
    assert result.projection_plan.privacy_findings_count == 3
    assert {action.kind for action in result.actions} == {
        "retain_stronger_project_access",
        "retain_stronger_repository_access",
        "retain_unclassified_project_member",
    }
    assert not any(action.mutation for action in result.actions)


def test_cli_plan_emits_the_exact_audit_plan_and_check_never_writes(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    project_manifest = _project_manifest()
    collaborator_manifest = _collaborator_manifest(project_manifest)
    snapshot = _snapshot(project_manifest)
    fixtures = {
        "project.json": project_manifest,
        "collaborator.json": collaborator_manifest,
        "snapshot.json": snapshot,
    }
    for name, model in fixtures.items():
        (tmp_path / name).write_text(
            json.dumps(model.model_dump(mode="json")),
            encoding="utf-8",
        )
    base = [
        "--frozen-wave-sha",
        WAVE,
        "--installed-runtime-sha",
        RUNTIME,
        "--project-manifest",
        str(tmp_path / "project.json"),
        "--collaborator-manifest",
        str(tmp_path / "collaborator.json"),
        "--snapshot",
        str(tmp_path / "snapshot.json"),
    ]
    plan_output = tmp_path / "plan.json"
    planned = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "prima-materia-github-universe.py"),
            "plan",
            *base,
            "--projection-output",
            str(plan_output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert planned.returncode == 0
    GitHubProjectionPlanV1.model_validate_json(plan_output.read_text())
    before = sorted(path.name for path in tmp_path.iterdir())

    checked = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "prima-materia-github-universe.py"),
            "check",
            *base,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert checked.returncode == 0
    assert json.loads(checked.stdout)["idempotent"] is True
    assert sorted(path.name for path in tmp_path.iterdir()) == before

    (tmp_path / "snapshot.json").write_text("{not-json", encoding="utf-8")
    failed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "prima-materia-github-universe.py"),
            "plan",
            *base,
            "--projection-output",
            str(plan_output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert failed.returncode == 1
    assert json.loads(plan_output.read_text())["passed"] is False
