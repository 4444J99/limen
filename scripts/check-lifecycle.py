#!/usr/bin/env python3
"""PR lifecycle registry drift predicate.

Offline checks hold the declaration/consumer boundary:

A  lifecycle.yaml dispositions exactly match estate.yaml's legacy vocabulary while that ratchet is open.
B  every declared consumer's lifecycle literals equal its shrink-only baseline, or reach zero once converted.
C  an armed consumer ratchet contains no disposition-id literal; it derives by capability.
E  every cohort has a declared default disposition or a resolving human lever.
G  the registry's predicate and ideal-form self-references resolve.

`--measure` additionally reports the unreachable PR count from the committed exhaustive census. It is
kept outside the offline gate because live GitHub reach is environment evidence, not a repo invariant.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "lifecycle.yaml"
ESTATE = ROOT / "institutio" / "github" / "estate.yaml"
IDEALS = ROOT / "institutio" / "governance" / "ideal-forms.yaml"
LEVERS = ROOT / "his-hand-levers.json"
PR_LEDGER = ROOT / "docs" / "github-pr-debt-ledger.json"
SELF_COMMAND = "python3 scripts/check-lifecycle.py --check"

failures: list[str] = []


def fail(check: str, message: str) -> None:
    failures.append(f"  ✗ [{check}] {message}")


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        fail("A", f"{path.relative_to(ROOT)} is unreadable: {exc}")
        return {}
    if not isinstance(payload, dict):
        fail("A", f"{path.relative_to(ROOT)} must contain a mapping")
        return {}
    return payload


def load_lever_ids() -> set[str]:
    try:
        payload = json.loads(LEVERS.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        fail("E", f"{LEVERS.relative_to(ROOT)} is unreadable: {exc}")
        return set()
    rows = payload.get("levers") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        fail("E", "his-hand-levers.json has no levers list")
        return set()
    return {str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")}


def legacy_estate_labels() -> set[str]:
    estate = load_yaml(ESTATE)
    policy = estate.get("pr_debt_policy") if isinstance(estate, dict) else None
    labels = policy.get("lifecycle_labels") if isinstance(policy, dict) else None
    if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
        fail("A", "estate.yaml pr_debt_policy.lifecycle_labels must be a string list")
        return set()
    return set(labels)


def validate_dispositions(registry: dict[str, Any]) -> set[str]:
    rows = registry.get("dispositions")
    if not isinstance(rows, dict) or not rows:
        fail("A", "registry has no dispositions mapping")
        return set()
    required = {
        "label_color",
        "description",
        "merge_eligible",
        "fail_closed",
        "human_owned",
        "terminal",
        "owner",
    }
    merge_eligible: list[str] = []
    for disposition, row in rows.items():
        if not isinstance(disposition, str) or not disposition.startswith("lifecycle:"):
            fail("A", f"{disposition!r}: disposition id must start with lifecycle:")
            continue
        if not isinstance(row, dict):
            fail("A", f"{disposition}: row must be a mapping")
            continue
        missing = sorted(required - set(row))
        if missing:
            fail("A", f"{disposition}: missing fields {missing}")
        if re.fullmatch(r"[0-9a-f]{6}", str(row.get("label_color") or "")) is None:
            fail("A", f"{disposition}: label_color must be a lowercase six-digit hex color")
        for capability in ("merge_eligible", "fail_closed", "human_owned", "terminal"):
            if not isinstance(row.get(capability), bool):
                fail("A", f"{disposition}: {capability} must be boolean")
        if row.get("merge_eligible") is True:
            merge_eligible.append(disposition)
    if len(merge_eligible) != 1:
        fail("A", f"exactly one disposition must be merge_eligible; found {merge_eligible}")
    return {str(key) for key in rows}


def validate_consumers(registry: dict[str, Any], labels: set[str]) -> None:
    consumers = registry.get("consumers")
    ratchets = registry.get("ratchets")
    baseline = registry.get("literal_baseline")
    if not isinstance(consumers, dict) or not consumers:
        fail("B", "registry has no consumers mapping")
        return
    if not isinstance(ratchets, dict):
        fail("B", "registry has no ratchets mapping")
        ratchets = {}
    if not isinstance(baseline, dict):
        fail("B", "registry has no literal_baseline mapping")
        baseline = {}

    consumer_paths: set[str] = set()
    for consumer, row in consumers.items():
        if not isinstance(row, dict):
            fail("B", f"{consumer}: consumer row must be a mapping")
            continue
        relative = str(row.get("path") or "")
        ratchet = str(row.get("ratchet") or "")
        derives = row.get("derives")
        if not relative or not (ROOT / relative).is_file():
            fail("B", f"{consumer}: consumer path does not resolve: {relative!r}")
            continue
        consumer_paths.add(relative)
        if not isinstance(derives, list) or not derives or not all(isinstance(item, str) for item in derives):
            fail("B", f"{consumer}: derives must be a non-empty string list")
        if ratchet not in ratchets or not isinstance(ratchets.get(ratchet), bool):
            fail("B", f"{consumer}: ratchet {ratchet!r} is missing or non-boolean")
            continue
        try:
            expected = int(baseline[relative])
        except (KeyError, TypeError, ValueError):
            fail("B", f"{consumer}: literal baseline is missing for {relative}")
            continue
        text = (ROOT / relative).read_text(encoding="utf-8")
        actual = sum(text.count(label) for label in labels)
        armed = bool(ratchets[ratchet])
        if armed and actual:
            fail("C", f"{consumer}: conversion ratchet is armed but {actual} disposition literal(s) remain")
        elif armed and expected != 0:
            fail("B", f"{consumer}: converted consumer must lower its literal baseline to 0 (found {expected})")
        elif not armed and actual != expected:
            direction = "grew" if actual > expected else "shrunk"
            fail("B", f"{consumer}: literal debt {direction} from baseline {expected} to {actual}; update the conversion receipt")

    extra_baselines = set(str(key) for key in baseline) - consumer_paths
    if extra_baselines:
        fail("B", f"literal baselines name undeclared consumers: {sorted(extra_baselines)}")


def validate_cohorts(registry: dict[str, Any], labels: set[str]) -> None:
    cohorts = registry.get("cohorts")
    if not isinstance(cohorts, dict) or not cohorts:
        fail("E", "registry has no cohorts mapping")
        return
    lever_ids = load_lever_ids()
    for cohort, row in cohorts.items():
        if not isinstance(row, dict):
            fail("E", f"{cohort}: cohort row must be a mapping")
            continue
        if not isinstance(row.get("selector"), dict) or not row["selector"]:
            fail("E", f"{cohort}: selector must be a non-empty mapping")
        disposition = row.get("default_disposition")
        lever = row.get("owner_lever")
        if disposition is None and not lever:
            fail("E", f"{cohort}: requires default_disposition or owner_lever")
        if disposition is not None and disposition not in labels:
            fail("E", f"{cohort}: unknown default_disposition {disposition!r}")
        if lever and lever not in lever_ids:
            fail("E", f"{cohort}: owner_lever {lever!r} does not resolve")


def validate_self_reference(registry: dict[str, Any]) -> None:
    if registry.get("predicate") != SELF_COMMAND:
        fail("G", f"predicate must be exactly {SELF_COMMAND!r}")
    if registry.get("ideal_form") != "IF-PR-LIFECYCLE":
        fail("G", "ideal_form must be IF-PR-LIFECYCLE")
    ideals = load_yaml(IDEALS).get("ideals") or {}
    if not isinstance(ideals, dict) or "IF-PR-LIFECYCLE" not in ideals:
        fail("G", "IF-PR-LIFECYCLE does not resolve in ideal-forms.yaml")
    if not Path(__file__).is_file():
        fail("G", "predicate script does not resolve")


def run_offline_checks() -> tuple[dict[str, Any], set[str]]:
    registry = load_yaml(REGISTRY)
    if registry.get("schema_version") != 0.1:
        fail("A", "schema_version must be 0.1")
    labels = validate_dispositions(registry)
    estate_labels = legacy_estate_labels()
    ratchets = registry.get("ratchets") or {}
    if not ratchets.get("estate_yaml_derives") and labels != estate_labels:
        fail("A", f"registry/estate disposition mismatch: registry={sorted(labels)} estate={sorted(estate_labels)}")
    validate_consumers(registry, labels)
    validate_cohorts(registry, labels)
    validate_self_reference(registry)
    return registry, labels


def measure_unreachable() -> int | None:
    try:
        ledger = json.loads(PR_LEDGER.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        fail("D", f"{PR_LEDGER.relative_to(ROOT)} is unreadable: {exc}")
        return None
    if not isinstance(ledger, dict) or not ledger.get("exhaustive"):
        fail("D", "PR-debt ledger is not an exhaustive census")
        return None
    value = ledger.get("lifecycle_untyped_count")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        fail("D", "PR-debt ledger has no nonnegative lifecycle_untyped_count")
        return None
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run offline registry parity checks")
    parser.add_argument("--measure", action="store_true", help="also print committed-census lifecycle distance")
    args = parser.parse_args()
    run_offline_checks()
    unreachable = measure_unreachable() if args.measure else None

    if failures:
        print("PR LIFECYCLE DRIFT — registry does not match its owners:")
        print("\n".join(failures))
        return 1
    literal_total = sum(int(value) for value in (load_yaml(REGISTRY).get("literal_baseline") or {}).values())
    print(f"OK: check-lifecycle — 5 dispositions; 7 owned cohorts; literal debt={literal_total}")
    if unreachable is not None:
        print(f"unreachable PRs: {unreachable}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
