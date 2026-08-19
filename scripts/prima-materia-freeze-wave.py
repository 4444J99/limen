#!/usr/bin/env python3
"""Freeze one alpha-to-omega denominator for independent source re-enumeration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.alpha_omega import (
    denominator_identifier,
    discover_repository_denominator,
    frozen_wave_digest,
    lambda_rung_registry_digest,
    load_lambda_rungs,
    load_storage_inventory_roots,
    physical_device_projection,
    protected_process_projection,
    registered_worktree_denominator,
    source_inventory_producer_digest,
)
from limen.prima_materia import (
    FrozenDeviceRoleV1,
    FrozenRepositoryV1,
    FrozenSourceInstanceV1,
    FrozenStorageRootV1,
    FrozenWaveManifestV1,
)
from limen.prima_materia_store import SourceRegistry
from limen.protected_exclusions import ProtectedExclusionRegistry
from limen.resource_envelope import observe_resource_telemetry

ENUMERATOR_SCHEMA = "limen.prima_materia_source_enumerators.v1"
ENUMERATOR_KINDS = {
    "repository",
    "physical_device",
    "private_root",
    "protected_process",
    "resource_telemetry",
    "source_registry",
}


def _path_digest(path: Path) -> str:
    return hashlib.sha256(str(path.resolve(strict=False)).encode()).hexdigest()


def _instance(source_id: str, identity: str) -> FrozenSourceInstanceV1:
    digest = hashlib.sha256(f"{source_id}\0{identity}".encode()).hexdigest()
    return FrozenSourceInstanceV1(
        instance_id=f"sourceInstance{digest[:24]}",
        source_id=source_id,
    )


def _parse_mapping(values: list[str], label: str) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{label} must use ID=PATH")
        identifier, raw_path = value.split("=", 1)
        if not identifier or identifier in parsed or not raw_path:
            raise ValueError(f"{label} contains an invalid or duplicate ID")
        parsed[identifier] = Path(raw_path).expanduser()
    return parsed


def _enumerators(path: Path) -> tuple[tuple[str, str], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("enumerators") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "enumerators"}
        or payload.get("schema") != ENUMERATOR_SCHEMA
        or not isinstance(rows, list)
    ):
        raise ValueError("source enumerator registry is invalid")
    result = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"kind", "source_id"}
            or row.get("kind") not in ENUMERATOR_KINDS
            or not isinstance(row.get("source_id"), str)
        ):
            raise ValueError("source enumerator descriptor is invalid")
        result.append((row["kind"], row["source_id"]))
    kinds = [kind for kind, _source_id in result]
    source_ids = [source_id for _kind, source_id in result]
    if (
        len(kinds) != len(set(kinds))
        or len(source_ids) != len(set(source_ids))
        or tuple(sorted(result)) != tuple(result)
    ):
        raise ValueError("source enumerator registry must be unique and sorted")
    return tuple(result)


def _runtime_control_plane(
    repository_root: Path,
) -> tuple[str, str, str, str, str]:
    status = subprocess.run(
        ["domus-limen-runtime", "status"],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if status.returncode != 0:
        raise ValueError("installed immutable runtime receipt is unavailable")
    payload = json.loads(status.stdout)
    receipt = payload.get("receipt") if isinstance(payload, dict) else None
    if not isinstance(receipt, dict):
        raise TypeError("installed immutable runtime receipt is invalid")
    repository = str(receipt.get("repository") or "")
    installed_sha = str(receipt.get("sha") or "")
    default_branch = str(receipt.get("default_branch") or "")
    runtime_path = payload.get("runtime") if isinstance(payload, dict) else None
    if (
        not repository
        or not default_branch
        or len(installed_sha) != 40
        or not isinstance(runtime_path, str)
        or not Path(runtime_path).is_dir()
    ):
        raise ValueError("installed immutable runtime receipt is incomplete")
    remote = subprocess.run(
        ["git", "ls-remote", repository, f"refs/heads/{default_branch}"],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    fields = remote.stdout.strip().split()
    if remote.returncode != 0 or len(fields) != 2 or len(fields[0]) != 40:
        raise ValueError("reviewed remote-main authority is unavailable")
    return (
        repository,
        default_branch,
        fields[0],
        installed_sha,
        _path_digest(Path(runtime_path)),
    )


def _device_roles(storage_inventory: Path | None) -> tuple[FrozenDeviceRoleV1, ...]:
    if storage_inventory is None:
        return ()
    payload = json.loads(storage_inventory.read_text(encoding="utf-8"))
    rows = payload.get("custody_devices") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise TypeError("storage inventory device roles are invalid")
    roles = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("physical_device"), str)
        ):
            raise TypeError("storage inventory device role is invalid")
        identifier = Path(row["physical_device"]).name
        roles.append(
            FrozenDeviceRoleV1(
                role_id=row["name"],
                physical_device_sha256=hashlib.sha256(identifier.encode()).hexdigest(),
            )
        )
    return tuple(sorted(roles, key=lambda item: item.role_id))


def _write_json(path: Path, payload: dict[str, object]) -> None:
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
    result.add_argument("--repository-root", type=Path, default=ROOT)
    result.add_argument(
        "--repository-search-root",
        action="append",
        default=[],
        type=Path,
    )
    result.add_argument("--repository", action="append", default=[])
    result.add_argument("--private-root", action="append", default=[])
    result.add_argument("--storage-inventory", type=Path)
    result.add_argument(
        "--source-registry",
        type=Path,
        default=ROOT / "institutio" / "governance" / "prima-materia-source-registry.json",
    )
    result.add_argument(
        "--source-enumerators",
        type=Path,
        default=ROOT / "institutio" / "governance" / "prima-materia-source-enumerators.json",
    )
    result.add_argument(
        "--protected-registry",
        type=Path,
        default=ROOT / "institutio" / "governance" / "reconciliation-protected-exclusions.json",
    )
    result.add_argument(
        "--lambda-rungs",
        type=Path,
        default=ROOT / "institutio" / "governance" / "prima-materia-lambda-rungs.json",
    )
    result.add_argument("--max-seconds", type=int, default=300)
    result.add_argument("--frozen-wave-output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if not 30 <= arguments.max_seconds <= 1800:
            raise ValueError("--max-seconds must be between 30 and 1800")
        started = time.monotonic()
        deadline = started + arguments.max_seconds
        repository_root = arguments.repository_root.expanduser().resolve(strict=True)
        repositories, repositories_complete = discover_repository_denominator(
            arguments.repository_search_root,
            deadline=deadline,
        )
        registered, registered_complete = registered_worktree_denominator(
            repository_root,
            lambda command, cwd, timeout: subprocess.run(
                command,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            ),
        )
        repositories.update(registered)
        repositories.update(_parse_mapping(arguments.repository, "--repository"))
        repositories.setdefault(
            denominator_identifier("repository", repository_root),
            repository_root,
        )
        private_roots = load_storage_inventory_roots(arguments.storage_inventory)
        private_roots.update(_parse_mapping(arguments.private_root, "--private-root"))
        source_registry = SourceRegistry.load(arguments.source_registry)
        lambda_rungs = load_lambda_rungs(arguments.lambda_rungs)
        protected_registry = ProtectedExclusionRegistry.load(
            repository_root,
            arguments.protected_registry,
        )
        devices = physical_device_projection()
        processes = protected_process_projection(protected_registry)
        telemetry_available = True
        try:
            observe_resource_telemetry()
        except RuntimeError:
            telemetry_available = False
        instances: list[FrozenSourceInstanceV1] = []
        enumerator_complete = True
        for kind, source_id in _enumerators(arguments.source_enumerators):
            if kind == "repository":
                values = [_instance(source_id, identifier) for identifier in repositories]
            elif kind == "private_root":
                values = [_instance(source_id, identifier) for identifier in private_roots]
            elif kind == "physical_device":
                identities = devices.get("device_identity_digests") or ()
                values = [_instance(source_id, str(value)) for value in identities]
                enumerator_complete &= devices.get("available") is True
            elif kind == "protected_process":
                values = [_instance(source_id, protected_registry.registry_digest)]
                enumerator_complete &= processes.get("available") is True
            elif kind == "source_registry":
                values = [_instance(source_id, source_registry.registry_digest)]
            elif kind == "resource_telemetry":
                values = [_instance(source_id, "host-resource-telemetry")]
                enumerator_complete &= telemetry_available
            else:  # pragma: no cover - registry validation owns this branch
                raise ValueError("source enumerator kind is unsupported")
            if not values:
                values = [_instance(source_id, "empty-denominator")]
            instances.extend(values)
        instance_ids = [item.instance_id for item in instances]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("independent source inventory produced duplicate instances")
        (
            repository,
            default_branch,
            remote_main_sha,
            installed_runtime_sha,
            runtime_path_sha256,
        ) = _runtime_control_plane(repository_root)
        inventory_producer_digest = source_inventory_producer_digest(
            ROOT / "scripts" / "prima-materia-source-inventory.py",
            arguments.source_enumerators,
        )
        now = datetime.now(UTC)
        freeze_complete = (
            repositories_complete and registered_complete and enumerator_complete and time.monotonic() <= deadline
        )
        wave = FrozenWaveManifestV1(
            wave_id=f"wave{now.strftime('%Y%m%dT%H%M%SZ')}",
            frozen_at=now,
            enumeration_complete=freeze_complete,
            repositories=tuple(
                FrozenRepositoryV1(
                    repository_id=identifier,
                    path_sha256=_path_digest(path),
                )
                for identifier, path in sorted(repositories.items())
            ),
            storage_roots=tuple(
                FrozenStorageRootV1(
                    root_id=identifier,
                    path_sha256=_path_digest(path),
                )
                for identifier, path in sorted(private_roots.items())
            ),
            source_instances=tuple(sorted(instances, key=lambda item: item.instance_id)),
            device_roles=_device_roles(arguments.storage_inventory),
            protected_exclusion_ids=tuple(sorted(item.exclusion_id for item in protected_registry.exclusions)),
            protected_registry_digest=protected_registry.registry_digest,
            source_registry_digest=source_registry.registry_digest,
            source_inventory_producer_digest=inventory_producer_digest,
            lambda_rung_registry_digest=lambda_rung_registry_digest(lambda_rungs),
            remote_main_sha=remote_main_sha,
            installed_runtime_sha=installed_runtime_sha,
            control_plane_runtime_path_sha256=runtime_path_sha256,
            control_plane_repository=repository,
            control_plane_default_branch=default_branch,
        )
        wave_sha256 = frozen_wave_digest(wave)
        _write_json(
            arguments.frozen_wave_output,
            wave.model_dump(mode="json"),
        )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"prima-materia-freeze-wave: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "schema": "limen.prima_materia_freeze_receipt.v1",
                "frozen_wave_sha256": wave_sha256,
                "repository_count": len(wave.repositories),
                "storage_root_count": len(wave.storage_roots),
                "source_instance_count": len(wave.source_instances),
                "complete": wave.enumeration_complete,
            },
            sort_keys=True,
        )
    )
    return 0 if wave.enumeration_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
