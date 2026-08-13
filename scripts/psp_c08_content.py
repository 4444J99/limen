#!/usr/bin/env python3
"""Deterministic, no-effect validation and packaging for the PSP-C08 staged content set."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


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
WORK_IDS = {f"PSP-P09-W0{number}" for number in range(1, 9)}
REQUIRED_BINDINGS = {"P02", "C03", "C04", "C06", "C07"}
EMAIL_RE = re.compile(r"\b[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SECRET_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|Bearer\s+\S+|AKIA[0-9A-Z]{16})\b")


class ContentError(ValueError):
    """A staged-content rule was violated."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContentError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContentError(f"{path} must contain an object")
    return value


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
    if bindings.get("state") != "PREPARED" or bindings.get("counts_as_closure") is not False:
        raise ContentError("dependency bindings must remain PREPARED without closure credit")
    binding_items = {item.get("id"): item for item in bindings.get("bindings", [])}
    if set(binding_items) != REQUIRED_BINDINGS:
        raise ContentError("dependency bindings must cover the current P02/C03/C04/C06/C07 chain exactly")
    if binding_items["P02"].get("disposition") != "accepted":
        raise ContentError("P02 must be recorded as accepted")
    if binding_items["C03"].get("accepted_through") != "PSP-P03-W06":
        raise ContentError("C03 must stop formal acceptance at PSP-P03-W06")
    if binding_items["C03"].get("reader_gate", {}).get("state") != "genuine-reader-blocked":
        raise ContentError("C03 reader evidence must remain genuinely blocked")
    for binding_id in ("C04", "C06", "C07"):
        if not binding_items[binding_id].get("disposition", "").startswith("prepared-"):
            raise ContentError(f"{binding_id} must remain prepared")
    if binding_items["C06"].get("visual_directions") != "UNSELECTED":
        raise ContentError("C06 visual directions must remain unselected")
    source_ids = {entry.get("id") for entry in register.get("sources", [])}
    assets = control.get("assets", [])
    if {asset.get("work_id") for asset in assets} != WORK_IDS:
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
    if {item.get("channel") for item in transformations} != {"technical-thread", "newsletter-blurb", "community-post", "recruiter-pointer"}:
        raise ContentError("channel transformations must cover the four staged channel forms")
    for transformation in transformations:
        if set(transformation.get("requires", [])) != {"canonical_source", "door_tag", "expiry"}:
            raise ContentError(f"{transformation.get('channel')} must require source, door tag, and expiry")
        if not set(transformation.get("allowed_work_ids", [])) <= WORK_IDS:
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
