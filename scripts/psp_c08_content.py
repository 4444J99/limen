#!/usr/bin/env python3
"""Deterministic, no-effect validation and packaging for the PSP-C08 staged content set."""

from __future__ import annotations

import argparse
import json
import re
import runpy
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROGRAM_SCRIPT = REPOSITORY_ROOT / "scripts" / "positioning-program.py"
CONTENT_RELATIVE = Path("docs/positioning/content")
REQUIRED_FILES = (
    "dependency-bindings.json",
    "content-control.json",
    "narrative-fixtures.json",
    "review-gates.json",
    "campaign-analytics-schema.json",
    "freshness-withdrawal-policy.json",
    "dry-run-publication-package.json",
)
WORK_IDS = tuple(f"PSP-P09-W0{number}" for number in range(1, 9))
WORK_ID_SET = set(WORK_IDS)
REQUIRED_BINDINGS = {"P02", "C03", "C04", "C06", "C07"}
ASSIGNMENT_POLICY = {
    "selection": "runtime_catalog",
    "registry": "institutio/positioning/program.yaml",
    "catalog_predicate": "python3 scripts/positioning-program.py --verify-model-assignments",
    "unavailable_action": "fail_blocked_no_silent_substitution",
}
EXPECTED_BINDING_DOCUMENT_KEYS = {
    "schema",
    "state",
    "counts_as_closure",
    "scope",
    "assignment_policy",
    "assignment_requirements",
    "bindings",
    "prohibitions",
}
EXPECTED_DEPENDENCY_BINDINGS = [
    {
        "id": "P02",
        "disposition": "accepted",
        "head": "8faa5fb9899231ebf5f87e78bb171544c11b79d7",
        "phase_receipt": "https://github.com/organvm/limen/issues/2172#issuecomment-5270095170",
    },
    {
        "id": "C03",
        "disposition": "current-offer-integrated-with-reader-gate",
        "offer_source_head": "b6af8086c9050634313f519c29a6dfcb922c3721",
        "integrated_main_head": "8f89ad16ca1df84b00cb8227c88f368d0d64631a",
        "accepted_through": "PSP-P03-W06",
        "accepted_head": "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec",
        "reader_gate": {
            "work_id": "PSP-P03-W07",
            "issue": "https://github.com/organvm/limen/issues/2188",
            "state": "genuine-reader-blocked",
        },
    },
    {
        "id": "C04",
        "disposition": "merged-prepared-proof",
        "limen_pr": 2313,
        "limen_source_head": "1bb0ceca162129f6c90ae47958712bb19cd99cbb",
        "limen_integrated_main_head": "3f2269dd38865244f826aaff4818912a636167be",
        "portfolio_pr": 220,
        "portfolio_source_head": "8974543ba9675ed0504141895812476efef5dd80",
        "portfolio_integrated_main_head": "a01b6d85f78d2d744c0c994f7220081bb54a85c5",
    },
    {
        "id": "C06",
        "disposition": "merged-prepared-public-surface-relay",
        "limen_pr": 2317,
        "limen_source_head": "854b6385de6b340485baaf59b1be55bd4d243a4d",
        "limen_integrated_main_head": "690617fc2aeea79acfe5604799e6413d70b6e4dd",
        "portfolio_pr": 221,
        "portfolio_source_head": "7c150fc81184df1715824be28b32472baadbb3b6",
        "portfolio_integrated_main_head": "797cda3fb903b07d4152e5bbde9f468beeeab3e0",
        "visual_directions": "UNSELECTED",
    },
    {
        "id": "C07",
        "disposition": "merged-prepared-private-inbound",
        "limen_pr": 2318,
        "limen_source_head": "9d81552a65cab1a8785e74251853881ac1957925",
        "limen_integrated_main_head": "799c4bbe80634bb870e379061d03d08a74ea5405",
    },
]
EXPECTED_PROHIBITIONS = [
    "No binding promotes a prepared dependency, reader evidence, or external effect.",
    "No binding authorizes publication, scheduling, sending, capture activation, analytics mutation, deployment, or formal closure.",
]
EMAIL_RE = re.compile(r"\b[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SECRET_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|Bearer\s+\S+|AKIA[0-9A-Z]{16})\b")


class ContentError(ValueError):
    """A staged-content rule was violated."""


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContentError(f"duplicate JSON member: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError, ContentError) as error:
        raise ContentError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContentError(f"{path} must contain an object")
    return value


@lru_cache(maxsize=1)
def expected_assignment_requirements() -> dict[str, dict[str, Any]]:
    """Derive execution requirements without persisting provider model names."""
    program = runpy.run_path(str(PROGRAM_SCRIPT))
    graph = program["index_program"](program["load_manifest"]())
    packets = [graph["work_by_id"][work_id] for work_id in WORK_IDS]
    chunk_assignment = program["chunk_assignment_for"]("PSP-C08", graph)
    requirements: dict[str, dict[str, Any]] = {
        "PSP-C08": {
            "selection": "runtime_catalog",
            "role": "chunk_conductor",
            "effort": chunk_assignment["effort"],
            "capabilities": sorted({capability for packet in packets for capability in packet["capabilities"]}),
        }
    }
    for work_id in WORK_IDS:
        packet = graph["work_by_id"][work_id]
        assignment = program["model_assignment_for"](work_id, graph)
        requirements[work_id] = {
            "selection": "runtime_catalog",
            "reasoning": packet["reasoning"],
            "effect": packet["effect"],
            "effort": assignment["effort"],
            "capabilities": packet["capabilities"],
        }
    return requirements


def flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(flatten(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(flatten(item) for item in value)
    return ""


def validate_private_text(value: Any, label: str) -> None:
    text = flatten(value)
    for address in EMAIL_RE.findall(text):
        if not address.endswith("@example.invalid"):
            raise ContentError(f"{label} contains an email address")
    if SECRET_RE.search(text):
        raise ContentError(f"{label} contains a credential-shaped value")
    if "private evidence" in text.lower() and "not" not in text.lower():
        raise ContentError(f"{label} presents private evidence instead of a redaction")


def freshness_state(review_by: str, reference_date: str) -> str:
    due = date.fromisoformat(review_by)
    reference = date.fromisoformat(reference_date)
    if due < reference:
        return "expired"
    if due == reference:
        return "review_due"
    return "current"


def expected_dry_run(control: dict[str, Any]) -> dict[str, Any]:
    assets: list[dict[str, str]] = []
    for asset in control["assets"]:
        disposition = "held-private"
        if asset.get("external_gate") == "HG-PUBLIC-IDENTITY":
            disposition = "held-HG-PUBLIC-IDENTITY"
        elif asset.get("external_gate") == "HG-PUBLICATION-SEND":
            disposition = "held-HG-PUBLICATION-SEND"
        elif asset["work_id"] == "PSP-P09-W07":
            disposition = "held-canonical-source"
        assets.append({"asset_id": asset["id"], "disposition": disposition})
    return {
        "schema": "psp-c08-dry-run-publication/v1",
        "mode": "dry-run-only",
        "network_calls": [],
        "send_count": 0,
        "publish_count": 0,
        "approval_refs": [],
        "canonical_source": "withheld-until-owner-approved",
        "assets": assets,
    }


def validate(root: Path) -> dict[str, Any]:
    content = root / CONTENT_RELATIVE
    for name in REQUIRED_FILES:
        if not (content / name).is_file():
            raise ContentError(f"missing {CONTENT_RELATIVE / name}")

    register = load_json(content / "claim-source-register.json")
    bindings = load_json(content / "dependency-bindings.json")
    control = load_json(content / "content-control.json")
    fixtures = load_json(content / "narrative-fixtures.json")
    review = load_json(content / "review-gates.json")
    analytics = load_json(content / "campaign-analytics-schema.json")
    freshness = load_json(content / "freshness-withdrawal-policy.json")
    dry_run = load_json(content / "dry-run-publication-package.json")

    if control.get("state") != "private-staging-only":
        raise ContentError("content control must remain private-staging-only")
    if set(bindings) != EXPECTED_BINDING_DOCUMENT_KEYS:
        raise ContentError("dependency binding document must use the exact public-safe schema")
    if bindings.get("schema") != "psp-c08-dependency-bindings/v2":
        raise ContentError("dependency bindings must use schema v2")
    if (
        bindings.get("state") != "PREPARED"
        or bindings.get("counts_as_closure") is not False
        or bindings.get("scope") != "private-staging-only"
    ):
        raise ContentError("dependency bindings must remain PREPARED without closure credit")
    if bindings.get("assignment_policy") != ASSIGNMENT_POLICY:
        raise ContentError("assignment policy must require runtime catalog discovery and fail closed")
    if bindings.get("assignment_requirements") != expected_assignment_requirements():
        raise ContentError("assignment requirements drifted from the canonical runtime registry")
    if bindings.get("bindings") != EXPECTED_DEPENDENCY_BINDINGS:
        raise ContentError("dependency bindings drifted from the accepted source and integration receipts")
    if bindings.get("prohibitions") != EXPECTED_PROHIBITIONS:
        raise ContentError("dependency binding prohibitions must remain exact")
    binding_items = {item.get("id"): item for item in bindings.get("bindings", [])}
    if set(binding_items) != REQUIRED_BINDINGS:
        raise ContentError("dependency bindings must cover the current P02/C03/C04/C06/C07 chain exactly")
    source_ids = {entry.get("id") for entry in register.get("sources", [])}
    assets = control.get("assets", [])
    if {asset.get("work_id") for asset in assets} != WORK_ID_SET:
        raise ContentError("content control must cover PSP-P09-W01 through PSP-P09-W08 exactly")
    if len({asset.get("id") for asset in assets}) != len(assets):
        raise ContentError("content asset IDs must be unique")
    for asset in assets:
        if not set(asset.get("source_ids", [])) <= source_ids:
            raise ContentError(f"{asset.get('id')} references an unknown source")
        citations = set(re.findall(r"\[\^([A-Z0-9-]+)\]", asset.get("draft", "")))
        if citations != set(asset.get("source_ids", [])):
            raise ContentError(f"{asset.get('id')} draft citations must exactly match source_ids")
        if asset.get("external_gate") not in {None, "HG-PUBLIC-IDENTITY", "HG-PUBLICATION-SEND"}:
            raise ContentError(f"{asset.get('id')} declares an unknown external gate")
        if freshness_state(asset["review_by"], control["reference_date"]) != "current":
            raise ContentError(f"{asset.get('id')} is not fresh at the recorded reference date")
        validate_private_text(asset, asset["id"])

    transformations = control.get("channel_transformations", [])
    if {item.get("channel") for item in transformations} != {
        "technical-thread",
        "newsletter-blurb",
        "community-post",
        "recruiter-pointer",
    }:
        raise ContentError("channel transformations must cover the four staged channel forms")
    for transformation in transformations:
        if set(transformation.get("requires", [])) != {"canonical_source", "door_tag", "expiry"}:
            raise ContentError(f"{transformation.get('channel')} must require source, door tag, and expiry")
        if not set(transformation.get("allowed_work_ids", [])) <= WORK_ID_SET:
            raise ContentError(f"{transformation.get('channel')} has an invalid work scope")

    if fixtures.get("state") != "synthetic-only":
        raise ContentError("narrative fixtures must remain synthetic-only")
    for fixture in (fixtures.get("architecture", {}), fixtures.get("incident", {})):
        if fixture.get("private_data") != "[redacted]":
            raise ContentError("narrative fixture must use the exact private-data redaction")
        validate_private_text(fixture, "narrative fixture")

    if review.get("state") != "review-pending":
        raise ContentError("review gates may not self-approve")
    approvals = {item.get("id"): item.get("status") for item in review.get("external_approvals", [])}
    if approvals != {"HG-PUBLIC-IDENTITY": "unapproved", "HG-PUBLICATION-SEND": "unapproved"}:
        raise ContentError("external review gates must remain exactly unapproved")
    if analytics.get("mode") != "dry-run-only":
        raise ContentError("campaign analytics must remain dry-run-only")
    for record in analytics.get("fixtures", []):
        if record.get("is_synthetic") is not True:
            raise ContentError("analytics fixture must be synthetic")
        if record.get("approval_ref") != "none":
            raise ContentError("analytics fixture may not imply approval")

    if freshness.get("default_review_days") != 30:
        raise ContentError("freshness policy must retain the staged 30-day review window")
    if freshness_state("2026-08-11", freshness["reference_date"]) != "expired":
        raise ContentError("freshness classifier must quarantine an expired asset")
    if dry_run != expected_dry_run(control):
        raise ContentError("dry-run package does not match deterministic staged assets")
    if dry_run["send_count"] or dry_run["publish_count"] or dry_run["network_calls"] or dry_run["approval_refs"]:
        raise ContentError("dry-run package must have no external effects or approvals")
    return {"assets": len(assets), "mode": dry_run["mode"], "status": "ok"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the private staging package")
    parser.add_argument("--dry-run", action="store_true", help="print the deterministic no-effect publication package")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if not args.check and not args.dry_run:
        parser.error("one of --check or --dry-run is required")
    try:
        control = load_json(args.root / CONTENT_RELATIVE / "content-control.json")
        if args.dry_run:
            print(json.dumps(expected_dry_run(control), indent=2, sort_keys=True))
        if args.check:
            print(json.dumps(validate(args.root), sort_keys=True))
    except ContentError as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
