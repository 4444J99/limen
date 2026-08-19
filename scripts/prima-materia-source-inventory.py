#!/usr/bin/env python3
"""Independently re-enumerate every source instance in a frozen wave."""

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
    SourceInventoryReceiptV1,
    denominator_identifier,
    discover_repository_denominator,
    frozen_wave_digest,
    load_frozen_wave,
    load_storage_inventory_roots,
    physical_device_projection,
    protected_process_projection,
    registered_worktree_denominator,
    source_inventory_producer_digest,
)
from limen.prima_materia import FrozenSourceInstanceV1
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
    result.add_argument("--repository-search-root", action="append", default=[], type=Path)
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
    result.add_argument("--frozen-wave", type=Path, required=True)
    result.add_argument("--max-seconds", type=int, default=300)
    result.add_argument("--output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if not 30 <= arguments.max_seconds <= 1800:
            raise ValueError("--max-seconds must be between 30 and 1800")
        deadline = time.monotonic() + arguments.max_seconds
        repository_root = arguments.repository_root.expanduser().resolve(strict=True)
        wave = load_frozen_wave(arguments.frozen_wave)
        wave_sha256 = frozen_wave_digest(wave)
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
            else:
                values = []
                enumerator_complete = False
            if not values:
                values = [_instance(source_id, "empty-denominator")]
            instances.extend(values)
        instances.sort(key=lambda item: item.instance_id)
        observed = tuple(instances)
        complete = (
            wave.enumeration_complete
            and repositories_complete
            and registered_complete
            and enumerator_complete
            and observed == wave.source_instances
            and time.monotonic() <= deadline
        )
        producer_digest = source_inventory_producer_digest(
            Path(__file__),
            arguments.source_enumerators,
        )
        receipt = SourceInventoryReceiptV1(
            observed_at=datetime.now(UTC),
            frozen_wave_sha256=wave_sha256,
            producer_digest=producer_digest,
            complete=complete,
            source_instances=observed,
        )
        _write_json(arguments.output, receipt.model_dump(mode="json"))
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"prima-materia-source-inventory: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "schema": "limen.prima_materia_source_inventory_run.v1",
                "complete": receipt.complete,
                "source_instance_count": len(receipt.source_instances),
                "frozen_wave_sha256": receipt.frozen_wave_sha256,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
