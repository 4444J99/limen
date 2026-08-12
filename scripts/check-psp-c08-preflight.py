#!/usr/bin/env python3
"""Validate the private PSP-C08 content-preflight package without external effects."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "docs" / "positioning" / "content"
sys.path.insert(0, str(ROOT / "scripts"))
from psp_c08_content import ContentError, validate as validate_content  # noqa: E402
REGISTER = CONTENT / "claim-source-register.json"
MEASUREMENT = CONTENT / "measurement-contract.json"
MANIFEST = CONTENT / "staging-manifest.json"
REQUIRED_FILES = (
    "README.md",
    "RELAY.md",
    "claim-source-register.json",
    "editorial-calendar.md",
    "flagship-engineering-report.md",
    "derivative-assets.md",
    "measurement-contract.json",
    "staging-manifest.json",
    "correction-withdrawal-contract.md",
    "assets/delivery-gates-flow.svg",
    "content-control.json",
    "narrative-fixtures.json",
    "review-gates.json",
    "campaign-analytics-schema.json",
    "freshness-withdrawal-policy.json",
    "dry-run-publication-package.json",
)
REQUIRED_WORK_IDS = tuple(f"PSP-P09-W0{number}" for number in range(1, 9))


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read {path.relative_to(ROOT)}: {error}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain an object")
    return value


def main() -> None:
    for name in REQUIRED_FILES:
        if not (CONTENT / name).is_file():
            fail(f"missing staged artifact: docs/positioning/content/{name}")

    register = load_json(REGISTER)
    if register.get("package_state") != "private-staging-only":
        fail("claim register must remain private-staging-only")

    sources = register.get("sources", [])
    allowed = {source.get("id") for source in sources if source.get("status") in {"verified", "ratified-method"}}
    if not {"CLM-LIMEN-OPERATING", "CLM-AUTHORSHIP", "CLM-PROOF-METHOD", "CLM-CAPTURE-DOORS"} <= allowed:
        fail("claim register is missing an admitted source")
    if sum(source.get("status") == "withheld" for source in sources) < 3:
        fail("claim register must retain all withheld-claim categories")

    gates = {gate.get("work_id"): gate for gate in register.get("external_gates", [])}
    for work_id, gate_name in (("PSP-P09-W02", "HG-PUBLIC-IDENTITY"), ("PSP-P09-W08", "HG-PUBLICATION-SEND")):
        gate = gates.get(work_id)
        if not gate or gate.get("gate") != gate_name or gate.get("state") != "unapproved":
            fail(f"{work_id} must retain its unapproved {gate_name} boundary")

    manifest = load_json(MANIFEST)
    if manifest.get("state") != "private-preflight":
        fail("staging manifest must remain a private preflight")
    work = {entry.get("id"): entry for entry in manifest.get("work", [])}
    if set(work) != set(REQUIRED_WORK_IDS):
        fail("staging manifest must cover PSP-P09-W01 through PSP-P09-W08 exactly")
    for work_id, entry in work.items():
        if entry.get("state") not in {"staged-not-complete", "human-gated-not-complete", "withheld-until-sanitized-source"}:
            fail(f"{work_id} has an invalid preflight state")
        if not entry.get("source_ids"):
            fail(f"{work_id} lacks source coverage")

    measurement = load_json(MEASUREMENT)
    fixture = measurement.get("synthetic_fixture", {})
    if measurement.get("state") != "synthetic-staging-only" or fixture.get("is_synthetic") is not True:
        fail("measurement contract must keep its fixture explicitly synthetic")
    if measurement.get("external_effect_boundary", {}).get("send_gate") != "HG-PUBLICATION-SEND":
        fail("measurement contract must name the publication-send gate")

    relay = (CONTENT / "RELAY.md").read_text(encoding="utf-8")
    if not re.search(r"Reconciliation base head \| `[0-9a-f]{40}`", relay):
        fail("relay must carry one full reconciliation base head")
    for marker in (
        "https://github.com/organvm/limen/pull/2316",
        "c7c932205faa405e291f8030235a73cedeaa219e",
        "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec",
        "23712398c6586e005c303eff632604985cd0a25c",
        "9bcc4606b68da83dc0878b060989d35c3b649d7f",
        "a72a05d917bf14d53221c7d02ec52d3786b4f88e",
        "6ff7d4e6bd9003213e2675f4e8d59c41a3726b3b",
        "6cb7f291ef758d26d136620398c6e9c09f74d0ea",
        "b3c8dcb8ee461fad7be971efc0fc60ca27726668",
        "6ee6bd7d546a56474cf3bd38e06fad794ab7bc45",
        "#2188/W07",
        "HG-PUBLIC-IDENTITY",
        "HG-PUBLICATION-SEND",
        "no publishing, distribution, capture activation",
    ):
        if marker not in relay:
            fail(f"relay lacks required public-safe receipt marker: {marker}")

    try:
        validate_content(ROOT)
    except ContentError as error:
        fail(f"private content controls invalid: {error}")

    print("PSP-C08 private content preflight passed: staged sources, gates, synthetic measurement, and no-effect publication controls are intact")


if __name__ == "__main__":
    main()
