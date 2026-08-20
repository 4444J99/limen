"""Fail-closed, read-only evaluation of the Prima Materia universe fixed point."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import rfc8785
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from limen.prima_materia import (
    CollaboratorUniverseManifestV1,
    ProjectUniverseManifestV1,
    UniverseSourceRegistryV1,
)

AUDIT_SCHEMA: Literal["limen.prima_materia_universe_audit.v1"] = "limen.prima_materia_universe_audit.v1"
GITHUB_PLAN_SCHEMA: Literal["limen.prima_materia_github_projection_plan.v1"] = (
    "limen.prima_materia_github_projection_plan.v1"
)
DEFAULT_MAX_AGE_SECONDS = 3600
CHECKS = (
    "all-canonical-projects-built",
    "canonical-project-coverage-complete",
    "collaborator-universe-reconciled",
    "github-projection-idempotent",
    "privacy-safe-projection",
    "source-coverage-complete",
)
_DIGEST = str


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _validate_git_sha(value: str) -> str:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("installed runtime SHA must be a full lowercase SHA-1")
    return value


def _validate_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value.astimezone(UTC)


def _validate_sorted_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} must be sorted")


def canonical_digest(value: BaseModel) -> str:
    return hashlib.sha256(rfc8785.dumps(value.model_dump(mode="json", by_alias=True))).hexdigest()


class GitHubProjectionPlanV1(BaseModel):
    """Privacy-safe output from a read-only GitHub Project reconciliation plan."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_id: Literal["limen.prima_materia_github_projection_plan.v1"] = Field(
        default=GITHUB_PLAN_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    observed_at: datetime
    frozen_wave_sha256: _DIGEST
    installed_runtime_sha: str
    source_registry_sha256: _DIGEST
    project_manifest_sha256: _DIGEST
    collaborator_manifest_sha256: _DIGEST
    project_owner: Literal["4444J99"]
    project_marker: Literal["organvm-universe:v1"]
    change_count: int = Field(ge=0)
    duplicate_project_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=4096)
    unbound_card_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100_000)
    privacy_findings_count: int = Field(ge=0)
    github_read_receipt_sha256: _DIGEST
    privacy_receipt_sha256: _DIGEST

    _observed = field_validator("observed_at")(_validate_aware)
    _runtime = field_validator("installed_runtime_sha")(_validate_git_sha)
    _digests = field_validator(
        "frozen_wave_sha256",
        "source_registry_sha256",
        "project_manifest_sha256",
        "collaborator_manifest_sha256",
        "github_read_receipt_sha256",
        "privacy_receipt_sha256",
    )(_validate_digest)

    @model_validator(mode="after")
    def identifiers_are_canonical(self) -> GitHubProjectionPlanV1:
        _validate_sorted_unique(self.duplicate_project_ids, "duplicate project identities")
        _validate_sorted_unique(self.unbound_card_ids, "unbound card identities")
        return self


def _runtime_sha(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    receipt = payload.get("receipt")
    if not isinstance(receipt, dict):
        return None
    value = receipt.get("sha")
    if not isinstance(value, str):
        return None
    try:
        return _validate_git_sha(value)
    except ValueError:
        return None


def _fresh(observed_at: datetime, now: datetime, max_age_seconds: int) -> bool:
    return observed_at <= now + timedelta(seconds=60) and now - observed_at <= timedelta(seconds=max_age_seconds)


def evaluate_universe_check(
    *,
    check: str,
    frozen_wave_sha256: str,
    installed_runtime_sha: str,
    runtime_status: Any,
    source_registry: UniverseSourceRegistryV1,
    project_manifest: ProjectUniverseManifestV1,
    collaborator_manifest: CollaboratorUniverseManifestV1,
    github_plan: GitHubProjectionPlanV1 | None,
    observed_at: datetime,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Return a bounded, privacy-safe result for one registered universe predicate."""

    if check not in CHECKS:
        raise ValueError("unknown universe check")
    _validate_digest(frozen_wave_sha256)
    _validate_git_sha(installed_runtime_sha)
    observed_at = _validate_aware(observed_at)
    if not 1 <= max_age_seconds <= 604_800:
        raise ValueError("max age must be between 1 and 604800 seconds")

    source_registry_sha256 = source_registry.canonical_digest
    project_manifest_sha256 = canonical_digest(project_manifest)
    collaborator_manifest_sha256 = canonical_digest(collaborator_manifest)
    project_ids = tuple(project.project_id for project in project_manifest.projects)

    bindings = {
        "runtime_exact": _runtime_sha(runtime_status) == installed_runtime_sha,
        "project_wave_exact": project_manifest.frozen_wave_digest == frozen_wave_sha256,
        "collaborator_wave_exact": collaborator_manifest.frozen_wave_digest == frozen_wave_sha256,
        "project_source_registry_exact": project_manifest.source_registry_digest == source_registry_sha256,
        "collaborator_source_registry_exact": (collaborator_manifest.source_registry_digest == source_registry_sha256),
        "collaborator_project_manifest_exact": (
            collaborator_manifest.project_universe_manifest_digest == project_manifest_sha256
        ),
        "collaborator_project_denominator_exact": collaborator_manifest.project_ids == project_ids,
    }
    base_exact = all(bindings.values())

    source_coverage = (
        base_exact and project_manifest.source_coverage_complete and collaborator_manifest.source_coverage_complete
    )
    canonical_projects = source_coverage and project_manifest.canonical_project_coverage_complete
    all_projects_built = canonical_projects and project_manifest.all_canonical_projects_built
    collaborators_reconciled = (
        canonical_projects and collaborator_manifest.reconciled and collaborator_manifest.collaborator_coverage_complete
    )

    plan_bindings = {
        "available": github_plan is not None,
        "fresh": bool(github_plan is not None and _fresh(github_plan.observed_at, observed_at, max_age_seconds)),
        "wave_exact": bool(github_plan is not None and github_plan.frozen_wave_sha256 == frozen_wave_sha256),
        "runtime_exact": bool(github_plan is not None and github_plan.installed_runtime_sha == installed_runtime_sha),
        "source_registry_exact": bool(
            github_plan is not None and github_plan.source_registry_sha256 == source_registry_sha256
        ),
        "project_manifest_exact": bool(
            github_plan is not None and github_plan.project_manifest_sha256 == project_manifest_sha256
        ),
        "collaborator_manifest_exact": bool(
            github_plan is not None and github_plan.collaborator_manifest_sha256 == collaborator_manifest_sha256
        ),
    }
    plan_exact = all(plan_bindings.values())
    privacy_safe = (
        collaborators_reconciled and plan_exact and github_plan is not None and github_plan.privacy_findings_count == 0
    )
    github_idempotent = (
        all_projects_built
        and collaborators_reconciled
        and privacy_safe
        and github_plan is not None
        and github_plan.change_count == 0
        and not github_plan.duplicate_project_ids
        and not github_plan.unbound_card_ids
    )

    predicates = {
        "source-coverage-complete": source_coverage,
        "canonical-project-coverage-complete": canonical_projects,
        "all-canonical-projects-built": all_projects_built,
        "collaborator-universe-reconciled": collaborators_reconciled,
        "privacy-safe-projection": privacy_safe,
        "github-projection-idempotent": github_idempotent,
    }
    return {
        "schema": AUDIT_SCHEMA,
        "check": check,
        "passed": predicates[check],
        "bindings": bindings,
        "github_plan": plan_bindings,
        "frozen_wave_sha256": frozen_wave_sha256,
        "installed_runtime_sha": installed_runtime_sha,
        "source_registry_sha256": source_registry_sha256,
        "project_manifest_sha256": project_manifest_sha256,
        "collaborator_manifest_sha256": collaborator_manifest_sha256,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _live_runtime_status() -> Any:
    result = subprocess.run(
        ["domus-limen-runtime", "status"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise ValueError("installed runtime status is unavailable")
    return json.loads(result.stdout)


def parser(root: Path) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--check", required=True, choices=CHECKS)
    result.add_argument("--frozen-wave-sha", required=True)
    result.add_argument("--installed-runtime-sha", required=True)
    result.add_argument(
        "--source-registry",
        type=Path,
        default=root / "institutio" / "governance" / "prima-materia-universe-sources.json",
    )
    result.add_argument(
        "--project-manifest",
        type=Path,
        default=root / "logs" / "prima-materia-universe" / "project-universe.json",
    )
    result.add_argument(
        "--collaborator-manifest",
        type=Path,
        default=root / "logs" / "prima-materia-universe" / "collaborator-universe.json",
    )
    result.add_argument(
        "--github-plan",
        type=Path,
        default=root / "logs" / "prima-materia-universe" / "github-project-plan.json",
    )
    result.add_argument(
        "--runtime-status-file",
        type=Path,
        help="Fixture/attested status input; omitted in registered live predicates.",
    )
    result.add_argument("--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS)
    return result


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    repository_root = root or Path(__file__).resolve().parents[3]
    arguments = parser(repository_root).parse_args(argv)
    try:
        source_registry = UniverseSourceRegistryV1.model_validate_json(
            arguments.source_registry.read_text(encoding="utf-8")
        )
        project_manifest = ProjectUniverseManifestV1.model_validate_json(
            arguments.project_manifest.read_text(encoding="utf-8")
        )
        collaborator_manifest = CollaboratorUniverseManifestV1.model_validate_json(
            arguments.collaborator_manifest.read_text(encoding="utf-8")
        )
        github_plan = GitHubProjectionPlanV1.model_validate_json(arguments.github_plan.read_text(encoding="utf-8"))
        runtime_status = (
            _read_json(arguments.runtime_status_file)
            if arguments.runtime_status_file is not None
            else _live_runtime_status()
        )
        result = evaluate_universe_check(
            check=arguments.check,
            frozen_wave_sha256=arguments.frozen_wave_sha,
            installed_runtime_sha=arguments.installed_runtime_sha,
            runtime_status=runtime_status,
            source_registry=source_registry,
            project_manifest=project_manifest,
            collaborator_manifest=collaborator_manifest,
            github_plan=github_plan,
            observed_at=datetime.now(UTC),
            max_age_seconds=arguments.max_age_seconds,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        result = {
            "schema": AUDIT_SCHEMA,
            "check": arguments.check,
            "passed": False,
            "reason": type(exc).__name__,
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["passed"] is True else 1


if __name__ == "__main__":
    sys.exit(main())
