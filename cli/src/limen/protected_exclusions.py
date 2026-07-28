"""Fail-closed protected-root contracts for reconciliation and reclamation.

Protected exclusions are repository-owned declarations.  Their tracked form is
repo-relative and contains no home-directory path.  Runtime consumers resolve
the declaration against the exact repository root and publish only digests.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rfc8785

REGISTRY_SCHEMA = "limen.reconciliation_protected_exclusions.v1"
PROJECTION_SCHEMA = "limen.protected_exclusion_projection.v1"


class ProtectedExclusionError(ValueError):
    """The protected-exclusion registry is unavailable or unsafe."""


def _digest(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _relative_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProtectedExclusionError(f"{field}-invalid")
    path = Path(value)
    if path.is_absolute() or path in {Path(), Path(".")} or ".." in path.parts:
        raise ProtectedExclusionError(f"{field}-must-be-safe-relative")
    return path


def _bounded_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or value.strip() != value or "\x00" in value:
        raise ProtectedExclusionError(f"{field}-invalid")
    return value


def paths_overlap(left: Path, right: Path) -> bool:
    """Return true when either resolved path contains the other."""

    left = left.resolve(strict=False)
    right = right.resolve(strict=False)
    return left == right or left in right.parents or right in left.parents


@dataclass(frozen=True)
class ProtectedExclusion:
    exclusion_id: str
    owner: str
    path: Path
    branch: str
    registration: Path
    blocks_omega: bool
    reason: str

    @classmethod
    def from_payload(cls, payload: object) -> ProtectedExclusion:
        if not isinstance(payload, dict):
            raise ProtectedExclusionError("exclusion-must-be-object")
        expected = {
            "exclusion_id",
            "owner",
            "path",
            "branch",
            "registration",
            "blocks_omega",
            "reason",
        }
        if set(payload) != expected:
            raise ProtectedExclusionError("exclusion-fields-mismatch")
        if not isinstance(payload["blocks_omega"], bool):
            raise ProtectedExclusionError("blocks-omega-invalid")
        return cls(
            exclusion_id=_bounded_text(payload["exclusion_id"], "exclusion-id"),
            owner=_bounded_text(payload["owner"], "owner"),
            path=_relative_path(payload["path"], "path"),
            branch=_bounded_text(payload["branch"], "branch"),
            registration=_relative_path(payload["registration"], "registration"),
            blocks_omega=payload["blocks_omega"],
            reason=_bounded_text(payload["reason"], "reason"),
        )

    def resolved_path(self, repository_root: Path) -> Path:
        return (repository_root.resolve(strict=True) / self.path).resolve(strict=False)

    def resolved_registration(self, repository_root: Path) -> Path:
        return (repository_root.resolve(strict=True) / self.registration).resolve(strict=False)

    def projection(self, repository_root: Path) -> dict[str, object]:
        resolved_path = self.resolved_path(repository_root)
        resolved_registration = self.resolved_registration(repository_root)
        payload: dict[str, object] = {
            "schema": PROJECTION_SCHEMA,
            "exclusion_id": self.exclusion_id,
            "owner": self.owner,
            "path_sha256": hashlib.sha256(str(resolved_path).encode()).hexdigest(),
            "branch_sha256": hashlib.sha256(self.branch.encode()).hexdigest(),
            "registration_sha256": hashlib.sha256(str(resolved_registration).encode()).hexdigest(),
            "blocks_omega": self.blocks_omega,
            "reason": self.reason,
            "path_exists": resolved_path.exists(),
            "registration_exists": resolved_registration.exists(),
        }
        return {**payload, "projection_sha256": _digest(payload)}


@dataclass(frozen=True)
class ProtectedExclusionRegistry:
    repository_root: Path
    exclusions: tuple[ProtectedExclusion, ...]
    registry_digest: str

    @classmethod
    def load(
        cls,
        repository_root: Path,
        registry_path: Path | None = None,
    ) -> ProtectedExclusionRegistry:
        try:
            root = repository_root.resolve(strict=True)
        except OSError as exc:
            raise ProtectedExclusionError("protected-exclusion-repository-root-unavailable") from exc
        path = registry_path or (root / "institutio" / "governance" / "reconciliation-protected-exclusions.json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProtectedExclusionError("protected-exclusion-registry-unavailable") from exc
        if not isinstance(payload, dict) or set(payload) != {"schema", "exclusions"}:
            raise ProtectedExclusionError("protected-exclusion-registry-fields-mismatch")
        if payload["schema"] != REGISTRY_SCHEMA or not isinstance(payload["exclusions"], list):
            raise ProtectedExclusionError("protected-exclusion-registry-schema-mismatch")
        exclusions = tuple(ProtectedExclusion.from_payload(item) for item in payload["exclusions"])
        identifiers = [item.exclusion_id for item in exclusions]
        branches = [item.branch for item in exclusions]
        paths = [item.path for item in exclusions]
        if len(identifiers) != len(set(identifiers)):
            raise ProtectedExclusionError("duplicate-exclusion-id")
        if len(branches) != len(set(branches)):
            raise ProtectedExclusionError("duplicate-protected-branch")
        if len(paths) != len(set(paths)):
            raise ProtectedExclusionError("duplicate-protected-path")
        return cls(
            repository_root=root,
            exclusions=tuple(sorted(exclusions, key=lambda item: item.exclusion_id)),
            registry_digest=_digest(payload),
        )

    @classmethod
    def from_exclusions(
        cls,
        repository_root: Path,
        exclusions: Iterable[ProtectedExclusion],
    ) -> ProtectedExclusionRegistry:
        root = repository_root.resolve(strict=True)
        ordered = tuple(sorted(exclusions, key=lambda item: item.exclusion_id))
        payload = {
            "schema": REGISTRY_SCHEMA,
            "exclusions": [
                {
                    "exclusion_id": item.exclusion_id,
                    "owner": item.owner,
                    "path": item.path.as_posix(),
                    "branch": item.branch,
                    "registration": item.registration.as_posix(),
                    "blocks_omega": item.blocks_omega,
                    "reason": item.reason,
                }
                for item in ordered
            ],
        }
        return cls(root, ordered, _digest(payload))

    def match(self, candidate: Path, *, branch: str | None = None) -> str | None:
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            return "protected-exclusion:unresolved-candidate"
        for exclusion in self.exclusions:
            if paths_overlap(resolved, exclusion.resolved_path(self.repository_root)):
                return f"protected-exclusion:{exclusion.exclusion_id}:path-overlap"
            if paths_overlap(
                resolved,
                exclusion.resolved_registration(self.repository_root),
            ):
                return f"protected-exclusion:{exclusion.exclusion_id}:registration-overlap"
            if branch and branch == exclusion.branch:
                return f"protected-exclusion:{exclusion.exclusion_id}:branch-match"
        return None

    def projection(self) -> dict[str, Any]:
        entries = [item.projection(self.repository_root) for item in self.exclusions]
        payload: dict[str, Any] = {
            "schema": "limen.protected_exclusion_registry_projection.v1",
            "registry_digest": self.registry_digest,
            "protected_exclusions": entries,
            "omega_blocker_count": sum(1 for item in self.exclusions if item.blocks_omega),
        }
        return {**payload, "projection_sha256": _digest(payload)}
