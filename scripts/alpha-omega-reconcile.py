#!/usr/bin/env python3
"""Produce two redacted live alpha-to-omega reconciliation audits."""

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
    build_reconciliation_manifest,
    fixed_point_pair,
    physical_device_projection,
    protected_process_projection,
)
from limen.prima_materia_store import SourceRegistry
from limen.protected_exclusions import ProtectedExclusionRegistry
from limen.resource_envelope import observe_resource_telemetry

MAX_REPOSITORIES = 4096
CommandRunner = Callable[
    [list[str], Path | None, int],
    subprocess.CompletedProcess[str],
]
SKIP_DIRECTORIES = {
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


def _identifier(prefix: str, path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve(strict=False)).encode()).hexdigest()
    return f"{prefix}-{digest[:16]}"


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


def _discover_repositories(
    search_roots: list[Path],
    *,
    deadline: float,
) -> tuple[dict[str, Path], bool]:
    found: dict[Path, None] = {}
    complete = True
    for search_root in search_roots:
        root = search_root.expanduser().resolve(strict=False)
        if not root.is_dir():
            continue
        for current, directories, files in os.walk(root, followlinks=False):
            if time.monotonic() >= deadline:
                complete = False
                break
            directories[:] = sorted(name for name in directories if name not in SKIP_DIRECTORIES and name != ".git")
            candidate = Path(current)
            if ".git" in files or (candidate / ".git").is_dir():
                found[candidate.resolve(strict=False)] = None
                if len(found) > MAX_REPOSITORIES:
                    raise ValueError("repository discovery exceeded the bounded limit")
        if not complete:
            break
    return (
        {_identifier("repository", path): path for path in sorted(found, key=str)},
        complete,
    )


def _inventory_private_roots(path: Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("storage inventory is unavailable") from exc
    roots = payload.get("roots") if isinstance(payload, dict) else None
    if not isinstance(roots, list) or len(roots) > MAX_REPOSITORIES:
        raise ValueError("storage inventory roots are invalid")
    result: dict[str, Path] = {}
    for row in roots:
        if not isinstance(row, dict) or not isinstance(row.get("root"), str):
            raise TypeError("storage inventory root is invalid")
        root = Path(row["root"]).expanduser()
        result[_identifier("private-root", root)] = root
    return result


def _base_sha(
    repository_root: Path,
    runner: CommandRunner,
) -> str:
    result = runner(
        ["git", "rev-parse", "HEAD"],
        repository_root,
        30,
    )
    if result.returncode != 0:
        raise ValueError("repository base SHA is unavailable")
    return result.stdout.strip()


def _registered_worktrees(
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
    if len(paths) > MAX_REPOSITORIES:
        raise ValueError("registered worktree census exceeded the bounded limit")
    return (
        {_identifier("worktree", path): path for path in paths},
        True,
    )


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
        "--base-sha",
        help="Exact 40-character merged base SHA; defaults to repository HEAD.",
    )
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
        "--protected-registry",
        type=Path,
        default=ROOT / "institutio" / "governance" / "reconciliation-protected-exclusions.json",
    )
    result.add_argument("--observed-source", action="append", default=[])
    result.add_argument(
        "--safe-reclaim-count",
        type=int,
        help="Exact completed reclaim census count; omission remains visible debt.",
    )
    result.add_argument("--receipt-predicates", type=Path)
    result.add_argument(
        "--max-seconds",
        type=int,
        default=300,
        help="Whole live-probe deadline (30..1800 seconds).",
    )
    result.add_argument("--output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if not 30 <= arguments.max_seconds <= 1800:
            raise ValueError("--max-seconds must be between 30 and 1800")
        deadline = time.monotonic() + arguments.max_seconds

        def bounded_runner(
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
                    "alpha-omega-deadline-exhausted",
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

        repository_root = arguments.repository_root.expanduser().resolve(strict=True)
        base_sha = arguments.base_sha or _base_sha(
            repository_root,
            bounded_runner,
        )
        if len(base_sha) != 40 or any(character not in "0123456789abcdef" for character in base_sha):
            raise ValueError("--base-sha must be a full lowercase Git SHA")
        base_exists = bounded_runner(
            ["git", "cat-file", "-e", f"{base_sha}^{{commit}}"],
            repository_root,
            30,
        )
        if base_exists.returncode != 0:
            raise ValueError("--base-sha is unavailable in the repository object database")
        explicit_repositories = _parse_mapping(
            arguments.repository,
            "--repository",
        )
        explicit_private_roots = _parse_mapping(
            arguments.private_root,
            "--private-root",
        )

        def audit() -> dict[str, object]:
            repositories, discovery_complete = _discover_repositories(
                arguments.repository_search_root,
                deadline=deadline,
            )
            registered, registrations_complete = _registered_worktrees(
                repository_root,
                bounded_runner,
            )
            repositories.update(registered)
            repositories.update(explicit_repositories)
            repositories.setdefault(
                _identifier("repository", repository_root),
                repository_root,
            )
            if len(repositories) > MAX_REPOSITORIES:
                raise ValueError("combined repository census exceeded the bounded limit")
            private_roots = _inventory_private_roots(arguments.storage_inventory)
            private_roots.update(explicit_private_roots)
            if len(private_roots) > MAX_REPOSITORIES:
                raise ValueError("combined private-root census exceeded the bounded limit")
            source_registry = SourceRegistry.load(arguments.source_registry)
            observed_sources = tuple(arguments.observed_source) or tuple(
                adapter.source_id for adapter in source_registry.adapters
            )
            protected_registry = ProtectedExclusionRegistry.load(
                repository_root,
                arguments.protected_registry,
            )
            receipts: dict[str, bool] = {}
            if arguments.receipt_predicates:
                raw_receipts = json.loads(arguments.receipt_predicates.read_text(encoding="utf-8"))
                if not isinstance(raw_receipts, dict) or any(
                    not isinstance(key, str) or not isinstance(value, bool) for key, value in raw_receipts.items()
                ):
                    raise ValueError("receipt predicates must be a boolean object")
                receipts = raw_receipts
            telemetry = observe_resource_telemetry()
            devices = physical_device_projection(runner=bounded_runner)
            processes = protected_process_projection(
                protected_registry,
                runner=bounded_runner,
            )
            return build_reconciliation_manifest(
                repository_root=repository_root,
                base_sha=base_sha,
                repositories=repositories,
                private_roots=private_roots,
                source_registry=source_registry,
                observed_source_ids=observed_sources,
                protected_registry=protected_registry,
                resource_telemetry=telemetry,
                physical_devices=devices,
                protected_processes=processes,
                automatically_safe_reclaim_count=arguments.safe_reclaim_count,
                repository_census_complete=(discovery_complete and registrations_complete),
                receipt_predicates=receipts,
                observed_at=datetime.now(UTC),
                runner=bounded_runner,
            )

        first = audit()
        second = audit()
        payload: dict[str, object] = {
            "schema": "limen.alpha_omega_reconciliation_receipt.v1",
            "first": first,
            "second": second,
            "fixed_point": fixed_point_pair(first, second),
        }
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "schema": "limen.alpha_omega_reconciliation_error.v1",
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
