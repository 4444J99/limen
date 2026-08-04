#!/usr/bin/env python3
"""Validate the project-neutral collaboration-operations boundary contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "institutio" / "collaboration-operations" / "platform.yaml"
ESTATE = ROOT / "institutio" / "github" / "estate.yaml"
ACCESS = ROOT / "institutio" / "github" / "access.yaml"
CONSTELLATION = ROOT / "organs" / "consulting" / "constellation" / "registry.yaml"

PLATFORM_REPO = "organvm-iii-ergon/collaboration-operations-platform"


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return data


def person(register: dict[str, Any], slug: str) -> dict[str, Any] | None:
    return next(
        (row for row in register.get("people") or [] if isinstance(row, dict) and row.get("slug") == slug),
        None,
    )


def project(register: dict[str, Any], slug: str, name: str) -> dict[str, Any] | None:
    row = person(register, slug)
    if row is None:
        return None
    return next(
        (item for item in row.get("projects") or [] if isinstance(item, dict) and item.get("name") == name),
        None,
    )


def validate_documents(
    contract: dict[str, Any],
    estate: dict[str, Any],
    access: dict[str, Any],
    register: dict[str, Any],
    *,
    selected_person: str | None = None,
) -> list[str]:
    errors: list[str] = []

    if contract.get("schema_version") != "limen.collaboration_operations.v1":
        errors.append("contract schema_version must be limen.collaboration_operations.v1")

    platform = contract.get("platform") or {}
    expected_platform = {
        "repository": PLATFORM_REPO,
        "state": "prepared_not_created",
        "estate_class": "operation_private",
        "audience": "self",
        "collaborator_grants": [],
        "fixture_policy": "synthetic_only",
        "purpose": "universal_private_collaboration_operations_and_records",
        "scope": "all_current_and_future_collaborations_and_clients",
        "record_model": "central_private_hub_with_owner_partitions",
    }
    for key, expected in expected_platform.items():
        if platform.get(key) != expected:
            errors.append(f"platform.{key} must be {expected!r}")

    bootstrap = platform.get("bootstrap") or {}
    if bootstrap.get("required_lever") != "L-COLLABORATION-OPERATIONS-PLATFORM-GENESIS":
        errors.append("platform bootstrap must retain the repository-creation lever")
    if "--dry-run" not in str(bootstrap.get("dry_run_command") or ""):
        errors.append("platform bootstrap command must remain a dry run")

    flow = contract.get("flow_policy") or {}
    required_flow = {
        "studio_code": "reusable_across_lanes",
        "collaboration_records": "private_platform_owner_partition_only",
        "client_content": "private_platform_owner_partition_only",
        "cross_client_content": "forbidden",
        "live_client_fixtures": "forbidden",
    }
    for key, expected in required_flow.items():
        if flow.get(key) != expected:
            errors.append(f"flow_policy.{key} must be {expected!r}")

    override = (estate.get("repo_overrides") or {}).get(PLATFORM_REPO) or {}
    if override.get("class") != "operation_private":
        errors.append(f"estate override for {PLATFORM_REPO} must be operation_private")
    if override.get("audience") != "self":
        errors.append(f"estate override for {PLATFORM_REPO} must declare audience self")
    estate_why = str(override.get("why") or "")
    if "universal private collaboration" not in estate_why or "partitioned" not in estate_why:
        errors.append(f"estate override for {PLATFORM_REPO} must describe the universal partitioned records hub")
    if (access.get("grants") or {}).get(PLATFORM_REPO):
        errors.append(f"{PLATFORM_REPO} must have no collaborator grant rows")

    lanes = contract.get("lanes") or {}
    if selected_person and selected_person not in lanes:
        errors.append(f"unknown collaboration person: {selected_person}")
        return errors

    wanted = {selected_person} if selected_person else {"david", "maddie", "ari"}

    if "david" in wanted:
        lane = lanes.get("david") or {}
        david_project = project(register, "david", "victoroff-os") or {}
        if lane.get("owner") != "persona:david" or lane.get("project") != "project:victoroff-os":
            errors.append("David lane must be owned by persona:david and project:victoroff-os")
        if lane.get("repository") != "4444J99/victoroff-os" or david_project.get("repo") != lane.get("repository"):
            errors.append("David lane must reference the constellation-owned 4444J99/victoroff-os repository")
        if lane.get("state") != "mostly_complete_external":
            errors.append("David lane must remain mostly_complete_external")
        if lane.get("mutation_authority") != "external_owner_lane_only":
            errors.append("David lane must deny platform-genesis mutation authority")
        issues = ((lane.get("source_references") or {}).get("github_issues") or [])
        if [item.get("number") for item in issues if isinstance(item, dict)] != [2, 3, 17, 27]:
            errors.append("David lane must preserve GitHub issues #2, #3, #17, and #27 as external references")
        series = ((lane.get("source_references") or {}).get("packet_series") or {})
        if (series.get("first"), series.get("last"), series.get("count")) != ("RW-001", "RW-010", 10):
            errors.append("David lane must preserve external packet references RW-001 through RW-010")

    if "maddie" in wanted:
        lane = lanes.get("maddie") or {}
        maddie_project = project(register, "maddie", "spiral") or {}
        grants = (access.get("grants") or {}).get("4444J99/sovereign-systems--elevate-align") or []
        if lane.get("repository") != maddie_project.get("repo"):
            errors.append("Maddie lane must reference the constellation-owned spiral repository")
        if lane.get("state") != "build_lane_closed":
            errors.append("Maddie build lane must remain closed")
        if len(grants) != 1 or grants[0].get("person") != "maddie" or grants[0].get("role") != "push":
            errors.append("Maddie lane must retain exactly one push-only grant")

    if "ari" in wanted:
        lane = lanes.get("ari") or {}
        ari_project = project(register, "ari", "podcast-suite") or {}
        if lane.get("repository") != ari_project.get("repo"):
            errors.append("Ari lane must reference the constellation-owned HOSPES repository")
        if lane.get("state") != "vault_split_required" or lane.get("content_class") != "vault_private":
            errors.append("Ari transcripts must remain vault-class behind the required split")
        if lane.get("custody_gate") != "transcript_vault_split_before_movement":
            errors.append("Ari custody movement must remain gated on the transcript vault split")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    parser.add_argument("--person", choices=("david", "maddie", "ari"))
    args = parser.parse_args()

    try:
        errors = validate_documents(
            load_yaml(args.contract),
            load_yaml(ESTATE),
            load_yaml(ACCESS),
            load_yaml(CONSTELLATION),
            selected_person=args.person,
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"collaboration-operations: invalid input: {exc}", file=sys.stderr)
        return 2

    for error in errors:
        print(f"FAIL {error}")
    if errors:
        print(f"collaboration-operations: {len(errors)} boundary failure(s)")
        return 1
    scope = args.person or "all lanes"
    print(
        f"collaboration-operations: OK — {scope}; universal private records hub, "
        "partitioned, synthetic-only, owner-routed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
