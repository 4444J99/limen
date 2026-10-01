#!/usr/bin/env python3
"""Validate coverage declarations, not the truth of services or evidence payloads.

No network, writes, credential access, task transitions, or external actions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

BASE = Path(__file__).resolve().parent
ID = re.compile(r"IC-(D|C|P)[0-9]{3}\Z")
KINDS = {"D": "domain", "C": "capability", "P": "practice"}
STATES = {"not_assessed", "planned", "available", "operating", "verified", "blocked"}
APPLICABILITY = {"unknown", "active", "contingent", "not_applicable", "declined"}
REQUIRED_EVIDENCE = {
    "purpose", "consent", "owner_acceptance", "provider_access",
    "resources", "workflow", "outcome", "fallback",
}


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone is required")
    return parsed.astimezone(timezone.utc)


def validate_catalog(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["catalog: object required"]
    if data.get("schema_version") != "institutional.coverage.v1":
        errors.append("catalog: unsupported schema_version")
    if data.get("registry_id") != "institutional-coverage":
        errors.append("catalog: wrong registry_id")
    policy = data.get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    for key in ("new_repositories_required", "changes_default_streams", "stores_personal_records", "runtime_activated", "automatic_authority_expansion"):
        if policy.get(key) is not False:
            errors.append(f"catalog: unsafe or missing policy {key}")
    snapshot = data.get("source_snapshot", {})
    if not isinstance(snapshot, dict) or not re.fullmatch(r"[0-9a-f]{40}", str(snapshot.get("commit_sha", ""))):
        errors.append("catalog: exact source commit required")
    sources = data.get("sources", {})
    if not isinstance(sources, dict):
        sources = {}
        errors.append("catalog: sources must be an object")
    rows = data.get("responsibilities")
    if not isinstance(rows, list) or not rows:
        return errors + ["catalog: nonempty responsibilities required"]
    ids: set[str] = set()
    for index, row in enumerate(rows):
        where = f"catalog row {index}"
        if not isinstance(row, dict):
            errors.append(f"{where}: object required")
            continue
        key = row.get("id")
        match = ID.fullmatch(key) if isinstance(key, str) else None
        if not match:
            errors.append(f"{where}: invalid stable ID")
        else:
            if key in ids:
                errors.append(f"{where}: duplicate stable ID")
            ids.add(key)
            if row.get("kind") != KINDS[match.group(1)]:
                errors.append(f"{where}: ID and kind disagree")
        for field in ("label", "accountable_function", "outcome", "first_acceptance", "boundary"):
            if not text(row.get(field)):
                errors.append(f"{where}: missing {field}")
        if row.get("owner_binding") != "proposed":
            errors.append(f"{where}: catalog roles are not accepted personal assignments")
        if row.get("service_state") != "not_assessed":
            errors.append(f"{where}: generic catalog cannot certify personal coverage")
        refs = row.get("source_refs")
        if not isinstance(refs, list) or any(not isinstance(r, str) or r not in sources for r in refs):
            errors.append(f"{where}: unresolved source reference")
        else:
            expected = ("partial_declared", "extend") if refs else ("unmapped", "discover")
            if (row.get("binding"), row.get("disposition")) != expected:
                errors.append(f"{where}: evidence and disposition disagree")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        links = row.get("handoffs")
        if not isinstance(links, list) or any(not isinstance(k, str) or k not in ids for k in links):
            errors.append(f"catalog row {index}: unresolved handoff")
    aliases = data.get("legacy_term_crosswalk")
    if not isinstance(aliases, dict) or not aliases or any(
        not text(alias) or not isinstance(target, str) or target not in ids
        for alias, target in aliases.items()
    ):
        errors.append("catalog: legacy term crosswalk must resolve to stable IDs")
    return errors


def check_evidence(item: Any, now: datetime) -> bool:
    if not isinstance(item, dict) or not text(item.get("ref")):
        return False
    try:
        observed = timestamp(item.get("observed_at"))
        until = timestamp(item.get("valid_until"))
        return observed <= now < until and observed < until
    except (TypeError, ValueError, OverflowError):
        return False


def validate_instance(data: Any, catalog: dict[str, Any], now: datetime) -> list[str]:
    """Require complete disposition and fresh evidence references; never fetch payloads."""
    if not isinstance(data, dict):
        return ["instance: object required"]
    errors: list[str] = []
    if data.get("schema_version") != "institutional.coverage-instance.v1":
        errors.append("instance: unsupported schema_version")
    if data.get("catalog_id") != catalog.get("registry_id"):
        errors.append("instance: wrong catalog_id")
    if not text(data.get("subject_ref")) or not isinstance(data.get("synthetic"), bool):
        errors.append("instance: subject_ref and explicit synthetic flag required")
    rows = data.get("records")
    if not isinstance(rows, list):
        return errors + ["instance: records must be a list"]
    expected = {r["id"] for r in catalog["responsibilities"]}
    seen: set[str] = set()
    for index, row in enumerate(rows):
        where = f"instance row {index}"  # Never echo names, references, or personal payloads.
        if not isinstance(row, dict):
            errors.append(f"{where}: object required")
            continue
        key = row.get("responsibility_id")
        if not isinstance(key, str) or key not in expected:
            errors.append(f"{where}: unknown responsibility")
        elif key in seen:
            errors.append(f"{where}: duplicate responsibility")
        else:
            seen.add(key)
        applicability, state = row.get("applicability"), row.get("service_state")
        if not isinstance(applicability, str) or applicability not in APPLICABILITY:
            errors.append(f"{where}: invalid applicability")
            applicability = ""
        if not isinstance(state, str) or state not in STATES:
            errors.append(f"{where}: invalid service_state")
            state = ""
        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            evidence = {}
            errors.append(f"{where}: evidence must be an object")
        if applicability in {"not_applicable", "declined"}:
            if not text(row.get("disposition_reason")) or not text(row.get("authority_ref")):
                errors.append(f"{where}: exclusion requires a reason and authority")
            if not check_evidence(evidence.get("applicability"), now):
                errors.append(f"{where}: exclusion requires current applicability evidence")
            if state != "not_assessed":
                errors.append(f"{where}: excluded responsibility cannot claim a service state")
        if state in {"available", "operating", "verified"}:
            for field in ("accountable_owner_ref", "delivery_provider_ref", "authority_ref"):
                if not text(row.get(field)):
                    errors.append(f"{where}: missing {field}")
            if applicability not in {"active", "contingent"}:
                errors.append(f"{where}: service readiness requires an applicable responsibility")
        if state == "verified":
            if applicability != "active":
                errors.append(f"{where}: delivered outcome requires active applicability")
            for field in sorted(REQUIRED_EVIDENCE):
                if not check_evidence(evidence.get(field), now):
                    errors.append(f"{where}: missing, stale or invalid {field} evidence")
        if state == "blocked" and not text(row.get("blocker_ref")):
            errors.append(f"{where}: blocked state requires a blocker reference")
    if seen != expected:
        errors.append("instance: every catalog responsibility needs an explicit disposition")
    return errors


def load_json(path: Path) -> Any:
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Input exceeds two MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=BASE / "registry.json")
    parser.add_argument("--instance", type=Path)
    parser.add_argument("--as-of", help="Timezone-aware ISO timestamp; defaults to current UTC")
    args = parser.parse_args()
    try:
        now = timestamp(args.as_of) if args.as_of else datetime.now(timezone.utc)
        catalog = load_json(args.catalog)
        errors = validate_catalog(catalog)
        instance = load_json(args.instance) if args.instance else None
        if args.instance is not None and not errors:
            errors.extend(validate_instance(instance, catalog, now))
        result: dict[str, Any] = {"declarations_valid": not errors, "errors": errors,
            "service_delivery_certified": False, "evidence_payloads_verified": False}
        if not errors:
            rows = catalog["responsibilities"]
            result["responsibility_counts"] = dict(Counter(r["kind"] for r in rows))
            result["binding_counts"] = dict(Counter(r["binding"] for r in rows))
            if instance is not None:
                result["synthetic_instance"] = instance["synthetic"]
                result["service_state_counts"] = dict(Counter(r["service_state"] for r in instance["records"]))
                result["applicability_counts"] = dict(Counter(r["applicability"] for r in instance["records"]))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if errors else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # Exception text may contain private paths or JSON fragments; report its type only.
        print(json.dumps({"declarations_valid": False, "error_type": type(exc).__name__,
                          "service_delivery_certified": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
