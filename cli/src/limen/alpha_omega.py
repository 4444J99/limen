"""Fail-closed, frozen-wave alpha-to-omega reconciliation."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import rfc8785
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from limen.omega_owner_receipt import (
    OmegaOwnerReceiptError,
    load_owner_receipt,
    normalized_owner_receipt,
)
from limen.prima_materia import (
    FrozenSourceInstanceV1,
    FrozenWaveManifestV1,
    ResourceClaimV1,
)
from limen.prima_materia_store import SourceRegistry
from limen.protected_exclusions import ProtectedExclusionRegistry
from limen.resource_envelope import ResourceTelemetry, evaluate_resource_envelope

MANIFEST_SCHEMA = "limen.alpha_omega_reconciliation.v2"
AUDIT_PAIR_SCHEMA = "limen.alpha_omega_fixed_point_pair.v2"
SOURCE_INVENTORY_SCHEMA: Literal["limen.prima_materia_source_inventory.v1"] = "limen.prima_materia_source_inventory.v1"
RECLAIM_CENSUS_SCHEMA: Literal["limen.prima_materia_reclaim_census.v1"] = "limen.prima_materia_reclaim_census.v1"
LAMBDA_RUNG_REGISTRY_SCHEMA: Literal["limen.prima_materia_lambda_rungs.v1"] = "limen.prima_materia_lambda_rungs.v1"
MAX_INPUT_FRESHNESS_SECONDS = 86_400
MAX_LOCAL_PROBE_THREADS = 3
MAX_FROZEN_ROOTS = 4096
DISCOVERY_SKIP_DIRECTORIES = {
    ".cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
CommandRunner = Callable[[list[str], Path | None, int], subprocess.CompletedProcess[str]]

LAMBDA_PREDICATES = (
    "frozen_repository_terminal_custody",
    "frozen_storage_terminal_custody",
    "removed_repositories_reconstruct",
    "private_material_restores_from_two_devices",
    "frozen_wave_adapter_debt_zero",
    "automatically_safe_reclaim_zero",
    "repository_and_stale_registration_census_zero_except_protected",
    "dynamic_resource_envelope_nonnegative",
    "empty_scratch_bootstrap_passed",
    "hydration_passed",
    "replay_passed",
    "composition_passed",
    "dematerialization_passed",
)


class AlphaOmegaError(RuntimeError):
    """A live reconciliation probe could not produce trustworthy evidence."""


def _digest(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _validate_digest(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("digest must be lowercase SHA-256")
    return value


def _validate_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value.astimezone(UTC)


class _Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class SourceInventoryReceiptV1(_Contract):
    schema_id: Literal["limen.prima_materia_source_inventory.v1"] = Field(
        default=SOURCE_INVENTORY_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    observed_at: datetime
    frozen_wave_sha256: str
    producer_digest: str
    complete: bool
    source_instances: tuple[FrozenSourceInstanceV1, ...] = Field(max_length=8192)

    _observed = field_validator("observed_at")(_validate_aware)
    _digests = field_validator("frozen_wave_sha256", "producer_digest")(_validate_digest)

    @model_validator(mode="after")
    def identities_are_unique_and_sorted(self) -> SourceInventoryReceiptV1:
        identities = tuple(item.instance_id for item in self.source_instances)
        if len(identities) != len(set(identities)):
            raise ValueError("source inventory contains duplicate instance IDs")
        if tuple(sorted(identities)) != identities:
            raise ValueError("source inventory must be sorted")
        return self


class ReclaimCensusReceiptV1(_Contract):
    schema_id: Literal["limen.prima_materia_reclaim_census.v1"] = Field(
        default=RECLAIM_CENSUS_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    observed_at: datetime
    frozen_wave_sha256: str
    plan_sha256: str | None = None
    protected_registry_digest: str
    scanned_count: int = Field(ge=0)
    candidate_count: int | None = Field(default=None, ge=0)
    deferred_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    complete: bool

    _observed = field_validator("observed_at")(_validate_aware)
    _digests = field_validator(
        "frozen_wave_sha256",
        "protected_registry_digest",
    )(_validate_digest)
    _optional_digest = field_validator("plan_sha256")(
        lambda value: _validate_digest(value) if value is not None else None
    )

    @model_validator(mode="after")
    def complete_census_has_an_integer_count(self) -> ReclaimCensusReceiptV1:
        if self.complete and self.candidate_count is None:
            raise ValueError("a complete reclaim census requires an integer candidate count")
        if self.complete and self.plan_sha256 is None:
            raise ValueError("a complete reclaim census requires a plan digest")
        if self.complete and (self.deferred_count or self.failure_count):
            raise ValueError("a complete reclaim census cannot defer or fail candidates")
        return self


class LambdaRungV1(_Contract):
    rung_id: str = Field(min_length=1, max_length=256, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    predicate: str = Field(min_length=1, max_length=8192)
    dependencies: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    timeout_seconds: int = Field(ge=1, le=7200)
    max_age_seconds: int = Field(ge=1, le=604_800)
    receipt_path: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def bindings_are_safe(self) -> LambdaRungV1:
        if self.predicate.count("{frozen_wave_sha256}") != 1:
            raise ValueError("lambda predicate must bind exactly one frozen-wave digest")
        path = Path(self.receipt_path)
        if path.is_absolute() or ".." in path.parts or path in {Path(), Path(".")}:
            raise ValueError("lambda owner receipt path must be safe and relative")
        if self.rung_id in self.dependencies or len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("lambda rung dependencies must be unique and non-recursive")
        return self


class LambdaRungRegistryV1(_Contract):
    schema_id: Literal["limen.prima_materia_lambda_rungs.v1"] = Field(
        default=LAMBDA_RUNG_REGISTRY_SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    rungs: tuple[LambdaRungV1, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def denominator_matches_lambda(self) -> LambdaRungRegistryV1:
        identifiers = tuple(rung.rung_id for rung in self.rungs)
        if identifiers != tuple(sorted(identifiers)):
            raise ValueError("lambda rung registry must be sorted")
        if set(identifiers) != set(LAMBDA_PREDICATES):
            raise ValueError("lambda rung registry must bind all and only the 13 lambda predicates")
        for rung in self.rungs:
            unknown = set(rung.dependencies) - set(identifiers)
            if unknown:
                raise ValueError(f"{rung.rung_id}: lambda dependency is not registered")
        dependencies = {rung.rung_id: rung.dependencies for rung in self.rungs}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(rung_id: str) -> None:
            if rung_id in visiting:
                raise ValueError("lambda rung registry contains a dependency cycle")
            if rung_id in visited:
                return
            visiting.add(rung_id)
            for dependency in dependencies[rung_id]:
                visit(dependency)
            visiting.remove(rung_id)
            visited.add(rung_id)

        for identifier in identifiers:
            visit(identifier)
        return self


def frozen_wave_digest(manifest: FrozenWaveManifestV1) -> str:
    return _digest(manifest.model_dump(mode="json"))


def lambda_rung_registry_digest(registry: LambdaRungRegistryV1) -> str:
    return _digest(registry.model_dump(mode="json"))


def source_inventory_producer_digest(
    producer_path: Path,
    enumerator_registry_path: Path,
) -> str:
    return hashlib.sha256(producer_path.read_bytes() + b"\0" + enumerator_registry_path.read_bytes()).hexdigest()


def predicate_state_digest(state: Mapping[str, Any]) -> str:
    normalized = dict(state)
    resource = normalized.get("resource_envelope")
    if isinstance(resource, Mapping):
        normalized["resource_envelope"] = {
            key: value
            for key, value in resource.items()
            if key
            not in {
                "observed_at",
                "ram_total_bytes",
                "ram_available_bytes",
                "memory_available_bytes",
                "swap_used_bytes",
                "required_free_bytes",
                "disk_free_bytes",
            }
        }
    devices = normalized.get("physical_devices")
    if isinstance(devices, Mapping):
        normalized["physical_devices"] = {key: value for key, value in devices.items() if key != "inventory_sha256"}
    return _digest(normalized)


def load_frozen_wave(path: Path) -> FrozenWaveManifestV1:
    return FrozenWaveManifestV1.model_validate_json(path.read_text(encoding="utf-8"))


def load_source_inventory(path: Path) -> SourceInventoryReceiptV1:
    return SourceInventoryReceiptV1.model_validate_json(path.read_text(encoding="utf-8"))


def load_reclaim_census(path: Path) -> ReclaimCensusReceiptV1:
    return ReclaimCensusReceiptV1.model_validate_json(path.read_text(encoding="utf-8"))


def load_lambda_rungs(path: Path) -> LambdaRungRegistryV1:
    return LambdaRungRegistryV1.model_validate_json(path.read_text(encoding="utf-8"))


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


def denominator_identifier(prefix: str, path: Path) -> str:
    digest = _path_digest(path)
    return f"{prefix}{digest[:24]}"


def discover_repository_denominator(
    search_roots: Iterable[Path],
    *,
    deadline: float,
) -> tuple[dict[str, Path], bool]:
    found: dict[Path, None] = {}
    complete = True
    for search_root in search_roots:
        root = search_root.expanduser().resolve(strict=False)
        if not root.is_dir():
            complete = False
            continue
        for current, directories, files in os.walk(root, followlinks=False):
            if time.monotonic() >= deadline:
                complete = False
                break
            directories[:] = sorted(
                name for name in directories if name not in DISCOVERY_SKIP_DIRECTORIES and name != ".git"
            )
            candidate = Path(current)
            if ".git" in files or (candidate / ".git").is_dir():
                found[candidate.resolve(strict=False)] = None
                if len(found) > MAX_FROZEN_ROOTS:
                    raise AlphaOmegaError("repository discovery exceeded the bounded limit")
        if time.monotonic() >= deadline:
            complete = False
            break
    return (
        {denominator_identifier("repository", path): path for path in sorted(found, key=str)},
        complete,
    )


def load_storage_inventory_roots(path: Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AlphaOmegaError("storage inventory is unavailable") from exc
    roots = payload.get("roots") if isinstance(payload, dict) else None
    if not isinstance(roots, list) or len(roots) > MAX_FROZEN_ROOTS:
        raise AlphaOmegaError("storage inventory roots are invalid")
    result: dict[str, Path] = {}
    for row in roots:
        if not isinstance(row, dict) or not isinstance(row.get("root"), str):
            raise AlphaOmegaError("storage inventory root is invalid")
        root = Path(row["root"]).expanduser()
        result[denominator_identifier("privateRoot", root)] = root
    return result


def registered_worktree_denominator(
    repository_root: Path,
    runner: CommandRunner,
) -> tuple[dict[str, Path], bool]:
    result = runner(
        ["git", "worktree", "list", "--porcelain"],
        repository_root,
        60,
    )
    if result.returncode != 0:
        return {}, False
    paths = [Path(line.split(" ", 1)[1]) for line in result.stdout.splitlines() if line.startswith("worktree ")]
    if len(paths) > MAX_FROZEN_ROOTS:
        raise AlphaOmegaError("registered worktree census exceeded the bounded limit")
    return (
        {denominator_identifier("repository", path): path for path in paths},
        True,
    )


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
    if not resolved.exists():
        return {**base, "available": False, "reason": "repository-absent"}
    if not resolved.is_dir():
        return {
            **base,
            "available": False,
            "reason": "repository-path-not-directory",
        }
    inside = _git(resolved, "rev-parse", "--is-inside-work-tree", runner=runner)
    if inside.returncode != 0:
        return {
            **base,
            "available": False,
            "reason": ("repository-probe-incomplete" if inside.returncode in {124, 127} else "not-a-git-worktree"),
        }
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
        object_type = _git(resolved, "cat-file", "-t", object_id, runner=runner)
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
    status_bytes = status.stdout.encode("utf-8", errors="surrogateescape")
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
        "stale_registration_count": sum(1 for line in worktree_lines if line.startswith("prunable")),
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
            "device_identity_digests": [],
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
            "device_identity_digests": [],
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
    result = runner(["lsof", "-n", "-a", "-d", "cwd", "-Fpn"], None, 30)
    if result.returncode not in {0, 1}:
        return {"available": False, "protected_cwds": []}
    observed = [Path(line[1:]).resolve(strict=False) for line in result.stdout.splitlines() if line.startswith("n/")]
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


def control_plane_projection(
    repository_root: Path,
    frozen_wave: FrozenWaveManifestV1,
    *,
    runner: CommandRunner = _run,
) -> dict[str, Any]:
    remote = runner(
        [
            "git",
            "ls-remote",
            frozen_wave.control_plane_repository,
            f"refs/heads/{frozen_wave.control_plane_default_branch}",
        ],
        repository_root,
        120,
    )
    runtime = runner(["domus-limen-runtime", "status"], repository_root, 30)
    remote_sha = ""
    if remote.returncode == 0:
        fields = remote.stdout.strip().split()
        if len(fields) == 2:
            remote_sha = fields[0]
    installed_sha = ""
    runtime_repository = ""
    runtime_path_digest = ""
    try:
        runtime_payload = json.loads(runtime.stdout) if runtime.returncode == 0 else {}
        receipt = runtime_payload.get("receipt", {}) if isinstance(runtime_payload, dict) else {}
        if isinstance(receipt, dict):
            installed_sha = str(receipt.get("sha") or "")
            runtime_repository = str(receipt.get("repository") or "")
        runtime_path = runtime_payload.get("runtime") if isinstance(runtime_payload, dict) else None
        if isinstance(runtime_path, str) and runtime_path:
            runtime_path_digest = _path_digest(Path(runtime_path))
    except json.JSONDecodeError:
        pass
    available = bool(remote_sha and installed_sha and runtime_repository and runtime_path_digest)
    matches = (
        available
        and remote_sha == frozen_wave.remote_main_sha
        and installed_sha == frozen_wave.installed_runtime_sha
        and runtime_repository == frozen_wave.control_plane_repository
        and runtime_path_digest == frozen_wave.control_plane_runtime_path_sha256
    )
    return {
        "available": available,
        "matches_frozen_wave": matches,
        "remote_main_sha": remote_sha or None,
        "installed_runtime_sha": installed_sha or None,
        "runtime_path_sha256": runtime_path_digest or None,
        "runtime_repository_sha256": (
            hashlib.sha256(runtime_repository.encode()).hexdigest() if runtime_repository else None
        ),
    }


def _fresh(
    observed_at: datetime,
    now: datetime,
    *,
    max_age_seconds: int = MAX_INPUT_FRESHNESS_SECONDS,
) -> bool:
    return observed_at <= now + timedelta(seconds=60) and now - observed_at <= timedelta(seconds=max_age_seconds)


def _owner_receipts(
    *,
    repository_root: Path,
    registry: LambdaRungRegistryV1,
    wave_sha256: str,
    now: datetime,
) -> tuple[dict[str, bool], dict[str, Any], bool]:
    base_passes: dict[str, bool] = {}
    projection: dict[str, Any] = {}
    complete = True
    for rung in registry.rungs:
        predicate = rung.predicate.replace("{frozen_wave_sha256}", wave_sha256)
        try:
            receipt = load_owner_receipt(
                repository_root / rung.receipt_path,
                rung_id=rung.rung_id,
                predicate=predicate,
                max_age_seconds=rung.max_age_seconds,
                now=now,
                require_pass=False,
            )
        except OmegaOwnerReceiptError as exc:
            complete = False
            base_passes[rung.rung_id] = False
            projection[rung.rung_id] = {
                "available": False,
                "reason": str(exc),
            }
            continue
        normalized = normalized_owner_receipt(receipt)
        base_passes[rung.rung_id] = receipt.status == "PASS"
        projection[rung.rung_id] = {
            "available": True,
            "status": receipt.status,
            "receipt_sha256": _digest(normalized),
            "predicate_digest": receipt.predicate_digest,
        }
    passes = {
        rung.rung_id: base_passes[rung.rung_id] and all(base_passes[dependency] for dependency in rung.dependencies)
        for rung in registry.rungs
    }
    return passes, projection, complete


def _project_repositories(
    frozen_wave: FrozenWaveManifestV1,
    repositories: Mapping[str, Path],
    *,
    runner: CommandRunner,
    max_workers: int,
) -> tuple[list[dict[str, Any]], bool]:
    expected = {item.repository_id: item.path_sha256 for item in frozen_wave.repositories}
    actual = {identifier: _path_digest(path) for identifier, path in repositories.items()}
    denominator_matches = expected == actual
    rows: list[dict[str, Any]] = []
    inputs = [
        (identifier, repositories[identifier])
        for identifier, path_digest in expected.items()
        if identifier in repositories and actual.get(identifier) == path_digest
    ]
    workers = min(MAX_LOCAL_PROBE_THREADS, max_workers, max(1, len(inputs)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        projected = executor.map(
            lambda value: repository_projection(value[0], value[1], runner=runner),
            inputs,
        )
        rows.extend(projected)
    observed = {row["repository_id"] for row in rows}
    for identifier, path_digest in expected.items():
        if identifier not in observed:
            rows.append(
                {
                    "repository_id": identifier,
                    "path_sha256": path_digest,
                    "available": False,
                    "reason": "frozen-repository-denominator-mismatch",
                }
            )
    return sorted(rows, key=lambda row: str(row["repository_id"])), denominator_matches


def _project_storage_roots(
    frozen_wave: FrozenWaveManifestV1,
    private_roots: Mapping[str, Path],
) -> tuple[list[dict[str, Any]], bool]:
    expected = {item.root_id: item.path_sha256 for item in frozen_wave.storage_roots}
    actual = {identifier: _path_digest(path) for identifier, path in private_roots.items()}
    denominator_matches = expected == actual
    rows = []
    for identifier, path_digest in expected.items():
        if identifier in private_roots and actual.get(identifier) == path_digest:
            rows.append(private_root_projection(identifier, private_roots[identifier]))
        else:
            rows.append(
                {
                    "root_id": identifier,
                    "path_sha256": path_digest,
                    "exists": False,
                    "reason": "frozen-storage-denominator-mismatch",
                }
            )
    return sorted(rows, key=lambda row: str(row["root_id"])), denominator_matches


def build_reconciliation_manifest(
    *,
    repository_root: Path,
    frozen_wave: FrozenWaveManifestV1,
    repositories: Mapping[str, Path],
    private_roots: Mapping[str, Path],
    source_registry: SourceRegistry,
    source_inventory: SourceInventoryReceiptV1,
    protected_registry: ProtectedExclusionRegistry,
    resource_claims: tuple[ResourceClaimV1, ...],
    resource_task_graph_digest: str,
    reclaim_census: ReclaimCensusReceiptV1,
    lambda_rungs: LambdaRungRegistryV1,
    resource_telemetry: ResourceTelemetry,
    physical_devices: Mapping[str, Any],
    protected_processes: Mapping[str, Any],
    control_plane: Mapping[str, Any],
    audit_deadline_seconds: int,
    observed_at: datetime | None = None,
    runner: CommandRunner = _run,
    max_workers: int = MAX_LOCAL_PROBE_THREADS,
) -> dict[str, Any]:
    instant = _validate_aware(observed_at or datetime.now(UTC))
    if not 1 <= audit_deadline_seconds <= 1800:
        raise AlphaOmegaError("audit-deadline-must-be-between-1-and-1800-seconds")
    if not 1 <= max_workers <= MAX_LOCAL_PROBE_THREADS:
        raise AlphaOmegaError("audit-probe-thread-count-out-of-range")
    _validate_digest(resource_task_graph_digest)
    root = repository_root.resolve(strict=True)
    wave_sha256 = frozen_wave_digest(frozen_wave)
    repository_rows, repository_denominator_matches = _project_repositories(
        frozen_wave,
        repositories,
        runner=runner,
        max_workers=max_workers,
    )
    private_rows, storage_denominator_matches = _project_storage_roots(
        frozen_wave,
        private_roots,
    )
    owner_passes, owner_projection, owner_receipts_complete = _owner_receipts(
        repository_root=root,
        registry=lambda_rungs,
        wave_sha256=wave_sha256,
        now=instant,
    )
    expected_sources = tuple((item.instance_id, item.source_id) for item in frozen_wave.source_instances)
    observed_sources = tuple((item.instance_id, item.source_id) for item in source_inventory.source_instances)
    source_inventory_matches = (
        source_inventory.complete
        and source_inventory.frozen_wave_sha256 == wave_sha256
        and source_inventory.producer_digest == frozen_wave.source_inventory_producer_digest
        and expected_sources == observed_sources
        and _fresh(source_inventory.observed_at, instant)
    )
    source_projection = source_registry.public_projection(item.source_id for item in source_inventory.source_instances)
    expected_protected = tuple(sorted(frozen_wave.protected_exclusion_ids))
    observed_protected = tuple(sorted(item.exclusion_id for item in protected_registry.exclusions))
    protection_projection = protected_registry.projection()
    protection_matches = (
        frozen_wave.protected_registry_digest == protected_registry.registry_digest
        and expected_protected == observed_protected
    )
    source_registry_matches = frozen_wave.source_registry_digest == source_registry.registry_digest
    lambda_registry_matches = frozen_wave.lambda_rung_registry_digest == lambda_rung_registry_digest(lambda_rungs)
    reclaim_matches = (
        reclaim_census.complete
        and reclaim_census.plan_sha256 is not None
        and reclaim_census.frozen_wave_sha256 == wave_sha256
        and reclaim_census.protected_registry_digest == protected_registry.registry_digest
        and _fresh(reclaim_census.observed_at, instant)
    )
    device_digests = set(physical_devices.get("device_identity_digests") or ())
    device_roles_match = all(item.physical_device_sha256 in device_digests for item in frozen_wave.device_roles)
    expected_claim_sources = {item.instance_id for item in frozen_wave.source_instances}
    claimed_sources = {claim.source_instance_id for claim in resource_claims}
    claims_live = (
        bool(resource_claims)
        and min(claim.effective_from for claim in resource_claims) <= instant
        and all(claim.rollback_until > instant for claim in resource_claims)
    )
    claims_complete = claims_live and claimed_sources == expected_claim_sources
    envelope = evaluate_resource_envelope(
        resource_telemetry,
        resource_claims,
        observed_at=instant,
    )
    disk_free = shutil.disk_usage(root).free
    resource_nonnegative = disk_free >= envelope.required_free_bytes and envelope.memory_nonnegative
    resource_projection: dict[str, Any] = {
        "observed_at": resource_telemetry.observed_at.isoformat(),
        "ram_total_bytes": resource_telemetry.ram_total_bytes,
        "ram_available_bytes": resource_telemetry.ram_available_bytes,
        "swap_used_bytes": resource_telemetry.swap_used_bytes,
        "required_free_bytes": envelope.required_free_bytes,
        "disk_free_bytes": disk_free,
        "peak_concurrent_memory_bytes": envelope.peak_concurrent_memory_bytes,
        "memory_nonnegative": envelope.memory_nonnegative,
        "nonnegative": resource_nonnegative,
        "claim_count": len(resource_claims),
        "claims_complete": claims_complete,
        "claims_live": claims_live,
        "claimed_source_count": len(claimed_sources),
        "expected_source_count": len(expected_claim_sources),
        "task_graph_sha256": resource_task_graph_digest,
        "max_claim_memory_bytes": max(
            (claim.memory_bytes for claim in resource_claims),
            default=0,
        ),
        "total_claim_file_count": sum(claim.file_count for claim in resource_claims),
        "total_claim_network_bytes": sum(claim.network_bytes for claim in resource_claims),
        "max_claim_wall_time_seconds": max(
            (claim.wall_time_seconds for claim in resource_claims),
            default=0,
        ),
    }
    protected_path_digests = {
        _path_digest(item.resolved_path(protected_registry.repository_root)) for item in protected_registry.exclusions
    }
    control_anchor_path_digest = frozen_wave.control_plane_runtime_path_sha256
    live_nonprotected = [
        row
        for row in repository_rows
        if row["path_sha256"] not in protected_path_digests
        and row["path_sha256"] != control_anchor_path_digest
        and row.get("available") is True
    ]
    unavailable_nonprotected = [
        row
        for row in repository_rows
        if row["path_sha256"] not in protected_path_digests
        and row["path_sha256"] != control_anchor_path_digest
        and row.get("available") is not True
    ]
    repository_probes_complete = all(
        row.get("reason")
        not in {
            "repository-probe-incomplete",
            "frozen-repository-denominator-mismatch",
        }
        for row in repository_rows
    )
    repository_custody_direct = all(
        row.get("all_local_refs_remote") is True and row.get("dirty_entry_count") == 0 for row in live_nonprotected
    ) and (not unavailable_nonprotected or owner_passes["removed_repositories_reconstruct"])
    storage_custody_direct = all(row.get("exists") is True for row in private_rows) or (
        owner_passes["frozen_storage_terminal_custody"] and owner_passes["private_material_restores_from_two_devices"]
    )
    predicates: dict[str, bool] = {
        "frozen_repository_terminal_custody": owner_passes["frozen_repository_terminal_custody"]
        and repository_custody_direct,
        "frozen_storage_terminal_custody": owner_passes["frozen_storage_terminal_custody"] and storage_custody_direct,
        "removed_repositories_reconstruct": owner_passes["removed_repositories_reconstruct"],
        "private_material_restores_from_two_devices": owner_passes["private_material_restores_from_two_devices"]
        and len(frozen_wave.device_roles) >= 2
        and device_roles_match,
        "frozen_wave_adapter_debt_zero": owner_passes["frozen_wave_adapter_debt_zero"]
        and source_inventory_matches
        and source_registry_matches
        and source_projection["missing_adapter_count"] == 0,
        "automatically_safe_reclaim_zero": owner_passes["automatically_safe_reclaim_zero"]
        and reclaim_matches
        and reclaim_census.complete
        and reclaim_census.candidate_count == 0,
        "repository_and_stale_registration_census_zero_except_protected": owner_passes[
            "repository_and_stale_registration_census_zero_except_protected"
        ]
        and repository_denominator_matches
        and not live_nonprotected
        and all(row.get("stale_registration_count", 0) == 0 for row in repository_rows if row.get("available") is True),
        "dynamic_resource_envelope_nonnegative": owner_passes["dynamic_resource_envelope_nonnegative"]
        and claims_complete
        and resource_nonnegative,
        "empty_scratch_bootstrap_passed": owner_passes["empty_scratch_bootstrap_passed"],
        "hydration_passed": owner_passes["hydration_passed"],
        "replay_passed": owner_passes["replay_passed"],
        "composition_passed": owner_passes["composition_passed"],
        "dematerialization_passed": owner_passes["dematerialization_passed"],
    }
    input_checks = {
        "frozen_wave_enumeration_complete": frozen_wave.enumeration_complete,
        "repository_denominator_matches": repository_denominator_matches,
        "repository_probes_complete": repository_probes_complete,
        "storage_denominator_matches": storage_denominator_matches,
        "source_inventory_matches": source_inventory_matches,
        "source_registry_matches": source_registry_matches,
        "lambda_rung_registry_matches": lambda_registry_matches,
        "protected_registry_matches": protection_matches,
        "reclaim_census_matches": reclaim_matches,
        "resource_task_graph_nonempty": claims_complete,
        "physical_device_probe_complete": physical_devices.get("available") is True,
        "device_roles_match": device_roles_match,
        "protected_process_probe_complete": protected_processes.get("available") is True,
        "control_plane_anchor_matches": control_plane.get("matches_frozen_wave") is True,
        "owner_receipts_complete": owner_receipts_complete,
    }
    audit_complete = all(input_checks.values())
    state = {
        "frozen_wave": {
            "wave_id": frozen_wave.wave_id,
            "wave_sha256": wave_sha256,
            "repository_count": len(frozen_wave.repositories),
            "storage_root_count": len(frozen_wave.storage_roots),
            "source_instance_count": len(frozen_wave.source_instances),
            "device_role_count": len(frozen_wave.device_roles),
            "remote_main_sha": frozen_wave.remote_main_sha,
            "installed_runtime_sha": frozen_wave.installed_runtime_sha,
        },
        "audit_complete": audit_complete,
        "incomplete_inputs": sorted(key for key, passed in input_checks.items() if not passed),
        "repositories": repository_rows,
        "private_roots": private_rows,
        "physical_devices": dict(physical_devices),
        "protected_processes": dict(protected_processes),
        "control_plane": dict(control_plane),
        "protected_exclusions": protection_projection,
        "source_coverage": source_projection,
        "source_inventory_sha256": _digest(source_inventory.model_dump(mode="json", exclude={"observed_at"})),
        "resource_envelope": resource_projection,
        "reclaim_census": reclaim_census.model_dump(
            mode="json",
            exclude={"observed_at"},
        ),
        "lambda_owner_receipts": owner_projection,
        "lambda_predicates": predicates,
    }
    state_sha256 = predicate_state_digest(state)
    lambda_passed = audit_complete and all(predicates.values())
    omega_admitted = lambda_passed and protection_matches and protection_projection["omega_blocker_count"] == 0
    return {
        "schema": MANIFEST_SCHEMA,
        "observed_at": instant.isoformat(),
        "audit_deadline_seconds": audit_deadline_seconds,
        "state_sha256": state_sha256,
        "state": state,
        "audit_complete": audit_complete,
        "lambda_passed": lambda_passed,
        "omega_admitted": omega_admitted,
    }


def fixed_point_pair(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> dict[str, Any]:
    if first.get("schema") != MANIFEST_SCHEMA or second.get("schema") != MANIFEST_SCHEMA:
        raise AlphaOmegaError("fixed-point-manifest-schema-mismatch")
    first_state = first.get("state")
    second_state = second.get("state")
    if not isinstance(first_state, dict) or not isinstance(second_state, dict):
        raise AlphaOmegaError("fixed-point-state-missing")
    first_sha = first.get("state_sha256")
    second_sha = second.get("state_sha256")
    if first_sha != predicate_state_digest(first_state) or second_sha != predicate_state_digest(second_state):
        raise AlphaOmegaError("fixed-point-state-digest-invalid")
    first_wave = first_state.get("frozen_wave", {}).get("wave_sha256")
    second_wave = second_state.get("frozen_wave", {}).get("wave_sha256")
    if not isinstance(first_wave, str) or first_wave != second_wave:
        raise AlphaOmegaError("fixed-point-frozen-wave-mismatch")
    complete = first.get("audit_complete") is True and second.get("audit_complete") is True
    payload = {
        "schema": AUDIT_PAIR_SCHEMA,
        "frozen_wave_sha256": first_wave,
        "first_observed_at": first.get("observed_at"),
        "second_observed_at": second.get("observed_at"),
        "first_state_sha256": first_sha,
        "second_state_sha256": second_sha,
        "complete": complete,
        "unchanged": complete and first_sha == second_sha,
        "lambda_passed": complete and first.get("lambda_passed") is True and second.get("lambda_passed") is True,
        "omega_admitted": complete and first.get("omega_admitted") is True and second.get("omega_admitted") is True,
    }
    return {**payload, "pair_sha256": _digest(payload)}
