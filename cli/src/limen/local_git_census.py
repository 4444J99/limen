"""Strict local Git-root census for universe recovery.

The lifecycle reaper intentionally scans only armed candidate roots.  This
module owns the wider read-only denominator: every checkout under the configured
workspace roots plus every linked worktree advertised by those repositories.
Absolute paths remain private and the tracked projection is content-addressed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from limen.protected_exclusions import (
    ProtectedExclusionError,
    ProtectedExclusionRegistry,
)
from limen.worktree_roots import (
    WorktreeInventoryError,
    _discover_workspace_checkouts,
    _git_worktree_paths,
)


SCHEMA = "limen.local-git-census.v1"
LOCAL_ROOT_POLICY_SCHEMA = "limen.local_git_root_policies.v1"
_GITHUB_REMOTE = re.compile(
    r"^(?:git@github\.com:|https?://github\.com/|ssh://git@github\.com/)(?P<coordinate>[^/]+/[^/]+?)(?:\.git)?$"
)


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _path_digest(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _git(path: Path, *args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return result.returncode, result.stdout.strip()


def _absolute_git_path(checkout: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = checkout / path
    return path.resolve(strict=False)


def _repository_from_remote(remote: str) -> str | None:
    match = _GITHUB_REMOTE.fullmatch(remote.strip())
    if match is None:
        return None
    return match.group("coordinate")


def _configured_workspace_roots() -> tuple[Path, ...]:
    raw = os.environ.get("LIMEN_RECLAIM_WORKSPACE_ROOTS")
    if raw is None:
        return (Path.home() / "Workspace",)
    return tuple(Path(value).expanduser() for value in raw.split(os.pathsep) if value.strip())


def _load_local_root_policies(
    repository_root: Path,
    workspace_roots: Iterable[Path],
) -> tuple[dict[str, dict[str, Any]], str, int]:
    path = repository_root / "institutio" / "governance" / "local-git-root-policies.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("local-git-root-policy-registry-unavailable") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema", "roots"}:
        raise ValueError("local-git-root-policy-registry-fields-mismatch")
    if payload.get("schema") != LOCAL_ROOT_POLICY_SCHEMA or not isinstance(payload.get("roots"), list):
        raise ValueError("local-git-root-policy-registry-schema-mismatch")
    expected_fields = {
        "policy_id",
        "workspace_relative_path",
        "classification",
        "owner",
        "expected_branch",
        "allow_unborn_head",
        "allow_no_remote",
        "reason",
    }
    policies: dict[str, dict[str, Any]] = {}
    identifiers: set[str] = set()
    relative_paths: set[Path] = set()
    roots = tuple(Path(root).expanduser().resolve(strict=False) for root in workspace_roots)
    if not roots:
        raise ValueError("local-git-root-policy-workspace-roots-empty")
    for value in payload["roots"]:
        if not isinstance(value, dict) or set(value) != expected_fields:
            raise ValueError("local-git-root-policy-fields-mismatch")
        policy_id = value.get("policy_id")
        owner = value.get("owner")
        expected_branch = value.get("expected_branch")
        reason = value.get("reason")
        if not all(isinstance(item, str) and item.strip() == item and item for item in (policy_id, owner, reason)):
            raise ValueError("local-git-root-policy-text-invalid")
        if expected_branch is not None and (not isinstance(expected_branch, str) or not expected_branch):
            raise ValueError("local-git-root-policy-branch-invalid")
        if value.get("classification") != "protected_local_only":
            raise ValueError("local-git-root-policy-classification-invalid")
        if not isinstance(value.get("allow_unborn_head"), bool) or not isinstance(value.get("allow_no_remote"), bool):
            raise ValueError("local-git-root-policy-allowance-invalid")
        relative = Path(str(value.get("workspace_relative_path") or ""))
        if relative.is_absolute() or relative in {Path(), Path(".")} or ".." in relative.parts:
            raise ValueError("local-git-root-policy-path-invalid")
        if policy_id in identifiers or relative in relative_paths:
            raise ValueError("local-git-root-policy-duplicate")
        identifiers.add(policy_id)
        relative_paths.add(relative)
        candidates = [root / relative for root in roots if (root / relative).exists()]
        if len(candidates) > 1:
            raise ValueError("local-git-root-policy-path-ambiguous")
        if candidates:
            policies[str(candidates[0].resolve(strict=False))] = dict(value)
    return policies, _digest(payload), len(payload["roots"])


def _inspect_root(
    path: Path,
    *,
    protections: ProtectedExclusionRegistry | None,
    local_root_policies: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved = path.resolve(strict=False)
    errors: list[str] = []
    local_policy = (local_root_policies or {}).get(str(resolved))

    branch_rc, branch_raw = _git(resolved, "symbolic-ref", "--short", "-q", "HEAD")
    branch: str | None = branch_raw if branch_rc == 0 else None

    head_rc, head_raw = _git(resolved, "rev-parse", "HEAD")
    head: str | None = head_raw
    if head_rc != 0 or len(head_raw) not in {40, 64}:
        unborn_allowed = bool(local_policy and local_policy.get("allow_unborn_head") and branch is not None)
        if not unborn_allowed:
            errors.append("head-unavailable")
        head = None
    if local_policy and local_policy.get("expected_branch") not in {None, branch}:
        errors.append("local-only-branch-mismatch")

    git_dir_rc, git_dir_raw = _git(resolved, "rev-parse", "--absolute-git-dir")
    common_rc, common_raw = _git(resolved, "rev-parse", "--git-common-dir")
    if git_dir_rc != 0 or common_rc != 0 or not git_dir_raw or not common_raw:
        errors.append("git-common-directory-unavailable")
        git_dir = common_dir = None
    else:
        git_dir = _absolute_git_path(resolved, git_dir_raw)
        common_dir = _absolute_git_path(resolved, common_raw)

    remote_rc, remote = _git(resolved, "config", "--get", "remote.origin.url")
    repository = _repository_from_remote(remote) if remote_rc == 0 else None
    if repository is None:
        no_remote_allowed = bool(
            local_policy and local_policy.get("allow_no_remote") and (remote_rc != 0 or not remote)
        )
        if not no_remote_allowed:
            errors.append("repository-identity-unavailable")

    status_rc, status = _git(resolved, "status", "--porcelain=v1", "--untracked-files=all")
    if status_rc != 0:
        errors.append("worktree-status-unavailable")
        dirty = untracked = None
    else:
        status_rows = status.splitlines() if status else []
        dirty = bool(status_rows)
        untracked = any(row.startswith("?? ") for row in status_rows)

    upstream_rc, upstream_raw = _git(
        resolved,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
    )
    upstream: str | None = upstream_raw if upstream_rc == 0 and upstream_raw else None
    ahead: int | None = None
    behind: int | None = None
    if upstream is not None:
        counts_rc, counts = _git(resolved, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        try:
            left, right = counts.split()
            ahead, behind = int(left), int(right)
        except (ValueError, TypeError):
            if counts_rc != 0:
                errors.append("upstream-divergence-unavailable")
    unpushed: bool | None
    if ahead is not None:
        unpushed = ahead > 0
    elif branch and head:
        remote_ref = f"refs/remotes/origin/{branch}"
        remote_ref_rc, remote_head = _git(resolved, "rev-parse", "--verify", remote_ref)
        if remote_ref_rc == 0 and remote_head:
            ancestor_rc, _ = _git(resolved, "merge-base", "--is-ancestor", head, remote_head)
            unpushed = ancestor_rc != 0
        else:
            unpushed = True
    else:
        unpushed = None

    protection = protections.match(resolved, branch=branch) if protections is not None else None
    if protection is None and local_policy is not None:
        protection = f"local-root-policy:{local_policy['policy_id']}:protected-local-only"
    common_dir_key = _path_digest(common_dir) if common_dir is not None else None
    repository_key = hashlib.sha256(repository.encode("utf-8")).hexdigest() if repository else None
    clone_identity = repository or (f"local-policy:{local_policy['policy_id']}" if local_policy is not None else None)
    clone_key = (
        _digest({"repository": clone_identity, "common_dir_key": common_dir_key})
        if clone_identity is not None and common_dir_key is not None
        else None
    )
    complete = not errors
    return {
        "path": str(resolved),
        "path_key": _path_digest(resolved),
        "repository": repository,
        "repository_key": repository_key,
        "clone_key": clone_key,
        "common_dir": str(common_dir) if common_dir is not None else None,
        "common_dir_key": common_dir_key,
        "checkout_kind": "linked_worktree" if git_dir and common_dir and git_dir != common_dir else "primary_clone",
        "head": head,
        "branch": branch,
        "dirty": dirty,
        "untracked": untracked,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "unpushed": unpushed,
        "protected": protection is not None,
        "protection_reason": protection,
        "local_only": local_policy is not None,
        "local_policy_id": local_policy.get("policy_id") if local_policy is not None else None,
        "custody_risk": bool(dirty or untracked or unpushed),
        "complete": complete,
        "errors": errors,
    }


def _tracked_root(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "path_key",
            "repository_key",
            "clone_key",
            "common_dir_key",
            "checkout_kind",
            "head",
            "dirty",
            "untracked",
            "ahead",
            "behind",
            "unpushed",
            "protected",
            "local_only",
            "local_policy_id",
            "custody_risk",
            "complete",
            "errors",
        )
    }


def collect_local_git_census(
    repository_root: Path,
    *,
    checkout_roots: Iterable[Path] | None = None,
    observed_at: datetime | None = None,
    require_protection_registry: bool = True,
    require_local_root_policy_registry: bool = True,
    workspace_roots: Iterable[Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return private facts and a redacted tracked projection for all local Git roots."""

    observed = (observed_at or datetime.now(UTC)).astimezone(UTC)
    failures: list[dict[str, Any]] = []
    try:
        protections = ProtectedExclusionRegistry.load(repository_root)
    except ProtectedExclusionError as exc:
        protections = None
        if require_protection_registry:
            failures.append({"scope": "protection_registry", "error": str(exc)})

    try:
        local_root_policies, local_policy_digest, local_policy_count = _load_local_root_policies(
            repository_root,
            workspace_roots or _configured_workspace_roots(),
        )
    except ValueError as exc:
        local_root_policies = {}
        local_policy_digest = None
        local_policy_count = 0
        if require_local_root_policy_registry:
            failures.append({"scope": "local_root_policy_registry", "error": str(exc)})

    if checkout_roots is None:
        try:
            discovered = _discover_workspace_checkouts(strict=True)
        except WorktreeInventoryError as exc:
            discovered = []
            failures.append({"scope": "workspace_discovery", "error": str(exc)})
    else:
        discovered = list(checkout_roots)

    candidates: list[Path] = []
    for checkout in sorted(discovered):
        try:
            candidates.extend(_git_worktree_paths(checkout, strict=True))
        except WorktreeInventoryError as exc:
            failures.append(
                {
                    "scope": "worktree_inventory",
                    "path": str(checkout.resolve(strict=False)),
                    "path_key": _path_digest(checkout.resolve(strict=False)),
                    "error": str(exc),
                }
            )

    unique: dict[str, Path] = {}
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        unique.setdefault(str(resolved), resolved)
    roots = [
        _inspect_root(
            path,
            protections=protections,
            local_root_policies=local_root_policies,
        )
        for path in unique.values()
    ]
    roots.sort(key=lambda row: str(row["path_key"]))
    for row in roots:
        for error in row["errors"]:
            failures.append(
                {
                    "scope": "git_root",
                    "path": row["path"],
                    "path_key": row["path_key"],
                    "error": error,
                }
            )

    clone_groups = {row["clone_key"] for row in roots if row["clone_key"] is not None}
    unaccounted = sum(not row["complete"] for row in roots)
    summary = {
        "checkout_seed_count": len(discovered),
        "root_count": len(roots),
        "clone_group_count": len(clone_groups),
        "linked_worktree_count": sum(row["checkout_kind"] == "linked_worktree" for row in roots),
        "protected_count": sum(bool(row["protected"]) for row in roots),
        "protection_exclusion_count": len(protections.exclusions) if protections is not None else 0,
        "local_root_policy_count": local_policy_count,
        "custody_risk_count": sum(bool(row["custody_risk"]) for row in roots),
        "failure_count": len(failures),
        "unaccounted": unaccounted,
        "exhaustive": not failures and unaccounted == 0,
    }
    private_payload = {
        "schema": SCHEMA,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "summary": summary,
        "protection_registry_digest": protections.registry_digest if protections is not None else None,
        "local_root_policy_registry_digest": local_policy_digest,
        "roots": roots,
        "failures": failures,
    }
    tracked_roots = [_tracked_root(row) for row in roots]
    tracked_failures = [{key: row[key] for key in ("scope", "path_key", "error") if key in row} for row in failures]
    tracked_payload = {
        "schema": SCHEMA,
        "observed_at": private_payload["observed_at"],
        "summary": summary,
        "protection_registry_digest": private_payload["protection_registry_digest"],
        "local_root_policy_registry_digest": private_payload["local_root_policy_registry_digest"],
        "content_sha256": _digest(tracked_roots),
        "roots": tracked_roots,
        "failures": tracked_failures,
    }
    return private_payload, tracked_payload
