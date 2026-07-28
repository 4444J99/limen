#!/usr/bin/env python3
"""Produce two independently bounded, frozen-wave alpha-to-omega audits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.alpha_omega import (
    MAX_FROZEN_ROOTS,
    build_reconciliation_manifest,
    control_plane_projection,
    denominator_identifier,
    discover_repository_denominator,
    fixed_point_pair,
    load_frozen_wave,
    load_lambda_rungs,
    load_reclaim_census,
    load_source_inventory,
    load_storage_inventory_roots,
    physical_device_projection,
    predicate_state_digest,
    protected_process_projection,
    registered_worktree_denominator,
)
from limen.prima_materia_store import SourceRegistry
from limen.protected_exclusions import ProtectedExclusionRegistry
from limen.resource_envelope import load_task_graph_claims, observe_resource_telemetry

CommandRunner = Callable[
    [list[str], Path | None, int],
    subprocess.CompletedProcess[str],
]


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
    result.add_argument("--frozen-wave", type=Path, required=True)
    result.add_argument("--source-inventory", type=Path, required=True)
    result.add_argument("--reclaim-census", type=Path, required=True)
    result.add_argument("--resource-task-graph", type=Path, required=True)
    result.add_argument(
        "--source-registry",
        type=Path,
        default=ROOT / "institutio" / "governance" / "prima-materia-source-registry.json",
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
    result.add_argument(
        "--max-seconds",
        type=int,
        default=300,
        help="Independent deadline for each audit (30..1800 seconds).",
    )
    result.add_argument(
        "--max-threads",
        type=int,
        default=3,
        help="Local repository probe threads (1..3).",
    )
    result.add_argument("--output", type=Path)
    return result


def _bounded_runner(deadline: float) -> CommandRunner:
    def run(
        command: list[str],
        cwd: Path | None,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return subprocess.CompletedProcess(
                command,
                124,
                "",
                "alpha-omega-audit-deadline-exhausted",
            )
        try:
            return subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                check=False,
                timeout=min(timeout, max(0.1, remaining)),
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                command,
                124,
                "",
                "alpha-omega-command-timeout",
            )
        except OSError as exc:
            return subprocess.CompletedProcess(
                command,
                127,
                "",
                type(exc).__name__,
            )

    return run


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if not 30 <= arguments.max_seconds <= 1800:
            raise ValueError("--max-seconds must be between 30 and 1800")
        if not 1 <= arguments.max_threads <= 3:
            raise ValueError("--max-threads must be between 1 and 3")
        repository_root = arguments.repository_root.expanduser().resolve(strict=True)
        explicit_repositories = _parse_mapping(arguments.repository, "--repository")
        explicit_private_roots = _parse_mapping(
            arguments.private_root,
            "--private-root",
        )
        frozen_wave = load_frozen_wave(arguments.frozen_wave)
        source_inventory = load_source_inventory(arguments.source_inventory)
        reclaim_census = load_reclaim_census(arguments.reclaim_census)
        lambda_rungs = load_lambda_rungs(arguments.lambda_rungs)
        source_registry = SourceRegistry.load(arguments.source_registry)
        protected_registry = ProtectedExclusionRegistry.load(
            repository_root,
            arguments.protected_registry,
        )
        resource_claims = load_task_graph_claims(arguments.resource_task_graph)
        task_graph_digest = hashlib.sha256(arguments.resource_task_graph.read_bytes()).hexdigest()

        def audit() -> dict[str, object]:
            deadline = time.monotonic() + arguments.max_seconds
            runner = _bounded_runner(deadline)
            repositories, discovery_complete = discover_repository_denominator(
                arguments.repository_search_root,
                deadline=deadline,
            )
            registered, registrations_complete = registered_worktree_denominator(
                repository_root,
                runner,
            )
            repositories.update(registered)
            repositories.update(explicit_repositories)
            repositories.setdefault(
                denominator_identifier("repository", repository_root),
                repository_root,
            )
            if len(repositories) > MAX_FROZEN_ROOTS:
                raise ValueError("combined repository census exceeded the bounded limit")
            private_roots = load_storage_inventory_roots(arguments.storage_inventory)
            private_roots.update(explicit_private_roots)
            if len(private_roots) > MAX_FROZEN_ROOTS:
                raise ValueError("combined private-root census exceeded the bounded limit")
            devices = physical_device_projection(runner=runner)
            processes = protected_process_projection(
                protected_registry,
                runner=runner,
            )
            control_plane = control_plane_projection(
                repository_root,
                frozen_wave,
                runner=runner,
            )
            manifest = build_reconciliation_manifest(
                repository_root=repository_root,
                frozen_wave=frozen_wave,
                repositories=repositories,
                private_roots=private_roots,
                source_registry=source_registry,
                source_inventory=source_inventory,
                protected_registry=protected_registry,
                resource_claims=resource_claims,
                resource_task_graph_digest=task_graph_digest,
                reclaim_census=reclaim_census,
                lambda_rungs=lambda_rungs,
                resource_telemetry=observe_resource_telemetry(),
                physical_devices=devices,
                protected_processes=processes,
                control_plane=control_plane,
                audit_deadline_seconds=arguments.max_seconds,
                observed_at=datetime.now(UTC),
                runner=runner,
                max_workers=arguments.max_threads,
            )
            if not discovery_complete or not registrations_complete:
                state = manifest["state"]
                if isinstance(state, dict):
                    state["audit_complete"] = False
                    incomplete = state.get("incomplete_inputs", [])
                    if isinstance(incomplete, list):
                        incomplete.append("repository_enumeration_complete")
                        state["incomplete_inputs"] = sorted(set(incomplete))
                    manifest["state_sha256"] = predicate_state_digest(state)
                manifest["audit_complete"] = False
                manifest["lambda_passed"] = False
                manifest["omega_admitted"] = False
            return manifest

        first = audit()
        second = audit()
        fixed_point = fixed_point_pair(first, second)
        payload: dict[str, object] = {
            "schema": "limen.alpha_omega_reconciliation_receipt.v2",
            "audit_deadline_seconds_each": arguments.max_seconds,
            "max_local_probe_threads": arguments.max_threads,
            "first": first,
            "second": second,
            "fixed_point": fixed_point,
        }
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(
            json.dumps(
                {
                    "schema": "limen.alpha_omega_reconciliation_error.v2",
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    if arguments.output:
        _write_json(arguments.output, payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if fixed_point["omega_admitted"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
