#!/usr/bin/env python3
"""Fail-closed Phase 0 predicates for consulting authority packets.

``prepare`` proves that an unsigned public-safe workshop packet is complete and
truthfully non-authoritative. ``authorize`` additionally validates a redacted
receipt issued from the client's private authority owner. It never treats a
prepared packet, a signature-shaped string, or vendor intent as client authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

REQUIRED_ROLES = {
    "executive_sponsor",
    "product_owner",
    "legal_compliance_owner",
    "it_security_owner",
    "records_owner",
    "communications_owner",
    "cultural_content_steward",
    "release_authority",
}

REQUIRED_GATES = {
    "discovery_sow",
    "confidentiality_and_data_processing",
    "security_review",
    "change_control",
    "acceptance_process",
    "named_owners",
    "data_boundary",
    "authority_statement",
    "delivery_accounts",
}

REQUIRED_ACCOUNTS = {
    "repositories",
    "azure_subscription",
    "identity_registrations",
    "domain_and_dns",
    "keys",
    "backups",
    "logs",
    "audit_exports",
}

REQUIRED_ARTIFACTS = {
    "product_boundary",
    "technical_contract",
    "delivery_roadmap",
    "acceptance_contract",
    "public_sources",
    "authority_workshop",
    "unsigned_charter",
}

FALSE_AUTHORITY_FLAGS = {
    "bbnc_commissioned",
    "workshop_conducted",
    "charter_executed",
    "phase_1_authorized",
    "production_access_authorized",
    "bbnc_repository_creation_authorized",
    "public_representation_authorized",
    "software_may_interpret_policy",
}

FALSE_DISCLOSURE_FLAGS = {
    "contains_personal_data",
    "contains_pricing",
    "contains_credentials",
    "contains_bbnc_private_material",
    "asserts_client_relationship",
}

SENSITIVE_KEY_PARTS = ("password", "secret", "access_token", "private_key")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("document root must be a JSON object")
    return data


def canonical_digest(document: dict[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _exact_ids(
    items: Any,
    key: str,
    required: set[str],
    label: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        errors.append(f"{label} must be a list")
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        item_id = item.get(key)
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"{label}[{index}].{key} must be a non-empty string")
            continue
        if item_id in indexed:
            errors.append(f"{label} contains duplicate {key} {item_id!r}")
        indexed[item_id] = item
    actual = set(indexed)
    if actual != required:
        errors.append(
            f"{label} ids must be exactly {sorted(required)}; got {sorted(actual)}"
        )
    return indexed


def _sensitive_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                found.append(f"{path}.{key}")
            found.extend(_sensitive_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_sensitive_keys(child, f"{path}[{index}]"))
    return found


def validate_preparation(
    document: dict[str, Any], *, repo_root: Path = ROOT
) -> list[str]:
    errors: list[str] = []

    if document.get("schema") != "consulting.phase0.preparation.v1":
        errors.append("schema must be consulting.phase0.preparation.v1")
    if document.get("engagement_id") != "bbnc-stewardship-to-bbnc-net":
        errors.append("engagement_id must bind the BBNC Stewardship to BBNC.net packet")
    if document.get("state") != "workshop_ready":
        errors.append("prepared public packet state must be workshop_ready")
    if not _timestamp(document.get("prepared_at")):
        errors.append("prepared_at must be an ISO-8601 UTC timestamp")

    disclosure = document.get("disclosure")
    if not isinstance(disclosure, dict):
        errors.append("disclosure must be an object")
    else:
        if disclosure.get("classification") != "public":
            errors.append("prepared packet classification must be public")
        for flag in sorted(FALSE_DISCLOSURE_FLAGS):
            if disclosure.get(flag) is not False:
                errors.append(f"disclosure.{flag} must be false")

    client = document.get("client")
    if not isinstance(client, dict) or client.get("authority_owner") != "BBNC":
        errors.append("client.authority_owner must be BBNC")

    delivery_party = document.get("delivery_party")
    if not isinstance(delivery_party, dict):
        errors.append("delivery_party must be an object")
    else:
        if delivery_party.get("name") != "Padavano":
            errors.append("delivery_party.name must use the live Padavano identity")
        if delivery_party.get("has_bbnc_authority") is not False:
            errors.append("delivery_party.has_bbnc_authority must be false")

    authority = document.get("authority")
    if not isinstance(authority, dict):
        errors.append("authority must be an object")
    else:
        if set(authority) != FALSE_AUTHORITY_FLAGS:
            errors.append(
                "authority flags must be exactly the fail-closed preparation set"
            )
        for flag in sorted(FALSE_AUTHORITY_FLAGS):
            if authority.get(flag) is not False:
                errors.append(f"authority.{flag} must be false before BBNC receipt")

    roles = _exact_ids(
        document.get("required_roles"),
        "role_id",
        REQUIRED_ROLES,
        "required_roles",
        errors,
    )
    for role_id, role in roles.items():
        if role.get("owner") != "BBNC":
            errors.append(f"required_roles[{role_id}].owner must be BBNC")
        if role.get("assignment_state") != "pending_bbnc_nomination":
            errors.append(
                f"required_roles[{role_id}] must remain pending_bbnc_nomination"
            )
        if "principal_ref" in role or "person" in role:
            errors.append(f"required_roles[{role_id}] exposes a personal assignment")

    gates = _exact_ids(
        document.get("gates"), "gate_id", REQUIRED_GATES, "gates", errors
    )
    for gate_id, gate in gates.items():
        if gate.get("state") != "open":
            errors.append(f"gates[{gate_id}] must be open in the prepared packet")
        if "evidence_digest" in gate or "evidence_ref" in gate:
            errors.append(f"gates[{gate_id}] must not claim authority evidence")

    accounts = _exact_ids(
        document.get("delivery_accounts"),
        "account_id",
        REQUIRED_ACCOUNTS,
        "delivery_accounts",
        errors,
    )
    for account_id, account in accounts.items():
        if account.get("owner") != "BBNC":
            errors.append(f"delivery_accounts[{account_id}].owner must be BBNC")
        if account.get("state") != "not_provisioned":
            errors.append(
                f"delivery_accounts[{account_id}] must be not_provisioned"
            )
        if "locator" in account or "evidence_digest" in account:
            errors.append(f"delivery_accounts[{account_id}] exposes owner state")

    data_boundary = document.get("data_boundary")
    if not isinstance(data_boundary, dict):
        errors.append("data_boundary must be an object")
    else:
        if data_boundary.get("packet_classification") != "public":
            errors.append("data_boundary.packet_classification must be public")
        if data_boundary.get("proposed_v1_stored_classes") != [
            "public",
            "bbnc_approved_internal",
        ]:
            errors.append("v1 stored classes must be public and BBNC-approved internal")
        if data_boundary.get("owner_system_only_classes") != [
            "confidential",
            "restricted",
        ]:
            errors.append("confidential and restricted must remain owner-system only")
        if data_boundary.get("unknown_defaults_to") != "restricted":
            errors.append("unknown classification must default to restricted")

    if document.get("accepted_work_package") is not None:
        errors.append("prepared packet must not claim an accepted work package")

    receipt = document.get("authority_receipt")
    if not isinstance(receipt, dict):
        errors.append("authority_receipt must be an object")
    elif receipt != {
        "state": "absent",
        "owner": "BBNC",
        "required_schema": "bbnc.phase0.authority-receipt.v1",
    }:
        errors.append("authority_receipt must remain absent and BBNC-owned")

    artifacts = _exact_ids(
        document.get("artifact_refs"),
        "artifact_id",
        REQUIRED_ARTIFACTS,
        "artifact_refs",
        errors,
    )
    resolved_root = repo_root.resolve()
    for artifact_id, artifact in artifacts.items():
        rel = artifact.get("path")
        if not isinstance(rel, str) or not rel:
            errors.append(f"artifact_refs[{artifact_id}].path must be non-empty")
            continue
        candidate = (resolved_root / rel).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            errors.append(f"artifact_refs[{artifact_id}] escapes the repository")
            continue
        if not candidate.is_file():
            errors.append(f"artifact_refs[{artifact_id}] does not exist: {rel}")

    charter = artifacts.get("unsigned_charter")
    if charter and isinstance(charter.get("path"), str):
        charter_path = resolved_root / charter["path"]
        if charter_path.is_file():
            banner = charter_path.read_text(encoding="utf-8")[:500]
            if "UNSIGNED WORKING DRAFT" not in banner or "NOT EFFECTIVE" not in banner:
                errors.append("unsigned charter is missing its non-authority banner")

    sensitive = _sensitive_keys(document)
    if sensitive:
        errors.append(f"packet contains prohibited sensitive keys: {', '.join(sensitive)}")

    return errors


def validate_authority_receipt(
    preparation: dict[str, Any], receipt: dict[str, Any] | None
) -> list[str]:
    errors = validate_preparation(preparation)
    if receipt is None:
        errors.append("BBNC-owned Phase 0 authority receipt is required")
        return errors

    if receipt.get("schema") != "bbnc.phase0.authority-receipt.v1":
        errors.append("receipt schema must be bbnc.phase0.authority-receipt.v1")
    if receipt.get("engagement_id") != preparation.get("engagement_id"):
        errors.append("receipt engagement_id does not match preparation")
    if receipt.get("authority_owner") != "BBNC":
        errors.append("receipt authority_owner must be BBNC")
    if receipt.get("delivery_party") != "Padavano":
        errors.append("receipt delivery_party must be Padavano")
    if receipt.get("preparation_digest") != canonical_digest(preparation):
        errors.append("receipt preparation_digest does not bind the exact packet")
    if not SHA256_RE.fullmatch(str(receipt.get("charter_digest", ""))):
        errors.append("receipt charter_digest must be sha256:<64 lowercase hex>")
    if not _timestamp(receipt.get("executed_at")):
        errors.append("receipt executed_at must be an ISO-8601 UTC timestamp")
    if not _timestamp(receipt.get("effective_at")):
        errors.append("receipt effective_at must be an ISO-8601 UTC timestamp")
    if receipt.get("accepted_work_package") != "phase-1-current-state-discovery":
        errors.append("receipt may authorize only phase-1-current-state-discovery")

    grants = receipt.get("grants")
    required_grants = {
        "phase_1_discovery": True,
        "production_access": False,
        "repository_creation": False,
        "public_launch": False,
        "later_work_packages": False,
    }
    if grants != required_grants:
        errors.append("receipt grants must authorize Phase 1 discovery only")

    roles = _exact_ids(
        receipt.get("roles"), "role_id", REQUIRED_ROLES, "receipt.roles", errors
    )
    for role_id, role in roles.items():
        principal_ref = role.get("principal_ref")
        if not isinstance(principal_ref, str) or not principal_ref.strip():
            errors.append(f"receipt.roles[{role_id}] needs an opaque principal_ref")
        if "name" in role:
            errors.append(f"receipt.roles[{role_id}] must not expose a name")

    gates = _exact_ids(
        receipt.get("gates"), "gate_id", REQUIRED_GATES, "receipt.gates", errors
    )
    for gate_id, gate in gates.items():
        if gate.get("state") != "passed":
            errors.append(f"receipt.gates[{gate_id}] must be passed")
        if not SHA256_RE.fullmatch(str(gate.get("evidence_digest", ""))):
            errors.append(f"receipt.gates[{gate_id}] needs an evidence_digest")
        if not isinstance(gate.get("owner_ref"), str) or not gate["owner_ref"].strip():
            errors.append(f"receipt.gates[{gate_id}] needs an opaque owner_ref")

    accounts = _exact_ids(
        receipt.get("delivery_accounts"),
        "account_id",
        REQUIRED_ACCOUNTS,
        "receipt.delivery_accounts",
        errors,
    )
    for account_id, account in accounts.items():
        if account.get("owner") != "BBNC":
            errors.append(f"receipt.delivery_accounts[{account_id}].owner must be BBNC")
        if not SHA256_RE.fullmatch(str(account.get("evidence_digest", ""))):
            errors.append(
                f"receipt.delivery_accounts[{account_id}] needs an evidence_digest"
            )

    if receipt.get("signatures_verified") is not True:
        errors.append("receipt must attest signatures_verified true")
    verification = receipt.get("verification")
    if not isinstance(verification, dict):
        errors.append("receipt verification must be an object")
    else:
        if verification.get("verified_by_role") not in {
            "legal_compliance_owner",
            "release_authority",
        }:
            errors.append("receipt verification must be owned by an authorized BBNC role")
        if not _timestamp(verification.get("verified_at")):
            errors.append("receipt verification.verified_at must be an ISO-8601 UTC timestamp")

    sensitive = _sensitive_keys(receipt)
    if sensitive:
        errors.append(f"receipt contains prohibited sensitive keys: {', '.join(sensitive)}")

    return errors


def _report(label: str, errors: list[str], quiet: bool) -> int:
    if errors:
        if not quiet:
            print(f"FAIL  {label}")
            for error in errors:
                print(f"      {error}")
        return 1
    if not quiet:
        print(f"PASS  {label}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="validate workshop readiness")
    prepare.add_argument("--packet", required=True, type=Path)
    prepare.add_argument("--quiet", action="store_true")

    authorize = subparsers.add_parser(
        "authorize", help="validate an external BBNC authority receipt"
    )
    authorize.add_argument("--packet", required=True, type=Path)
    authorize.add_argument("--receipt", required=True, type=Path)
    authorize.add_argument("--quiet", action="store_true")

    args = parser.parse_args()
    try:
        packet = load_json(args.packet)
        if args.command == "prepare":
            return _report(str(args.packet), validate_preparation(packet), args.quiet)
        receipt = load_json(args.receipt)
        return _report(
            str(args.receipt), validate_authority_receipt(packet, receipt), args.quiet
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if not args.quiet:
            print(f"FAIL  {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
