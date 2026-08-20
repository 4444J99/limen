"""Privacy-safe, snapshot-driven GitHub universe reconciliation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import rfc8785
from pydantic import Field, field_validator, model_validator

from limen.prima_materia import (
    CollaboratorUniverseManifestV1,
    PrimaMateriaModel,
    ProjectUniverseEntryV1,
    ProjectUniverseManifestV1,
)
from limen.universe_audit import GitHubProjectionPlanV1, canonical_digest

RESULT_SCHEMA: Literal["limen.prima_materia_github_reconciliation.v1"] = "limen.prima_materia_github_reconciliation.v1"
SNAPSHOT_SCHEMA: Literal["limen.prima_materia_github_snapshot.v1"] = "limen.prima_materia_github_snapshot.v1"
PROJECT_OWNER: Literal["4444J99"] = "4444J99"
PROJECT_MARKER: Literal["organvm-universe:v1"] = "organvm-universe:v1"
PROJECT_TITLE = "ORGANVM Universe"
ProjectLevel = Literal["read", "write", "admin"]
RepositoryLevel = Literal["read", "triage", "write", "maintain", "admin"]
ActionKind = Literal[
    "create_project",
    "rename_project",
    "create_card",
    "update_card",
    "grant_project_access",
    "raise_project_access",
    "grant_repository_access",
    "raise_repository_access",
    "retain_stronger_project_access",
    "retain_stronger_repository_access",
    "retain_unclassified_project_member",
    "retain_unclassified_repository_grant",
]


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _validate_git_sha(value: str) -> str:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("runtime SHA must be a full lowercase SHA-1")
    return value


def _validate_opaque(value: str) -> str:
    if not 16 <= len(value) <= 128 or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for character in value
    ):
        raise ValueError("identity must be a bounded base64url-style identifier")
    return value


def _validate_key(value: str) -> str:
    if not 1 <= len(value) <= 256 or "\x00" in value or value.strip() != value:
        raise ValueError("reference must be a bounded nonblank string")
    return value


def _validate_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value.astimezone(UTC)


def _sorted_unique(values: tuple[str, ...], label: str, validator=_validate_key) -> tuple[str, ...]:
    normalized = tuple(validator(value) for value in values)
    if normalized != tuple(sorted(normalized)) or len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be sorted and unique")
    return normalized


def _privacy_digest(findings: tuple[str, ...]) -> str:
    payload = {
        "schema": "limen.prima_materia_github_privacy_receipt.v1",
        "findings": findings,
    }
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


class GitHubUniverseCardSnapshotV1(PrimaMateriaModel):
    card_id: str
    project_id: str | None = None
    lifecycle_stage: str | None = None
    build_status: str | None = None
    artifact_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    receipt_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    collaborator_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)

    _card = field_validator("card_id")(_validate_opaque)

    @model_validator(mode="after")
    def fields_are_privacy_safe_and_canonical(self) -> GitHubUniverseCardSnapshotV1:
        if self.project_id is not None:
            _validate_opaque(self.project_id)
        if self.lifecycle_stage is not None:
            _validate_key(self.lifecycle_stage)
        if self.build_status is not None:
            _validate_key(self.build_status)
        _sorted_unique(self.artifact_refs, "card artifacts")
        _sorted_unique(self.receipt_refs, "card receipts")
        _sorted_unique(self.collaborator_ids, "card collaborators", _validate_opaque)
        return self


class GitHubProjectMemberSnapshotV1(PrimaMateriaModel):
    github_login_sha256: str
    access_level: ProjectLevel

    _digest = field_validator("github_login_sha256")(_validate_digest)


class GitHubUniverseProjectSnapshotV1(PrimaMateriaModel):
    project_node_id: str
    title: str
    marker: str | None = None
    cards: tuple[GitHubUniverseCardSnapshotV1, ...] = Field(default_factory=tuple, max_length=100_000)
    members: tuple[GitHubProjectMemberSnapshotV1, ...] = Field(default_factory=tuple, max_length=100_000)

    _node = field_validator("project_node_id")(_validate_opaque)
    _title = field_validator("title")(_validate_key)
    _marker = field_validator("marker")(lambda value: _validate_key(value) if value is not None else None)

    @model_validator(mode="after")
    def child_identities_are_unique(self) -> GitHubUniverseProjectSnapshotV1:
        card_ids = tuple(card.card_id for card in self.cards)
        member_ids = tuple(member.github_login_sha256 for member in self.members)
        if len(card_ids) != len(set(card_ids)):
            raise ValueError("GitHub Project card identities must be unique")
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("GitHub Project member identities must be unique")
        return self


class GitHubRepositoryGrantSnapshotV1(PrimaMateriaModel):
    repository_id: str
    github_login_sha256: str
    access_level: RepositoryLevel

    _repository = field_validator("repository_id")(_validate_key)
    _digest = field_validator("github_login_sha256")(_validate_digest)


class GitHubUniverseSnapshotV1(PrimaMateriaModel):
    """Bounded remote-read state with no raw login or private repository names."""

    schema_version: Literal["limen.prima_materia_github_snapshot.v1"] = SNAPSHOT_SCHEMA
    observed_at: datetime
    owner: Literal["4444J99"]
    enumeration_complete: bool
    github_read_receipt_sha256: str
    projects: tuple[GitHubUniverseProjectSnapshotV1, ...] = Field(max_length=4096)
    repository_grants: tuple[GitHubRepositoryGrantSnapshotV1, ...] = Field(
        default_factory=tuple,
        max_length=100_000,
    )

    _observed = field_validator("observed_at")(_validate_aware)
    _receipt = field_validator("github_read_receipt_sha256")(_validate_digest)

    @model_validator(mode="after")
    def remote_identities_are_unique(self) -> GitHubUniverseSnapshotV1:
        project_ids = tuple(project.project_node_id for project in self.projects)
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("GitHub Project node identities must be unique")
        grant_ids = tuple((grant.repository_id, grant.github_login_sha256) for grant in self.repository_grants)
        if len(grant_ids) != len(set(grant_ids)):
            raise ValueError("repository grant identities must be unique")
        return self


class GitHubReconciliationActionV1(PrimaMateriaModel):
    kind: ActionKind
    target_type: Literal["project", "card", "project_access", "repository_access"]
    target_id: str
    mutation: bool
    current_level: str | None = None
    desired_level: str | None = None
    reason: str

    _target = field_validator("target_id")(_validate_key)
    _levels = field_validator("current_level", "desired_level")(
        lambda value: _validate_key(value) if value is not None else None
    )
    _reason = field_validator("reason")(_validate_key)

    @model_validator(mode="after")
    def retained_drift_is_never_a_mutation(self) -> GitHubReconciliationActionV1:
        if self.kind.startswith("retain_") and self.mutation:
            raise ValueError("retained stronger or unclassified access is observation-only")
        return self


class GitHubUniverseReconciliationV1(PrimaMateriaModel):
    schema_version: Literal["limen.prima_materia_github_reconciliation.v1"] = RESULT_SCHEMA
    safe_to_apply: bool
    idempotent: bool
    projection_plan: GitHubProjectionPlanV1
    actions: tuple[GitHubReconciliationActionV1, ...] = Field(max_length=200_000)
    privacy_findings: tuple[str, ...] = Field(max_length=200_000)

    @model_validator(mode="after")
    def summary_matches_plan(self) -> GitHubUniverseReconciliationV1:
        mutation_count = sum(action.mutation for action in self.actions)
        if mutation_count != self.projection_plan.change_count:
            raise ValueError("projection change count must equal mutation actions")
        if len(self.privacy_findings) != self.projection_plan.privacy_findings_count:
            raise ValueError("privacy finding count must equal the privacy receipt")
        expected_idempotent = (
            mutation_count == 0
            and not self.projection_plan.duplicate_project_ids
            and not self.projection_plan.unbound_card_ids
            and not self.privacy_findings
        )
        if self.idempotent != expected_idempotent:
            raise ValueError("idempotence summary does not match the plan")
        expected_safe = (
            not self.projection_plan.duplicate_project_ids
            and not self.projection_plan.unbound_card_ids
            and not self.privacy_findings
        )
        if self.safe_to_apply != expected_safe:
            raise ValueError("apply safety does not match fail-closed findings")
        return self


def _desired_card(project: ProjectUniverseEntryV1) -> dict[str, object]:
    return {
        "project_id": project.project_id,
        "lifecycle_stage": project.lifecycle_stage,
        "build_status": project.build_status,
        "artifact_refs": project.artifact_refs,
        "receipt_refs": project.receipt_refs,
        "collaborator_ids": project.collaborator_ids,
    }


def _card_matches(card: GitHubUniverseCardSnapshotV1, project: ProjectUniverseEntryV1) -> bool:
    desired = _desired_card(project)
    return all(getattr(card, field) == value for field, value in desired.items())


def _maximum_level(levels: set[str], order: tuple[str, ...]) -> str:
    return max(levels, key=order.index)


def _desired_access(
    collaborator_manifest: CollaboratorUniverseManifestV1,
) -> tuple[dict[str, ProjectLevel], dict[tuple[str, str], RepositoryLevel]]:
    project_levels: dict[str, set[str]] = defaultdict(set)
    repository_levels: dict[tuple[str, str], set[str]] = defaultdict(set)
    for collaborator in collaborator_manifest.collaborators:
        digest = collaborator.github_login_sha256
        for relationship in collaborator.relationships:
            if relationship.project_access_status in {"pending", "active"}:
                if digest is None or relationship.project_access_level == "none":
                    raise ValueError("desired Project access lacks a proven GitHub identity")
                project_levels[digest].add(relationship.project_access_level)
            for access in relationship.repository_accesses:
                if access.status in {"pending", "active"}:
                    if digest is None or access.access_level == "none":
                        raise ValueError("desired repository access lacks a proven GitHub identity")
                    repository_levels[(access.repository_id, digest)].add(access.access_level)
    return (
        {
            digest: cast(ProjectLevel, _maximum_level(levels, ("read", "write", "admin")))
            for digest, levels in project_levels.items()
        },
        {
            identity: cast(RepositoryLevel, _maximum_level(levels, ("read", "triage", "write", "maintain", "admin")))
            for identity, levels in repository_levels.items()
        },
    )


def _access_actions(
    *,
    desired: dict,
    current: dict,
    target_type: Literal["project_access", "repository_access"],
    level_order: tuple[str, ...],
) -> tuple[list[GitHubReconciliationActionV1], list[str]]:
    actions = []
    findings = []
    for identity, desired_level in sorted(desired.items(), key=lambda item: str(item[0])):
        current_level = current.get(identity)
        target_id = ":".join(identity) if isinstance(identity, tuple) else identity
        if current_level is None:
            actions.append(
                GitHubReconciliationActionV1(
                    kind=("grant_project_access" if target_type == "project_access" else "grant_repository_access"),
                    target_type=target_type,
                    target_id=target_id,
                    mutation=True,
                    desired_level=desired_level,
                    reason="source-authorized access is absent from the remote snapshot",
                )
            )
        elif level_order.index(current_level) < level_order.index(desired_level):
            actions.append(
                GitHubReconciliationActionV1(
                    kind=("raise_project_access" if target_type == "project_access" else "raise_repository_access"),
                    target_type=target_type,
                    target_id=target_id,
                    mutation=True,
                    current_level=current_level,
                    desired_level=desired_level,
                    reason="remote access is below the source-authorized level",
                )
            )
        elif level_order.index(current_level) > level_order.index(desired_level):
            finding = f"stronger-{target_type}:{target_id}"
            findings.append(finding)
            actions.append(
                GitHubReconciliationActionV1(
                    kind=(
                        "retain_stronger_project_access"
                        if target_type == "project_access"
                        else "retain_stronger_repository_access"
                    ),
                    target_type=target_type,
                    target_id=target_id,
                    mutation=False,
                    current_level=current_level,
                    desired_level=desired_level,
                    reason="stronger live access is preserved and requires source-owner disposition",
                )
            )
    for identity, current_level in sorted(current.items(), key=lambda item: str(item[0])):
        if identity in desired:
            continue
        target_id = ":".join(identity) if isinstance(identity, tuple) else identity
        findings.append(f"unclassified-{target_type}:{target_id}")
        actions.append(
            GitHubReconciliationActionV1(
                kind=(
                    "retain_unclassified_project_member"
                    if target_type == "project_access"
                    else "retain_unclassified_repository_grant"
                ),
                target_type=target_type,
                target_id=target_id,
                mutation=False,
                current_level=current_level,
                reason="live access has no source-authorized collaborator disposition",
            )
        )
    return actions, findings


def reconcile_github_universe(
    *,
    frozen_wave_sha256: str,
    installed_runtime_sha: str,
    project_manifest: ProjectUniverseManifestV1,
    collaborator_manifest: CollaboratorUniverseManifestV1,
    snapshot: GitHubUniverseSnapshotV1,
) -> GitHubUniverseReconciliationV1:
    """Build a deterministic plan without performing any GitHub mutation."""

    _validate_digest(frozen_wave_sha256)
    _validate_git_sha(installed_runtime_sha)
    project_manifest_sha256 = canonical_digest(project_manifest)
    collaborator_manifest_sha256 = canonical_digest(collaborator_manifest)
    if project_manifest.frozen_wave_digest != frozen_wave_sha256:
        raise ValueError("project manifest does not bind the frozen wave")
    if collaborator_manifest.frozen_wave_digest != frozen_wave_sha256:
        raise ValueError("collaborator manifest does not bind the frozen wave")
    if collaborator_manifest.source_registry_digest != project_manifest.source_registry_digest:
        raise ValueError("universe manifests do not bind the same source registry")
    if collaborator_manifest.project_universe_manifest_digest != project_manifest_sha256:
        raise ValueError("collaborator manifest does not bind the project manifest")
    project_ids = tuple(project.project_id for project in project_manifest.projects)
    if collaborator_manifest.project_ids != project_ids:
        raise ValueError("collaborator manifest does not bind the project denominator")
    if not project_manifest.source_coverage_complete:
        raise ValueError("GitHub projection requires complete source coverage")
    if not project_manifest.canonical_project_coverage_complete:
        raise ValueError("GitHub projection requires complete canonical project coverage")
    if not collaborator_manifest.reconciled:
        raise ValueError("GitHub projection requires reconciled collaborators")
    if not snapshot.enumeration_complete:
        raise ValueError("GitHub remote-read snapshot is incomplete")

    marker_projects = tuple(project for project in snapshot.projects if project.marker == PROJECT_MARKER)
    duplicate_project_ids = (
        tuple(sorted(project.project_node_id for project in marker_projects)) if len(marker_projects) > 1 else ()
    )
    adopted = marker_projects[0] if len(marker_projects) == 1 else None
    desired_projects = {project.project_id: project for project in project_manifest.projects}
    unbound_card_ids = []
    if adopted is not None:
        cards_by_project: dict[str, list[GitHubUniverseCardSnapshotV1]] = defaultdict(list)
        for card in adopted.cards:
            if card.project_id not in desired_projects:
                unbound_card_ids.append(card.card_id)
            else:
                cards_by_project[card.project_id].append(card)
        for cards in cards_by_project.values():
            if len(cards) > 1:
                unbound_card_ids.extend(card.card_id for card in cards)
    unbound_card_ids = sorted(set(unbound_card_ids))

    actions: list[GitHubReconciliationActionV1] = []
    findings: list[str] = []
    structural_failure = bool(duplicate_project_ids or unbound_card_ids)
    if not structural_failure:
        if adopted is None:
            actions.append(
                GitHubReconciliationActionV1(
                    kind="create_project",
                    target_type="project",
                    target_id=PROJECT_MARKER,
                    mutation=True,
                    desired_level=PROJECT_TITLE,
                    reason="no marker-bound user Project exists",
                )
            )
        elif adopted.title != PROJECT_TITLE:
            actions.append(
                GitHubReconciliationActionV1(
                    kind="rename_project",
                    target_type="project",
                    target_id=adopted.project_node_id,
                    mutation=True,
                    current_level=adopted.title,
                    desired_level=PROJECT_TITLE,
                    reason="marker-bound Project title differs from the canonical title",
                )
            )

        live_cards = {card.project_id: card for card in adopted.cards} if adopted is not None else {}
        for project_id, project in sorted(desired_projects.items()):
            live_card: GitHubUniverseCardSnapshotV1 | None = live_cards.get(project_id)
            if live_card is None:
                actions.append(
                    GitHubReconciliationActionV1(
                        kind="create_card",
                        target_type="card",
                        target_id=project_id,
                        mutation=True,
                        reason="canonical project lacks a marker-bound card",
                    )
                )
            elif not _card_matches(live_card, project):
                actions.append(
                    GitHubReconciliationActionV1(
                        kind="update_card",
                        target_type="card",
                        target_id=live_card.card_id,
                        mutation=True,
                        reason="marker-bound card differs from the frozen project manifest",
                    )
                )

        desired_project_access, desired_repository_access = _desired_access(collaborator_manifest)
        live_project_access = (
            {member.github_login_sha256: member.access_level for member in adopted.members}
            if adopted is not None
            else {}
        )
        project_actions, project_findings = _access_actions(
            desired=desired_project_access,
            current=live_project_access,
            target_type="project_access",
            level_order=("read", "write", "admin"),
        )
        live_repository_access = {
            (grant.repository_id, grant.github_login_sha256): grant.access_level for grant in snapshot.repository_grants
        }
        repository_actions, repository_findings = _access_actions(
            desired=desired_repository_access,
            current=live_repository_access,
            target_type="repository_access",
            level_order=("read", "triage", "write", "maintain", "admin"),
        )
        actions.extend(project_actions)
        actions.extend(repository_actions)
        findings.extend(project_findings)
        findings.extend(repository_findings)

    actions_tuple = tuple(
        sorted(
            actions,
            key=lambda action: (
                action.target_type,
                action.target_id,
                action.kind,
            ),
        )
    )
    findings_tuple = tuple(sorted(set(findings)))
    mutation_count = sum(action.mutation for action in actions_tuple)
    projection_plan = GitHubProjectionPlanV1(
        observed_at=snapshot.observed_at,
        frozen_wave_sha256=frozen_wave_sha256,
        installed_runtime_sha=installed_runtime_sha,
        source_registry_sha256=project_manifest.source_registry_digest,
        project_manifest_sha256=project_manifest_sha256,
        collaborator_manifest_sha256=collaborator_manifest_sha256,
        project_owner=PROJECT_OWNER,
        project_marker=PROJECT_MARKER,
        change_count=mutation_count,
        duplicate_project_ids=duplicate_project_ids,
        unbound_card_ids=tuple(unbound_card_ids),
        privacy_findings_count=len(findings_tuple),
        github_read_receipt_sha256=snapshot.github_read_receipt_sha256,
        privacy_receipt_sha256=_privacy_digest(findings_tuple),
    )
    return GitHubUniverseReconciliationV1(
        safe_to_apply=not structural_failure and not findings_tuple,
        idempotent=not structural_failure and not findings_tuple and mutation_count == 0,
        projection_plan=projection_plan,
        actions=actions_tuple,
        privacy_findings=findings_tuple,
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("check", "plan"))
    result.add_argument("--frozen-wave-sha", required=True)
    result.add_argument("--installed-runtime-sha", required=True)
    result.add_argument("--project-manifest", type=Path, required=True)
    result.add_argument("--collaborator-manifest", type=Path, required=True)
    result.add_argument("--snapshot", type=Path, required=True)
    result.add_argument("--projection-output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.mode == "plan" and arguments.projection_output is None:
            raise ValueError("plan mode requires --projection-output")
        if arguments.mode == "check" and arguments.projection_output is not None:
            raise ValueError("check mode is read-only and rejects --projection-output")
        project_manifest = ProjectUniverseManifestV1.model_validate_json(
            arguments.project_manifest.read_text(encoding="utf-8")
        )
        collaborator_manifest = CollaboratorUniverseManifestV1.model_validate_json(
            arguments.collaborator_manifest.read_text(encoding="utf-8")
        )
        snapshot = GitHubUniverseSnapshotV1.model_validate_json(arguments.snapshot.read_text(encoding="utf-8"))
        reconciliation = reconcile_github_universe(
            frozen_wave_sha256=arguments.frozen_wave_sha,
            installed_runtime_sha=arguments.installed_runtime_sha,
            project_manifest=project_manifest,
            collaborator_manifest=collaborator_manifest,
            snapshot=snapshot,
        )
        if arguments.mode == "plan":
            _write_json(
                arguments.projection_output,
                reconciliation.projection_plan.model_dump(mode="json", by_alias=True),
            )
        passed = reconciliation.idempotent if arguments.mode == "check" else reconciliation.safe_to_apply
        result = {
            "schema": RESULT_SCHEMA,
            "mode": arguments.mode,
            "passed": passed,
            "safe_to_apply": reconciliation.safe_to_apply,
            "idempotent": reconciliation.idempotent,
            "change_count": reconciliation.projection_plan.change_count,
            "duplicate_project_count": len(reconciliation.projection_plan.duplicate_project_ids),
            "unbound_card_count": len(reconciliation.projection_plan.unbound_card_ids),
            "privacy_findings_count": len(reconciliation.privacy_findings),
            "projection_plan_sha256": hashlib.sha256(
                rfc8785.dumps(
                    reconciliation.projection_plan.model_dump(
                        mode="json",
                        by_alias=True,
                    )
                )
            ).hexdigest(),
        }
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        result = {
            "schema": RESULT_SCHEMA,
            "mode": arguments.mode,
            "passed": False,
            "reason": type(exc).__name__,
        }
        if arguments.mode == "plan" and arguments.projection_output is not None:
            _write_json(arguments.projection_output, result)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
