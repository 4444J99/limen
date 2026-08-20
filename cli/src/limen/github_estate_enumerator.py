"""Live, privacy-safe GitHub estate snapshots and universe enumeration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import rfc8785
from pydantic import Field, field_validator, model_validator

from limen.prima_materia import PrimaMateriaModel
from limen.universe_adapter_runner import (
    Dimension,
    UniverseCensusFragmentV1,
    UniverseCollaboratorFragmentV1,
    UniverseCollaboratorInstanceFragmentV1,
    UniverseProjectFragmentV1,
    UniverseProjectInstanceFragmentV1,
)
from limen.universe_freezer import UniverseSourceInstanceExpectationV1

SOURCE_KIND: Literal["github_estate"] = "github_estate"
OWNER_REF: Literal["institutio/github/estate.yaml"] = "institutio/github/estate.yaml"
SNAPSHOT_REF: Literal["docs/github-universe-snapshot.json"] = "docs/github-universe-snapshot.json"
CONTEXT_SCHEMA: Literal["limen.universe_enumerator_context.v1"] = "limen.universe_enumerator_context.v1"
SNAPSHOT_SCHEMA: Literal["limen.github_estate_source_snapshot.v1"] = "limen.github_estate_source_snapshot.v1"
PROJECT_MARKER = "organvm-universe:v1"
MAX_API_OUTPUT_BYTES = 32 * 1024 * 1024
AccessLevel = Literal["read", "triage", "write", "maintain", "admin", "unknown"]
AccessStatus = Literal["active", "pending"]
ApiJson = Callable[[tuple[str, ...]], Any]


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _digest_payload(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _opaque(prefix: str, value: Any) -> str:
    return f"{prefix}{_digest_payload(value)[:24]}"


def _repository_identity(full_name: str) -> str:
    return _opaque("repositoryIdentifier", {"repository": full_name})


def _login_digest(login: str) -> str:
    return hashlib.sha256(login.strip().lower().encode()).hexdigest()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value.astimezone(UTC)


class GitHubEstateContextV1(PrimaMateriaModel):
    context_schema: Literal["limen.universe_enumerator_context.v1"] = Field(
        default=CONTEXT_SCHEMA,
        alias="schema",
    )
    dimension: Dimension
    source_kind: Literal["github_estate"] = SOURCE_KIND
    owner_ref: Literal["institutio/github/estate.yaml"] = OWNER_REF
    completeness_predicate: str = Field(min_length=1, max_length=4096)
    privacy_projection_ref: str = Field(min_length=1, max_length=256)
    frozen_wave_sha256: str
    source_registry_sha256: str
    frozen_at: datetime
    custody_receipt_sha256: str | None = None

    _digests = field_validator(
        "frozen_wave_sha256",
        "source_registry_sha256",
    )(_validate_digest)
    _custody = field_validator("custody_receipt_sha256")(
        lambda value: _validate_digest(value) if value is not None else None
    )
    _frozen = field_validator("frozen_at")(_aware_utc)


class GitHubEstateAccessRowV1(PrimaMateriaModel):
    repository_id: str
    github_login_sha256: str
    access_level: AccessLevel
    status: AccessStatus

    _login = field_validator("github_login_sha256")(_validate_digest)


class GitHubEstateSourceSnapshotV1(PrimaMateriaModel):
    schema_version: Literal["limen.github_estate_source_snapshot.v1"] = SNAPSHOT_SCHEMA
    observed_at: datetime
    repository_owner_sha256: str
    project_owner_sha256: str
    repository_enumeration_complete: bool
    collaborator_enumeration_complete: bool
    project_enumeration_complete: bool
    project_scope_available: bool
    repository_ids: tuple[str, ...] = Field(max_length=100_000)
    access_rows: tuple[GitHubEstateAccessRowV1, ...] = Field(max_length=1_000_000)
    project_row_ids: tuple[str, ...] = Field(max_length=100_000)
    repository_debt_ids: tuple[str, ...] = Field(max_length=100_000)
    collaborator_debt_ids: tuple[str, ...] = Field(max_length=1_000_000)
    project_debt_ids: tuple[str, ...] = Field(max_length=100_000)
    github_read_receipt_sha256: str

    _observed = field_validator("observed_at")(_aware_utc)
    _digests = field_validator(
        "repository_owner_sha256",
        "project_owner_sha256",
        "github_read_receipt_sha256",
    )(_validate_digest)

    @model_validator(mode="after")
    def evidence_is_canonical(self) -> GitHubEstateSourceSnapshotV1:
        for label, values in (
            ("repository identities", self.repository_ids),
            ("Project row identities", self.project_row_ids),
            ("repository debt", self.repository_debt_ids),
            ("collaborator debt", self.collaborator_debt_ids),
            ("Project debt", self.project_debt_ids),
        ):
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise ValueError(f"{label} must be sorted and unique")
        access_keys = tuple((item.repository_id, item.github_login_sha256, item.status) for item in self.access_rows)
        if access_keys != tuple(sorted(access_keys)) or len(access_keys) != len(set(access_keys)):
            raise ValueError("GitHub access rows must be sorted and unique")
        if self.repository_enumeration_complete != (not self.repository_debt_ids):
            raise ValueError("repository completeness must match its debt")
        if self.collaborator_enumeration_complete != (
            self.repository_enumeration_complete and not self.collaborator_debt_ids
        ):
            raise ValueError("collaborator completeness must match repository coverage and debt")
        if self.project_enumeration_complete != (not self.project_debt_ids):
            raise ValueError("Project completeness must match its debt")
        payload = self.model_dump(mode="json", exclude={"github_read_receipt_sha256"})
        if self.github_read_receipt_sha256 != _digest_payload(payload):
            raise ValueError("GitHub read receipt does not bind the snapshot")
        return self


class GitHubReadError(RuntimeError):
    """A bounded GitHub read failed without carrying provider output."""


def _gh_json(arguments: tuple[str, ...], *, timeout_seconds: int = 45) -> Any:
    environment = {key: value for key, value in os.environ.items() if key not in {"GH_TOKEN", "GITHUB_TOKEN"}}
    try:
        process = subprocess.run(
            ("gh", *arguments),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            stdin=subprocess.DEVNULL,
            env=environment,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitHubReadError(type(exc).__name__) from None
    if process.returncode != 0:
        raise GitHubReadError("github-api-read-failed")
    if len(process.stdout.encode()) > MAX_API_OUTPUT_BYTES:
        raise GitHubReadError("github-api-output-limit")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        raise GitHubReadError("github-api-invalid-json") from None


def _pages(api_json: ApiJson, endpoint: str) -> list[dict[str, Any]]:
    value = api_json(("api", "--paginate", "--slurp", endpoint))
    if not isinstance(value, list):
        raise GitHubReadError("github-api-page-shape")
    rows: list[dict[str, Any]] = []
    for page in value:
        if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
            raise GitHubReadError("github-api-row-shape")
        rows.extend(page)
    return rows


def _access_level(value: Any) -> AccessLevel:
    aliases: dict[str, AccessLevel] = {
        "pull": "read",
        "read": "read",
        "triage": "triage",
        "push": "write",
        "write": "write",
        "maintain": "maintain",
        "admin": "admin",
    }
    return aliases.get(str(value or "").lower(), "unknown")


def _collect_repository_access(
    full_name: str,
    *,
    api_json: ApiJson,
) -> tuple[str, tuple[GitHubEstateAccessRowV1, ...], tuple[str, ...]]:
    repository_id = _repository_identity(full_name)
    rows: list[GitHubEstateAccessRowV1] = []
    debt: list[str] = []
    surfaces = (
        (
            "outside",
            f"/repos/{full_name}/collaborators?affiliation=outside&per_page=100",
            "active",
        ),
        (
            "invitations",
            f"/repos/{full_name}/invitations?per_page=100",
            "pending",
        ),
    )
    for surface, endpoint, status in surfaces:
        try:
            observations = _pages(api_json, endpoint)
        except GitHubReadError:
            debt.append(
                _opaque(
                    "githubCollaboratorDebt",
                    {"repository_id": repository_id, "surface": surface},
                )
            )
            continue
        for observation in observations:
            login = observation.get("login") if status == "active" else (observation.get("invitee") or {}).get("login")
            level = _access_level(
                observation.get("role_name") if status == "active" else observation.get("permissions")
            )
            if not isinstance(login, str) or not login.strip():
                debt.append(
                    _opaque(
                        "githubCollaboratorDebt",
                        {
                            "repository_id": repository_id,
                            "surface": surface,
                            "reason": "missing-login",
                            "row_sha256": _digest_payload(observation),
                        },
                    )
                )
                continue
            status_literal: AccessStatus = "active" if status == "active" else "pending"
            row = GitHubEstateAccessRowV1(
                repository_id=repository_id,
                github_login_sha256=_login_digest(login),
                access_level=level,
                status=status_literal,
            )
            if level == "unknown":
                debt.append(
                    _opaque(
                        "githubCollaboratorDebt",
                        {
                            "repository_id": repository_id,
                            "github_login_sha256": row.github_login_sha256,
                            "surface": surface,
                            "reason": "unknown-access-level",
                        },
                    )
                )
            rows.append(row)
    grouped: dict[tuple[str, str, AccessStatus], set[AccessLevel]] = {}
    for row in rows:
        key = (row.repository_id, row.github_login_sha256, row.status)
        grouped.setdefault(key, set()).add(row.access_level)
    canonical: list[GitHubEstateAccessRowV1] = []
    for key, levels in sorted(grouped.items()):
        if len(levels) != 1:
            debt.append(
                _opaque(
                    "githubCollaboratorDebt",
                    {
                        "repository_id": key[0],
                        "github_login_sha256": key[1],
                        "status": key[2],
                        "reason": "conflicting-access-levels",
                        "levels": sorted(levels),
                    },
                )
            )
            continue
        canonical.append(
            GitHubEstateAccessRowV1(
                repository_id=key[0],
                github_login_sha256=key[1],
                status=key[2],
                access_level=next(iter(levels)),
            )
        )
    return repository_id, tuple(canonical), tuple(sorted(set(debt)))


def _project_rows(
    *,
    project_owner: str,
    api_json: ApiJson,
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    query = """
query($endCursor: String) {
  user(login: $PROJECT_OWNER) {
    projectsV2(first: 100, after: $endCursor) {
      nodes { id title shortDescription readme }
      pageInfo { hasNextPage endCursor }
    }
  }
}
""".replace("$PROJECT_OWNER", json.dumps(project_owner))
    try:
        pages = api_json(
            (
                "api",
                "graphql",
                "--paginate",
                "--slurp",
                "-f",
                f"query={query}",
            )
        )
    except GitHubReadError:
        return (
            False,
            (),
            (
                _opaque(
                    "githubProjectDebt",
                    {"surface": "user-projects-v2", "reason": "unavailable"},
                ),
            ),
        )
    if not isinstance(pages, list):
        raise GitHubReadError("github-project-page-shape")
    row_ids: list[str] = []
    debt: list[str] = []
    for page in pages:
        try:
            projects = page["data"]["user"]["projectsV2"]["nodes"]
        except (KeyError, TypeError):
            raise GitHubReadError("github-project-row-shape") from None
        if not isinstance(projects, list):
            raise GitHubReadError("github-project-row-shape")
        for project in projects:
            if not isinstance(project, dict) or not isinstance(project.get("id"), str):
                debt.append(
                    _opaque(
                        "githubProjectDebt",
                        {"surface": "user-projects-v2", "reason": "invalid-project-row"},
                    )
                )
                continue
            marker_bound = PROJECT_MARKER in (f"{project.get('shortDescription') or ''}\n{project.get('readme') or ''}")
            row_ids.append(
                _opaque(
                    "githubProjectRow",
                    {
                        "node_id": project["id"],
                        "marker_bound": marker_bound,
                    },
                )
            )
    debt.append(
        _opaque(
            "githubProjectDebt",
            {"surface": "user-project-items-and-members", "reason": "enumerator-unimplemented"},
        )
    )
    return True, tuple(sorted(set(row_ids))), tuple(sorted(set(debt)))


def collect_github_estate_snapshot(
    *,
    repository_owner: str,
    project_owner: str,
    observed_at: datetime,
    api_json: ApiJson = _gh_json,
    max_repositories: int = 2000,
    workers: int = 8,
) -> GitHubEstateSourceSnapshotV1:
    observed_at = _aware_utc(observed_at)
    if not 1 <= max_repositories <= 10_000:
        raise ValueError("max_repositories must be between 1 and 10000")
    if not 1 <= workers <= 16:
        raise ValueError("workers must be between 1 and 16")
    repository_debt: list[str] = []
    collaborator_debt: list[str] = []
    try:
        repository_rows = _pages(
            api_json,
            f"/orgs/{repository_owner}/repos?type=all&per_page=100",
        )
    except GitHubReadError:
        repository_rows = []
        repository_debt.append(
            _opaque(
                "githubRepositoryDebt",
                {"surface": "organization-repositories", "reason": "unavailable"},
            )
        )
    if len(repository_rows) > max_repositories:
        repository_debt.append(
            _opaque(
                "githubRepositoryDebt",
                {
                    "surface": "organization-repositories",
                    "reason": "repository-limit",
                    "observed_count": len(repository_rows),
                },
            )
        )
        repository_rows = []
    if not repository_rows and not repository_debt:
        repository_debt.append(
            _opaque(
                "githubRepositoryDebt",
                {"surface": "organization-repositories", "reason": "empty-census"},
            )
        )

    full_names: list[str] = []
    for row in repository_rows:
        full_name = row.get("full_name")
        if not isinstance(full_name, str) or not full_name.startswith(f"{repository_owner}/"):
            repository_debt.append(
                _opaque(
                    "githubRepositoryDebt",
                    {
                        "surface": "organization-repositories",
                        "reason": "invalid-repository-row",
                        "row_sha256": _digest_payload(row),
                    },
                )
            )
            continue
        full_names.append(full_name)
    if len(full_names) != len(set(full_names)):
        repository_debt.append(
            _opaque(
                "githubRepositoryDebt",
                {"surface": "organization-repositories", "reason": "duplicate-repository"},
            )
        )
    full_names = sorted(set(full_names))

    access_rows: list[GitHubEstateAccessRowV1] = []
    if not repository_debt:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _collect_repository_access,
                    full_name,
                    api_json=api_json,
                ): full_name
                for full_name in full_names
            }
            for future in as_completed(futures):
                full_name = futures[future]
                try:
                    _repository_id, rows, debt = future.result()
                except (GitHubReadError, OSError, TypeError, ValueError):
                    collaborator_debt.append(
                        _opaque(
                            "githubCollaboratorDebt",
                            {
                                "repository_id": _repository_identity(full_name),
                                "surface": "repository-access",
                                "reason": "worker-failed",
                            },
                        )
                    )
                    continue
                access_rows.extend(rows)
                collaborator_debt.extend(debt)
    else:
        collaborator_debt.append(
            _opaque(
                "githubCollaboratorDebt",
                {"surface": "repository-access", "reason": "repository-census-incomplete"},
            )
        )

    project_scope_available, project_row_ids, project_debt = _project_rows(
        project_owner=project_owner,
        api_json=api_json,
    )
    payload: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA,
        "observed_at": observed_at,
        "repository_owner_sha256": hashlib.sha256(repository_owner.encode()).hexdigest(),
        "project_owner_sha256": hashlib.sha256(project_owner.encode()).hexdigest(),
        "repository_enumeration_complete": not repository_debt,
        "collaborator_enumeration_complete": not repository_debt and not collaborator_debt,
        "project_enumeration_complete": not project_debt,
        "project_scope_available": project_scope_available,
        "repository_ids": tuple(sorted(_repository_identity(value) for value in full_names)),
        "access_rows": tuple(
            sorted(
                access_rows,
                key=lambda item: (
                    item.repository_id,
                    item.github_login_sha256,
                    item.status,
                ),
            )
        ),
        "project_row_ids": project_row_ids,
        "repository_debt_ids": tuple(sorted(set(repository_debt))),
        "collaborator_debt_ids": tuple(sorted(set(collaborator_debt))),
        "project_debt_ids": project_debt,
    }
    receipt_payload = {
        **payload,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "access_rows": tuple(item.model_dump(mode="json") for item in payload["access_rows"]),
    }
    payload["github_read_receipt_sha256"] = _digest_payload(receipt_payload)
    return GitHubEstateSourceSnapshotV1.model_validate(payload)


def _source_instance(surface: str) -> str:
    return _opaque(
        "sourceInstanceGitHubEstate",
        {"owner_ref": OWNER_REF, "surface": surface},
    )


def enumerate_github_estate(
    *,
    dimension: Dimension,
    context: GitHubEstateContextV1,
    snapshot_path: Path,
) -> dict[str, Any]:
    if context.dimension != dimension:
        raise ValueError("requested dimension does not match the enumerator context")
    snapshot = GitHubEstateSourceSnapshotV1.model_validate_json(snapshot_path.read_text())
    if snapshot.observed_at > context.frozen_at:
        raise ValueError("GitHub snapshot is newer than the frozen wave")
    repository_instance = _source_instance("repositories")
    collaborator_instance = _source_instance("collaborators")
    project_instance = _source_instance("projects")
    repository_rows = tuple(
        sorted(
            _opaque("githubRepositoryRow", {"repository_id": repository_id})
            for repository_id in snapshot.repository_ids
        )
    )
    collaborator_rows = tuple(
        sorted(_opaque("githubAccessRow", row.model_dump(mode="json")) for row in snapshot.access_rows)
    )
    project_rows = tuple(
        sorted(
            _opaque("githubProjectObservationRow", {"project_row_id": row_id}) for row_id in snapshot.project_row_ids
        )
    )
    receipt_ref = _opaque(
        f"githubEstate{dimension.title()}Receipt",
        {
            "dimension": dimension,
            "github_read_receipt_sha256": snapshot.github_read_receipt_sha256,
            "frozen_wave_sha256": context.frozen_wave_sha256,
        },
    )
    observed_at = snapshot.observed_at
    fragment: UniverseCensusFragmentV1 | UniverseProjectFragmentV1 | UniverseCollaboratorFragmentV1
    if dimension == "census":
        fragment = UniverseCensusFragmentV1(
            source_kind=SOURCE_KIND,
            observed_at=observed_at,
            enumeration_complete=True,
            receipt_ref=receipt_ref,
            source_instances=tuple(
                UniverseSourceInstanceExpectationV1(
                    source_instance_id=_source_instance(surface),
                    source_kind=SOURCE_KIND,
                    owner_receipt_ref=_opaque(
                        "githubEstateSourceReceipt",
                        {
                            "surface": surface,
                            "github_read_receipt_sha256": snapshot.github_read_receipt_sha256,
                        },
                    ),
                )
                for surface in ("repositories", "collaborators", "projects")
            ),
        )
    elif dimension == "project":
        repository_debt = tuple(sorted(set(repository_rows) | set(snapshot.repository_debt_ids)))
        collaborator_debt = tuple(sorted(set(collaborator_rows) | set(snapshot.collaborator_debt_ids)))
        project_debt = tuple(sorted(set(project_rows) | set(snapshot.project_debt_ids)))
        fragment = UniverseProjectFragmentV1(
            source_kind=SOURCE_KIND,
            observed_at=observed_at,
            enumeration_complete=not (repository_debt or collaborator_debt or project_debt),
            receipt_ref=receipt_ref,
            instances=(
                UniverseProjectInstanceFragmentV1(
                    source_instance_id=repository_instance,
                    required_project_ids=(),
                    projects=(),
                    unclassified_row_ids=repository_debt,
                ),
                UniverseProjectInstanceFragmentV1(
                    source_instance_id=collaborator_instance,
                    required_project_ids=(),
                    projects=(),
                    unclassified_row_ids=collaborator_debt,
                ),
                UniverseProjectInstanceFragmentV1(
                    source_instance_id=project_instance,
                    required_project_ids=(),
                    projects=(),
                    unclassified_row_ids=project_debt,
                ),
            ),
        )
    else:
        collaborator_debt = tuple(sorted(set(collaborator_rows) | set(snapshot.collaborator_debt_ids)))
        fragment = UniverseCollaboratorFragmentV1(
            source_kind=SOURCE_KIND,
            observed_at=observed_at,
            enumeration_complete=not (snapshot.repository_debt_ids or collaborator_debt or snapshot.project_debt_ids),
            receipt_ref=receipt_ref,
            instances=(
                UniverseCollaboratorInstanceFragmentV1(
                    source_instance_id=repository_instance,
                    required_collaborator_ids=(),
                    collaborators=(),
                    reference_only_identity_ids=(),
                    unclassified_row_ids=tuple(sorted(set(repository_rows) | set(snapshot.repository_debt_ids))),
                ),
                UniverseCollaboratorInstanceFragmentV1(
                    source_instance_id=collaborator_instance,
                    required_collaborator_ids=(),
                    collaborators=(),
                    reference_only_identity_ids=(),
                    unclassified_row_ids=collaborator_debt,
                ),
                UniverseCollaboratorInstanceFragmentV1(
                    source_instance_id=project_instance,
                    required_collaborator_ids=(),
                    collaborators=(),
                    reference_only_identity_ids=(),
                    unclassified_row_ids=tuple(sorted(set(project_rows) | set(snapshot.project_debt_ids))),
                ),
            ),
        )
    return fragment.model_dump(mode="json")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("--output", type=Path, required=True)
    snapshot.add_argument("--repository-owner", default="organvm")
    snapshot.add_argument("--project-owner", default="4444J99")
    snapshot.add_argument("--max-repositories", type=int, default=2000)
    snapshot.add_argument("--workers", type=int, default=8)
    snapshot.add_argument("--observed-at")
    enumerate_parser = subparsers.add_parser("enumerate")
    enumerate_parser.add_argument(
        "--dimension",
        choices=("census", "project", "collaborator"),
        required=True,
    )
    enumerate_parser.add_argument("--snapshot", type=Path, default=Path(SNAPSHOT_REF))
    return result


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    arguments = parser().parse_args(argv)
    repository_root = (root or Path(__file__).resolve().parents[3]).resolve()
    try:
        if arguments.command == "snapshot":
            observed_at = datetime.fromisoformat(arguments.observed_at) if arguments.observed_at else datetime.now(UTC)
            snapshot = collect_github_estate_snapshot(
                repository_owner=arguments.repository_owner,
                project_owner=arguments.project_owner,
                observed_at=observed_at,
                max_repositories=arguments.max_repositories,
                workers=arguments.workers,
            )
            output = arguments.output
            if not output.is_absolute():
                output = repository_root / output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
            print(
                json.dumps(
                    {
                        "repository_count": len(snapshot.repository_ids),
                        "access_row_count": len(snapshot.access_rows),
                        "project_row_count": len(snapshot.project_row_ids),
                        "repository_complete": snapshot.repository_enumeration_complete,
                        "collaborator_complete": snapshot.collaborator_enumeration_complete,
                        "project_complete": snapshot.project_enumeration_complete,
                        "project_scope_available": snapshot.project_scope_available,
                        "debt_count": (
                            len(snapshot.repository_debt_ids)
                            + len(snapshot.collaborator_debt_ids)
                            + len(snapshot.project_debt_ids)
                        ),
                        "github_read_receipt_sha256": snapshot.github_read_receipt_sha256,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            return 0

        raw_context = sys.stdin.buffer.read(64 * 1024 + 1)
        if len(raw_context) > 64 * 1024:
            raise ValueError("enumerator context exceeds the bounded protocol")
        context = GitHubEstateContextV1.model_validate_json(raw_context)
        snapshot_path = arguments.snapshot
        if not snapshot_path.is_absolute():
            snapshot_path = repository_root / snapshot_path
        payload = enumerate_github_estate(
            dimension=arguments.dimension,
            context=context,
            snapshot_path=snapshot_path,
        )
    except (
        GitHubReadError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 1
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
