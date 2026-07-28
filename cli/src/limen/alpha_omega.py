"""Redacted alpha-to-omega reconciliation and fixed-point evidence."""

from __future__ import annotations

import hashlib
import plistlib
import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import rfc8785

from limen.prima_materia_store import SourceRegistry
from limen.protected_exclusions import ProtectedExclusionRegistry
from limen.resource_envelope import (
    ResourceTelemetry,
    evaluate_resource_envelope,
)

MANIFEST_SCHEMA = "limen.alpha_omega_reconciliation.v1"
AUDIT_PAIR_SCHEMA = "limen.alpha_omega_fixed_point_pair.v1"
CommandRunner = Callable[[list[str], Path | None, int], subprocess.CompletedProcess[str]]


class AlphaOmegaError(RuntimeError):
    """A live reconciliation probe could not produce trustworthy evidence."""


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _run(
    command: list[str],
    cwd: Path | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 127, "", type(exc).__name__)


def _path_digest(path: Path) -> str:
    return hashlib.sha256(str(path.resolve(strict=False)).encode()).hexdigest()


def _git(
    repository: Path,
    *arguments: str,
    runner: CommandRunner = _run,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return runner(["git", *arguments], repository, timeout)


def repository_projection(
    repository_id: str,
    path: Path,
    *,
    runner: CommandRunner = _run,
) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=False)
    base: dict[str, Any] = {
        "repository_id": repository_id,
        "path_sha256": _path_digest(resolved),
    }
    inside = _git(
        resolved,
        "rev-parse",
        "--is-inside-work-tree",
        runner=runner,
    )
    if inside.returncode != 0:
        return {**base, "available": False, "reason": "not-a-git-worktree"}
    head = _git(resolved, "rev-parse", "HEAD", runner=runner)
    tree = _git(resolved, "rev-parse", "HEAD^{tree}", runner=runner)
    branch = _git(resolved, "branch", "--show-current", runner=runner)
    status = _git(
        resolved,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        runner=runner,
    )
    refs = _git(
        resolved,
        "for-each-ref",
        "--format=%(refname)%00%(objectname)%00%(*objectname)",
        "refs/heads",
        "refs/tags",
        "refs/notes",
        "refs/stash",
        runner=runner,
    )
    remote = _git(
        resolved,
        "ls-remote",
        "--refs",
        "origin",
        runner=runner,
        timeout=120,
    )
    worktrees = _git(
        resolved,
        "worktree",
        "list",
        "--porcelain",
        runner=runner,
    )
    required = (head, tree, branch, status, refs, remote, worktrees)
    if any(result.returncode != 0 for result in required):
        return {
            **base,
            "available": False,
            "reason": "repository-probe-incomplete",
        }
    status_bytes = status.stdout.encode("utf-8", errors="surrogateescape")
    local_ref_lines = [line for line in refs.stdout.splitlines() if line]
    remote_ref_lines = [line for line in remote.stdout.splitlines() if line]
    remote_objects: list[str] = []
    remote_shape_valid = True
    for line in remote_ref_lines:
        parts = line.split("\t", 1)
        if len(parts) != 2 or not parts[0] or not parts[1].startswith("refs/"):
            remote_shape_valid = False
            break
        remote_objects.append(parts[0])
    all_local_refs_remote = remote_shape_valid and bool(remote_objects)
    for line in local_ref_lines:
        parts = line.split("\0")
        if len(parts) != 3:
            all_local_refs_remote = False
            break
        _local_ref, object_id, _peeled = parts
        if object_id in remote_objects:
            continue
        object_type = _git(
            resolved,
            "cat-file",
            "-t",
            object_id,
            runner=runner,
        )
        if object_type.returncode != 0 or object_type.stdout.strip() != "commit":
            all_local_refs_remote = False
            break
        if not any(
            _git(
                resolved,
                "merge-base",
                "--is-ancestor",
                object_id,
                remote_object,
                runner=runner,
            ).returncode
            == 0
            for remote_object in remote_objects
        ):
            all_local_refs_remote = False
            break
    worktree_lines = worktrees.stdout.splitlines()
    return {
        **base,
        "available": True,
        "head": head.stdout.strip(),
        "tree": tree.stdout.strip(),
        "branch_sha256": hashlib.sha256(branch.stdout.strip().encode()).hexdigest(),
        "dirty_entry_count": status.stdout.count("\0"),
        "working_state_sha256": hashlib.sha256(status_bytes).hexdigest(),
        "local_ref_count": len(local_ref_lines),
        "local_refs_sha256": hashlib.sha256(refs.stdout.encode()).hexdigest(),
        "remote_ref_count": len(remote_ref_lines),
        "remote_refs_sha256": hashlib.sha256(remote.stdout.encode()).hexdigest(),
        "remote_proof_available": bool(remote_ref_lines),
        "all_local_refs_remote": all_local_refs_remote,
        "registered_worktree_count": sum(1 for line in worktree_lines if line.startswith("worktree ")),
        "stale_registration_count": sum(1 for line in worktree_lines if line == "prunable"),
        "registration_state_sha256": hashlib.sha256(worktrees.stdout.encode()).hexdigest(),
    }


def private_root_projection(root_id: str, path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=False)
    projection: dict[str, Any] = {
        "root_id": root_id,
        "path_sha256": _path_digest(resolved),
        "exists": resolved.exists(),
    }
    if not resolved.exists():
        return projection
    try:
        info = resolved.lstat()
    except OSError:
        return {**projection, "exists": False, "reason": "identity-unavailable"}
    return {
        **projection,
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "mtime_ns": str(info.st_mtime_ns),
    }


def physical_device_projection(
    *,
    runner: CommandRunner = _run,
) -> dict[str, Any]:
    result = runner(["/usr/sbin/diskutil", "list", "-plist"], None, 30)
    if result.returncode != 0:
        return {
            "available": False,
            "device_count": 0,
            "inventory_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
        }
    raw = result.stdout.encode("utf-8", errors="surrogateescape")
    try:
        payload = plistlib.loads(raw)
        devices = payload.get("AllDisksAndPartitions", [])
        if not isinstance(devices, list) or any(
            not isinstance(value, dict) or not isinstance(value.get("DeviceIdentifier"), str) for value in devices
        ):
            raise ValueError
        identifiers = sorted(str(value["DeviceIdentifier"]) for value in devices)
    except (plistlib.InvalidFileException, TypeError, ValueError):
        return {
            "available": False,
            "device_count": 0,
            "inventory_sha256": hashlib.sha256(raw).hexdigest(),
        }
    return {
        "available": True,
        "device_count": len(identifiers),
        "device_identity_digests": [hashlib.sha256(value.encode()).hexdigest() for value in identifiers],
        "inventory_sha256": hashlib.sha256(raw).hexdigest(),
    }


def protected_process_projection(
    protected_registry: ProtectedExclusionRegistry,
    *,
    runner: CommandRunner = _run,
) -> dict[str, Any]:
    result = runner(
        ["lsof", "-n", "-a", "-d", "cwd", "-Fpn"],
        None,
        30,
    )
    if result.returncode not in {0, 1}:
        return {"available": False, "protected_cwds": []}
    observed: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("n/"):
            observed.append(Path(line[1:]).resolve(strict=False))
    rows = []
    for exclusion in protected_registry.exclusions:
        root = exclusion.resolved_path(protected_registry.repository_root)
        rows.append(
            {
                "exclusion_id": exclusion.exclusion_id,
                "active_cwd_count": sum(1 for cwd in observed if cwd == root or root in cwd.parents),
            }
        )
    return {"available": True, "protected_cwds": rows}


def _protected_path_digests(
    protected_registry: ProtectedExclusionRegistry,
) -> frozenset[str]:
    return frozenset(
        _path_digest(exclusion.resolved_path(protected_registry.repository_root))
        for exclusion in protected_registry.exclusions
    )


def build_reconciliation_manifest(
    *,
    repository_root: Path,
    base_sha: str,
    repositories: Mapping[str, Path],
    private_roots: Mapping[str, Path],
    source_registry: SourceRegistry,
    observed_source_ids: Iterable[str],
    protected_registry: ProtectedExclusionRegistry,
    resource_telemetry: ResourceTelemetry,
    physical_devices: Mapping[str, Any],
    protected_processes: Mapping[str, Any],
    automatically_safe_reclaim_count: int | None,
    repository_census_complete: bool = True,
    receipt_predicates: Mapping[str, bool] | None = None,
    observed_at: datetime | None = None,
    runner: CommandRunner = _run,
) -> dict[str, Any]:
    instant = observed_at or datetime.now(UTC)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise AlphaOmegaError("observed-at-must-be-aware")
    if automatically_safe_reclaim_count is not None and automatically_safe_reclaim_count < 0:
        raise AlphaOmegaError("safe-reclaim-count-must-be-nonnegative")
    if len(base_sha) != 40 or any(value not in "0123456789abcdef" for value in base_sha):
        raise AlphaOmegaError("base-sha-invalid")
    root = repository_root.resolve(strict=True)
    repository_rows = [
        repository_projection(identifier, path, runner=runner) for identifier, path in sorted(repositories.items())
    ]
    private_rows = [private_root_projection(identifier, path) for identifier, path in sorted(private_roots.items())]
    source_projection = source_registry.public_projection(observed_source_ids)
    protection_projection = protected_registry.projection()
    claims = tuple(adapter.resource_claim for adapter in source_registry.adapters)
    envelope = evaluate_resource_envelope(
        resource_telemetry,
        claims,
        observed_at=instant,
    )
    disk_free = shutil.disk_usage(root).free
    resource_projection = {
        "observed_at": resource_telemetry.observed_at.isoformat(),
        "ram_total_bytes": resource_telemetry.ram_total_bytes,
        "ram_available_bytes": resource_telemetry.ram_available_bytes,
        "swap_used_bytes": resource_telemetry.swap_used_bytes,
        "required_free_bytes": envelope.required_free_bytes,
        "disk_free_bytes": disk_free,
        "nonnegative": disk_free >= envelope.required_free_bytes,
    }
    protected_digests = _protected_path_digests(protected_registry)
    nonprotected_repositories = [row for row in repository_rows if row["path_sha256"] not in protected_digests]
    provided = dict(receipt_predicates or {})
    predicates: dict[str, bool] = {
        "frozen_repository_terminal_custody": repository_census_complete
        and all(
            row.get("available") is True
            and row.get("all_local_refs_remote") is True
            and row.get("dirty_entry_count") == 0
            for row in nonprotected_repositories
        ),
        "frozen_storage_terminal_custody": provided.get(
            "frozen_storage_terminal_custody",
            False,
        ),
        "removed_repositories_reconstruct": provided.get(
            "removed_repositories_reconstruct",
            False,
        ),
        "private_material_restores_from_two_devices": provided.get(
            "private_material_restores_from_two_devices",
            False,
        ),
        "frozen_wave_adapter_debt_zero": source_projection["missing_adapter_count"] == 0,
        "automatically_safe_reclaim_zero": automatically_safe_reclaim_count == 0,
        "repository_and_stale_registration_census_zero_except_protected": (
            repository_census_complete
            and not nonprotected_repositories
            and all(row.get("stale_registration_count", 0) == 0 for row in repository_rows)
        ),
        "dynamic_resource_envelope_nonnegative": resource_projection["nonnegative"],
        "empty_scratch_bootstrap_passed": provided.get(
            "empty_scratch_bootstrap_passed",
            False,
        ),
        "hydration_passed": provided.get("hydration_passed", False),
        "replay_passed": provided.get("replay_passed", False),
        "composition_passed": provided.get("composition_passed", False),
        "dematerialization_passed": provided.get(
            "dematerialization_passed",
            False,
        ),
    }
    state = {
        "base_sha": base_sha,
        "repository_census_complete": repository_census_complete,
        "repositories": repository_rows,
        "private_roots": private_rows,
        "physical_devices": dict(physical_devices),
        "protected_processes": dict(protected_processes),
        "protected_exclusions": protection_projection,
        "source_coverage": source_projection,
        "resource_envelope_nonnegative": resource_projection["nonnegative"],
        "automatically_safe_reclaim_count": automatically_safe_reclaim_count,
        "lambda_predicates": predicates,
    }
    state_sha256 = _canonical_digest(state)
    lambda_passed = all(predicates.values())
    omega_admitted = lambda_passed and protection_projection["omega_blocker_count"] == 0
    return {
        "schema": MANIFEST_SCHEMA,
        "observed_at": instant.isoformat(),
        "state_sha256": state_sha256,
        **state,
        "resource_envelope": resource_projection,
        "lambda_passed": lambda_passed,
        "omega_admitted": omega_admitted,
    }


def fixed_point_pair(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> dict[str, Any]:
    if first.get("schema") != MANIFEST_SCHEMA or second.get("schema") != MANIFEST_SCHEMA:
        raise AlphaOmegaError("fixed-point-manifest-schema-mismatch")
    first_sha = first.get("state_sha256")
    second_sha = second.get("state_sha256")
    if not isinstance(first_sha, str) or not isinstance(second_sha, str):
        raise AlphaOmegaError("fixed-point-state-digest-missing")
    payload = {
        "schema": AUDIT_PAIR_SCHEMA,
        "first_observed_at": first.get("observed_at"),
        "second_observed_at": second.get("observed_at"),
        "first_state_sha256": first_sha,
        "second_state_sha256": second_sha,
        "unchanged": first_sha == second_sha,
        "lambda_passed": first.get("lambda_passed") is True and second.get("lambda_passed") is True,
        "omega_admitted": first.get("omega_admitted") is True and second.get("omega_admitted") is True,
    }
    return {**payload, "pair_sha256": _canonical_digest(payload)}
