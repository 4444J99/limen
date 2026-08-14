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
    "dependency-bindings.json",
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
    def object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        value: dict = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON member: {key}")
            value[key] = item
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_without_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
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
        if entry.get("state") not in {
            "staged-not-complete",
            "human-gated-not-complete",
            "withheld-until-sanitized-source",
        }:
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
        "8faa5fb9899231ebf5f87e78bb171544c11b79d7",
        "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec",
        "b6af8086c9050634313f519c29a6dfcb922c3721",
        "8f89ad16ca1df84b00cb8227c88f368d0d64631a",
        "1bb0ceca162129f6c90ae47958712bb19cd99cbb",
        "3f2269dd38865244f826aaff4818912a636167be",
        "8974543ba9675ed0504141895812476efef5dd80",
        "a01b6d85f78d2d744c0c994f7220081bb54a85c5",
        "854b6385de6b340485baaf59b1be55bd4d243a4d",
        "690617fc2aeea79acfe5604799e6413d70b6e4dd",
        "7c150fc81184df1715824be28b32472baadbb3b6",
        "797cda3fb903b07d4152e5bbde9f468beeeab3e0",
        "9d81552a65cab1a8785e74251853881ac1957925",
        "799c4bbe80634bb870e379061d03d08a74ea5405",
        "#2188/W07",
        "UNSELECTED",
        "runtime catalog",
        "counts_as_closure=false",
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

    print(
        "PSP-C08 private content preflight passed: staged sources, gates, synthetic measurement, and no-effect publication controls are intact"
    )


if __name__ == "__main__":
    main()
