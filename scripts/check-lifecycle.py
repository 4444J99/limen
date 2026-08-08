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
import subprocess
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
TERMINAL_LEVER_STATES = frozenset({"discharged", "retired", "done", "closed"})
ADMISSION_CONTRACT = {
    "draft": False,
    "mergeable": True,
    "required_checks": "green",
    "conflicts": "none",
}
INITIAL_LITERAL_CEILING = {
    "scripts/merge-drain.py": 6,
    "scripts/pr-lifecycle-manifest.py": 5,
    "scripts/pr-lifecycle-estate-manifest.py": 6,
    "scripts/gitvs.py": 8,
}

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


def load_levers() -> dict[str, str]:
    try:
        payload = json.loads(LEVERS.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        fail("E", f"{LEVERS.relative_to(ROOT)} is unreadable: {exc}")
        return {}
    rows = payload.get("levers") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        fail("E", "his-hand-levers.json has no levers list")
        return {}
    return {
        str(row["id"]): str(row.get("status") or "")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }


def legacy_estate_policy() -> dict[str, Any]:
    estate = load_yaml(ESTATE)
    policy = estate.get("pr_debt_policy") if isinstance(estate, dict) else None
    if not isinstance(policy, dict):
        fail("A", "estate.yaml has no pr_debt_policy mapping")
        return {}
    return policy


def legacy_estate_labels(policy: dict[str, Any]) -> set[str]:
    labels = policy.get("lifecycle_labels")
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
    elif rows[merge_eligible[0]].get("admits") != ADMISSION_CONTRACT:
        fail(
            "A",
            f"{merge_eligible[0]}: admits must equal the typed merge admission contract",
        )
    return {str(key) for key in rows}


def previous_literal_baseline() -> dict[str, int] | None:
    """Read the prior exact tree when available so baseline debt cannot regrow."""
    relative = REGISTRY.relative_to(ROOT).as_posix()
    for revision in ("HEAD^1", "HEAD^"):
        result = subprocess.run(
            ["git", "show", f"{revision}:{relative}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            continue
        try:
            payload = yaml.safe_load(result.stdout) or {}
            baseline = payload.get("literal_baseline")
            if isinstance(baseline, dict):
                return {str(path): int(value) for path, value in baseline.items()}
        except (TypeError, ValueError, yaml.YAMLError):
            return None
    return None


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
        loader_markers = row.get("loader_markers")
        if not relative or not (ROOT / relative).is_file():
            fail("B", f"{consumer}: consumer path does not resolve: {relative!r}")
            continue
        consumer_paths.add(relative)
        if not isinstance(derives, list) or not derives or not all(isinstance(item, str) for item in derives):
            fail("B", f"{consumer}: derives must be a non-empty string list")
        if (
            not isinstance(loader_markers, list)
            or not loader_markers
            or not all(isinstance(item, str) and item for item in loader_markers)
        ):
            fail("C", f"{consumer}: loader_markers must declare observable registry derivation")
            loader_markers = []
        if ratchet not in ratchets or not isinstance(ratchets.get(ratchet), bool):
            fail("B", f"{consumer}: ratchet {ratchet!r} is missing or non-boolean")
            continue
        try:
            expected = int(baseline[relative])
        except (KeyError, TypeError, ValueError):
            fail("B", f"{consumer}: literal baseline is missing for {relative}")
            continue
        try:
            text = (ROOT / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            fail("B", f"{consumer}: consumer source is unreadable: {exc}")
            continue
        actual = sum(text.count(label) for label in labels)
        armed = bool(ratchets[ratchet])
        if armed and any(marker not in text for marker in loader_markers):
            missing_markers = [marker for marker in loader_markers if marker not in text]
            fail("C", f"{consumer}: armed derivation markers missing: {missing_markers}")
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

    previous = previous_literal_baseline()
    ceiling = previous or INITIAL_LITERAL_CEILING
    for relative, value in baseline.items():
        try:
            current = int(value)
            maximum = int(ceiling[relative])
        except (KeyError, TypeError, ValueError):
            fail("B", f"{relative}: no prior shrink-only literal ceiling")
            continue
        if current > maximum:
            fail("B", f"{relative}: literal baseline regrew from {maximum} to {current}")


def validate_cohorts(registry: dict[str, Any], labels: set[str]) -> None:
    cohorts = registry.get("cohorts")
    if not isinstance(cohorts, dict) or not cohorts:
        fail("E", "registry has no cohorts mapping")
        return
    levers = load_levers()
    precedence = registry.get("cohort_precedence")
    if not isinstance(precedence, list) or set(precedence) != set(cohorts):
        fail("E", "cohort_precedence must name every cohort exactly once")
        precedence = []
    elif precedence[0] != "draft" or precedence[-1] != "all":
        fail("E", "cohort_precedence must evaluate draft first and all last")
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
        if lever and lever not in levers:
            fail("E", f"{cohort}: owner_lever {lever!r} does not resolve")
        if disposition is None and lever and levers.get(str(lever)) in TERMINAL_LEVER_STATES:
            fail(
                "E",
                f"{cohort}: terminal owner_lever {lever!r} cannot replace a default disposition",
            )


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
    estate_policy = legacy_estate_policy()
    estate_labels = legacy_estate_labels(estate_policy)
    ratchets = registry.get("ratchets") or {}
    estate_derives = ratchets.get("estate_yaml_derives")
    if not isinstance(estate_derives, bool):
        fail("A", "ratchets.estate_yaml_derives must be boolean")
    elif not estate_derives and labels != estate_labels:
        fail("A", f"registry/estate disposition mismatch: registry={sorted(labels)} estate={sorted(estate_labels)}")
    elif estate_derives:
        if "lifecycle_labels" in estate_policy:
            fail("A", "converted estate.yaml must not retain lifecycle_labels")
        if estate_policy.get("lifecycle_registry") != "../governance/lifecycle.yaml":
            fail("A", "converted estate.yaml must point to ../governance/lifecycle.yaml")
    validate_consumers(registry, labels)
    validate_cohorts(registry, labels)
    validate_self_reference(registry)
    return registry, labels


def measure_unreachable(registry: dict[str, Any]) -> int | None:
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
    rows = ledger.get("pull_requests")
    if not isinstance(rows, list):
        fail("D", "PR-debt ledger has no pull_requests census")
        return None
    preservation_missing = sum(
        1
        for row in rows
        if isinstance(row, dict)
        and row.get("lifecycle_disposition") == "lifecycle:preservation"
        and row.get("lifecycle_disposition_source") != "label"
    )
    live_baseline = registry.get("live_baseline")
    metadata_drift = (
        live_baseline.get("lifecycle_label_metadata_drift_count")
        if isinstance(live_baseline, dict)
        else None
    )
    if isinstance(metadata_drift, bool) or not isinstance(metadata_drift, int) or metadata_drift < 0:
        fail("D", "live_baseline has no nonnegative lifecycle_label_metadata_drift_count")
        return None
    return value + preservation_missing + metadata_drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run offline registry parity checks")
    parser.add_argument("--measure", action="store_true", help="also print committed-census lifecycle distance")
    args = parser.parse_args()
    if not (args.check or args.measure):
        parser.error("one of --check or --measure is required")
    registry, _labels = run_offline_checks()
    unreachable = measure_unreachable(registry) if args.measure else None

    if failures:
        print("PR LIFECYCLE DRIFT — registry does not match its owners:")
        print("\n".join(failures))
        return 1
    literal_total = sum(int(value) for value in (registry.get("literal_baseline") or {}).values())
    print(f"OK: check-lifecycle — 5 dispositions; 7 owned cohorts; literal debt={literal_total}")
    if unreachable is not None:
        print(f"unreachable PRs: {unreachable}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
